"""
planning/tests/test_grounded_environment.py

Issue 4 verification. Mocks tools.read_tools.get_connection the same way
planning/tests/test_fulfillment_decomposition.py (Issue 2) and
planning/fulfillment_demo.py already do -- no live database, no
ANTHROPIC_API_KEY needed (planning/model_provider.py's offline fallback),
matching this repo's existing convention.

Fake DB scenario, same shape as fulfillment_demo.py's:
  - "Brake Pad"     -> id=1, quantity=20  (plenty of stock, no alternatives)
  - "Oil Filter"    -> id=2, quantity=0   (out of stock)
  - "Oil Filter XL" -> id=3, quantity=5   (REAL, registered alternative for
                                            Oil Filter, in stock)
  - "Turbo Booster 3000" does not exist anywhere in this database --
    used below as the hallucinated/fabricated alternative a real model
    (or an ungrounded evaluator) might wrongly accept.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_ROOT = ROOT / "mcp-server"
for _p in (str(ROOT), str(MCP_SERVER_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from planning.fulfillment_decomposition import JobRequest  # noqa: E402
from planning.fulfillment_planning import decide_with_lats  # noqa: E402
from planning.grounded_environment import GroundedFulfillmentEnvironment  # noqa: E402
from planning.model_provider import get_llm  # noqa: E402
from planning.routing import Environment  # noqa: E402

_PARTS = {
    "Brake Pad": (1, "Brake Pad", 20),
    "Oil Filter": (2, "Oil Filter", 0),
    "Oil Filter XL": (3, "Oil Filter XL", 5),
}
# part_id -> [(alt_part_name,), ...], same shape suggest_alternative() returns
_ALTERNATIVES = {2: [("Oil Filter XL",)], 1: []}


def _fake_cursor():
    cursor = MagicMock()

    def execute(sql, params=()):
        cursor._sql = sql
        cursor._params = params

    def fetchall():
        sql = cursor._sql
        if "FROM SpareParts WHERE part_name LIKE" in sql:
            needle = cursor._params[0].strip("%")
            row = _PARTS.get(needle)
            return [row] if row else []
        if "FROM AlternativeParts" in sql:
            return _ALTERNATIVES.get(cursor._params[0], [])
        return []

    def fetchone():
        sql = cursor._sql
        if "SELECT quantity FROM SpareParts WHERE id" in sql:
            part_id = cursor._params[0]
            for row in _PARTS.values():
                if row[0] == part_id:
                    return (row[2],)
            return None
        return None

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = fetchall
    cursor.fetchone.side_effect = fetchone
    return cursor


def _fake_connection():
    conn = MagicMock()
    conn.cursor.return_value = _fake_cursor()
    return conn


@pytest.fixture()
def fake_db():
    with patch("tools.read_tools.get_connection", side_effect=_fake_connection):
        yield


# ---------------------------------------------------------------------
# Facts the grounded environment must be able to verify (Issue 4 req. 3)
# ---------------------------------------------------------------------


def test_verifies_requested_part_exists_and_its_real_quantity(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Brake Pad"])
    env = GroundedFulfillmentEnvironment(job)
    found = env.part_exists("Brake Pad")
    assert found == {"id": 1, "part_name": "Brake Pad"}
    assert env.real_stock(found["id"]) == 20
    assert env.part_exists("Turbo Booster 3000") is None


def test_verifies_alternative_exists_and_its_real_quantity(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    found = env.part_exists("Oil Filter XL")
    assert found == {"id": 3, "part_name": "Oil Filter XL"}
    assert env.real_stock(found["id"]) == 5


def test_verifies_registered_alternative_linkage(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    assert env.is_registered_alternative("Oil Filter XL") is True
    assert env.is_registered_alternative("Turbo Booster 3000") is False


# ---------------------------------------------------------------------
# evaluate() branches
# ---------------------------------------------------------------------


def test_accepts_direct_part_with_real_stock(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Brake Pad"])
    env = GroundedFulfillmentEnvironment(job)
    feedback = env.evaluate("proceed with the originally requested part (Brake Pad, quantity 20).")
    assert feedback.success is True
    assert feedback.score == 1.0


def test_rejects_direct_part_that_is_actually_out_of_stock(fake_db):
    """Even if the candidate text itself claims stock, the grounded
    environment re-checks the real database rather than trusting it."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    feedback = env.evaluate(
        "proceed with the originally requested part -- Oil Filter has plenty of stock, go ahead."
    )
    assert feedback.success is False
    assert any("quantity=0" in detail for detail in feedback.details)


def test_accepts_a_genuinely_valid_alternative(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    feedback = env.evaluate("proceed with alternative 'Oil Filter XL' (qty=5); the original part has no stock.")
    assert feedback.success is True
    assert feedback.score == 1.0


def test_delay_is_always_grounded_safe(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    feedback = env.evaluate("delay the job -- neither the part nor any alternative has stock.")
    assert feedback.success is True


def test_unparseable_candidate_is_rejected_as_ungrounded(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    feedback = env.evaluate("Proceed anyway without checking stock again.")
    assert feedback.success is False


# ---------------------------------------------------------------------
# The REAL grounded-critique catch (Issue 4 requirement 6):
#   - the model proposes an alternative
#   - an ungrounded/random evaluator could accept it
#   - the real database shows the alternative is unavailable/invalid
#   - the grounded evaluator rejects it
# ---------------------------------------------------------------------


def test_grounded_environment_catches_a_hallucinated_alternative_a_random_evaluator_would_accept(fake_db):
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    candidate_state = (
        "proceed with alternative 'Turbo Booster 3000' (qty=99); it is a suitable "
        "substitute for the Oil Filter and is currently in stock."
    )

    # The ungrounded evaluator ignores `state` completely (see
    # planning/vendor/planning_lab/algorithms/environment.py) -- seeded here
    # with an rng draw that clears its own success_threshold, demonstrating
    # concretely that it WOULD accept this fabricated candidate.
    ungrounded = Environment(success_threshold=0.6, rng=random.Random(0))
    ungrounded_feedback = ungrounded.evaluate(candidate_state)
    assert ungrounded_feedback.success is True  # the random evaluator is fooled

    # The grounded evaluator checks the real database: "Turbo Booster 3000"
    # does not exist in SpareParts at all.
    grounded = GroundedFulfillmentEnvironment(job)
    grounded_feedback = grounded.evaluate(candidate_state)
    assert grounded_feedback.success is False
    assert any("does not exist in the real SpareParts table" in detail for detail in grounded_feedback.details)


def test_grounded_environment_catches_a_real_part_never_offered_as_this_jobs_alternative(fake_db):
    """"Turbo Booster 3000" doesn't exist at all (previous test). This
    test covers the other invalid case in requirement 3: a real,
    in-stock part that exists in SpareParts but was never actually
    linked as an AlternativeParts row for the requested part -- i.e. "an
    alternative actually exists" fails even though the named part is
    real."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    env = GroundedFulfillmentEnvironment(job)
    # Brake Pad is real and in stock, but AlternativeParts has no row
    # linking it to Oil Filter (see _ALTERNATIVES above).
    feedback = env.evaluate("proceed with alternative 'Brake Pad' (qty=20); use it instead.")
    assert feedback.success is False
    assert any("not a registered AlternativeParts entry" in detail for detail in feedback.details)


# ---------------------------------------------------------------------
# Integration with the existing Issue 3 LATS wiring (requirement 5) --
# PS/ToT/LATS algorithms themselves are untouched; only the default
# environment decide_with_lats() constructs changes.
# ---------------------------------------------------------------------


def test_decide_with_lats_uses_the_grounded_environment_by_default(fake_db):
    """No `environment=` passed -- decide_with_lats must default to
    GroundedFulfillmentEnvironment, and a genuinely valid, real,
    in-stock, registered alternative must be accepted end-to-end through
    the unmodified vendored lats() search loop."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()
    findings = "Oil Filter: id=2 quantity=0\nOil Filter: alternatives=[Oil Filter XL (qty=5)]"

    result = decide_with_lats(job, findings, llm)

    assert result.success is True
    assert "Oil Filter XL" in result.output


def test_decide_with_lats_grounded_environment_rejects_a_fabricated_finding(fake_db):
    """Feed decide_with_lats a findings string that names an alternative
    absent from the real (mocked) database. The offline LLM double
    faithfully proposes it (it only ever echoes back what the prompt told
    it), but the grounded environment -- wired in as the default -- must
    still reject it against the real database on every branch, so the
    run never reports success. n_actions=1 isolates the
    proceed-with-fabricated-alternative branch (the offline double's
    second, always-available candidate is a plain delay, which is
    grounded-safe by construction and would otherwise mask the catch)."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()
    findings = "Oil Filter: id=2 quantity=0\nOil Filter: alternatives=[Turbo Booster 3000 (qty=99)]"

    result = decide_with_lats(job, findings, llm, iterations=2, n_actions=1)

    assert result.success is False
    assert "Turbo Booster 3000" in result.output  # the rejected candidate, not a fabricated success
    root_feedback = [child.feedback for child in result.root.children if child.feedback is not None]
    assert root_feedback  # at least one grounded evaluation actually ran
    assert all(not feedback.success for feedback in root_feedback)
    assert any(
        "does not exist in the real SpareParts table" in detail
        for feedback in root_feedback
        for detail in feedback.details
    )

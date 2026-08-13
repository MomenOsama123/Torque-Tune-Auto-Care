"""
planning/tests/test_self_correction.py

Issue 5 verification. Same fake-DB convention as
planning/tests/test_grounded_environment.py (Issue 4) -- no live
database, no ANTHROPIC_API_KEY needed (planning/model_provider.py's
offline fallback).

Fake DB scenario (same shape as test_grounded_environment.py's):
  - "Oil Filter"          -> id=2, quantity=0   (out of stock)
  - "Oil Filter XL"       -> id=3, quantity=5   (REAL, registered
                                                   alternative for Oil
                                                   Filter, in stock)
  - "Turbo Booster 3000" does not exist anywhere in this database --
    used below as the fabricated alternative a first Reflexion trial
    proposes and the grounded environment must reject.
"""

from __future__ import annotations

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
from planning.grounded_environment import GroundedFulfillmentEnvironment  # noqa: E402
from planning.model_provider import get_llm  # noqa: E402
from planning.self_correction import (  # noqa: E402
    decide_with_reflexion,
    refine_customer_notification,
)

_PARTS = {
    "Oil Filter": (2, "Oil Filter", 0),
    "Oil Filter XL": (3, "Oil Filter XL", 5),
}
_ALTERNATIVES = {2: [("Oil Filter XL",)]}


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
# Reflexion, on the final decision (Issue 5 requirement 2 + 3):
# episodic memory actually transfers between trials, and a failed
# trial's reflection provably changes the next trial's outcome.
# ---------------------------------------------------------------------


def test_decide_with_reflexion_defaults_to_the_grounded_environment(fake_db):
    """No `environment=` passed -- same default convention as Issue 4's
    decide_with_lats. A genuinely valid, real, in-stock, registered
    alternative is accepted on the first trial."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()
    findings = "Oil Filter: id=2 quantity=0\nOil Filter: alternatives=[Oil Filter XL (qty=5)]"

    result = decide_with_reflexion(job, findings, llm, max_trials=2)

    assert result.success is True
    assert "Oil Filter XL" in result.output
    assert len(result.trials) == 1  # succeeded on the first trial, no reflection needed


def test_a_failed_trials_reflection_changes_the_next_trials_outcome(fake_db):
    """The real causal demonstration Issue 5 requirement 3 asks for:
    trial 1 proposes a fabricated alternative ('Turbo Booster 3000') that
    the grounded environment rejects; the reflection it generates names
    the genuinely available alternative from this job's own findings;
    trial 2's attempt applies that reflection and succeeds. If episodic
    memory were NOT actually passed to the next trial, trial 2 would
    repeat the identical (deterministic, offline) trial-1 attempt and
    fail again."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()
    findings = (
        "Oil Filter: id=2 quantity=0\n"
        "Oil Filter: alternatives=[Turbo Booster 3000 (qty=99), Oil Filter XL (qty=5)]"
    )

    result = decide_with_reflexion(job, findings, llm, max_trials=3)

    assert len(result.trials) == 2
    trial_1, trial_2 = result.trials

    # Trial 1: fabricated alternative, grounded-rejected, real reflection produced.
    assert "Turbo Booster 3000" in trial_1.attempt
    assert trial_1.feedback.success is False
    assert any("does not exist in the real SpareParts table" in d for d in trial_1.feedback.details)
    assert trial_1.reflection is not None
    assert "Oil Filter XL" in trial_1.reflection

    # Trial 2: applied the reflection, proposed the real alternative, grounded-accepted.
    assert "Oil Filter XL" in trial_2.attempt
    assert "Turbo Booster 3000" not in trial_2.attempt
    assert trial_2.feedback.success is True

    # Overall result reflects the eventual success, not the first failure.
    assert result.success is True
    assert "Oil Filter XL" in result.output
    assert result.memory  # the episodic buffer that carried the lesson is non-empty


def test_reflexion_reports_failure_and_best_attempt_when_no_trial_succeeds(fake_db):
    """No real alternative anywhere in the findings -- every trial's
    fabricated/absent candidate is grounded-rejected, so the loop
    exhausts max_trials and honestly reports failure (not a fabricated
    success)."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()
    findings = "Oil Filter: id=2 quantity=0\nOil Filter: alternatives=[Turbo Booster 3000 (qty=99)]"

    result = decide_with_reflexion(job, findings, llm, max_trials=2)

    assert result.success is False
    assert len(result.trials) == 2


# ---------------------------------------------------------------------
# Self-Refine, on the cheap sub-task (Issue 5 requirement 1).
# ---------------------------------------------------------------------


def test_refine_customer_notification_wraps_issue3s_draft_notification(fake_db):
    """refine_customer_notification() must produce a genuine draft (via
    Issue 3's draft_notification -- not a duplicate prompt) and then run
    it through the vendored reflect_and_refine()."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()

    result = refine_customer_notification(job, "delay the job -- nothing is in stock.", llm)

    assert result.draft  # a real first-pass draft exists
    assert result.critique  # a critique was produced
    assert result.revised  # a final deliverable exists


def test_self_refine_critique_echoes_the_real_deterministic_checks(fake_db):
    """The offline critique (planning/model_provider._mock_self_refine_critique)
    must not invent a second opinion -- it echoes self_refine.py's own
    real, grounded deterministic_checks() report. A short draft fails the
    real word-count check, so the offline critique must surface that,
    and the resulting revision must differ from the original draft."""
    job = JobRequest(job_id="job-1", required_parts=["Oil Filter"])
    llm = get_llm()

    result = refine_customer_notification(job, "delay.", llm)

    assert "under 80 words" in result.critique or "no visible structure" in result.critique
    assert result.revised != result.draft


__all__: list[str] = []

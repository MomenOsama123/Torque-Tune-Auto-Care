"""
mcp-server/memory/semantic_memory.py

Long-term, consolidated knowledge, backed by the database. This is the
ONLY place semantic facts are written -- never by the promote-or-drop
router, never at message-write time. It's driven by a separate, periodic
consolidation pass (see run_consolidation() below and
memory/run_consolidation.py), which:

  1. expires stale facts first (expire_stale_facts),
  2. reads only episodes the router has promoted but nobody has
     consolidated yet (episodic.get_unconsolidated_episodes),
  3. extracts candidate facts from them via the shared LLM seam
     (rag/llm_client.py -- real Claude call if ANTHROPIC_API_KEY is set,
     otherwise a documented mock),
  4. applies each fact through update_fact(), which versions on change
     and always records *why* (change_reason) -- so a contradiction
     between two episodes is resolved explicitly and traceably, never by
     silently overwriting the old value.
"""

import json
from typing import List, Dict, Any
from databases.db import get_connection

try:
    from rag.llm_client import llm_call
except ImportError:  # pragma: no cover - path fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from rag.llm_client import llm_call


EXTRACTION_SYSTEM_PROMPT = (
    "You extract durable facts worth remembering long-term from a batch of "
    "promoted conversation episodes for an auto-parts inventory assistant. "
    "Return ONLY a JSON array of objects: "
    '{"fact_key": "<snake_case key>", "fact_value": "<value>", "reason": "<why>"}. '
    "Return an empty array if nothing durable is present."
)


class SemanticMemory:
    """
    Manages long-term, consolidated knowledge backed by the database.
    Supports versioning, updating existing facts, expiration, and explicit
    conflict resolution.
    """

    def __init__(self, llm_client=None):
        # Accepted for backward compatibility / dependency injection in
        # tests; actual extraction calls go through rag.llm_client's shared
        # seam (see llm_call import above).
        self.llm_client = llm_client

    # -----------------------------------------------------------------
    # Periodic consolidation entry point
    # -----------------------------------------------------------------
    def consolidate_episodes(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyzes a batch of episodes to extract new facts or update
        existing ones. Returns the list of {fact_key, fact_value, reason}
        objects it applied, so a periodic job (run_consolidation.py) can
        report what happened -- including any conflicts it resolved.
        """
        if not episodes:
            return []

        formatted = "\n".join(
            f"[episode {i}] {ep['content']}" for i, ep in enumerate(episodes)
        )
        user_prompt = f"extract_facts\n\n{formatted}"

        raw_text, _in_tok, _out_tok = llm_call(EXTRACTION_SYSTEM_PROMPT, user_prompt, want_json=True)

        try:
            extracted_facts = json.loads(raw_text)
        except (json.JSONDecodeError, TypeError):
            extracted_facts = []

        applied = []
        for fact in extracted_facts:
            key = fact.get("fact_key")
            value = fact.get("fact_value")
            reason = fact.get("reason", "extracted during consolidation")
            if not key or value is None:
                continue
            result = self.update_fact(key, value, change_reason=reason)
            applied.append({"fact_key": key, "fact_value": value, "reason": reason, **result})
        return applied

    # -----------------------------------------------------------------
    # Fact writes: versioning + explicit conflict trail
    # -----------------------------------------------------------------
    def update_fact(self, key: str, new_value: Any, change_reason: str = "manual update",
                     expires_at: str | None = None) -> Dict[str, Any]:
        """
        Updates an existing fact in the database. Sets the current active
        version to inactive and inserts a new active version -- so an old
        fact is never lost, only superseded, and every write says why.
        Returns {"status": "unchanged"|"created"|"updated"|"conflict_resolved", ...}.
        """
        conn = get_connection()
        cursor = conn.cursor()

        try:
            new_value_json = json.dumps(new_value)

            cursor.execute(
                "SELECT id, fact_value, version FROM SemanticMemory WHERE fact_key = ? AND is_active = 1",
                (key,),
            )
            active_row = cursor.fetchone()

            if active_row:
                current_id, current_val_json, current_version = active_row

                if current_val_json == new_value_json:
                    return {"status": "unchanged", "version": current_version}

                # A different value for a key that already has an active
                # fact IS a conflict between what was believed before and
                # what this consolidation pass just found -- log it
                # explicitly rather than overwriting silently.
                old_value = json.loads(current_val_json)
                conflict_note = (
                    f"conflict: '{key}' was '{old_value}', now '{new_value}'. "
                    f"Reason for change: {change_reason}"
                )
                print(f"[semantic_memory] {conflict_note}")

                cursor.execute(
                    "UPDATE SemanticMemory SET is_active = 0 WHERE id = ?",
                    (current_id,),
                )
                new_version = current_version + 1
                status = "conflict_resolved"
            else:
                new_version = 1
                status = "created"

            cursor.execute(
                """
                INSERT INTO SemanticMemory (fact_key, fact_value, version, is_active, change_reason, expires_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (key, new_value_json, new_version, change_reason, expires_at),
            )

            conn.commit()
            return {"status": status, "version": new_version}
        finally:
            conn.close()

    # -----------------------------------------------------------------
    # Expiration
    # -----------------------------------------------------------------
    def expire_stale_facts(self) -> List[str]:
        """
        Marks any active fact whose expires_at has passed as inactive.
        Run at the START of every consolidation pass (see
        run_consolidation.py) -- staleness handling is part of the same
        periodic job as extraction, not a separate thing anyone has to
        remember to run. Returns the list of fact_keys expired.
        """
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT fact_key FROM SemanticMemory
                WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
                """
            )
            expired_keys = [row[0] for row in cursor.fetchall()]

            if expired_keys:
                cursor.execute(
                    """
                    UPDATE SemanticMemory SET is_active = 0
                    WHERE is_active = 1 AND expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP
                    """
                )
                conn.commit()
            return expired_keys
        finally:
            conn.close()

    # -----------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------
    def get_active_facts(self) -> Dict[str, Any]:
        """Retrieves only the currently active facts for the LLM to use."""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT fact_key, fact_value FROM SemanticMemory WHERE is_active = 1"
            )
            rows = cursor.fetchall()

            active_knowledge = {}
            for row in rows:
                fact_key = row[0]
                fact_value = json.loads(row[1])
                active_knowledge[fact_key] = fact_value

            return active_knowledge
        finally:
            conn.close()

    def get_fact_history(self, key: str) -> List[Dict[str, Any]]:
        """All versions (active and superseded) of a fact, oldest first --
        the trace that proves conflicts are resolved explicitly, not
        silently overwritten."""
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT fact_value, version, is_active, change_reason, expires_at, updated_at
                FROM SemanticMemory WHERE fact_key = ? ORDER BY version ASC
                """,
                (key,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "fact_value": json.loads(row[0]),
                    "version": row[1],
                    "is_active": bool(row[2]),
                    "change_reason": row[3],
                    "expires_at": row[4],
                    "updated_at": str(row[5]),
                }
                for row in rows
            ]
        finally:
            conn.close()

import json
from typing import List, Dict, Any
from databases.db import get_connection

class EpisodicMemory:
    """
    Stores significant events and actions in the database.
    This serves as a persistent, chronological ledger of important occurrences.
    """
    def __init__(self):
        # We no longer need an in-memory list. 
        # The database handles the state now.
        pass

    def add_episode(self, event_type: str, content: Any, promotion_reason: str) -> None:
        """
        Saves a new episode directly into the SQL database.
        Called by the system when the Router outputs a 'promote' decision.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            # Convert the content object to a JSON string for storage
            content_json = json.dumps(content)
            
            cursor.execute(
                """
                INSERT INTO EpisodicMemory (event_type, content, promotion_reason)
                VALUES (?, ?, ?)
                """,
                (event_type, content_json, promotion_reason)
            )
            conn.commit()
        finally:
            conn.close()

    def get_all_episodes(self) -> List[Dict[str, Any]]:
        """
        Retrieve all episodes from the database.
        Used for the Semantic Consolidation step.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT event_type, content, promotion_reason, created_at 
                FROM EpisodicMemory 
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            
            episodes = []
            for row in rows:
                episodes.append({
                    "event_type": row[0],
                    "content": json.loads(row[1]),  # Parse JSON string back to dict
                    "promotion_reason": row[2],
                    "timestamp": str(row[3])
                })
            return episodes
        finally:
            conn.close()

    def get_recent_episodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent episodes for immediate context retrieval.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                """
                SELECT event_type, content, promotion_reason, created_at 
                FROM EpisodicMemory 
                ORDER BY id DESC 
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            
            episodes = []
            for row in rows:
                episodes.append({
                    "event_type": row[0],
                    "content": json.loads(row[1]),
                    "promotion_reason": row[2],
                    "timestamp": str(row[3])
                })
                
            # Reverse to maintain chronological order (oldest to newest) among the recent ones
            episodes.reverse()
            return episodes
        finally:
            conn.close()

    def get_unconsolidated_episodes(self) -> List[Dict[str, Any]]:
        """
        Episodes the promote-or-drop router has written but no consolidation
        pass has looked at yet. This is the ONLY feed semantic consolidation
        reads from -- it is never handed episodes directly by the router, and
        it is never called synchronously inside add_interaction(). A separate
        job (memory/run_consolidation.py) calls this on its own schedule.
        """
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT id, event_type, content, promotion_reason, created_at
                FROM EpisodicMemory
                WHERE consolidated = 0
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()

            episodes = []
            for row in rows:
                episodes.append({
                    "id": row[0],
                    "event_type": row[1],
                    "content": json.loads(row[2]),
                    "promotion_reason": row[3],
                    "timestamp": str(row[4]),
                })
            return episodes
        finally:
            conn.close()

    def mark_consolidated(self, episode_ids: List[int]) -> None:
        """Flip `consolidated` once a consolidation pass has read these episodes,
        so the next pass doesn't re-extract the same facts from them."""
        if not episode_ids:
            return

        conn = get_connection()
        cursor = conn.cursor()
        try:
            placeholders = ",".join("?" for _ in episode_ids)
            cursor.execute(
                f"UPDATE EpisodicMemory SET consolidated = 1 WHERE id IN ({placeholders})",
                tuple(episode_ids),
            )
            conn.commit()
        finally:
            conn.close()

"""
Notebook System — automatic investigation journal for the player.

Records clues, NPC statements, contradictions, and key events throughout the
game. The player can query the notebook at any time to review their progress.

Contradiction highlighting: when a new clue contradicts a previous NPC claim,
the notebook automatically links them together.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NotebookEntry(BaseModel):
    """A single entry in the player's investigation notebook."""

    round: int
    entry_type: str  # "clue" / "statement" / "contradiction" / "event" / "movement"
    text: str
    character_id: Optional[str] = None
    character_name: Optional[str] = None
    location: Optional[str] = None
    linked_entry_ids: List[int] = Field(default_factory=list)  # cross-references
    tags: List[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    """A detected contradiction between NPC claim and evidence."""

    round_detected: int
    character_id: str
    character_name: str
    original_claim: str
    original_round: int
    contradicting_evidence: str
    summary: str  # human-readable summary


class NotebookSystem:
    """Per-session notebook that auto-records investigation progress."""

    def __init__(self):
        self._notebooks: Dict[str, List[NotebookEntry]] = {}
        self._contradictions: Dict[str, List[Contradiction]] = {}
        self._next_id: Dict[str, int] = {}

    def _ensure_session(self, session_id: str) -> None:
        if session_id not in self._notebooks:
            self._notebooks[session_id] = []
            self._contradictions[session_id] = []
            self._next_id[session_id] = 0

    def _add(self, session_id: str, entry: NotebookEntry) -> int:
        self._ensure_session(session_id)
        entry_id = self._next_id[session_id]
        self._next_id[session_id] += 1
        self._notebooks[session_id].append(entry)
        return entry_id

    # ------------------------------------------------------------------
    # Recording APIs
    # ------------------------------------------------------------------

    def record_clue(
        self,
        session_id: str,
        round_num: int,
        clue_text: str,
        location: str,
    ) -> int:
        return self._add(
            session_id,
            NotebookEntry(
                round=round_num,
                entry_type="clue",
                text=clue_text,
                location=location,
                tags=["evidence"],
            ),
        )

    def record_statement(
        self,
        session_id: str,
        round_num: int,
        character_id: str,
        character_name: str,
        statement: str,
    ) -> int:
        return self._add(
            session_id,
            NotebookEntry(
                round=round_num,
                entry_type="statement",
                text=statement,
                character_id=character_id,
                character_name=character_name,
                tags=["npc_claim"],
            ),
        )

    def record_contradiction(
        self,
        session_id: str,
        round_num: int,
        character_id: str,
        character_name: str,
        original_claim: str,
        claim_round: int,
        evidence: str,
    ) -> None:
        self._ensure_session(session_id)
        summary = (
            f"{character_name}在第{claim_round}回合声称：「{original_claim}」"
            f"——但证据显示：{evidence}"
        )
        self._contradictions[session_id].append(
            Contradiction(
                round_detected=round_num,
                character_id=character_id,
                character_name=character_name,
                original_claim=original_claim,
                original_round=claim_round,
                contradicting_evidence=evidence,
                summary=summary,
            )
        )
        self._add(
            session_id,
            NotebookEntry(
                round=round_num,
                entry_type="contradiction",
                text=summary,
                character_id=character_id,
                character_name=character_name,
                tags=["contradiction", "important"],
            ),
        )

    def record_event(
        self,
        session_id: str,
        round_num: int,
        text: str,
        tags: list[str] | None = None,
    ) -> int:
        return self._add(
            session_id,
            NotebookEntry(
                round=round_num,
                entry_type="event",
                text=text,
                tags=tags or [],
            ),
        )

    def record_movement(
        self,
        session_id: str,
        round_num: int,
        location: str,
    ) -> int:
        return self._add(
            session_id,
            NotebookEntry(
                round=round_num,
                entry_type="movement",
                text=f"前往{location}",
                location=location,
                tags=["movement"],
            ),
        )

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    def get_notebook(self, session_id: str) -> List[dict]:
        """Get the full notebook as a list of dicts, ordered by round."""
        self._ensure_session(session_id)
        entries = self._notebooks[session_id]
        return [e.model_dump() for e in entries]

    def get_contradictions(self, session_id: str) -> List[dict]:
        """Get all detected contradictions."""
        self._ensure_session(session_id)
        return [c.model_dump() for c in self._contradictions[session_id]]

    def get_clues(self, session_id: str) -> List[dict]:
        """Get all discovered clues from the notebook."""
        self._ensure_session(session_id)
        return [
            e.model_dump()
            for e in self._notebooks[session_id]
            if e.entry_type == "clue"
        ]

    def get_summary(self, session_id: str) -> dict:
        """Get a summary of investigation progress."""
        self._ensure_session(session_id)
        entries = self._notebooks[session_id]
        return {
            "total_entries": len(entries),
            "clues_found": sum(1 for e in entries if e.entry_type == "clue"),
            "statements_recorded": sum(
                1 for e in entries if e.entry_type == "statement"
            ),
            "contradictions_found": len(self._contradictions[session_id]),
            "locations_visited": list(
                {
                    e.location
                    for e in entries
                    if e.entry_type == "movement" and e.location
                }
            ),
        }

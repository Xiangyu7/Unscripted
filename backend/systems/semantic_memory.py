"""
Semantic Memory System — embedding-based memory for NPC statements and clues.

Uses GLM (Zhipu AI) embedding-3 model to compute vector embeddings, enabling:
- Semantic contradiction detection: find NPC statements that conflict with new evidence
- Clue connection discovery: automatically link related clues in the notebook
- Semantic search: find relevant past entries by meaning, not just keywords

All embeddings are stored in-memory per session. The system gracefully degrades
when the embedding API is unavailable (returns empty results instead of crashing).
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from config import Config, LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class MemoryEntry(BaseModel):
    """A single entry stored in semantic memory with its embedding."""

    session_id: str
    round: int
    entry_type: str  # "statement" or "clue"
    character_id: Optional[str] = None
    text: str
    embedding: List[float] = Field(default_factory=list)


class SemanticMatch(BaseModel):
    """A search result with similarity score."""

    text: str
    character_id: Optional[str] = None
    round: int
    entry_type: str  # "statement" or "clue"
    similarity: float


class ClueConnection(BaseModel):
    """A pair of semantically related clues."""

    clue_a: str
    clue_b: str
    similarity: float


# ---------------------------------------------------------------------------
# Core system
# ---------------------------------------------------------------------------

class SemanticMemory:
    """Embedding-based semantic memory for NPC statements and clues.

    Stores vector embeddings and supports similarity-based retrieval:
    - Find NPC statements that may contradict a new clue
    - Discover connections between clues for notebook auto-linking
    - General semantic search across all stored entries

    Uses Zhipu AI embedding-3 via the OpenAI-compatible API. Falls back to
    no-op behaviour when the embedding service is unavailable.
    """

    # Similarity thresholds
    CONTRADICTION_THRESHOLD = 0.7
    CLUE_CONNECTION_THRESHOLD = 0.7

    def __init__(self, config: Config):
        self._entries: Dict[str, List[MemoryEntry]] = {}
        self._enabled = False

        # Only initialise the embedding client for OpenAI-compatible providers.
        # Fallback provider does not expose an embedding endpoint.
        if config.provider != LLMProvider.FALLBACK and config.api_key:
            try:
                from openai import AsyncOpenAI

                self.client = AsyncOpenAI(
                    api_key=config.api_key,
                    base_url="https://open.bigmodel.cn/api/paas/v4",
                )
                self.model = "embedding-3"
                self._enabled = True
                logger.info("SemanticMemory initialised with embedding-3 model")
            except Exception as exc:
                logger.warning("Failed to initialise embedding client: %s", exc)
                self.client = None
                self.model = None
        else:
            self.client = None
            self.model = None
            logger.info(
                "SemanticMemory disabled (provider=%s)",
                config.provider.value,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_session(self, session_id: str) -> None:
        if session_id not in self._entries:
            self._entries[session_id] = []

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors using pure Python."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def _get_embedding(self, text: str) -> List[float]:
        """Compute the embedding for a single text string."""
        if not self._enabled or self.client is None:
            return []
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.warning("Embedding API call failed: %s", exc)
            return []

    async def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Compute embeddings for multiple texts in a single API call."""
        if not self._enabled or self.client is None:
            return [[] for _ in texts]
        if not texts:
            return []
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            # The API returns embeddings sorted by index.
            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [item.embedding for item in sorted_data]
        except Exception as exc:
            logger.warning("Batch embedding API call failed: %s", exc)
            return [[] for _ in texts]

    def _get_entries(
        self,
        session_id: str,
        entry_type: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """Retrieve stored entries, optionally filtered by type."""
        self._ensure_session(session_id)
        entries = self._entries[session_id]
        if entry_type is not None:
            entries = [e for e in entries if e.entry_type == entry_type]
        return entries

    # ------------------------------------------------------------------
    # Storage APIs
    # ------------------------------------------------------------------

    async def store_statement(
        self,
        session_id: str,
        round_num: int,
        character_id: str,
        text: str,
    ) -> None:
        """Compute and store the embedding for an NPC statement."""
        self._ensure_session(session_id)
        embedding = await self._get_embedding(text)
        self._entries[session_id].append(
            MemoryEntry(
                session_id=session_id,
                round=round_num,
                entry_type="statement",
                character_id=character_id,
                text=text,
                embedding=embedding,
            )
        )

    async def store_clue(
        self,
        session_id: str,
        round_num: int,
        text: str,
    ) -> None:
        """Compute and store the embedding for a discovered clue."""
        self._ensure_session(session_id)
        embedding = await self._get_embedding(text)
        self._entries[session_id].append(
            MemoryEntry(
                session_id=session_id,
                round=round_num,
                entry_type="clue",
                character_id=None,
                text=text,
                embedding=embedding,
            )
        )

    async def store_batch(
        self,
        session_id: str,
        items: List[Dict],
    ) -> None:
        """Store multiple entries at once, batching the embedding API call.

        Each item in *items* should be a dict with keys:
            round, entry_type ("statement"/"clue"), text,
            and optionally character_id.
        """
        if not items:
            return
        self._ensure_session(session_id)

        texts = [item["text"] for item in items]
        embeddings = await self._get_embeddings_batch(texts)

        for item, embedding in zip(items, embeddings):
            self._entries[session_id].append(
                MemoryEntry(
                    session_id=session_id,
                    round=item["round"],
                    entry_type=item["entry_type"],
                    character_id=item.get("character_id"),
                    text=item["text"],
                    embedding=embedding,
                )
            )

    # ------------------------------------------------------------------
    # Query APIs
    # ------------------------------------------------------------------

    async def find_related_statements(
        self,
        session_id: str,
        clue_text: str,
        threshold: Optional[float] = None,
    ) -> List[SemanticMatch]:
        """Find NPC statements semantically related to a new clue.

        Returns statements whose cosine similarity with *clue_text* exceeds
        the threshold (default ``CONTRADICTION_THRESHOLD``). Results are sorted
        by descending similarity so the strongest potential contradictions
        come first.
        """
        if not self._enabled:
            return []

        threshold = threshold if threshold is not None else self.CONTRADICTION_THRESHOLD
        clue_embedding = await self._get_embedding(clue_text)
        if not clue_embedding:
            return []

        statements = self._get_entries(session_id, entry_type="statement")
        matches: List[SemanticMatch] = []

        for entry in statements:
            if not entry.embedding:
                continue
            sim = self._cosine_similarity(clue_embedding, entry.embedding)
            if sim >= threshold:
                matches.append(
                    SemanticMatch(
                        text=entry.text,
                        character_id=entry.character_id,
                        round=entry.round,
                        entry_type=entry.entry_type,
                        similarity=round(sim, 4),
                    )
                )

        matches.sort(key=lambda m: m.similarity, reverse=True)
        return matches

    async def find_clue_connections(
        self,
        session_id: str,
        threshold: Optional[float] = None,
    ) -> List[ClueConnection]:
        """Find pairs of semantically related clues.

        Compares every pair of discovered clues and returns those whose
        similarity exceeds the threshold. Powers the "notebook auto-connection"
        feature — linked clues are displayed together in the UI.
        """
        if not self._enabled:
            return []

        threshold = threshold if threshold is not None else self.CLUE_CONNECTION_THRESHOLD
        clues = self._get_entries(session_id, entry_type="clue")

        # Re-embed any clues missing embeddings (e.g. stored during API outage)
        missing_indices = [i for i, c in enumerate(clues) if not c.embedding]
        if missing_indices:
            missing_texts = [clues[i].text for i in missing_indices]
            embeddings = await self._get_embeddings_batch(missing_texts)
            for idx, embedding in zip(missing_indices, embeddings):
                clues[idx].embedding = embedding

        connections: List[ClueConnection] = []
        for i in range(len(clues)):
            if not clues[i].embedding:
                continue
            for j in range(i + 1, len(clues)):
                if not clues[j].embedding:
                    continue
                sim = self._cosine_similarity(
                    clues[i].embedding, clues[j].embedding,
                )
                if sim >= threshold:
                    connections.append(
                        ClueConnection(
                            clue_a=clues[i].text,
                            clue_b=clues[j].text,
                            similarity=round(sim, 4),
                        )
                    )

        connections.sort(key=lambda c: c.similarity, reverse=True)
        return connections

    async def search(
        self,
        session_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[SemanticMatch]:
        """Semantic search: find the most relevant stored entries for a query.

        Returns up to *top_k* entries ranked by cosine similarity, regardless
        of entry type. Useful for answering player queries like "what do I
        know about the wine cellar?"
        """
        if not self._enabled:
            return []

        query_embedding = await self._get_embedding(query)
        if not query_embedding:
            return []

        all_entries = self._get_entries(session_id)
        scored: List[SemanticMatch] = []

        for entry in all_entries:
            if not entry.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, entry.embedding)
            scored.append(
                SemanticMatch(
                    text=entry.text,
                    character_id=entry.character_id,
                    round=entry.round,
                    entry_type=entry.entry_type,
                    similarity=round(sim, 4),
                )
            )

        scored.sort(key=lambda m: m.similarity, reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def clear_session(self, session_id: str) -> None:
        """Remove all stored data for a session."""
        self._entries.pop(session_id, None)

    def get_stats(self, session_id: str) -> Dict:
        """Return summary statistics for a session's semantic memory."""
        self._ensure_session(session_id)
        entries = self._entries[session_id]
        statements = [e for e in entries if e.entry_type == "statement"]
        clues = [e for e in entries if e.entry_type == "clue"]
        embedded = sum(1 for e in entries if e.embedding)
        return {
            "total_entries": len(entries),
            "statements": len(statements),
            "clues": len(clues),
            "embedded": embedded,
            "enabled": self._enabled,
        }

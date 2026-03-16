"""
ContinuityGuardian — tracks all narrative statements across rounds and
detects contradictions so that NPC dialogue remains consistent.

This module is purely rule-based (no LLM calls).  It stores per-session
narrative history and provides helpers that can be injected into character
agent system prompts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ─── Data models ────────────────────────────────────────────────────────

class NarrativeStatement(BaseModel):
    round: int
    character_id: str  # e.g. "linlan", "zhoumu", "songzhi", "system", "director"
    statement: str     # The raw text that was said
    topics: List[str] = Field(default_factory=list)   # Key topics mentioned
    claims: List[str] = Field(default_factory=list)    # Factual claims made
    is_key: bool = False  # Key statements (denials, admissions, emotions) are never forgotten


class ContinuityState(BaseModel):
    session_id: str
    statements: List[NarrativeStatement] = Field(default_factory=list)
    player_known_facts: List[str] = Field(default_factory=list)
    character_claims: Dict[str, List[str]] = Field(default_factory=dict)
    revealed_info: Dict[str, List[str]] = Field(default_factory=dict)
    contradiction_log: List[str] = Field(default_factory=list)
    # Compressed summaries of older conversation rounds per character
    character_summaries: Dict[str, str] = Field(default_factory=dict)
    # Round number up to which summaries have been generated
    summarized_up_to: Dict[str, int] = Field(default_factory=dict)


# ─── Contradiction detection patterns ──────────────────────────────────

# Each pattern is a tuple of (negation_regex, reveal_regex, description_template).
# If a character previously matched *negation_regex* and the new statement
# matches *reveal_regex* for the same subject, a contradiction is flagged.
#
# {subject} is replaced with the captured group from the negation pattern
# during matching; {character} is replaced with the character name / id.

_NEGATION_PATTERNS: List[dict] = [
    {
        "name": "deny_knowledge_then_reveal",
        "negation": re.compile(r"不知道(.+?)(?:[。，,\s]|$)"),
        "reveal": re.compile(r"(.+?)"),  # placeholder — subject is extracted first
        "description": "角色之前说不知道「{subject}」，但现在提到了相关信息",
    },
    {
        "name": "deny_seeing_then_mention",
        "negation": re.compile(r"没(?:有)?见(?:过|到)(.+?)(?:[。，,\s]|$)"),
        "reveal": re.compile(r"(?:看到|见到|看见|遇到|碰到|遇见)(.+?)(?:[。，,\s]|$)"),
        "description": "角色之前说没见过「{subject}」，但现在提到见过",
    },
    {
        "name": "deny_presence_then_admit",
        "negation": re.compile(r"不在(.+?)(?:[。，,\s]|$)"),
        "reveal": re.compile(r"(?:在|去了|到了|去过)(.+?)(?:[。，,\s]|$)"),
        "description": "角色之前说不在「{subject}」，但现在承认去过",
    },
    {
        "name": "deny_action_then_admit",
        "negation": re.compile(r"没(?:有)?(.{1,10}?)(?:[。，,\s]|$)"),
        "reveal": re.compile(r"(.+?)"),  # subject-based
        "description": "角色之前否认「{subject}」，但现在的发言暗示了相反的事实",
    },
]

# Patterns for detecting location claims
_LOCATION_CLAIM_RE = re.compile(
    r"(?:我)?(?:在|去了|到了|待在|一直在)([^。，,\s]{1,10})"
)

# Patterns for detecting time claims
_TIME_CLAIM_RE = re.compile(
    r"(昨晚|今天|那天|当时|那时候|凌晨|深夜|傍晚|下午|上午|早上)"
    r"(?:我)?(?:在|去了|到了|见到|看到|做了|没有)(.+?)(?:[。，,\s]|$)"
)


def _extract_subjects(text: str) -> List[str]:
    """Extract potential subject keywords from a statement."""
    # Remove common filler / punctuation, split into chunks
    cleaned = re.sub(r"[。，,！？、：；""''…\s]+", " ", text).strip()
    # Return non-trivial segments (length >= 2)
    return [seg for seg in cleaned.split() if len(seg) >= 2]


def _subject_overlap(subject: str, text: str) -> bool:
    """Check whether *subject* appears (or substantially overlaps) in *text*."""
    if subject in text:
        return True
    # Also check if at least half the characters of subject appear in text
    if len(subject) >= 2:
        matches = sum(1 for ch in subject if ch in text)
        if matches / len(subject) >= 0.6:
            return True
    return False


# ─── Key statement detection ──────────────────────────────────────────

# Patterns that indicate a statement should NEVER be forgotten
_KEY_DENIAL_RE = re.compile(r"不知道|没见过|没有见|不在|没去过|不认识|没听说")
_KEY_ADMISSION_RE = re.compile(r"好吧|实话说|坦白|承认|其实|说实话|告诉你|不瞒你")
_KEY_EMOTION_RE = re.compile(r"[！!]{1,}|你到底|闭嘴|别问了|够了|住嘴|滚|放过我")
_KEY_REVEAL_RE = re.compile(r"秘密|遗嘱|密室|酒窖|争吵|失踪|计划|真相")


def _is_key_statement(text: str) -> bool:
    """Detect whether a statement is important enough to never forget."""
    if _KEY_DENIAL_RE.search(text):
        return True
    if _KEY_ADMISSION_RE.search(text):
        return True
    if _KEY_EMOTION_RE.search(text):
        return True
    if _KEY_REVEAL_RE.search(text):
        return True
    # Long statements (>60 chars) are usually more substantial
    if len(text) > 80:
        return True
    return False


def _extract_topic_keywords(text: str) -> List[str]:
    """Extract topic keywords for matching against player actions."""
    keywords = []
    topic_patterns = [
        "顾言", "林岚", "周牧", "宋知微", "赵伯",
        "遗嘱", "遗产", "失踪", "争吵", "秘密", "计划",
        "书房", "酒窖", "花园", "走廊", "宴会厅",
        "手机", "电话", "消息", "纸条", "信",
        "脚印", "划痕", "密室", "钥匙",
    ]
    for kw in topic_patterns:
        if kw in text:
            keywords.append(kw)
    return keywords


def _build_summary_from_statements(statements: List[NarrativeStatement], char_name: str) -> str:
    """Compress a list of older statements into a brief summary."""
    if not statements:
        return ""

    topics_mentioned: Dict[str, int] = defaultdict(int)
    denials = []
    reveals = []

    for s in statements:
        for topic in s.topics:
            topics_mentioned[topic] += 1
        if _KEY_DENIAL_RE.search(s.statement):
            # Extract what was denied
            m = re.search(r"不知道(.+?)(?:[。，,\s]|$)", s.statement)
            if m:
                denials.append(f"第{s.round}轮否认知道「{m.group(1).strip()[:10]}」")
        if _KEY_ADMISSION_RE.search(s.statement):
            reveals.append(f"第{s.round}轮透露了一些信息")

    parts = []
    if topics_mentioned:
        top_topics = sorted(topics_mentioned.items(), key=lambda x: -x[1])[:5]
        topic_str = "、".join(t[0] for t in top_topics)
        parts.append(f"{char_name}之前的对话主要涉及：{topic_str}")
    if denials:
        parts.append(f"重要否认：{'; '.join(denials[:3])}")
    if reveals:
        parts.append(f"曾经松口：{'; '.join(reveals[:3])}")

    return "。".join(parts)


# ─── ContinuityGuardian ────────────────────────────────────────────────

class ContinuityGuardian:
    """Tracks narrative statements per session and detects contradictions.

    Usage:
        guardian = ContinuityGuardian()

        # After each NPC turn, record what they said:
        guardian.record_statement(session_id, round, character_id, text,
                                  topics=["顾言", "遗嘱"],
                                  claims=["不知道顾言去哪了"])

        # Before generating the next NPC response, inject context:
        prompt_section = guardian.build_continuity_prompt(session_id, character_id)
    """

    def __init__(self) -> None:
        self._states: Dict[str, ContinuityState] = {}

    # ── helpers ──────────────────────────────────────────────────────

    def _ensure_session(self, session_id: str) -> ContinuityState:
        if session_id not in self._states:
            self._states[session_id] = ContinuityState(session_id=session_id)
        return self._states[session_id]

    # ── public API ───────────────────────────────────────────────────

    def record_statement(
        self,
        session_id: str,
        round: int,
        character_id: str,
        text: str,
        topics: Optional[List[str]] = None,
        claims: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Record a narrative statement and return a contradiction warning if
        one is detected, otherwise ``None``.

        *topics* and *claims* are optional — if omitted the guardian will
        attempt lightweight auto-extraction from the text.
        """
        state = self._ensure_session(session_id)

        # Auto-extract topics / claims when not provided
        if topics is None:
            topics = _extract_subjects(text)
        if claims is None:
            claims = self._auto_extract_claims(text)

        stmt = NarrativeStatement(
            round=round,
            character_id=character_id,
            statement=text,
            topics=topics,
            claims=claims,
            is_key=_is_key_statement(text),
        )
        state.statements.append(stmt)

        # Auto-summarize when a character has many old statements
        char_stmts = [s for s in state.statements if s.character_id == character_id]
        summarized_round = state.summarized_up_to.get(character_id, 0)
        if len(char_stmts) > 8:
            # Summarize everything older than the last 5 statements
            cutoff = char_stmts[-5].round
            if cutoff > summarized_round:
                old_stmts = [s for s in char_stmts if s.round < cutoff]
                char_names = {"linlan": "林岚", "zhoumu": "周牧", "songzhi": "宋知微"}
                name = char_names.get(character_id, character_id)
                state.character_summaries[character_id] = _build_summary_from_statements(old_stmts, name)
                state.summarized_up_to[character_id] = cutoff

        # Update per-character bookkeeping
        if character_id not in state.character_claims:
            state.character_claims[character_id] = []
        state.character_claims[character_id].extend(claims)

        if character_id not in state.revealed_info:
            state.revealed_info[character_id] = []
        state.revealed_info[character_id].extend(topics)

        # Track player-known facts (anything said *to* the player is known)
        if character_id != "system":
            state.player_known_facts.extend(topics)

        # Check for contradictions
        contradiction = self.check_contradiction(session_id, character_id, text)
        if contradiction:
            state.contradiction_log.append(contradiction)
        return contradiction

    # ── query methods ────────────────────────────────────────────────

    def get_character_history(
        self, session_id: str, character_id: str
    ) -> List[NarrativeStatement]:
        """Return all statements made by *character_id* in the session."""
        state = self._ensure_session(session_id)
        return [s for s in state.statements if s.character_id == character_id]

    def get_smart_memory(
        self, session_id: str, character_id: str, player_action: str = ""
    ) -> str:
        """Build a layered memory context:
        1. Compressed summary of old conversations (never lost)
        2. ALL key statements (denials, admissions, emotions — never forgotten)
        3. Topic-relevant statements matching the current player action
        4. Most recent 3 statements for immediate context
        """
        state = self._ensure_session(session_id)
        char_stmts = [s for s in state.statements if s.character_id == character_id]
        if not char_stmts:
            return ""

        char_names = {"linlan": "林岚", "zhoumu": "周牧", "songzhi": "宋知微"}
        name = char_names.get(character_id, character_id)
        parts: List[str] = []

        # Layer 1: Compressed summary of older rounds
        summary = state.character_summaries.get(character_id, "")
        if summary:
            parts.append(f"【{name}的早期对话摘要】\n{summary}")

        # Layer 2: Key statements (NEVER forgotten)
        key_stmts = [s for s in char_stmts if s.is_key]
        # Don't repeat keys that are in the recent 3
        recent_rounds = {s.round for s in char_stmts[-3:]}
        old_key_stmts = [s for s in key_stmts if s.round not in recent_rounds]
        if old_key_stmts:
            key_lines = []
            for s in old_key_stmts[-6:]:  # Cap at 6 key memories
                display = s.statement[:80] + "…" if len(s.statement) > 80 else s.statement
                key_lines.append(f"- 第{s.round}轮: \"{display}\"")
            parts.append(
                f"【{name}的重要发言（不可遗忘）】\n" + "\n".join(key_lines)
            )

        # Layer 3: Topic-relevant statements matching player action
        if player_action:
            action_keywords = _extract_topic_keywords(player_action)
            if action_keywords:
                relevant = []
                for s in char_stmts:
                    if s.round in recent_rounds:
                        continue  # Will be in Layer 4
                    if s in old_key_stmts:
                        continue  # Already in Layer 2
                    stmt_keywords = _extract_topic_keywords(s.statement)
                    overlap = set(action_keywords) & set(stmt_keywords)
                    if overlap:
                        relevant.append(s)
                if relevant:
                    rel_lines = []
                    for s in relevant[-3:]:
                        display = s.statement[:80] + "…" if len(s.statement) > 80 else s.statement
                        rel_lines.append(f"- 第{s.round}轮: \"{display}\"")
                    parts.append(
                        f"【与当前话题相关的历史发言】\n" + "\n".join(rel_lines)
                    )

        # Layer 4: Most recent statements (immediate context)
        recent = char_stmts[-3:]
        if recent:
            recent_lines = []
            for s in recent:
                display = s.statement[:80] + "…" if len(s.statement) > 80 else s.statement
                recent_lines.append(f"- 第{s.round}轮: \"{display}\"")
            parts.append(
                f"【{name}最近的发言】\n" + "\n".join(recent_lines)
            )

        if parts:
            parts.append(
                "你必须与以上发言保持一致。如果你之前否认过某事，不能突然透露——除非有合理的角色动机。"
            )

        return "\n\n".join(parts)

    def get_context_summary(self, session_id: str, character_id: str) -> str:
        """Generate a concise summary of what this character has previously
        said, suitable for injection into their LLM prompt."""
        history = self.get_character_history(session_id, character_id)
        if not history:
            return ""

        lines: List[str] = []
        for stmt in history:
            # Truncate very long statements for the summary
            display = stmt.statement
            if len(display) > 60:
                display = display[:57] + "..."
            lines.append(f"- 第{stmt.round}轮: {display}")

        summary = "你在之前的对话中说过：\n" + "\n".join(lines)
        summary += "\n注意: 不要与以上发言产生矛盾"
        return summary

    def get_player_knowledge_summary(self, session_id: str) -> str:
        """Summarise what the player already knows so that NPCs avoid
        re-revealing or accidentally leaking unknown information."""
        state = self._ensure_session(session_id)
        if not state.player_known_facts:
            return ""

        # De-duplicate while preserving order
        seen: set = set()
        unique_facts: List[str] = []
        for fact in state.player_known_facts:
            if fact not in seen:
                seen.add(fact)
                unique_facts.append(fact)

        lines = "\n".join(f"- {f}" for f in unique_facts)
        return (
            "【玩家目前已知的信息】\n"
            f"{lines}\n"
            "注意: 不要重复透露以上信息，也不要意外泄露玩家尚未知道的关键线索。"
        )

    # ── contradiction detection ──────────────────────────────────────

    def check_contradiction(
        self, session_id: str, character_id: str, new_statement: str
    ) -> Optional[str]:
        """Rule-based check whether *new_statement* contradicts any previous
        claim by the same character.  Returns a human-readable description of
        the contradiction, or ``None``."""
        state = self._ensure_session(session_id)
        prev_statements = [
            s for s in state.statements
            if s.character_id == character_id
            # Exclude the statement we just appended (it is the new one)
            and s.statement != new_statement
        ]
        if not prev_statements:
            return None

        # --- Pattern 1: "不知道 X" then reveals X -------------------------
        for prev in prev_statements:
            m = re.search(r"不知道(.+?)(?:[。，,\s]|$)", prev.statement)
            if m:
                subject = m.group(1).strip()
                if subject and _subject_overlap(subject, new_statement):
                    # Make sure new statement is actually providing info, not
                    # repeating "不知道"
                    if "不知道" not in new_statement or subject not in re.findall(
                        r"不知道(.+?)(?:[。，,\s]|$)", new_statement
                    ):
                        return (
                            f"[矛盾] {character_id} 在第{prev.round}轮说"
                            f"不知道「{subject}」，但现在提到了相关内容"
                        )

        # --- Pattern 2: "没见过 X" then "见到 X" ---------------------------
        for prev in prev_statements:
            m = re.search(r"没(?:有)?见(?:过|到)(.+?)(?:[。，,\s]|$)", prev.statement)
            if m:
                subject = m.group(1).strip()
                if subject and re.search(
                    rf"(?:看到|见到|看见|遇到|碰到|遇见){re.escape(subject)}",
                    new_statement,
                ):
                    return (
                        f"[矛盾] {character_id} 在第{prev.round}轮说"
                        f"没见过「{subject}」，但现在提到见过"
                    )

        # --- Pattern 3: location contradiction "不在 A" then "在 A" ---------
        for prev in prev_statements:
            m = re.search(r"不在(.+?)(?:[。，,\s]|$)", prev.statement)
            if m:
                location = m.group(1).strip()
                if location and re.search(
                    rf"(?:在|去了|到了|去过){re.escape(location)}", new_statement
                ):
                    return (
                        f"[矛盾] {character_id} 在第{prev.round}轮说"
                        f"不在「{location}」，但现在承认去过"
                    )

        # --- Pattern 4: location A vs location B at the same time ----------
        prev_locations: List[tuple] = []
        for prev in prev_statements:
            lm = _LOCATION_CLAIM_RE.search(prev.statement)
            if lm:
                prev_locations.append((prev.round, lm.group(1).strip()))

        new_loc_m = _LOCATION_CLAIM_RE.search(new_statement)
        if new_loc_m and prev_locations:
            new_loc = new_loc_m.group(1).strip()
            for prev_round, prev_loc in prev_locations:
                if prev_loc and new_loc and prev_loc != new_loc:
                    # Only flag if the statements refer to the same timeframe
                    # (simple heuristic: both mention the same time keyword, or
                    # neither mentions a specific time)
                    return (
                        f"[矛盾] {character_id} 在第{prev_round}轮说"
                        f"在「{prev_loc}」，但现在说在「{new_loc}」"
                    )

        # --- Pattern 5: "没(有) X" then admits X ---------------------------
        for prev in prev_statements:
            m = re.search(r"没(?:有)?([^。，,\s]{2,8}?)(?:[。，,\s]|$)", prev.statement)
            if m:
                action = m.group(1).strip()
                if not action:
                    continue
                # Skip generic negations already covered above
                if action.startswith("见") or action.startswith("知"):
                    continue
                # Check if new statement positively asserts the same action
                positive_pattern = re.compile(
                    rf"(?:^|[。，,\s])(?:我)?{re.escape(action)}"
                )
                if positive_pattern.search(new_statement):
                    return (
                        f"[矛盾] {character_id} 在第{prev.round}轮否认"
                        f"「{action}」，但现在的发言暗示了相反的事实"
                    )

        return None

    def get_all_contradictions(self, session_id: str) -> List[str]:
        """Return every contradiction detected so far in this session."""
        state = self._ensure_session(session_id)
        return list(state.contradiction_log)

    # ── prompt builders ──────────────────────────────────────────────

    def build_continuity_prompt(
        self, session_id: str, character_id: str
    ) -> str:
        """Build a prompt section that should be appended to the character
        agent's system prompt in order to maintain narrative consistency.

        Combines the character's conversation history, the player's current
        knowledge, and any relevant contradiction warnings.
        """
        parts: List[str] = []

        # 1. Character's own history
        context = self.get_context_summary(session_id, character_id)
        if context:
            parts.append(context)

        # 2. Player knowledge
        player_knowledge = self.get_player_knowledge_summary(session_id)
        if player_knowledge:
            parts.append(player_knowledge)

        # 3. Contradiction warnings specific to this character
        state = self._ensure_session(session_id)
        char_contradictions = [
            c for c in state.contradiction_log if character_id in c
        ]
        if char_contradictions:
            warning_lines = "\n".join(f"- {c}" for c in char_contradictions)
            parts.append(
                "【警告 — 已检测到的叙事矛盾】\n"
                f"{warning_lines}\n"
                "务必在后续对话中避免加深这些矛盾。"
            )

        # 4. General consistency rules
        if parts:
            parts.append(
                "【连贯性规则】\n"
                "1. 你的回答必须与之前的发言保持一致\n"
                "2. 如果你之前说过不知道某事，不可以突然透露相关细节\n"
                "3. 如果你改口，必须有合理的角色动机（例如信任度提升后主动坦白）\n"
                "4. 不要重复已经告诉玩家的信息，除非玩家主动追问"
            )

        return "\n\n".join(parts)

    # ── internal helpers ─────────────────────────────────────────────

    @staticmethod
    def _auto_extract_claims(text: str) -> List[str]:
        """Best-effort extraction of factual claims from raw text."""
        claims: List[str] = []

        # "不知道 X"
        for m in re.finditer(r"不知道(.+?)(?:[。，,\s]|$)", text):
            claims.append(f"不知道{m.group(1).strip()}")

        # "没见过 X"
        for m in re.finditer(r"没(?:有)?见(?:过|到)(.+?)(?:[。，,\s]|$)", text):
            claims.append(f"没见过{m.group(1).strip()}")

        # "不在 X"
        for m in re.finditer(r"不在(.+?)(?:[。，,\s]|$)", text):
            claims.append(f"不在{m.group(1).strip()}")

        # "在 X" (location)
        for m in _LOCATION_CLAIM_RE.finditer(text):
            claims.append(f"在{m.group(1).strip()}")

        # "没(有) verb"
        for m in re.finditer(r"没(?:有)?([^。，,\s]{2,8}?)(?:[。，,\s]|$)", text):
            action = m.group(1).strip()
            if action and not action.startswith("见") and not action.startswith("知"):
                claims.append(f"没有{action}")

        return claims

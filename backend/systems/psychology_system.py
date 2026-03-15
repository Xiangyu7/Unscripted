"""
Character Psychology Agent — manages deep psychological state for each NPC per session.

The existing game only tracks trust_to_player (0-100) and suspicion (0-100) per character.
This agent adds a richer emotional model: fear, anger, guilt, composure, desperation, and
tracks defensive strategies, lies told, pressure history, and emotional breaks. It produces
behavior directives that the dialogue-generating CharacterAgent can consume, and detects
"breaking point" events that trigger special narrative moments.

Usage:
    psych = CharacterPsychologyAgent()
    state = psych.get_state(session_id, "linlan")
    state = psych.update_after_turn(session_id, "linlan", intent_type, rule_result, player_action, tension)
    directive = psych.get_behavior_directive(session_id, "linlan")
    event = psych.check_breaking_point(session_id, "linlan")
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class CharacterPsychState(BaseModel):
    """
    Deep psychological state for a single NPC within a single game session.

    All float fields are normalized to the 0.0-1.0 range:
        0.0 = absent / minimal
        1.0 = extreme / maximal

    Attributes:
        character_id:       Unique character identifier (e.g. "linlan").
        fear:               Fear of being exposed or caught (0-1).
        anger:              Anger toward the interrogator / player (0-1).
        guilt:              Internal guilt about what they have done or know (0-1).
        composure:          Ability to maintain a calm facade (0-1, decreases under pressure).
        desperation:        Desperation level (0-1, triggers extreme behavior at high values).
        defensive_strategy: Current conversational strategy the character is employing.
                            One of: deflect, redirect, partial_confess, attack, shutdown.
        alliance_target:    Character ID this NPC is currently trying to ally with, or None.
        recent_lies:        Lies the character has told during this session (for contradiction
                            detection by other systems).
        pressure_history:   Topics / actions the player has pressured this character about.
        emotional_breaks:   Count of times composure has dropped below 0.3 during the session.
    """

    character_id: str
    fear: float = Field(default=0.2, ge=0.0, le=1.0)
    anger: float = Field(default=0.1, ge=0.0, le=1.0)
    guilt: float = Field(default=0.3, ge=0.0, le=1.0)
    composure: float = Field(default=0.8, ge=0.0, le=1.0)
    desperation: float = Field(default=0.0, ge=0.0, le=1.0)
    defensive_strategy: str = "deflect"
    alliance_target: Optional[str] = None
    recent_lies: List[str] = Field(default_factory=list)
    pressure_history: List[str] = Field(default_factory=list)
    emotional_breaks: int = 0


# ---------------------------------------------------------------------------
# Per-character initial psychology presets
# ---------------------------------------------------------------------------

# These presets reflect each character's personality and narrative role so that
# from the very first interaction their psychology feels distinct.

_INITIAL_PRESETS: Dict[str, Dict[str, object]] = {
    # 林岚 — the composed secretary who knows the truth.
    # High composure, moderate guilt (she is complicit), low anger.
    "linlan": {
        "fear": 0.25,
        "anger": 0.1,
        "guilt": 0.4,
        "composure": 0.85,
        "desperation": 0.0,
        "defensive_strategy": "deflect",
        "alliance_target": None,
    },
    # 周牧 — the nervous childhood friend who fought with the victim.
    # Lower composure, high guilt, moderate fear, slightly elevated anger.
    "zhoumu": {
        "fear": 0.4,
        "anger": 0.2,
        "guilt": 0.5,
        "composure": 0.6,
        "desperation": 0.05,
        "defensive_strategy": "redirect",
        "alliance_target": None,
    },
    # 宋知微 — the analytical reporter, mostly an outsider.
    # High composure, low guilt and fear; she deflects via logic, not emotion.
    "songzhi": {
        "fear": 0.15,
        "anger": 0.05,
        "guilt": 0.1,
        "composure": 0.8,
        "desperation": 0.0,
        "defensive_strategy": "redirect",
        "alliance_target": None,
    },
}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* to the closed interval [lo, hi]."""
    return max(lo, min(hi, value))


def _consecutive_pressure_count(pressure_history: List[str], character_id: str) -> int:
    """
    Count how many of the most recent pressure_history entries target
    *character_id* consecutively (from the tail of the list).

    Each entry in pressure_history is a string of the form
    ``"<intent>:<character_id>:<summary>"``.  We count consecutive entries
    whose character part matches.
    """
    count = 0
    for entry in reversed(pressure_history):
        parts = entry.split(":", 2)
        if len(parts) >= 2 and parts[1] == character_id:
            count += 1
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Strategy selection logic
# ---------------------------------------------------------------------------

def _choose_strategy(state: CharacterPsychState) -> str:
    """
    Determine the best defensive_strategy for the character given current
    psychological values.

    Strategies (in rough order of desperation):
        deflect        — calmly steer the conversation elsewhere
        redirect       — point at another NPC / topic to shift blame
        partial_confess — reveal a small truth to relieve pressure
        attack         — go on the offensive, challenge the player
        shutdown       — refuse to engage, stonewall

    Returns:
        One of the five strategy strings.
    """
    if state.desperation > 0.7:
        # Extremely desperate — confess something small to reduce heat
        return "partial_confess"
    if state.anger > 0.7:
        # Very angry — lash out
        return "attack"
    if state.composure < 0.25:
        # Can barely hold it together — shut down
        return "shutdown"
    if state.fear > 0.6:
        # Scared — redirect blame to another NPC
        return "redirect"
    # Default — calmly deflect
    return "deflect"


# ---------------------------------------------------------------------------
# Main agent class
# ---------------------------------------------------------------------------

class CharacterPsychologyAgent:
    """
    Manages per-session, per-character psychological state and produces
    behaviour directives consumed by the dialogue-generating CharacterAgent.

    State is stored in-memory, keyed by ``(session_id, character_id)``.

    Typical per-turn flow:
        1. ``update_after_turn(...)`` — mutate psychology based on what just happened.
        2. ``get_behavior_directive(...)`` — read behaviour hints for the dialogue agent.
        3. ``check_breaking_point(...)`` — detect special narrative events.
    """

    def __init__(self) -> None:
        """Initialise with an empty session-state dictionary."""
        self._states: Dict[Tuple[str, str], CharacterPsychState] = {}

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    def get_state(self, session_id: str, character_id: str) -> CharacterPsychState:
        """
        Return the current ``CharacterPsychState`` for the given session and
        character.  If no state exists yet, one is created using the character's
        initial preset (or sensible defaults if the character has no preset).

        Args:
            session_id:   The game session identifier.
            character_id: The NPC identifier (e.g. ``"linlan"``).

        Returns:
            The (possibly freshly-created) ``CharacterPsychState``.
        """
        key = (session_id, character_id)
        if key not in self._states:
            preset = _INITIAL_PRESETS.get(character_id, {})
            self._states[key] = CharacterPsychState(
                character_id=character_id, **preset
            )
        return self._states[key]

    # ------------------------------------------------------------------
    # Core update logic
    # ------------------------------------------------------------------

    def update_after_turn(
        self,
        session_id: str,
        character_id: str,
        intent_type: str,
        rule_result: dict,
        player_action: str,
        tension: int,
    ) -> CharacterPsychState:
        """
        Update the psychological state of *character_id* based on what
        happened during the current turn.

        The update takes into account:
        * The player's intent (ask, bluff, accuse, search, etc.).
        * Whether the action was successful / blocked.
        * The current global tension level.
        * Whether the player has been consecutively targeting this character
          (cumulative pressure / 累计压力).

        Args:
            session_id:   The game session identifier.
            character_id: The NPC being updated.
            intent_type:  The classified player intent as a string value
                          (matching ``IntentType`` enum values: ``"ask"``,
                          ``"bluff"``, ``"accuse"``, ``"search"``, etc.).
            rule_result:  The dict returned by ``rule_judge.judge_action``.
            player_action: The raw player action text.
            tension:      Current global tension (0-100).

        Returns:
            The updated ``CharacterPsychState``.
        """
        st = self.get_state(session_id, character_id)

        # ---- Record pressure history ----
        summary = player_action[:60] if player_action else ""
        st.pressure_history.append(f"{intent_type}:{character_id}:{summary}")

        # ---- Tension amplifier ----
        # When global tension is high (>70), negative-emotion deltas are amplified.
        tension_amp = 1.0 + max(0.0, (tension - 70) / 100.0)  # 1.0 .. 1.3

        # ---- Consecutive-targeting multiplier (累计压力) ----
        consec = _consecutive_pressure_count(st.pressure_history, character_id)
        consec_mult = 1.0
        if consec >= 5:
            consec_mult = 2.0
        elif consec >= 3:
            consec_mult = 1.5

        # ---- Intent-specific deltas ----
        target_char = rule_result.get("target_character") or ""
        # Determine whether *this* character is the direct target of the action.
        is_target = (
            target_char == character_id
            or intent_type in ("accuse",)  # accuse affects everyone
        )

        if intent_type == "ask" and is_target:
            # Polite questioning — mild pressure
            st.composure = _clamp(st.composure - 0.03 * consec_mult * tension_amp)
            st.fear = _clamp(st.fear + 0.02 * tension_amp)
            st.anger = _clamp(st.anger + 0.01 * tension_amp)

        elif intent_type == "bluff" and is_target:
            # Deceptive pressure — provokes anger, erodes composure faster
            st.composure = _clamp(st.composure - 0.08 * consec_mult * tension_amp)
            st.anger = _clamp(st.anger + 0.10 * consec_mult * tension_amp)
            st.fear = _clamp(st.fear + 0.05 * tension_amp)
            st.desperation = _clamp(st.desperation + 0.04 * tension_amp)

        elif intent_type == "accuse":
            # Direct accusation — devastating psychological impact
            st.composure = _clamp(st.composure - 0.20 * consec_mult * tension_amp)
            st.fear = _clamp(min(st.fear + 0.25 * tension_amp, 1.0))
            st.desperation = _clamp(st.desperation + 0.15 * tension_amp)
            st.anger = _clamp(st.anger + 0.08 * tension_amp)
            st.guilt = _clamp(st.guilt + 0.05 * tension_amp)

        elif intent_type == "search":
            # Searching for evidence — fear increases if clues related to character
            discovered = rule_result.get("discovered_clues", [])
            relevance = _clue_relevance(discovered, character_id)
            if relevance > 0:
                st.fear = _clamp(st.fear + 0.06 * relevance * tension_amp)
                st.composure = _clamp(st.composure - 0.04 * relevance * tension_amp)
                st.desperation = _clamp(st.desperation + 0.03 * relevance * tension_amp)

        elif intent_type == "observe" and is_target:
            # Being watched — slight unease
            st.composure = _clamp(st.composure - 0.01 * tension_amp)
            st.fear = _clamp(st.fear + 0.01 * tension_amp)

        elif intent_type == "eavesdrop":
            # If eavesdropping succeeds and reveals something, fear goes up
            if rule_result.get("success") == "full":
                st.fear = _clamp(st.fear + 0.03 * tension_amp)
                st.composure = _clamp(st.composure - 0.02 * tension_amp)

        # ---- Natural composure recovery (very small) ----
        # If the character was NOT the target this turn, they recover slightly.
        if not is_target and intent_type not in ("accuse",):
            st.composure = _clamp(st.composure + 0.02)
            st.anger = _clamp(st.anger - 0.02)

        # ---- Track emotional breaks ----
        if st.composure < 0.3:
            st.emotional_breaks += 1

        # ---- Desperation floor: once past a threshold it never fully resets ----
        # Characters don't just "calm down" from near-confession territory.
        if st.desperation > 0.5:
            st.desperation = _clamp(st.desperation - 0.01)  # tiny natural decay only

        # ---- Re-evaluate defensive strategy ----
        st.defensive_strategy = _choose_strategy(st)

        # ---- Alliance logic ----
        # When fear is high but anger is low, the character tries to ally with
        # the NPC they distrust least (i.e. redirect blame elsewhere).
        if st.fear > 0.5 and st.anger < 0.4:
            st.alliance_target = _pick_alliance_target(character_id)
        elif st.anger > 0.6:
            # Too angry to cooperate
            st.alliance_target = None

        return st

    # ------------------------------------------------------------------
    # Behaviour directives
    # ------------------------------------------------------------------

    def get_behavior_directive(self, session_id: str, character_id: str) -> dict:
        """
        Produce a behaviour directive dictionary that the dialogue-generating
        ``CharacterAgent`` can use to modulate tone, word choice, and body
        language.

        The directive contains:
            ``composure_level``  — "high" / "medium" / "low"
            ``manner``           — free-text description of how the NPC should
                                   speak and behave.
            ``strategy``         — the current ``defensive_strategy``.
            ``special_flags``    — list of additional flags (e.g. ``"may_confess"``,
                                   ``"wants_to_flee"``, ``"aggressive"``).

        Args:
            session_id:   Game session identifier.
            character_id: NPC identifier.

        Returns:
            A dict with keys ``composure_level``, ``manner``, ``strategy``,
            and ``special_flags``.
        """
        st = self.get_state(session_id, character_id)

        # ---- Composure band ----
        if st.composure > 0.6:
            composure_level = "high"
            manner = (
                "保持冷静的外表，说话平稳有条理，善于转移话题，"
                "偶尔用礼貌的微笑掩饰内心波动。"
            )
        elif st.composure > 0.3:
            composure_level = "medium"
            manner = (
                "表面镇定但开始露出破绽：偶尔出现口误、"
                "目光闪躲、手指不自觉地摩挲物品，回答越来越含糊。"
            )
        else:
            composure_level = "low"
            manner = (
                "几近崩溃：说话结巴、前后矛盾、"
                "可能脱口说出不该说的信息，呼吸急促，声音发抖。"
            )

        # ---- Special flags based on extreme values ----
        special_flags: List[str] = []

        if st.desperation > 0.7:
            special_flags.append("may_confess")
            manner += (
                "走投无路之下可能会吐露部分真相以转移矛头，"
                "或者把罪责推给其他人。"
            )

        if st.fear > 0.8:
            special_flags.append("wants_to_flee")
            manner += (
                "极度恐惧，试图结束对话、找借口离开，"
                "或者拼命把话题引向其他NPC。"
            )

        if st.anger > 0.7:
            special_flags.append("aggressive")
            manner += (
                "充满攻击性，语气尖锐，可能在愤怒中无意暴露信息。"
            )

        if st.guilt > 0.7 and st.composure < 0.4:
            special_flags.append("guilt_slip")
            manner += (
                "内疚感压倒理智，可能不自觉地为受害者说话或表现出过度的自责。"
            )

        if st.alliance_target:
            special_flags.append(f"seeking_ally:{st.alliance_target}")

        return {
            "composure_level": composure_level,
            "manner": manner,
            "strategy": st.defensive_strategy,
            "special_flags": special_flags,
        }

    # ------------------------------------------------------------------
    # Breaking-point detection
    # ------------------------------------------------------------------

    def check_breaking_point(
        self, session_id: str, character_id: str
    ) -> Optional[str]:
        """
        Check whether the character has reached a psychological breaking point
        that should trigger a special narrative event.

        Breaking points (checked in priority order):
            * ``desperation > 0.85``  → ``"partial_confession"``
            * ``composure  < 0.15``   → ``"emotional_breakdown"``
            * ``anger      > 0.9``    → ``"aggressive_outburst"``

        Only the highest-priority matching event is returned; the caller is
        responsible for deciding how to handle it (e.g. injecting a special
        NPC event into the turn response).

        Args:
            session_id:   Game session identifier.
            character_id: NPC identifier.

        Returns:
            A string event name, or ``None`` if no breaking point is reached.
        """
        st = self.get_state(session_id, character_id)

        if st.desperation > 0.85:
            return "partial_confession"
        if st.composure < 0.15:
            return "emotional_breakdown"
        if st.anger > 0.9:
            return "aggressive_outburst"

        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# Mapping of clue IDs to the character(s) they are most relevant to.
# A relevance score of 1.0 means the clue directly implicates the character;
# lower values mean indirect association.
_CLUE_RELEVANCE_MAP: Dict[str, Dict[str, float]] = {
    "study_scratches": {"linlan": 0.7, "zhoumu": 0.3},
    "wine_cellar_footprint": {"zhoumu": 0.8, "linlan": 0.3},
    "torn_letter": {"songzhi": 0.6, "linlan": 0.4},
    "will_draft": {"linlan": 1.0, "zhoumu": 0.9},
    "anonymous_tip": {"songzhi": 1.0},
    "cellar_sound": {"linlan": 0.5, "zhoumu": 0.6},
}


def _clue_relevance(discovered_clue_ids: List[str], character_id: str) -> float:
    """
    Return the maximum relevance score (0.0 – 1.0) of the discovered clues
    to *character_id*.  Returns 0.0 if none of the clues are relevant.
    """
    if not discovered_clue_ids:
        return 0.0
    scores = [
        _CLUE_RELEVANCE_MAP.get(cid, {}).get(character_id, 0.0)
        for cid in discovered_clue_ids
    ]
    return max(scores) if scores else 0.0


def _pick_alliance_target(character_id: str) -> Optional[str]:
    """
    Choose which other NPC *character_id* would try to ally with when under
    pressure.  This is a simple heuristic based on the story relationships.

    Returns:
        Another character's ID, or ``None``.
    """
    # Alliance preferences based on the Gu-family-case story:
    #   林岚 tries to ally with 宋知微 (both are calm, can trade info)
    #   周牧 tries to ally with 林岚  (she knows things; he wants cover)
    #   宋知微 tries to ally with 周牧 (easiest to manipulate for info)
    alliance_map: Dict[str, str] = {
        "linlan": "songzhi",
        "zhoumu": "linlan",
        "songzhi": "zhoumu",
    }
    return alliance_map.get(character_id)

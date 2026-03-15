"""
ConspiracyAgent: Manages NPC-NPC alliances, strategic blame-shifting,
and group dynamics so that characters feel like they interact with
each other instead of acting as isolated interrogation targets.

Pure game-logic module -- no LLM calls.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────
# Character roster constants
# ──────────────────────────────────────────────────────────────────────

CHARACTER_IDS = ["linlan", "zhoumu", "songzhi"]
CHARACTER_NAMES: Dict[str, str] = {
    "linlan": "林岚",
    "zhoumu": "周牧",
    "songzhi": "宋知微",
}

# All unique character pairs
ALL_PAIRS = [
    ("linlan", "zhoumu"),
    ("linlan", "songzhi"),
    ("zhoumu", "songzhi"),
]


# ──────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────

class AllianceState(BaseModel):
    """Tracks alliance between two characters."""
    char_a: str
    char_b: str
    strength: float = 0.0  # -1 (hostile) to 1 (strong allies)
    reason: str = ""


class ConspiracyState(BaseModel):
    session_id: str
    alliances: List[AllianceState] = Field(default_factory=list)
    active_schemes: List[str] = Field(default_factory=list)  # Current NPC strategies
    blame_target: Optional[str] = None  # Who NPCs are trying to redirect blame to
    information_shared: Dict[str, List[str]] = Field(default_factory=dict)  # What NPCs have shared between themselves


# ──────────────────────────────────────────────────────────────────────
# Pre-defined event pools (Chinese)
# Placeholders: {char_a}, {char_b}, {target}
# ──────────────────────────────────────────────────────────────────────

ALLIANCE_FORMATION_EVENTS: List[str] = [
    "{char_a}悄悄走到{char_b}身边，低声说了几句话。{char_b}的表情变得复杂起来。",
    "{char_a}和{char_b}交换了一个微妙的眼神，似乎达成了某种默契。",
    "{char_b}犹豫了一下，最终还是把手中的东西递给了{char_a}，两人之间的气氛微妙地缓和了。",
    "{char_a}轻声对{char_b}说：'我觉得我们现在应该站在同一边。'{char_b}沉默了几秒，缓缓点了点头。",
    "{char_b}主动给{char_a}倒了一杯水，两人站在角落里低声交谈，不时警惕地看向{target}的方向。",
    "你注意到{char_a}和{char_b}不知什么时候站到了一起，两人之间的距离明显比之前近了不少。",
    "{char_a}用手肘轻轻碰了碰{char_b}，朝你的方向微微示意。{char_b}心领神会地点了点头。",
]

BLAME_REDIRECT_EVENTS: List[str] = [
    "{char_a}突然提高声音：'与其怀疑我们，你有没有查过{target}为什么恰好出现在这里？'",
    "{char_a}冷笑一声：'你们都盯着我干什么？{target}从刚才开始就一直在回避关键问题。'",
    "{char_b}若有所思地说：'有意思……{target}，你刚才说的和我了解到的可不太一样。'",
    "{char_a}转向你，压低声音说：'我劝你仔细查查{target}。有些事……我不方便明说。'",
    "'{target}那晚的行踪，你核实过吗？'{char_a}意味深长地看了{char_b}一眼。",
    "{char_b}突然开口：'说到底，在场的人里，{target}的动机最明显不是吗？'房间里一时安静下来。",
    "{char_a}叹了口气：'我本来不想说的……但{target}昨晚的表现，实在太反常了。'",
]

BETRAYAL_EVENTS: List[str] = [
    "{char_a}冷冷地看了{char_b}一眼：'如果你要把我拖下水，我可不会陪你演戏。'",
    "{char_a}突然转向你：'我有些事想单独告诉你。关于{char_b}……你可能被骗了。'",
    "{char_b}的脸色瞬间变了：'{char_a}，你这是什么意思？我们不是说好了——'话到一半，{char_a}已经转身走开了。",
    "'{char_b}，你自己的问题还没解释清楚吧？'{char_a}的语气突然变得冰冷，之前的默契荡然无存。",
    "{char_a}猛地站起来指着{char_b}：'够了！我不想再替你隐瞒了！'",
    "你注意到{char_a}悄悄把一样东西藏进了口袋——那似乎是刚才{char_b}给的纸条。{char_a}的表情耐人寻味。",
    "{char_a}的声音很轻，但每个字都像刀子：'{char_b}，从现在开始，你说的每一句话，我都会如实转告。'",
]

TENSION_ESCALATION_EVENTS: List[str] = [
    "{char_a}猛地站起来：'够了！你们都不要再问了！'椅子差点翻倒，房间里一片沉默。",
    "空气仿佛凝固了。{char_a}和{char_b}互相瞪视着，谁也不肯先移开目光。",
    "{char_a}的拳头紧紧攥着，指节发白。{char_b}不自觉地后退了一步。",
    "'你们到底想怎样？！'{char_a}的声音在颤抖，情绪已经到了崩溃的边缘。",
    "{char_b}苦笑着摇了摇头：'事情到了这一步，我看在座的每一个人都脱不了干系。'",
    "一声巨响——{char_a}一拳砸在桌子上。所有人都愣住了。沉默比任何话语都更让人不安。",
    "{char_a}深吸一口气，双手捂住脸：'我不想再待在这里了……这个地方让我快疯了。'",
]


# ──────────────────────────────────────────────────────────────────────
# Helper: pick a character name, handling placeholder → display name
# ──────────────────────────────────────────────────────────────────────

def _name(char_id: str) -> str:
    """Return the Chinese display name for a character id."""
    return CHARACTER_NAMES.get(char_id, char_id)


def _fill_template(
    template: str,
    char_a: str,
    char_b: str,
    target: str = "",
) -> str:
    """Fill a template string with character display names."""
    return template.format(
        char_a=_name(char_a),
        char_b=_name(char_b),
        target=_name(target) if target else "",
    )


def _other_characters(exclude: str) -> List[str]:
    """Return character ids excluding the given one."""
    return [c for c in CHARACTER_IDS if c != exclude]


# ──────────────────────────────────────────────────────────────────────
# Simplified psych snapshot that the engine can produce per character
# ──────────────────────────────────────────────────────────────────────

class CharacterPsychState(BaseModel):
    """Lightweight psychology snapshot passed into the conspiracy agent."""
    character_id: str
    suspicion: int = 30        # 0-100
    trust_to_player: int = 50  # 0-100
    desperation: float = 0.0   # 0-1, derived from suspicion + trust loss


# ──────────────────────────────────────────────────────────────────────
# ConspiracyAgent
# ──────────────────────────────────────────────────────────────────────

class ConspiracyAgent:
    """
    Manages NPC-NPC dynamics: alliances, strategic blame-shifting,
    information sharing, and betrayals.

    Pure game logic -- no LLM calls.
    """

    def __init__(self) -> None:
        # session_id -> ConspiracyState
        self._states: Dict[str, ConspiracyState] = {}

    # ── internal helpers ─────────────────────────────────────────────

    def _get_or_create(self, session_id: str) -> ConspiracyState:
        """Retrieve an existing conspiracy state or bootstrap a new one."""
        if session_id not in self._states:
            # Seed initial alliances for every pair at neutral
            alliances = [
                AllianceState(
                    char_a=a,
                    char_b=b,
                    strength=0.0,
                    reason="初始状态",
                )
                for a, b in ALL_PAIRS
            ]
            # LinLan and ZhouMu start with a slight natural affinity
            # (both know about the will)
            for a in alliances:
                if {a.char_a, a.char_b} == {"linlan", "zhoumu"}:
                    a.strength = 0.2
                    a.reason = "双方都了解遗嘱相关内情，存在天然利益关联"
            self._states[session_id] = ConspiracyState(
                session_id=session_id,
                alliances=alliances,
                information_shared={cid: [] for cid in CHARACTER_IDS},
            )
        return self._states[session_id]

    def _find_alliance(
        self, state: ConspiracyState, a: str, b: str
    ) -> Optional[AllianceState]:
        """Find the alliance record between two characters (order-agnostic)."""
        pair = {a, b}
        for al in state.alliances:
            if {al.char_a, al.char_b} == pair:
                return al
        return None

    @staticmethod
    def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, value))

    # ── public API ───────────────────────────────────────────────────

    def update_alliances(
        self,
        session_id: str,
        characters_psych_states: List[CharacterPsychState],
        player_target: Optional[str],
        discovered_clues: List[str],
        tension: int,
    ) -> ConspiracyState:
        """
        Update alliance dynamics based on current game state.

        Parameters
        ----------
        session_id : str
            Current game session.
        characters_psych_states : list[CharacterPsychState]
            Latest psychological snapshot for each NPC.
        player_target : str | None
            The character_id the player is currently focusing on (or None).
        discovered_clues : list[str]
            Clue IDs discovered so far.
        tension : int
            Current global tension (0-100).

        Returns
        -------
        ConspiracyState
            The updated conspiracy state for this session.
        """
        cs = self._get_or_create(session_id)
        psych_map: Dict[str, CharacterPsychState] = {
            p.character_id: p for p in characters_psych_states
        }

        # ---- Rule 1: Player pressure creates defensive alliances ----
        if player_target and player_target in CHARACTER_IDS:
            defenders = _other_characters(player_target)
            alliance = self._find_alliance(cs, defenders[0], defenders[1])
            if alliance:
                # The more pressure, the stronger the defensive bond
                target_suspicion = psych_map.get(
                    player_target, CharacterPsychState(character_id=player_target)
                ).suspicion
                pressure_factor = target_suspicion / 100.0  # 0-1
                delta = 0.05 + 0.10 * pressure_factor
                alliance.strength = self._clamp(alliance.strength + delta)
                alliance.reason = (
                    f"玩家持续施压{_name(player_target)}，"
                    f"{_name(defenders[0])}和{_name(defenders[1])}产生防御性同盟"
                )

            # The pressured character's alliance with others weakens slightly
            # (others don't want guilt by association)
            for other in defenders:
                al = self._find_alliance(cs, player_target, other)
                if al:
                    al.strength = self._clamp(al.strength - 0.03)

        # ---- Rule 2: Strong evidence against one -> others distance ----
        for psych in characters_psych_states:
            if psych.suspicion >= 70:
                for other in _other_characters(psych.character_id):
                    al = self._find_alliance(cs, psych.character_id, other)
                    if al:
                        al.strength = self._clamp(al.strength - 0.08)
                        al.reason = (
                            f"{_name(psych.character_id)}嫌疑过高，"
                            f"{_name(other)}开始保持距离"
                        )

        # ---- Rule 3: High tension destabilizes all alliances ----
        if tension > 70:
            instability = (tension - 70) / 30.0  # 0-1 over 70-100
            for al in cs.alliances:
                # Stronger alliances are more resistant but not immune
                erosion = 0.04 * instability * (1.0 - 0.5 * max(al.strength, 0))
                al.strength = self._clamp(al.strength - erosion)

        # ---- Rule 4: Natural affinity (linlan-zhoumu shared knowledge) ----
        # Reinforced slightly each update if neither is under extreme pressure
        ll_psych = psych_map.get(
            "linlan", CharacterPsychState(character_id="linlan")
        )
        zm_psych = psych_map.get(
            "zhoumu", CharacterPsychState(character_id="zhoumu")
        )
        al_lz = self._find_alliance(cs, "linlan", "zhoumu")
        if al_lz and ll_psych.suspicion < 70 and zm_psych.suspicion < 70:
            al_lz.strength = self._clamp(al_lz.strength + 0.02)

        # ---- Rule 5: SongZhi gravitates toward the less suspicious ----
        sz_psych = psych_map.get(
            "songzhi", CharacterPsychState(character_id="songzhi")
        )
        if sz_psych:
            others = [
                (cid, psych_map.get(cid, CharacterPsychState(character_id=cid)))
                for cid in ["linlan", "zhoumu"]
            ]
            # Sort by suspicion ascending -> ally with the less suspicious one
            others.sort(key=lambda x: x[1].suspicion)
            preferred, rejected = others[0][0], others[1][0]
            al_pref = self._find_alliance(cs, "songzhi", preferred)
            al_rej = self._find_alliance(cs, "songzhi", rejected)
            if al_pref:
                al_pref.strength = self._clamp(al_pref.strength + 0.03)
                al_pref.reason = (
                    f"{_name('songzhi')}倾向于和嫌疑较低的{_name(preferred)}靠近"
                )
            if al_rej:
                al_rej.strength = self._clamp(al_rej.strength - 0.02)

        # ---- Determine blame target ----
        # NPCs collectively try to redirect blame to the most suspicious member
        most_suspicious = max(
            characters_psych_states, key=lambda p: p.suspicion
        )
        if most_suspicious.suspicion >= 50:
            cs.blame_target = most_suspicious.character_id
        else:
            cs.blame_target = None

        # ---- Update active schemes ----
        cs.active_schemes = self._derive_schemes(cs, psych_map, tension)

        # ---- Track information leaks from discovered clues ----
        clue_evidence_map: Dict[str, str] = {
            "study_scratches": "linlan",
            "wine_cellar_footprint": "zhoumu",
            "torn_letter": "songzhi",
            "will_draft": "zhoumu",
            "anonymous_tip": "songzhi",
            "cellar_sound": "linlan",
        }
        for clue_id in discovered_clues:
            implicated = clue_evidence_map.get(clue_id)
            if implicated:
                for other in _other_characters(implicated):
                    shared = cs.information_shared.setdefault(other, [])
                    info = f"玩家发现了与{_name(implicated)}相关的线索({clue_id})"
                    if info not in shared:
                        shared.append(info)

        return cs

    def _derive_schemes(
        self,
        cs: ConspiracyState,
        psych_map: Dict[str, CharacterPsychState],
        tension: int,
    ) -> List[str]:
        """Derive the current active strategies based on alliance state."""
        schemes: List[str] = []

        # Strong alliances -> coordinated deflection
        for al in cs.alliances:
            if al.strength >= 0.4:
                target = cs.blame_target
                if target and target not in (al.char_a, al.char_b):
                    schemes.append(
                        f"{_name(al.char_a)}和{_name(al.char_b)}联合将怀疑引向{_name(target)}"
                    )
                else:
                    schemes.append(
                        f"{_name(al.char_a)}和{_name(al.char_b)}互相掩护，统一口径"
                    )

        # Hostile alliances -> active sabotage
        for al in cs.alliances:
            if al.strength <= -0.4:
                schemes.append(
                    f"{_name(al.char_a)}和{_name(al.char_b)}互相拆台，争相把嫌疑推给对方"
                )

        # High-desperation characters -> solo survival mode
        for cid in CHARACTER_IDS:
            psych = psych_map.get(cid, CharacterPsychState(character_id=cid))
            if psych.desperation > 0.7:
                schemes.append(
                    f"{_name(cid)}已陷入自保模式，可能做出不可预测的举动"
                )

        # High tension global scheme
        if tension >= 80:
            schemes.append("局势高度紧张，所有人的伪装随时可能崩塌")

        return schemes

    # ── NPC event generation ─────────────────────────────────────────

    def get_npc_events(
        self,
        session_id: str,
        tension: int,
        phase: str,
        round_num: int,
    ) -> List[str]:
        """
        Generate 0-2 strategic NPC interaction events based on the
        current conspiracy state.

        Parameters
        ----------
        session_id : str
        tension : int  (0-100)
        phase : str    Current game phase.
        round_num : int

        Returns
        -------
        list[str]
            0-2 event descriptions in Chinese.
        """
        cs = self._get_or_create(session_id)
        events: List[str] = []

        # Probability of generating an event scales with round & tension
        base_chance = min(0.3 + round_num * 0.04 + tension * 0.003, 0.85)

        # --- Decide which event type to generate ---

        # Find strongest positive and strongest negative alliance
        strongest_ally = max(cs.alliances, key=lambda a: a.strength)
        strongest_rival = min(cs.alliances, key=lambda a: a.strength)

        # Determine a blame target fallback
        blame_target = cs.blame_target or random.choice(CHARACTER_IDS)

        # Event 1: primary event
        if random.random() < base_chance:
            event_text = self._pick_primary_event(
                cs, tension, strongest_ally, strongest_rival, blame_target
            )
            if event_text:
                events.append(event_text)

        # Event 2: secondary event (lower chance, only at mid-high tension)
        secondary_chance = base_chance * 0.4 if tension >= 40 else 0.0
        if random.random() < secondary_chance and len(events) < 2:
            event_text = self._pick_secondary_event(
                cs, tension, strongest_ally, blame_target
            )
            if event_text and event_text not in events:
                events.append(event_text)

        return events

    def share_information(
        self,
        session_id: str,
        source_character_id: str,
        target_character_id: str,
        info: str,
    ) -> None:
        """Record an explicit NPC-to-NPC information transfer."""
        cs = self._get_or_create(session_id)
        display = f"{_name(source_character_id)}私下透露：{info}"
        bucket = cs.information_shared.setdefault(target_character_id, [])
        if display not in bucket:
            bucket.append(display)

    def _pick_primary_event(
        self,
        cs: ConspiracyState,
        tension: int,
        strongest_ally: AllianceState,
        strongest_rival: AllianceState,
        blame_target: str,
    ) -> Optional[str]:
        """Select and fill a primary NPC event."""
        # High tension + hostile alliance -> betrayal or escalation
        if tension >= 70 and strongest_rival.strength <= -0.3:
            pool = BETRAYAL_EVENTS if random.random() < 0.6 else TENSION_ESCALATION_EVENTS
            template = random.choice(pool)
            return _fill_template(
                template,
                char_a=strongest_rival.char_a,
                char_b=strongest_rival.char_b,
                target=blame_target,
            )

        # High tension -> escalation
        if tension >= 60:
            pool = TENSION_ESCALATION_EVENTS
            # Pick the most desperate pair
            pair = random.choice(ALL_PAIRS)
            template = random.choice(pool)
            return _fill_template(
                template, char_a=pair[0], char_b=pair[1], target=blame_target
            )

        # Strong alliance exists -> show alliance or blame redirect
        if strongest_ally.strength >= 0.3:
            third = [
                c for c in CHARACTER_IDS
                if c not in (strongest_ally.char_a, strongest_ally.char_b)
            ][0]
            if random.random() < 0.5:
                template = random.choice(ALLIANCE_FORMATION_EVENTS)
                return _fill_template(
                    template,
                    char_a=strongest_ally.char_a,
                    char_b=strongest_ally.char_b,
                    target=third,
                )
            else:
                template = random.choice(BLAME_REDIRECT_EVENTS)
                return _fill_template(
                    template,
                    char_a=strongest_ally.char_a,
                    char_b=strongest_ally.char_b,
                    target=third,
                )

        # Default: mild alliance-forming or blame redirect
        pair = random.choice(ALL_PAIRS)
        third = [c for c in CHARACTER_IDS if c not in pair][0]
        if random.random() < 0.6:
            template = random.choice(ALLIANCE_FORMATION_EVENTS)
        else:
            template = random.choice(BLAME_REDIRECT_EVENTS)
        return _fill_template(
            template, char_a=pair[0], char_b=pair[1], target=third
        )

    def _pick_secondary_event(
        self,
        cs: ConspiracyState,
        tension: int,
        strongest_ally: AllianceState,
        blame_target: str,
    ) -> Optional[str]:
        """Select and fill a secondary (less dramatic) NPC event."""
        # Prefer blame redirect as secondary
        redirector = random.choice(
            [c for c in CHARACTER_IDS if c != blame_target]
        )
        other = [
            c for c in CHARACTER_IDS if c not in (redirector, blame_target)
        ][0]
        template = random.choice(BLAME_REDIRECT_EVENTS)
        return _fill_template(
            template, char_a=redirector, char_b=other, target=blame_target
        )

    # ── Character conspiracy context injection ───────────────────────

    def get_character_conspiracy_context(
        self, session_id: str, character_id: str
    ) -> str:
        """
        Return a Chinese context string to inject into a character's
        dialogue system prompt, describing their current alliance strategy.

        Parameters
        ----------
        session_id : str
        character_id : str

        Returns
        -------
        str
            Chinese text suitable for appending to the character system prompt.
        """
        cs = self._get_or_create(session_id)

        lines: List[str] = []
        lines.append("【当前人际关系与策略】")

        # Describe each alliance from this character's perspective
        for al in cs.alliances:
            if character_id not in (al.char_a, al.char_b):
                continue
            partner = al.char_b if al.char_a == character_id else al.char_a
            partner_name = _name(partner)

            if al.strength >= 0.5:
                lines.append(
                    f"- 你和{partner_name}目前是较为紧密的同盟关系。"
                    f"你们应该互相配合，统一口径，必要时帮对方打掩护。"
                )
            elif al.strength >= 0.2:
                lines.append(
                    f"- 你和{partner_name}目前关系尚可，有合作的基础。"
                    f"在不暴露自己秘密的前提下，可以适当配合对方。"
                )
            elif al.strength >= -0.2:
                lines.append(
                    f"- 你和{partner_name}目前关系一般，保持观望即可。"
                )
            elif al.strength >= -0.5:
                lines.append(
                    f"- 你和{partner_name}之间的关系趋于紧张。"
                    f"对方可能随时把矛头指向你，你需要提高警惕。"
                )
            else:
                lines.append(
                    f"- 你和{partner_name}已经几乎撕破脸了。"
                    f"如果对方试图攻击你，你可以毫不犹豫地反击和揭露对方的问题。"
                )

        # Blame strategy
        if cs.blame_target and cs.blame_target != character_id:
            target_name = _name(cs.blame_target)
            lines.append(
                f"\n【策略指引】当话题对你不利时，你可以巧妙地把怀疑引向{target_name}。"
                f"不要太直白，可以用暗示、反问或'无意'提及的方式。"
            )
        elif cs.blame_target == character_id:
            # This character IS the blame target -- they should be defensive
            lines.append(
                "\n【策略指引】你目前被其他人暗中针对，感觉到了来自多个方向的压力。"
                "你应该更加谨慎地措辞，尽量把话题引向别人，或者用情绪化的方式转移注意力。"
            )
        else:
            lines.append(
                "\n【策略指引】目前没有明确的嫌疑焦点，你应该观察局势，"
                "避免成为第一个被怀疑的人。"
            )

        # Information that this character has learned from NPC-NPC interaction
        shared = cs.information_shared.get(character_id, [])
        if shared:
            lines.append("\n【你从其他角色处间接获知的信息】")
            for info in shared[-3:]:  # Only the most recent 3
                lines.append(f"- {info}")

        # Reveal / hide guidance based on alliance state
        allies = [
            al for al in cs.alliances
            if character_id in (al.char_a, al.char_b) and al.strength >= 0.3
        ]
        if allies:
            ally_names = []
            for al in allies:
                partner = al.char_b if al.char_a == character_id else al.char_a
                ally_names.append(_name(partner))
            names_str = "、".join(ally_names)
            lines.append(
                f"\n【信息管理】你目前和{names_str}有同盟关系。"
                f"不要在玩家面前说任何可能让同盟者处于不利地位的话。"
                f"如果玩家问到与同盟者相关的敏感信息，你应该帮忙打圆场或岔开话题。"
            )
        else:
            lines.append(
                "\n【信息管理】你目前没有可靠的同盟者，一切只能靠自己。"
                "谨慎地释放信息，确保每一句话都对自己有利。"
            )

        return "\n".join(lines)

    # ── Betrayal check ───────────────────────────────────────────────

    def should_trigger_betrayal(
        self,
        session_id: str,
        character_id: str,
        tension: int,
    ) -> Optional[str]:
        """
        Check if conditions are met for a character to betray their ally.

        Conditions (ALL must be met):
        - Alliance strength with at least one partner < 0.3
        - Tension > 60
        - Character desperation > 0.5

        Parameters
        ----------
        session_id : str
        character_id : str
        tension : int

        Returns
        -------
        str | None
            Betrayal event text (Chinese) or None if no betrayal triggers.
        """
        cs = self._get_or_create(session_id)

        if tension <= 60:
            return None

        # We need to estimate desperation from the conspiracy state.
        # In a full integration, this would come from CharacterPsychState;
        # here we derive it from how many alliances are weak/hostile.
        own_alliances = [
            al for al in cs.alliances
            if character_id in (al.char_a, al.char_b)
        ]
        if not own_alliances:
            return None

        # Desperation proxy: average of (1 - alliance_strength) over own alliances
        # clamped to 0-1. More isolated = more desperate.
        avg_strength = sum(al.strength for al in own_alliances) / len(own_alliances)
        desperation = max(0.0, min(1.0, 0.5 - avg_strength + tension / 200.0))

        if desperation <= 0.5:
            return None

        # Find a weak alliance to betray
        for al in own_alliances:
            if al.strength < 0.3:
                partner = al.char_b if al.char_a == character_id else al.char_a
                third = [
                    c for c in CHARACTER_IDS
                    if c not in (character_id, partner)
                ][0]

                template = random.choice(BETRAYAL_EVENTS)
                event_text = _fill_template(
                    template,
                    char_a=character_id,
                    char_b=partner,
                    target=third,
                )

                # Betrayal consequences: alliance drops sharply
                al.strength = self._clamp(al.strength - 0.3)
                al.reason = (
                    f"{_name(character_id)}背叛了{_name(partner)}，同盟关系破裂"
                )

                return event_text

        return None

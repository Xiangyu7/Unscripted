"""
Turn Engine v3 — Sandbox + DM Control

Architecture:
  Layer 0: World State + Open Action Engine + NPC Autonomy (sandbox foundation)
  Layer 1: Expert Agents (psychology, conspiracy, continuity, architect, tension)
  Layer 2: DM Agent (final arbiter — receives ALL proposals, makes ONE coherent decision)
  Layer 3: Character Agent + Image Agent (presentation)

The Director Agent is REMOVED — its role is fully covered by:
  - Story Architect (narrative planning)
  - DM Agent (final decisions)
"""

import asyncio
from typing import Dict, List, Optional

# Agents (真 Agent — LLM 推理)
from agents.character_agent import CharacterAgent
from agents.deduction_validator import DeductionValidator
from agents.dm_agent import DMAgent, AgentProposals
from agents.story_architect_agent import StoryArchitectAgent

# Systems (纯逻辑 — 0 token)
from systems.psychology_system import CharacterPsychologyAgent
from systems.conspiracy_system import ConspiracyAgent
from systems.conspiracy_system import CharacterPsychState as ConspiracyPsychState
from systems.continuity_system import ContinuityGuardian
from systems.lie_detector import LieDetector
from systems.npc_behavior_system import NPCAutonomyAgent
from systems.score_system import calculate_score
from systems.tension_system import TensionConductor
from systems.npc_interaction import NPCInteractionSystem, build_memory_context
from systems.npc_secret_conversation import SecretConversationSystem
from systems.notebook_system import NotebookSystem
from systems.checkpoint_system import CheckpointSystem
from systems.action_cost_system import ActionCostSystem
from systems.confrontation_system import ConfrontationSystem
from engine.truth_resolver import TruthResolver

# Services (外部 API 封装)
from services.image_service import ImageAgent
from config import Config, LLMProvider
from engine.open_action_engine import OpenActionEngine
from engine.world_state import WorldStateManager
from schemas.game_state import (
    CheckpointState,
    ConfrontationState,
    Event,
    GameState,
    IntentType,
    NPCEvent,
    NPCReply,
    PublicStatement,
    TurnResponse,
    VoteOption,
    VoteRecord,
    VoteState,
    get_character_scoped_facts,
    get_fact_by_id,
    record_fact_disclosure,
    redact_game_state,
)


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


sessions: Dict[str, GameState] = {}

CONFRONTATION_COMMANDS = {
    "公开对峙",
    "发起公开对峙",
    "开始公开对峙",
    "进入公开对峙",
}

FINAL_VOTE_OPTIONS = [
    VoteOption(id="linlan", label="林岚"),
    VoteOption(id="zhoumu", label="周牧"),
    VoteOption(id="songzhi", label="宋知微"),
    VoteOption(id="guyan_self_staged", label="顾言自导自演", kind="theory"),
]

FINAL_VOTE_THEORIES = {
    "linlan": "林岚策划了顾言的失踪案，并且一直在掩盖真相。",
    "zhoumu": "周牧因为遗产冲突策划了顾言的失踪案。",
    "songzhi": "宋知微为了独家新闻提前策划了这场失踪风波。",
    "guyan_self_staged": "顾言自导自演，假装失踪，躲在酒窖密室里试探所有人。",
}

CLUE_FACT_MAP = {
    # Layer 1: physical evidence
    "study_scratches": ["clue_study_scratches"],
    "wine_cellar_footprint": ["clue_wine_cellar_footprint"],
    "torn_letter": ["clue_torn_letter"],
    "anonymous_tip": ["clue_anonymous_tip"],
    # Layer 2: key evidence
    "will_draft": ["clue_will_draft", "shared_estate_tension"],
    "cellar_provisions": ["clue_cellar_provisions"],
    # Layer 3: truth evidence
    "linlan_phone_log": ["clue_linlan_phone_log"],
    "cellar_sound": ["clue_cellar_sound"],
    "staged_evidence": ["clue_staged_evidence"],
}


# ── Character voice mapping ──
# Each character gets a maximally distinct GLM-TTS voice.
# Narrator uses a deep, cinematic voice.
CHARACTER_VOICES = {
    "linlan":   "xiaochen",  # 林岚: 小陈 — 成熟冷静的女声，适合秘书
    "zhoumu":   "chuichui",  # 周牧: 锤锤 — 成人男声，略带紧张
    "songzhi":  "tongtong",  # 宋知微: 彤彤 — 清晰干练的女声，适合记者
    "narrator": "xiaochen",  # 旁白: 小陈 — 用慢速+低语速营造解说感
}
# NOTE: GLM TTS 只有 3 个成人音色 (tongtong/chuichui/xiaochen)
# jam/kazi/douji/luodo 是"动物圈"卡通音色，不适合成人角色


def _character_voice(character_id: str, psych_state) -> tuple:
    """Return (voice_id, speed) for a character based on psychology."""
    voice = CHARACTER_VOICES.get(character_id, "tongtong")

    # Base speed
    speed = 1.0

    if psych_state is None:
        return voice, speed

    # Emotion → speed modulation
    composure = getattr(psych_state, "composure", 0.8)
    anger = getattr(psych_state, "anger", 0.1)
    fear = getattr(psych_state, "fear", 0.2)
    desperation = getattr(psych_state, "desperation", 0.0)

    # Low composure → speak faster (nervous, stumbling)
    if composure < 0.3:
        speed += 0.3
    elif composure < 0.5:
        speed += 0.15

    # High anger → speak faster and louder
    if anger > 0.7:
        speed += 0.2

    # High fear → speak faster (rushed)
    if fear > 0.7:
        speed += 0.15

    # High desperation → slow down (defeated, exhausted)
    if desperation > 0.7:
        speed -= 0.15

    # Clamp to GLM TTS range
    speed = max(0.5, min(2.0, speed))

    return voice, round(speed, 2)


# Words that indicate LLM hallucinated a wrong setting
_BANNED_SETTING_WORDS = ["城堡", "庄园", "教堂", "图书馆", "博物馆", "宫殿", "神殿", "地牢"]

# Replacements for common hallucinations
_SETTING_REPLACEMENTS = {
    "城堡": "老宅",
    "庄园": "老宅",
    "教堂": "宴会厅",
    "图书馆": "书房",
    "博物馆": "宴会厅",
    "宫殿": "老宅",
    "神殿": "老宅",
    "地牢": "酒窖",
}


def _compute_mood(psych_state) -> str:
    """Map a CharacterPsychState to a mood label for the frontend.

    Priority order: desperate > angry > fearful > nervous > calm > guarded.
    """
    if psych_state is None:
        return "neutral"
    desperation = getattr(psych_state, "desperation", 0.0)
    anger = getattr(psych_state, "anger", 0.1)
    fear = getattr(psych_state, "fear", 0.2)
    composure = getattr(psych_state, "composure", 0.8)

    if desperation > 0.6:
        return "desperate"   # 绝望
    if anger > 0.6:
        return "angry"       # 愤怒
    if fear > 0.6:
        return "fearful"     # 恐惧
    if composure < 0.3:
        return "nervous"     # 紧张
    if composure > 0.7 and anger < 0.2:
        return "calm"        # 冷静
    return "guarded"         # 警惕


def _sanitize_narration(text: str) -> str:
    """Fix LLM hallucinations that break the game setting."""
    if not text:
        return text
    for wrong, correct in _SETTING_REPLACEMENTS.items():
        if wrong in text:
            text = text.replace(wrong, correct)
    return text


def _get_current_scene_short(scene: str, available_scenes: List[str]) -> str:
    """Extract short scene name from full scene string like '顾家老宅·宴会厅' → '宴会厅'."""
    for s in available_scenes:
        if s in scene:
            return s
    return scene


def _discover_clues_for_action(
    state: GameState,
    action_category: str,
    legacy_intent: str,
    player_location: str,
) -> List[str]:
    """
    Bridge between Open Action Engine and clue system.
    Maps action categories to clue discovery conditions.
    """
    discovered = []
    location = _get_current_scene_short(player_location, state.available_scenes)

    # Map action categories to the intent types used in clue conditions
    is_search = action_category in ("investigate",) or legacy_intent in ("search", "observe")
    is_eavesdrop = action_category in ("stealth",) or legacy_intent == "eavesdrop"
    is_observe = legacy_intent == "observe"

    for clue in state.clues:
        if clue.discovered:
            continue
        if clue.location != location:
            continue

        condition = clue.discover_condition
        can_discover = False

        # Check all OR-separated conditions
        parts = condition.split("或") if "或" in condition else [condition]

        for part in parts:
            part = part.strip()

            # "search<location>" condition
            if f"search{location}" in part and is_search:
                if "tension>=" in part:
                    try:
                        threshold = int(part.split("tension>=")[1].split()[0])
                        if state.tension >= threshold:
                            can_discover = True
                    except (ValueError, IndexError):
                        can_discover = True
                else:
                    can_discover = True

            # "eavesdrop<location>" condition
            if f"eavesdrop{location}" in part and is_eavesdrop:
                can_discover = True

            # "observe" condition
            if "observe" in part and is_observe:
                can_discover = True

        if can_discover:
            discovered.append(clue.id)

    return discovered


def _record_behavior_tags(state: GameState, action_result, player_action: str, target_char_id: str | None):
    """Record behavior tags based on player action for ending calculation."""
    tags = state.behavior_tags
    choices = state.key_choices

    cat = action_result.action_category
    intent = action_result.legacy_intent

    # Investigation style
    if cat in ("investigate", "stealth"):
        tags["investigate"] = tags.get("investigate", 0) + 1
    if cat == "confront" or intent == "accuse":
        tags["aggressive"] = tags.get("aggressive", 0) + 1
    if cat == "social" and any(kw in player_action for kw in ["安慰", "理解", "相信", "帮", "没事", "别怕"]):
        tags["empathetic"] = tags.get("empathetic", 0) + 1
    if cat == "manipulate" or intent == "bluff":
        tags["manipulative"] = tags.get("manipulative", 0) + 1
    if cat in ("investigate",) and any(kw in player_action for kw in ["手机", "包", "口袋", "钱包", "私人"]):
        tags["searched_private"] = tags.get("searched_private", 0) + 1
    if cat in ("environmental",) and any(kw in player_action for kw in ["砸", "摔", "打碎", "踢"]):
        tags["destructive"] = tags.get("destructive", 0) + 1
    if cat == "communicate" and any(kw in player_action for kw in ["威胁", "恐吓", "警告", "最后机会"]):
        tags["threatening"] = tags.get("threatening", 0) + 1

    # Track unique locations visited
    scene_short = state.scene.split("·")[-1] if "·" in state.scene else state.scene
    visited_key = f"visited_{scene_short}"
    if visited_key not in tags:
        tags[visited_key] = 1

    # Key choices (irreversible moments)
    # Helped Zhou Mu when he was vulnerable
    if target_char_id == "zhoumu" and cat == "social" and any(kw in player_action for kw in ["安慰", "帮", "相信", "理解"]):
        if "helped_zhoumu" not in choices:
            choices.append("helped_zhoumu")

    # Exposed Lin Lan publicly
    if target_char_id == "linlan" and cat == "confront" and any(kw in player_action for kw in ["手机", "消息", "按计划", "揭露", "揭穿"]):
        if "exposed_linlan" not in choices:
            choices.append("exposed_linlan")

    # Shared info with Song Zhiwei
    if target_char_id == "songzhi" and cat in ("communicate", "social") and any(kw in player_action for kw in ["告诉", "分享", "交换", "给你看", "展示"]):
        if "trusted_songzhi" not in choices:
            choices.append("trusted_songzhi")


def _calc_truth_level(state: GameState) -> str:
    """A=complete, B=core, C=partial, D=lost"""
    discovered_ids = {c.id for c in state.clues if c.discovered}

    truth_clues = {"cellar_sound", "staged_evidence", "linlan_phone_log"}
    key_clues = {"will_draft", "cellar_provisions"}

    truth_found = len(truth_clues & discovered_ids)
    key_found = len(key_clues & discovered_ids)
    total_found = len(discovered_ids)

    if truth_found >= 2 and key_found >= 1 and total_found >= 6:
        return "A"  # Complete truth
    elif truth_found >= 1 and total_found >= 4:
        return "B"  # Core truth
    elif total_found >= 2:
        return "C"  # Partial
    else:
        return "D"  # Lost


def _calc_moral_stance(state: GameState) -> str:
    """X=just, Y=gray, Z=chaos"""
    tags = state.behavior_tags

    aggressive = tags.get("aggressive", 0) + tags.get("threatening", 0)
    destructive = tags.get("destructive", 0)
    private_search = tags.get("searched_private", 0)
    empathetic = tags.get("empathetic", 0)
    manipulative = tags.get("manipulative", 0)

    chaos_score = aggressive + destructive * 2 + manipulative
    justice_score = empathetic * 2 - private_search - manipulative

    if chaos_score >= 6 or destructive >= 2 or state.tension >= 90:
        return "Z"  # Chaos
    elif justice_score >= 2 and private_search <= 1 and aggressive <= 2:
        return "X"  # Just
    else:
        return "Y"  # Gray area


def _calc_relationship(state: GameState) -> str:
    """α=allied, β=isolated, γ=hostile"""
    allies = 0
    hostile = 0
    for char in state.characters:
        if char.trust_to_player >= 60:
            allies += 1
        elif char.trust_to_player <= 20:
            hostile += 1

    if hostile >= 2:
        return "γ"  # Hostile
    elif allies >= 1:
        return "α"  # Allied
    else:
        return "β"  # Isolated


def _resolve_ending(truth: str, moral: str, rel: str, state: GameState) -> str:
    """Generate ending text based on the three dimensions."""
    discovered_count = sum(1 for c in state.clues if c.discovered)
    choices = state.key_choices

    # Get NPC names for personalized endings
    ally_names = [c.name for c in state.characters if c.trust_to_player >= 60]
    hostile_names = [c.name for c in state.characters if c.trust_to_player <= 20]

    # ── Complete truth endings ──
    if truth == "A":
        if moral == "X" and rel == "α":
            ally = ally_names[0] if ally_names else "林岚"
            return (
                f"完美破局——{ally}在最后关头站到了你这边。\n\n"
                f"「跟我来。」{ally}带你走向酒窖深处，推开那扇隐藏的暗门。\n"
                "顾言就坐在里面，看着监控画面。他抬头看你，缓缓鼓掌。\n\n"
                "「你是唯一一个既找到了真相，又没有伤害任何人的人。」\n"
                "「这场试探——你通过了。不只是智力上的，更是人格上的。」"
            )
        elif moral == "Z":
            return (
                "真相的讽刺——你找到了全部真相，但你的方式让所有人心寒。\n\n"
                "顾言从酒窖密室走出来，看了看满地狼藉，又看了看你。\n"
                "「你确实聪明。」他的语气很平淡，「但如果查案的过程中你变成了比嫌疑人更可怕的人——"
                "那找到真相又有什么意义？」\n\n"
                "他转身走了。你赢了推理，但输了更重要的东西。"
            )
        elif moral == "Y" and rel == "α":
            return (
                "代价真相——你找到了全部答案，但手段并不完全光彩。\n\n"
                "顾言走出密室时，表情复杂。「你很厉害。」他停顿了一下，\n"
                "「但翻别人手机、威胁嫌疑人……下次试试更干净的方法。」\n\n"
                "宋知微在笔记本上写下最后一行：「真相水落石出——但侦探的手段值得商榷。」"
            )
        elif rel == "β":
            return (
                "孤胆真相——你独自揭开了全部真相，没有任何人帮你。\n\n"
                "你在公开对峙中摆出所有证据。三个人面面相觑，没有人说话。\n"
                "最后是赵伯打破了沉默：「既然侦探先生都看透了……我去请顾少爷出来吧。」\n\n"
                "顾言走出酒窖时看着你：「你不需要任何人的帮助。这让我佩服，也让我有点……害怕。」"
            )
        else:
            return (
                "真相大白——你揭开了顾言自导自演的全部真相。\n\n"
                "顾言从酒窖密室中走出，向你鼓掌：「了不起。你看穿了一切。」\n"
                "一场精心设计的试探，在你面前无所遁形。"
            )

    # ── Core truth endings ──
    elif truth == "B":
        if "helped_zhoumu" in choices and rel == "α":
            return (
                "不完美但足够——你抓住了真相的核心，而你的善意带来了意外的回报。\n\n"
                "当你在对峙中说出「顾言是自己策划了这场失踪」时，周牧沉默了很久。\n"
                "然后他开口了：「他说得对。而且……我知道为什么。」\n\n"
                "因为你之前的善意，周牧选择补上了你拼图中缺失的那块。\n"
                "真相在两个人的合力下浮出水面。"
            )
        elif rel == "γ":
            return (
                "被围攻的真相——你说对了核心，但没有人愿意站在你这边。\n\n"
                "「顾言是自己失踪的！」你在对峙中大声说出结论。\n"
                f"但{hostile_names[0] if hostile_names else '周牧'}冷笑：「你有证据吗？还是又在诈唬？」\n\n"
                "没有盟友为你佐证，你的推理在三个人的沉默中显得苍白。\n"
                "直到天亮——顾言自己走出来，证实了你的判断。但这个夜晚，没有人觉得你赢了。"
            )
        else:
            return (
                "核心真相——你看穿了最关键的秘密：顾言的失踪是自导自演。\n\n"
                "虽然还有一些细节你没来得及挖掘，但方向完全正确。\n"
                "顾言走出酒窖时，对你微微点头：「你走得比大多数人都远。」"
            )

    # ── Partial truth endings ──
    elif truth == "C":
        if moral == "X" and rel == "α":
            ally = ally_names[0] if ally_names else "林岚"
            return (
                f"留白结局——你走在正确的方向上，{ally}看到了你的正直。\n\n"
                "天亮了，你还差最后一步。但你的调查方式赢得了尊重。\n"
                f"离开老宅时，{ally}悄悄塞给你一张纸条：\n"
                "「答案在酒窖最深处。下次来，我带你去。」\n\n"
                "你没有在这一夜解开全部真相——但你知道，真相不会永远沉默。"
            )
        elif moral == "Z":
            return (
                "反噬——你的激进手段搞砸了一切。\n\n"
                "在你的高压审讯下，局面彻底失控。周牧在崩溃中喊出了半截真相，\n"
                "但更多的证据在混乱中被毁。林岚关上了所有的门。\n\n"
                "「你不是侦探，」宋知微合上笔记本，「你是第四个嫌疑人。」\n"
                "天亮后警察到来，你和其他人一起被带走问话。"
            )
        else:
            return (
                "方向正确——你发现了一些关键线索，但真相的全貌还笼罩在迷雾中。\n\n"
                "你给出了你的判断。不完美，但方向是对的。\n"
                "后续的调查证实了你的部分推理——但完整的真相比你想象的更曲折。"
            )

    # ── Lost endings ──
    else:  # truth == "D"
        if moral == "Z" and rel == "γ":
            return (
                "彻底崩盘——你什么都没查到，还把所有人变成了敌人。\n\n"
                "天亮了。警察到来时，三个嫌疑人异口同声：「我们要投诉这个侦探。」\n"
                "你被请出了顾家大门。第二天新闻上说，顾言自己回了家。\n"
                "「一场误会。」报道上这么写。\n\n"
                "但你知道不是。你只是没有能力——或者没有耐心——去找到答案。"
            )
        elif moral == "X":
            return (
                "正直的失败——你的方法无可指摘，但时间不够了。\n\n"
                "天亮时你还站在走廊里，手里握着几条零散的线索。\n"
                "顾言第二天自己走出了酒窖。他看了看你收集的笔记，叹了口气：\n"
                "「你是个好人。但有时候，好人需要走得更快一些。」"
            )
        else:
            return (
                "迷雾未散——天亮了，真相仍然笼罩在迷雾之中。\n\n"
                "你尽力了，但这个夜晚的秘密太多、太深。\n"
                "离开老宅时，你回头看了一眼。那些窗户后面，到底藏着什么？\n"
                "也许有些真相，需要不止一个夜晚才能揭开。"
            )


class TurnEngine:
    """Sandbox turn engine with DM control."""

    def __init__(self, config: Config):
        self.config = config

        # Layer 0: Sandbox foundation
        self.action_engine = OpenActionEngine(config)
        self.world = WorldStateManager()
        self.npc_autonomy = NPCAutonomyAgent()

        # Layer 1: Expert agents
        self.story_architect = StoryArchitectAgent(config)
        self.tension_conductor = TensionConductor()
        self.psychology = CharacterPsychologyAgent()
        self.conspiracy = ConspiracyAgent()
        self.continuity = ContinuityGuardian()
        self.deduction_validator = DeductionValidator(config)
        self.truth_resolver = TruthResolver()
        self.lie_detector = LieDetector()
        self.npc_interaction = NPCInteractionSystem()
        self.secret_conversations = SecretConversationSystem()
        self.notebook = NotebookSystem()
        self.checkpoint_system = CheckpointSystem()
        self.action_cost_system = ActionCostSystem()
        self.confrontation_system = ConfrontationSystem()

        # Layer 2: DM (final arbiter)
        self.dm = DMAgent(config)

        # Layer 3: Presentation
        self.character_agent = CharacterAgent(config)
        self.image_agent = (
            ImageAgent(config.modelscope_api_key)
            if config.modelscope_api_key
            else None
        )

        # Progress tracking
        self._stuck_turns: Dict[str, int] = {}
        self._last_clue_counts: Dict[str, int] = {}
        self._pacing_state: Dict[str, dict] = {}

        # Undo snapshots: session_id → previous state snapshot
        self._undo_snapshots: Dict[str, dict] = {}

    def init_world(self, session_id: str):
        """Initialize world state and truth resolver for a new session."""
        self.world.create_initial_state(session_id)
        self.truth_resolver.init_session(session_id)

    def _save_undo_snapshot(self, session_id: str):
        """Save a deep snapshot of all per-session state before a turn."""
        import copy
        state = sessions.get(session_id)
        if state is None:
            return
        self._undo_snapshots[session_id] = {
            "game_state": state.model_copy(deep=True),
            "truth_state": copy.deepcopy(self.truth_resolver.get_state(session_id)),
            "world_state": copy.deepcopy(self.world.get_state(session_id)),
            "psych_states": {
                char.id: copy.deepcopy(self.psychology.get_state(session_id, char.id))
                for char in state.characters
            },
            "stuck_turns": self._stuck_turns.get(session_id, 0),
            "last_clue_count": self._last_clue_counts.get(session_id, 0),
            "pacing_state": copy.deepcopy(self._pacing_state.get(session_id)),
            "npc_locations": copy.deepcopy(
                self.npc_autonomy._locations.get(session_id, {})
            ),
            "continuity": copy.deepcopy(
                self.continuity._states.get(session_id)
            ),
            "lie_records": copy.deepcopy(
                self.lie_detector._records.get(session_id, [])
            ),
            "lie_triggered": copy.deepcopy(
                self.lie_detector._triggered.get(session_id, set())
            ),
            "notebook": copy.deepcopy(
                self.notebook._notebooks.get(session_id)
            ),
        }

    def undo_last_turn(self, session_id: str) -> bool:
        """Restore the snapshot saved before the last turn. Returns True on success."""
        import copy
        snap = self._undo_snapshots.pop(session_id, None)
        if snap is None:
            return False

        # Restore GameState
        sessions[session_id] = snap["game_state"]

        # Restore truth resolver
        self.truth_resolver._states[session_id] = snap["truth_state"]

        # Restore world state
        if snap["world_state"] is not None:
            self.world._states[session_id] = snap["world_state"]

        # Restore psychology (keyed by (session_id, char_id) tuple)
        for char_id, ps in snap["psych_states"].items():
            self.psychology._states[(session_id, char_id)] = ps

        # Restore progress tracking
        self._stuck_turns[session_id] = snap["stuck_turns"]
        self._last_clue_counts[session_id] = snap["last_clue_count"]
        if snap["pacing_state"] is not None:
            self._pacing_state[session_id] = snap["pacing_state"]

        # Restore NPC locations
        if snap["npc_locations"]:
            self.npc_autonomy._locations[session_id] = snap["npc_locations"]

        # Restore continuity + lie detector + notebook
        if snap["continuity"] is not None:
            self.continuity._states[session_id] = snap["continuity"]
        self.lie_detector._records[session_id] = snap["lie_records"]
        self.lie_detector._triggered[session_id] = snap["lie_triggered"]
        if snap["notebook"] is not None:
            self.notebook._notebooks[session_id] = snap["notebook"]

        return True

    def has_undo(self, session_id: str) -> bool:
        return session_id in self._undo_snapshots

    def _is_complex_turn(
        self, action_result, breaking_points: dict,
        conspiracy_events: list, betrayal_events: list,
        visible_npc_actions: list, round_num: int, tension: int,
        stuck_turns: int,
    ) -> bool:
        """
        Decide if this turn is complex enough to need LLM for DM/Architect.
        Simple turns use rules-only (0 extra LLM calls).
        Complex turns use LLM (2 extra calls for DM + Architect).

        Complex if ANY of:
        - Breaking point triggered (character crisis)
        - Betrayal event triggered
        - 3+ events competing for the same turn
        - Player did something unusual (action_category not in basic set)
        - Phase transition happening
        - Round is at act boundary (6, 15)
        - Tension is extreme (>75 or <10 after being >30)
        - Player is stuck (3+ turns no progress)
        """
        total_events = (
            len(breaking_points) + len(conspiracy_events)
            + len(betrayal_events) + len(visible_npc_actions)
        )
        is_unusual_action = action_result.action_category in (
            "manipulate", "environmental", "stealth", "communicate"
        )
        at_act_boundary = round_num in (6, 7, 15, 16)

        return (
            bool(breaking_points)
            or bool(betrayal_events)
            or total_events >= 3
            or is_unusual_action
            or at_act_boundary
            or tension > 75
            or stuck_turns >= 3
        )

    def _should_generate_character_replies(
        self, action_result, target_char_id: Optional[str], is_complex: bool
    ) -> bool:
        """Reserve NPC dialogue generation for high-value turns."""
        return (
            is_complex
            or target_char_id is not None
            or action_result.legacy_intent == "accuse"
            or action_result.action_category in (
                "social",
                "manipulate",
                "confront",
                "communicate",
            )
        )

    def _get_pacing_state(self, session_id: str) -> dict:
        if session_id not in self._pacing_state:
            self._pacing_state[session_id] = {
                "act_clue_reveals": {"1": 0, "2": 0, "3": 0},
                "reveal_budgets": {"1": 2, "2": 2, "3": 3},
                "cooldowns": {
                    "betrayal": 0,
                    "major_clue": 0,
                    "twist": 0,
                    "confession": 0,
                },
                "recent_high_intensity_turns": 0,
                "stuck_recovery_level": 0,
                "last_act": 1,
            }
        return self._pacing_state[session_id]

    def _decrement_pacing_cooldowns(self, pacing_state: dict) -> None:
        for key, value in pacing_state["cooldowns"].items():
            if value > 0:
                pacing_state["cooldowns"][key] = value - 1

    def _build_pacing_snapshot(self, session_id: str, act_hint: int) -> dict:
        pacing_state = self._get_pacing_state(session_id)
        act_key = str(act_hint)
        reveal_budget = pacing_state["reveal_budgets"][act_key]
        reveal_count = pacing_state["act_clue_reveals"][act_key]
        return {
            "act_reveal_count": reveal_count,
            "reveal_budget": reveal_budget,
            "reveal_budget_remaining": max(0, reveal_budget - reveal_count),
            "event_cooldowns": dict(pacing_state["cooldowns"]),
            "recent_high_intensity_turns": pacing_state["recent_high_intensity_turns"],
            "stuck_recovery_level": pacing_state["stuck_recovery_level"],
        }

    def _update_pacing_state(
        self,
        session_id: str,
        *,
        act: int,
        new_clue_count: int,
        approved_events: List[str],
        turn_mood: str,
        inject_twist: Optional[str],
        stuck_turns: int,
    ) -> None:
        pacing_state = self._get_pacing_state(session_id)
        act_key = str(act)
        pacing_state["last_act"] = act

        if new_clue_count > 0:
            pacing_state["act_clue_reveals"][act_key] += new_clue_count
            pacing_state["cooldowns"]["major_clue"] = 2

        event_text = "\n".join(approved_events)
        if any(keyword in event_text for keyword in ("隐瞒", "拖下水", "不陪你演戏", "背叛")):
            pacing_state["cooldowns"]["betrayal"] = 2
        if any(keyword in event_text for keyword in ("说出", "承认", "终于", "坦白")):
            pacing_state["cooldowns"]["confession"] = 2
        if inject_twist:
            pacing_state["cooldowns"]["twist"] = 3

        if turn_mood in ("tense", "explosive"):
            pacing_state["recent_high_intensity_turns"] = min(
                3, pacing_state["recent_high_intensity_turns"] + 1
            )
        else:
            pacing_state["recent_high_intensity_turns"] = max(
                0, pacing_state["recent_high_intensity_turns"] - 1
            )

        if stuck_turns >= 3:
            pacing_state["stuck_recovery_level"] = min(
                3, pacing_state["stuck_recovery_level"] + 1
            )
        else:
            pacing_state["stuck_recovery_level"] = max(
                0, pacing_state["stuck_recovery_level"] - 1
            )

    def _apply_clue_fact_disclosures(
        self,
        state: GameState,
        clue_ids: List[str],
        method: str,
    ) -> None:
        for clue_id in clue_ids:
            for fact_id in CLUE_FACT_MAP.get(clue_id, []):
                fact = get_fact_by_id(state, fact_id)
                if fact is None:
                    continue
                record_fact_disclosure(
                    state,
                    fact_id,
                    learned_by=["player"],
                    method=method,
                    round_num=state.round,
                    make_public=fact.scope == "public",
                    source=clue_id,
                )

    def _apply_npc_information_shares(
        self, session_id: str, state: GameState, round_num: int
    ) -> None:
        for share in self.npc_autonomy.consume_pending_shares(session_id):
            source_name = next(
                (char.name for char in state.characters if char.id == share["source"]),
                share["source"],
            )
            target_name = next(
                (char.name for char in state.characters if char.id == share["target"]),
                share["target"],
            )
            record_fact_disclosure(
                state,
                share["fact_id"],
                learned_by=[share["target"]],
                method="npc_share",
                round_num=round_num,
                source=share["source"],
            )
            self.conspiracy.share_information(
                session_id,
                source_character_id=share["source"],
                target_character_id=share["target"],
                info=share["summary"],
            )
            state.events.append(
                Event(
                    round=round_num,
                    type="npc_share",
                    text=f"{source_name}向{target_name}私下传递了信息。",
                )
            )

    def _is_confrontation_command(self, player_action: str) -> bool:
        return player_action.strip() in CONFRONTATION_COMMANDS

    def _extract_vote_choice(self, state: GameState, player_action: str) -> Optional[str]:
        raw = player_action.strip()
        for prefix in ("投票:", "指认:", "投给:", "vote:"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
                break

        vote_state = state.vote_state
        if not vote_state:
            return None

        for option in vote_state.options:
            if raw == option.id or raw == option.label:
                return option.id
        return None

    def _build_turn_response(
        self,
        state: GameState,
        *,
        director_note: str,
        system_narration: str = "",
        new_clues: Optional[List[str]] = None,
        npc_replies: Optional[List[NPCReply]] = None,
        npc_events: Optional[List[NPCEvent]] = None,
        public_statements: Optional[List[PublicStatement]] = None,
        vote_records: Optional[List[VoteRecord]] = None,
        scene_image: Optional[str] = None,
        game_over: Optional[bool] = None,
        ending: Optional[str] = None,
    ) -> TurnResponse:
        return TurnResponse(
            round=state.round,
            phase=state.phase,
            tension=state.tension,
            scene=state.scene,
            director_note=director_note,
            new_clues=new_clues or [],
            npc_replies=npc_replies or [],
            npc_events=npc_events or [],
            public_statements=public_statements or [],
            vote_records=vote_records or [],
            system_narration=system_narration,
            scene_image=scene_image,
            game_over=state.game_over if game_over is None else game_over,
            ending=state.ending if ending is None else ending,
            game_state=redact_game_state(state),
        )

    def _build_public_statement(
        self, char, state: GameState, discovered_count: int
    ) -> PublicStatement:
        if char.id == "linlan":
            if discovered_count >= 3 or state.tension >= 55:
                text = "林岚的声音压得很稳：「如果今晚真有人操控了全局，那个人一定熟悉顾家的每一条动线。」"
            else:
                text = "林岚抬眼扫过众人：「继续各自试探没有意义。把昨晚的时间线摆到桌面上吧。」"
        elif char.id == "zhoumu":
            if char.suspicion >= 60:
                text = "周牧皱着眉拍了拍桌面：「别只盯着我。谁最清楚遗嘱的事，大家心里都明白。」"
            else:
                text = "周牧烦躁地扯了扯领口：「这事八成和遗产脱不了关系，总得有人先把话挑明。」"
        else:
            if discovered_count >= 2:
                text = "宋知微翻开笔记本：「我只看证据。书房、酒窖、遗嘱，这三条线现在已经连到一起了。」"
            else:
                text = "宋知微靠在椅背上，语速很快：「态度先放一边。谁在回避问题，等会儿表决时一眼就能看出来。」"
        return PublicStatement(
            character_id=char.id,
            character_name=char.name,
            text=text,
        )

    def _build_npc_vote(self, char, state: GameState, player_choice_id: str) -> VoteRecord:
        discovered_count = sum(1 for clue in state.clues if clue.discovered)
        if char.id == "linlan":
            if player_choice_id == "guyan_self_staged" and (
                discovered_count >= 4
                or state.tension >= 60
                or char.trust_to_player >= 45
            ):
                target_id = "guyan_self_staged"
                reason = "林岚沉默片刻：「如果有人能让全宅同时失控，那个人只能是顾言自己。」"
            else:
                target_id = "zhoumu"
                reason = "林岚冷冷开口：「昨晚情绪最失控的人，是周牧。」"
        elif char.id == "zhoumu":
            if player_choice_id == "guyan_self_staged" and discovered_count >= 5 and state.tension >= 70:
                target_id = "guyan_self_staged"
                reason = "周牧咬了咬牙：「如果非要说最会玩这一套的人……也许真是顾言自己。」"
            else:
                target_id = "linlan"
                reason = "周牧抬手指向林岚：「她知道得太多了，肯定瞒了我们最关键的一段。」"
        else:
            if discovered_count >= 3 or player_choice_id == "guyan_self_staged":
                target_id = "guyan_self_staged"
                reason = "宋知微把笔记本一合：「从证据链看，这更像一场被精心导演过的失踪。」"
            else:
                target_id = "linlan"
                reason = "宋知微语气平静：「如果先投一个最像知情者的人，我会先投林岚。」"

        target_label = next(
            option.label for option in FINAL_VOTE_OPTIONS if option.id == target_id
        )
        return VoteRecord(
            voter_id=char.id,
            voter_name=char.name,
            target_id=target_id,
            target_label=target_label,
            reason=reason,
        )

    async def _start_confrontation(
        self, state: GameState, player_action: str
    ) -> TurnResponse:
        state.round += 1
        state.phase = "公开对峙"
        state.scene = "宴会厅"
        for char in state.characters:
            char.location = "宴会厅"

        state.tension = _clamp(state.tension + 12)
        discovered_count = sum(1 for clue in state.clues if clue.discovered)
        statements = [
            self._build_public_statement(char, state, discovered_count)
            for char in state.characters
        ]
        state.vote_state = VoteState(
            status="awaiting_player_vote",
            prompt="所有人的话都摆上了桌面。现在，给出你的最终判断。",
            options=[option.model_copy(deep=True) for option in FINAL_VOTE_OPTIONS],
            public_statements=statements,
        )

        state.events.append(Event(round=state.round, type="confrontation", text=f"玩家：{player_action}"))
        for stmt in statements:
            state.events.append(
                Event(
                    round=state.round,
                    type="public_statement",
                    text=f"{stmt.character_name}：{stmt.text}",
                )
            )

        return self._build_turn_response(
            state,
            director_note="长桌边的每个人都被迫亮明了态度。",
            system_narration="你要求所有人回到宴会厅公开对峙。灯光压低了，空气像绷紧的琴弦，所有目光都集中到你身上。",
            public_statements=statements,
        )

    async def _resolve_final_vote(
        self, state: GameState, player_choice_id: str
    ) -> TurnResponse:
        state.round += 1
        state.phase = "投票表决"
        state.tension = _clamp(state.tension + 15)

        vote_state = state.vote_state or VoteState(options=[option.model_copy(deep=True) for option in FINAL_VOTE_OPTIONS])
        option_map = {option.id: option for option in vote_state.options}
        player_option = option_map[player_choice_id]

        votes: List[VoteRecord] = [
            VoteRecord(
                voter_id="player",
                voter_name="你",
                target_id=player_option.id,
                target_label=player_option.label,
                reason=f"你最终把票投给了「{player_option.label}」。",
            )
        ]
        votes.extend(
            self._build_npc_vote(char, state, player_choice_id)
            for char in state.characters
        )

        tally: Dict[str, int] = {}
        for vote in votes:
            tally[vote.target_id] = tally.get(vote.target_id, 0) + 1

        player_priority = {option.id: idx for idx, option in enumerate(vote_state.options)}
        winning_option_id = max(
            tally,
            key=lambda option_id: (
                tally[option_id],
                1 if option_id == player_choice_id else 0,
                -player_priority.get(option_id, 999),
            ),
        )
        winning_option = option_map[winning_option_id]

        try:
            deduction = await self.deduction_validator.validate(
                player_accusation=FINAL_VOTE_THEORIES[winning_option_id],
                discovered_clues=[clue.text for clue in state.clues if clue.discovered],
                player_known_facts=state.knowledge.player_known,
            )
            ending = deduction.response_text
            outcome = deduction.ending_type
        except Exception:
            outcome = "good" if winning_option_id == "guyan_self_staged" else "wrong"
            if winning_option_id == "guyan_self_staged":
                ending = (
                    "真相被强行撕开——公开表决最终指向了顾言本人。"
                    "当所有人的目光转向酒窖方向时，顾言终于现身，承认这一切都是他的试探。"
                )
            else:
                ending = (
                    "表决落下帷幕，但空气中没有任何如释重负。"
                    "你们把票投向了错误的方向，而真正的操盘者仍在暗处看着这一切。"
                )

        max_votes = tally[winning_option_id]
        tally_text = "，".join(
            f"{option_map[option_id].label}{count}票"
            for option_id, count in sorted(
                tally.items(),
                key=lambda item: (-item[1], player_priority.get(item[0], 999)),
            )
        )

        if winning_option_id == player_choice_id:
            ending += f"\n\n公开表决结果收束到「{winning_option.label}」：{tally_text}。"
        else:
            ending += (
                f"\n\n你把票投给了「{player_option.label}」，"
                f"但公开表决最终指向了「{winning_option.label}」：{tally_text}。"
            )

        vote_state.status = "resolved"
        vote_state.player_choice_id = player_choice_id
        vote_state.votes = votes
        vote_state.tally = tally
        vote_state.winning_option_id = winning_option_id
        vote_state.winning_option_label = winning_option.label
        vote_state.outcome = outcome
        state.vote_state = vote_state

        state.game_over = True
        state.ending = ending
        state.events.append(Event(round=state.round, type="vote", text=f"公开表决结果：{winning_option.label}（{max_votes}票）"))
        for vote in votes:
            state.events.append(
                Event(
                    round=state.round,
                    type="vote_record",
                    text=f"{vote.voter_name}投给了{vote.target_label}：{vote.reason}",
                )
            )

        return self._build_turn_response(
            state,
            director_note=f"表决结果落在「{winning_option.label}」上，谁都无法再退回沉默。",
            system_narration="你做出最后的指认，其他人也被迫在长桌前公开站队。票数一张张摊开，今夜终于被推向结局。",
            vote_records=votes,
            game_over=True,
            ending=ending,
        )

    async def process_turn(
        self, session_id: str, player_action: str
    ) -> TurnResponse:
        """
        Pipeline:
         1.  Get states
         2.  Check game over
         3.  NPC Autonomy (NPCs act independently)
         4.  Open Action Engine (understand any player action)
         5.  Expert agents gather proposals (architect, tension, psychology, conspiracy)
         6.  DM Agent adjudicates (single coherent decision)
         7.  Character Agents + Image (presentation, parallel)
         8.  Apply world changes + update game state
         9.  Continuity tracking
        10.  End condition check
        11.  Return
        """
        # ── 1. Get states ──
        state = sessions.get(session_id)
        if state is None:
            raise ValueError(f"Session '{session_id}' not found.")

        ws = self.world.get_state(session_id)
        if ws is None:
            self.init_world(session_id)
            ws = self.world.get_state(session_id)

        # ── 2. Game over ──
        if state.game_over:
            return TurnResponse(
                round=state.round, phase=state.phase, tension=state.tension,
                scene=state.scene,
                director_note="游戏已经结束。" + (state.ending or ""),
                game_over=True, ending=state.ending,
                game_state=redact_game_state(state),
            )

        if self._is_confrontation_command(player_action):
            if state.vote_state and state.vote_state.status == "awaiting_player_vote":
                return self._build_turn_response(
                    state,
                    director_note="所有人都已经把话挑明了，现在只差你投出最后一票。",
                    system_narration="宴会厅里没有人再试图回避你的目光。请选择一个最终判断。",
                )
            return await self._start_confrontation(state, player_action)

        if state.vote_state and state.vote_state.status == "awaiting_player_vote":
            vote_choice = self._extract_vote_choice(state, player_action)
            if vote_choice is not None:
                return await self._resolve_final_vote(state, vote_choice)
            return self._build_turn_response(
                state,
                director_note="公开对峙已经开始，不要再绕圈子了。",
                system_narration="三个人都在等你给出最后判断。直接选择一个投票对象。",
            )

        pacing_state = self._get_pacing_state(session_id)
        self._decrement_pacing_cooldowns(pacing_state)
        act_hint = 1 if state.round + 1 <= 6 else 2 if state.round + 1 <= 15 else 3
        pacing_snapshot = self._build_pacing_snapshot(session_id, act_hint)

        # ── 3. NPC Autonomy ──
        discovered_clue_ids = [c.id for c in state.clues if c.discovered]
        psych_states_for_npc = {}
        for char in state.characters:
            ps = self.psychology.get_state(session_id, char.id)
            psych_states_for_npc[char.id] = {
                "desperation": ps.desperation,
                "fear": ps.fear,
                "composure": ps.composure,
            }

        npc_actions = self.npc_autonomy.simulate_npc_turns(
            session_id=session_id,
            player_location=state.scene,
            round_num=state.round + 1,
            tension=state.tension,
            discovered_clues=discovered_clue_ids,
            psych_states=psych_states_for_npc,
        )

        for npc_act in npc_actions:
            if npc_act.moved:
                for char in state.characters:
                    if char.id == npc_act.character_id:
                        char.location = npc_act.location
                        break

        visible_npc_actions = self.npc_autonomy.get_visible_actions(
            session_id, state.scene
        )
        hidden_npc_actions = [
            a for a in npc_actions if not a.visible_to_player
        ]
        self._apply_npc_information_shares(session_id, state, state.round + 1)

        # ── 3b. Secret conversations — NPCs scheme behind player's back ──
        npc_locs = {c.id: c.location for c in state.characters}
        discovered_clue_texts = [c.text for c in state.clues if c.discovered]
        secret_conv = self.secret_conversations.simulate(
            session_id, state.scene, npc_locs, state.tension, state.round + 1,
            config=self.config,
            character_states=psych_states_for_npc,
            discovered_clue_texts=discovered_clue_texts,
        )
        # If pre-written scripts are exhausted, try LLM-powered dynamic generation
        if secret_conv is None and self.config.provider != LLMProvider.FALLBACK:
            secret_conv = await self.secret_conversations.simulate_dynamic(
                session_id, state.scene, npc_locs, state.tension, state.round + 1,
                config=self.config,
                character_states=psych_states_for_npc,
                discovered_clue_texts=discovered_clue_texts,
            )
        if secret_conv:
            # Apply psychological effects (player doesn't see these directly)
            for char_id, effects in secret_conv.psych_effects.items():
                ps = self.psychology.get_state(session_id, char_id)
                for attr, delta in effects.items():
                    current = getattr(ps, attr, 0.0)
                    setattr(ps, attr, max(0.0, min(1.0, current + delta)))

        # ── 4. Open Action Engine ──
        world_summary = self.world.get_state_summary(session_id, state.scene)
        player_inv = ", ".join(ws.player_inventory) if ws.player_inventory else "无"

        chars_ctx_parts = []
        for c in state.characters:
            if c.location == state.scene:
                chars_ctx_parts.append(
                    f"- {c.name}({c.public_role}): 信任={c.trust_to_player}, 嫌疑={c.suspicion}"
                )
            else:
                chars_ctx_parts.append(f"- {c.name}: 不在此处(在{c.location})")
        characters_context = "\n".join(chars_ctx_parts) or "无人在场"

        full_world_context = (
            f"【当前位置】{state.scene}\n"
            f"【时间】{ws.time} ({ws.time_period})\n"
            f"【天气】{ws.weather}\n"
            f"【玩家物品】{player_inv}\n"
            f"【紧张度】{state.tension}/100\n"
            f"【阶段】{state.phase}\n\n"
            f"【场景描述】\n{world_summary}\n\n"
            f"【在场人物】\n{characters_context}"
        )

        recent_history = [e.text for e in state.events[-6:]] if state.events else []

        action_result = await self.action_engine.simulate(
            player_action=player_action,
            world_context=full_world_context,
            characters_context=characters_context,
            recent_history=recent_history,
        )
        action_result.narration = _sanitize_narration(action_result.narration)

        # Handle movement — works for pure moves AND compound actions
        # ("回到宴会厅骗周牧" = move + manipulate)
        def _try_move() -> bool:
            """Try to detect and apply movement from action text or result."""
            # Check targets first
            for target in action_result.targets:
                for avail in state.available_scenes:
                    if avail in target or target in avail or target == avail:
                        state.scene = avail
                        return True
            # Check player action text for location keywords
            for avail in state.available_scenes:
                if avail in player_action:
                    # Confirm it's a movement intent (去/回/前往/到)
                    move_keywords = ["去", "回", "前往", "到", "走到", "来到", "进入", "回到"]
                    if any(kw in player_action and avail in player_action for kw in move_keywords):
                        state.scene = avail
                        return True
            # Check narration as last resort
            if action_result.narration:
                for avail in state.available_scenes:
                    if f"来到了{avail}" in action_result.narration or f"到达{avail}" in action_result.narration:
                        state.scene = avail
                        return True
            return False

        if action_result.action_category == "move" and action_result.feasible:
            _try_move()
        elif action_result.feasible:
            # Compound action: player might have moved AND done something else
            # e.g., "回到宴会厅质问林岚" → category=confront, but includes movement
            _try_move()

        legacy_intent = action_result.legacy_intent

        # ── 4b. Clue discovery bridge ──
        # The Open Action Engine doesn't know about the clue system,
        # so we run clue discovery here based on the player's location + action type.
        current_location = _get_current_scene_short(state.scene, state.available_scenes)
        engine_clues = _discover_clues_for_action(
            state, action_result.action_category, legacy_intent, state.scene
        )
        # Merge with any clues the LLM might have found (unlikely but possible)
        all_discovered = list(set(action_result.discovered_clues + engine_clues))
        action_result.discovered_clues = all_discovered

        # ── 5. Expert agents gather proposals ──
        discovered_count = sum(1 for c in state.clues if c.discovered)

        # Tension conductor
        tension_adj = self.tension_conductor.conduct(
            session_id=session_id,
            round_num=state.round + 1,
            max_rounds=state.max_rounds,
            current_tension=state.tension,
            raw_delta=action_result.tension_delta,
            discovered_clues_count=discovered_count,
            phase=state.phase,
        )

        # Story pacing state
        prev_clue_count = self._last_clue_counts.get(session_id, 0)
        if discovered_count == prev_clue_count:
            self._stuck_turns[session_id] = self._stuck_turns.get(session_id, 0) + 1
        else:
            self._stuck_turns[session_id] = 0
        self._last_clue_counts[session_id] = discovered_count

        # Character psychology
        target_char_id = None
        for t in action_result.targets:
            if t in [c.id for c in state.characters]:
                target_char_id = t
                break

        for char in state.characters:
            self.psychology.update_after_turn(
                session_id=session_id,
                character_id=char.id,
                intent_type=legacy_intent,
                rule_result={
                    "success": action_result.success_level,
                    "tension_delta": action_result.tension_delta,
                    "trust_changes": action_result.trust_changes,
                    "suspicion_changes": action_result.suspicion_changes,
                    "discovered_clues": action_result.discovered_clues,
                    "target_character": target_char_id,
                },
                player_action=player_action,
                tension=state.tension,
            )

        # Collect breaking points
        breaking_points: Dict[str, str] = {}
        for char in state.characters:
            bp = self.psychology.check_breaking_point(session_id, char.id)
            if bp:
                breaking_points[char.id] = bp

        # Collect psych directives
        psych_directives: Dict[str, dict] = {}
        for char in state.characters:
            psych_directives[char.id] = self.psychology.get_behavior_directive(
                session_id, char.id
            )

        # Conspiracy
        psych_snapshots = []
        for char in state.characters:
            ps = self.psychology.get_state(session_id, char.id)
            psych_snapshots.append(ConspiracyPsychState(
                character_id=char.id,
                suspicion=char.suspicion,
                trust_to_player=char.trust_to_player,
                desperation=ps.desperation,
            ))

        self.conspiracy.update_alliances(
            session_id=session_id,
            characters_psych_states=psych_snapshots,
            player_target=target_char_id,
            discovered_clues=discovered_clue_ids,
            tension=state.tension,
        )

        conspiracy_events = self.conspiracy.get_npc_events(
            session_id, state.tension, state.phase, state.round + 1
        )

        betrayal_events = []
        for char in state.characters:
            betrayal = self.conspiracy.should_trigger_betrayal(
                session_id, char.id, state.tension
            )
            if betrayal:
                betrayal_events.append(betrayal)

        # ── 6. DM Agent: the final arbiter ──
        # Smart routing: only use LLM for complex turns
        is_complex = self._is_complex_turn(
            action_result, breaking_points, conspiracy_events,
            betrayal_events, [a for a in visible_npc_actions],
            state.round + 1, state.tension, self._stuck_turns.get(session_id, 0),
        )

        # For simple turns, force DM and Architect to use rules-only (0 LLM tokens)
        provider_overridden = False
        original_dm_provider = None
        original_arch_provider = None
        if not is_complex:
            original_dm_provider = self.dm.config.provider
            original_arch_provider = self.story_architect.config.provider
            self.dm.config.provider = LLMProvider.FALLBACK
            self.story_architect.config.provider = LLMProvider.FALLBACK
            provider_overridden = True

        try:
            architect_directive = await self.story_architect.generate_directive({
                "session_id": session_id,
                "round": state.round + 1,
                "max_rounds": state.max_rounds,
                "tension": state.tension,
                "phase": state.phase,
                "discovered_clue_count": discovered_count,
                "total_clues": len(state.clues),
                "player_progress": discovered_count / max(len(state.clues), 1),
                "player_type": "exploration",
                "stuck_turns": self._stuck_turns.get(session_id, 0),
                **pacing_snapshot,
            })

            proposals = AgentProposals(
                # Action engine
                action_narration=action_result.narration,
                action_category=action_result.action_category,
                action_feasible=action_result.feasible,
                action_tension_delta=action_result.tension_delta,
                # Story architect
                current_act=architect_directive.current_act,
                current_beat=architect_directive.current_beat,
                pacing=architect_directive.pacing,
                architect_director_note=architect_directive.director_note,
                architect_narration=architect_directive.system_narration,
                architect_events=architect_directive.suggested_events,
                hint_level=architect_directive.hint_level,
                # Tension conductor
                tension_adjusted_delta=tension_adj.adjusted_delta,
                tension_atmosphere=tension_adj.atmosphere,
                # NPC autonomy
                visible_npc_actions=[a.action for a in visible_npc_actions],
                hidden_npc_actions=[a.action for a in hidden_npc_actions],
                npc_evidence=[
                    e for a in npc_actions if a.evidence_left for e in [a.evidence_left]
                ],
                # Psychology
                breaking_points=breaking_points,
                psych_directives=psych_directives,
                # Conspiracy
                conspiracy_events=conspiracy_events,
                betrayal_events=betrayal_events,
                # Context
                round_num=state.round + 1,
                max_rounds=state.max_rounds,
                tension=state.tension,
                phase=state.phase,
                discovered_clues=discovered_count,
                total_clues=len(state.clues),
                player_action=player_action,
                stuck_turns=self._stuck_turns.get(session_id, 0),
                act_reveal_count=pacing_snapshot["act_reveal_count"],
                reveal_budget=pacing_snapshot["reveal_budget"],
                reveal_budget_remaining=pacing_snapshot["reveal_budget_remaining"],
                event_cooldowns=pacing_snapshot["event_cooldowns"],
                recent_high_intensity_turns=pacing_snapshot["recent_high_intensity_turns"],
                stuck_recovery_level=pacing_snapshot["stuck_recovery_level"],
            )

            dm_directive = await self.dm.adjudicate(proposals, session_id=session_id)
        finally:
            if provider_overridden:
                self.dm.config.provider = original_dm_provider
                self.story_architect.config.provider = original_arch_provider

        # ── 7. Character Agents + Image Agent (parallel) ──
        current_scene_short = _get_current_scene_short(state.scene, state.available_scenes)
        relevant_characters = []
        should_generate_replies = self._should_generate_character_replies(
            action_result, target_char_id, is_complex
        )
        if should_generate_replies:
            for char in state.characters:
                is_targeted = char.id == target_char_id
                is_present = char.location == current_scene_short
                is_accuse = legacy_intent == "accuse"
                if is_targeted or (is_present and action_result.action_category != "move") or is_accuse:
                    relevant_characters.append(char)

        # Force a specific NPC to react if DM says so
        if should_generate_replies and dm_directive.force_npc_reaction:
            forced = next(
                (c for c in state.characters if c.id == dm_directive.force_npc_reaction),
                None,
            )
            if forced and forced not in relevant_characters:
                relevant_characters.append(forced)

        char_extra_contexts: Dict[str, str] = {}
        for char in relevant_characters:
            parts = []
            d = psych_directives.get(char.id, {})
            if d:
                parts.append(
                    f"【当前心理状态】\n"
                    f"- 镇定程度：{d.get('composure_level', 'high')}\n"
                    f"- 行为指导：{d.get('manner', '')}\n"
                    f"- 防御策略：{d.get('strategy', 'deflect')}"
                )
            conspiracy_ctx = self.conspiracy.get_character_conspiracy_context(
                session_id, char.id
            )
            if conspiracy_ctx:
                parts.append(f"【与其他角色的关系动态】\n{conspiracy_ctx}")
            continuity_ctx = self.continuity.build_continuity_prompt(
                session_id, char.id
            )
            if continuity_ctx:
                parts.append(continuity_ctx)

            # Secret conversation behavioral tell — NPC acts differently
            tell_ctx = self.secret_conversations.get_tell_context_for_prompt(
                session_id, char.id
            )
            if tell_ctx:
                parts.append(tell_ctx)

            # Memory context — smart layered memory (key statements never forgotten)
            smart_mem = self.continuity.get_smart_memory(
                session_id, char.id, player_action
            )
            if smart_mem:
                parts.append(smart_mem)
            if char.id in action_result.npc_reactions:
                parts.append(f"【对玩家行为的反应提示】\n{action_result.npc_reactions[char.id]}")
            # DM mood instruction
            parts.append(f"【本轮氛围】{dm_directive.turn_mood}")
            char_extra_contexts[char.id] = "\n\n".join(parts)

        async def get_char_response(char):
            extra = char_extra_contexts.get(char.id, "")
            try:
                intent_enum = IntentType(legacy_intent)
            except ValueError:
                intent_enum = IntentType.other
            text = await self.character_agent.generate_response(
                character=char, state=state, player_action=player_action,
                intent=intent_enum,
                rule_result={"success": action_result.success_level,
                             "narration": action_result.narration,
                             "discovered_clues": action_result.discovered_clues},
                extra_context=extra,
                scoped_facts=get_character_scoped_facts(state, char.id),
                hard_boundaries=char.hard_boundaries,
            )
            text = _sanitize_narration(text)
            voice, speed = _character_voice(char.id, self.psychology.get_state(session_id, char.id))
            return NPCReply(
                character_id=char.id, character_name=char.name, text=text,
                voice=voice, speed=speed,
            )

        # Image generation runs in background — never blocks the turn response.
        # The image URL is cached, so next turn at same scene will have it ready.
        should_generate_image = self.image_agent is not None and (
            action_result.action_category == "move"
            or action_result.discovered_clues
            or action_result.world_changes
        )

        if should_generate_image and self.image_agent:
            # Fire and forget — don't await, just cache when ready
            asyncio.create_task(self.image_agent.generate_scene_image(
                scene=state.scene, narration=action_result.narration,
                tension=state.tension, phase=state.phase,
            ))

        # Only character responses block the turn (they're the core content)
        tasks = [get_char_response(c) for c in relevant_characters]

        npc_replies: List[NPCReply] = []
        scene_image = None
        if tasks:
            results = await asyncio.gather(*tasks)
            npc_replies = list(results)

        # ── 8. Apply world changes + update state ──
        if action_result.world_changes:
            self.world.apply_changes(session_id, action_result.world_changes)
        for npc_act in npc_actions:
            if npc_act.world_changes:
                self.world.apply_changes(session_id, npc_act.world_changes)
        self.world.advance_time(session_id)

        state.round += 1

        # Tension: DM has final say
        state.tension = _clamp(state.tension + dm_directive.final_tension_delta)

        for char in state.characters:
            if char.id in action_result.trust_changes:
                char.trust_to_player = _clamp(
                    char.trust_to_player + action_result.trust_changes[char.id]
                )
            if char.id in action_result.suspicion_changes:
                char.suspicion = _clamp(
                    char.suspicion + action_result.suspicion_changes[char.id]
                )

        # ── Behavior tagging for ending system ──
        _record_behavior_tags(state, action_result, player_action, target_char_id)

        # Clue discovery (DM can suppress for pacing)
        new_clue_texts = []
        new_clue_ids: List[str] = []
        if dm_directive.allow_clue_discovery:
            for clue_id in action_result.discovered_clues:
                for clue in state.clues:
                    if clue.id == clue_id and not clue.discovered:
                        clue.discovered = True
                        clue.holder = "player"
                        new_clue_texts.append(clue.text)
                        new_clue_ids.append(clue.id)
                        if clue.text not in state.knowledge.player_known:
                            state.knowledge.player_known.append(clue.text)
        if new_clue_ids:
            self._apply_clue_fact_disclosures(
                state, new_clue_ids, method="clue_discovered"
            )

        # ── Truth Resolver: update weights based on player behavior ──
        self.truth_resolver.update_weights(
            session_id, player_action, target_char_id,
            [c.id for c in state.clues if c.discovered],
        )
        self.truth_resolver.try_lock(session_id, state.round)

        # ── Lie Detector: check if new clues expose NPC lies ──
        caught_lies = []
        if new_clue_ids:
            caught_lies = self.lie_detector.check_for_contradictions(
                session_id, new_clue_ids
            )

        # Phase
        if legacy_intent == "accuse":
            state.phase = "公开对峙"
        elif architect_directive.current_beat == "crisis" and state.phase not in ("高压对峙", "公开对峙"):
            state.phase = "高压对峙"
        elif architect_directive.current_beat == "climax" and state.phase != "终局逼近":
            state.phase = "终局逼近"
        elif state.tension >= 70 and state.phase == "自由试探":
            state.phase = "高压对峙"
        elif discovered_count >= 3 and state.phase == "自由试探":
            state.phase = "深入调查"

        state.events.append(
            Event(round=state.round, type=legacy_intent, text=f"玩家：{player_action}")
        )

        # ── 9. Continuity + Lie tracking ──
        for reply in npc_replies:
            self.continuity.record_statement(
                session_id=session_id, round=state.round,
                character_id=reply.character_id, text=reply.text,
            )
            self.lie_detector.record_npc_response(
                session_id, state.round,
                reply.character_id, reply.character_name, reply.text,
            )

        # Events: DM-approved + caught lies (highest priority)
        npc_events = []

        # NPC-to-NPC confrontation — two characters argue in front of the player
        current_scene_short = _get_current_scene_short(state.scene, state.available_scenes)
        present_char_ids = [c.id for c in state.characters if c.location == current_scene_short]
        discovered_texts = [c.text for c in state.clues if c.discovered]

        confrontation = self.npc_interaction.get_confrontation(
            session_id, present_char_ids, state.tension, state.round, discovered_texts,
        )
        for line in confrontation:
            npc_replies.append(NPCReply(
                character_id=line.character_id,
                character_name=line.character_name,
                text=line.text,
            ))

        # Proactive NPC speech — NPC speaks up without being asked
        proactive = self.npc_interaction.get_proactive_lines(
            session_id, present_char_ids, state.tension, state.round,
            [c.id for c in state.clues if c.discovered],
        )
        for line in proactive:
            npc_events.append(NPCEvent(text=line.text))
            state.events.append(Event(round=state.round, type="proactive", text=line.text))

        # Caught lies get inserted — dramatic moments
        for lie in caught_lies:
            npc_events.append(NPCEvent(text=lie.confrontation_text))
            state.events.append(Event(
                round=state.round, type="lie_caught",
                text=f"[揭穿谎言] {lie.character_name}: {lie.confrontation_text[:100]}",
            ))

        for evt_text in dm_directive.approved_events:
            # Filter out non-Chinese text (LLM sometimes outputs English IDs or code)
            if not evt_text or not any('\u4e00' <= c <= '\u9fff' for c in evt_text):
                continue
            evt_text = _sanitize_narration(evt_text)
            npc_events.append(NPCEvent(text=evt_text))
            state.events.append(Event(round=state.round, type="npc_event", text=evt_text))

        self.dm.record_used_events(session_id, dm_directive.approved_events)

        # DM twist injection
        if dm_directive.inject_twist:
            dm_directive.inject_twist = _sanitize_narration(dm_directive.inject_twist)
            npc_events.append(NPCEvent(text=dm_directive.inject_twist))
            state.events.append(
                Event(round=state.round, type="twist", text=dm_directive.inject_twist)
            )

        # Evidence from NPC actions
        location_evidence = self.npc_autonomy.get_evidence_at_location(
            session_id, state.scene
        )
        for evidence in location_evidence:
            npc_events.append(NPCEvent(text=f"你注意到：{evidence}"))

        # Evidence from secret conversations (NPCs scheming behind your back)
        secret_evidence = self.secret_conversations.get_evidence_at_location(
            session_id, state.scene
        )
        for evidence in secret_evidence:
            npc_events.append(NPCEvent(text=f"你注意到一些异常：{evidence}"))
            state.events.append(Event(
                round=state.round, type="secret_evidence", text=evidence,
            ))

        # ── 10. End conditions ──
        game_over = False
        ending = None

        if state.round >= state.max_rounds:
            game_over = True
        elif state.tension >= 100:
            game_over = True
        else:
            cellar_sound = next(
                (c for c in state.clues if c.id == "cellar_sound"), None
            )
            if (
                cellar_sound and cellar_sound.discovered
                and legacy_intent in ("search", "other")
                and state.scene == "酒窖"
                and state.tension >= 80
            ):
                game_over = True

            if legacy_intent == "accuse" and player_action:
                try:
                    deduction = await self.deduction_validator.validate(
                        player_accusation=player_action,
                        discovered_clues=[c.text for c in state.clues if c.discovered],
                        player_known_facts=state.knowledge.player_known,
                    )
                    if deduction.ending_type in ("perfect", "good"):
                        game_over = True
                except Exception:
                    action_lower = player_action.lower()
                    truth_kw = ["自导自演", "自己策划", "假装失踪", "酒窖密室", "试探"]
                    if sum(1 for kw in truth_kw if kw in action_lower) >= 2:
                        game_over = True

        if game_over:
            state.game_over = True
            # Use behavior-chain ending system
            truth_level = _calc_truth_level(state)
            moral_stance = _calc_moral_stance(state)
            relationship = _calc_relationship(state)
            ending = _resolve_ending(truth_level, moral_stance, relationship, state)
            # Calculate detective score
            score = calculate_score(
                clues_found=sum(1 for c in state.clues if c.discovered),
                total_clues=len(state.clues),
                truth_accuracy={"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.15}.get(truth_level, 0.4),
                rounds_used=state.round,
                max_rounds=state.max_rounds,
                lies_caught=len(caught_lies),
                confrontations_won=len(caught_lies),
                game_over_reason="deduction" if legacy_intent == "accuse" else "timeout" if state.round >= state.max_rounds else "chaos",
            )
            score_text = (
                f"\n\n{'─'*30}\n"
                f"结局维度: 真相={truth_level} 立场={moral_stance} 关系={relationship}\n"
                f"侦探评分: {score.total_score}/100 — {score.rank}级 ({score.rank_title})\n"
                f"  线索收集: {score.clue_score}/40\n"
                f"  推理质量: {score.deduction_score}/30\n"
                f"  调查效率: {score.efficiency_score}/15\n"
                f"  审讯互动: {score.interaction_score}/15\n"
                f"{'─'*30}\n"
                f"{score.summary}"
            )
            ending = (ending or "") + score_text
            state.ending = ending

        self._update_pacing_state(
            session_id,
            act=architect_directive.current_act,
            new_clue_count=len(new_clue_ids),
            approved_events=dm_directive.approved_events,
            turn_mood=dm_directive.turn_mood,
            inject_twist=dm_directive.inject_twist,
            stuck_turns=self._stuck_turns.get(session_id, 0),
        )

        # ── 10b. Map psychology → mood label ──
        for char in state.characters:
            ps = self.psychology.get_state(session_id, char.id)
            char.mood = _compute_mood(ps)

        # ── 11. Return (DM-controlled narration) ──
        director_note = dm_directive.director_note
        if dm_directive.hint_text:
            director_note = dm_directive.hint_text

        return TurnResponse(
            round=state.round,
            phase=state.phase,
            tension=state.tension,
            scene=state.scene,
            director_note=director_note,
            new_clues=new_clue_texts,
            npc_replies=npc_replies,
            npc_events=npc_events,
            system_narration=_sanitize_narration(dm_directive.system_narration),
            narrator_voice=CHARACTER_VOICES.get("narrator", "luodo"),
            scene_image=scene_image,
            game_over=game_over,
            ending=ending,
            game_state=redact_game_state(state),
        )

    # ═══════════════════════════════════════════════════════════════════
    # Streaming turn — yields SSE events as they become available
    # ═══════════════════════════════════════════════════════════════════

    async def process_turn_streaming(self, session_id: str, player_action: str):
        """
        Async generator that yields dict events progressively.

        Phase 0 (0ms):   sync computations + fallback narration
        Phase 1 (~1-2s): OAE + Architect in parallel → narration_update
        Phase 2 (~2-4s): DM adjudication → director_note + events
        Phase 3 (~3-6s): Character agents via as_completed → NPC replies
        Final:           state changes, clues, ending
        """
        # ── 1. Get states ──
        state = sessions.get(session_id)
        if state is None:
            yield {"type": "error", "text": f"Session '{session_id}' not found."}
            return

        ws = self.world.get_state(session_id)
        if ws is None:
            self.init_world(session_id)
            ws = self.world.get_state(session_id)

        # ── Save undo snapshot before any state mutation ──
        if not state.game_over:
            self._save_undo_snapshot(session_id)

        # ── 2. Game over ──
        if state.game_over:
            yield {"type": "narration", "text": "游戏已经结束。" + (state.ending or "")}
            yield {"type": "state", "round": state.round, "phase": state.phase,
                   "tension": state.tension, "scene": state.scene,
                   "game_over": True, "game_state": redact_game_state(state)}
            yield {"type": "done"}
            return

        # ── Edge cases: confrontation / voting → fall back to process_turn ──
        if self._is_confrontation_command(player_action):
            result = await self.process_turn(session_id, player_action)
            for evt in self._turn_response_to_events(result):
                yield evt
            return

        if state.vote_state and state.vote_state.status == "awaiting_player_vote":
            result = await self.process_turn(session_id, player_action)
            for evt in self._turn_response_to_events(result):
                yield evt
            return

        # ── Resolve pending checkpoint ──
        if (
            state.checkpoint_state
            and state.checkpoint_state.status == "awaiting_hypothesis"
        ):
            choice_id = player_action.strip()
            # Match by option id or label
            matched_id = None
            for opt in state.checkpoint_state.options:
                if choice_id == opt.id or choice_id == opt.label:
                    matched_id = opt.id
                    break
            if not matched_id and state.checkpoint_state.options:
                # Try numeric index (1-based)
                try:
                    idx = int(choice_id) - 1
                    if 0 <= idx < len(state.checkpoint_state.options):
                        matched_id = state.checkpoint_state.options[idx].id
                except ValueError:
                    pass
            if not matched_id:
                matched_id = state.checkpoint_state.options[0].id if state.checkpoint_state.options else "unsure"

            feedback, weight_adj = self.checkpoint_system.resolve(
                state.checkpoint_state, matched_id
            )
            # Apply weight adjustments to truth resolver
            tr_state = self.truth_resolver.get_state(session_id)
            for truth_id, delta in weight_adj.items():
                tr_state.truth_weights[truth_id] = tr_state.truth_weights.get(truth_id, 1.0) + delta

            state.checkpoint_state.status = "resolved"
            state.checkpoint_state.player_choice_id = matched_id
            state.checkpoint_state.feedback = feedback
            state.checkpoints_completed.append(state.checkpoint_state.checkpoint_round)

            yield {"type": "checkpoint_feedback", "text": feedback, "choice_id": matched_id}
            state.checkpoint_state = None  # Clear after resolving
            yield {"type": "state", "round": state.round, "phase": state.phase,
                   "tension": state.tension, "scene": state.scene,
                   "game_over": False, "game_state": redact_game_state(state)}
            yield {"type": "done"}
            return

        # ── Resolve pending confrontation ──
        if (
            state.confrontation_state
            and state.confrontation_state.status == "awaiting_player_choice"
        ):
            choice_id = player_action.strip()
            matched_id = None
            for opt in state.confrontation_state.options:
                if choice_id == opt.id or choice_id == opt.label:
                    matched_id = opt.id
                    break
            if not matched_id and state.confrontation_state.options:
                try:
                    idx = int(choice_id) - 1
                    if 0 <= idx < len(state.confrontation_state.options):
                        matched_id = state.confrontation_state.options[idx].id
                except ValueError:
                    pass
            if not matched_id:
                matched_id = state.confrontation_state.options[0].id if state.confrontation_state.options else None

            if matched_id:
                outcome = self.confrontation_system.resolve(
                    session_id, state.confrontation_state, matched_id
                )
                if outcome:
                    # Apply effects
                    target_id = state.confrontation_state.target_character_id
                    for char in state.characters:
                        if char.id == target_id:
                            char.trust_to_player = _clamp(char.trust_to_player + outcome.trust_change)
                            char.suspicion = _clamp(char.suspicion + outcome.suspicion_change)
                            break
                    state.tension = _clamp(state.tension + outcome.tension_change)

                    state.confrontation_state.status = "resolved"
                    state.confrontation_state.player_choice_id = matched_id
                    state.confrontation_state.outcome = outcome.outcome_type
                    state.confrontation_state.result_text = outcome.result_text

                    yield {
                        "type": "confrontation_result",
                        "text": outcome.result_text,
                        "outcome": outcome.outcome_type,
                        "character": state.confrontation_state.target_character_name,
                        "character_id": target_id,
                    }

                    # Reveal clue if outcome grants one
                    if outcome.reveals_clue:
                        for clue in state.clues:
                            if clue.id == outcome.reveals_clue and not clue.discovered:
                                clue.discovered = True
                                clue.holder = "player"
                                if clue.text not in state.knowledge.player_known:
                                    state.knowledge.player_known.append(clue.text)
                                yield {"type": "clue", "text": clue.text, "id": clue.id}
                                break

            state.confrontation_state = None
            yield {"type": "state", "round": state.round, "phase": state.phase,
                   "tension": state.tension, "scene": state.scene,
                   "game_over": False, "game_state": redact_game_state(state)}
            yield {"type": "done"}
            return

        # ══════════════════════════════════════════════════════════════
        # Phase 0: Synchronous computations (0ms)
        # ══════════════════════════════════════════════════════════════

        pacing_state = self._get_pacing_state(session_id)
        self._decrement_pacing_cooldowns(pacing_state)
        act_hint = 1 if state.round + 1 <= 6 else 2 if state.round + 1 <= 15 else 3
        pacing_snapshot = self._build_pacing_snapshot(session_id, act_hint)

        # ── Action cost: reset points at start of turn ──
        state.action_points = self.action_cost_system.reset(state.max_action_points)

        # ── Checkpoint: check if this round triggers a reasoning checkpoint ──
        next_round = state.round + 1
        if self.checkpoint_system.should_trigger(next_round, state.checkpoints_completed):
            discovered_clue_ids_cp = [c.id for c in state.clues if c.discovered]
            cp_state = self.checkpoint_system.get_checkpoint(next_round, discovered_clue_ids_cp)
            state.checkpoint_state = cp_state
            state.round = next_round
            yield {
                "type": "checkpoint",
                "prompt": cp_state.prompt,
                "options": [{"id": o.id, "label": o.label, "kind": o.kind} for o in cp_state.options],
            }
            yield {"type": "state", "round": state.round, "phase": state.phase,
                   "tension": state.tension, "scene": state.scene,
                   "game_over": False, "game_state": redact_game_state(state)}
            yield {"type": "done"}
            return

        # ── 3. NPC Autonomy ──
        discovered_clue_ids = [c.id for c in state.clues if c.discovered]
        # Snapshot present characters BEFORE NPC autonomy moves them (for confrontation detection)
        scene_short_pre_npc = _get_current_scene_short(state.scene, state.available_scenes)
        present_char_ids_at_turn_start = [
            c.id for c in state.characters if c.location == scene_short_pre_npc
        ]
        psych_states_for_npc = {}
        for char in state.characters:
            ps = self.psychology.get_state(session_id, char.id)
            psych_states_for_npc[char.id] = {
                "desperation": ps.desperation,
                "fear": ps.fear,
                "composure": ps.composure,
            }

        npc_actions = self.npc_autonomy.simulate_npc_turns(
            session_id=session_id,
            player_location=state.scene,
            round_num=state.round + 1,
            tension=state.tension,
            discovered_clues=discovered_clue_ids,
            psych_states=psych_states_for_npc,
        )

        for npc_act in npc_actions:
            if npc_act.moved:
                for char in state.characters:
                    if char.id == npc_act.character_id:
                        char.location = npc_act.location
                        break

        visible_npc_actions = self.npc_autonomy.get_visible_actions(
            session_id, state.scene
        )
        hidden_npc_actions = [
            a for a in npc_actions if not a.visible_to_player
        ]
        self._apply_npc_information_shares(session_id, state, state.round + 1)

        # Secret conversations
        npc_locs = {c.id: c.location for c in state.characters}
        discovered_clue_texts = [c.text for c in state.clues if c.discovered]
        secret_conv = self.secret_conversations.simulate(
            session_id, state.scene, npc_locs, state.tension, state.round + 1,
            config=self.config,
            character_states=psych_states_for_npc,
            discovered_clue_texts=discovered_clue_texts,
        )
        # If pre-written scripts are exhausted, try LLM-powered dynamic generation
        if secret_conv is None and self.config.provider != LLMProvider.FALLBACK:
            secret_conv = await self.secret_conversations.simulate_dynamic(
                session_id, state.scene, npc_locs, state.tension, state.round + 1,
                config=self.config,
                character_states=psych_states_for_npc,
                discovered_clue_texts=discovered_clue_texts,
            )
        if secret_conv:
            for char_id, effects in secret_conv.psych_effects.items():
                ps = self.psychology.get_state(session_id, char_id)
                for attr, delta in effects.items():
                    current = getattr(ps, attr, 0.0)
                    setattr(ps, attr, max(0.0, min(1.0, current + delta)))

        # ── Opening guidance: first turn orientation ──
        if state.round == 0:
            char_names = "、".join(c.name for c in state.characters)
            scene_names = "、".join(state.available_scenes[:3])
            yield {
                "type": "event",
                "text": (
                    f"在场的有{char_names}。"
                    f"你可以前往{scene_names}等地点进行调查，"
                    f"也可以直接和在场的人对话。"
                ),
            }

        # ── Ambient hints: sounds from adjacent rooms ──
        for npc_act in visible_npc_actions:
            if not npc_act.visible_to_player and npc_act.sound_generated:
                yield {
                    "type": "ambient_hint",
                    "text": f"你隐约听到{npc_act.location}方向传来{npc_act.sound_generated}……",
                }

        # ── Dramatic NPC events: full-screen cinematic moments ──
        for npc_act in visible_npc_actions:
            if npc_act.dramatic and npc_act.dramatic_text and npc_act.visible_to_player:
                ps = self.psychology.get_state(session_id, npc_act.character_id)
                yield {
                    "type": "dramatic_event",
                    "character": npc_act.character_name,
                    "character_id": npc_act.character_id,
                    "text": npc_act.dramatic_text,
                    "mood": _compute_mood(ps),
                }

        # ── Generate fallback narration and yield immediately ──
        fallback_result = self.action_engine.simulate_fallback(player_action)
        fallback_narration = _sanitize_narration(fallback_result.narration)
        if fallback_narration:
            yield {"type": "narration", "text": fallback_narration}

        # ══════════════════════════════════════════════════════════════
        # Phase 1: Parallel LLM — OAE + Story Architect (~1-2s)
        # ══════════════════════════════════════════════════════════════

        # Build world context for OAE
        world_summary = self.world.get_state_summary(session_id, state.scene)
        player_inv = ", ".join(ws.player_inventory) if ws.player_inventory else "无"

        chars_ctx_parts = []
        for c in state.characters:
            if c.location == state.scene:
                chars_ctx_parts.append(
                    f"- {c.name}({c.public_role}): 信任={c.trust_to_player}, 嫌疑={c.suspicion}"
                )
            else:
                chars_ctx_parts.append(f"- {c.name}: 不在此处(在{c.location})")
        characters_context = "\n".join(chars_ctx_parts) or "无人在场"

        full_world_context = (
            f"【当前位置】{state.scene}\n"
            f"【时间】{ws.time} ({ws.time_period})\n"
            f"【天气】{ws.weather}\n"
            f"【玩家物品】{player_inv}\n"
            f"【紧张度】{state.tension}/100\n"
            f"【阶段】{state.phase}\n\n"
            f"【场景描述】\n{world_summary}\n\n"
            f"【在场人物】\n{characters_context}"
        )

        recent_history = [e.text for e in state.events[-6:]] if state.events else []
        discovered_count = sum(1 for c in state.clues if c.discovered)

        # Launch OAE and Story Architect in parallel
        oae_task = asyncio.create_task(self.action_engine.simulate(
            player_action=player_action,
            world_context=full_world_context,
            characters_context=characters_context,
            recent_history=recent_history,
        ))

        # Smart routing: pre-check complexity with fallback result
        is_complex_pre = self._is_complex_turn(
            fallback_result, {}, [],
            [], [a for a in visible_npc_actions],
            state.round + 1, state.tension, self._stuck_turns.get(session_id, 0),
        )
        provider_overridden = False
        original_dm_provider = None
        original_arch_provider = None
        if not is_complex_pre:
            original_dm_provider = self.dm.config.provider
            original_arch_provider = self.story_architect.config.provider
            self.dm.config.provider = LLMProvider.FALLBACK
            self.story_architect.config.provider = LLMProvider.FALLBACK
            provider_overridden = True

        architect_task = asyncio.create_task(self.story_architect.generate_directive({
            "session_id": session_id,
            "round": state.round + 1,
            "max_rounds": state.max_rounds,
            "tension": state.tension,
            "phase": state.phase,
            "discovered_clue_count": discovered_count,
            "total_clues": len(state.clues),
            "player_progress": discovered_count / max(len(state.clues), 1),
            "player_type": "exploration",
            "stuck_turns": self._stuck_turns.get(session_id, 0),
            **pacing_snapshot,
        }))

        try:
            # Wait for OAE result
            action_result = await oae_task
            action_result.narration = _sanitize_narration(action_result.narration)

            # If LLM produced different narration, send update
            if (action_result.narration
                    and action_result.narration != fallback_narration):
                yield {"type": "narration_update", "text": action_result.narration}

            # ── Action cost check ──
            action_cat = action_result.action_category
            if not self.action_cost_system.can_afford(state.action_points, action_cat):
                blocked_msg = self.action_cost_system.get_blocked_message(action_cat)
                yield {"type": "action_blocked", "text": blocked_msg}
                yield {"type": "state", "round": state.round, "phase": state.phase,
                       "tension": state.tension, "scene": state.scene,
                       "game_over": False, "game_state": redact_game_state(state)}
                yield {"type": "done"}
                return
            state.action_points = self.action_cost_system.spend(state.action_points, action_cat)

            # ── Evidence confrontation detection (use pre-NPC-autonomy snapshot) ──
            confrontation = self.confrontation_system.detect_confrontation(
                session_id, player_action, discovered_clue_ids, present_char_ids_at_turn_start,
            )
            if confrontation:
                # Fill evidence text from clue
                for clue in state.clues:
                    if clue.id == confrontation.evidence_clue_id and clue.discovered:
                        confrontation.evidence_text = clue.text
                        break
                state.confrontation_state = confrontation
                yield {
                    "type": "confrontation",
                    "prompt": confrontation.prompt,
                    "character": confrontation.target_character_name,
                    "character_id": confrontation.target_character_id,
                    "evidence_text": confrontation.evidence_text,
                    "options": [{"id": o.id, "label": o.label, "kind": o.kind} for o in confrontation.options],
                }
                yield {"type": "state", "round": state.round, "phase": state.phase,
                       "tension": state.tension, "scene": state.scene,
                       "game_over": False, "game_state": redact_game_state(state)}
                yield {"type": "done"}
                return

            # ── Movement handling ──
            def _try_move() -> bool:
                for target in action_result.targets:
                    for avail in state.available_scenes:
                        if avail in target or target in avail or target == avail:
                            state.scene = avail
                            return True
                for avail in state.available_scenes:
                    if avail in player_action:
                        move_keywords = ["去", "回", "前往", "到", "走到", "来到", "进入", "回到"]
                        if any(kw in player_action and avail in player_action for kw in move_keywords):
                            state.scene = avail
                            return True
                if action_result.narration:
                    for avail in state.available_scenes:
                        if f"来到了{avail}" in action_result.narration or f"到达{avail}" in action_result.narration:
                            state.scene = avail
                            return True
                return False

            prev_scene = state.scene
            if action_result.action_category == "move" and action_result.feasible:
                _try_move()
            elif action_result.feasible:
                _try_move()

            # Record movement in notebook
            if state.scene != prev_scene:
                self.notebook.record_movement(session_id, state.round + 1, state.scene)

            legacy_intent = action_result.legacy_intent

            # ── Clue discovery bridge ──
            engine_clues = _discover_clues_for_action(
                state, action_result.action_category, legacy_intent, state.scene
            )
            all_discovered = list(set(action_result.discovered_clues + engine_clues))
            action_result.discovered_clues = all_discovered

            # ── Expert agents (sync computations) ──
            tension_adj = self.tension_conductor.conduct(
                session_id=session_id,
                round_num=state.round + 1,
                max_rounds=state.max_rounds,
                current_tension=state.tension,
                raw_delta=action_result.tension_delta,
                discovered_clues_count=discovered_count,
                phase=state.phase,
            )

            prev_clue_count = self._last_clue_counts.get(session_id, 0)
            if discovered_count == prev_clue_count:
                self._stuck_turns[session_id] = self._stuck_turns.get(session_id, 0) + 1
            else:
                self._stuck_turns[session_id] = 0
            self._last_clue_counts[session_id] = discovered_count

            target_char_id = None
            for t in action_result.targets:
                if t in [c.id for c in state.characters]:
                    target_char_id = t
                    break

            for char in state.characters:
                self.psychology.update_after_turn(
                    session_id=session_id, character_id=char.id,
                    intent_type=legacy_intent,
                    rule_result={
                        "success": action_result.success_level,
                        "tension_delta": action_result.tension_delta,
                        "trust_changes": action_result.trust_changes,
                        "suspicion_changes": action_result.suspicion_changes,
                        "discovered_clues": action_result.discovered_clues,
                        "target_character": target_char_id,
                    },
                    player_action=player_action, tension=state.tension,
                )

            breaking_points: Dict[str, str] = {}
            for char in state.characters:
                bp = self.psychology.check_breaking_point(session_id, char.id)
                if bp:
                    breaking_points[char.id] = bp

            psych_directives: Dict[str, dict] = {}
            for char in state.characters:
                psych_directives[char.id] = self.psychology.get_behavior_directive(
                    session_id, char.id
                )

            psych_snapshots = []
            for char in state.characters:
                ps = self.psychology.get_state(session_id, char.id)
                psych_snapshots.append(ConspiracyPsychState(
                    character_id=char.id, suspicion=char.suspicion,
                    trust_to_player=char.trust_to_player, desperation=ps.desperation,
                ))

            self.conspiracy.update_alliances(
                session_id=session_id, characters_psych_states=psych_snapshots,
                player_target=target_char_id, discovered_clues=discovered_clue_ids,
                tension=state.tension,
            )

            conspiracy_events = self.conspiracy.get_npc_events(
                session_id, state.tension, state.phase, state.round + 1
            )

            betrayal_events = []
            for char in state.characters:
                betrayal = self.conspiracy.should_trigger_betrayal(
                    session_id, char.id, state.tension
                )
                if betrayal:
                    betrayal_events.append(betrayal)

            # Re-check complexity with real action_result
            is_complex = self._is_complex_turn(
                action_result, breaking_points, conspiracy_events,
                betrayal_events, [a for a in visible_npc_actions],
                state.round + 1, state.tension, self._stuck_turns.get(session_id, 0),
            )
            if is_complex and provider_overridden:
                self.dm.config.provider = original_dm_provider
                self.story_architect.config.provider = original_arch_provider
                provider_overridden = False

            # ══════════════════════════════════════════════════════════
            # Phase 2: DM adjudication (~2-4s)
            # ══════════════════════════════════════════════════════════

            architect_directive = await architect_task

            proposals = AgentProposals(
                action_narration=action_result.narration,
                action_category=action_result.action_category,
                action_feasible=action_result.feasible,
                action_tension_delta=action_result.tension_delta,
                current_act=architect_directive.current_act,
                current_beat=architect_directive.current_beat,
                pacing=architect_directive.pacing,
                architect_director_note=architect_directive.director_note,
                architect_narration=architect_directive.system_narration,
                architect_events=architect_directive.suggested_events,
                hint_level=architect_directive.hint_level,
                tension_adjusted_delta=tension_adj.adjusted_delta,
                tension_atmosphere=tension_adj.atmosphere,
                visible_npc_actions=[a.action for a in visible_npc_actions],
                hidden_npc_actions=[a.action for a in hidden_npc_actions],
                npc_evidence=[
                    e for a in npc_actions if a.evidence_left for e in [a.evidence_left]
                ],
                breaking_points=breaking_points,
                psych_directives=psych_directives,
                conspiracy_events=conspiracy_events,
                betrayal_events=betrayal_events,
                round_num=state.round + 1,
                max_rounds=state.max_rounds,
                tension=state.tension,
                phase=state.phase,
                discovered_clues=discovered_count,
                total_clues=len(state.clues),
                player_action=player_action,
                stuck_turns=self._stuck_turns.get(session_id, 0),
                act_reveal_count=pacing_snapshot["act_reveal_count"],
                reveal_budget=pacing_snapshot["reveal_budget"],
                reveal_budget_remaining=pacing_snapshot["reveal_budget_remaining"],
                event_cooldowns=pacing_snapshot["event_cooldowns"],
                recent_high_intensity_turns=pacing_snapshot["recent_high_intensity_turns"],
                stuck_recovery_level=pacing_snapshot["stuck_recovery_level"],
            )

            dm_directive = await self.dm.adjudicate(proposals, session_id=session_id)

            # Yield DM narration (replaces OAE narration if present)
            if dm_directive.system_narration:
                sanitized_dm_narration = _sanitize_narration(dm_directive.system_narration)
                yield {"type": "narration_update", "text": sanitized_dm_narration}

            # Yield director note
            director_note = dm_directive.director_note
            if dm_directive.hint_text:
                director_note = dm_directive.hint_text
            if director_note:
                yield {"type": "director", "text": director_note}

            # ══════════════════════════════════════════════════════════
            # Phase 3: Character agents via as_completed (~3-6s)
            # ══════════════════════════════════════════════════════════

            current_scene_short = _get_current_scene_short(state.scene, state.available_scenes)
            relevant_characters = []
            should_generate_replies = self._should_generate_character_replies(
                action_result, target_char_id, is_complex
            )
            if should_generate_replies:
                for char in state.characters:
                    is_targeted = char.id == target_char_id
                    is_present = char.location == current_scene_short
                    is_accuse = legacy_intent == "accuse"
                    if is_targeted or (is_present and action_result.action_category != "move") or is_accuse:
                        relevant_characters.append(char)

            if should_generate_replies and dm_directive.force_npc_reaction:
                forced = next(
                    (c for c in state.characters if c.id == dm_directive.force_npc_reaction),
                    None,
                )
                if forced and forced not in relevant_characters:
                    relevant_characters.append(forced)

            char_extra_contexts: Dict[str, str] = {}
            for char in relevant_characters:
                parts = []
                d = psych_directives.get(char.id, {})
                if d:
                    parts.append(
                        f"【当前心理状态】\n"
                        f"- 镇定程度：{d.get('composure_level', 'high')}\n"
                        f"- 行为指导：{d.get('manner', '')}\n"
                        f"- 防御策略：{d.get('strategy', 'deflect')}"
                    )
                conspiracy_ctx = self.conspiracy.get_character_conspiracy_context(
                    session_id, char.id
                )
                if conspiracy_ctx:
                    parts.append(f"【与其他角色的关系动态】\n{conspiracy_ctx}")
                continuity_ctx = self.continuity.build_continuity_prompt(
                    session_id, char.id
                )
                if continuity_ctx:
                    parts.append(continuity_ctx)
                tell_ctx = self.secret_conversations.get_tell_context_for_prompt(
                    session_id, char.id
                )
                if tell_ctx:
                    parts.append(tell_ctx)
                # Memory context — smart layered memory
                smart_mem = self.continuity.get_smart_memory(
                    session_id, char.id, player_action
                )
                if smart_mem:
                    parts.append(smart_mem)
                if char.id in action_result.npc_reactions:
                    parts.append(f"【对玩家行为的反应提示】\n{action_result.npc_reactions[char.id]}")
                parts.append(f"【本轮氛围】{dm_directive.turn_mood}")
                char_extra_contexts[char.id] = "\n\n".join(parts)

            async def _get_char_response_s(char):
                extra = char_extra_contexts.get(char.id, "")
                try:
                    intent_enum = IntentType(legacy_intent)
                except ValueError:
                    intent_enum = IntentType.other
                text = await self.character_agent.generate_response(
                    character=char, state=state, player_action=player_action,
                    intent=intent_enum,
                    rule_result={"success": action_result.success_level,
                                 "narration": action_result.narration,
                                 "discovered_clues": action_result.discovered_clues},
                    extra_context=extra,
                    scoped_facts=get_character_scoped_facts(state, char.id),
                    hard_boundaries=char.hard_boundaries,
                )
                text = _sanitize_narration(text)
                voice, speed = _character_voice(char.id, self.psychology.get_state(session_id, char.id))
                return NPCReply(
                    character_id=char.id, character_name=char.name, text=text,
                    voice=voice, speed=speed,
                )

            # Fire-and-forget image generation
            should_generate_image = self.image_agent is not None and (
                action_result.action_category == "move"
                or action_result.discovered_clues
                or action_result.world_changes
            )
            if should_generate_image and self.image_agent:
                asyncio.create_task(self.image_agent.generate_scene_image(
                    scene=state.scene, narration=action_result.narration,
                    tension=state.tension, phase=state.phase,
                ))

            # Yield NPC replies as they complete (key streaming optimization)
            npc_replies: List[NPCReply] = []
            if relevant_characters:
                char_tasks = [
                    asyncio.create_task(_get_char_response_s(c))
                    for c in relevant_characters
                ]
                for coro in asyncio.as_completed(char_tasks):
                    reply = await coro
                    npc_replies.append(reply)
                    yield {
                        "type": "npc",
                        "character": reply.character_name,
                        "character_id": reply.character_id,
                        "text": reply.text,
                        "voice": reply.voice,
                        "speed": reply.speed,
                    }

            # ══════════════════════════════════════════════════════════
            # Final: Apply state changes + yield remaining events
            # ══════════════════════════════════════════════════════════

            if action_result.world_changes:
                self.world.apply_changes(session_id, action_result.world_changes)
            for npc_act in npc_actions:
                if npc_act.world_changes:
                    self.world.apply_changes(session_id, npc_act.world_changes)
            self.world.advance_time(session_id)

            state.round += 1
            state.tension = _clamp(state.tension + dm_directive.final_tension_delta)

            for char in state.characters:
                if char.id in action_result.trust_changes:
                    char.trust_to_player = _clamp(
                        char.trust_to_player + action_result.trust_changes[char.id]
                    )
                if char.id in action_result.suspicion_changes:
                    char.suspicion = _clamp(
                        char.suspicion + action_result.suspicion_changes[char.id]
                    )

            # ── Behavior tagging for ending system ──
            _record_behavior_tags(state, action_result, player_action, target_char_id)

            new_clue_texts = []
            new_clue_ids: List[str] = []
            if dm_directive.allow_clue_discovery:
                for clue_id in action_result.discovered_clues:
                    for clue in state.clues:
                        if clue.id == clue_id and not clue.discovered:
                            clue.discovered = True
                            clue.holder = "player"
                            new_clue_texts.append(clue.text)
                            new_clue_ids.append(clue.id)
                            if clue.text not in state.knowledge.player_known:
                                state.knowledge.player_known.append(clue.text)
            if new_clue_ids:
                self._apply_clue_fact_disclosures(
                    state, new_clue_ids, method="clue_discovered"
                )

            self.truth_resolver.update_weights(
                session_id, player_action, target_char_id,
                [c.id for c in state.clues if c.discovered],
            )
            self.truth_resolver.try_lock(session_id, state.round)

            # ── Truth hint: signal to player that their investigation matters ──
            weight_info = self.truth_resolver.get_weight_delta(session_id)
            if weight_info.get("just_locked"):
                yield {
                    "type": "truth_hint",
                    "text": "真相的轮廓在你的调查中逐渐清晰了……",
                    "intensity": "strong",
                }
            elif weight_info.get("top_weight_delta", 0) > 0.3:
                yield {
                    "type": "truth_hint",
                    "text": "你的调查方向正在影响事件的走向……",
                    "intensity": "subtle",
                }

            caught_lies = []
            if new_clue_ids:
                caught_lies = self.lie_detector.check_for_contradictions(
                    session_id, new_clue_ids
                )

            if legacy_intent == "accuse":
                state.phase = "公开对峙"
            elif architect_directive.current_beat == "crisis" and state.phase not in ("高压对峙", "公开对峙"):
                state.phase = "高压对峙"
            elif architect_directive.current_beat == "climax" and state.phase != "终局逼近":
                state.phase = "终局逼近"
            elif state.tension >= 70 and state.phase == "自由试探":
                state.phase = "高压对峙"
            elif discovered_count >= 3 and state.phase == "自由试探":
                state.phase = "深入调查"

            state.events.append(
                Event(round=state.round, type=legacy_intent, text=f"玩家：{player_action}")
            )

            for reply in npc_replies:
                self.continuity.record_statement(
                    session_id=session_id, round=state.round,
                    character_id=reply.character_id, text=reply.text,
                )
                self.lie_detector.record_npc_response(
                    session_id, state.round,
                    reply.character_id, reply.character_name, reply.text,
                )
                # Record NPC statement in notebook
                self.notebook.record_statement(
                    session_id, state.round,
                    reply.character_id, reply.character_name, reply.text,
                )

            # Events
            current_scene_short = _get_current_scene_short(state.scene, state.available_scenes)
            present_char_ids = [c.id for c in state.characters if c.location == current_scene_short]
            discovered_texts = [c.text for c in state.clues if c.discovered]

            confrontation = self.npc_interaction.get_confrontation(
                session_id, present_char_ids, state.tension, state.round, discovered_texts,
            )
            for line in confrontation:
                npc_replies.append(NPCReply(
                    character_id=line.character_id,
                    character_name=line.character_name,
                    text=line.text,
                ))
                yield {
                    "type": "npc",
                    "character": line.character_name,
                    "character_id": line.character_id,
                    "text": line.text,
                }

            proactive = self.npc_interaction.get_proactive_lines(
                session_id, present_char_ids, state.tension, state.round,
                [c.id for c in state.clues if c.discovered],
            )
            for line in proactive:
                yield {"type": "event", "text": line.text}
                state.events.append(Event(round=state.round, type="proactive", text=line.text))

            for lie in caught_lies:
                yield {
                    "type": "lie_caught",
                    "character": lie.character_name,
                    "character_id": lie.character_id,
                    "original_claim": lie.original_claim,
                    "text": lie.confrontation_text,
                }
                state.events.append(Event(
                    round=state.round, type="lie_caught",
                    text=f"[揭穿谎言] {lie.character_name}: {lie.confrontation_text[:100]}",
                ))
                # Record contradiction in notebook
                self.notebook.record_contradiction(
                    session_id, state.round,
                    lie.character_id, lie.character_name,
                    lie.original_claim, lie.claim_round,
                    lie.confrontation_text[:80],
                )

            for evt_text in dm_directive.approved_events:
                if not evt_text or not any('\u4e00' <= c <= '\u9fff' for c in evt_text):
                    continue
                evt_text = _sanitize_narration(evt_text)
                yield {"type": "event", "text": evt_text}
                state.events.append(Event(round=state.round, type="npc_event", text=evt_text))

            self.dm.record_used_events(session_id, dm_directive.approved_events)

            if dm_directive.inject_twist:
                twist_text = _sanitize_narration(dm_directive.inject_twist)
                yield {"type": "event", "text": twist_text}
                state.events.append(
                    Event(round=state.round, type="twist", text=twist_text)
                )

            location_evidence = self.npc_autonomy.get_evidence_at_location(
                session_id, state.scene
            )
            for evidence in location_evidence:
                yield {"type": "npc_action", "text": f"你注意到：{evidence}"}
                self.notebook.record_event(
                    session_id, state.round, f"发现痕迹：{evidence}", ["evidence"],
                )

            secret_evidence = self.secret_conversations.get_evidence_at_location(
                session_id, state.scene
            )
            for evidence in secret_evidence:
                yield {"type": "event", "text": f"你注意到一些异常：{evidence}"}
                state.events.append(Event(
                    round=state.round, type="secret_evidence", text=evidence,
                ))

            for i, clue_text in enumerate(new_clue_texts):
                # Dramatic lead-in before the clue content
                clue_id = new_clue_ids[i] if i < len(new_clue_ids) else ""
                clue_obj = next((c for c in state.clues if c.id == clue_id), None)
                clue_location = clue_obj.location if clue_obj else current_scene_short

                yield {
                    "type": "clue_discovery",
                    "text": clue_text,
                    "location": clue_location,
                    "layer": 3 if clue_id.startswith("clue_L3") else 2 if clue_id.startswith("clue_L2") else 1,
                }

                # Record in notebook
                self.notebook.record_clue(
                    session_id, state.round, clue_text, clue_location,
                )

            # End conditions
            game_over = False
            ending = None

            if state.round >= state.max_rounds:
                game_over = True
            elif state.tension >= 100:
                game_over = True
            else:
                cellar_sound = next(
                    (c for c in state.clues if c.id == "cellar_sound"), None
                )
                if (
                    cellar_sound and cellar_sound.discovered
                    and legacy_intent in ("search", "other")
                    and state.scene == "酒窖"
                    and state.tension >= 80
                ):
                    game_over = True

                if legacy_intent == "accuse" and player_action:
                    try:
                        deduction = await self.deduction_validator.validate(
                            player_accusation=player_action,
                            discovered_clues=[c.text for c in state.clues if c.discovered],
                            player_known_facts=state.knowledge.player_known,
                        )
                        if deduction.ending_type in ("perfect", "good"):
                            game_over = True
                    except Exception:
                        action_lower = player_action.lower()
                        truth_kw = ["自导自演", "自己策划", "假装失踪", "酒窖密室", "试探"]
                        if sum(1 for kw in truth_kw if kw in action_lower) >= 2:
                            game_over = True

            if game_over:
                state.game_over = True
                # Use behavior-chain ending system
                truth_level = _calc_truth_level(state)
                moral_stance = _calc_moral_stance(state)
                relationship = _calc_relationship(state)
                ending = _resolve_ending(truth_level, moral_stance, relationship, state)
                score = calculate_score(
                    clues_found=sum(1 for c in state.clues if c.discovered),
                    total_clues=len(state.clues),
                    truth_accuracy={"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.15}.get(truth_level, 0.4),
                    rounds_used=state.round,
                    max_rounds=state.max_rounds,
                    lies_caught=len(caught_lies),
                    confrontations_won=len(caught_lies),
                    game_over_reason="deduction" if legacy_intent == "accuse" else "timeout" if state.round >= state.max_rounds else "chaos",
                )
                state.ending = ending

                # ── Truth Replay: chronological playback ──
                for i, step in enumerate(state.truth.hidden_chain):
                    yield {
                        "type": "truth_replay",
                        "step": i + 1,
                        "total": len(state.truth.hidden_chain),
                        "text": step,
                    }

                yield {"type": "ending", "text": ending}

                # ── NPC Afterwords: characters speak honestly ──
                for char in state.characters:
                    afterword = self._build_npc_afterword(char, truth_level, state)
                    if afterword:
                        yield {
                            "type": "afterword",
                            "character": char.name,
                            "character_id": char.id,
                            "text": afterword,
                        }

                # ── Score Card: separate visual event ──
                yield {
                    "type": "score_card",
                    "total_score": score.total_score,
                    "rank": score.rank,
                    "rank_title": score.rank_title,
                    "clue_score": score.clue_score,
                    "deduction_score": score.deduction_score,
                    "efficiency_score": score.efficiency_score,
                    "interaction_score": score.interaction_score,
                    "summary": score.summary,
                    "truth_level": truth_level,
                    "moral_stance": moral_stance,
                    "relationship": relationship,
                }

            self._update_pacing_state(
                session_id,
                act=architect_directive.current_act,
                new_clue_count=len(new_clue_ids),
                approved_events=dm_directive.approved_events,
                turn_mood=dm_directive.turn_mood,
                inject_twist=dm_directive.inject_twist,
                stuck_turns=self._stuck_turns.get(session_id, 0),
            )

            # Map psychology → mood label
            for char in state.characters:
                ps = self.psychology.get_state(session_id, char.id)
                char.mood = _compute_mood(ps)

            # Final state event
            state_data = {
                "type": "state",
                "round": state.round,
                "phase": state.phase,
                "tension": state.tension,
                "scene": state.scene,
                "game_over": game_over,
                "game_state": redact_game_state(state),
            }
            yield state_data
            yield {"type": "done"}

        finally:
            if provider_overridden:
                self.dm.config.provider = original_dm_provider
                self.story_architect.config.provider = original_arch_provider

    def _build_npc_afterword(
        self, char, truth_level: str, state: GameState
    ) -> str:
        """Generate an honest afterword from an NPC after the game ends."""
        trust = char.trust_to_player

        if "委托" in char.secret or "自导自演" in char.secret or "共谋" in char.secret:
            # Accomplice character
            if truth_level in ("A", "B"):
                return (
                    f"{char.name}放下了一切伪装，轻声说："
                    f"「你看穿了一切。说实话……我松了一口气。"
                    f"隐瞒真相比你想象的要累得多。」"
                )
            else:
                return (
                    f"{char.name}看着你，欲言又止："
                    f"「也许有一天你会明白我为什么这么做。」"
                )
        elif "争吵" in char.secret or "吵" in char.secret:
            # Character with argument secret
            if trust >= 50:
                return (
                    f"{char.name}苦笑了一下："
                    f"「我承认我昨晚失控了。但我没有害他。"
                    f"我只是……不想失去这段关系。」"
                )
            else:
                return (
                    f"{char.name}别过脸去："
                    f"「你不会理解的。有些事情……不是对错能解释的。」"
                )
        else:
            # Outsider character
            if truth_level == "A":
                return (
                    f"{char.name}合上了笔记本："
                    f"「你是我见过最出色的调查者。"
                    f"这个故事——我会如实记录。」"
                )
            else:
                return (
                    f"{char.name}推了推眼镜："
                    f"「这个夜晚还有很多没有被写出来的故事。"
                    f"也许我们都只看到了真相的一角。」"
                )

    def _turn_response_to_events(self, result: TurnResponse):
        """Convert a TurnResponse into a list of SSE event dicts."""
        events = []
        if result.system_narration:
            events.append({"type": "narration", "text": result.system_narration})
        if result.director_note:
            events.append({"type": "director", "text": result.director_note})
        for reply in result.npc_replies:
            events.append({
                "type": "npc", "character": reply.character_name,
                "character_id": reply.character_id, "text": reply.text,
                "voice": reply.voice, "speed": reply.speed,
            })
        for evt in result.npc_events:
            events.append({"type": "event", "text": evt.text})
        for clue in result.new_clues:
            events.append({"type": "clue", "text": clue})
        if result.scene_image:
            events.append({"type": "scene_image", "url": result.scene_image, "scene": result.scene})
        if result.game_over and result.ending:
            events.append({"type": "ending", "text": result.ending})
        state_data = {
            "type": "state", "round": result.round, "phase": result.phase,
            "tension": result.tension, "scene": result.scene,
            "game_over": result.game_over,
        }
        if result.game_state:
            state_data["game_state"] = result.game_state
        events.append(state_data)
        events.append({"type": "done"})
        return events

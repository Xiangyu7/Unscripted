"""
Truth Resolver — Schrödinger's Mystery System

At game start, the truth is NOT determined. Multiple possible truths coexist.
Based on how the player investigates, one truth "crystallizes" mid-game.

This means:
  - Playthrough 1: Player focuses on Lin Lan → truth becomes "Lin Lan kidnapped Gu Yan"
  - Playthrough 2: Player focuses on wine cellar → truth becomes "Gu Yan staged it"
  - Playthrough 3: Player focuses on Zhou Mu → truth becomes "Zhou Mu's accident"

Same clues, same NPCs, different answer every time.
"""

import random
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PossibleTruth(BaseModel):
    """One possible truth for the mystery."""
    id: str
    summary: str                          # One-line summary
    culprit: Optional[str] = None         # Character ID, or None if no crime
    detail: str                           # Full explanation

    # How each clue should be interpreted under this truth
    clue_interpretations: Dict[str, str] = Field(default_factory=dict)

    # What each NPC's real secret is under this truth
    npc_secrets: Dict[str, str] = Field(default_factory=dict)

    # Keywords that signal the player is leaning toward this truth
    lock_signals: List[str] = Field(default_factory=list)

    # Ending text variants
    perfect_ending: str = ""
    good_ending: str = ""

    # Weight for initial random selection (higher = more likely)
    base_weight: float = 1.0


class TruthState(BaseModel):
    """Per-session truth tracking."""
    possible_truths: List[str] = Field(default_factory=list)  # truth IDs still possible
    truth_weights: Dict[str, float] = Field(default_factory=dict)  # truth_id → weight
    locked_truth_id: Optional[str] = None  # Once locked, this is THE answer
    lock_round: Optional[int] = None
    # Track weight changes per turn for truth_hint events
    previous_weights: Dict[str, float] = Field(default_factory=dict)
    just_locked: bool = False


# ═══════════════════════════════════════════════════════════════
# The 4 possible truths for the Gu Family Case
# ═══════════════════════════════════════════════════════════════

GU_FAMILY_TRUTHS: Dict[str, PossibleTruth] = {
    "self_staged": PossibleTruth(
        id="self_staged",
        summary="顾言自导自演了失踪，藏在酒窖密室里试探所有人",
        culprit=None,
        detail=(
            "顾言精心策划了自己的失踪。他修改遗嘱是诱饵，想看看身边人在利益面前的真面目。"
            "林岚是唯一的知情者，负责配合执行计划。顾言就躲在酒窖的密室里，通过手机遥控一切。"
        ),
        clue_interpretations={
            "study_scratches": "划痕是顾言自己从书房急匆匆出去时刮到的",
            "wine_cellar_footprint": "脚印是顾言自己走进酒窖密室时留下的",
            "torn_letter": "信是顾言写给林岚的行动计划，被林岚撕碎销毁",
            "will_draft": "'看看他们的反应'——顾言故意留下的试探标记",
            "anonymous_tip": "匿名纸条是顾言自己写的，用来制造混乱",
            "cellar_provisions": "顾言给自己准备的物资，打算在密室里待一晚",
            "linlan_phone_log": "顾言在'失踪'后仍在给林岚发指令",
            "cellar_sound": "密室里顾言的呼吸声",
            "staged_evidence": "书房'失踪现场'是顾言和林岚一起布置的道具",
        },
        npc_secrets={
            "linlan": "她是顾言计划的唯一执行者，负责转移遗嘱副本并制造假象",
            "zhoumu": "他确实因为遗产和顾言吵过架，但跟失踪无关",
            "songzhi": "她收到的匿名信其实是顾言自己寄的",
        },
        lock_signals=["自导自演", "假装", "密室", "计划", "试探", "导演", "安排", "演戏", "酒窖藏人"],
        perfect_ending=(
            "完美破局——你精准地道出了真相的核心！"
            "顾言从酒窖密室中走出，向你鼓掌：'了不起，你看穿了一切。'"
            "他的失踪确实是一场精心策划的试探——"
            "而你，是唯一识破了这场戏的人。"
        ),
        good_ending=(
            "你找到了关键线索，离真相只有一步之遥。"
            "顾言缓缓走出密室，微微点头：'你看到了大部分……但还差一点。'"
        ),
        base_weight=1.0,
    ),

    "linlan_coverup": PossibleTruth(
        id="linlan_coverup",
        summary="林岚为了保护遗嘱秘密，把顾言锁在了酒窖里",
        culprit="linlan",
        detail=(
            "林岚发现顾言要修改遗嘱，将大部分财产捐给基金会。"
            "作为管理这笔遗产的秘书，她的利益会受到巨大损害。"
            "她趁晚宴混乱时引顾言到酒窖，锁上了门，想争取时间销毁新遗嘱。"
        ),
        clue_interpretations={
            "study_scratches": "林岚拖着顾言经过书房时门被刮到的",
            "wine_cellar_footprint": "林岚把顾言带到酒窖时两人的脚印",
            "torn_letter": "林岚撕毁的是顾言打算公开的遗嘱修改通知",
            "will_draft": "'看看他们的反应'是顾言写的——但他没机会看了",
            "anonymous_tip": "林岚提前放的，想把注意力引向遗产纠纷，掩盖自己的行动",
            "cellar_provisions": "林岚给被锁住的顾言准备的——她不想伤害他，只是想拖延时间",
            "linlan_phone_log": "林岚用顾言的手机给自己发了假消息，制造顾言还在外面的假象",
            "cellar_sound": "被锁在酒窖里的顾言发出的声音",
            "staged_evidence": "林岚布置的假现场，想让人以为顾言是被外人带走的",
        },
        npc_secrets={
            "linlan": "她把顾言锁在了酒窖里，正在想办法销毁新遗嘱",
            "zhoumu": "他跟顾言吵过架但和失踪无关，不过他的争吵给了林岚下手的掩护",
            "songzhi": "她收到的匿名信让她提前来到了现场，但她不知道是谁发的",
        },
        lock_signals=["林岚", "秘书", "锁", "遗嘱", "保护", "利益", "销毁", "掩盖"],
        perfect_ending=(
            "真相大白——林岚的面具终于碎裂。"
            "当你亮出证据时，她的手开始颤抖：'我……我没有别的选择。'"
            "酒窖的门被打开，顾言安然无恙地走了出来。"
            "他看着林岚，眼中是失望和痛惜：'我最信任的人，原来是你。'"
        ),
        good_ending=(
            "你找到了林岚的破绽，但还缺少关键证据。"
            "林岚冷笑：'你说的都是推测。'但她握紧的拳头出卖了她。"
        ),
        base_weight=1.0,
    ),

    "zhoumu_accident": PossibleTruth(
        id="zhoumu_accident",
        summary="周牧和顾言争吵时失手推倒了他，慌乱中把他藏到了酒窖",
        culprit="zhoumu",
        detail=(
            "昨晚的争吵比所有人想象的都激烈。"
            "周牧得知顾言要把遗产捐出去后彻底失控，推搡中顾言撞到了书桌角，晕倒了。"
            "周牧吓坏了，把昏迷的顾言拖到酒窖藏起来，然后假装什么都没发生。"
        ),
        clue_interpretations={
            "study_scratches": "争吵时周牧推顾言撞到门把手留下的痕迹",
            "wine_cellar_footprint": "周牧拖着昏迷的顾言进酒窖时的脚印——所以特别深",
            "torn_letter": "周牧撕碎的是自己写给顾言的求和信——他后悔了但又不敢承认",
            "will_draft": "'看看他们的反应'是顾言的原话——周牧看到后更加愤怒",
            "anonymous_tip": "宋知微提前得到的线报——有人告诉她顾家会出事",
            "cellar_provisions": "周牧给昏迷的顾言准备的水和食物——他不想他死",
            "linlan_phone_log": "林岚一直在联系顾言但联系不上——她不知道发生了什么",
            "cellar_sound": "酒窖里逐渐苏醒的顾言发出的声音",
            "staged_evidence": "周牧慌忙布置的假现场，想让人以为是外人所为",
        },
        npc_secrets={
            "linlan": "她真的不知道发生了什么，但她一直在联系顾言联系不上，开始怀疑",
            "zhoumu": "他失手伤了顾言并藏了起来，正陷入恐惧和自责中",
            "songzhi": "她收到线报来采访，意外卷入了真正的犯罪现场",
        },
        lock_signals=["周牧", "争吵", "推", "失手", "意外", "打架", "冲突", "隐瞒", "愤怒"],
        perfect_ending=(
            "周牧终于崩溃了。"
            "当你把所有证据摆在他面前时，他的伪装彻底瓦解。"
            "他捂着脸，声音哽咽：'我没想伤害他……我只是太生气了……'"
            "你们冲进酒窖，发现顾言已经醒来。他虚弱地靠在墙上，"
            "看着被带来的周牧：'老朋友……我们需要谈谈。'"
        ),
        good_ending=(
            "你注意到了周牧的异常表现，但还缺少直接证据。"
            "周牧还在苦撑：'我跟你说了，我什么都不知道！'但他的声音在发抖。"
        ),
        base_weight=1.0,
    ),

    "songzhi_setup": PossibleTruth(
        id="songzhi_setup",
        summary="宋知微为了独家新闻，事先安排了这场'失踪'",
        culprit="songzhi",
        detail=(
            "宋知微不只是一个普通记者。她提前调查了顾家的遗产纠纷，"
            "发现这是一个爆炸性新闻的金矿。她匿名给顾言发了一封信，"
            "暗示有人要对他不利，引导他'暂时消失'以求自保。"
            "顾言上当后躲进酒窖，宋知微则在晚宴上'恰好在场'，准备记录一切。"
        ),
        clue_interpretations={
            "study_scratches": "顾言收到宋知微的警告信后，慌忙从书房取走贵重物品",
            "wine_cellar_footprint": "受到惊吓的顾言自己躲进酒窖",
            "torn_letter": "宋知微撕碎了自己发给顾言的匿名警告信的底稿",
            "will_draft": "遗嘱是宋知微调查的核心——她知道这会引发冲突",
            "anonymous_tip": "这张纸条就是宋知微自己放的——她在制造新闻素材",
            "cellar_provisions": "顾言被吓到后自己准备的——他真以为有人要害他",
            "linlan_phone_log": "林岚在找老板，但顾言按照'匿名警告'的指示不敢回复",
            "cellar_sound": "躲在酒窖里惊魂未定的顾言",
            "staged_evidence": "没有人布置——顾言慌忙离开时自己弄乱的",
        },
        npc_secrets={
            "linlan": "她完全不知情，正在焦急地找老板",
            "zhoumu": "他跟顾言的争吵是真的，但和失踪无关",
            "songzhi": "她是幕后操纵者——用假情报引导了顾言的'自我失踪'",
        },
        lock_signals=["宋知微", "记者", "新闻", "匿名", "线报", "策划", "操纵", "信息"],
        perfect_ending=(
            "宋知微被你逼到了墙角。"
            "当你揭露匿名信的真正来源时，她的职业笑容终于凝固了。"
            "'你比我想象的聪明，'她缓缓说，'但这本该是一个完美的独家新闻。'"
            "真相是：没有人伤害顾言。宋知微用假情报让他自己吓自己，"
            "然后在他'失踪'后扮演无辜的旁观者，等着收割头条。"
        ),
        good_ending=(
            "你觉得宋知微的出现太巧了——一个记者怎么会恰好在犯罪现场？"
            "她还在微笑：'我只是在做我的工作。'但你知道事情没那么简单。"
        ),
        base_weight=0.8,  # Slightly less common
    ),
}


class TruthResolver:
    """Manages truth state per session — decides which truth becomes real."""

    def __init__(self):
        self._states: Dict[str, TruthState] = {}

    def init_session(self, session_id: str):
        """Initialize truth state for a new game session."""
        truth_ids = list(GU_FAMILY_TRUTHS.keys())
        weights = {tid: GU_FAMILY_TRUTHS[tid].base_weight for tid in truth_ids}
        self._states[session_id] = TruthState(
            possible_truths=truth_ids,
            truth_weights=weights,
        )

    def get_state(self, session_id: str) -> TruthState:
        if session_id not in self._states:
            self.init_session(session_id)
        return self._states[session_id]

    def is_locked(self, session_id: str) -> bool:
        return self.get_state(session_id).locked_truth_id is not None

    def get_locked_truth(self, session_id: str) -> Optional[PossibleTruth]:
        state = self.get_state(session_id)
        if state.locked_truth_id:
            return GU_FAMILY_TRUTHS.get(state.locked_truth_id)
        return None

    def update_weights(
        self,
        session_id: str,
        player_action: str,
        target_character: Optional[str],
        discovered_clue_ids: List[str],
    ):
        """Update truth weights based on player behavior."""
        state = self.get_state(session_id)
        if state.locked_truth_id:
            return  # Already locked

        # Snapshot weights before this update (for delta tracking)
        state.previous_weights = dict(state.truth_weights)
        state.just_locked = False

        action_lower = player_action.lower()

        for truth_id in state.possible_truths:
            truth = GU_FAMILY_TRUTHS[truth_id]
            boost = 0.0

            # Check lock signals in player action
            for signal in truth.lock_signals:
                if signal in action_lower:
                    boost += 0.3

            # Character focus boost
            if target_character and truth.culprit == target_character:
                boost += 0.2
            elif target_character is None and truth.culprit is None:
                boost += 0.1  # Investigating "no crime" theories

            state.truth_weights[truth_id] = state.truth_weights.get(truth_id, 1.0) + boost

    def try_lock(self, session_id: str, round_num: int, force: bool = False) -> Optional[str]:
        """
        Try to lock the truth. Returns the locked truth ID or None.

        Lock conditions:
        - Round >= 8 AND one truth has 2x the weight of others → lock
        - Round >= 12 → force lock (pick highest weight)
        - force=True → immediate lock
        """
        state = self.get_state(session_id)
        if state.locked_truth_id:
            return state.locked_truth_id

        weights = state.truth_weights
        if not weights:
            return None

        sorted_truths = sorted(weights.items(), key=lambda x: -x[1])
        top_id, top_weight = sorted_truths[0]
        second_weight = sorted_truths[1][1] if len(sorted_truths) > 1 else 0

        should_lock = False

        if force:
            should_lock = True
        elif round_num >= 12:
            # Force lock by round 12
            should_lock = True
        elif round_num >= 8 and top_weight >= second_weight * 1.5:
            # Clear leader by round 8
            should_lock = True

        if should_lock:
            # Add some randomness to prevent determinism
            if not force and round_num < 12 and random.random() < 0.3:
                # 30% chance to pick second-highest for surprise
                if len(sorted_truths) > 1 and second_weight > 0.5:
                    top_id = sorted_truths[1][0]

            state.locked_truth_id = top_id
            state.lock_round = round_num
            state.just_locked = True
            return top_id

        return None

    def get_clue_interpretation(
        self, session_id: str, clue_id: str
    ) -> Optional[str]:
        """Get the interpretation of a clue based on the locked truth."""
        truth = self.get_locked_truth(session_id)
        if truth:
            return truth.clue_interpretations.get(clue_id)
        return None

    def get_npc_secret(self, session_id: str, character_id: str) -> Optional[str]:
        """Get the NPC's real secret based on the locked truth."""
        truth = self.get_locked_truth(session_id)
        if truth:
            return truth.npc_secrets.get(character_id)
        return None

    def get_ending(self, session_id: str, quality: str) -> str:
        """Get the ending text for the locked truth."""
        truth = self.get_locked_truth(session_id)
        if not truth:
            return "真相仍然笼罩在迷雾之中。"
        if quality == "perfect":
            return truth.perfect_ending
        return truth.good_ending

    def get_weight_delta(self, session_id: str) -> dict:
        """Get weight change info for truth_hint events."""
        state = self.get_state(session_id)
        if not state.previous_weights:
            return {"just_locked": False, "top_weight_delta": 0.0}

        # Calculate the maximum single-truth weight change
        max_delta = 0.0
        for tid, current_w in state.truth_weights.items():
            prev_w = state.previous_weights.get(tid, current_w)
            delta = abs(current_w - prev_w)
            if delta > max_delta:
                max_delta = delta

        return {
            "just_locked": state.just_locked,
            "top_weight_delta": max_delta,
        }

    def get_debug_info(self, session_id: str) -> dict:
        """For debugging: show all truth weights."""
        state = self.get_state(session_id)
        return {
            "locked": state.locked_truth_id,
            "lock_round": state.lock_round,
            "weights": dict(state.truth_weights),
        }

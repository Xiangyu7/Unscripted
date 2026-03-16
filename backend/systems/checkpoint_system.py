"""
Checkpoint System — Reasoning checkpoints at rounds 6 and 12.

Pure rules, zero LLM calls. Forces the player to commit to a hypothesis
mid-game, creating a sense of stakes and intellectual engagement.
"""

from typing import Dict, List, Optional, Set

from schemas.game_state import CheckpointState, VoteOption


# ── Checkpoint trigger rounds ──
CHECKPOINT_ROUNDS = [6, 12]

# ── Pre-written hypothesis options ──
_ROUND_6_OPTIONS = [
    VoteOption(id="self_staged", label="顾言是自愿消失的", kind="hypothesis"),
    VoteOption(id="kidnapped", label="有人绑架了顾言", kind="hypothesis"),
    VoteOption(id="estate", label="这和遗产纠纷有关", kind="hypothesis"),
    VoteOption(id="unsure", label="还不确定", kind="hypothesis"),
]

_ROUND_12_BASE_OPTIONS = [
    VoteOption(id="linlan_did_it", label="林岚策划了失踪", kind="hypothesis"),
    VoteOption(id="zhoumu_did_it", label="周牧失手伤了顾言", kind="hypothesis"),
    VoteOption(id="songzhi_did_it", label="宋知微操纵了一切", kind="hypothesis"),
    VoteOption(id="self_staged_12", label="顾言自导自演", kind="hypothesis"),
]

# Clue-based refinement: if certain clues are discovered, swap in more specific options
_CLUE_REFINED_OPTIONS: Dict[str, VoteOption] = {
    "linlan_phone_log": VoteOption(
        id="linlan_phone", label="林岚用顾言手机伪造消息", kind="hypothesis"
    ),
    "cellar_provisions": VoteOption(
        id="cellar_hide", label="有人把顾言藏在酒窖", kind="hypothesis"
    ),
    "staged_evidence": VoteOption(
        id="staged", label="书房现场是伪造的", kind="hypothesis"
    ),
}

# ── Feedback for each choice ──
_ROUND_6_FEEDBACK: Dict[str, str] = {
    "self_staged": "有趣的假设。如果顾言是自愿消失的，那他一定有帮手……注意观察谁在暗中配合。",
    "kidnapped": "这意味着凶手就在我们中间。仔细观察每个人的不在场证明。",
    "estate": "金钱是永恒的动机。看看谁在遗产问题上最紧张。",
    "unsure": "谨慎也是一种智慧。继续收集线索，真相自然会浮出水面。",
}

_ROUND_12_FEEDBACK: Dict[str, str] = {
    "linlan_did_it": "林岚确实有动机——如果顾言修改遗嘱，她的利益将受到直接损害。但还需要关键证据。",
    "zhoumu_did_it": "周牧昨晚的争吵确实异常激烈。如果是失手……他现在一定承受着巨大的压力。",
    "songzhi_did_it": "一个记者恰好出现在犯罪现场？这确实太巧了。调查她的真正目的。",
    "self_staged_12": "如果是自导自演，那顾言现在就在某个地方看着这一切。酒窖的声音……",
    "linlan_phone": "手机通话记录是关键线索。如果林岚在伪造消息，那她一定在掩盖更大的秘密。",
    "cellar_hide": "酒窖的秘密即将揭开。去那里看看——但要小心。",
    "staged": "如果现场是伪造的，那真正的故事发生在别处。重新审视所有证据。",
}

# ── Truth weight adjustments based on checkpoint choices ──
_WEIGHT_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
    "self_staged": {"self_staged": 0.4},
    "kidnapped": {"linlan_coverup": 0.2, "zhoumu_accident": 0.2},
    "estate": {"linlan_coverup": 0.3, "zhoumu_accident": 0.2},
    "unsure": {},  # No weight change
    "linlan_did_it": {"linlan_coverup": 0.5},
    "zhoumu_did_it": {"zhoumu_accident": 0.5},
    "songzhi_did_it": {"songzhi_setup": 0.5},
    "self_staged_12": {"self_staged": 0.5},
    "linlan_phone": {"linlan_coverup": 0.4},
    "cellar_hide": {"self_staged": 0.2, "linlan_coverup": 0.2, "zhoumu_accident": 0.2},
    "staged": {"self_staged": 0.3, "linlan_coverup": 0.2},
}


class CheckpointSystem:
    """Pure-rule system for reasoning checkpoints."""

    def should_trigger(
        self, round_num: int, checkpoints_completed: List[int]
    ) -> bool:
        """Check if a checkpoint should trigger this round."""
        return round_num in CHECKPOINT_ROUNDS and round_num not in checkpoints_completed

    def get_checkpoint(
        self, round_num: int, discovered_clue_ids: List[str]
    ) -> CheckpointState:
        """Build the checkpoint state with options for the given round."""
        if round_num <= 6:
            prompt = "调查进行到一半——你现在的假说是什么？"
            options = list(_ROUND_6_OPTIONS)
        else:
            prompt = "距离真相越来越近了。根据目前掌握的线索，你认为……"
            options = list(_ROUND_12_BASE_OPTIONS)
            # Refine options based on discovered clues
            discovered_set: Set[str] = set(discovered_clue_ids)
            for clue_id, refined_opt in _CLUE_REFINED_OPTIONS.items():
                if clue_id in discovered_set:
                    # Replace the last generic option with a clue-specific one
                    if len(options) > 3:
                        options[-1] = refined_opt
                        break

        return CheckpointState(
            status="awaiting_hypothesis",
            checkpoint_round=round_num,
            prompt=prompt,
            options=options,
        )

    def resolve(
        self, checkpoint_state: CheckpointState, choice_id: str
    ) -> tuple:
        """
        Resolve a checkpoint choice.
        Returns (feedback_text, weight_adjustments dict).
        """
        round_num = checkpoint_state.checkpoint_round
        feedback_map = _ROUND_6_FEEDBACK if round_num <= 6 else _ROUND_12_FEEDBACK
        feedback = feedback_map.get(choice_id, "你的推理正在影响事件的走向……")
        weight_adj = _WEIGHT_ADJUSTMENTS.get(choice_id, {})
        return feedback, weight_adj

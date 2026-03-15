"""
Lie Detector System — catches NPCs contradicting themselves.

When a player discovers a clue that contradicts what an NPC previously said,
triggers a dramatic "caught in a lie" moment. This is the core "gotcha!" feeling
that makes detective games addictive.
"""

from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel


class LieRecord(BaseModel):
    """A recorded NPC claim that can be contradicted by evidence."""
    round: int
    character_id: str
    character_name: str
    claim: str               # What the NPC said
    topic: str               # What topic it relates to
    contradicted_by: Optional[str] = None  # Clue ID that contradicts this


class CaughtLie(BaseModel):
    """A detected contradiction between NPC claim and discovered evidence."""
    character_id: str
    character_name: str
    original_claim: str       # What they said
    claim_round: int          # When they said it
    contradicting_clue: str   # Clue text that proves the lie
    confrontation_text: str   # Dramatic reveal text (Chinese)


# Pre-defined lies that NPCs will tell, matched to clues that expose them
NPC_LIES: Dict[str, List[dict]] = {
    "linlan": [
        {
            "claim": "我不知道顾言去了哪里",
            "topic": "顾言下落",
            "exposed_by": ["linlan_phone_log"],
            "confrontation": (
                "「你说你不知道顾言在哪？」你亮出手机截图，"
                "「可是他在失踪之后还给你发了消息：'按计划行动'。你怎么解释？」"
                "\n林岚的脸色一瞬间变得煞白。"
            ),
        },
        {
            "claim": "我没有动过书房里的任何东西",
            "topic": "书房",
            "exposed_by": ["study_scratches", "staged_evidence"],
            "confrontation": (
                "「你说你没进过书房？」你指着门把手上的划痕，"
                "「这些痕迹是从里面刮出来的。有人从书房里急着出去——那个人是你吗？」"
                "\n林岚的嘴唇紧抿，但手指不自觉地攥紧了衣角。"
            ),
        },
        {
            "claim": "我和顾言只是普通的雇佣关系",
            "topic": "与顾言关系",
            "exposed_by": ["will_draft"],
            "confrontation": (
                "「普通的雇佣关系？」你把遗嘱草稿放在桌上，"
                "「上面写着'看看他们的反应'。这不像是老板写给普通员工的备注。你们之间有什么秘密交易？」"
                "\n林岚低下了头，沉默了很长时间。"
            ),
        },
    ],
    "zhoumu": [
        {
            "claim": "我昨晚一直在宴会厅没出去",
            "topic": "昨晚行踪",
            "exposed_by": ["wine_cellar_footprint"],
            "confrontation": (
                "「你说你一直在宴会厅？」你指着酒窖入口的脚印，"
                "「可酒窖门口有一双新鲜脚印——尺码跟你的鞋一模一样。你去过酒窖，对吧？」"
                "\n周牧端酒杯的手突然僵住了。"
            ),
        },
        {
            "claim": "我和顾言关系很好，没有任何矛盾",
            "topic": "与顾言关系",
            "exposed_by": ["will_draft", "torn_letter"],
            "confrontation": (
                "「没有矛盾？」你抖开遗嘱草稿，"
                "「顾言打算把遗产全捐了。你——他最好的朋友——一分钱都拿不到。这还叫没矛盾？」"
                "\n周牧的笑容终于绷不住了：「那又怎么样？！我……我只是说了几句气话！」"
            ),
        },
        {
            "claim": "我什么都没听到，什么都没看到",
            "topic": "酒窖",
            "exposed_by": ["cellar_sound"],
            "confrontation": (
                "「什么都没听到？」你盯着他的眼睛，"
                "「酒窖深处有呼吸声。有人活着藏在那里。你之前说听到过酒窖方向的动静——你到底听到了什么？」"
                "\n周牧的额头开始冒汗。"
            ),
        },
    ],
    "songzhi": [
        {
            "claim": "我只是碰巧被邀请参加晚宴",
            "topic": "出现原因",
            "exposed_by": ["anonymous_tip"],
            "confrontation": (
                "「碰巧？」你拿出垃圾桶里的纸条，"
                "「这上面写着'今晚注意遗产'。笔迹很工整——像是提前准备好的。你是不是早就知道今晚会出事？」"
                "\n宋知微的眼神闪了一下，但很快恢复了镇定。"
            ),
        },
        {
            "claim": "我从来没去过书房",
            "topic": "书房",
            "exposed_by": ["study_scratches"],
            "confrontation": (
                "「你说你没去过书房？可有人在晚宴开始前看到你往书房方向走。"
                "而且书房门把手上有新鲜划痕——你确定不是你留下的？」"
                "\n宋知微嘴角微扬：「你的推理很有趣。但有趣不等于正确。」"
            ),
        },
    ],
}


class LieDetector:
    """Tracks NPC claims and detects contradictions with discovered evidence."""

    def __init__(self):
        self._records: Dict[str, List[LieRecord]] = {}  # session_id → records
        self._triggered: Dict[str, set] = {}  # session_id → set of triggered lie keys

    def _key(self, char_id: str, topic: str) -> str:
        return f"{char_id}:{topic}"

    def record_npc_response(
        self,
        session_id: str,
        round_num: int,
        character_id: str,
        character_name: str,
        response_text: str,
    ):
        """Record an NPC's response and check if it contains trackable claims."""
        if session_id not in self._records:
            self._records[session_id] = []

        lies = NPC_LIES.get(character_id, [])
        for lie_def in lies:
            # Check if the NPC's response touches this topic
            if any(kw in response_text for kw in lie_def["topic"].split()):
                self._records[session_id].append(LieRecord(
                    round=round_num,
                    character_id=character_id,
                    character_name=character_name,
                    claim=lie_def["claim"],
                    topic=lie_def["topic"],
                ))

    def check_for_contradictions(
        self,
        session_id: str,
        newly_discovered_clue_ids: List[str],
    ) -> List[CaughtLie]:
        """
        Check if any newly discovered clues contradict previous NPC claims.
        Returns dramatic confrontation moments.
        """
        if session_id not in self._triggered:
            self._triggered[session_id] = set()

        caught: List[CaughtLie] = []

        for char_id, lie_defs in NPC_LIES.items():
            for lie_def in lie_defs:
                key = self._key(char_id, lie_def["topic"])
                if key in self._triggered[session_id]:
                    continue  # Already triggered this one

                # Check if any of the exposing clues were just discovered
                for clue_id in lie_def["exposed_by"]:
                    if clue_id in newly_discovered_clue_ids:
                        self._triggered[session_id].add(key)
                        char_name = {
                            "linlan": "林岚",
                            "zhoumu": "周牧",
                            "songzhi": "宋知微",
                        }.get(char_id, char_id)

                        caught.append(CaughtLie(
                            character_id=char_id,
                            character_name=char_name,
                            original_claim=lie_def["claim"],
                            claim_round=0,  # Will be filled from records if available
                            contradicting_clue=clue_id,
                            confrontation_text=lie_def["confrontation"],
                        ))
                        break  # Only trigger once per lie

        return caught

    def get_available_confrontations(
        self,
        session_id: str,
        discovered_clue_ids: List[str],
    ) -> List[dict]:
        """
        Get confrontation options the player can use.
        Returns list of {character_id, character_name, prompt_text} for UI buttons.
        """
        if session_id not in self._triggered:
            self._triggered[session_id] = set()

        options = []
        for char_id, lie_defs in NPC_LIES.items():
            for lie_def in lie_defs:
                key = self._key(char_id, lie_def["topic"])
                if key in self._triggered[session_id]:
                    continue
                # Check if player has the exposing evidence
                has_evidence = any(
                    cid in discovered_clue_ids for cid in lie_def["exposed_by"]
                )
                if has_evidence:
                    char_name = {
                        "linlan": "林岚", "zhoumu": "周牧", "songzhi": "宋知微",
                    }.get(char_id, char_id)
                    options.append({
                        "character_id": char_id,
                        "character_name": char_name,
                        "prompt": f"用证据质问{char_name}：{lie_def['topic']}",
                    })
        return options

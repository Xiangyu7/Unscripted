"""
NPC Secret Conversation System

While the player is busy in one location, NPCs in OTHER locations
may have private conversations. The player doesn't see the dialogue,
but sees the CONSEQUENCES:
  - Changed attitudes
  - Physical evidence (cigarette butts, moved objects)
  - Behavioral shifts
  - Inconsistencies to catch

This creates the feeling that NPCs have their own lives and agendas.
"""

import random
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel


class SecretConversation(BaseModel):
    """A conversation that happened between NPCs while the player wasn't watching."""
    participants: List[str]        # character IDs
    location: str                  # Where it happened
    topic: str                     # What they discussed
    summary: str                   # Brief description (for internal tracking)

    # What the player can discover
    evidence: str                  # Physical evidence left behind
    evidence_location: str         # Where the evidence is

    # Effects on NPCs
    psych_effects: Dict[str, dict] = {}  # char_id → {composure: -0.05, ...}
    alliance_change: Optional[float] = None  # Change to their alliance strength
    behavioral_tells: Dict[str, str] = {}    # char_id → observable behavior change


# ═══════════════════════════════════════════════════════════════
# Pre-written secret conversations
# ═══════════════════════════════════════════════════════════════

SECRET_CONVERSATIONS: List[dict] = [
    # LinLan + ZhouMu: form a pact
    {
        "id": "pact_will",
        "participants": ["linlan", "zhoumu"],
        "preferred_location": "花园",
        "min_tension": 30,
        "min_round": 4,
        "topic": "遗嘱",
        "summary": "林岚暗示周牧：如果他不追究遗嘱的事，她可以帮他隐瞒昨晚的争吵",
        "evidence": "花园石凳旁有两组脚印，还有一个被掐灭的烟头——周牧的牌子",
        "evidence_location": "花园",
        "psych_effects": {
            "linlan": {"composure": -0.03, "fear": 0.05},
            "zhoumu": {"composure": -0.05, "anger": -0.1, "fear": 0.03},
        },
        "alliance_change": 0.3,
        "behavioral_tells": {
            "linlan": "林岚说话时不再针对周牧——她之前一直在暗示他很可疑，但突然停了",
            "zhoumu": "周牧不再紧张地喝酒了——像是卸下了什么包袱。但他避免和你对视",
        },
    },
    # LinLan + SongZhi: information exchange
    {
        "id": "info_trade",
        "participants": ["linlan", "songzhi"],
        "preferred_location": "走廊",
        "min_tension": 35,
        "min_round": 5,
        "topic": "匿名信",
        "summary": "宋知微用匿名信的信息试探林岚，林岚意识到有人在幕后操纵",
        "evidence": "走廊壁灯下有一张被揉皱又展平的纸——上面是宋知微的笔迹，记录着某种时间线",
        "evidence_location": "走廊",
        "psych_effects": {
            "linlan": {"fear": 0.08, "composure": -0.05},
            "songzhi": {"composure": 0.03, "fear": -0.02},
        },
        "alliance_change": -0.1,
        "behavioral_tells": {
            "linlan": "林岚比之前更警惕了——她开始频繁看手机，像是在确认什么",
            "songzhi": "宋知微的笔记本上多了好几页新内容，她推眼镜的频率明显加快了",
        },
    },
    # ZhouMu + SongZhi: reluctant confession
    {
        "id": "drunk_confession",
        "participants": ["zhoumu", "songzhi"],
        "preferred_location": "宴会厅",
        "min_tension": 40,
        "min_round": 6,
        "topic": "争吵",
        "summary": "周牧喝多了，不小心跟宋知微透露了昨晚争吵的部分内容",
        "evidence": "吧台上多了三个空酒杯——周牧喝了很多。旁边有一张餐巾纸，上面有宋知微快速记的几个关键词",
        "evidence_location": "宴会厅",
        "psych_effects": {
            "zhoumu": {"composure": -0.1, "desperation": 0.05, "anger": 0.03},
            "songzhi": {"composure": 0.05},
        },
        "alliance_change": 0.1,
        "behavioral_tells": {
            "zhoumu": "周牧看起来很后悔——他在咬嘴唇，不停地搓手。他喝得比之前更多了",
            "songzhi": "宋知微有一种压抑不住的兴奋——她发现了重要的东西，但在努力装作若无其事",
        },
    },
    # LinLan alone: secret phone call
    {
        "id": "secret_call",
        "participants": ["linlan"],
        "preferred_location": "走廊",
        "min_tension": 50,
        "min_round": 8,
        "topic": "顾言",
        "summary": "林岚躲在走廊尽头打了一个神秘的电话",
        "evidence": "走廊尽头的窗台上有林岚的口红印——她靠在那里打过电话。手机信号记录显示8:47有一通时长2分钟的通话",
        "evidence_location": "走廊",
        "psych_effects": {
            "linlan": {"fear": 0.1, "composure": -0.08},
        },
        "alliance_change": None,
        "behavioral_tells": {
            "linlan": "林岚把手机收得更紧了——之前她只是偶尔看，现在她把它攥在手心里不放",
        },
    },
    # ZhouMu alone: tries the wine cellar door
    {
        "id": "zhoumu_cellar_attempt",
        "participants": ["zhoumu"],
        "preferred_location": "酒窖",
        "min_tension": 45,
        "min_round": 7,
        "topic": "酒窖",
        "summary": "周牧偷偷去了酒窖，试图打开深处的那扇门，但失败了",
        "evidence": "酒窖深处的木门上有新的抓痕——有人试图用力推开它。门前的灰尘被踩乱了",
        "evidence_location": "酒窖",
        "psych_effects": {
            "zhoumu": {"fear": 0.12, "desperation": 0.08, "composure": -0.1},
        },
        "alliance_change": None,
        "behavioral_tells": {
            "zhoumu": "周牧的指甲缝里有木屑——他试图扣开什么东西。他回来时脸色苍白，额头有汗",
        },
    },
]


class SecretConversationSystem:
    """Manages NPC private interactions that happen off-screen."""

    def __init__(self):
        self._triggered: Dict[str, set] = {}  # session → triggered conversation IDs
        self._pending_evidence: Dict[str, List[dict]] = {}  # session → evidence waiting to be discovered
        self._pending_tells: Dict[str, Dict[str, str]] = {}  # session → {char_id: tell text}

    def simulate(
        self,
        session_id: str,
        player_location: str,
        npc_locations: Dict[str, str],
        tension: int,
        round_num: int,
    ) -> Optional[SecretConversation]:
        """
        Check if any secret conversation should happen this turn.
        Only triggers if the player is NOT at the conversation location.
        Returns the conversation (for internal effects) or None.
        """
        if session_id not in self._triggered:
            self._triggered[session_id] = set()

        # 25% chance per turn
        if random.random() > 0.25:
            return None

        for conv_def in SECRET_CONVERSATIONS:
            if conv_def["id"] in self._triggered[session_id]:
                continue

            if tension < conv_def["min_tension"]:
                continue
            if round_num < conv_def["min_round"]:
                continue

            # Check if participants are NOT where the player is
            participants = conv_def["participants"]
            loc = conv_def["preferred_location"]

            if loc == player_location:
                continue  # Player would see this — skip

            # Check if participants could plausibly be at this location
            # (we don't strictly enforce location, just that player isn't there)
            all_present = all(
                npc_locations.get(pid, "") != player_location
                for pid in participants
            )
            if not all_present:
                continue

            # Trigger this conversation
            self._triggered[session_id].add(conv_def["id"])

            # Store evidence for later discovery
            if session_id not in self._pending_evidence:
                self._pending_evidence[session_id] = []
            self._pending_evidence[session_id].append({
                "text": conv_def["evidence"],
                "location": conv_def["evidence_location"],
            })

            # Store behavioral tells
            if session_id not in self._pending_tells:
                self._pending_tells[session_id] = {}
            for char_id, tell in conv_def.get("behavioral_tells", {}).items():
                self._pending_tells[session_id][char_id] = tell

            return SecretConversation(
                participants=participants,
                location=loc,
                topic=conv_def["topic"],
                summary=conv_def["summary"],
                evidence=conv_def["evidence"],
                evidence_location=conv_def["evidence_location"],
                psych_effects=conv_def.get("psych_effects", {}),
                alliance_change=conv_def.get("alliance_change"),
                behavioral_tells=conv_def.get("behavioral_tells", {}),
            )

        return None

    def get_evidence_at_location(
        self, session_id: str, location: str
    ) -> List[str]:
        """Get evidence from secret conversations at a location. Consumed on read."""
        if session_id not in self._pending_evidence:
            return []
        found = []
        remaining = []
        for ev in self._pending_evidence[session_id]:
            if ev["location"] == location:
                found.append(ev["text"])
            else:
                remaining.append(ev)
        self._pending_evidence[session_id] = remaining
        return found

    def get_behavioral_tell(
        self, session_id: str, character_id: str
    ) -> Optional[str]:
        """Get behavioral change for a character (consumed on read)."""
        tells = self._pending_tells.get(session_id, {})
        return tells.pop(character_id, None)

    def get_tell_context_for_prompt(
        self, session_id: str, character_id: str
    ) -> str:
        """Get context to inject into character prompt about their behavioral change."""
        tell = self._pending_tells.get(session_id, {}).get(character_id)
        if not tell:
            return ""
        return (
            f"\n【最近发生的事（侦探不知道）】\n"
            f"你刚才做了一些事情，现在你的行为有细微变化：\n"
            f"{tell}\n"
            f"在对话中自然地表现出这些变化，但不要直接说出原因。"
        )

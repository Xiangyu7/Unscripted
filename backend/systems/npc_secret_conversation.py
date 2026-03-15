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

For the first ~20 rounds, pre-written conversations are used (zero LLM tokens).
Once pre-written scripts are exhausted, an LLM generates dynamic conversations
so NPC interactions never run out.
"""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from pydantic import BaseModel

if TYPE_CHECKING:
    from config import Config


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


DYNAMIC_CONV_SYSTEM_PROMPT = """\
你是一个推理游戏的NPC互动模拟器。两个角色在玩家不知情的情况下进行了一段简短对话。

游戏背景：顾家老宅，主人顾言在晚宴中失踪。三位嫌疑人各有秘密。
真相：顾言自导自演失踪，试探身边人。

角色设定：
- 林岚（秘书）：知道顾言的计划，冷静但紧张
- 周牧（发小）：昨晚与顾言争吵过，在隐瞒什么
- 宋知微（记者）：收到过匿名线报，在暗中调查

你必须返回JSON：
{
  "dialogue_summary": "一句话总结对话内容",
  "evidence": "对话后留下的物理痕迹（50字以内）",
  "evidence_location": "痕迹所在地点",
  "psych_effects": {"角色ID": {"composure": 变化值, "fear": 变化值}},
  "behavioral_tells": {"角色ID": "行为变化描述"}
}
"""

# Character ID → display name mapping for prompt construction
_CHAR_NAMES: Dict[str, str] = {
    "linlan": "林岚",
    "zhoumu": "周牧",
    "songzhi": "宋知微",
}


class SecretConversationSystem:
    """Manages NPC private interactions that happen off-screen."""

    def __init__(self):
        self._triggered: Dict[str, set] = {}  # session → triggered conversation IDs
        self._pending_evidence: Dict[str, List[dict]] = {}  # session → evidence waiting to be discovered
        self._pending_tells: Dict[str, Dict[str, str]] = {}  # session → {char_id: tell text}
        self._llm_client = None  # lazily initialised on first dynamic call
        self._llm_config: Optional[Config] = None

    # ------------------------------------------------------------------
    # LLM client (lazy init, same pattern as DMAgent)
    # ------------------------------------------------------------------

    def _ensure_llm_client(self, config: Config):
        """Initialise the LLM client once, re-use on subsequent calls."""
        if self._llm_client is not None:
            return

        from config import LLMProvider

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI
            self._llm_client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
        elif config.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self._llm_client = anthropic.AsyncAnthropic(api_key=config.anthropic_key)

        self._llm_config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(
        self,
        session_id: str,
        player_location: str,
        npc_locations: Dict[str, str],
        tension: int,
        round_num: int,
        *,
        config: Optional[Config] = None,
        character_states: Optional[Dict[str, dict]] = None,
        discovered_clue_texts: Optional[List[str]] = None,
    ) -> Optional[SecretConversation]:
        """
        Check if any secret conversation should happen this turn.
        Only triggers if the player is NOT at the conversation location.
        Returns the conversation (for internal effects) or None.

        For the first ~20 rounds the pre-written scripts are used.  When all
        pre-written scripts have been triggered (or none match the current
        conditions) and an LLM provider is available, this returns a coroutine
        placeholder — callers must ``await simulate_dynamic(...)`` separately.

        .. note::
            This method remains synchronous for backward-compatibility.
            If a dynamic conversation is needed, it returns ``None`` here and
            the caller should follow up with :meth:`simulate_dynamic`.
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

        # No pre-written conversation matched.  Fall through to None so the
        # caller may optionally invoke simulate_dynamic() if an LLM is available.
        return None

    # ------------------------------------------------------------------
    # LLM-powered dynamic conversation
    # ------------------------------------------------------------------

    async def simulate_dynamic(
        self,
        session_id: str,
        player_location: str,
        npc_locations: Dict[str, str],
        tension: int,
        round_num: int,
        config: "Config",
        character_states: Dict[str, dict],
        discovered_clue_texts: List[str],
    ) -> Optional[SecretConversation]:
        """Generate an NPC secret conversation via a single LLM call.

        Called when pre-written scripts are exhausted or none match.

        Args:
            session_id: Current game session identifier.
            player_location: Where the player currently is.
            npc_locations: ``{character_id: location}`` for every NPC.
            tension: Current tension value (0-100).
            round_num: Current round number.
            config: Application :class:`Config` (carries LLM provider info).
            character_states: ``{character_id: {composure, fear, ...}}`` psych states.
            discovered_clue_texts: List of clue text strings discovered so far.

        Returns:
            A :class:`SecretConversation` or ``None`` if the LLM call fails
            or no eligible NPC pair is found.
        """
        from config import LLMProvider

        if config.provider == LLMProvider.FALLBACK:
            return None

        # --- Pick two NPCs that are NOT at the player's location ----------
        eligible = [
            cid for cid, loc in npc_locations.items()
            if loc != player_location
        ]
        if len(eligible) < 2:
            # Need at least two characters to have a conversation
            if len(eligible) == 1:
                participants = eligible  # solo action (like existing pre-written ones)
            else:
                return None
        else:
            participants = random.sample(eligible, 2)

        # Pick a plausible location (any location that is NOT the player's)
        all_locations = set(npc_locations.values()) - {player_location}
        location = random.choice(list(all_locations)) if all_locations else "走廊"

        # --- Build user prompt -------------------------------------------
        char_names = [_CHAR_NAMES.get(cid, cid) for cid in participants]
        psych_lines = []
        for cid in participants:
            state = character_states.get(cid, {})
            if state:
                parts = [f"{k}={v}" for k, v in state.items()]
                psych_lines.append(f"  {_CHAR_NAMES.get(cid, cid)}: {', '.join(parts)}")
            else:
                psych_lines.append(f"  {_CHAR_NAMES.get(cid, cid)}: 无详细状态")

        clue_text = "、".join(discovered_clue_texts[:10]) if discovered_clue_texts else "暂无"

        user_prompt = (
            f"当前回合：{round_num}，紧张度：{tension}/100\n"
            f"地点：{location}（玩家不在此处）\n"
            f"对话角色：{'、'.join(char_names)}\n"
            f"\n角色心理状态：\n" + "\n".join(psych_lines) + "\n"
            f"\n玩家已发现的线索：{clue_text}\n"
            f"\n请生成这两个角色此刻的一段秘密互动。"
        )

        # --- LLM call ----------------------------------------------------
        try:
            self._ensure_llm_client(config)
            raw = await self._call_llm(user_prompt, config)
        except Exception as exc:
            print(f"[SecretConversation] LLM call failed: {exc}")
            return None

        # --- Parse response ----------------------------------------------
        try:
            parsed = self._parse_llm_response(raw)
        except Exception as exc:
            print(f"[SecretConversation] Failed to parse LLM response: {exc}")
            return None

        # --- Build SecretConversation from parsed JSON --------------------
        evidence = parsed.get("evidence", "")
        evidence_location = parsed.get("evidence_location", location)
        psych_effects = parsed.get("psych_effects", {})
        behavioral_tells = parsed.get("behavioral_tells", {})
        summary = parsed.get("dialogue_summary", "NPC之间发生了一段对话")

        # Store evidence for later discovery
        if evidence:
            if session_id not in self._pending_evidence:
                self._pending_evidence[session_id] = []
            self._pending_evidence[session_id].append({
                "text": evidence,
                "location": evidence_location,
            })

        # Store behavioral tells
        if behavioral_tells:
            if session_id not in self._pending_tells:
                self._pending_tells[session_id] = {}
            for char_id, tell in behavioral_tells.items():
                self._pending_tells[session_id][char_id] = tell

        return SecretConversation(
            participants=participants,
            location=location,
            topic=summary[:20],
            summary=summary,
            evidence=evidence,
            evidence_location=evidence_location,
            psych_effects=psych_effects,
            behavioral_tells=behavioral_tells,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm(self, user_prompt: str, config: "Config") -> str:
        """Make a single LLM call and return the raw text response."""
        from config import LLMProvider

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            response = await self._llm_client.chat.completions.create(
                model=config.model,
                messages=[
                    {"role": "system", "content": DYNAMIC_CONV_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=600,
            )
            return response.choices[0].message.content

        elif config.provider == LLMProvider.ANTHROPIC:
            response = await self._llm_client.messages.create(
                model=config.model,
                max_tokens=600,
                system=DYNAMIC_CONV_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.8,
            )
            return response.content[0].text

        else:
            raise ValueError(f"Unsupported provider for dynamic conversation: {config.provider}")

    @staticmethod
    def _parse_llm_response(raw: str) -> dict:
        """Parse the LLM JSON response, stripping markdown fences if present."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]
        return json.loads(raw)

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

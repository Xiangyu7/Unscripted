"""
StoryArchitectAgent — manages the macro narrative arc across the entire game session.

Ensures the story follows proper dramatic structure (setup -> rising action -> climax
-> resolution) using a three-act model with adaptive pacing.  Works alongside the
DirectorAgent: the architect decides *what* should happen narratively while the
director decides *how* to present it.

Usage:
    architect = StoryArchitectAgent(config)
    directive = await architect.generate_directive(state_summary)
    # directive.director_note, directive.system_narration, etc.
"""

from __future__ import annotations

import json
import random
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from config import Config, LLMProvider


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NarrativeBeat(BaseModel):
    """A single beat in the narrative arc."""
    act: int                    # 1, 2, or 3
    beat_type: str              # "setup" / "rising" / "crisis" / "climax" / "resolution"
    description: str            # What should happen narratively


class ArchitectDirective(BaseModel):
    """Output of the StoryArchitectAgent — instructions for the current turn."""
    current_act: int
    current_beat: str
    pacing: str                 # "accelerate" / "sustain" / "slow_down" / "climax"
    director_note: str          # Atmospheric note (Chinese, <=50 chars)
    system_narration: str       # Scene description (Chinese, <=80 chars)
    suggested_events: List[str] = Field(default_factory=list)  # Suggested NPC events (Chinese)
    hint_level: str             # "none" / "subtle" / "moderate" / "strong"
    should_reveal_clue: bool    # Whether to help player discover clues this turn


# ---------------------------------------------------------------------------
# Pre-written directive pools (Chinese)
# ---------------------------------------------------------------------------

# ── Director notes (atmospheric hints for the player) ──

ACT1_NOTES = [
    "夜色渐深，宴会厅里的气氛有些微妙。",
    "你注意到有人在暗处交换了一个意味深长的眼神。",
    "顾家老宅在夜幕下显得格外安静，但安静得有些不自然。",
    "每个人都带着得体的微笑，但笑容背后藏着什么？",
    "趁着气氛还算轻松，不妨四处走走看看。",
    "初来乍到，先了解每个人的身份和关系或许是个好主意。",
    "这场晚宴的主人迟迟没有出现，大家似乎都在回避这个话题。",
    "你隐约感觉到，在场的每个人都有自己不愿提及的事情。",
]

ACT2_NOTES = [
    "事情开始变得不简单了，线索之间似乎有某种联系。",
    "空气中弥漫着紧张的气息，有人在说谎。",
    "你发现的这些线索正在拼凑出一幅令人不安的画面。",
    "有人的表情出现了裂痕——他们的伪装开始维持不住了。",
    "信任和猜疑交织在一起，真相的轮廓正在浮现。",
    "越深入调查，你越觉得这件事远比表面看到的复杂。",
    "每个人都有动机，每个人都有秘密——但谁在撒最大的谎？",
    "线索指向了一个令人震惊的方向，但你还需要更多证据。",
    "事情正在朝着无法控制的方向发展，你感觉时间在流逝。",
    "暗流涌动，在场的人之间的关系远比你想象的要复杂。",
]

ACT2_CRISIS_NOTES = [
    "气氛已经到了临界点，任何一句话都可能成为导火索。",
    "有人开始急了——说话的速度和语调都变了。",
    "矛盾集中爆发的时刻就要到了。",
    "你察觉到有人在暗中做出了某个决定。",
    "空气仿佛凝固了，所有人都在等待那个打破沉默的瞬间。",
]

ACT3_NOTES = [
    "真相就在眼前，所有的谎言都开始崩塌。",
    "今夜注定不会平静地结束。",
    "最后的迷雾正在散去，所有的碎片即将归位。",
    "在场的每个人都知道——伪装已经没有意义了。",
    "决定性的时刻到了，你必须做出判断。",
    "所有的线索都指向了一个惊人的真相。",
    "谜底即将揭晓——但你准备好面对真相了吗？",
    "一切都在朝着最终的对决收束。",
]

# ── System narrations (atmospheric scene descriptions) ──

ACT1_NARRATIONS = [
    "老宅的壁灯散发着温暖的光芒，古旧的家具上覆盖着精致的刺绣桌布。一切看起来很正常，但又处处透着一股说不出的违和感。",
    "窗外飘来淡淡的桂花香，客厅里的老式留声机放着轻柔的爵士乐。晚宴的氛围似乎很平和——至少表面如此。",
    "走廊尽头的那幅全家福映入眼帘，照片里顾言笑得很灿烂。但此刻，这位主人却不见踪影。",
    "烛光在水晶杯中跳动，映照出每个人若有所思的面容。今夜的风格外清冷。",
    "老宅的每个角落都弥漫着时光的气息，厚重的木地板在脚下轻轻作响，仿佛在低声诉说着什么。",
    "壁炉里的火焰忽明忽暗，在墙壁上投下摇曳的影子。窗外传来虫鸣声，为这个寂静的夜晚增添了几分生气。",
]

ACT2_NARRATIONS = [
    "老宅的灯光似乎暗了几分，走廊里的影子拉得更长了。有什么东西正在改变。",
    "远处隐隐传来雷声，暴风雨正在逼近。屋内的气氛也随之变得压抑起来。",
    "壁炉里的火焰猛地跳动了一下，有人不自觉地打了个寒颤。角落里的老钟敲响了沉闷的钟声。",
    "一阵穿堂风吹灭了走廊上的两盏壁灯，黑暗中有人倒吸了一口凉气。",
    "不知谁碰翻了桌上的酒杯，暗红色的液体在白色桌布上缓缓洇开，像是某种不祥的预兆。",
    "窗外的月亮被乌云遮住了，整个老宅陷入了一种沉闷的昏暗之中。有人在角落里窃窃私语。",
    "老宅深处传来一声闷响，所有人都下意识地停下了手中的动作，侧耳倾听。",
]

ACT2_CRISIS_NARRATIONS = [
    "闪电劈过夜空，将所有人的面容照得惨白。在那一瞬间，你看到了某人眼中一闪而过的恐惧。",
    "整栋老宅都在风雨中摇晃，灯光闪烁不定。一种末日将至的压迫感笼罩着在场的每一个人。",
    "有人猛地站了起来，椅子在地板上发出刺耳的声响，打破了令人窒息的沉默。",
    "暴风雨终于到了——雨点重重砸在窗户上，伴随着远处滚滚的雷声，一切都在走向临界。",
]

ACT3_NARRATIONS = [
    "暴风雨达到了最猛烈的程度，老宅在风雨中嘎吱作响。闪电的白光将每个人的表情都照得无处遁形。",
    "所有的烛光都在剧烈摇曳，仿佛连光明本身都在为即将揭晓的真相而颤抖。",
    "时间仿佛凝固了——在这个决定性的瞬间，所有人的呼吸都变得清晰可闻。",
    "老宅的钟敲了午夜的最后一声，回音在走廊中久久不散。一切都将在今夜有个了断。",
    "雨渐渐小了，但屋内的紧张气氛反而到达了顶点。黎明之前，必须有一个答案。",
    "空气仿佛被抽干了一般，沉重得几乎让人喘不过气来。所有的伪装都已经支离破碎。",
]

# ── Suggested NPC events per act ──

ACT1_EVENTS = [
    "周牧走向吧台给自己倒了杯酒，顺便向林岚搭了句话。林岚礼貌地回应了，但目光始终没有从手机上移开。",
    "宋知微在客厅里慢慢踱步，时不时端详墙上的照片和摆设，似乎在寻找什么。",
    "林岚接了一个电话，声音压得很低，挂断后表情有一瞬间的凝重，但很快恢复了常态。",
    "周牧和宋知微在沙发区聊了几句，看起来是在闲聊，但两人似乎都在试探对方。",
]

ACT2_EVENTS = [
    "周牧和林岚之间突然起了争执，虽然很快被压下去了，但空气中的火药味明显浓了。",
    "宋知微冷不丁地抛出了一个尖锐的问题，让另外两个人同时变了脸色。",
    "林岚不小心碰掉了桌上的一个相框，照片散落一地——她捡起来的时候手微微发抖。",
    "周牧接到了一条短信，看完后脸色大变，匆匆走向走廊尽头打了个电话。",
    "宋知微翻开了茶几上的一本旧相册，指着其中一张照片若有所思地说了句什么。",
    "林岚和周牧对视了一眼，那个眼神里包含着某种只有他们才懂的信息。",
]

ACT2_CRISIS_EVENTS = [
    "周牧猛地拍了桌子：'够了！我受够了你们之间的秘密！'林岚面无表情地看着他，一言不发。",
    "宋知微突然站起来说：'我觉得我们应该去酒窖看看。'这句话让其他人都愣住了。",
    "林岚的手机突然响了——来电显示是顾言。所有人的目光都聚集到了那部手机上。",
    "周牧在和林岚争论时脱口而出了什么，随即慌忙想要圆回来，但已经晚了。",
]

ACT3_EVENTS = [
    "三个人之间爆发了激烈的对峙，所有的礼貌和伪装都被撕碎了。",
    "宋知微拿出了一份文件，冷冷地说：'我想各位应该解释一下这个。'",
    "周牧突然崩溃了，双手捂着脸说：'我什么都知道……从一开始我就知道。'",
    "林岚长叹一口气，终于开口说出了她一直隐瞒的事情。",
    "有人试图冲向门口离开，但被其他人拦住了。'今晚谁都别想走。'",
]

# ── Stalemate-breaking events (when player is stuck) ──

STALEMATE_BREAKER_EVENTS = [
    "突然，走廊尽头传来了一声巨响——像是什么沉重的东西倒了下来。所有人都朝那个方向看去。",
    "宋知微突然从包里拿出一张照片递给你：'我觉得你应该看看这个。'",
    "周牧像是下定了某种决心，走到你面前低声说：'有些事，我觉得你应该知道。'",
    "林岚的手机屏幕亮了一下，上面的消息内容被你无意中瞥见了——发件人居然是顾言。",
    "一只猫从不知什么地方窜了出来，惊得周牧手中的酒杯掉落。杯子碎了，露出了藏在杯底的一张纸条。",
    "老宅的某处传来了隐约的敲击声——有节奏的，像是某种信号。",
]


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

ARCHITECT_SYSTEM_PROMPT = """你是一个互动悬疑叙事游戏的"故事建筑师"。你的职责是从宏观层面管理整个故事的戏剧结构。

你需要根据当前的游戏状态，给出本轮的叙事指令，确保故事遵循"设置→冲突升级→高潮→解决"的戏剧弧线。

你必须以JSON格式回复，包含以下字段：
- current_act: 当前所处的幕次(1/2/3)
- current_beat: 当前的叙事节拍("setup"/"rising"/"crisis"/"climax"/"resolution")
- pacing: 节奏控制("accelerate"/"sustain"/"slow_down"/"climax")
- director_note: 给玩家的氛围暗示（中文，不超过50字）
- system_narration: 场景氛围描写（中文，不超过80字）
- suggested_events: 建议的NPC互动事件数组（中文，0-2个）
- hint_level: 给玩家的提示等级("none"/"subtle"/"moderate"/"strong")
- should_reveal_clue: 是否应该帮助玩家在本轮发现线索(true/false)

三幕结构参考：
- 第一幕(回合1-6): 设置阶段，让玩家自由探索，低紧张度，温暖氛围，介绍角色个性
- 第二幕(回合7-15): 对抗阶段，线索开始串联，NPC关系出现裂痕，紧张度逐步攀升
- 第三幕(回合16-20): 解决阶段，一切收束，角色承受最大压力，真相浮出水面

自适应节奏规则：
- 如果玩家已经找到很多线索，可以提前推进到下一幕
- 如果玩家卡住了（stuck_turns > 3），应该触发戏剧性事件打破僵局
- 紧张度越高，节奏应该越快，但要留有"释放"的波谷

请始终保持悬疑感，不要直接透露真相。"""


# ---------------------------------------------------------------------------
# Function-calling / tool schemas
# ---------------------------------------------------------------------------

# OpenAI-compatible function schema (used with `tools` parameter)
_ARCHITECT_DIRECTIVE_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "architect_directive",
        "description": "生成本轮的叙事指令，管理故事的戏剧结构和节奏。",
        "parameters": {
            "type": "object",
            "properties": {
                "current_act": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "description": "当前所处的幕次",
                },
                "current_beat": {
                    "type": "string",
                    "enum": ["setup", "rising", "crisis", "climax", "resolution"],
                    "description": "当前的叙事节拍",
                },
                "pacing": {
                    "type": "string",
                    "enum": ["accelerate", "sustain", "slow_down", "climax"],
                    "description": "节奏控制",
                },
                "director_note": {
                    "type": "string",
                    "description": "给玩家的氛围暗示（中文，不超过50字）",
                },
                "system_narration": {
                    "type": "string",
                    "description": "场景氛围描写（中文，不超过80字）",
                },
                "suggested_events": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "建议的NPC互动事件（中文，0-2个）",
                },
                "hint_level": {
                    "type": "string",
                    "enum": ["none", "subtle", "moderate", "strong"],
                    "description": "给玩家的提示等级",
                },
                "should_reveal_clue": {
                    "type": "boolean",
                    "description": "是否应该帮助玩家在本轮发现线索",
                },
            },
            "required": [
                "current_act", "current_beat", "pacing",
                "director_note", "system_narration",
                "hint_level", "should_reveal_clue",
            ],
        },
    },
}

# Anthropic tool schema (used with Anthropic's tool_use format)
_ARCHITECT_DIRECTIVE_TOOL_ANTHROPIC = {
    "name": "architect_directive",
    "description": "生成本轮的叙事指令，管理故事的戏剧结构和节奏。",
    "input_schema": _ARCHITECT_DIRECTIVE_TOOL_OPENAI["function"]["parameters"],
}


# ---------------------------------------------------------------------------
# StoryArchitectAgent
# ---------------------------------------------------------------------------

class StoryArchitectAgent:
    """
    Manages the macro narrative arc for the game session.

    Ensures the story has proper dramatic structure across three acts, with
    adaptive pacing that responds to player progress, tension levels, and
    stuck states.

    The agent can use LLM (OpenAI-compatible or Anthropic) for rich directive
    generation, or fall back to rule-based logic with pre-written pools.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = None

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )
        elif config.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=config.anthropic_key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_directive(self, state_summary: dict) -> ArchitectDirective:
        """
        Generate a narrative directive for the current turn.

        Args:
            state_summary: Dict containing:
                round:                Current round number (1-based).
                max_rounds:           Maximum rounds in the game (default 20).
                tension:              Current tension level (0-100).
                phase:                Current game phase string.
                discovered_clue_count: Number of clues the player has found.
                total_clues:          Total number of clues in the game.
                player_progress:      Overall progress ratio (0.0-1.0).
                player_type:          Detected player style (e.g. "cautious",
                                      "aggressive", "explorer").
                stuck_turns:          Consecutive turns with no meaningful progress.

        Returns:
            An ArchitectDirective with narrative instructions for this turn.
        """
        # Try LLM path first; fall back to rules on any failure
        if self.config.provider != LLMProvider.FALLBACK:
            try:
                return await self._generate_with_llm(state_summary)
            except Exception as e:
                print(f"[StoryArchitectAgent] LLM call failed: {e}, falling back to rules")

        return self._generate_with_rules(state_summary)

    # ------------------------------------------------------------------
    # LLM-based generation
    # ------------------------------------------------------------------

    async def _generate_with_llm(self, state_summary: dict) -> ArchitectDirective:
        """Generate directive using LLM with function calling (tool_use)."""
        user_prompt = self._build_user_prompt(state_summary)

        parsed: Optional[dict] = None
        raw: str = ""

        if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[_ARCHITECT_DIRECTIVE_TOOL_OPENAI],
                tool_choice={"type": "function", "function": {"name": "architect_directive"}},
                temperature=0.7,
                max_tokens=600,
            )
            msg = response.choices[0].message
            # Try to parse from tool_calls first
            if msg.tool_calls:
                try:
                    parsed = json.loads(msg.tool_calls[0].function.arguments)
                except (json.JSONDecodeError, AttributeError, IndexError):
                    pass
            # Fall back to parsing message.content if tool_calls missing
            if parsed is None:
                raw = msg.content or ""

        elif self.config.provider == LLMProvider.ANTHROPIC:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=600,
                system=ARCHITECT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[_ARCHITECT_DIRECTIVE_TOOL_ANTHROPIC],
                tool_choice={"type": "tool", "name": "architect_directive"},
                temperature=0.7,
            )
            # Anthropic returns tool_use blocks in content
            for block in response.content:
                if block.type == "tool_use" and block.name == "architect_directive":
                    parsed = block.input
                    break
            # Fall back to text block if no tool_use found
            if parsed is None:
                for block in response.content:
                    if block.type == "text":
                        raw = block.text or ""
                        break
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        # If tool_calls didn't yield data, try parsing raw text (markdown-wrapped JSON)
        if parsed is None and raw:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse LLM response: {raw[:300]}")

        if parsed is None:
            raise ValueError("LLM returned no tool call and no parseable content")

        return self._build_directive_from_data(parsed, state_summary)

    def _build_directive_from_data(
        self, parsed: dict, state_summary: dict
    ) -> ArchitectDirective:
        """Build an ArchitectDirective from a parsed data dict with validation."""
        current_act = parsed.get("current_act", self._determine_act(state_summary))
        if current_act not in (1, 2, 3):
            current_act = self._determine_act(state_summary)

        current_beat = parsed.get("current_beat", "setup")
        if current_beat not in ("setup", "rising", "crisis", "climax", "resolution"):
            current_beat = "setup"

        pacing = parsed.get("pacing", "sustain")
        if pacing not in ("accelerate", "sustain", "slow_down", "climax"):
            pacing = "sustain"

        hint_level = parsed.get("hint_level", "none")
        if hint_level not in ("none", "subtle", "moderate", "strong"):
            hint_level = "none"

        suggested_events = parsed.get("suggested_events", [])
        if not isinstance(suggested_events, list):
            suggested_events = []
        suggested_events = [str(e) for e in suggested_events[:2]]

        return ArchitectDirective(
            current_act=current_act,
            current_beat=current_beat,
            pacing=pacing,
            director_note=str(parsed.get("director_note", ""))[:50],
            system_narration=str(parsed.get("system_narration", ""))[:80],
            suggested_events=suggested_events,
            hint_level=hint_level,
            should_reveal_clue=bool(parsed.get("should_reveal_clue", False)),
        )

    def _build_user_prompt(self, state_summary: dict) -> str:
        """Build the user message for LLM-based generation."""
        round_num = state_summary.get("round", 1)
        max_rounds = state_summary.get("max_rounds", 20)
        tension = state_summary.get("tension", 20)
        phase = state_summary.get("phase", "自由试探")
        discovered = state_summary.get("discovered_clue_count", 0)
        total = state_summary.get("total_clues", 6)
        progress = state_summary.get("player_progress", 0.0)
        player_type = state_summary.get("player_type", "unknown")
        stuck = state_summary.get("stuck_turns", 0)
        reveal_count = state_summary.get("act_reveal_count", 0)
        reveal_budget = state_summary.get("reveal_budget", 0)
        cooldowns = state_summary.get("event_cooldowns", {})
        recent_high_intensity = state_summary.get("recent_high_intensity_turns", 0)

        return f"""【当前游戏状态】
- 回合：{round_num}/{max_rounds}（进度 {round_num / max_rounds * 100:.0f}%）
- 阶段：{phase}
- 紧张度：{tension}/100
- 已发现线索：{discovered}/{total}
- 当前幕已揭示线索：{reveal_count}/{reveal_budget}
- 事件冷却：{cooldowns}
- 最近高强度回合：{recent_high_intensity}
- 玩家进度评分：{progress:.2f}
- 玩家类型：{player_type}
- 连续无进展回合：{stuck}

请根据以上状态，给出本轮的叙事指令。以JSON格式回复。"""

    # ------------------------------------------------------------------
    # Rule-based fallback generation
    # ------------------------------------------------------------------

    def _generate_with_rules(self, state_summary: dict) -> ArchitectDirective:
        """Generate directive using pure rule-based logic (no LLM)."""
        round_num = state_summary.get("round", 1)
        max_rounds = state_summary.get("max_rounds", 20)
        tension = state_summary.get("tension", 20)
        discovered = state_summary.get("discovered_clue_count", 0)
        total = state_summary.get("total_clues", 6)
        stuck = state_summary.get("stuck_turns", 0)

        # Determine act and beat
        act = self._determine_act(state_summary)
        beat = self._determine_beat(state_summary, act)
        pacing = self._determine_pacing(state_summary, act, beat)
        hint_level = self._determine_hint_level(state_summary, act)
        should_reveal = self._should_reveal_clue(state_summary, act, hint_level)

        # Select content from pools
        director_note = self._pick_director_note(act, beat, stuck)
        system_narration = self._pick_system_narration(act, beat)
        suggested_events = self._pick_suggested_events(
            act, beat, stuck, tension, state_summary
        )

        return ArchitectDirective(
            current_act=act,
            current_beat=beat,
            pacing=pacing,
            director_note=director_note,
            system_narration=system_narration,
            suggested_events=suggested_events,
            hint_level=hint_level,
            should_reveal_clue=should_reveal,
        )

    # ------------------------------------------------------------------
    # Three-act structure logic
    # ------------------------------------------------------------------

    def _determine_act(self, state_summary: dict) -> int:
        """
        Determine the current act based on round number and player progress.

        Act boundaries are flexible — a player who finds clues quickly may
        advance to later acts sooner, while a slow player gets more time in
        earlier acts.
        """
        round_num = state_summary.get("round", 1)
        max_rounds = state_summary.get("max_rounds", 20)
        discovered = state_summary.get("discovered_clue_count", 0)
        tension = state_summary.get("tension", 20)

        # Default boundaries based on 20-round game
        act2_start = 7
        act3_start = 16

        # Adaptive: fast player — shift boundaries earlier
        if discovered >= 4 and round_num <= 8:
            act2_start = min(act2_start, round_num)
        if discovered >= 4 and tension > 55 and round_num <= 13:
            act3_start = min(act3_start, round_num + 2)

        # Adaptive: slow player — shift boundaries later (give more time)
        if discovered < 2 and round_num >= 10:
            act2_start = max(act2_start, 5)  # keep in Act 2 (don't push to Act 3)
            act3_start = max(act3_start, 17)

        # Determine act
        if round_num >= act3_start:
            return 3
        elif round_num >= act2_start:
            return 2
        else:
            return 1

    def _determine_beat(self, state_summary: dict, act: int) -> str:
        """Determine the narrative beat within the current act."""
        round_num = state_summary.get("round", 1)
        max_rounds = state_summary.get("max_rounds", 20)
        tension = state_summary.get("tension", 20)
        discovered = state_summary.get("discovered_clue_count", 0)

        if act == 1:
            return "setup"

        elif act == 2:
            # Sub-beats within Act 2
            if tension > 60 or discovered >= 4:
                return "crisis"
            else:
                return "rising"

        else:  # act == 3
            if round_num >= max_rounds - 1:
                return "resolution"
            elif tension >= 75 or round_num >= max_rounds - 2:
                return "climax"
            else:
                return "crisis"

    def _determine_pacing(self, state_summary: dict, act: int, beat: str) -> str:
        """Determine the pacing instruction for this turn."""
        round_num = state_summary.get("round", 1)
        max_rounds = state_summary.get("max_rounds", 20)
        discovered = state_summary.get("discovered_clue_count", 0)
        stuck = state_summary.get("stuck_turns", 0)
        reveal_budget_remaining = state_summary.get("reveal_budget_remaining", 1)
        recent_high_intensity = state_summary.get("recent_high_intensity_turns", 0)

        # Fast player: accelerate
        if discovered >= 4 and round_num <= 8:
            return "accelerate"

        # Stuck player: slow down and help
        if stuck > 3:
            return "slow_down"
        if reveal_budget_remaining <= 0:
            return "slow_down"
        if recent_high_intensity >= 2:
            return "slow_down"

        # Act/beat based defaults
        if beat == "climax" or beat == "resolution":
            return "climax"
        elif beat == "crisis":
            return "accelerate"
        elif act == 1:
            return "sustain"
        elif act == 2:
            return "sustain"
        else:
            return "climax"

    def _determine_hint_level(self, state_summary: dict, act: int) -> str:
        """Determine how strongly to hint at clues."""
        discovered = state_summary.get("discovered_clue_count", 0)
        total = state_summary.get("total_clues", 6)
        stuck = state_summary.get("stuck_turns", 0)
        round_num = state_summary.get("round", 1)
        stuck_recovery_level = state_summary.get("stuck_recovery_level", 0)

        if act == 1:
            if stuck_recovery_level >= 2:
                return "moderate"
            if stuck > 2:
                return "subtle"
            return "none"

        elif act == 2:
            if stuck_recovery_level >= 2:
                return "strong"
            if stuck > 3:
                return "moderate"
            if discovered < 2 and round_num >= 10:
                return "moderate"
            return "subtle"

        else:  # act == 3
            if discovered < 3:
                return "strong"
            if stuck > 2:
                return "strong"
            return "moderate"

    def _should_reveal_clue(
        self, state_summary: dict, act: int, hint_level: str
    ) -> bool:
        """Decide whether to actively help the player discover a clue."""
        discovered = state_summary.get("discovered_clue_count", 0)
        total = state_summary.get("total_clues", 6)
        stuck = state_summary.get("stuck_turns", 0)
        round_num = state_summary.get("round", 1)
        reveal_budget_remaining = state_summary.get("reveal_budget_remaining", 1)
        cooldowns = state_summary.get("event_cooldowns", {})
        stuck_recovery_level = state_summary.get("stuck_recovery_level", 0)

        # Always help in Act 3 if player is behind
        if act == 3 and discovered < 3:
            return True
        if reveal_budget_remaining <= 0:
            return False
        if cooldowns.get("major_clue", 0) > 0 and stuck_recovery_level < 2:
            return False

        # Help if stuck for too long
        if stuck > 3:
            return True
        if stuck_recovery_level >= 2:
            return True

        # Moderately help in Act 2 if player is behind schedule
        if act == 2 and discovered < 2 and round_num >= 10:
            return True

        # Strong hint means we should reveal
        if hint_level == "strong":
            return True

        return False

    # ------------------------------------------------------------------
    # Content selection from pools
    # ------------------------------------------------------------------

    def _pick_director_note(self, act: int, beat: str, stuck: int) -> str:
        """Select a director note from the appropriate pool."""
        if stuck > 3:
            # Inject urgency when player is stuck
            stuck_notes = [
                "也许换个方向或地点探索会有新发现。",
                "仔细想想，是不是遗漏了什么重要的细节？",
                "不妨试着和其他人聊聊——每个人都有自己的秘密。",
                "这里的某个角落可能藏着你忽略的东西。",
            ]
            return random.choice(stuck_notes)

        if act == 1:
            return random.choice(ACT1_NOTES)
        elif act == 2:
            if beat == "crisis":
                return random.choice(ACT2_CRISIS_NOTES)
            return random.choice(ACT2_NOTES)
        else:
            return random.choice(ACT3_NOTES)

    def _pick_system_narration(self, act: int, beat: str) -> str:
        """Select a system narration from the appropriate pool."""
        if act == 1:
            return random.choice(ACT1_NARRATIONS)
        elif act == 2:
            if beat == "crisis":
                return random.choice(ACT2_CRISIS_NARRATIONS)
            return random.choice(ACT2_NARRATIONS)
        else:
            return random.choice(ACT3_NARRATIONS)

    def _pick_suggested_events(
        self, act: int, beat: str, stuck: int, tension: int, state_summary: dict
    ) -> List[str]:
        """Select suggested NPC events for this turn."""
        events: List[str] = []
        cooldowns = state_summary.get("event_cooldowns", {})
        recent_high_intensity = state_summary.get("recent_high_intensity_turns", 0)

        # If player is stuck, always inject a stalemate-breaking event
        if stuck > 3:
            events.append(random.choice(STALEMATE_BREAKER_EVENTS))
            return events

        if recent_high_intensity >= 2:
            return events

        # Probability of an event increases with act and tension
        if act == 1:
            if random.random() < 0.3:
                events.append(random.choice(ACT1_EVENTS))
        elif act == 2:
            if beat == "crisis":
                # Always suggest an event during crisis
                if cooldowns.get("betrayal", 0) <= 0 and cooldowns.get("confession", 0) <= 0:
                    events.append(random.choice(ACT2_CRISIS_EVENTS))
            elif random.random() < 0.5:
                events.append(random.choice(ACT2_EVENTS))
        else:  # act == 3
            # High probability of events in final act
            if cooldowns.get("betrayal", 0) <= 0:
                events.append(random.choice(ACT3_EVENTS))
            if random.random() < 0.3:
                # Occasionally suggest a second event for maximum drama
                pool = [e for e in ACT3_EVENTS if e not in events]
                if pool:
                    events.append(random.choice(pool))

        return events

import json
import random
from typing import Optional

from config import Config, LLMProvider
from schemas.game_state import GameState


DIRECTOR_SYSTEM_PROMPT = """你是一个互动悬疑剧的导演AI。你的职责是：
1. 根据玩家的行动和当前局势，给出简短的导演旁白（不超过2句话）
2. 决定是否触发NPC之间的互动事件（让角色之间产生冲突或联盟）
3. 给出简短的场景氛围描写（1-2句话）

你必须以JSON格式回复，包含以下字段：
- director_note: 导演视角的局势判断（给玩家的暗示，不超过50字）
- npc_events: 数组，NPC之间自发的互动（0-1个），每个是一段描写文字
- system_narration: 场景氛围描写（不超过80字）

规则：
- 不要透露真相
- 根据紧张度调整氛围：低于30轻松试探，30-60暗流涌动，60以上剑拔弩张
- 当线索积累到3个以上时，应该让NPC之间开始互相质疑
- 保持悬疑感，不要太早揭示关键信息"""


def _build_director_user_prompt(
    state: GameState, player_action: str, rule_result: dict
) -> str:
    """Build the user message for the director agent."""
    discovered_clues = [c.text for c in state.clues if c.discovered]
    char_summary = ", ".join(
        f"{c.name}(信任:{c.trust_to_player},嫌疑:{c.suspicion},位置:{c.location})"
        for c in state.characters
    )

    return f"""【当前状态】
- 回合：{state.round}/{state.max_rounds}
- 场景：{state.scene}
- 阶段：{state.phase}
- 紧张度：{state.tension}/100
- 已发现线索：{discovered_clues if discovered_clues else "无"}
- 角色状态：{char_summary}

【玩家行动】
{player_action}

【规则判定】
- 结果：{rule_result['success']}
- 系统叙述：{rule_result['narration']}
- 新发现线索：{rule_result['discovered_clues']}

请以JSON格式回复。"""


# ─── Fallback responses ──────────────────────────────────────────────

_LOW_TENSION_NOTES = [
    "气氛看似平静，但每个人的眼神都在躲闪。注意观察谁最不自然。",
    "晚宴的残余还在桌上，但主人的位子空着。大家都在掩饰自己的不安。",
    "现在是试探的好时机——大家的防备还没有完全建立起来。",
    "顾家老宅的每个角落似乎都藏着秘密，但现在还没有人愿意先开口。",
    "三个人各怀心思，你需要找到突破口。",
]

_MID_TENSION_NOTES = [
    "空气中的火药味越来越浓，有人开始坐立不安了。",
    "事情正在朝着失控的方向发展，你需要抓紧时间。",
    "真相的碎片正在一点点浮出水面，但拼图还远未完成。",
    "有人在说谎，而且他们知道你在逼近真相。",
    "局势越来越微妙——每一步都可能改变结局。",
]

_HIGH_TENSION_NOTES = [
    "局面已经到了临界点，任何一个错误都可能让真相永远被埋葬。",
    "所有人的伪装都快要维持不住了——现在是关键时刻。",
    "紧张的气氛几乎要让人窒息，决断的时刻到了。",
    "再不行动，一切就来不及了。你必须做出选择。",
    "真相就在眼前，但危险也是。",
]

_LOW_NARRATIONS = [
    "老宅的壁灯投下昏黄的光影，古董钟在角落里滴答作响。",
    "窗外的月光透过纱帘洒进来，为这个不安的夜晚增添了几分诡异。",
    "远处传来猫头鹰的叫声，夜风轻轻拂过走廊的窗帘。",
    "烛光摇曳，映照出墙上挂着的顾家全家福——但照片里的主人已经不见了。",
]

_MID_NARRATIONS = [
    "一阵冷风从不知什么地方吹来，桌上的蜡烛猛地晃了一下。",
    "老宅深处似乎传来什么声响，但仔细听又消失了。",
    "有人不经意地打碎了一个酒杯，声音在寂静中格外刺耳。",
    "空气中弥漫着一种不安的气息，仿佛暴风雨前的宁静。",
]

_HIGH_NARRATIONS = [
    "老宅中的气氛已经紧绷到了极点，每个人都像是随时会爆发的火药桶。",
    "雷声在远处隐隐滚动，像是在为即将揭晓的真相做铺垫。",
    "灯光忽然闪了一下，有人倒吸了一口凉气。所有人的神经都绷到了极限。",
    "时间在一分一秒地流逝，真相和危险同时在逼近。",
]

_NPC_EVENTS_LOW = [
    "周牧端起酒杯走向林岚，笑着说了句什么，但林岚只是微微点了点头就转身离开了。",
    "宋知微在角落里翻看着手机，不时抬头打量其他人的表情。",
    "林岚安静地站在窗边，目光似乎一直在注视着书房的方向。",
]

_NPC_EVENTS_MID = [
    "周牧突然拔高了声音对林岚说：'你到底知不知道顾言去哪了？'林岚面无表情地回了一句：'我是秘书，不是保姆。'",
    "宋知微不知从哪里掏出了一个小本子开始记录什么，周牧看到后明显有些紧张：'你记什么呢？'",
    "林岚看了一眼宋知微正在写的东西，忽然说：'宋小姐，你似乎对这里的情况异常熟悉。'",
    "周牧试图和宋知微搭话，但对方直接抛出一个尖锐的问题：'你昨晚几点离开顾言的？'周牧的笑容瞬间僵住了。",
]

_NPC_EVENTS_HIGH = [
    "周牧猛地站起来指着林岚：'你一直在隐瞒什么！'林岚冰冷地回视：'比起我，你更应该解释一下昨晚的事。'",
    "宋知微突然说：'我觉得在座的各位，都有不可告人的秘密。'一时间所有人都沉默了。",
    "林岚和周牧之间爆发了激烈的对峙，宋知微在一旁冷静地观察着这一切，嘴角微微上扬。",
    "周牧的手在微微发抖，他看着其他人说：'如果顾言出了什么事……我们谁都脱不了干系。'",
]


def _fallback_direction(
    state: GameState, player_action: str, rule_result: dict
) -> dict:
    """Generate director output without LLM, using rule-based logic."""
    tension = state.tension
    discovered_count = sum(1 for c in state.clues if c.discovered)

    # Select notes and narrations based on tension level
    if tension < 30:
        note = random.choice(_LOW_TENSION_NOTES)
        narration = random.choice(_LOW_NARRATIONS)
        event_pool = _NPC_EVENTS_LOW
        event_chance = 0.3
    elif tension < 60:
        note = random.choice(_MID_TENSION_NOTES)
        narration = random.choice(_MID_NARRATIONS)
        event_pool = _NPC_EVENTS_MID
        event_chance = 0.5
    else:
        note = random.choice(_HIGH_TENSION_NOTES)
        narration = random.choice(_HIGH_NARRATIONS)
        event_pool = _NPC_EVENTS_HIGH
        event_chance = 0.7

    # Decide whether to trigger an NPC event
    npc_events = []
    if discovered_count >= 3 or random.random() < event_chance:
        npc_events.append(random.choice(event_pool))

    return {
        "director_note": note,
        "npc_events": npc_events,
        "system_narration": narration,
        "suggested_phase": None,
    }


class DirectorAgent:
    """Director agent that orchestrates narrative pacing and NPC interactions."""

    def __init__(self, config: Config):
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

    async def generate_direction(
        self,
        state: GameState,
        player_action: str,
        rule_result: dict,
    ) -> dict:
        """
        Generate director output: note, NPC events, and scene narration.

        Returns:
            {
                "director_note": str,
                "npc_events": [str],
                "system_narration": str,
                "suggested_phase": Optional[str],
            }
        """
        if self.config.provider == LLMProvider.FALLBACK:
            return _fallback_direction(state, player_action, rule_result)

        user_prompt = _build_director_user_prompt(state, player_action, rule_result)

        try:
            if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": DIRECTOR_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.8,
                    max_tokens=500,
                )
                raw = response.choices[0].message.content

            elif self.config.provider == LLMProvider.ANTHROPIC:
                response = await self.client.messages.create(
                    model=self.config.model,
                    max_tokens=500,
                    system=DIRECTOR_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.8,
                )
                raw = response.content[0].text

            # Parse JSON from response (handle possible markdown wrapping)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            parsed = json.loads(raw)
            return {
                "director_note": parsed.get("director_note", ""),
                "npc_events": parsed.get("npc_events", []),
                "system_narration": parsed.get("system_narration", ""),
                "suggested_phase": parsed.get("suggested_phase", None),
            }

        except Exception as e:
            print(f"[DirectorAgent] LLM call failed: {e}, falling back to rules")
            return _fallback_direction(state, player_action, rule_result)

import random
from typing import Dict, List

from config import Config, LLMProvider
from schemas.game_state import Character, GameState, IntentType


def _build_character_system_prompt(
    character: Character,
    state: GameState,
    scoped_facts: List[str],
    hard_boundaries: List[str],
) -> str:
    """Build the system prompt for a character agent."""
    pk = "\n".join(f"- {k}" for k in scoped_facts) or "- 暂无新增信息"
    rm = "\n".join(f"- {k}: {v}" for k, v in character.relation_map.items())
    hb = "\n".join(f"- {b}" for b in hard_boundaries) or "- 避免主动泄露未公开的核心秘密"

    # Load dynamically filtered persona from .md skill file
    from characters import build_dynamic_persona
    skill_content, bracket_description = build_dynamic_persona(
        character.id, state.tension, character.trust_to_player
    )
    depth = _CHARACTER_DEPTH.get(character.id, "")

    # If we have a skill sheet, inject only the relevant sections
    persona_block = ""
    if skill_content:
        persona_block = f"\n{skill_content}\n"

    tension_line = f"\n【当前张力区间】tension={state.tension}，你现在处于{bracket_description}状态\n"

    return f"""你现在扮演"{character.name}"——你不是AI，你就是这个人。你有自己的想法、情绪和秘密。
{persona_block}{tension_line}
【你是谁】
{character.name}，{character.public_role}。{depth}

【对面的人是谁】
一个叫来调查顾言失踪案的私人侦探。顾家请来的。你不完全信任他——他在调查你们每个人。
- 你对这个侦探的信任度：{character.trust_to_player}/100（{"你基本不信任他，说话要设防" if character.trust_to_player < 30 else "你稍微信任他，但仍保持警惕" if character.trust_to_player < 60 else "你相对信任他，愿意配合"}）
- 你身上的嫌疑：{character.suspicion}/100（{"你觉得自己很安全" if character.suspicion < 30 else "你感到压力，要小心应对" if character.suspicion < 60 else "你知道自己被盯上了，非常紧张"}）

【你的性格和说话方式】
{character.style}
{character.speaking_rules}

【你的目标】{character.goal}
【你害怕什么】{character.fear}

【你知道的事情（侦探不知道这些）】
{pk}

【你对在场其他人的看法】
{rm}

【绝对红线——打死也不能说的】
{hb}

【此刻的场景】
地点：{state.scene}（顾家老宅内）
气氛紧张度：{state.tension}/100
当前阶段：{state.phase}

【表演要求】
1. 你就是{character.name}——用她/他的语气、习惯、小动作来说话
2. 不要"配合调查"——你有自己的利益要保护。该撒谎就撒谎，该回避就回避
3. 主动出击：反问侦探、转移话题、暗示别人更可疑
4. 加入身体语言和微表情（攥紧杯子、移开目光、冷笑）
5. 30-100字，只输出角色的对话和动作描写
6. 绝不输出JSON、旁白或元数据
7. 绝不用"作为AI"之类的元发言"""


# ── Per-character depth profiles ──────────────────────────────────

_CHARACTER_DEPTH = {
    "linlan": (
        "28岁，顾家工作3年的私人秘书。永远穿深色职业装，头发一丝不乱。"
        "说话时习惯微微偏头，像是在衡量每一个字的分量。"
        "口头禅：'这个问题……恐怕不在我的职责范围内。'"
        "紧张时会不自觉地用指尖敲桌面。"
        "她看起来完美得不真实——而这本身就很可疑。"
        "她对顾言有一种超越雇佣关系的忠诚——可能是感激，也可能是别的什么。"
    ),
    "zhoumu": (
        "32岁，顾言从小一起长大的兄弟。穿着随意，衬衫扣子总松两颗。"
        "笑起来声音很大，但笑不到眼睛里。"
        "口头禅：'哎呀别这么严肃嘛！''说起来……'（每次说'说起来'后面跟的往往是谎话）"
        "紧张时会反复给自己倒酒、摸鼻子、突然站起来又坐下。"
        "他嘴上说跟顾言是铁兄弟，但一提到钱就会微妙地变脸。"
        "他昨晚喝了很多酒——是为了壮胆？还是为了忘记什么？"
    ),
    "songzhi": (
        "26岁，某财经媒体的调查记者。戴细框眼镜，随身带一本黑色笔记本。"
        "说话像连珠炮：快、准、追问到底。"
        "口头禅：'等一下，你刚才说……''这条信息很有趣。''我需要确认一下。'"
        "她总是在观察——你跟别人说话时，她在旁边记笔记。"
        "习惯性地推眼镜——尤其是发现关键信息的时候。"
        "她出现在这里'太巧了'——一个调查记者恰好在主人失踪的晚宴上？"
    ),
}


def _build_character_user_prompt(
    player_action: str, rule_result: dict
) -> str:
    """Build the user message for the character agent."""
    return f"""【侦探刚才做了什么】
{player_action}

【规则判断结果】
{rule_result.get('narration', '')}

请以你的角色身份回应。"""


# ─── Fallback response pools ─────────────────────────────────────────

# Responses organized by character_id -> intent_type -> list of responses
# Additional variants for different trust levels (high/low)

_FALLBACK_RESPONSES: Dict[str, Dict[str, List[str]]] = {
    "linlan": {
        "observe": [
            "林岚注意到你的目光，微微侧过身，表情没有任何变化。「有什么需要的吗？」她的语气公事公办。",
            "你的打量让林岚微微皱眉。她整了整衣领，目光平静地回望你：「看够了？」",
            "林岚站在窗边，背影笔直。察觉到你的注视后，她只是淡淡地说：「如果没事的话，我还有工作。」",
        ],
        "ask": [
            "林岚微微抬起下巴：「你想知道什么？不过我不确定我能帮上什么忙。」语气礼貌但疏远。",
            "「这个问题……」林岚停顿了一下，似乎在斟酌用词，「我觉得你应该去问更了解情况的人。」",
            "林岚的表情没有波动：「顾先生的事情，我作为秘书，只负责工作范畴内的事务。」",
            "「你为什么会这样问？」林岚不答反问，目光中带着一丝警惕。",
        ],
        "ask_low_trust": [
            "林岚冷冷地看了你一眼：「我不觉得我有义务回答这个问题。」",
            "「恕我直言，我们似乎还没有熟到可以讨论这些的地步。」林岚的语气如同冬天的风。",
        ],
        "bluff": [
            "林岚的眼神闪了一下，但很快恢复平静：「哦？你知道什么？」她反问道，语气不紧不慢。",
            "「如果你真的知道，就不会用这种方式试探了。」林岚嘴角微微弯了一下，但那算不上是笑。",
            "林岚安静地看了你几秒钟：「有些事情，知道了不一定是好事。你确定要继续？」",
        ],
        "search": [
            "林岚看着你翻找的动作，没有阻止也没有帮忙，只是安静地站在一旁观察。",
            "「你在找什么？」林岚的语气平淡，但你注意到她的视线在你检查某个方向时微微偏移了。",
        ],
        "accuse": [
            "林岚的表情终于有了变化——不是慌张，而是一种冰冷的审视：「你有证据吗？还是只是猜测？」",
            "「你可以怀疑任何人，但请注意用词。」林岚的声音降低了，却更加锋利。",
        ],
        "eavesdrop": [
            "你隐约听到林岚在低声自语：「……时间不多了，必须在天亮之前……」但后面的话被风声盖过了。",
            "林岚似乎在打电话，你只听到了最后一句：「……按计划进行。」然后她挂断了电话。",
        ],
        "other": [
            "林岚礼貌地点了点头，没有多说什么。",
            "「嗯。」林岚简短地回应，继续处理手头的事情。",
        ],
    },
    "zhoumu": {
        "observe": [
            "周牧正在倒第三杯酒，看到你盯着他，咧嘴一笑：「怎么，我脸上有花？」但他端酒杯的手有点不稳。",
            "你观察着周牧——他一直在活动，一会儿看看窗外，一会儿翻翻手机，明显坐不住。",
            "周牧靠在椅背上，看似随意，但你注意到他的右脚一直在轻轻抖动。",
        ],
        "ask": [
            "周牧大手一挥：「顾言那家伙？估计又跑去哪里谈什么大生意了吧。」他笑得有点用力。",
            "「你问我？」周牧眨了眨眼，「哥们我就是来吃饭喝酒的，别的我可啥也不知道啊！」语气夸张，像是在掩饰什么。",
            "周牧的笑容僵了一瞬：「你怎么突然问这个……」随即又恢复常态，「没什么，我就是觉得你管得挺宽啊，哈哈。」",
            "「这事你应该去问林岚吧？」周牧把话题推给了别人，「她是秘书，什么事她最清楚了。」",
        ],
        "ask_low_trust": [
            "周牧的脸色沉了下来：「你打听这些干什么？你到底是谁派来的？」",
            "「别问了行不行？」周牧的声音突然提高，随即又压低，四下看了看，「……没什么，我就是烦了。」",
        ],
        "bluff": [
            "周牧的笑容明显僵住了，喉结上下动了一下：「你……你说什么？」",
            "「你少唬我。」周牧干笑两声，但声音比刚才高了至少一个八度，「我什么都不知道。」",
            "周牧的眼神闪烁了一瞬：「你到底知不知道啊？别在这里装神弄鬼的……」他显然被你的话动摇了。",
        ],
        "search": [
            "周牧看你到处翻，有些紧张地跟在后面：「你找什么呢？需要帮忙吗？」他的热情有点可疑。",
            "「嘿嘿，别翻了。」周牧挡在一个角落前面，又很快假装自然地移开了，「我是说……这边没什么好看的。」",
        ],
        "accuse": [
            "周牧猛地站起来，椅子差点翻倒：「你说什么？！你凭什么……」他的声音在发抖，拳头紧紧攥着。",
            "「你放屁！」周牧脸涨得通红，但声音却在颤抖，「我和顾言是兄弟，我怎么会……」",
        ],
        "eavesdrop": [
            "周牧在角落里嘀咕着什么，你隐约听到：「……不能让他们知道昨晚的事……」",
            "你听到周牧在跟某人低声说：「遗嘱的事先别提，听到没有？」",
        ],
        "other": [
            "周牧摆了摆手：「随便吧。」然后继续喝他的酒。",
            "「嗯？哦，好。」周牧心不在焉地回应着，目光飘向了别处。",
        ],
    },
    "songzhi": {
        "observe": [
            "宋知微正在用手机拍摄现场的细节。发现你在看她，她反而迎上你的目光：「你也在观察？很好，我们可以交换一下笔记。」",
            "宋知微的眼睛像扫描仪一样快速巡视着房间。她注意到你的注视，嘴角微微上扬：「看来我们想到一块去了。」",
            "你注意到宋知微一直在小本子上记录什么，她抬头看到你时，不动声色地合上了本子。",
        ],
        "ask": [
            "宋知微眼睛一亮：「这个问题问得好。不过在我回答之前——你是怎么注意到这一点的？」她总是在用问题回答问题。",
            "「等一下，」宋知微竖起一根手指，「你刚才说'顾言'？你注意到没有，林岚在提到他的时候，总是用'顾先生'？」",
            "宋知微歪着头想了想：「我可以告诉你我知道的，但我也有个问题想问你。公平交易，怎么样？」",
            "「所以你的意思是——」宋知微把你的话重新组织了一遍，语速很快，「这很有意思。我之前也有类似的猜测。」",
        ],
        "ask_low_trust": [
            "宋知微的眼神变得锐利：「你在套我的话？」她笑了笑，「职业病让我很容易看穿这一套。」",
            "「我没办法回答你的问题，至少现在不行。」宋知微合上笔记本，语气礼貌但坚定。",
        ],
        "bluff": [
            "宋知微挑了挑眉：「真的吗？那你具体知道什么？」她的反应异常冷静，反而让你不确定她是否在害怕。",
            "「有意思。」宋知微的眼睛亮了起来，「如果你真的知道什么，我们不妨坐下来好好谈谈。互利互惠。」",
            "宋知微嘴角微扬：「你的演技不错。但是作为记者，我见过太多虚张声势了。不过——你这么说，倒是给了我一个思路。」",
        ],
        "search": [
            "宋知微跟了上来：「你也在找证据？太好了。你去那边，我看看这边——比一个人效率高。」她的热情让你有些意外。",
            "「你找到什么了？」宋知微几乎是瞬间出现在你身边，目光紧紧盯着你手里的东西。",
        ],
        "accuse": [
            "宋知微的笑容消失了，但她的眼神依然犀利：「你在指控我？好，那请拿出你的证据。作为记者，我最尊重事实。」",
            "「有意思的推理。」宋知微平静地说，但你注意到她的手指在桌面上轻轻敲了几下，「不过你的逻辑链条缺了几环。」",
        ],
        "eavesdrop": [
            "你隐约听到宋知微在自言自语：「……匿名的爆料……果然不是空穴来风……」她似乎在整理什么线索。",
            "宋知微在跟某人通话，你只捕捉到了几个词：「……独家……今晚之前……必须确认……」",
        ],
        "other": [
            "宋知微微笑着点头：「继续——我在听。」她随时准备抓住任何有价值的信息。",
            "「好的，记下了。」宋知微在本子上快速写了什么。",
        ],
    },
}


def _get_fallback_response(
    character: Character,
    intent: IntentType,
    rule_result: dict,
) -> str:
    """Generate a fallback response for a character without LLM."""
    char_responses = _FALLBACK_RESPONSES.get(character.id, {})

    intent_key = intent.value

    # Use low-trust variants if applicable
    if character.trust_to_player < 25 and f"{intent_key}_low_trust" in char_responses:
        responses = char_responses[f"{intent_key}_low_trust"]
    elif intent_key in char_responses:
        responses = char_responses[intent_key]
    else:
        responses = char_responses.get("other", ["……"])

    # If action was blocked, add some flavor
    response = random.choice(responses)

    if rule_result.get("success") == "blocked" and intent in (
        IntentType.ask,
        IntentType.bluff,
    ):
        blocked_additions = [
            f"\n\n{character.name}似乎不想继续这个话题。",
            f"\n\n{character.name}移开了目光，明显不愿再说。",
        ]
        response += random.choice(blocked_additions)

    return response


class CharacterAgent:
    """Character agent with persistent conversation memory per NPC per session.

    Each NPC maintains their own conversation thread — the LLM genuinely
    remembers every exchange, not through injected summaries but through
    actual message history. This makes NPCs feel like real people who
    remember what you said 5 turns ago.
    """

    # Max conversation history to keep (in messages) to avoid context overflow
    MAX_HISTORY = 16  # 8 exchanges (user + assistant)

    def __init__(self, config: Config):
        self.config = config
        self.client = None
        # Persistent conversation threads: {(session_id, char_id): [messages]}
        self._threads: Dict[tuple, List[dict]] = {}

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

    def _get_thread(self, session_id: str, char_id: str) -> List[dict]:
        """Get or create the conversation thread for a character."""
        key = (session_id, char_id)
        if key not in self._threads:
            self._threads[key] = []
        return self._threads[key]

    def _trim_thread(self, thread: List[dict]):
        """Keep thread within token budget by trimming old messages."""
        while len(thread) > self.MAX_HISTORY:
            thread.pop(0)

    async def generate_response(
        self,
        character: Character,
        state: GameState,
        player_action: str,
        intent: IntentType,
        rule_result: dict,
        extra_context: str = "",
        scoped_facts: List[str] | None = None,
        hard_boundaries: List[str] | None = None,
    ) -> str:
        """
        Generate an in-character response with persistent conversation memory.

        The NPC's LLM sees the FULL conversation history — it genuinely
        remembers what was said before, not through summaries but through
        actual message context.
        """
        if self.config.provider == LLMProvider.FALLBACK:
            return _get_fallback_response(character, intent, rule_result)

        # Build system prompt (updates each turn with current state)
        system_prompt = _build_character_system_prompt(
            character,
            state,
            scoped_facts or character.private_knowledge,
            hard_boundaries or character.hard_boundaries,
        )
        if extra_context:
            system_prompt += "\n\n" + extra_context

        user_prompt = _build_character_user_prompt(player_action, rule_result)

        # Get persistent conversation thread
        thread = self._get_thread(state.session_id, character.id)

        # Add new user message to thread
        thread.append({"role": "user", "content": user_prompt})
        self._trim_thread(thread)

        try:
            if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
                # System prompt + full conversation history
                messages = [{"role": "system", "content": system_prompt}] + thread
                response = await self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    temperature=0.9,
                    max_tokens=300,
                )
                reply = response.choices[0].message.content.strip()

            else:
                return _get_fallback_response(character, intent, rule_result)

            # Save assistant reply to thread — NPC will remember this next time
            thread.append({"role": "assistant", "content": reply})
            self._trim_thread(thread)

            return reply

        except Exception as e:
            # Remove the failed user message from thread
            if thread and thread[-1]["role"] == "user":
                thread.pop()
            print(f"[CharacterAgent] LLM call failed for {character.name}: {e}, falling back")
            return _get_fallback_response(character, intent, rule_result)

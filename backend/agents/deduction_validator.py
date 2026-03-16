import json
from typing import Dict, List

from pydantic import BaseModel

from config import Config, LLMProvider


# ─── Data Models ────────────────────────────────────────────────────


class DeductionResult(BaseModel):
    truth_score: float          # 0.0-1.0, how close to the truth
    key_insights: List[str]     # Which truth elements the player identified
    missing_insights: List[str] # What the player missed
    ending_type: str            # "perfect" / "good" / "partial" / "wrong"
    response_text: str          # Narrative response to player's deduction (Chinese)


# ─── Truth Definition ───────────────────────────────────────────────

# Each truth element has: display name, weight, and keyword list.
TRUTH_ELEMENTS: Dict[str, Dict] = {
    "no_crime": {
        "name": "并非真正的犯罪",
        "weight": 0.20,
        "keywords": ["没有犯罪", "没有人被害", "没有凶手", "不是谋杀", "并没有失踪"],
    },
    "self_staged": {
        "name": "顾言自导自演",
        "weight": 0.25,
        "keywords": ["自导自演", "自己策划", "假装失踪", "自己安排", "故意消失", "装的", "演戏"],
    },
    "testing_people": {
        "name": "目的是试探身边的人",
        "weight": 0.20,
        "keywords": ["试探", "考验", "测试", "看看谁", "观察", "真面目", "试验"],
    },
    "wine_cellar": {
        "name": "藏身于酒窖密室",
        "weight": 0.15,
        "keywords": ["酒窖", "密室", "地下", "藏在"],
    },
    "will_motive": {
        "name": "遗嘱变更是导火索",
        "weight": 0.10,
        "keywords": ["遗嘱", "遗产", "慈善", "捐", "财产"],
    },
    "lin_lan_accomplice": {
        "name": "林岚是知情者/协助者",
        "weight": 0.10,
        "keywords": ["林岚知道", "林岚配合", "林岚帮", "秘书参与"],
    },
}


# ─── LLM Prompts ────────────────────────────────────────────────────

LLM_SYSTEM_PROMPT = (
    "你是一个推理游戏的裁判。玩家正在给出他们对案件的推理结论。"
    "请评估玩家的推理与真相的匹配度。\n\n"
    "案件真相：\n"
    "顾言（失踪者）自导自演了这场失踪。他没有遇害，也没有真正失踪。"
    "他故意策划了这一切，目的是试探和考验身边的人——看看谁是真心对待他的，谁在觊觎他的财富。"
    "他躲藏在自家酒窖的密室里，全程通过监控和林岚的汇报观察各人的反应。"
    "导火索是遗嘱变更——顾言打算将大部分财产捐给慈善机构，这激化了潜在的利益冲突。"
    "林岚（顾言的秘书）是唯一的知情者和协助者，她帮助顾言完成了整个计划。\n\n"
    "请根据以下六个真相要素，对玩家的推理进行评分。"
    "每个要素的评分范围为0到1（0表示完全没有提及或完全错误，1表示完全正确地识别了该要素）。\n\n"
    "六个真相要素：\n"
    "1. no_crime: 并非真正的犯罪（没有人被害）\n"
    "2. self_staged: 顾言自导自演了失踪\n"
    "3. testing_people: 目的是试探/考验身边的人\n"
    "4. wine_cellar: 顾言藏身于酒窖密室\n"
    "5. will_motive: 遗嘱/遗产变更是导火索\n"
    "6. lin_lan_accomplice: 林岚是知情者/协助者\n\n"
    "请以JSON格式回复，格式如下：\n"
    '{"no_crime": 0.0, "self_staged": 0.0, "testing_people": 0.0, '
    '"wine_cellar": 0.0, "will_motive": 0.0, "lin_lan_accomplice": 0.0}\n\n'
    "注意：\n"
    "- 只输出JSON，不要输出其他内容\n"
    "- 即使玩家用不同的措辞表达了相同的意思，也应该给予较高的分数\n"
    "- 评估语义含义，而不仅仅是关键词匹配"
)


# ─── Ending Narratives ──────────────────────────────────────────────

ENDING_NARRATIVES = {
    "perfect": (
        "完美破局——你精准地道出了真相的核心！"
        "顾言从酒窖密室中走出，向你缓缓鼓掌。「我设下这个局，就是想看看谁能真正看透一切。」"
        "他的目光扫过在场的每一个人，有欣慰，也有失望。"
        "「感谢你——让我知道，这世上还有人愿意追寻真相本身，而不是被表象所迷惑。」"
        "林岚站在一旁，嘴角浮现出一丝如释重负的微笑。这场精心策划的试探，终于落下帷幕。"
    ),
    "good": (
        "接近真相——你抓住了关键线索！"
        "顾言缓缓从暗处走出，微微点头：「你看到了大部分真相，这已经超出了我的预期。」"
        "他审视着你，目光中带着几分赞许：「虽然还有一些细节你没能完全拼凑起来，"
        "但你的洞察力已经证明了你的价值。」"
        "真相的拼图还差几块，但你已经描绘出了最重要的轮廓。"
    ),
    "partial": (
        "部分正确——你的方向是对的，但还缺少关键的拼图。"
        "顾言的声音从某个看不见的地方传来：「你触碰到了真相的边缘，但还不够。」"
        "你回想着搜集到的所有线索，隐约感觉自己遗漏了什么至关重要的东西。"
        "有些答案明明就在眼前，却因为一念之差而错过了。"
        "或许再多一点时间、再多一点留意，结局会完全不同。"
    ),
    "wrong": (
        "推理偏差——你的推理与真相相去甚远。"
        "沉默在房间中蔓延开来。没有人回应你的指控，只有墙上的钟在滴答作响。"
        "周牧露出困惑的表情，林岚面无表情地垂下了目光，宋知微在笔记本上划去了什么。"
        "也许从一开始，你追寻的方向就偏离了。真相往往藏在最不起眼的地方，"
        "而最大的骗局，从来不是别人对你说的谎，而是你自己心中先入为主的假设。"
    ),
}


# ─── Validator Class ────────────────────────────────────────────────


class DeductionValidator:
    """Validates player deductions using keyword matching + LLM semantic analysis."""

    def __init__(self, config: Config):
        self.config = config
        self.client = None

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

    async def validate(
        self,
        player_accusation: str,
        discovered_clues: List[str],
        player_known_facts: List[str],
    ) -> DeductionResult:
        """
        Evaluate the player's final deduction against the core truth.

        Uses a two-pass approach:
          1. Fast keyword scoring (always runs)
          2. LLM semantic scoring (if an LLM provider is available)

        The higher score per element is used, so players are never penalised
        for expressing the truth in unexpected wording.

        Args:
            player_accusation: The player's deduction text.
            discovered_clues: Clue texts the player has uncovered during the game.
            player_known_facts: Facts the game has confirmed the player knows.

        Returns:
            A DeductionResult with score, insights, ending type, and narrative.
        """
        # Step 1 — keyword scoring (always available)
        kw_scores = self._keyword_score(player_accusation)

        # Step 2 — LLM semantic scoring (best-effort)
        llm_scores: Dict[str, float] = {}
        if self.config.provider != LLMProvider.FALLBACK:
            try:
                llm_scores = await self._llm_score(player_accusation)
            except Exception as e:
                print(f"[DeductionValidator] LLM scoring failed: {e}, using keywords only")

        # Merge: take the higher of keyword / LLM for each element
        merged_scores: Dict[str, float] = {}
        for key in TRUTH_ELEMENTS:
            merged_scores[key] = max(
                kw_scores.get(key, 0.0),
                llm_scores.get(key, 0.0),
            )

        # Compute weighted truth score
        truth_score = sum(
            merged_scores[key] * TRUTH_ELEMENTS[key]["weight"]
            for key in TRUTH_ELEMENTS
        )
        truth_score = round(min(max(truth_score, 0.0), 1.0), 4)

        # Determine identified vs. missed insights
        key_insights: List[str] = []
        missing_insights: List[str] = []
        for key, elem in TRUTH_ELEMENTS.items():
            if merged_scores[key] >= 0.5:
                key_insights.append(elem["name"])
            else:
                missing_insights.append(elem["name"])

        # Step 3 — determine ending type
        if truth_score >= 0.75:
            ending_type = "perfect"
        elif truth_score >= 0.5:
            ending_type = "good"
        elif truth_score >= 0.25:
            ending_type = "partial"
        else:
            ending_type = "wrong"

        # Step 4 — narrative response
        response_text = ENDING_NARRATIVES[ending_type]

        return DeductionResult(
            truth_score=truth_score,
            key_insights=key_insights,
            missing_insights=missing_insights,
            ending_type=ending_type,
            response_text=response_text,
        )

    # ── Internal: keyword-based scoring ─────────────────────────────

    def _keyword_score(self, player_accusation: str) -> Dict[str, float]:
        """
        Score each truth element by checking whether any of its keywords
        appear in the player's accusation text.

        Returns a dict mapping element key -> 0.0 or 1.0.
        """
        scores: Dict[str, float] = {}
        text = player_accusation.lower()
        for key, elem in TRUTH_ELEMENTS.items():
            matched = any(kw in text for kw in elem["keywords"])
            scores[key] = 1.0 if matched else 0.0
        return scores

    # ── Internal: LLM-based semantic scoring ────────────────────────

    async def _llm_score(self, player_accusation: str) -> Dict[str, float]:
        """
        Ask the LLM to semantically score how well the player's accusation
        matches each truth element on a 0-1 scale.

        Returns a dict mapping element key -> float score (0.0-1.0).
        """
        user_prompt = f"以下是玩家的推理结论：\n\n「{player_accusation}」\n\n请对每个真相要素评分（0-1），以JSON格式回复。"

        raw: str = ""

        if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=200,
            )
            raw = response.choices[0].message.content

        # Parse JSON from response (handle possible markdown wrapping)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            raw = raw.rsplit("```", 1)[0]
        parsed = json.loads(raw)

        # Clamp every value to [0, 1] and only keep known keys
        scores: Dict[str, float] = {}
        for key in TRUTH_ELEMENTS:
            val = parsed.get(key, 0.0)
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = 0.0
            scores[key] = min(max(val, 0.0), 1.0)

        return scores

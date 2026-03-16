"""LLM slot-filling pipeline — one call to populate an entire story template."""

from __future__ import annotations

import json
from typing import Any, Dict

from config import Config, LLMProvider
from stories.templates.base_template import StoryTemplate


class StoryGenerator:
    """Fills all template slots with a single LLM call."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client: Any = None

        if config.provider == LLMProvider.OPENAI_COMPATIBLE:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self, template: StoryTemplate, user_theme: str
    ) -> Dict[str, str]:
        """Fill all template slots via a single LLM call.

        Returns a dict mapping slot names to their filled values.
        Raises ``RuntimeError`` if no LLM is configured.
        """
        if self.config.provider == LLMProvider.FALLBACK:
            raise RuntimeError("Story generation requires an LLM provider.")

        prompt = self._build_prompt(template, user_theme)
        raw = await self._call_llm(prompt)
        return self._parse_slots(raw, template)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, template: StoryTemplate, user_theme: str) -> str:
        char_reqs = self._format_character_requirements(template)
        clue_reqs = self._format_clue_requirements(template)
        slot_list = json.dumps(template.slots, ensure_ascii=False, indent=2)

        return f"""你是一个推理游戏编剧。根据以下主题和模板要求，填充所有槽位。
你需要创作一个完整、逻辑自洽的推理故事。

## 主题
{user_theme}

## 故事类型
{template.template_name}——{template.description}

## 结构要求
- {template.suspect_count}个嫌疑人
- {template.location_count}个地点
- {template.clue_count}条线索（分三层：物理证据、关键证据、真相证据）

## 真相链（故事骨架，你需要填充具体内容）
{self._format_truth_chain(template)}

## 角色要求
{char_reqs}

## 线索要求（必须能推导出真相）
{clue_reqs}

## 需要填充的所有槽位
{slot_list}

## 输出要求
1. 返回严格的JSON对象，key对应上面的槽位名，value是填充的内容
2. 所有ID字段（如suspect_A_id）必须是纯小写英文字母，不含空格
3. 角色姓名需要符合主题设定（如邮轮场景用合适的名字）
4. 线索文本要具体生动，30-80字，用第二人称描述玩家发现的过程
5. 说话风格要有个性差异，每个角色说话方式不同
6. 所有内容必须逻辑自洽：线索指向真相，角色秘密不矛盾
7. 不要在JSON值中使用槽位占位符（如{{location_A}}），要用实际填充的内容
8. 只返回JSON，不要有任何其他文字"""

    def _format_truth_chain(self, template: StoryTemplate) -> str:
        lines = []
        for step in template.truth_chain:
            lines.append(f"  {step.order}. {step.template}")
            lines.append(f"     涉及: {', '.join(step.involves)}")
        return "\n".join(lines)

    def _format_character_requirements(self, template: StoryTemplate) -> str:
        lines = []
        for cs in template.character_slots:
            lines.append(f"### {cs.slot_id} ({cs.role_type})")
            lines.append(f"  - 与受害者关系: {cs.relation_to_victim}")
            lines.append(f"  - 秘密类型: {cs.secret_type}")
            lines.append(f"  - 红线模板: {', '.join(cs.hard_boundary_templates)}")
            lines.append(f"  - 初始信任度: {cs.trust_default}, 嫌疑度: {cs.suspicion_default}")
            lines.append("")
        return "\n".join(lines)

    def _format_clue_requirements(self, template: StoryTemplate) -> str:
        lines = []
        for cs in template.clue_slots:
            lines.append(
                f"  - [{cs.slot_id}] 层级{cs.layer} | "
                f"地点: {cs.location_slot} | "
                f"指向: {cs.points_to} | "
                f"要求: {cs.text_instruction}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
            resp = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的推理游戏编剧。你只输出JSON，不输出任何其他内容。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content or "{}"

        raise RuntimeError(f"Unsupported provider: {self.config.provider}")

    # ------------------------------------------------------------------
    # Parse & validate slots
    # ------------------------------------------------------------------

    def _parse_slots(
        self, raw: str, template: StoryTemplate
    ) -> Dict[str, str]:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            text = "\n".join(lines)

        data = json.loads(text)

        # Ensure all required slots are present
        missing = [k for k in template.slots if k not in data]
        if missing:
            raise ValueError(f"LLM response missing slots: {missing}")

        # Ensure all values are strings
        return {k: str(v) for k, v in data.items()}

"""Logic consistency validator for generated stories.

Checks structural integrity after LLM fills the template slots.
"""

from __future__ import annotations

from typing import Dict, List

from stories.templates.base_template import StoryTemplate


class StoryValidator:
    """Validates a filled template for logical consistency."""

    def validate(
        self, template: StoryTemplate, filled: Dict[str, str]
    ) -> List[str]:
        """Return a list of errors.  Empty list = all checks passed."""
        errors: List[str] = []

        self._check_required_slots(template, filled, errors)
        self._check_ids_format(filled, errors)
        self._check_locations_consistent(template, filled, errors)
        self._check_clue_texts(template, filled, errors)
        self._check_characters_distinct(filled, errors)
        self._check_truth_chain_slots(template, filled, errors)

        return errors

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_required_slots(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        errors: List[str],
    ) -> None:
        """Every slot in the template must be filled with a non-empty value."""
        for slot_name in template.slots:
            val = filled.get(slot_name, "").strip()
            if not val:
                errors.append(f"槽位 '{slot_name}' 为空")

    def _check_ids_format(
        self, filled: Dict[str, str], errors: List[str]
    ) -> None:
        """ID fields must be lowercase ASCII letters only."""
        id_fields = [k for k in filled if k.endswith("_id")]
        for field in id_fields:
            val = filled.get(field, "")
            if not val.isalpha() or not val.islower():
                errors.append(
                    f"ID字段 '{field}' = '{val}' 不是纯小写字母"
                )

    def _check_locations_consistent(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        errors: List[str],
    ) -> None:
        """Clue location slots must map to actual location values."""
        location_values = {
            filled.get("location_A", ""),
            filled.get("location_B", ""),
            filled.get("location_C", ""),
            filled.get("hidden_location", ""),
            filled.get("location_E", ""),
        }
        location_values.discard("")

        for cs in template.clue_slots:
            # Extract the slot key from the location_slot template
            # e.g. "{location_B}" -> "location_B"
            loc_key = cs.location_slot.strip("{}")
            loc_val = filled.get(loc_key, "")
            if loc_val and loc_val not in location_values:
                errors.append(
                    f"线索 {cs.slot_id} 的地点 '{loc_val}' 不在可用地点列表中"
                )

    def _check_clue_texts(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        errors: List[str],
    ) -> None:
        """Each clue must have a non-trivial text."""
        # Check that all three layers have at least one clue
        layer_counts = {1: 0, 2: 0, 3: 0}
        for cs in template.clue_slots:
            text_key = f"{cs.slot_id}_text"
            text = filled.get(text_key, "").strip()
            if text and len(text) >= 10:
                layer_counts[cs.layer] = layer_counts.get(cs.layer, 0) + 1

        if layer_counts.get(3, 0) < 2:
            errors.append("第三层线索不足2条，玩家无法推导出真相")

        for layer_num in (1, 2, 3):
            if layer_counts.get(layer_num, 0) == 0:
                errors.append(f"第{layer_num}层没有有效线索文本")

    def _check_characters_distinct(
        self, filled: Dict[str, str], errors: List[str]
    ) -> None:
        """Character names must be distinct."""
        names = []
        for key in ("suspect_A_name", "suspect_B_name", "suspect_C_name", "victim"):
            name = filled.get(key, "")
            if name:
                names.append(name)

        if len(names) != len(set(names)):
            errors.append("角色姓名有重复")

        # IDs must also be distinct
        ids = []
        for key in ("suspect_A_id", "suspect_B_id", "suspect_C_id", "victim_id"):
            id_val = filled.get(key, "")
            if id_val:
                ids.append(id_val)

        if len(ids) != len(set(ids)):
            errors.append("角色ID有重复")

    def _check_truth_chain_slots(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        errors: List[str],
    ) -> None:
        """Slots referenced in the truth chain must be filled."""
        import re

        for step in template.truth_chain:
            # Find all {slot} references in the template
            slot_refs = re.findall(r"\{(\w+)\}", step.template)
            for ref in slot_refs:
                if ref not in filled or not filled[ref].strip():
                    errors.append(
                        f"真相链步骤{step.order}引用的槽位 '{ref}' 未填充"
                    )

"""StoryTemplate data model — the skeleton that LLM fills with skin."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ClueSlot(BaseModel):
    """Template slot for a single clue."""

    slot_id: str  # "clue_layer1_a"
    layer: int  # 1=surface / 2=key / 3=truth
    location_slot: str  # "{location_A}" — to be filled
    discover_condition_template: str  # "search {location_A}"
    tension_min: int = 0  # minimum tension to discover (0/30/45/50/55)
    points_to: str  # what this clue reveals ("victim_movement"/"motive"/"truth")
    text_instruction: str  # guidance for LLM on what this clue's text should convey


class CharacterSlot(BaseModel):
    """Template slot for a character."""

    slot_id: str  # "suspect_A"
    role_type: str  # "insider"/"outsider"/"wildcard"
    relation_to_victim: str  # "employee"/"friend"/"stranger"
    secret_type: str  # "accomplice"/"guilty"/"innocent_with_secret"
    hard_boundary_templates: List[str]  # ["绝不透露{secret_object}"]
    trust_default: int = 40
    suspicion_default: int = 40
    private_knowledge_instructions: List[str]  # guidance for generating private_knowledge


class TruthChainStep(BaseModel):
    """One step in the truth chain (hidden_chain)."""

    order: int
    template: str  # "{victim}失踪前独自进入{location_A}"
    involves: List[str]  # ["victim", "suspect_A"]


class EndingCondition(BaseModel):
    """Condition for triggering an ending type."""

    ending_type: str  # "perfect"/"good"/"partial"/"fail"
    required_clue_layers: List[int]  # [1,2,3] = need all three layers
    required_truth_keywords: List[str]  # concepts player must identify


class StoryTemplate(BaseModel):
    """Complete story template skeleton.

    LLM fills the ``slots`` dict; the template guarantees structural integrity.
    """

    template_id: str
    template_name: str  # "失踪-自导自演型"
    description: str  # one-line description of when to use

    # Structure constraints
    suspect_count: int = 3
    location_count: int = 5
    clue_count: int = 9

    # Skeleton
    truth_type: str  # "self_staged" / "murder" / "conspiracy"
    truth_chain: List[TruthChainStep]
    character_slots: List[CharacterSlot]
    clue_slots: List[ClueSlot]
    ending_conditions: List[EndingCondition]

    # Opening event template
    opening_template: str  # "{setting}的{event_name}进行到一半，{victim}忽然不知所踪……"

    # Slot manifest — everything the LLM must fill
    slots: Dict[str, str]  # {slot_name: description_for_llm}

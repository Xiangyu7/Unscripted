from stories.templates.base_template import (
    CharacterSlot,
    ClueSlot,
    EndingCondition,
    StoryTemplate,
    TruthChainStep,
)
from stories.templates.self_staged import SELF_STAGED_TEMPLATE

TEMPLATE_REGISTRY: dict[str, StoryTemplate] = {
    "self_staged": SELF_STAGED_TEMPLATE,
}


def select_template(theme: str) -> StoryTemplate:
    """Select the best template for a given theme.

    Currently returns the only available template. As more templates are added,
    this can use keyword matching or LLM classification.
    """
    theme_lower = theme.lower()
    for keyword in ("失踪", "消失", "不见", "下落不明"):
        if keyword in theme_lower:
            return TEMPLATE_REGISTRY["self_staged"]
    # Default to self_staged (only template available)
    return TEMPLATE_REGISTRY["self_staged"]

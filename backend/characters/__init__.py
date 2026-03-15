"""
Character skill loader — reads .md persona files and injects into LLM prompts.

Each character has a detailed markdown "skill sheet" that defines their
personality, speaking patterns, body language, inner world, and behavioral
changes at different tension levels. This replaces hardcoded Python strings
with rich, editable documents that game writers can modify without code changes.
"""

import os
from functools import lru_cache
from typing import Dict, Optional

_CHARACTERS_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=10)
def load_character_skill(character_id: str) -> Optional[str]:
    """Load a character's .md skill file. Returns content or None."""
    path = os.path.join(_CHARACTERS_DIR, f"{character_id}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def get_all_character_skills() -> Dict[str, str]:
    """Load all character skill files. Returns {char_id: content}."""
    skills = {}
    for filename in os.listdir(_CHARACTERS_DIR):
        if filename.endswith(".md"):
            char_id = filename[:-3]
            content = load_character_skill(char_id)
            if content:
                skills[char_id] = content
    return skills

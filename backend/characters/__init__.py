"""
Character skill loader — reads .md persona files and injects into LLM prompts.

Each character has a detailed markdown "skill sheet" that defines their
personality, speaking patterns, body language, inner world, and behavioral
changes at different tension levels. This replaces hardcoded Python strings
with rich, editable documents that game writers can modify without code changes.

``build_dynamic_persona`` extracts only the sections relevant to the current
game state (tension level, trust) instead of injecting the entire document,
keeping the LLM prompt focused and token-efficient.
"""

import os
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

_CHARACTERS_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Section classification ──────────────────────────────────────────
# Sections that are always included (the character's "soul")
_ALWAYS_INCLUDE = {"性格内核", "说话方式", "身体语言", "对其他人的态度"}
# Sections that are always skipped (redundant or too meta)
_ALWAYS_SKIP = {"基本信息", "内心世界"}
# Sections with special conditional logic
_CONDITIONAL = {"秘密层级", "随tension变化的行为"}


@lru_cache(maxsize=10)
def load_character_skill(character_id: str) -> Optional[str]:
    """Load a character's .md skill file. Returns content or None."""
    path = os.path.join(_CHARACTERS_DIR, f"{character_id}.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _parse_sections(md_content: str) -> List[Tuple[str, str]]:
    """Split markdown content into (heading, body) pairs by ``## `` headings.

    Returns a list of tuples. The first element may have an empty heading
    (the preamble before the first ``## ``).
    """
    sections: List[Tuple[str, str]] = []
    current_heading = ""
    current_lines: List[str] = []

    for line in md_content.splitlines():
        if line.startswith("## "):
            # Save previous section
            if current_heading or current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_heading or current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))

    return sections


def _filter_tension_behavior(body: str, tension: int) -> str:
    """Extract only the tension bracket line matching the current tension."""
    lines = body.splitlines()
    selected: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("- tension"):
            # Keep non-bracket lines (e.g. intro text)
            if stripped:
                selected.append(line)
            continue

        # Match bracket: "- tension < 30:", "- tension 30-50:", "- tension > 70:" etc.
        if "< 30" in stripped and tension < 30:
            selected.append(line)
        elif "30-50" in stripped and 30 <= tension <= 50:
            selected.append(line)
        elif "50-70" in stripped and 50 < tension <= 70:
            selected.append(line)
        elif "> 70" in stripped and tension > 70:
            selected.append(line)

    return "\n".join(selected)


def _filter_secret_layers(body: str, tension: int) -> str:
    """Show only the secret layers that could plausibly surface at current tension.

    - tension < 30:  表面 + 第一层
    - tension 30-50: 表面 + 第一层 + 第二层
    - tension > 50:  all layers
    """
    lines = body.splitlines()
    selected: List[str] = []

    # Define which layer keywords are visible at each tension range
    always_visible = {"表面", "第一层"}
    mid_visible = always_visible | {"第二层"}
    # tension > 50 shows everything

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("- "):
            if stripped:
                selected.append(line)
            continue

        if tension > 50:
            # All layers visible
            selected.append(line)
        elif tension >= 30:
            # 表面 + 第一层 + 第二层
            if any(kw in stripped for kw in mid_visible):
                selected.append(line)
        else:
            # 表面 + 第一层 only
            if any(kw in stripped for kw in always_visible):
                selected.append(line)

    return "\n".join(selected)


def get_tension_bracket_description(tension: int) -> str:
    """Return a human-readable Chinese description of the current tension bracket."""
    if tension < 30:
        return "低张力——气氛相对平静，角色保持常态"
    elif tension <= 50:
        return "中低张力——气氛开始紧张，角色有所防备"
    elif tension <= 70:
        return "中高张力——压力明显，角色行为出现变化"
    else:
        return "高张力——气氛极度紧张，角色可能失控或暴露"


def build_dynamic_persona(
    character_id: str, tension: int, trust_to_player: int
) -> Tuple[Optional[str], str]:
    """Build a focused persona prompt by extracting only relevant skill-sheet sections.

    Args:
        character_id: Character identifier matching the .md filename.
        tension: Current game tension level (0-100).
        trust_to_player: Character's trust toward the player (0-100).

    Returns:
        A tuple of (persona_text, bracket_description).
        persona_text is None if no skill sheet exists for the character.
        bracket_description is always a valid string describing the tension bracket.
    """
    raw = load_character_skill(character_id)
    bracket_description = get_tension_bracket_description(tension)

    if raw is None:
        return None, bracket_description

    sections = _parse_sections(raw)
    output_parts: List[str] = []

    for heading, body in sections:
        if not heading:
            # Skip preamble (the # title line)
            continue

        if heading in _ALWAYS_SKIP:
            continue

        if heading in _ALWAYS_INCLUDE:
            output_parts.append(f"## {heading}\n{body}")
            continue

        if heading == "随tension变化的行为":
            filtered = _filter_tension_behavior(body, tension)
            if filtered:
                output_parts.append(f"## 当前行为模式\n{filtered}")
            continue

        if heading == "秘密层级":
            filtered = _filter_secret_layers(body, tension)
            if filtered:
                output_parts.append(f"## 秘密层级\n{filtered}")
            continue

        # Any unknown sections: skip by default (safe fallback)

    persona_text = "\n\n".join(output_parts)
    return persona_text, bracket_description


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

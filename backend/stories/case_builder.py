"""Assemble a filled template into a playable GameState.

Mirrors the structure of ``gu_family_case.create_initial_state`` so
the generated case works with the existing turn engine.
"""

from __future__ import annotations

import re
import uuid
from typing import Dict, List

from schemas.game_state import (
    Character,
    Clue,
    Event,
    FactScope,
    GameState,
    KnowledgeFact,
    KnowledgeGraph,
    StoryTruth,
)
from stories.templates.base_template import StoryTemplate


def _fact(
    fact_id: str,
    text: str,
    scope: FactScope,
    *,
    holders: list[str] | None = None,
    revealed_to_player: bool = False,
    publicly_revealed: bool = False,
    source: str = "",
    related_characters: list[str] | None = None,
    tags: list[str] | None = None,
) -> KnowledgeFact:
    return KnowledgeFact(
        id=fact_id,
        text=text,
        scope=scope,
        holders=holders or [],
        revealed_to_player=revealed_to_player,
        publicly_revealed=publicly_revealed,
        source=source,
        related_characters=related_characters or [],
        tags=tags or [],
    )


def _fill(template_str: str, slots: Dict[str, str]) -> str:
    """Replace {slot_name} placeholders with filled values."""
    result = template_str
    for key, val in slots.items():
        result = result.replace(f"{{{key}}}", val)
    return result


class CaseBuilder:
    """Build a playable GameState from a filled template."""

    def build(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        session_id: str | None = None,
    ) -> GameState:
        sid = session_id or str(uuid.uuid4())

        truth = self._build_truth(template, filled)
        characters = self._build_characters(template, filled)
        clues = self._build_clues(template, filled)
        knowledge = self._build_knowledge(template, filled, characters, clues)
        events = self._build_events(template, filled)
        scenes = self._build_scenes(filled)

        return GameState(
            session_id=sid,
            story_id=f"generated_{template.template_id}_{sid[:8]}",
            title=self._build_title(filled),
            scene=filled.get("scene_name", scenes[0]),
            phase="自由试探",
            round=0,
            tension=20,
            truth=truth,
            characters=characters,
            clues=clues,
            knowledge=knowledge,
            events=events,
            available_scenes=scenes,
            game_over=False,
            ending=None,
            max_rounds=20,
        )

    # ------------------------------------------------------------------
    # Truth
    # ------------------------------------------------------------------

    def _build_truth(
        self, template: StoryTemplate, filled: Dict[str, str]
    ) -> StoryTruth:
        hidden_chain = [
            _fill(step.template, filled) for step in template.truth_chain
        ]

        # Build core truth from the template type
        victim = filled.get("victim", "受害者")
        suspect_a = filled.get("suspect_A_name", "嫌疑人A")
        mcguffin = filled.get("mcguffin", "关键物品")

        if template.truth_type == "self_staged":
            core_truth = (
                f"{suspect_a}拿走了{mcguffin}副本，{suspect_a[0]}不是凶手。"
                f"{victim}其实是自己策划了失踪，"
                f"目的是试探身边人的真实面目。"
                f"{filled.get('suspect_B_name', '嫌疑人B')}昨晚与{victim}争执"
                f"是因为发现{victim}要{filled.get('motive_action', '修改')}{mcguffin}。"
            )
        else:
            core_truth = "。".join(hidden_chain[:3])

        return StoryTruth(
            core_truth=core_truth,
            culprit=None if template.truth_type == "self_staged" else filled.get("victim_id"),
            hidden_chain=hidden_chain,
        )

    # ------------------------------------------------------------------
    # Characters
    # ------------------------------------------------------------------

    def _build_characters(
        self, template: StoryTemplate, filled: Dict[str, str]
    ) -> List[Character]:
        characters = []
        for cs in template.character_slots:
            prefix = cs.slot_id  # "suspect_A"

            char_id = filled.get(f"{prefix}_id", prefix)
            char_name = filled.get(f"{prefix}_name", prefix)
            victim_name = filled.get("victim", "受害者")
            victim_id = filled.get("victim_id", "victim")

            # Build relation_map
            relation_map = {}
            for other_cs in template.character_slots:
                if other_cs.slot_id == cs.slot_id:
                    continue
                other_id = filled.get(f"{other_cs.slot_id}_id", other_cs.slot_id)
                view_key = f"{prefix}_view_{other_cs.slot_id.split('_')[1]}"
                relation_map[other_id] = filled.get(view_key, "保持警惕")

            # Add victim to relation_map
            victim_view_key = f"{prefix}_view_victim"
            relation_map[victim_id] = filled.get(victim_view_key, "复杂的关系")

            # Build hard_boundaries
            hard_boundaries = [
                _fill(hb, filled) for hb in cs.hard_boundary_templates
            ]

            # Build private_knowledge
            private_knowledge = [
                _fill(pk, filled) for pk in cs.private_knowledge_instructions
            ]

            # Build secret from template pattern
            secret = self._build_secret(cs, filled)

            characters.append(
                Character(
                    id=char_id,
                    name=char_name,
                    public_role=filled.get(f"{prefix}_role", cs.relation_to_victim),
                    style=filled.get(f"{prefix}_style", ""),
                    goal=filled.get(f"{prefix}_goal", ""),
                    fear=filled.get(f"{prefix}_fear", ""),
                    secret=secret,
                    private_knowledge=private_knowledge,
                    relation_map=relation_map,
                    trust_to_player=cs.trust_default,
                    suspicion=cs.suspicion_default,
                    speaking_rules=filled.get(f"{prefix}_speaking_rules", ""),
                    hard_boundaries=hard_boundaries,
                    location=filled.get("location_A", "大厅"),
                )
            )

        return characters

    def _build_secret(self, cs, filled: Dict[str, str]) -> str:
        victim = filled.get("victim", "受害者")
        mcguffin = filled.get("mcguffin", "关键物品")

        if cs.secret_type == "accomplice":
            return (
                f"受{victim}委托{filled.get('protect_action', '处理了关键物品')}，"
                f"知道{victim}失踪是自导自演"
            )
        elif cs.secret_type == "guilty":
            return f"与{victim}的失踪有直接关系"
        elif cs.secret_type == "innocent_with_secret":
            if cs.role_type == "relation":
                return (
                    f"昨晚与{victim}大吵一架，"
                    f"因为得知{victim}要{filled.get('motive_action', '处置')}{mcguffin}"
                )
            else:
                return f"收到过匿名爆料，暗示今晚{filled.get('setting', '这里')}会有大事发生"
        return "有不可告人的秘密"

    # ------------------------------------------------------------------
    # Clues
    # ------------------------------------------------------------------

    def _build_clues(
        self, template: StoryTemplate, filled: Dict[str, str]
    ) -> List[Clue]:
        clues = []
        for cs in template.clue_slots:
            text_key = f"{cs.slot_id}_text"
            text = filled.get(text_key, cs.text_instruction)
            # Resolve any remaining slot references in text
            text = _fill(text, filled)

            location_key = cs.location_slot.strip("{}")
            location = filled.get(location_key, cs.location_slot)

            # Build discover_condition by replacing slot references
            condition = _fill(cs.discover_condition_template, filled)
            if cs.tension_min > 0 and "tension" not in condition:
                condition += f" 且 tension>={cs.tension_min}"

            clues.append(
                Clue(
                    id=cs.slot_id,
                    text=text,
                    location=location,
                    discover_condition=condition,
                )
            )

        return clues

    # ------------------------------------------------------------------
    # Knowledge
    # ------------------------------------------------------------------

    def _build_knowledge(
        self,
        template: StoryTemplate,
        filled: Dict[str, str],
        characters: List[Character],
        clues: List[Clue],
    ) -> KnowledgeGraph:
        victim = filled.get("victim", "受害者")
        victim_id = filled.get("victim_id", "victim")
        setting = filled.get("setting", "现场")
        event_name = filled.get("event_name", "活动")

        char_ids = [c.id for c in characters]
        all_holders = char_ids + ["player"]

        # Public facts (opening knowledge)
        public_facts = [
            f"{filled.get('victim_title', '')}{victim}在{event_name}中途失踪",
            f"所有人暂时不能离开{setting}",
            f"今晚是{setting}的{event_name}",
        ]

        # Initialize character_beliefs
        character_beliefs = {cid: [] for cid in char_ids}

        facts: List[KnowledgeFact] = []

        # Opening public facts
        for i, pf in enumerate(public_facts):
            facts.append(
                _fact(
                    f"public_{i}",
                    pf,
                    FactScope.public,
                    holders=all_holders,
                    revealed_to_player=True,
                    publicly_revealed=True,
                    source="opening",
                    related_characters=char_ids + [victim_id],
                    tags=["opening"],
                )
            )

        # NPC private facts (from private_knowledge)
        for char in characters:
            for j, pk in enumerate(char.private_knowledge):
                facts.append(
                    _fact(
                        f"{char.id}_private_{j}",
                        pk,
                        FactScope.npc_private,
                        holders=[char.id],
                        source="backstory",
                        related_characters=[char.id, victim_id],
                        tags=["private"],
                    )
                )

        # Shared secrets
        if len(char_ids) >= 2:
            facts.append(
                _fact(
                    "shared_conflict",
                    f"这场失踪案和{setting}的{filled.get('conflict_type', '内部纠纷')}高度相关。",
                    FactScope.shared_secret,
                    holders=char_ids[1:],  # B and C know
                    source="backstory",
                    related_characters=char_ids + [victim_id],
                    tags=["shared"],
                )
            )

        # Clue-derived facts
        for cs in template.clue_slots:
            clue_fact_text = self._clue_to_fact_text(cs, filled)
            facts.append(
                _fact(
                    f"clue_{cs.slot_id}",
                    clue_fact_text,
                    FactScope.player_known,
                    source=cs.slot_id,
                    tags=["clue", f"layer{cs.layer}"],
                )
            )

        # Truth facts
        if template.truth_type == "self_staged":
            sa_name = filled.get("suspect_A_name", "嫌疑人A")
            mcguffin = filled.get("mcguffin", "关键物品")
            hidden_loc = filled.get("hidden_location", "密室")

            facts.append(
                _fact(
                    "truth_transfer",
                    f"真相是{sa_name}受{victim}委托{filled.get('protect_action', '转移了关键物品')}，{sa_name[0]}不是凶手。",
                    FactScope.truth,
                    source="truth",
                    related_characters=[char_ids[0], victim_id] if char_ids else [],
                    tags=["truth"],
                )
            )
            facts.append(
                _fact(
                    "truth_self_staged",
                    f"真相是{victim}自导自演了这场失踪案，目的是试探所有人。",
                    FactScope.truth,
                    source="truth",
                    related_characters=char_ids + [victim_id],
                    tags=["truth", "core"],
                )
            )
            facts.append(
                _fact(
                    "truth_hideout",
                    f"{victim}目前藏在{hidden_loc}中观察所有人的反应。",
                    FactScope.truth,
                    source="truth",
                    related_characters=[victim_id],
                    tags=["truth"],
                )
            )

        return KnowledgeGraph(
            public_facts=public_facts,
            player_known=[],
            character_beliefs=character_beliefs,
            facts=facts,
        )

    def _clue_to_fact_text(self, cs, filled: Dict[str, str]) -> str:
        """Generate the knowledge-graph interpretation of a clue."""
        points_to = cs.points_to
        mapping = {
            "victim_movement": "有人在事发前后经过这里——行踪有迹可循。",
            "plan_exists": "这不是偶发事件——有人提前策划了这一切。",
            "prior_knowledge": "有人事先就知道今晚会出事。",
            "motive": f"这一切与{filled.get('mcguffin', '关键物品')}有关——{filled.get('victim', '受害者')}在故意测试身边人。",
            "voluntary_hiding": "这不像被胁迫的场景，更像是有人自愿待在这里。",
            "accomplice_link": f"{filled.get('suspect_A_name', '某人')}与{filled.get('victim', '受害者')}在事后仍有联系——{filled.get('suspect_A_name', '某人')}是共谋者。",
            "victim_alive": f"{filled.get('victim', '受害者')}还活着，就藏在{filled.get('hidden_location', '某处')}。",
            "staged_scene": "所谓的'现场'是精心布置的——整场失踪是被导演的。",
        }
        return mapping.get(points_to, f"线索指向: {points_to}")

    # ------------------------------------------------------------------
    # Events & scenes
    # ------------------------------------------------------------------

    def _build_events(
        self, template: StoryTemplate, filled: Dict[str, str]
    ) -> List[Event]:
        opening_text = _fill(template.opening_template, filled)
        return [
            Event(round=0, type="opening", text=opening_text),
        ]

    def _build_scenes(self, filled: Dict[str, str]) -> List[str]:
        return [
            filled.get("location_A", "大厅"),
            filled.get("location_B", "私人房间"),
            filled.get("location_C", "户外"),
            filled.get("hidden_location", "密室"),
            filled.get("location_E", "走廊"),
        ]

    def _build_title(self, filled: Dict[str, str]) -> str:
        setting = filled.get("setting", "")
        victim = filled.get("victim", "某人")
        return f"{setting}失踪案" if setting else f"{victim}失踪案"

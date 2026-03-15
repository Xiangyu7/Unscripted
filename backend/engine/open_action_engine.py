"""
Open Action Engine — LLM-powered free-form action simulator.

Replaces the rigid intent classifier + rule judge pipeline with a world
simulator that can understand ANY player action and produce realistic
consequences.  Falls back to enhanced keyword matching when no LLM is
available.

Pipeline:
  1. Player types free-form action (Chinese)
  2. LLM (or fallback) interprets what the player is doing
  3. Engine simulates physical / social consequences in the world
  4. Returns ActionConsequence with narration, stat changes, clue discovery, etc.
"""

import json
import random
import re
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from config import Config, LLMProvider
from engine.intent_classifier import (
    CHARACTER_NAMES,
    LOCATION_NAMES,
    classify_intent,
)
from schemas.game_state import IntentType


# ═══════════════════════════════════════════════════════════════════════════
# Output model
# ═══════════════════════════════════════════════════════════════════════════


class ActionConsequence(BaseModel):
    """Result of simulating a player action in the world."""

    # ── Understanding ──
    action_summary: str = ""              # One-line summary of what player is doing
    action_category: str = "other"        # Broad category: social/investigate/manipulate/move/confront/stealth/environmental/communicate/other
    targets: List[str] = Field(default_factory=list)  # Character IDs and/or object IDs involved

    # ── Feasibility ──
    feasible: bool = True                 # Can this physically/logically happen?
    infeasible_reason: str = ""           # Why not (if not feasible)

    # ── Consequences ──
    success_level: str = "full"           # full / partial / blocked
    tension_delta: int = 0
    trust_changes: Dict[str, int] = Field(default_factory=dict)      # char_id -> delta
    suspicion_changes: Dict[str, int] = Field(default_factory=dict)  # char_id -> delta

    # ── World changes ──
    world_changes: List[Dict] = Field(default_factory=list)
    # Each dict: {"type": "modify_object"|"move_object"|"change_lighting"|..., ...params}

    # ── Clue discovery ──
    discovered_clues: List[str] = Field(default_factory=list)  # Clue IDs discovered

    # ── NPC reactions ──
    npc_reactions: Dict[str, str] = Field(default_factory=dict)   # char_id -> brief reaction
    witness_characters: List[str] = Field(default_factory=list)   # Characters who saw this

    # ── Narration ──
    narration: str = ""  # Chinese narration of what happened

    # ── Legacy compatibility ──
    legacy_intent: str = "other"  # Map back to old IntentType for backwards compat


# ═══════════════════════════════════════════════════════════════════════════
# Valid categories and legacy intent mapping
# ═══════════════════════════════════════════════════════════════════════════

VALID_CATEGORIES = [
    "social", "investigate", "manipulate", "move", "confront",
    "stealth", "environmental", "communicate", "other",
]

VALID_SUCCESS_LEVELS = ["full", "partial", "blocked"]

# Map broad action_category → legacy IntentType value
_CATEGORY_TO_LEGACY: Dict[str, str] = {
    "social": "ask",
    "communicate": "ask",
    "investigate": "search",
    "manipulate": "bluff",
    "confront": "accuse",
    "move": "move",
    "stealth": "eavesdrop",
    "environmental": "other",
    "other": "other",
}

_FAST_PATH_INTENTS = {
    IntentType.observe,
    IntentType.search,
    IntentType.move,
    IntentType.hide,
}


# ═══════════════════════════════════════════════════════════════════════════
# LLM system prompt
# ═══════════════════════════════════════════════════════════════════════════

_WORLD_SIMULATOR_SYSTEM_PROMPT = """你是一个互动推理游戏的世界模拟器。你的任务是模拟玩家行为在游戏世界中产生的后果。

游戏背景：顾家老宅（一座中式传统老宅院），一场晚宴后主人顾言神秘失踪。玩家是受邀的侦探。
三位嫌疑人：林岚（秘书，ID: linlan）、周牧（发小，ID: zhoumu）、宋知微（记者，ID: songzhi）
可用地点：宴会厅、书房、花园、酒窖、走廊

【重要：场景描写约束】
- 这是一座中国传统风格的老宅院，不是城堡、庄园、教堂或西式建筑
- narration 中必须使用"世界状态"里描述的实际场景，禁止编造不存在的地点
- 不要出现"城堡""庄园""图书馆""大教堂"等与设定不符的词
- 使用下面提供的【场景描述】中的细节来写旁白
- 如果玩家的行动涉及移动到另一个地点，必须在targets里包含目标地点名

规则：
1. 玩家可以做任何事情——不限于预设行为
2. 根据世界状态判断行为是否可行（物品是否存在、门是否锁着、人是否在场）
3. 模拟合理的物理和社交后果
4. NPC会根据性格做出反应：
   - 林岚：冷静理性，公事公办，高警惕
   - 周牧：外表大大咧咧，内心紧张，容易被激将
   - 宋知微：敏锐好奇，善于交换信息，记者本能
5. 创意行为应该被鼓励和奖励，不要轻易说"没什么影响"
6. tension_delta 范围: -5 到 +20
7. trust_changes 和 suspicion_changes 范围: -15 到 +15
8. 对于不可能的行为（飞天遁地、超自然能力），设 feasible=false 并解释原因
9. 侦探不会主动伤害他人，但可以做出威胁性或挑衅性的行为
10. 如果玩家的行动包含"去/回/前往+地点"，action_category 应设为 "move"，把目标地点放在 targets 里
11. 如果玩家同时做了两件事（如"回到宴会厅然后质问某人"），优先处理移动，narration 中描述到达后的行为

action_category 必须是以下之一：social / investigate / manipulate / move / confront / stealth / environmental / communicate / other

success_level 必须是以下之一：full / partial / blocked

你必须返回严格的JSON格式，字段如下：
{
    "action_summary": "一句话总结玩家在做什么",
    "action_category": "social/investigate/manipulate/move/confront/stealth/environmental/communicate/other",
    "targets": ["涉及的角色ID或物品名称或目标地点"],
    "feasible": true/false,
    "infeasible_reason": "如果不可行，解释原因",
    "success_level": "full/partial/blocked",
    "tension_delta": 0,
    "trust_changes": {"角色ID": 变化值},
    "suspicion_changes": {"角色ID": 变化值},
    "world_changes": [{"type": "变化类型", "detail": "具体描述"}],
    "discovered_clues": ["线索ID，如果发现了的话"],
    "npc_reactions": {"角色ID": "简短反应描述"},
    "witness_characters": ["目击角色ID"],
    "narration": "中文叙述，基于世界状态中的场景细节描写（50-150字，禁止编造不存在的场景元素）"
}

错误示范（绝对禁止）：
  ✗「你来到了城堡的图书馆」→ ✓「你来到了老宅的书房」
  ✗「庄园大门紧锁」→ ✓「老宅大门紧锁」
  ✗「教堂的钟声响起」→ ✓「走廊的挂钟响起」"""


# ═══════════════════════════════════════════════════════════════════════════
# Fallback: enhanced free-form action patterns
# ═══════════════════════════════════════════════════════════════════════════

# Each pattern: (regex_or_keywords, handler_function_name)
# Handlers return partial ActionConsequence fields as a dict.

def _detect_targets(action: str) -> List[str]:
    """Extract character IDs and location names mentioned in the action."""
    targets = []
    for name, char_id in CHARACTER_NAMES.items():
        if name in action and char_id not in targets:
            targets.append(char_id)
    for loc_key, loc_name in LOCATION_NAMES.items():
        if loc_key in action and loc_name not in targets:
            targets.append(loc_name)
    return targets


def _detect_witnesses(action: str, targets: List[str]) -> List[str]:
    """Characters who would witness the action (present at same location)."""
    # In fallback mode we can't know exact locations; assume all NPCs might see.
    # The caller can refine this with actual world state.
    char_ids = {"linlan", "zhoumu", "songzhi"}
    # Anyone targeted definitely witnesses; add a couple of random others.
    witnesses = [t for t in targets if t in char_ids]
    others = list(char_ids - set(witnesses))
    if others:
        witnesses.extend(random.sample(others, min(1, len(others))))
    return witnesses


# ── Free-form action pattern definitions ──────────────────────────────────

_FREEFORM_PATTERNS: List[Dict] = [
    # 1. Social gesture: pouring drinks, offering items
    {
        "keywords": ["倒酒", "递酒", "递过", "端茶", "送水", "分享", "倒茶", "递水", "敬酒", "倒杯", "倒了一杯", "递给"],
        "category": "social",
        "legacy": "ask",
        "tension_range": (-2, 2),
        "trust_range": (3, 5),
        "suspicion_range": (-2, 0),
        "narration_templates": [
            "你{action_verb}，这个友善的举动让气氛稍微缓和了一些。",
            "你主动{action_verb}，在场的人似乎对你的善意感到意外。",
        ],
        "summary": "做出友善的社交举动",
    },
    # 2. Destructive action: breaking things
    {
        "keywords": ["打碎", "摔", "砸", "踢翻", "掀翻", "推倒", "摔碎", "打破"],
        "category": "environmental",
        "legacy": "other",
        "tension_range": (8, 12),
        "trust_range": (-8, -3),
        "suspicion_range": (0, 3),
        "narration_templates": [
            "「砰」的一声，你{action_verb}——碎片散落一地。所有人都被这突如其来的动静惊到了。",
            "你猛地{action_verb}，声音在寂静的老宅里格外刺耳。在场的人都紧张地看向你。",
        ],
        "summary": "破坏性行为引起关注",
        "world_change_type": "modify_object",
    },
    # 3. Environmental: manipulate lighting
    {
        "keywords": ["关灯", "灭灯", "关掉灯", "熄灭", "拉闸", "开灯", "打开灯", "灯关", "灯灭", "灯打开"],
        "category": "environmental",
        "legacy": "other",
        "tension_range": (5, 10),
        "trust_range": (-3, 0),
        "suspicion_range": (0, 2),
        "narration_templates": [
            "你{action_verb}，房间陷入了{light_state}。有人发出了惊呼声。",
            "随着你{action_verb}，周围的氛围瞬间{mood_change}。",
        ],
        "summary": "改变环境光线",
        "world_change_type": "change_lighting",
    },
    # 4. Investigate personal items
    {
        "keywords": ["翻手机", "偷看手机", "检查手机", "翻包", "偷看包", "检查口袋", "翻口袋", "看手机", "翻钱包", "的手机", "的包", "的口袋"],
        "category": "investigate",
        "legacy": "search",
        "tension_range": (6, 10),
        "trust_range": (-10, -5),
        "suspicion_range": (3, 8),
        "narration_templates": [
            "你趁人不注意，悄悄{action_verb}。这是一个冒险的举动，但可能会有意外收获。",
            "你小心翼翼地{action_verb}，心跳加速——如果被发现可不好解释。",
        ],
        "summary": "偷偷检查某人的私人物品",
    },
    # 5. Secret communication: writing notes
    {
        "keywords": ["写纸条", "留便条", "写字条", "留言", "传纸条", "写信"],
        "category": "communicate",
        "legacy": "ask",
        "tension_range": (1, 3),
        "trust_range": (0, 2),
        "suspicion_range": (0, 1),
        "narration_templates": [
            "你悄悄{action_verb}，将它放在了一个只有目标能看到的地方。",
            "你快速{action_verb}，希望能传递一些不便当面说的信息。",
        ],
        "summary": "秘密传递书面信息",
    },
    # 6. Block access: barricade door
    {
        "keywords": ["堵门", "锁门", "挡住门", "堵住", "封住出口", "关门", "反锁", "门锁", "把门"],
        "category": "environmental",
        "legacy": "other",
        "tension_range": (8, 15),
        "trust_range": (-6, -2),
        "suspicion_range": (2, 5),
        "narration_templates": [
            "你{action_verb}，空气中弥漫着一股压迫感。没有人能轻易离开了。",
            "「咔嗒」——你{action_verb}。在场的人面面相觑，气氛骤然紧张起来。",
        ],
        "summary": "封锁出入口，限制行动",
        "world_change_type": "block_access",
    },
    # 7. External communication: calling police, phoning outside
    {
        "keywords": ["打电话", "报警", "拨打", "打110", "叫警察", "联系外面", "求助"],
        "category": "communicate",
        "legacy": "other",
        "tension_range": (10, 18),
        "trust_range": (-5, -1),
        "suspicion_range": (0, 3),
        "narration_templates": [
            "你拿出手机试图{action_verb}——但信号似乎很微弱。你不确定对方是否听清了你的话。",
            "你尝试{action_verb}，但老宅里的信号断断续续。不过这个举动本身就足以让所有人紧张起来。",
        ],
        "summary": "尝试联系外部世界",
    },
    # 8. Intimidation / threatening
    {
        "keywords": ["威胁", "恐吓", "吓唬", "警告", "别想跑", "给我说实话", "最后一次机会"],
        "category": "confront",
        "legacy": "accuse",
        "tension_range": (10, 16),
        "trust_range": (-12, -5),
        "suspicion_range": (5, 10),
        "narration_templates": [
            "你的语气变得凌厉，{action_verb}。空气仿佛凝固了——你能感受到对方的紧张。",
            "你向前一步，{action_verb}。对方的表情出现了明显的裂痕。",
        ],
        "summary": "通过威胁施加压力",
    },
    # 9. Comforting / empathizing
    {
        "keywords": ["安慰", "拍肩", "拍背", "安抚", "没事", "别怕", "理解你", "相信你"],
        "category": "social",
        "legacy": "ask",
        "tension_range": (-5, -1),
        "trust_range": (5, 10),
        "suspicion_range": (-3, 0),
        "narration_templates": [
            "你轻声{action_verb}，对方的防备似乎稍微卸下了一些。",
            "你真诚地{action_verb}，能看到对方眼中闪过一丝动容。",
        ],
        "summary": "安慰或表达同理心",
    },
    # 10. Examine food/drinks (poisoning check)
    {
        "keywords": ["检查食物", "闻酒", "检查饮料", "查看餐桌", "验毒", "检查杯子", "闻一闻", "尝一口"],
        "category": "investigate",
        "legacy": "search",
        "tension_range": (4, 8),
        "trust_range": (-2, 0),
        "suspicion_range": (1, 4),
        "narration_templates": [
            "你仔细{action_verb}，试图发现其中是否有什么异常。",
            "你凑近{action_verb}——一个侦探的直觉告诉你，细节往往藏在最不起眼的地方。",
        ],
        "summary": "检查食物或饮品是否有异常",
    },
    # 11. Distraction / creating diversion
    {
        "keywords": ["转移注意", "制造混乱", "声东击西", "吸引注意", "大声", "制造噪音", "故意打翻"],
        "category": "manipulate",
        "legacy": "bluff",
        "tension_range": (5, 10),
        "trust_range": (-4, -1),
        "suspicion_range": (0, 3),
        "narration_templates": [
            "你巧妙地{action_verb}，趁其他人分心的瞬间，你获得了一个短暂的行动窗口。",
            "你{action_verb}，在混乱中，你注意到有人的反应异常——这本身就是一条线索。",
        ],
        "summary": "制造干扰以转移注意力",
    },
    # 12. Follow / tail someone
    {
        "keywords": ["跟踪", "尾随", "跟着", "悄悄跟", "盯梢", "偷偷跟"],
        "category": "stealth",
        "legacy": "eavesdrop",
        "tension_range": (4, 8),
        "trust_range": (-3, 0),
        "suspicion_range": (2, 5),
        "narration_templates": [
            "你保持距离，悄悄{action_verb}。对方似乎没有察觉到你的存在——至少暂时没有。",
            "你小心翼翼地{action_verb}，在走廊的阴影中匿迹潜行。",
        ],
        "summary": "暗中跟踪某人",
    },
    # 13. Reveal information / share clues
    {
        "keywords": ["告诉", "透露", "分享线索", "展示证据", "给看", "摊牌", "公开"],
        "category": "communicate",
        "legacy": "ask",
        "tension_range": (3, 8),
        "trust_range": (2, 6),
        "suspicion_range": (-2, 3),
        "narration_templates": [
            "你决定{action_verb}，对方听完后表情复杂，似乎在重新评估局势。",
            "你把手中的信息{action_verb}。这是一步险棋——但也许能撬动僵局。",
        ],
        "summary": "主动分享信息或证据",
    },
    # 14. Set a trap
    {
        "keywords": ["设陷阱", "设圈套", "布置", "引蛇出洞", "故意留下", "放诱饵", "下套"],
        "category": "manipulate",
        "legacy": "bluff",
        "tension_range": (5, 10),
        "trust_range": (-2, 0),
        "suspicion_range": (0, 2),
        "narration_templates": [
            "你暗中{action_verb}，现在只需要等待，看谁会上钩。",
            "你精心{action_verb}，一切就绪——猎人最需要的，是耐心。",
        ],
        "summary": "设置圈套等待嫌疑人露出马脚",
    },
    # 15. Check windows / exits
    {
        "keywords": ["检查窗户", "看窗", "查看出口", "检查门窗", "试试窗", "推窗", "开窗"],
        "category": "investigate",
        "legacy": "search",
        "tension_range": (3, 6),
        "trust_range": (0, 1),
        "suspicion_range": (0, 2),
        "narration_templates": [
            "你走到窗边{action_verb}。外面一片漆黑，夜风从缝隙中灌入，带着一股阴冷的气息。",
            "你仔细{action_verb}，发现{window_detail}。这个细节也许值得记住。",
        ],
        "summary": "检查门窗和出口",
    },
    # 16. Take a photo / record evidence
    {
        "keywords": ["拍照", "录音", "录像", "拍下", "记录", "拍摄", "保存证据"],
        "category": "investigate",
        "legacy": "search",
        "tension_range": (2, 5),
        "trust_range": (-3, -1),
        "suspicion_range": (1, 4),
        "narration_templates": [
            "你掏出手机{action_verb}——有些证据，还是保留一份比较安心。",
            "你快速{action_verb}。几个人似乎注意到了你的动作，表情各异。",
        ],
        "summary": "记录现场证据",
    },
    # 17. Propose cooperation / alliance
    {
        "keywords": ["合作", "一起", "联手", "结盟", "帮我", "互相帮助", "站在我这边"],
        "category": "social",
        "legacy": "ask",
        "tension_range": (-3, 2),
        "trust_range": (4, 8),
        "suspicion_range": (-3, -1),
        "narration_templates": [
            "你提议{action_verb}。对方沉默了片刻，似乎在权衡利弊。",
            "你伸出橄榄枝{action_verb}。在这种局面下，多一个盟友总比多一个敌人好。",
        ],
        "summary": "提议合作或结盟",
    },
    # 18. Lie down / pretend to sleep or faint
    {
        "keywords": ["装睡", "装晕", "假装昏倒", "躺下", "假死", "装死", "闭眼"],
        "category": "manipulate",
        "legacy": "bluff",
        "tension_range": (3, 8),
        "trust_range": (-2, 0),
        "suspicion_range": (0, 3),
        "narration_templates": [
            "你突然{action_verb}，在场的人一阵慌乱——但也有人在冷眼观察你是否在演戏。",
            "你{action_verb}。周围传来急促的脚步声和低声交谈——你竖起耳朵，捕捉每一个细节。",
        ],
        "summary": "通过假装身体不适来观察他人反应",
    },
    # 19. Smell / listen carefully (sensory)
    {
        "keywords": ["仔细听", "侧耳", "嗅", "闻", "感受", "触摸墙壁", "摸"],
        "category": "investigate",
        "legacy": "observe",
        "tension_range": (2, 5),
        "trust_range": (0, 1),
        "suspicion_range": (0, 1),
        "narration_templates": [
            "你屏住呼吸，{action_verb}。在安静的老宅里，你似乎捕捉到了一些不寻常的{sense_detail}。",
            "你凝神{action_verb}。作为一名经验丰富的侦探，你知道有些线索是用眼睛看不到的。",
        ],
        "summary": "运用感官仔细感知环境",
    },
    # 20. Confront with evidence
    {
        "keywords": ["拿出证据", "出示", "把证据", "用证据", "证据给", "当面对质"],
        "category": "confront",
        "legacy": "accuse",
        "tension_range": (10, 18),
        "trust_range": (-8, -2),
        "suspicion_range": (5, 12),
        "narration_templates": [
            "你{action_verb}。对方的脸色瞬间变了——这一击，正中要害。",
            "你将手中的证据{action_verb}，直视对方的眼睛。空气仿佛凝固了。",
        ],
        "summary": "用证据直接对质",
    },
]


def _match_freeform_pattern(action: str) -> Optional[Dict]:
    """
    Try to match the player action against free-form patterns.
    Returns the first matching pattern dict, or None.
    """
    for pattern in _FREEFORM_PATTERNS:
        for kw in pattern["keywords"]:
            if kw in action:
                return pattern
    return None


def _build_fallback_consequence(
    action: str,
    pattern: Optional[Dict],
    targets: List[str],
) -> ActionConsequence:
    """Build an ActionConsequence from a matched free-form pattern."""
    if pattern is None:
        # Ultimate fallback: classify with legacy classifier, produce minimal result
        intent_type, metadata = classify_intent(action)
        return _legacy_intent_to_consequence(action, intent_type.value, metadata)

    char_targets = [t for t in targets if t in ("linlan", "zhoumu", "songzhi")]
    tension = random.randint(*pattern["tension_range"])
    trust = {}
    suspicion = {}
    for cid in char_targets:
        trust[cid] = random.randint(*pattern["trust_range"])
        suspicion[cid] = random.randint(*pattern["suspicion_range"])

    # If no specific character targeted, apply small changes to a random NPC
    if not char_targets:
        random_npc = random.choice(["linlan", "zhoumu", "songzhi"])
        if pattern["trust_range"][1] != 0 or pattern["trust_range"][0] != 0:
            trust[random_npc] = random.randint(*pattern["trust_range"])
        if pattern["suspicion_range"][1] != 0 or pattern["suspicion_range"][0] != 0:
            suspicion[random_npc] = random.randint(*pattern["suspicion_range"])

    narration = random.choice(pattern["narration_templates"])
    # Clean up action text for template: strip leading pronouns and truncate
    action_verb = action.strip()
    # Strip leading pronouns and common prefixes (try longest first)
    for prefix in ["我试试", "我打算", "我想要", "我想", "我要", "我去", "我来", "你", "我"]:
        if action_verb.startswith(prefix):
            action_verb = action_verb[len(prefix):]
            break
    # Strip adverbs that commonly appear in the narration template to avoid duplication
    # e.g. template has "猛地{action_verb}" and action is "猛地砸碎" → "砸碎"
    for adverb in ["猛地", "悄悄", "偷偷", "小心翼翼地", "仔细", "突然"]:
        if narration.count(adverb) > 0 and action_verb.startswith(adverb):
            action_verb = action_verb[len(adverb):]
            break
    action_verb = action_verb.strip()[:20]
    narration = narration.replace("{action_verb}", action_verb)
    narration = narration.replace("{light_state}", random.choice(["黑暗", "昏暗的光线"]))
    narration = narration.replace("{mood_change}", random.choice(["变得压抑", "变得紧张"]))
    narration = narration.replace("{window_detail}", random.choice([
        "窗户上有一道细微的划痕",
        "窗子似乎被人从外面动过",
        "窗帘后面夹着一张纸片",
    ]))
    narration = narration.replace("{sense_detail}", random.choice([
        "声响", "气味", "触感",
    ]))

    # Build world changes
    world_changes = []
    if "world_change_type" in pattern:
        world_changes.append({
            "type": pattern["world_change_type"],
            "detail": pattern["summary"],
        })

    # Generate NPC reactions
    npc_reactions = {}
    reaction_pool = {
        "linlan": [
            "微微皱眉，冷静地观察着", "不动声色地注视着一切",
            "眼神中闪过一丝警觉",
        ],
        "zhoumu": [
            "紧张地吞了口唾沫", "故作轻松地笑了笑",
            "不安地搓着手",
        ],
        "songzhi": [
            "眼睛一亮，像是发现了好素材", "迅速在本子上记了一笔",
            "嘴角微扬，饶有兴趣地观察着",
        ],
    }
    witnesses = _detect_witnesses(action, targets)
    for cid in witnesses:
        if cid in reaction_pool:
            npc_reactions[cid] = random.choice(reaction_pool[cid])

    return ActionConsequence(
        action_summary=pattern["summary"],
        action_category=pattern["category"],
        targets=targets,
        feasible=True,
        infeasible_reason="",
        success_level="full",
        tension_delta=tension,
        trust_changes=trust,
        suspicion_changes=suspicion,
        world_changes=world_changes,
        discovered_clues=[],
        npc_reactions=npc_reactions,
        witness_characters=witnesses,
        narration=narration,
        legacy_intent=pattern["legacy"],
    )


def _legacy_intent_to_consequence(
    action: str, intent_value: str, metadata: dict
) -> ActionConsequence:
    """Convert a legacy intent classification into an ActionConsequence."""
    target_char = metadata.get("target_character")
    targets = []
    if target_char:
        targets.append(target_char)
    target_loc = metadata.get("target_location")
    if target_loc:
        targets.append(target_loc)

    # Mapping intent → category
    _intent_to_cat = {
        "observe": "investigate",
        "ask": "social",
        "bluff": "manipulate",
        "search": "investigate",
        "accuse": "confront",
        "move": "move",
        "eavesdrop": "stealth",
        "hide": "stealth",
        "other": "other",
    }
    category = _intent_to_cat.get(intent_value, "other")

    # Default narration and values per intent
    _defaults: Dict[str, Dict] = {
        "observe": {
            "narration": "你仔细打量着周围的一切，试图从细节中找出端倪。",
            "tension": (3, 5), "trust": (1, 3), "suspicion": (0, 1),
            "success": "full", "summary": "观察周围环境",
        },
        "ask": {
            "narration": "你开口询问，试图从对方的回答中获取有用的信息。",
            "tension": (3, 6), "trust": (-1, 3), "suspicion": (1, 3),
            "success": "full", "summary": "向某人提问",
        },
        "bluff": {
            "narration": "你抛出了一个试探性的说法，密切观察对方的反应。",
            "tension": (8, 12), "trust": (-10, -5), "suspicion": (3, 8),
            "success": "partial", "summary": "试探或诈唬",
        },
        "search": {
            "narration": "你仔细搜查了周围，寻找可能被忽略的线索。",
            "tension": (6, 10), "trust": (-3, -1), "suspicion": (2, 5),
            "success": "full", "summary": "搜查当前区域",
        },
        "accuse": {
            "narration": "你公开提出了你的怀疑，气氛一下子紧张到了极点。",
            "tension": (12, 18), "trust": (-15, -8), "suspicion": (8, 15),
            "success": "full", "summary": "公开指控",
        },
        "move": {
            "narration": "你移动到了新的位置。",
            "tension": (1, 3), "trust": (0, 0), "suspicion": (0, 0),
            "success": "full", "summary": "移动到另一地点",
        },
        "eavesdrop": {
            "narration": "你小心翼翼地藏好自己，竖起耳朵聆听。",
            "tension": (5, 8), "trust": (0, 0), "suspicion": (0, 2),
            "success": "full" if random.random() < 0.5 else "partial",
            "summary": "偷听或暗中观察",
        },
        "hide": {
            "narration": "你决定暂时保守这个信息，等待更好的时机。",
            "tension": (0, 1), "trust": (0, 0), "suspicion": (0, 0),
            "success": "full", "summary": "隐瞒信息",
        },
        "other": {
            "narration": "你做了一些事情。虽然效果尚不明确，但老宅里的每个动作都不会被忽视。",
            "tension": (1, 4), "trust": (-1, 1), "suspicion": (0, 2),
            "success": "partial", "summary": "做了一些不寻常的事",
        },
    }

    defaults = _defaults.get(intent_value, _defaults["other"])

    trust_changes = {}
    suspicion_changes = {}
    if target_char:
        trust_changes[target_char] = random.randint(*defaults["trust"])
        suspicion_changes[target_char] = random.randint(*defaults["suspicion"])

    return ActionConsequence(
        action_summary=defaults["summary"],
        action_category=category,
        targets=targets,
        feasible=True,
        success_level=defaults["success"],
        tension_delta=random.randint(*defaults["tension"]),
        trust_changes=trust_changes,
        suspicion_changes=suspicion_changes,
        narration=defaults["narration"],
        legacy_intent=intent_value,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Infeasible action detection (fallback mode)
# ═══════════════════════════════════════════════════════════════════════════

_INFEASIBLE_KEYWORDS = [
    ("飞", "你不会飞——这里是现实世界。"),
    ("瞬移", "瞬间移动超出了人类的能力范围。"),
    ("传送", "这不是科幻游戏，你无法传送自己。"),
    ("魔法", "这个世界没有魔法。"),
    ("隐身", "你没有隐身的能力。"),
    ("杀", "作为侦探，你不会对他人痛下杀手。"),
    ("捅", "你不会对他人使用暴力伤害。"),
    ("打死", "你不会对他人使用致命暴力。"),
    ("穿墙", "墙壁是实体的，你无法穿过它。"),
    ("读心", "你无法读取他人的心思，但你可以通过观察来推断。"),
    ("时间倒流", "时间只能向前流逝。"),
    ("黑入", "你没有黑客技能——但也许可以试试别的方法。"),
]


def _check_infeasible(action: str) -> Optional[str]:
    """Check if the action is physically/logically impossible. Returns reason or None."""
    for keyword, reason in _INFEASIBLE_KEYWORDS:
        if keyword in action:
            return reason
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Main Engine class
# ═══════════════════════════════════════════════════════════════════════════


class OpenActionEngine:
    """
    LLM-powered open action engine that simulates ANY player action.

    When an LLM provider is configured, sends the action + full world context
    to the model for rich consequence simulation. Falls back to enhanced
    keyword matching with 20+ free-form action patterns when no LLM is
    available.
    """

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

    # ── Public API ────────────────────────────────────────────────────────

    async def simulate(
        self,
        player_action: str,
        world_context: str,
        characters_context: str,
        recent_history: Optional[List[str]] = None,
    ) -> ActionConsequence:
        """
        Simulate the consequences of any free-form player action.

        Args:
            player_action: Raw text the player typed (Chinese).
            world_context: Summary of current world state (location, objects,
                           lighting, time, player inventory, etc.).
            characters_context: Which characters are present and their basic
                                state (trust, suspicion, location).
            recent_history: Optional list of recent action strings for context
                            (oldest-first, typically 3-5 entries).

        Returns:
            ActionConsequence with full simulation results.
        """
        try:
            quick_intent, _ = classify_intent(player_action)
        except Exception:
            quick_intent = IntentType.other

        if quick_intent in _FAST_PATH_INTENTS:
            return self._simulate_fallback(player_action)

        # ── LLM path ──
        if self.config.provider != LLMProvider.FALLBACK and self.client is not None:
            try:
                return await self._simulate_with_llm(
                    player_action, world_context, characters_context, recent_history
                )
            except Exception as e:
                print(f"[OpenActionEngine] LLM call failed: {e}, falling back to keywords")

        # ── Fallback path ──
        return self._simulate_fallback(player_action)

    # ── LLM simulation ───────────────────────────────────────────────────

    async def _simulate_with_llm(
        self,
        player_action: str,
        world_context: str,
        characters_context: str,
        recent_history: Optional[List[str]] = None,
    ) -> ActionConsequence:
        """Send action + context to LLM and parse the consequence JSON."""
        user_prompt = self._build_user_prompt(
            player_action, world_context, characters_context, recent_history
        )

        raw: str = ""

        if self.config.provider == LLMProvider.OPENAI_COMPATIBLE:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": _WORLD_SIMULATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=800,
            )
            raw = response.choices[0].message.content or ""

        elif self.config.provider == LLMProvider.ANTHROPIC:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=800,
                system=_WORLD_SIMULATOR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.7,
            )
            raw = response.content[0].text or ""

        result = self._parse_llm_response(raw)
        if result is not None:
            return result

        # LLM returned unparseable output — fall back
        print(
            f"[OpenActionEngine] Failed to parse LLM response, falling back. "
            f"Raw: {raw[:300]}"
        )
        return self._simulate_fallback(player_action)

    # ── Fallback simulation ──────────────────────────────────────────────

    def simulate_fallback(self, player_action: str) -> ActionConsequence:
        """Public wrapper for fallback simulation (used by streaming engine)."""
        return self._simulate_fallback(player_action)

    def _simulate_fallback(self, player_action: str) -> ActionConsequence:
        """
        Enhanced keyword-based action simulation.

        Tries free-form patterns first, then falls back to legacy intent
        classification. Checks for infeasible actions.
        """
        # 1. Check infeasibility
        infeasible_reason = _check_infeasible(player_action)
        if infeasible_reason:
            return ActionConsequence(
                action_summary="不可能的行为",
                action_category="other",
                targets=_detect_targets(player_action),
                feasible=False,
                infeasible_reason=infeasible_reason,
                success_level="blocked",
                tension_delta=0,
                narration=f"你想这么做，但是——{infeasible_reason}",
                legacy_intent="other",
            )

        # 2. Try free-form pattern matching
        targets = _detect_targets(player_action)
        pattern = _match_freeform_pattern(player_action)
        if pattern is not None:
            return _build_fallback_consequence(player_action, pattern, targets)

        # 3. Fall back to legacy intent classification
        return _build_fallback_consequence(player_action, None, targets)

    # ── Prompt builders ──────────────────────────────────────────────────

    def _build_user_prompt(
        self,
        player_action: str,
        world_context: str,
        characters_context: str,
        recent_history: Optional[List[str]] = None,
    ) -> str:
        """Build the user message for the LLM world simulator."""
        parts: List[str] = []

        parts.append("【当前世界状态】")
        parts.append(world_context)
        parts.append("")

        parts.append("【在场角色】")
        parts.append(characters_context)
        parts.append("")

        if recent_history:
            parts.append("【最近行动记录】")
            history_slice = recent_history[-5:]  # Last 3-5 entries
            for i, entry in enumerate(history_slice, 1):
                parts.append(f"  {i}. {entry}")
            parts.append("")

        parts.append(f"【玩家当前行动】\n{player_action}")

        return "\n".join(parts)

    def _build_world_context(
        self,
        world_summary: str,
        characters_present: List[str],
    ) -> str:
        """
        Build the world context section of the prompt.

        Combines the world summary with a list of characters present.
        Useful for callers who want to construct world_context externally.
        """
        parts: List[str] = [world_summary, ""]
        if characters_present:
            parts.append("在场人物：" + "、".join(characters_present))
        return "\n".join(parts)

    # ── Response parsing ─────────────────────────────────────────────────

    def _parse_llm_response(self, raw_text: str) -> Optional[ActionConsequence]:
        """
        Parse LLM JSON output into an ActionConsequence.

        Handles:
        - Markdown code fences (```json ... ```)
        - Extra text around the JSON object
        - Missing fields (uses sensible defaults)
        - Out-of-range numeric values (clamped)

        Returns None if parsing fails completely.
        """
        text = raw_text.strip()
        if not text:
            return None

        # Strip markdown code fences
        if text.startswith("```"):
            # Remove opening ```json or ``` line
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            else:
                text = text[3:]
            # Remove closing ```
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]

        # Try to extract a JSON object from raw text
        # Use a greedy match that finds the outermost { ... }
        brace_start = text.find("{")
        if brace_start == -1:
            return None

        # Find matching closing brace
        depth = 0
        brace_end = -1
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break

        if brace_end == -1:
            return None

        json_str = text[brace_start:brace_end + 1]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        # ── Extract and validate fields ──

        action_summary = str(data.get("action_summary", ""))
        action_category = str(data.get("action_category", "other"))
        if action_category not in VALID_CATEGORIES:
            action_category = "other"

        targets = data.get("targets", [])
        if not isinstance(targets, list):
            targets = []
        targets = [str(t) for t in targets]

        feasible = bool(data.get("feasible", True))
        infeasible_reason = str(data.get("infeasible_reason", ""))

        success_level = str(data.get("success_level", "full"))
        if success_level not in VALID_SUCCESS_LEVELS:
            success_level = "full"

        # Clamp numeric values
        tension_delta = _clamp_int(data.get("tension_delta", 0), -5, 20)

        trust_changes = _parse_int_dict(data.get("trust_changes", {}), -15, 15)
        suspicion_changes = _parse_int_dict(data.get("suspicion_changes", {}), -15, 15)

        world_changes = data.get("world_changes", [])
        if not isinstance(world_changes, list):
            world_changes = []

        discovered_clues = data.get("discovered_clues", [])
        if not isinstance(discovered_clues, list):
            discovered_clues = []
        discovered_clues = [str(c) for c in discovered_clues]

        npc_reactions = data.get("npc_reactions", {})
        if not isinstance(npc_reactions, dict):
            npc_reactions = {}
        npc_reactions = {str(k): str(v) for k, v in npc_reactions.items()}

        witness_characters = data.get("witness_characters", [])
        if not isinstance(witness_characters, list):
            witness_characters = []
        witness_characters = [str(w) for w in witness_characters]

        narration = str(data.get("narration", ""))

        # Compute legacy intent from action_category
        legacy_intent = _CATEGORY_TO_LEGACY.get(action_category, "other")

        return ActionConsequence(
            action_summary=action_summary,
            action_category=action_category,
            targets=targets,
            feasible=feasible,
            infeasible_reason=infeasible_reason,
            success_level=success_level,
            tension_delta=tension_delta,
            trust_changes=trust_changes,
            suspicion_changes=suspicion_changes,
            world_changes=world_changes,
            discovered_clues=discovered_clues,
            npc_reactions=npc_reactions,
            witness_characters=witness_characters,
            narration=narration,
            legacy_intent=legacy_intent,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Utility helpers
# ═══════════════════════════════════════════════════════════════════════════


def _clamp_int(value, lo: int, hi: int) -> int:
    """Safely parse and clamp an integer value."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    return max(lo, min(hi, v))


def _parse_int_dict(raw, lo: int, hi: int) -> Dict[str, int]:
    """Parse a dict of string->int, clamping values to [lo, hi]."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        try:
            result[str(k)] = _clamp_int(v, lo, hi)
        except (TypeError, ValueError):
            continue
    return result

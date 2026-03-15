"""
NPC Autonomy Agent — simulates independent NPC behaviour each turn.

While the player explores one location, every NPC has their own agenda and acts
accordingly.  Actions produce *evidence* (moved objects, sounds, dropped items)
that the player can discover later, creating a living world with hidden
storylines.

This is pure game logic — no LLM calls.  All NPC behaviour is driven by
pre-written action pools, round number, tension, discovered clues, and the
psychological state produced by ``CharacterPsychologyAgent``.

Usage:
    autonomy = NPCAutonomyAgent()

    # At the start of each turn, after the player acts:
    actions = autonomy.simulate_npc_turns(
        session_id="abc",
        player_location="书房",
        round_num=7,
        tension=45,
        discovered_clues=["study_scratches"],
        psych_states={"linlan": {...}, "zhoumu": {...}, "songzhi": {...}},
    )

    # Get only what the player can perceive:
    visible = autonomy.get_visible_actions("abc", "书房")

    # On a later visit, check for evidence left behind:
    evidence = autonomy.get_evidence_at_location("abc", "花园")
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NPCAction(BaseModel):
    """An action an NPC takes autonomously."""
    character_id: str
    character_name: str
    action: str                          # What they're doing (Chinese)
    location: str                        # Where they do it
    previous_location: str = ""          # Where they were
    moved: bool = False                  # Did they change location?
    visible_to_player: bool = False      # Is the player in the same location?
    evidence_left: Optional[str] = None  # Evidence of the action (footprints, moved objects, etc.)
    sound_generated: Optional[str] = None  # Sound that could be heard from adjacent rooms
    world_changes: List[Dict] = Field(default_factory=list)  # Changes to world state


class NPCAutonomyState(BaseModel):
    """Tracks each NPC's autonomous behaviour plan."""
    character_id: str
    long_term_goal: str = ""
    current_goal: str                    # What they're currently trying to accomplish
    current_plan: str = ""
    fallback_plan: str = ""
    next_action_pool: str = ""
    plan_step: int = 0
    planned_actions: List[str] = Field(default_factory=list)
    completed_actions: List[str] = Field(default_factory=list)
    knowledge_updates: List[str] = Field(default_factory=list)
    stress_level: float = 0.0           # Affects decision-making
    last_outcome: str = ""
    last_revision_round: int = 0


# ---------------------------------------------------------------------------
# Room adjacency (for sound propagation)
# ---------------------------------------------------------------------------

# Adjacency mapping.  走廊 connects to every room.
# Sound from 酒窖 is faint through the staircase.
ADJACENT_ROOMS: Dict[str, List[str]] = {
    "宴会厅": ["走廊", "花园"],
    "书房":   ["走廊"],
    "花园":   ["宴会厅", "走廊"],
    "酒窖":   ["走廊"],
    "走廊":   ["宴会厅", "书房", "花园", "酒窖"],
}

# Rooms where sound from 酒窖 arrives *faintly* (needs extra description).
_FAINT_SOUND_SOURCES = {"酒窖"}

ALL_LOCATIONS = ["宴会厅", "书房", "花园", "酒窖", "走廊"]


# ---------------------------------------------------------------------------
# Character metadata
# ---------------------------------------------------------------------------

_CHAR_NAMES: Dict[str, str] = {
    "linlan":  "林岚",
    "zhoumu":  "周牧",
    "songzhi": "宋知微",
}

_ALL_CHAR_IDS = ["linlan", "zhoumu", "songzhi"]


# ---------------------------------------------------------------------------
# Pre-defined action pools (Chinese descriptions)
# ---------------------------------------------------------------------------
# Structure:  character_id -> situation_key -> list of (action_text, kwargs)
# kwargs may include: location, evidence_left, sound_generated, world_changes

_LINLAN_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    # ── Calm / early game ──
    "idle_banquet": [
        {
            "action": "林岚站在宴会厅角落，目光不动声色地扫视着每个人的表情。",
            "location": "宴会厅",
        },
        {
            "action": "林岚端起一杯红酒，慢慢啜饮，眼神始终盯着大门方向。",
            "location": "宴会厅",
        },
        {
            "action": "林岚翻看手机，表情平静如水，偶尔用指尖轻敲屏幕。",
            "location": "宴会厅",
        },
        {
            "action": "林岚整理着宴会厅的花瓶，动作机械，似乎在思考别的事情。",
            "location": "宴会厅",
            "evidence_left": "宴会厅的花瓶位置似乎被人动过",
        },
        {
            "action": "林岚站在窗边，低头看着手表，嘴唇微微翕动像在默数时间。",
            "location": "宴会厅",
        },
    ],

    # ── Checking study (when clues found there) ──
    "check_study": [
        {
            "action": "林岚悄悄走进书房，快速翻看了书桌上的文件，然后恢复原样。",
            "location": "书房",
            "evidence_left": "书房桌上的文件顺序似乎和之前不太一样",
            "sound_generated": "书房里传来轻微的纸张翻动声",
            "world_changes": [{"type": "object_state", "target": "书房_文件", "from": "untouched", "to": "slightly_rearranged"}],
        },
        {
            "action": "林岚打开书房的抽屉检查了一下，又迅速关上，脸色微变。",
            "location": "书房",
            "evidence_left": "书房抽屉没有完全关好，露出一条缝",
            "sound_generated": "书房传来抽屉开合的声响",
            "world_changes": [{"type": "object_state", "target": "书房_抽屉", "from": "closed", "to": "slightly_open"}],
        },
        {
            "action": "林岚蹲在书房的书架前，手指快速划过书脊，似乎在寻找什么。",
            "location": "书房",
            "evidence_left": "书架上有几本书被抽出又插回去的痕迹",
        },
        {
            "action": "林岚站在书房窗前，手指划过窗台，检查是否有人从窗户进出。",
            "location": "书房",
        },
        {
            "action": "林岚仔细检查了书房门锁，用衣袖擦拭了门把手。",
            "location": "书房",
            "evidence_left": "书房门把手上的指纹被人擦拭过",
            "world_changes": [{"type": "object_state", "target": "书房_门把手", "from": "has_scratches", "to": "wiped_clean"}],
        },
    ],

    # ── Secret phone activity (tension > 50) ──
    "secret_phone": [
        {
            "action": "林岚走到走廊尽头，背对众人低声打了一个电话。",
            "location": "走廊",
            "evidence_left": "林岚的手机屏幕亮了一下",
            "sound_generated": "走廊尽头传来低沉的说话声",
        },
        {
            "action": "林岚快速编辑了一条短信，又反复修改了几次才发送。",
            "location": "走廊",
            "evidence_left": "林岚的手机通知灯闪了几下",
        },
        {
            "action": "林岚接了一个电话，只说了一句「知道了」就挂断了。",
            "location": "走廊",
            "sound_generated": "有人在走廊低声说了句什么",
        },
        {
            "action": "林岚打开手机查看了什么信息，表情从平静变得凝重。",
            "location": "宴会厅",
            "evidence_left": "林岚的手机屏幕亮了一下",
        },
        {
            "action": "林岚躲到花园角落里拨打电话，压低了声音，表情严肃。",
            "location": "花园",
            "sound_generated": "花园传来极轻的说话声",
            "evidence_left": "花园角落的草地上有新的高跟鞋印",
        },
    ],

    # ── Warn Gu Yan (tension > 70) ──
    "warn_guyan": [
        {
            "action": "林岚借口去取东西，快步走向酒窖方向。",
            "location": "酒窖",
            "evidence_left": "酒窖入口处有一双高跟鞋留下的新脚印",
            "sound_generated": "楼梯方向传来高跟鞋的急促脚步声",
            "world_changes": [{"type": "object_state", "target": "酒窖_门", "from": "closed", "to": "unlocked"}],
        },
        {
            "action": "林岚找到通往酒窖的楼梯，向下面低声喊了几句什么。",
            "location": "酒窖",
            "sound_generated": "酒窖方向传来隐约的人声",
            "evidence_left": "酒窖楼梯扶手上沾了一点口红印",
        },
        {
            "action": "林岚在酒窖门口来回踱步，犹豫不决，最终轻轻敲了三下门。",
            "location": "酒窖",
            "sound_generated": "远处传来三声沉闷的敲门声",
            "evidence_left": "酒窖门上有新的指痕",
        },
        {
            "action": "林岚从酒窖匆匆返回，裙角沾了点灰，她不自然地拍了拍。",
            "location": "走廊",
            "evidence_left": "走廊地面上有一小撮酒窖方向带来的灰尘",
        },
        {
            "action": "林岚向酒窖方向塞了一张纸条，然后迅速离开。",
            "location": "酒窖",
            "evidence_left": "酒窖门缝里似乎有一角白色纸片",
            "sound_generated": "有人在楼梯附近快步走过",
            "world_changes": [{"type": "item_placed", "target": "酒窖_纸条", "description": "门缝里的纸条"}],
        },
    ],

    # ── Search for torn letter pieces (player found torn_letter) ──
    "search_letter": [
        {
            "action": "林岚在花园灌木丛中仔细翻找，似乎在寻找什么碎片。",
            "location": "花园",
            "evidence_left": "花园灌木丛被人翻动过，有几片叶子散落在地上",
            "sound_generated": "花园里传来翻动灌木丛的窸窣声",
        },
        {
            "action": "林岚蹲在花园小径旁，捡起了几片纸屑塞进口袋。",
            "location": "花园",
            "evidence_left": "花园小径上残留了几片碎纸屑，似乎有人捡走了大部分",
            "world_changes": [{"type": "object_state", "target": "花园_碎纸", "from": "scattered", "to": "partially_collected"}],
        },
        {
            "action": "林岚在花园石凳下方摸索，取出一个信封角，看了一眼就藏进衣服里。",
            "location": "花园",
            "evidence_left": "石凳下方的泥土有被翻动的痕迹",
        },
        {
            "action": "林岚假装赏花，实际上目光一直在搜索地面上的纸片。",
            "location": "花园",
        },
        {
            "action": "林岚在花园的垃圾桶里翻了翻，取出一张揉皱的纸片仔细辨认。",
            "location": "花园",
            "evidence_left": "花园垃圾桶的盖子没有盖好",
            "world_changes": [{"type": "object_state", "target": "花园_垃圾桶", "from": "closed", "to": "lid_ajar"}],
        },
    ],

    # ── Desperate contact (desperation > 0.6) ──
    "desperate_contact": [
        {
            "action": "林岚躲在走廊死角，用颤抖的手拨通了一个号码。",
            "location": "走廊",
            "sound_generated": "走廊深处传来压低的、焦急的说话声",
            "evidence_left": "走廊角落的墙壁上留下了指甲刮过的痕迹",
        },
        {
            "action": "林岚冲向酒窖，用力拍了两下门，低声说：「情况不对，你必须有所准备。」",
            "location": "酒窖",
            "sound_generated": "酒窖方向传来两声沉闷的拍门声和急促的低语",
            "evidence_left": "酒窖门上留下了掌印",
            "world_changes": [{"type": "event", "description": "林岚试图联系酒窖里的人"}],
        },
        {
            "action": "林岚在花园角落，对着手机急促地说：「不能再拖了，他快发现了。」",
            "location": "花园",
            "sound_generated": "花园传来急促而压低的女声",
            "evidence_left": "花园角落的草被人来回踩踏，留下焦虑踱步的痕迹",
        },
        {
            "action": "林岚表情失控了一瞬，赶紧背过身去，从包里取出一张写好的纸条藏到花瓶底下。",
            "location": "宴会厅",
            "evidence_left": "宴会厅花瓶底下似乎藏了什么东西",
            "world_changes": [{"type": "item_placed", "target": "宴会厅_花瓶_纸条", "description": "花瓶底下的纸条"}],
        },
        {
            "action": "林岚走到一个无人注意的角落，深吸一口气，双手微微发抖。她低头发了一条加密消息。",
            "location": "走廊",
            "evidence_left": "走廊角落的地面上有来回踱步的鞋印",
        },
    ],
}


_ZHOUMU_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    # ── Drinking / nervous at banquet ──
    "idle_banquet": [
        {
            "action": "周牧靠在吧台边，一杯接一杯地喝着威士忌，手指不停敲打杯壁。",
            "location": "宴会厅",
            "world_changes": [{"type": "object_state", "target": "宴会厅_酒", "from": "full", "to": "depleting"}],
        },
        {
            "action": "周牧坐在沙发上，一会儿翻手机，一会儿抬头看门口，坐立不安。",
            "location": "宴会厅",
        },
        {
            "action": "周牧端着酒杯在宴会厅里漫无目的地走来走去，偶尔对着空气干笑两声。",
            "location": "宴会厅",
            "evidence_left": "吧台上多了几个空酒杯",
            "world_changes": [{"type": "counter", "target": "宴会厅_空酒杯", "delta": 2}],
        },
        {
            "action": "周牧猛地灌了一大口酒，被呛到咳嗽了几声，惹得旁人侧目。",
            "location": "宴会厅",
            "sound_generated": "宴会厅传来一阵咳嗽声",
        },
        {
            "action": "周牧独自坐在角落里，反复看着手机上的一条消息，眉头紧锁。",
            "location": "宴会厅",
        },
    ],

    # ── Restless wandering (tension > 30) ──
    "restless_wander": [
        {
            "action": "周牧说了句「我透透气」就走出了宴会厅，在走廊里来回踱步。",
            "location": "走廊",
            "evidence_left": "走廊地毯上有明显的来回踩踏痕迹",
            "sound_generated": "走廊里有人来回走动的脚步声",
        },
        {
            "action": "周牧靠在走廊的墙上，掏出烟想点却没点着，又塞了回去。",
            "location": "走廊",
            "evidence_left": "走廊墙角有一根未点燃的烟掉在地上",
        },
        {
            "action": "周牧在走廊里对着窗户外面发呆，不知道在想什么。",
            "location": "走廊",
        },
        {
            "action": "周牧走到走廊尽头又折返回来，这样重复了好几遍。",
            "location": "走廊",
            "sound_generated": "走廊里有反复来回的脚步声",
        },
        {
            "action": "周牧在走廊里掏出手机，看了一眼又锁屏，神经质地重复着这个动作。",
            "location": "走廊",
        },
    ],

    # ── Avoiding wine cellar (player found wine_cellar_footprint) ──
    "avoid_cellar": [
        {
            "action": "周牧路过通往酒窖的楼梯口时明显加快了脚步，目光不敢往下看。",
            "location": "走廊",
            "evidence_left": "楼梯口附近的地面上有匆忙走过的鞋印",
        },
        {
            "action": "周牧特意绕了远路避开酒窖方向，假装在欣赏走廊上的画。",
            "location": "走廊",
        },
        {
            "action": "有人提到酒窖，周牧的身体明显僵了一下，随即装作没听到。",
            "location": "宴会厅",
        },
        {
            "action": "周牧走到走廊分岔口，犹豫了一下，选择了远离酒窖的方向。",
            "location": "走廊",
        },
        {
            "action": "周牧端着酒杯走向走廊，经过酒窖入口时手抖了一下，酒洒了几滴。",
            "location": "走廊",
            "evidence_left": "走廊靠近酒窖入口处的地面上有几滴酒渍",
        },
    ],

    # ── Getting air in garden (tension > 50) ──
    "garden_calm": [
        {
            "action": "周牧独自坐在花园石凳上，双手抱头，深深地呼了几口气。",
            "location": "花园",
            "evidence_left": "花园石凳旁有一个被揉皱的纸巾",
        },
        {
            "action": "周牧在花园里来回走动，嘴里念叨着什么，偶尔踢一下小石子。",
            "location": "花园",
            "evidence_left": "花园小径上的石子被踢散了",
            "sound_generated": "花园里有人走来走去的脚步声",
        },
        {
            "action": "周牧蹲在花园的喷泉旁边，用凉水拍了拍脸，像是在让自己冷静下来。",
            "location": "花园",
            "evidence_left": "喷泉边的地面上有水渍",
        },
        {
            "action": "周牧靠在花园的树上，仰头看着天空，长长地叹了一口气。",
            "location": "花园",
        },
        {
            "action": "周牧坐在花园台阶上，把脸埋在膝盖里，肩膀微微颤抖。",
            "location": "花园",
            "sound_generated": "花园里传来压抑的叹息声",
        },
    ],

    # ── Sneaking toward cellar (tension > 60, curiosity + guilt) ──
    "sneak_cellar": [
        {
            "action": "周牧鬼鬼祟祟地走向酒窖楼梯，探头往下张望了几眼。",
            "location": "酒窖",
            "evidence_left": "酒窖楼梯口的灰尘上有新的脚印",
            "sound_generated": "楼梯方向传来小心翼翼的脚步声",
        },
        {
            "action": "周牧下到酒窖入口处，侧耳倾听了一会儿，脸色越来越白。",
            "location": "酒窖",
            "sound_generated": "酒窖入口处有微弱的动静",
            "evidence_left": "酒窖门框上有人扶过的手印",
        },
        {
            "action": "周牧拿着手机的手电筒功能，在酒窖楼梯上照了照，但没敢走下去。",
            "location": "走廊",
            "evidence_left": "酒窖楼梯上方有手电光照过的痕迹（墙上蜘蛛网被碰落）",
            "sound_generated": "楼梯方向传来几声轻轻的脚步",
        },
        {
            "action": "周牧壮着胆子走进酒窖，在酒架之间搜索了一番，什么也没找到就离开了。",
            "location": "酒窖",
            "evidence_left": "酒窖里有几瓶酒的位置发生了变化",
            "sound_generated": "酒窖里传来酒瓶碰撞的叮当声",
            "world_changes": [{"type": "object_state", "target": "酒窖_酒架", "from": "orderly", "to": "slightly_disturbed"}],
        },
        {
            "action": "周牧走到酒窖深处，突然听到一声动静，吓得转身就跑。",
            "location": "走廊",
            "sound_generated": "酒窖方向传来急促的奔跑声和碰倒什么东西的声音",
            "evidence_left": "酒窖入口到走廊之间有慌张奔跑的鞋印",
        },
    ],

    # ── Retreat when accused ──
    "retreat": [
        {
            "action": "周牧默默退到走廊里，背靠着墙壁，双手插在口袋里。",
            "location": "走廊",
        },
        {
            "action": "周牧快步离开房间，在走廊里猛踹了一脚墙壁。",
            "location": "走廊",
            "sound_generated": "走廊传来一声闷响",
            "evidence_left": "走廊墙面上多了一个鞋印",
        },
        {
            "action": "周牧甩门而出，走廊里回荡着他粗重的呼吸声。",
            "location": "走廊",
            "sound_generated": "门被用力关上，走廊里有粗重的喘息声",
        },
        {
            "action": "周牧躲到走廊尽头的阴影里，蹲下来抱着头。",
            "location": "走廊",
        },
        {
            "action": "周牧逃到走廊，掏出手机犹豫着要不要打某个电话。",
            "location": "走廊",
            "evidence_left": "走廊地上有一张从口袋里带出的收据",
        },
    ],

    # ── Open sealed letter (desperation > 0.5) ──
    "open_letter": [
        {
            "action": "周牧从内衣口袋里掏出一封密封的信，手指在封口处来回摩挲。",
            "location": "走廊",
            "evidence_left": "走廊角落发现一小片撕破的信封纸",
        },
        {
            "action": "周牧终于撕开了那封一直随身带着的信，看完后脸色煞白。",
            "location": "走廊",
            "evidence_left": "走廊垃圾桶里有一个被撕开的信封",
            "sound_generated": "走廊里有人倒抽一口凉气",
            "world_changes": [{"type": "event", "description": "周牧打开了顾言留给他的信"}],
        },
        {
            "action": "周牧颤抖着打开信封，读了几行就把信揉成一团塞回口袋。",
            "location": "花园",
            "evidence_left": "花园地面上有一小块信封碎片",
        },
        {
            "action": "周牧把信举到眼前反复看了三遍，嘴唇在哆嗦。",
            "location": "走廊",
        },
        {
            "action": "周牧拆开信后愣了很久，然后突然把信塞进最近的花盆里。",
            "location": "宴会厅",
            "evidence_left": "宴会厅某个花盆的泥土被人翻动过",
            "world_changes": [{"type": "item_placed", "target": "宴会厅_花盆_信", "description": "花盆里藏了一封信"}],
        },
    ],

    # ── Nervous phone check (any time) ──
    "phone_check": [
        {
            "action": "周牧掏出手机看了一眼，快速锁屏，又看了一眼，又锁屏。",
            "location": "宴会厅",
        },
        {
            "action": "周牧的手机响了一下，他看到来电显示后直接挂断了。",
            "location": "宴会厅",
            "sound_generated": "宴会厅里一部手机响了一声就被掐断了",
        },
        {
            "action": "周牧低头发了一条短信，发完后又立刻把消息删了。",
            "location": "走廊",
        },
        {
            "action": "周牧拿着手机对着屏幕发呆，像是在等某个人的回复。",
            "location": "宴会厅",
        },
        {
            "action": "周牧的手机一直在震动，他按下静音，但手仍然握着手机不放。",
            "location": "宴会厅",
        },
    ],
}


_SONGZHI_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    # ── Early investigation ──
    "early_investigate": [
        {
            "action": "宋知微拿出手机，悄悄拍了几张宴会厅的全景照片。",
            "location": "宴会厅",
            "evidence_left": "有人可能注意到了一道轻微的闪光",
            "sound_generated": "宴会厅里传来轻微的手机快门声",
        },
        {
            "action": "宋知微拿着小本子走到每位宾客身边，以闲聊的方式记录信息。",
            "location": "宴会厅",
        },
        {
            "action": "宋知微仔细检查了宴会厅的布置，特别关注了出入口的位置。",
            "location": "宴会厅",
            "evidence_left": "宴会厅出入口附近有被翻动过的装饰物",
        },
        {
            "action": "宋知微在宴会厅角落支起手机，似乎在录像。",
            "location": "宴会厅",
            "evidence_left": "宴会厅角落有一部手机靠在花瓶上，镜头朝向大厅",
            "world_changes": [{"type": "item_placed", "target": "宴会厅_录像手机", "description": "角落里有一部正在录像的手机"}],
        },
        {
            "action": "宋知微翻看了桌上的宾客签到册，并用手机拍了下来。",
            "location": "宴会厅",
            "evidence_left": "宾客签到册被翻到了新的一页",
        },
    ],

    # ── Scooping the player (going to unsearched locations) ──
    "scoop_search": [
        {
            "action": "宋知微独自走进书房，快速扫视了房间一圈，在笔记本上记了几笔。",
            "location": "书房",
            "evidence_left": "书房门是虚掩的，之前是关着的",
            "sound_generated": "书房里有轻微的脚步声和翻动物品的声音",
            "world_changes": [{"type": "object_state", "target": "书房_门", "from": "closed", "to": "ajar"}],
        },
        {
            "action": "宋知微摸到了花园，蹲在灌木丛旁仔细查看。",
            "location": "花园",
            "evidence_left": "花园灌木丛旁的泥土上有膝盖跪压的痕迹",
        },
        {
            "action": "宋知微走向走廊，检查了各个房间门口的情况。",
            "location": "走廊",
            "evidence_left": "走廊里某些房间的门把手上有新的擦痕",
        },
        {
            "action": "宋知微大胆地走向酒窖方向，在入口处探头观察了一番。",
            "location": "酒窖",
            "evidence_left": "酒窖入口处有女性鞋印",
            "sound_generated": "酒窖方向有轻微的脚步声",
        },
        {
            "action": "宋知微检查了走廊墙上的相框和挂饰，寻找隐藏的线索。",
            "location": "走廊",
            "evidence_left": "走廊的一幅画被人挪动过，露出了后面的墙壁",
        },
    ],

    # ── Follow up on player's clue ──
    "follow_clue": [
        {
            "action": "宋知微匆匆赶到玩家刚才发现线索的地方，开始自己的二次搜索。",
            "location": "书房",  # overridden dynamically
            "evidence_left": "现场有被二次翻动的痕迹",
        },
        {
            "action": "宋知微在线索发现地附近反复踱步，低头寻找更多细节。",
            "location": "书房",
            "evidence_left": "地面上有额外的脚印，显然不止一个人来过",
        },
        {
            "action": "宋知微用手机拍摄了线索现场的每个角落，闪光灯闪了好几次。",
            "location": "书房",
            "sound_generated": "有连续的手机闪光灯声音从远处传来",
            "evidence_left": "可能有人注意到了频繁的闪光",
        },
        {
            "action": "宋知微拿出放大镜仔细端详发现线索的位置，嘴里轻声自语。",
            "location": "书房",
        },
        {
            "action": "宋知微在笔记本上画了一张简单的现场示意图。",
            "location": "书房",
            "evidence_left": "现场发现一张被撕下的笔记本纸角",
        },
    ],

    # ── Secret recording (tension > 40) ──
    "secret_record": [
        {
            "action": "宋知微不动声色地打开了手机录音功能，放进外套口袋。",
            "location": "宴会厅",
            "world_changes": [{"type": "event", "description": "宋知微开始秘密录音"}],
        },
        {
            "action": "宋知微调整了胸前的胸针——那其实是一个微型录音器。",
            "location": "走廊",
            "evidence_left": "走廊的镜子里可以看到宋知微胸前的胸针在闪光",
        },
        {
            "action": "宋知微靠近正在交谈的人，手里拿着手机装作看新闻，实际在录音。",
            "location": "宴会厅",
        },
        {
            "action": "宋知微在走廊拐角处架好了手机，悄悄开始录像。",
            "location": "走廊",
            "evidence_left": "走廊拐角处有一部手机用纸杯支着，镜头对着过道",
            "world_changes": [{"type": "item_placed", "target": "走廊_隐藏摄像", "description": "拐角处藏着录像手机"}],
        },
        {
            "action": "宋知微把录音笔藏在桌上的餐巾纸下面。",
            "location": "宴会厅",
            "evidence_left": "餐巾纸下面隐约露出一个小黑盒子的边角",
            "world_changes": [{"type": "item_placed", "target": "宴会厅_录音笔", "description": "餐巾纸下藏的录音笔"}],
        },
    ],

    # ── Found something on her own (tension > 60) ──
    "own_discovery": [
        {
            "action": "宋知微在书房角落发现了一张半藏着的收据，上面有最近的药房购买记录。",
            "location": "书房",
            "evidence_left": "书房角落有一张被翻出来的收据",
            "world_changes": [{"type": "mini_clue", "id": "pharmacy_receipt", "description": "药房收据——有人最近大量购买了安眠药"}],
        },
        {
            "action": "宋知微翻看花园角落的一个花盆，发现底部贴着一张标签。",
            "location": "花园",
            "evidence_left": "花园某个花盆被翻转过",
            "world_changes": [{"type": "mini_clue", "id": "pot_label", "description": "花盆底部的标签写着一个电话号码"}],
        },
        {
            "action": "宋知微用手机搜索了什么信息，突然表情一变，喃喃说：「原来如此……」",
            "location": "走廊",
        },
        {
            "action": "宋知微在走廊发现一个不起眼的通风口，里面似乎塞了什么东西。",
            "location": "走廊",
            "evidence_left": "走廊通风口的螺丝有被拧动过的痕迹",
            "world_changes": [{"type": "mini_clue", "id": "vent_item", "description": "通风口里藏着一个U盘"}],
        },
        {
            "action": "宋知微拼凑了几条线索后露出了记者特有的兴奋表情，快速在本子上写了一大段。",
            "location": "宴会厅",
        },
    ],

    # ── Confronting other NPCs (when alone with them) ──
    "confront_linlan": [
        {
            "action": "宋知微走到林岚面前，开门见山地问：「林秘书，你在顾言失踪前最后一次见他是什么时候？」",
            "location": "宴会厅",
            "evidence_left": "宋知微和林岚之间的气氛明显变得紧张",
            "world_changes": [{"type": "event", "description": "宋知微质问了林岚关于顾言的下落"}],
        },
        {
            "action": "宋知微拿出手机展示了一些东西给林岚看，林岚的表情瞬间僵住了。",
            "location": "走廊",
            "evidence_left": "林岚和宋知微在走廊里有过一次紧张的对峙",
            "sound_generated": "走廊里传来两个女人压低声音争论的声音",
        },
        {
            "action": "宋知微假装不经意地提到了「遗嘱」两个字，同时紧盯着林岚的反应。",
            "location": "宴会厅",
            "world_changes": [{"type": "event", "description": "宋知微试探林岚对遗嘱的反应"}],
        },
        {
            "action": "宋知微在林岚旁边坐下，低声说：「我知道你在隐瞒什么。我们可以合作，也可以各自为政。」",
            "location": "宴会厅",
            "sound_generated": "宴会厅某个角落传来低沉的对话声",
        },
        {
            "action": "宋知微跟踪林岚到走廊，在她打电话时尝试偷听。",
            "location": "走廊",
            "evidence_left": "走廊的门后面有蹲过人的痕迹",
            "world_changes": [{"type": "event", "description": "宋知微偷听了林岚的电话"}],
        },
    ],

    # ── Confronting Zhou Mu ──
    "confront_zhoumu": [
        {
            "action": "宋知微举着酒杯走向周牧，看似随意地说：「周先生，你昨晚好像睡得不太好？」",
            "location": "宴会厅",
            "world_changes": [{"type": "event", "description": "宋知微试探周牧关于昨晚的情况"}],
        },
        {
            "action": "宋知微突然问周牧：「你和顾言之间，是不是有什么过不去的坎？」周牧的杯子差点掉了。",
            "location": "宴会厅",
            "evidence_left": "吧台上有酒洒出来的痕迹",
            "sound_generated": "宴会厅传来杯子碰撞的声音",
        },
        {
            "action": "宋知微把一张照片递给周牧看，周牧看完后脸色大变。",
            "location": "走廊",
            "evidence_left": "走廊地上有一张被丢下的照片",
        },
        {
            "action": "宋知微拍了拍周牧的肩膀：「别紧张，我只是想帮你。但你得先跟我说实话。」",
            "location": "花园",
        },
        {
            "action": "宋知微在周牧喝酒时凑过去，低声说：「我知道你昨晚去过酒窖附近。」",
            "location": "宴会厅",
            "sound_generated": "宴会厅吧台附近传来压低的对话声",
            "world_changes": [{"type": "event", "description": "宋知微暗示知道周牧昨晚的行踪"}],
        },
    ],
}

# Unified lookup
_ACTION_POOLS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "linlan":  _LINLAN_ACTIONS,
    "zhoumu":  _ZHOUMU_ACTIONS,
    "songzhi": _SONGZHI_ACTIONS,
}

_PLAN_LIBRARY: Dict[str, Dict[str, Dict[str, str]]] = {
    "linlan": {
        "hold_cover_story": {
            "goal": "保护秘密，维持统一口径",
            "pool": "secret_phone",
            "fallback": "idle_banquet",
        },
        "scrub_study_traces": {
            "goal": "回收书房线索，防止遗嘱痕迹继续外泄",
            "pool": "check_study",
            "fallback": "secret_phone",
        },
        "recover_letter_fragments": {
            "goal": "抢在别人之前回收花园里的碎片线索",
            "pool": "search_letter",
            "fallback": "secret_phone",
        },
        "warn_hidden_master": {
            "goal": "向顾言通风报信，准备终局应对",
            "pool": "warn_guyan",
            "fallback": "desperate_contact",
        },
    },
    "zhoumu": {
        "preserve_alibi": {
            "goal": "维持无辜形象，避免自己成为第一嫌疑人",
            "pool": "garden_calm",
            "fallback": "idle_banquet",
        },
        "verify_cellar_risk": {
            "goal": "确认酒窖方向有没有暴露风险",
            "pool": "sneak_cellar",
            "fallback": "retreat",
        },
        "destroy_dangerous_letter": {
            "goal": "处理不利于自己的书信痕迹",
            "pool": "open_letter",
            "fallback": "retreat",
        },
        "redirect_attention": {
            "goal": "不断制造新的怀疑方向，把焦点移开",
            "pool": "avoid_cellar",
            "fallback": "phone_check",
        },
    },
    "songzhi": {
        "map_story": {
            "goal": "建立完整叙事链，抢先掌握真相结构",
            "pool": "early_investigate",
            "fallback": "scoop_search",
        },
        "secret_recording": {
            "goal": "记录关键反应，积累可利用的证言材料",
            "pool": "secret_record",
            "fallback": "early_investigate",
        },
        "chase_hidden_clue": {
            "goal": "抢在所有人之前追到关键线索现场",
            "pool": "follow_clue",
            "fallback": "own_discovery",
        },
        "pressure_linlan": {
            "goal": "撬开林岚的防线，逼她暴露立场",
            "pool": "confront_linlan",
            "fallback": "secret_record",
        },
        "pressure_zhoumu": {
            "goal": "利用周牧情绪不稳的弱点换取突破口",
            "pool": "confront_zhoumu",
            "fallback": "secret_record",
        },
    },
}

_SECRET_POOLS = {
    "check_study",
    "search_letter",
    "warn_guyan",
    "desperate_contact",
    "sneak_cellar",
    "open_letter",
    "secret_record",
    "follow_clue",
    "own_discovery",
}


# ---------------------------------------------------------------------------
# Helper: pick a random action from a pool, optionally override location
# ---------------------------------------------------------------------------

def _pick_action(
    pool: List[Dict[str, Any]],
    override_location: Optional[str] = None,
) -> Dict[str, Any]:
    """Pick a random action dict from a pool, with optional location override."""
    entry = random.choice(pool)
    result = dict(entry)  # shallow copy so we don't mutate the pool
    if override_location is not None:
        result["location"] = override_location
    return result


# ---------------------------------------------------------------------------
# NPC Autonomy Agent
# ---------------------------------------------------------------------------

class NPCAutonomyAgent:
    """
    Simulates independent NPC behaviour each game turn.

    State is stored in-memory, keyed by ``session_id``.
    """

    def __init__(self) -> None:
        # session_id -> character_id -> current location
        self._locations: Dict[str, Dict[str, str]] = {}
        # session_id -> character_id -> NPCAutonomyState
        self._states: Dict[str, Dict[str, NPCAutonomyState]] = {}
        # session_id -> round_num -> list of NPCAction (history of all actions)
        self._action_history: Dict[str, Dict[int, List[NPCAction]]] = {}
        # session_id -> location -> list of evidence strings (accumulated)
        self._evidence: Dict[str, Dict[str, List[str]]] = {}
        # session_id -> set of locations the player has already searched
        self._player_searched: Dict[str, set] = {}
        # session_id -> pending NPC-to-NPC information transfers
        self._pending_shares: Dict[str, List[Dict[str, str]]] = {}
        # session_id -> share keys already triggered
        self._share_history: Dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Internal: ensure session data structures exist
    # ------------------------------------------------------------------

    def _ensure_session(self, session_id: str) -> None:
        """Lazily initialise storage for a session."""
        if session_id not in self._locations:
            self._locations[session_id] = {
                "linlan": "宴会厅",
                "zhoumu": "宴会厅",
                "songzhi": "宴会厅",
            }
        if session_id not in self._states:
            self._states[session_id] = {
                "linlan": NPCAutonomyState(
                    character_id="linlan",
                    long_term_goal="保护秘密，完成顾言交代的任务",
                    current_goal="保护秘密，完成顾言交代的任务",
                    current_plan="hold_cover_story",
                    fallback_plan="warn_hidden_master",
                    next_action_pool="secret_phone",
                    planned_actions=["hold_cover_story", "warn_hidden_master"],
                ),
                "zhoumu": NPCAutonomyState(
                    character_id="zhoumu",
                    long_term_goal="隐瞒昨晚的争吵，避免成为嫌疑人",
                    current_goal="隐瞒昨晚的争吵，避免成为嫌疑人",
                    current_plan="preserve_alibi",
                    fallback_plan="redirect_attention",
                    next_action_pool="garden_calm",
                    planned_actions=["preserve_alibi", "redirect_attention"],
                ),
                "songzhi": NPCAutonomyState(
                    character_id="songzhi",
                    long_term_goal="挖掘独家新闻素材",
                    current_goal="挖掘独家新闻素材",
                    current_plan="map_story",
                    fallback_plan="secret_recording",
                    next_action_pool="early_investigate",
                    planned_actions=["map_story", "secret_recording"],
                ),
            }
        if session_id not in self._action_history:
            self._action_history[session_id] = {}
        if session_id not in self._evidence:
            self._evidence[session_id] = defaultdict(list)
        if session_id not in self._player_searched:
            self._player_searched[session_id] = set()
        if session_id not in self._pending_shares:
            self._pending_shares[session_id] = []
        if session_id not in self._share_history:
            self._share_history[session_id] = set()

    # ------------------------------------------------------------------
    # Internal: get desperation from psych_states or default
    # ------------------------------------------------------------------

    @staticmethod
    def _get_desperation(
        psych_states: Optional[Dict[str, Any]], character_id: str
    ) -> float:
        """Extract desperation for *character_id* from the psych_states dict."""
        if not psych_states:
            return 0.0
        entry = psych_states.get(character_id)
        if entry is None:
            return 0.0
        if isinstance(entry, dict):
            return float(entry.get("desperation", 0.0))
        # It might be a Pydantic model
        return float(getattr(entry, "desperation", 0.0))

    def _select_plan(
        self,
        session_id: str,
        character_id: str,
        round_num: int,
        tension: int,
        discovered_clues: List[str],
        desperation: float,
        player_location: str,
    ) -> Dict[str, str]:
        """Pick the most appropriate current plan for a character."""
        if character_id == "linlan":
            if desperation > 0.6 or tension >= 72:
                return {"name": "warn_hidden_master", **_PLAN_LIBRARY["linlan"]["warn_hidden_master"]}
            if "torn_letter" in discovered_clues:
                return {"name": "recover_letter_fragments", **_PLAN_LIBRARY["linlan"]["recover_letter_fragments"]}
            if any(clue in discovered_clues for clue in ("study_scratches", "will_draft")) and round_num >= 5:
                return {"name": "scrub_study_traces", **_PLAN_LIBRARY["linlan"]["scrub_study_traces"]}
            return {"name": "hold_cover_story", **_PLAN_LIBRARY["linlan"]["hold_cover_story"]}

        if character_id == "zhoumu":
            if desperation > 0.55:
                return {"name": "destroy_dangerous_letter", **_PLAN_LIBRARY["zhoumu"]["destroy_dangerous_letter"]}
            if tension >= 60 or "wine_cellar_footprint" in discovered_clues or "cellar_sound" in discovered_clues:
                return {"name": "verify_cellar_risk", **_PLAN_LIBRARY["zhoumu"]["verify_cellar_risk"]}
            if round_num >= 6 or tension >= 45:
                return {"name": "redirect_attention", **_PLAN_LIBRARY["zhoumu"]["redirect_attention"]}
            return {"name": "preserve_alibi", **_PLAN_LIBRARY["zhoumu"]["preserve_alibi"]}

        linlan_loc = self._locations.get(session_id, {}).get("linlan", "宴会厅")
        zhoumu_loc = self._locations.get(session_id, {}).get("zhoumu", "宴会厅")
        songzhi_loc = self._locations.get(session_id, {}).get("songzhi", "宴会厅")
        if tension >= 45:
            return {"name": "secret_recording", **_PLAN_LIBRARY["songzhi"]["secret_recording"]}
        if discovered_clues and round_num >= 4:
            return {"name": "chase_hidden_clue", **_PLAN_LIBRARY["songzhi"]["chase_hidden_clue"]}
        if songzhi_loc == linlan_loc and songzhi_loc != player_location and tension >= 30:
            return {"name": "pressure_linlan", **_PLAN_LIBRARY["songzhi"]["pressure_linlan"]}
        if songzhi_loc == zhoumu_loc and songzhi_loc != player_location and tension >= 28:
            return {"name": "pressure_zhoumu", **_PLAN_LIBRARY["songzhi"]["pressure_zhoumu"]}
        return {"name": "map_story", **_PLAN_LIBRARY["songzhi"]["map_story"]}

    def _activate_plan(
        self,
        state: NPCAutonomyState,
        plan: Dict[str, str],
        round_num: int,
    ) -> None:
        """Persist a plan change into the autonomy state."""
        if state.current_plan != plan["name"]:
            state.last_outcome = f"replanned:{state.current_plan or 'none'}->{plan['name']}"
            state.plan_step = 0
            state.last_revision_round = round_num
        state.current_plan = plan["name"]
        state.current_goal = plan["goal"]
        state.fallback_plan = plan["fallback"]
        state.next_action_pool = plan["pool"]
        state.planned_actions = [plan["pool"], plan["fallback"]]

    def _pick_action_from_pool(
        self,
        char_id: str,
        pool_name: str,
        player_location: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Pick an action from a desired pool and report whether it was blocked."""
        pool = _ACTION_POOLS[char_id].get(pool_name)
        if not pool:
            return None, "missing_pool"

        candidate = _pick_action(pool)
        if pool_name in _SECRET_POOLS and candidate.get("location") == player_location:
            return None, "blocked_by_player"
        return candidate, "progressed"

    def _record_information_shares(
        self,
        session_id: str,
        player_location: str,
        tension: int,
    ) -> None:
        """Create private NPC-to-NPC information transfers when plans intersect."""
        location_buckets: Dict[str, List[str]] = defaultdict(list)
        for char_id, location in self._locations[session_id].items():
            if location != player_location:
                location_buckets[location].append(char_id)

        for colocated in location_buckets.values():
            members = set(colocated)
            if {"linlan", "zhoumu"}.issubset(members) and tension >= 45:
                self._queue_share(
                    session_id,
                    source="linlan",
                    target="zhoumu",
                    fact_id="linlan_test_plan",
                    summary="林岚低声提醒周牧，顾言的试探计划还没有结束，别先乱阵脚。",
                )
            if {"zhoumu", "songzhi"}.issubset(members) and tension >= 38:
                self._queue_share(
                    session_id,
                    source="zhoumu",
                    target="songzhi",
                    fact_id="zhoumu_cellar_hint",
                    summary="周牧在情绪失控时漏出一句：昨晚酒窖附近确实有过动静。",
                )

    def _queue_share(
        self,
        session_id: str,
        *,
        source: str,
        target: str,
        fact_id: str,
        summary: str,
    ) -> None:
        key = f"{source}->{target}:{fact_id}"
        if key in self._share_history[session_id]:
            return
        self._share_history[session_id].add(key)
        self._pending_shares[session_id].append(
            {
                "source": source,
                "target": target,
                "fact_id": fact_id,
                "summary": summary,
            }
        )
        source_state = self._states[session_id][source]
        target_state = self._states[session_id][target]
        note = f"{_CHAR_NAMES[source]}向{_CHAR_NAMES[target]}传递了信息：{summary}"
        source_state.knowledge_updates.append(note)
        target_state.knowledge_updates.append(note)

    # ------------------------------------------------------------------
    # NPC decision logic
    # ------------------------------------------------------------------

    def _decide_linlan(
        self,
        session_id: str,
        player_location: str,
        round_num: int,
        tension: int,
        discovered_clues: List[str],
        desperation: float,
    ) -> Dict[str, Any]:
        """Choose an action for 林岚 based on the current situation."""

        # Track the player's searched locations
        self._player_searched[session_id].add(player_location)

        # Desperate contact takes priority
        if desperation > 0.6:
            return _pick_action(_LINLAN_ACTIONS["desperate_contact"])

        # High tension: warn Gu Yan
        if tension > 70:
            # Don't go to 酒窖 if player is there
            if player_location != "酒窖":
                return _pick_action(_LINLAN_ACTIONS["warn_guyan"])
            else:
                # Fallback: phone from elsewhere
                return _pick_action(_LINLAN_ACTIONS["secret_phone"])

        # Player found torn_letter: search for remaining pieces
        if "torn_letter" in discovered_clues:
            if player_location != "花园":
                return _pick_action(_LINLAN_ACTIONS["search_letter"])

        # Player found study clues: go check the study
        study_clues_found = any(
            c in discovered_clues for c in ("study_scratches", "will_draft")
        )
        if study_clues_found and round_num > 5:
            if player_location != "书房":
                return _pick_action(_LINLAN_ACTIONS["check_study"])

        # Medium tension: secret phone activity
        if tension > 50:
            return _pick_action(_LINLAN_ACTIONS["secret_phone"])

        # Default: stay at banquet, observe
        if round_num <= 5:
            return _pick_action(_LINLAN_ACTIONS["idle_banquet"])

        # After round 5, even without triggers, occasionally check phone
        if random.random() < 0.3:
            return _pick_action(_LINLAN_ACTIONS["secret_phone"])

        return _pick_action(_LINLAN_ACTIONS["idle_banquet"])

    def _decide_zhoumu(
        self,
        session_id: str,
        player_location: str,
        round_num: int,
        tension: int,
        discovered_clues: List[str],
        desperation: float,
    ) -> Dict[str, Any]:
        """Choose an action for 周牧 based on the current situation."""

        # Desperate: open the sealed letter
        if desperation > 0.5:
            return _pick_action(_ZHOUMU_ACTIONS["open_letter"])

        # High tension: sneak toward cellar (curiosity + guilt)
        if tension > 60:
            if player_location != "酒窖" and random.random() < 0.6:
                return _pick_action(_ZHOUMU_ACTIONS["sneak_cellar"])
            else:
                # Too scared with player nearby, retreat
                return _pick_action(_ZHOUMU_ACTIONS["retreat"])

        # Medium-high tension: garden to calm down
        if tension > 50:
            if player_location != "花园":
                return _pick_action(_ZHOUMU_ACTIONS["garden_calm"])
            else:
                return _pick_action(_ZHOUMU_ACTIONS["restless_wander"])

        # Player found wine cellar footprint: avoid cellar conspicuously
        if "wine_cellar_footprint" in discovered_clues:
            if random.random() < 0.5:
                return _pick_action(_ZHOUMU_ACTIONS["avoid_cellar"])

        # Low-medium tension: restless wandering
        if tension > 30:
            if random.random() < 0.5:
                return _pick_action(_ZHOUMU_ACTIONS["restless_wander"])
            else:
                return _pick_action(_ZHOUMU_ACTIONS["phone_check"])

        # Default: drink at banquet
        if round_num <= 5:
            return _pick_action(_ZHOUMU_ACTIONS["idle_banquet"])

        # After round 5, mix between idle and nervous phone checks
        if random.random() < 0.3:
            return _pick_action(_ZHOUMU_ACTIONS["phone_check"])

        return _pick_action(_ZHOUMU_ACTIONS["idle_banquet"])

    def _decide_songzhi(
        self,
        session_id: str,
        player_location: str,
        round_num: int,
        tension: int,
        discovered_clues: List[str],
        desperation: float,
    ) -> Dict[str, Any]:
        """Choose an action for 宋知微 based on the current situation."""

        npc_locations = self._locations.get(session_id, {})

        # High tension: own discovery
        if tension > 60 and random.random() < 0.5:
            # Pick a location the player is NOT in
            unsearched = [
                loc for loc in ALL_LOCATIONS
                if loc != player_location and loc != "宴会厅"
            ]
            loc = random.choice(unsearched) if unsearched else "走廊"
            return _pick_action(_SONGZHI_ACTIONS["own_discovery"], override_location=loc)

        # Medium tension: secret recording
        if tension > 40 and random.random() < 0.4:
            return _pick_action(_SONGZHI_ACTIONS["secret_record"])

        # If alone with Lin Lan (both not where the player is), confront her
        linlan_loc = npc_locations.get("linlan", "宴会厅")
        songzhi_loc = npc_locations.get("songzhi", "宴会厅")
        if (
            linlan_loc == songzhi_loc
            and linlan_loc != player_location
            and tension > 30
            and random.random() < 0.4
        ):
            return _pick_action(
                _SONGZHI_ACTIONS["confront_linlan"],
                override_location=linlan_loc,
            )

        # If alone with Zhou Mu, confront him
        zhoumu_loc = npc_locations.get("zhoumu", "宴会厅")
        if (
            zhoumu_loc == songzhi_loc
            and zhoumu_loc != player_location
            and tension > 25
            and random.random() < 0.35
        ):
            return _pick_action(
                _SONGZHI_ACTIONS["confront_zhoumu"],
                override_location=zhoumu_loc,
            )

        # If the player just found a clue, follow up
        if discovered_clues and random.random() < 0.5:
            # Figure out the location of the most recent clue
            clue_locations = {
                "study_scratches": "书房",
                "will_draft": "书房",
                "wine_cellar_footprint": "酒窖",
                "torn_letter": "花园",
                "anonymous_tip": "宴会厅",
                "cellar_sound": "酒窖",
            }
            # Pick the last discovered clue's location
            latest_clue = discovered_clues[-1]
            clue_loc = clue_locations.get(latest_clue, "走廊")
            if clue_loc != player_location:
                return _pick_action(
                    _SONGZHI_ACTIONS["follow_clue"],
                    override_location=clue_loc,
                )

        # Early rounds: basic investigation
        if round_num <= 5:
            return _pick_action(_SONGZHI_ACTIONS["early_investigate"])

        # Scoop the player: go to locations they haven't searched
        player_visited = self._player_searched.get(session_id, set())
        unsearched = [
            loc for loc in ALL_LOCATIONS
            if loc not in player_visited and loc != player_location
        ]
        if unsearched and random.random() < 0.6:
            target_loc = random.choice(unsearched)
            return _pick_action(
                _SONGZHI_ACTIONS["scoop_search"],
                override_location=target_loc,
            )

        # Default: continue investigating
        return _pick_action(_SONGZHI_ACTIONS["early_investigate"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_npc_turns(
        self,
        session_id: str,
        player_location: str,
        round_num: int,
        tension: int,
        discovered_clues: List[str],
        psych_states: Optional[Dict[str, Any]] = None,
    ) -> List[NPCAction]:
        """
        Simulate what every NPC does THIS turn, independently of the player.

        Args:
            session_id:       Game session identifier.
            player_location:  The location where the player currently is.
            round_num:        Current round number (1-based).
            tension:          Current tension level (0-100).
            discovered_clues: List of clue IDs the player has discovered.
            psych_states:     Optional dict of ``{character_id: psych_state}``
                              from ``CharacterPsychologyAgent``.  Used to read
                              ``desperation`` values.

        Returns:
            A list of ``NPCAction`` objects, one per NPC.
        """
        self._ensure_session(session_id)

        # Record the player's current location for scooping logic
        self._player_searched[session_id].add(player_location)

        decision_funcs = {
            "linlan":  self._decide_linlan,
            "zhoumu":  self._decide_zhoumu,
            "songzhi": self._decide_songzhi,
        }

        actions: List[NPCAction] = []

        for char_id in _ALL_CHAR_IDS:
            desperation = self._get_desperation(psych_states, char_id)
            autonomy_state = self._states[session_id][char_id]
            plan = self._select_plan(
                session_id=session_id,
                character_id=char_id,
                round_num=round_num,
                tension=tension,
                discovered_clues=discovered_clues,
                desperation=desperation,
                player_location=player_location,
            )
            self._activate_plan(autonomy_state, plan, round_num)

            raw, outcome = self._pick_action_from_pool(
                char_id,
                autonomy_state.next_action_pool,
                player_location,
            )

            if raw is None:
                fallback_pool = autonomy_state.fallback_plan
                raw, outcome = self._pick_action_from_pool(
                    char_id,
                    fallback_pool,
                    player_location,
                )
                autonomy_state.next_action_pool = fallback_pool

            if raw is None:
                raw = decision_funcs[char_id](
                    session_id=session_id,
                    player_location=player_location,
                    round_num=round_num,
                    tension=tension,
                    discovered_clues=discovered_clues,
                    desperation=desperation,
                )
                outcome = "fallback_rules"

            previous_location = self._locations[session_id].get(char_id, "宴会厅")
            new_location = raw.get("location", previous_location)
            moved = new_location != previous_location

            # Determine visibility to player
            visible = new_location == player_location

            npc_action = NPCAction(
                character_id=char_id,
                character_name=_CHAR_NAMES[char_id],
                action=raw["action"],
                location=new_location,
                previous_location=previous_location,
                moved=moved,
                visible_to_player=visible,
                evidence_left=raw.get("evidence_left"),
                sound_generated=raw.get("sound_generated"),
                world_changes=raw.get("world_changes", []),
            )

            # Update NPC location
            self._locations[session_id][char_id] = new_location

            # Store evidence at the action's location (for later discovery)
            if npc_action.evidence_left:
                self._evidence[session_id][new_location].append(
                    npc_action.evidence_left
                )

            # Update autonomy state
            autonomy_state.completed_actions.append(raw["action"])
            autonomy_state.stress_level = desperation
            autonomy_state.plan_step += 1
            autonomy_state.last_outcome = outcome

            actions.append(npc_action)

        self._record_information_shares(session_id, player_location, tension)

        # Store in history
        self._action_history[session_id][round_num] = actions

        return actions

    def get_visible_actions(
        self, session_id: str, player_location: str
    ) -> List[NPCAction]:
        """
        Filter the most recent round's actions to only what the player can
        perceive:

        * **Same location** — the player sees the full action.
        * **Adjacent location with sound** — the player hears a sound
          description (the action text is replaced with the sound).

        Returns:
            A list of ``NPCAction`` with adjusted visibility.
        """
        self._ensure_session(session_id)

        history = self._action_history.get(session_id, {})
        if not history:
            return []

        latest_round = max(history.keys())
        latest_actions = history[latest_round]

        adjacent = set(ADJACENT_ROOMS.get(player_location, []))
        result: List[NPCAction] = []

        for act in latest_actions:
            if act.location == player_location:
                # Player sees the full action
                visible_act = act.model_copy(update={"visible_to_player": True})
                result.append(visible_act)

            elif act.location in adjacent and act.sound_generated:
                # Player hears a sound from an adjacent room
                sound_desc = act.sound_generated
                # If the sound comes from the wine cellar, it's faint
                if act.location in _FAINT_SOUND_SOURCES:
                    sound_desc = f"（隐约）{sound_desc}"

                sound_action = NPCAction(
                    character_id=act.character_id,
                    character_name=act.character_name,
                    action=sound_desc,
                    location=act.location,
                    previous_location=act.previous_location,
                    moved=act.moved,
                    visible_to_player=False,
                    evidence_left=None,  # player doesn't see evidence yet
                    sound_generated=act.sound_generated,
                    world_changes=[],  # player doesn't know about world changes
                )
                result.append(sound_action)

        return result

    def get_evidence_at_location(
        self, session_id: str, location: str
    ) -> List[str]:
        """
        Return all evidence strings left by NPCs at *location* across all
        previous rounds.  The player can discover these on a visit.

        Once returned, the evidence is **consumed** (removed) so it is not
        reported again on subsequent visits.

        Args:
            session_id: Game session identifier.
            location:   The location to check.

        Returns:
            A list of evidence description strings (Chinese).
        """
        self._ensure_session(session_id)

        evidence_list = self._evidence[session_id].get(location, [])
        if not evidence_list:
            return []

        # Return and clear
        result = list(evidence_list)
        self._evidence[session_id][location] = []
        return result

    def update_npc_location(
        self, session_id: str, character_id: str, new_location: str
    ) -> None:
        """
        Manually update an NPC's location (e.g. when game logic forces a
        character to move).

        Args:
            session_id:   Game session identifier.
            character_id: The NPC identifier.
            new_location: The new location string.
        """
        self._ensure_session(session_id)
        self._locations[session_id][character_id] = new_location

    def get_npc_locations(self, session_id: str) -> Dict[str, str]:
        """
        Return the current location of every NPC.

        Args:
            session_id: Game session identifier.

        Returns:
            A dict ``{character_id: location}`` for all NPCs.
        """
        self._ensure_session(session_id)
        return dict(self._locations[session_id])

    # ------------------------------------------------------------------
    # Convenience: get autonomy state for debugging / advanced logic
    # ------------------------------------------------------------------

    def get_autonomy_state(
        self, session_id: str, character_id: str
    ) -> NPCAutonomyState:
        """Return the ``NPCAutonomyState`` for a given NPC in a session."""
        self._ensure_session(session_id)
        return self._states[session_id][character_id]

    def consume_pending_shares(self, session_id: str) -> List[Dict[str, str]]:
        """Return and clear pending NPC-to-NPC information transfers."""
        self._ensure_session(session_id)
        pending = list(self._pending_shares.get(session_id, []))
        self._pending_shares[session_id] = []
        return pending

    def get_action_history(
        self, session_id: str
    ) -> Dict[int, List[NPCAction]]:
        """Return the full action history ``{round_num: [NPCAction, ...]}``."""
        self._ensure_session(session_id)
        return dict(self._action_history.get(session_id, {}))

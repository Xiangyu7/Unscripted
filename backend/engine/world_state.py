"""
World State — tracks every mutable object, location, and inventory in the game world.

This is the foundation layer that enables true sandbox freedom: players can turn off
lights, smash vases, open drawers, pick up items, and check character belongings.
All state is deterministic (no LLM calls). The turn engine and agents read from this
to build context-aware narration.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ObjectState(BaseModel):
    """A single interactable object in the world."""
    name: str                                       # Display name (Chinese)
    description: str                                # Short description
    location: str                                   # Room key or character_id if carried
    state: str = "normal"                           # normal/broken/open/closed/locked/hidden/moved/missing
    interactable: bool = True                       # Can the player interact with it?
    contains: List[str] = Field(default_factory=list)  # What is inside (if container)
    hidden_clue: Optional[str] = None               # Clue ID revealed on proper interaction
    notes: str = ""                                 # Extra state info (free-form)


class LocationState(BaseModel):
    """State of a single location / room."""
    name: str                                       # 宴会厅, 书房, etc.
    description: str                                # Atmospheric description (Chinese)
    lighting: str = "normal"                        # bright / normal / dim / dark
    accessible: bool = True
    connections: List[str] = Field(default_factory=list)     # Connected location keys
    ambient_sounds: List[str] = Field(default_factory=list)  # Current ambient sounds
    details: List[str] = Field(default_factory=list)         # Observable details that change


class CharacterInventory(BaseModel):
    """Items carried by an NPC."""
    character_id: str
    items: List[str] = Field(default_factory=list)


class WorldState(BaseModel):
    """Complete world state snapshot for one game session."""
    session_id: str

    # Time & environment
    time: str = "21:00"                             # In-game clock (HH:MM)
    weather: str = "微雨"                           # Affects garden & mood
    time_period: str = "入夜"                       # 入夜 / 深夜 / 凌晨

    # Spatial
    locations: Dict[str, LocationState] = Field(default_factory=dict)
    objects: Dict[str, ObjectState] = Field(default_factory=dict)  # object_id -> state

    # Inventories
    character_inventories: Dict[str, CharacterInventory] = Field(default_factory=dict)
    player_inventory: List[str] = Field(default_factory=list)

    # Change log (cleared each turn, used by narration layer)
    recent_changes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Lighting labels used for narrative descriptions
# ---------------------------------------------------------------------------

_LIGHTING_DESC: Dict[str, str] = {
    "bright": "明亮",
    "normal": "柔和的灯光",
    "dim": "昏暗",
    "dark": "漆黑一片",
}

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _add_minutes(time_str: str, minutes: int) -> str:
    """Add *minutes* to an HH:MM string and return the new HH:MM."""
    h, m = map(int, time_str.split(":"))
    total = h * 60 + m + minutes
    total %= 24 * 60  # wrap around midnight
    return f"{total // 60:02d}:{total % 60:02d}"


def _time_to_minutes(time_str: str) -> int:
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


def _time_period_for(time_str: str) -> str:
    """Determine the narrative time-period label."""
    mins = _time_to_minutes(time_str)
    # 18:00-22:59 -> 入夜, 23:00-01:59 -> 深夜, 02:00-05:59 -> 凌晨
    if mins >= 18 * 60 or mins < 2 * 60:
        if mins >= 23 * 60 or mins < 2 * 60:
            return "深夜"
        return "入夜"
    if mins < 6 * 60:
        return "凌晨"
    return "入夜"  # fallback


# ---------------------------------------------------------------------------
# WorldStateManager
# ---------------------------------------------------------------------------

class WorldStateManager:
    """Manages per-session WorldState instances.  Pure state — no LLM calls."""

    def __init__(self) -> None:
        self._states: Dict[str, WorldState] = {}

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def create_initial_state(self, session_id: str) -> WorldState:
        """Build the richly detailed initial world state for the Gu family mansion."""

        # ── Locations ────────────────────────────────────────────────
        locations: Dict[str, LocationState] = {
            "宴会厅": LocationState(
                name="宴会厅",
                description=(
                    "顾家老宅的宴会厅宽敞而气派。水晶吊灯洒下暖黄色的光，"
                    "壁炉中的火焰噼啪作响，留声机里传出低沉的爵士乐。"
                    "长桌上残留着晚宴的痕迹，空气里弥漫着红酒与木质家具的气息。"
                    "窗外雨声淅沥，为这个夜晚平添了几分萧索。"
                ),
                lighting="normal",
                accessible=True,
                connections=["走廊", "花园"],
                ambient_sounds=["留声机的爵士乐", "壁炉噼啪声", "雨声"],
                details=[
                    "长桌上有未收拾的餐具和残留的红酒",
                    "壁炉上方挂着一幅顾家全家福",
                    "留声机的唱针偶尔跳动一下，发出轻微的噪音",
                ],
            ),
            "书房": LocationState(
                name="书房",
                description=(
                    "书房是顾言最私密的空间。厚重的书架占据了整面墙壁，"
                    "书桌上台灯发出昏黄的光，一杯茶早已凉透。"
                    "空气中残留着淡淡的墨香与烟草味。"
                    "这里是顾言最后被人看到的地方——门把手上有新鲜的划痕。"
                ),
                lighting="dim",
                accessible=True,
                connections=["走廊"],
                ambient_sounds=["老式挂钟的滴答声", "窗外雨声(隔窗)"],
                details=[
                    "书桌上有一杯凉透的茶",
                    "门把手上有新的划痕",
                    "电脑处于休眠状态，屏幕微微发光",
                    "纸篓里有揉成一团的纸",
                ],
            ),
            "花园": LocationState(
                name="花园",
                description=(
                    "夜雨中的花园笼罩着一层朦胧的雾气。月光时隐时现，"
                    "石径两旁的灌木在风中轻轻摇晃。假山旁的鱼池里，"
                    "锦鲤偶尔搅动水面。凉亭在远处若隐若现，"
                    "花架上的紫藤在雨中散发出湿润的清香。"
                ),
                lighting="dim",
                accessible=True,
                connections=["宴会厅", "走廊"],
                ambient_sounds=["雨声", "蛙鸣", "风声"],
                details=[
                    "石径上有被雨水冲刷过的泥泞脚印",
                    "灌木丛中似乎夹着什么东西",
                    "鱼池的水面上漂着几片落叶",
                ],
            ),
            "酒窖": LocationState(
                name="酒窖",
                description=(
                    "沿着狭窄的石阶向下，空气变得阴冷潮湿。"
                    "酒窖里只有一盏摇摇晃晃的灯泡，昏暗的光线在酒桶间投下巨大的阴影。"
                    "酒架上整齐排列着积满灰尘的酒瓶。"
                    "最深处有一扇沉重的木门，不知通向何处。"
                    "空气中除了酒香，还有一种说不清的潮湿气味——"
                    "以及远处传来的低沉嗡嗡声。"
                ),
                lighting="dark",
                accessible=True,
                connections=["走廊"],
                ambient_sounds=["滴水声", "远处低沉的嗡嗡声"],
                details=[
                    "地面上有几组杂乱的脚印",
                    "酒桶上有新的刮痕",
                    "最深处的木门紧锁着",
                    "墙壁上有一段颜色略有不同的区域",
                ],
            ),
            "走廊": LocationState(
                name="走廊",
                description=(
                    "长长的走廊连接着宅邸的各个房间。壁灯发出温暖但不甚明亮的光，"
                    "古董花架上摆着一只青花瓷瓶。脚下的波斯地毯吞噬了大部分脚步声。"
                    "走廊尽头是一扇紧闭的门，通向花园的侧门也在这里。"
                    "往下的楼梯隐没在阴影中，通往地下酒窖。"
                ),
                lighting="normal",
                accessible=True,
                connections=["宴会厅", "书房", "花园", "酒窖"],
                ambient_sounds=["远处的留声机声", "偶尔的脚步声"],
                details=[
                    "走廊尽头有一扇关着的门",
                    "地毯上有淡淡的脚印",
                    "壁灯的光在墙上投下摇曳的影子",
                ],
            ),
        }

        # ── Objects ──────────────────────────────────────────────────
        objects: Dict[str, ObjectState] = {}

        # --- 宴会厅 objects ---
        objects["banquet_long_table"] = ObjectState(
            name="长桌",
            description="铺着白色桌布的红木长桌，上面还残留着晚宴的餐具和酒渍",
            location="宴会厅",
            state="normal",
            contains=["残留餐具", "酒渍", "几只空酒杯"],
        )
        objects["banquet_vase"] = ObjectState(
            name="花瓶",
            description="桌上摆放的一只精美青花瓷花瓶，插着几支已经有些蔫的百合",
            location="宴会厅",
            state="normal",
        )
        objects["banquet_gramophone"] = ObjectState(
            name="留声机",
            description="角落里的老式留声机，正播放着低沉的爵士乐，唱针偶尔发出轻微的噪音",
            location="宴会厅",
            state="normal",
            notes="playing_jazz",
        )
        objects["banquet_wine_cabinet"] = ObjectState(
            name="酒柜",
            description="靠墙的红木酒柜，透过玻璃门可以看到里面整齐排列的各式酒瓶",
            location="宴会厅",
            state="closed",
            contains=["红酒×3", "白兰地×2", "威士忌×1"],
        )
        objects["banquet_fireplace"] = ObjectState(
            name="壁炉",
            description="壁炉里的火焰噼啪作响，散发着温暖的光芒，壁炉台上摆着几张照片",
            location="宴会厅",
            state="normal",
            notes="lit",
        )
        objects["banquet_clock"] = ObjectState(
            name="老式挂钟",
            description="墙上悬挂的老式挂钟，钟摆有节奏地左右摇晃，指针指向九点",
            location="宴会厅",
            state="normal",
        )
        objects["banquet_family_photo"] = ObjectState(
            name="全家福照片",
            description="壁炉上方挂着的顾家全家福——顾言站在中间，面带微笑，身旁围绕着今晚的所有人",
            location="宴会厅",
            state="normal",
            notes="拍摄于三年前，所有人看起来关系融洽",
        )
        objects["banquet_candelabra"] = ObjectState(
            name="烛台",
            description="银质烛台上插着三支白色蜡烛，火焰在气流中微微摇曳",
            location="宴会厅",
            state="normal",
            notes="lit",
        )
        objects["banquet_sofa"] = ObjectState(
            name="沙发",
            description="壁炉旁的深色皮质沙发，坐垫上留有刚坐过的凹痕",
            location="宴会厅",
            state="normal",
        )
        objects["banquet_dining_chairs"] = ObjectState(
            name="餐椅",
            description="长桌四周围着六把高背餐椅，椅背上雕刻着精致的花纹",
            location="宴会厅",
            state="normal",
            notes="六把，其中一把被微微拉开",
        )
        objects["banquet_bar_counter"] = ObjectState(
            name="吧台",
            description="角落里的小型吧台，台面上放着几只用过的酒杯和一个开瓶器",
            location="宴会厅",
            state="normal",
            contains=["用过的酒杯", "开瓶器", "鸡尾酒调配器具"],
        )

        # --- 书房 objects ---
        objects["study_desk"] = ObjectState(
            name="书桌",
            description="厚重的红木书桌，桌面上散落着几份文件，一杯凉透的茶放在角落",
            location="书房",
            state="normal",
            contains=["几份文件", "凉茶", "钢笔"],
        )
        objects["study_desk_lamp"] = ObjectState(
            name="台灯",
            description="黄铜底座的复古台灯，发出昏黄的光，是书房里唯一的光源",
            location="书房",
            state="normal",
            notes="on",
        )
        objects["study_safe"] = ObjectState(
            name="保险箱",
            description="书桌后方的小型保险箱，需要密码才能打开",
            location="书房",
            state="locked",
            hidden_clue="will_draft",
            notes="密码未知，外表没有被强行打开的痕迹",
        )
        objects["study_bookshelf"] = ObjectState(
            name="书架",
            description="占据整面墙的胡桃木书架，上面摆满了各种书籍——法律、文学、哲学，还有几本影集",
            location="书房",
            state="normal",
            contains=["法律书籍", "文学作品", "哲学著作", "影集"],
        )
        objects["study_computer"] = ObjectState(
            name="电脑",
            description="书桌上的笔记本电脑，屏幕处于休眠状态，微微发出蓝光",
            location="书房",
            state="normal",
            notes="sleep_mode，需要密码解锁",
        )
        objects["study_wastebasket"] = ObjectState(
            name="纸篓",
            description="书桌旁的竹编纸篓，里面有几团揉皱的纸",
            location="书房",
            state="normal",
            contains=["揉皱的纸团"],
            hidden_clue="crumpled_note",
        )
        objects["study_desk_drawer"] = ObjectState(
            name="书桌抽屉",
            description="书桌下方的三层抽屉，铜质把手上有些许氧化的痕迹",
            location="书房",
            state="closed",
            contains=["钢笔", "笔记本", "一把旧钥匙"],
        )
        objects["study_file_cabinet"] = ObjectState(
            name="文件柜",
            description="墙角的铁皮文件柜，上面贴着'机密'的标签",
            location="书房",
            state="locked",
            notes="需要钥匙才能打开，林岚持有钥匙",
        )

        # --- 花园 objects ---
        objects["garden_stone_bench"] = ObjectState(
            name="石凳",
            description="假山旁的青石长凳，表面因雨水而湿漉漉的",
            location="花园",
            state="normal",
            notes="表面湿滑",
        )
        objects["garden_rockery"] = ObjectState(
            name="假山",
            description="精心堆叠的太湖石假山，造型如同一座微缩山峰，石缝间长着青苔",
            location="花园",
            state="normal",
        )
        objects["garden_shrubs"] = ObjectState(
            name="灌木丛",
            description="花园边缘的一丛修剪过的冬青灌木，枝叶茂密，里面似乎夹着什么东西",
            location="花园",
            state="normal",
            hidden_clue="torn_letter",
        )
        objects["garden_koi_pond"] = ObjectState(
            name="鱼池",
            description="椭圆形的锦鲤池，水面上漂着几片落叶，几条红色锦鲤在水下缓缓游动",
            location="花园",
            state="normal",
        )
        objects["garden_pavilion"] = ObjectState(
            name="凉亭",
            description="花园深处的六角凉亭，飞檐翘角，亭内有石桌石凳，是避雨谈话的好去处",
            location="花园",
            state="normal",
        )
        objects["garden_flower_trellis"] = ObjectState(
            name="花架",
            description="木质花架上攀援着紫藤，雨水顺着藤蔓滴落，散发出湿润的花香",
            location="花园",
            state="normal",
        )

        # --- 酒窖 objects ---
        objects["cellar_wine_barrels"] = ObjectState(
            name="酒桶",
            description="靠墙排列的几只橡木大酒桶，桶身上刻着年份标记，有些桶上有新鲜的刮痕",
            location="酒窖",
            state="normal",
            notes="有些桶上有新的刮痕，似乎被人移动过",
        )
        objects["cellar_wine_rack"] = ObjectState(
            name="酒架",
            description="铁质酒架上横放着数十瓶葡萄酒，瓶身上积着厚厚的灰尘",
            location="酒窖",
            state="normal",
            contains=["陈年葡萄酒若干"],
        )
        objects["cellar_wooden_door"] = ObjectState(
            name="木门",
            description="酒窖最深处的一扇沉重橡木门，门上有铁质锁扣和锈迹斑斑的铰链，门缝里透出微弱的光",
            location="酒窖",
            state="locked",
            notes="门缝里似乎透出微弱的光线，门后隐约传来嗡嗡声",
        )
        objects["cellar_floor"] = ObjectState(
            name="地面",
            description="石板地面上覆盖着薄薄的灰尘，上面有几组杂乱的脚印",
            location="酒窖",
            state="normal",
            hidden_clue="wine_cellar_footprint",
            notes="脚印至少有两种不同的鞋印",
        )
        objects["cellar_wall"] = ObjectState(
            name="墙壁",
            description="酒窖的石砌墙壁，大部分被霉斑覆盖，但有一段区域的颜色明显比周围新",
            location="酒窖",
            state="normal",
            notes="有一段区域颜色略有不同，像是近期修补过",
        )

        # --- 走廊 objects ---
        objects["corridor_wall_sconces"] = ObjectState(
            name="壁灯",
            description="走廊两侧的四盏铁艺壁灯，散发着昏黄的暖光",
            location="走廊",
            state="normal",
            notes="on，共四盏",
        )
        objects["corridor_antique_stand"] = ObjectState(
            name="古董花架",
            description="走廊中段的红木花架，上面摆着一只青花瓷瓶和一盆兰花",
            location="走廊",
            state="normal",
            contains=["青花瓷瓶", "兰花盆栽"],
        )
        objects["corridor_carpet"] = ObjectState(
            name="地毯",
            description="走廊中铺设的深红色波斯地毯，厚实柔软，上面有几处淡淡的脚印",
            location="走廊",
            state="normal",
            notes="脚印方向从书房通往酒窖楼梯",
        )
        objects["corridor_stairs"] = ObjectState(
            name="楼梯",
            description="走廊尽头向下延伸的窄石阶，通往地下酒窖，光线在几步之后就变得暗淡",
            location="走廊",
            state="normal",
        )

        # ── Character inventories ────────────────────────────────────
        character_inventories: Dict[str, CharacterInventory] = {
            "linlan": CharacterInventory(
                character_id="linlan",
                items=[
                    "手机",
                    "钥匙串(有书房钥匙和文件柜钥匙)",
                    "公文包",
                    "口红",
                ],
            ),
            "zhoumu": CharacterInventory(
                character_id="zhoumu",
                items=[
                    "手机",
                    "钱包",
                    "打火机",
                    "一封信(未拆开)",
                ],
            ),
            "songzhi": CharacterInventory(
                character_id="songzhi",
                items=[
                    "手机",
                    "记者证",
                    "录音笔",
                    "小型相机",
                    "笔记本",
                ],
            ),
        }

        # ── Assemble & store ─────────────────────────────────────────
        world = WorldState(
            session_id=session_id,
            time="21:00",
            weather="微雨",
            time_period="入夜",
            locations=locations,
            objects=objects,
            character_inventories=character_inventories,
            player_inventory=[],
            recent_changes=[],
        )

        self._states[session_id] = world
        return world

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_state(self, session_id: str) -> WorldState:
        """Return the current WorldState, raising if the session does not exist."""
        state = self._states.get(session_id)
        if state is None:
            raise ValueError(f"WorldState for session '{session_id}' not found.")
        return state

    # ------------------------------------------------------------------
    # Time & environment
    # ------------------------------------------------------------------

    def advance_time(self, session_id: str) -> None:
        """Advance the in-game clock by ~15 minutes and apply environmental effects."""
        state = self.get_state(session_id)
        state.recent_changes.clear()

        old_period = state.time_period
        state.time = _add_minutes(state.time, 15)
        state.time_period = _time_period_for(state.time)

        if state.time_period != old_period:
            state.recent_changes.append(
                f"时间流逝，现在已是{state.time_period}时分。"
            )

        # After midnight: dim lighting naturally in some locations
        mins = _time_to_minutes(state.time)
        is_late = (mins >= 23 * 60) or (mins < 6 * 60)

        if is_late:
            for loc_key, loc in state.locations.items():
                if loc_key == "酒窖":
                    continue  # already dark
                if loc.lighting == "normal":
                    loc.lighting = "dim"
                    state.recent_changes.append(
                        f"{loc.name}的灯光变得更加昏暗了。"
                    )
                elif loc.lighting == "bright":
                    loc.lighting = "normal"

        # Weather may shift after midnight
        if state.time == "00:00":
            state.weather = "大雨"
            state.recent_changes.append("窗外的雨势骤然加大，雷声隐隐传来。")
            garden = state.locations.get("花园")
            if garden:
                if "雷声" not in garden.ambient_sounds:
                    garden.ambient_sounds.append("雷声")
        elif state.time == "03:00":
            state.weather = "雨停"
            state.recent_changes.append("雨终于停了，空气中弥漫着泥土的气息。")
            garden = state.locations.get("花园")
            if garden:
                if "雷声" in garden.ambient_sounds:
                    garden.ambient_sounds.remove("雷声")

    # ------------------------------------------------------------------
    # Object mutations
    # ------------------------------------------------------------------

    def modify_object(
        self,
        session_id: str,
        object_id: str,
        new_state: str,
        notes: str = "",
    ) -> str:
        """Change an object's state and return a narration string describing the change."""
        state = self.get_state(session_id)
        obj = state.objects.get(object_id)
        if obj is None:
            return f"找不到物品「{object_id}」。"

        old_state = obj.state
        obj.state = new_state
        if notes:
            obj.notes = notes

        # Generate narration for common transitions
        narration = self._narrate_state_change(obj, old_state, new_state)

        # Side effects
        if new_state == "broken":
            obj.interactable = False
            # Breaking a container spills its contents
            if obj.contains:
                narration += f"里面的东西散落一地：{'、'.join(obj.contains)}。"
                obj.contains.clear()
        elif new_state == "open":
            if obj.contains:
                narration += f"里面有：{'、'.join(obj.contains)}。"
        elif new_state == "missing":
            obj.interactable = False

        # Reveal hidden clue when opened / interacted
        if new_state == "open" and obj.hidden_clue:
            narration += f"（发现了重要线索）"

        state.recent_changes.append(narration)
        return narration

    def move_object(
        self,
        session_id: str,
        object_id: str,
        new_location: str,
    ) -> str:
        """Move an object to a new location, character, or player inventory.

        *new_location* can be a location key (e.g. ``"书房"``), a character id
        (e.g. ``"linlan"``), or the literal ``"player"`` for the player's
        inventory.

        Returns a short narration string.
        """
        state = self.get_state(session_id)
        obj = state.objects.get(object_id)
        if obj is None:
            return f"找不到物品「{object_id}」。"

        old_location = obj.location

        if new_location == "player":
            # Move to player inventory
            state.player_inventory.append(obj.name)
            obj.location = "player"
            narration = f"你拿起了{obj.name}。"
        else:
            obj.location = new_location
            target_label = new_location
            # Try to get a human-readable label
            loc = state.locations.get(new_location)
            if loc:
                target_label = loc.name
            narration = f"{obj.name}被移到了{target_label}。"

        obj.state = "moved"
        state.recent_changes.append(narration)
        return narration

    # ------------------------------------------------------------------
    # Location queries
    # ------------------------------------------------------------------

    def get_location_description(self, session_id: str, location: str) -> str:
        """Generate a rich Chinese description of a location's current state."""
        state = self.get_state(session_id)
        loc = state.locations.get(location)
        if loc is None:
            return f"你不知道「{location}」在哪里。"

        parts: List[str] = []

        # Base description
        parts.append(loc.description)

        # Lighting
        light_label = _LIGHTING_DESC.get(loc.lighting, loc.lighting)
        parts.append(f"这里{light_label}。")

        # Ambient sounds
        if loc.ambient_sounds:
            parts.append("你能听到：" + "，".join(loc.ambient_sounds) + "。")

        # Weather effect for garden
        if location == "花园":
            parts.append(f"外面{state.weather}。")

        # Observable details
        if loc.details:
            parts.append("你注意到：" + "；".join(loc.details) + "。")

        # Visible objects (only non-hidden, non-missing ones)
        visible_objs = self.get_objects_at_location(session_id, location)
        if visible_objs:
            obj_strs: List[str] = []
            for o in visible_objs:
                if o.state == "broken":
                    obj_strs.append(f"{o.name}（已损坏）")
                elif o.state == "open":
                    obj_strs.append(f"{o.name}（打开的）")
                elif o.state == "locked":
                    obj_strs.append(f"{o.name}（锁着的）")
                elif o.state == "closed":
                    obj_strs.append(f"{o.name}（关着的）")
                else:
                    obj_strs.append(o.name)
            parts.append("这里有：" + "、".join(obj_strs) + "。")

        # Time
        parts.append(f"现在是{state.time}，{state.time_period}。")

        # Recent changes
        if state.recent_changes:
            parts.append("刚才发生了一些变化：" + "；".join(state.recent_changes) + "。")

        return "\n".join(parts)

    def get_objects_at_location(
        self, session_id: str, location: str
    ) -> List[ObjectState]:
        """Return all visible objects at *location*."""
        state = self.get_state(session_id)
        return [
            obj
            for obj in state.objects.values()
            if obj.location == location
            and obj.state not in ("hidden", "missing")
        ]

    # ------------------------------------------------------------------
    # Inventory queries
    # ------------------------------------------------------------------

    def get_character_items(self, session_id: str, character_id: str) -> List[str]:
        """Return the item list for a character."""
        state = self.get_state(session_id)
        inv = state.character_inventories.get(character_id)
        if inv is None:
            return []
        return list(inv.items)

    # ------------------------------------------------------------------
    # Feasibility check
    # ------------------------------------------------------------------

    def can_player_do(
        self,
        session_id: str,
        action_description: str,
        player_location: str = "",
    ) -> dict:
        """Basic physics / feasibility check for a free-form player action.

        Returns::

            {
                "feasible": bool,
                "reason": str,          # Chinese explanation
                "relevant_objects": [...],
            }
        """
        state = self.get_state(session_id)
        action = action_description.lower()
        relevant: List[str] = []

        # Find objects mentioned in the action
        for obj_id, obj in state.objects.items():
            if obj.name in action_description:
                relevant.append(obj_id)

        # If nothing matched by name, try a looser check
        if not relevant:
            for obj_id, obj in state.objects.items():
                # Check partial name match (at least 2 chars)
                for i in range(len(obj.name) - 1):
                    fragment = obj.name[i:i + 2]
                    if fragment in action_description:
                        relevant.append(obj_id)
                        break

        # Determine feasibility
        if not relevant:
            # No specific object targeted — could be a general action
            return {
                "feasible": True,
                "reason": "未涉及特定物品，可以尝试。",
                "relevant_objects": [],
            }

        # Check each relevant object
        problems: List[str] = []
        for obj_id in relevant:
            obj = state.objects[obj_id]

            # Location check
            if player_location and obj.location not in (
                player_location,
                "player",
            ):
                problems.append(
                    f"{obj.name}不在你当前的位置（{player_location}），"
                    f"它在{obj.location}。"
                )
                continue

            # State checks
            if obj.state == "missing":
                problems.append(f"{obj.name}已经不在了。")
            elif obj.state == "broken":
                problems.append(f"{obj.name}已经损坏，无法互动。")
            elif not obj.interactable:
                problems.append(f"{obj.name}目前无法互动。")

            # Locked container checks
            if obj.state == "locked":
                # Check for "open" or "打开" type actions
                open_words = ["打开", "开", "开锁", "解锁", "撬"]
                if any(w in action_description for w in open_words):
                    # Check if player has a key
                    has_key = any("钥匙" in item for item in state.player_inventory)
                    if not has_key:
                        # Check if action mentions forcing it
                        force_words = ["撬", "砸", "踹", "强行", "破坏"]
                        if not any(w in action_description for w in force_words):
                            problems.append(
                                f"{obj.name}是锁着的，你需要找到钥匙或者想办法强行打开。"
                            )

        if problems:
            return {
                "feasible": False,
                "reason": " ".join(problems),
                "relevant_objects": relevant,
            }

        return {
            "feasible": True,
            "reason": "可以执行。",
            "relevant_objects": relevant,
        }

    # ------------------------------------------------------------------
    # Batch changes
    # ------------------------------------------------------------------

    def apply_changes(self, session_id: str, changes: List[dict]) -> None:
        """Apply a batch of world-state changes.

        Each *change* dict must have a ``"type"`` key.  Supported types:

        - ``modify_object``: ``{object_id, new_state, notes?}``
        - ``move_object``:   ``{object_id, new_location}``
        - ``change_lighting``: ``{location, lighting}``
        - ``add_detail``:    ``{location, detail}``
        - ``remove_detail``: ``{location, detail}``
        - ``remove_object``: ``{object_id}``
        - ``add_inventory``: ``{character_id | "player", item}``
        - ``remove_inventory``: ``{character_id | "player", item}``
        """
        state = self.get_state(session_id)

        for change in changes:
            ctype = change.get("type", "")

            if ctype == "modify_object":
                self.modify_object(
                    session_id,
                    change["object_id"],
                    change["new_state"],
                    change.get("notes", ""),
                )

            elif ctype == "move_object":
                self.move_object(
                    session_id,
                    change["object_id"],
                    change["new_location"],
                )

            elif ctype == "change_lighting":
                loc = state.locations.get(change["location"])
                if loc:
                    old = loc.lighting
                    loc.lighting = change["lighting"]
                    new_label = _LIGHTING_DESC.get(change["lighting"], change["lighting"])
                    state.recent_changes.append(
                        f"{loc.name}的光线变为{new_label}了。"
                    )

            elif ctype == "add_detail":
                loc = state.locations.get(change["location"])
                if loc:
                    detail = change["detail"]
                    if detail not in loc.details:
                        loc.details.append(detail)
                        state.recent_changes.append(f"你注意到{detail}。")

            elif ctype == "remove_detail":
                loc = state.locations.get(change["location"])
                if loc:
                    detail = change["detail"]
                    if detail in loc.details:
                        loc.details.remove(detail)

            elif ctype == "remove_object":
                obj_id = change["object_id"]
                obj = state.objects.get(obj_id)
                if obj:
                    obj.state = "missing"
                    obj.interactable = False
                    state.recent_changes.append(f"{obj.name}不见了。")

            elif ctype == "add_inventory":
                target = change.get("character_id", change.get("target", ""))
                item = change["item"]
                if target == "player":
                    if item not in state.player_inventory:
                        state.player_inventory.append(item)
                        state.recent_changes.append(f"你获得了{item}。")
                else:
                    inv = state.character_inventories.get(target)
                    if inv and item not in inv.items:
                        inv.items.append(item)

            elif ctype == "remove_inventory":
                target = change.get("character_id", change.get("target", ""))
                item = change["item"]
                if target == "player":
                    if item in state.player_inventory:
                        state.player_inventory.remove(item)
                        state.recent_changes.append(f"你失去了{item}。")
                else:
                    inv = state.character_inventories.get(target)
                    if inv and item in inv.items:
                        inv.items.remove(item)

    # ------------------------------------------------------------------
    # State summary (for LLM prompt injection)
    # ------------------------------------------------------------------

    def get_state_summary(self, session_id: str, location: str) -> str:
        """Compact Chinese summary of *location* state for injecting into LLM prompts."""
        state = self.get_state(session_id)
        loc = state.locations.get(location)
        if loc is None:
            return f"未知地点：{location}"

        lines: List[str] = []
        lines.append(f"【当前场景：{loc.name}】")
        lines.append(f"时间：{state.time}（{state.time_period}）| 天气：{state.weather}")
        lines.append(f"光线：{_LIGHTING_DESC.get(loc.lighting, loc.lighting)}")

        if loc.ambient_sounds:
            lines.append(f"环境音：{'、'.join(loc.ambient_sounds)}")

        # Objects summary
        visible = self.get_objects_at_location(session_id, location)
        if visible:
            obj_parts: List[str] = []
            for o in visible:
                tag = ""
                if o.state not in ("normal",):
                    tag = f"[{o.state}]"
                obj_parts.append(f"{o.name}{tag}")
            lines.append(f"物品：{'、'.join(obj_parts)}")

        # Details
        if loc.details:
            lines.append(f"细节：{'；'.join(loc.details)}")

        # Player inventory
        if state.player_inventory:
            lines.append(f"玩家持有：{'、'.join(state.player_inventory)}")

        # Connections
        if loc.connections:
            lines.append(f"可前往：{'、'.join(loc.connections)}")

        # Recent changes
        if state.recent_changes:
            lines.append(f"最近变化：{'；'.join(state.recent_changes)}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _narrate_state_change(obj: ObjectState, old: str, new: str) -> str:
        """Produce a short Chinese narration for an object state transition."""
        name = obj.name

        # Specific transition narrations
        transitions = {
            ("normal", "broken"): f"「砰」的一声，{name}碎了一地。",
            ("normal", "open"): f"你打开了{name}。",
            ("closed", "open"): f"你打开了{name}。",
            ("locked", "open"): f"锁「咔哒」一声弹开，你打开了{name}。",
            ("normal", "closed"): f"你关上了{name}。",
            ("open", "closed"): f"你关上了{name}。",
            ("normal", "locked"): f"{name}被锁上了。",
            ("normal", "hidden"): f"{name}被藏了起来。",
            ("normal", "moved"): f"{name}被移动了位置。",
            ("normal", "missing"): f"{name}消失了。",
        }

        narration = transitions.get((old, new))
        if narration:
            return narration

        # Fallback
        if new == "broken":
            return f"{name}被破坏了。"
        if new == "open":
            return f"{name}被打开了。"
        if new == "closed":
            return f"{name}被关上了。"
        if new == "locked":
            return f"{name}被锁上了。"
        if new == "missing":
            return f"{name}不见了。"
        return f"{name}的状态变为了{new}。"

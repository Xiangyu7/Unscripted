"""Template 1: 失踪-自导自演型 — extracted from gu_family_case.py.

Pattern: the victim fakes their own disappearance to test people around them.
The insider (suspect_A) is an accomplice, the friend (suspect_B) has motive,
and the outsider (suspect_C) has prior knowledge.
"""

from stories.templates.base_template import (
    CharacterSlot,
    ClueSlot,
    EndingCondition,
    StoryTemplate,
    TruthChainStep,
)

SELF_STAGED_TEMPLATE = StoryTemplate(
    template_id="self_staged",
    template_name="失踪-自导自演型",
    description="受害者自导自演失踪，为了试探身边人。适合豪门、商战、家族等主题。",
    suspect_count=3,
    location_count=5,
    clue_count=9,
    truth_type="self_staged",

    # ── Truth chain (abstracted from gu_family_case) ──
    truth_chain=[
        TruthChainStep(
            order=1,
            template="{victim}失踪前独自进入{location_B}取走{mcguffin}",
            involves=["victim"],
        ),
        TruthChainStep(
            order=2,
            template="{suspect_A_name}受{victim}委托{protect_action}",
            involves=["victim", "suspect_A"],
        ),
        TruthChainStep(
            order=3,
            template="{suspect_B_name}昨晚与{victim}因{conflict_object}激烈争吵",
            involves=["victim", "suspect_B"],
        ),
        TruthChainStep(
            order=4,
            template="{suspect_C_name}收到匿名线报来到现场——线报其实是{victim}自己发的",
            involves=["victim", "suspect_C"],
        ),
        TruthChainStep(
            order=5,
            template="{victim}目前藏在{hidden_location}观察所有人",
            involves=["victim"],
        ),
    ],

    # ── Character slots ──
    character_slots=[
        CharacterSlot(
            slot_id="suspect_A",
            role_type="insider",
            relation_to_victim="employee",
            secret_type="accomplice",
            hard_boundary_templates=[
                "绝不主动提及{mcguffin}",
                "绝不承认知道{victim}的下落",
                "绝不透露与{victim}的私下交易内容",
            ],
            trust_default=35,
            suspicion_default=45,
            private_knowledge_instructions=[
                "知道{location_B}在{victim}失踪前被{victim}本人进入过",
                "知道{mcguffin}已被转移到安全位置",
                "知道{victim}有一个'试探计划'但不知道全部细节",
            ],
        ),
        CharacterSlot(
            slot_id="suspect_B",
            role_type="relation",
            relation_to_victim="friend",
            secret_type="innocent_with_secret",
            hard_boundary_templates=[
                "绝不主动承认昨晚争吵的具体内容",
                "绝不透露自己知道{mcguffin}要被{motive_action}",
                "绝不承认自己去过{hidden_location}附近",
            ],
            trust_default=40,
            suspicion_default=55,
            private_knowledge_instructions=[
                "知道{victim}昨晚情绪异常激动",
                "知道{mcguffin}可能要被{motive_action}",
                "听到有人去过{hidden_location}但没看清是谁",
            ],
        ),
        CharacterSlot(
            slot_id="suspect_C",
            role_type="outsider",
            relation_to_victim="stranger",
            secret_type="innocent_with_secret",
            hard_boundary_templates=[
                "绝不透露匿名线报的存在",
                "绝不承认自己提前知道会出事",
                "绝不透露信息来源",
            ],
            trust_default=50,
            suspicion_default=35,
            private_knowledge_instructions=[
                "收到过匿名信息提到'{mcguffin}'和'真相'",
                "知道{setting}内部有激烈的{conflict_type}",
                "注意到{suspect_A_name}在事发前曾去过{location_B}方向",
            ],
        ),
    ],

    # ── Clue slots (9 clues, 3 layers) ──
    clue_slots=[
        # Layer 1: physical evidence (easy discovery)
        ClueSlot(
            slot_id="clue_L1_a",
            layer=1,
            location_slot="{location_B}",
            discover_condition_template="search{location_B}",
            tension_min=0,
            points_to="victim_movement",
            text_instruction="在{location_B}发现的物理痕迹，暗示有人急忙离开（如划痕、脚印、打翻的东西）",
        ),
        ClueSlot(
            slot_id="clue_L1_b",
            layer=1,
            location_slot="{hidden_location}",
            discover_condition_template="search{hidden_location}",
            tension_min=0,
            points_to="victim_movement",
            text_instruction="在{hidden_location}入口发现的痕迹，暗示有人进去了但没出来",
        ),
        ClueSlot(
            slot_id="clue_L1_c",
            layer=1,
            location_slot="{location_C}",
            discover_condition_template="search{location_C}",
            tension_min=0,
            points_to="plan_exists",
            text_instruction="在{location_C}发现的碎片化信息（撕碎的信/纸条），暗示有预谋的计划",
        ),
        ClueSlot(
            slot_id="clue_L1_d",
            layer=1,
            location_slot="{location_A}",
            discover_condition_template="search{location_A} 或 observe仔细",
            tension_min=0,
            points_to="prior_knowledge",
            text_instruction="在{location_A}发现的纸条或留言，暗示有人提前知道事情会发生",
        ),
        # Layer 2: key evidence (needs tension)
        ClueSlot(
            slot_id="clue_L2_a",
            layer=2,
            location_slot="{location_B}",
            discover_condition_template="search{location_B} 且 tension>=30",
            tension_min=30,
            points_to="motive",
            text_instruction="在{location_B}深处找到的{mcguffin}相关文件，旁边有{victim}的批注暗示这是一场测试",
        ),
        ClueSlot(
            slot_id="clue_L2_b",
            layer=2,
            location_slot="{hidden_location}",
            discover_condition_template="search{hidden_location} 且 tension>=35",
            tension_min=35,
            points_to="voluntary_hiding",
            text_instruction="在{hidden_location}发现有人准备了生活用品（食物、水、毯子），暗示有人自愿待在这里",
        ),
        # Layer 3: truth evidence (needs high tension)
        ClueSlot(
            slot_id="clue_L3_a",
            layer=3,
            location_slot="{location_A}",
            discover_condition_template="search{location_A} 且 tension>=45",
            tension_min=45,
            points_to="accomplice_link",
            text_instruction="{suspect_A_name}的通讯设备上有{victim}在'失踪后'发的消息：'{secret_message}'",
        ),
        ClueSlot(
            slot_id="clue_L3_b",
            layer=3,
            location_slot="{hidden_location}",
            discover_condition_template="eavesdrop{hidden_location} 或 search{hidden_location} 且 tension>=50",
            tension_min=50,
            points_to="victim_alive",
            text_instruction="在{hidden_location}最深处听到微弱的人类声响（呼吸/脚步），{victim}还活着就在里面",
        ),
        ClueSlot(
            slot_id="clue_L3_c",
            layer=3,
            location_slot="{location_B}",
            discover_condition_template="search{location_B} 且 tension>=55",
            tension_min=55,
            points_to="staged_scene",
            text_instruction="仔细检查后发现{location_B}的'失踪现场'过于整齐，痕迹是人为布置的而非真实挣扎",
        ),
    ],

    # ── Ending conditions ──
    ending_conditions=[
        EndingCondition(
            ending_type="perfect",
            required_clue_layers=[1, 2, 3],
            required_truth_keywords=["自导自演", "试探", "活着"],
        ),
        EndingCondition(
            ending_type="good",
            required_clue_layers=[1, 2],
            required_truth_keywords=["自愿", "计划"],
        ),
        EndingCondition(
            ending_type="partial",
            required_clue_layers=[1],
            required_truth_keywords=[],
        ),
        EndingCondition(
            ending_type="fail",
            required_clue_layers=[],
            required_truth_keywords=[],
        ),
    ],

    # ── Opening event template ──
    opening_template=(
        "{event_atmosphere}，{setting}的{event_name}正式开始。"
        "然而，{victim_title}{victim}却在{event_name}进行到一半时不知所踪。"
        "{authority_figure}宣布所有人不得离开，等待事情水落石出。"
    ),

    # ── Slot manifest (everything the LLM must fill) ──
    slots={
        # Setting
        "setting": "故事发生的地点名称（如'顾家老宅'、'远洋邮轮'、'雪山别墅'）",
        "event_name": "正在进行的活动（如'年度晚宴'、'航行晚会'、'新年聚会'）",
        "event_atmosphere": "开场氛围描述（如'华灯初上'、'暮色笼罩海面'）",
        "authority_figure": "宣布封锁的权威人物（如'管家'、'船长'、'别墅管家'）",

        # Locations (5)
        "location_A": "主要社交场所（如'宴会厅'、'甲板沙龙'、'大厅'）",
        "location_B": "受害者的私人空间（如'书房'、'船长室'、'工作间'）",
        "location_C": "室外或半开放空间（如'花园'、'甲板'、'露台'）",
        "hidden_location": "隐秘的藏身之处（如'酒窖'、'底舱'、'地下室'）",
        "location_E": "连接各处的通道（如'走廊'、'甲板走道'、'楼梯间'）",

        # Victim
        "victim": "受害者/失踪者的姓名",
        "victim_title": "受害者的头衔或称谓（如'主人'、'船长'、'老板'）",
        "victim_id": "受害者的英文ID（小写字母，如'guyan'、'captain'）",

        # Core McGuffin
        "mcguffin": "核心争议物品（如'遗嘱'、'航海日志'、'合同'）",
        "motive_action": "围绕核心物品的争议行为（如'修改'、'销毁'、'公开'）",
        "conflict_object": "引发冲突的原因（如'遗产分配'、'航线变更'、'股权变动'）",
        "conflict_type": "冲突的性质（如'遗产纠纷'、'权力斗争'、'商业纠纷'）",

        # Suspect A (insider/accomplice)
        "suspect_A_name": "嫌疑人A的姓名（内部人/协助者）",
        "suspect_A_id": "嫌疑人A的英文ID",
        "suspect_A_role": "嫌疑人A的公开身份（如'秘书'、'大副'、'助理'）",
        "suspect_A_style": "嫌疑人A的说话风格描述",
        "suspect_A_goal": "嫌疑人A的个人目标",
        "suspect_A_fear": "嫌疑人A害怕什么",
        "suspect_A_speaking_rules": "嫌疑人A的语言习惯和小动作",

        # Suspect B (relation/has motive)
        "suspect_B_name": "嫌疑人B的姓名（关系人/有动机）",
        "suspect_B_id": "嫌疑人B的英文ID",
        "suspect_B_role": "嫌疑人B的公开身份（如'发小'、'合伙人'、'兄弟'）",
        "suspect_B_style": "嫌疑人B的说话风格描述",
        "suspect_B_goal": "嫌疑人B的个人目标",
        "suspect_B_fear": "嫌疑人B害怕什么",
        "suspect_B_speaking_rules": "嫌疑人B的语言习惯和小动作",

        # Suspect C (outsider)
        "suspect_C_name": "嫌疑人C的姓名（外部人/旁观者）",
        "suspect_C_id": "嫌疑人C的英文ID",
        "suspect_C_role": "嫌疑人C的公开身份（如'记者'、'旅客'、'客人'）",
        "suspect_C_style": "嫌疑人C的说话风格描述",
        "suspect_C_goal": "嫌疑人C的个人目标",
        "suspect_C_fear": "嫌疑人C害怕什么",
        "suspect_C_speaking_rules": "嫌疑人C的语言习惯和小动作",

        # Action verbs
        "protect_action": "A协助victim的行为（如'转移遗嘱副本'、'隐藏日志'）",
        "secret_message": "victim发给A的秘密指令（如'按计划行动'）",

        # Relationship descriptions
        "suspect_A_view_B": "A对B的看法",
        "suspect_A_view_C": "A对C的看法",
        "suspect_A_view_victim": "A对victim的看法",
        "suspect_B_view_A": "B对A的看法",
        "suspect_B_view_C": "B对C的看法",
        "suspect_B_view_victim": "B对victim的看法",
        "suspect_C_view_A": "C对A的看法",
        "suspect_C_view_B": "C对B的看法",
        "suspect_C_view_victim": "C对victim的看法",

        # Clue texts (9 clues)
        "clue_L1_a_text": "第一层线索a的具体描写（{location_B}中的物理痕迹）",
        "clue_L1_b_text": "第一层线索b的具体描写（{hidden_location}入口的痕迹）",
        "clue_L1_c_text": "第一层线索c的具体描写（{location_C}中的碎片信息）",
        "clue_L1_d_text": "第一层线索d的具体描写（{location_A}中的提前预警）",
        "clue_L2_a_text": "第二层线索a的具体描写（{mcguffin}相关文件及victim的批注）",
        "clue_L2_b_text": "第二层线索b的具体描写（{hidden_location}中的生活用品）",
        "clue_L3_a_text": "第三层线索a的具体描写（suspect_A设备上victim'失踪后'的消息）",
        "clue_L3_b_text": "第三层线索b的具体描写（{hidden_location}深处的人类声响）",
        "clue_L3_c_text": "第三层线索c的具体描写（{location_B}现场痕迹是人为布置的）",

        # Scene description
        "scene_name": "初始场景全名（如'顾家老宅·宴会厅'）",
    },
)

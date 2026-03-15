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


def create_initial_state(session_id: str) -> GameState:
    """Create the initial game state for the Gu Family Missing Case."""

    truth = StoryTruth(
        core_truth=(
            "林岚拿走了遗嘱副本，她不是凶手。顾言其实是自己策划了失踪，"
            "目的是试探身边人的真实面目。周牧昨晚与顾言争执是因为发现"
            "顾言要修改遗嘱，将大部分财产捐给基金会。"
        ),
        culprit=None,
        hidden_chain=[
            "顾言失踪前独自进入书房取走原版遗嘱",
            "林岚受顾言委托转移遗嘱副本",
            "周牧昨晚与顾言因遗产分配激烈争吵",
            "宋知微收到匿名信——信其实是顾言自己寄的",
            "顾言目前藏在酒窖密室中观察所有人",
        ],
    )

    characters = [
        Character(
            id="linlan",
            name="林岚",
            public_role="顾家秘书",
            style="说话简洁克制，用词精准，从不主动暴露情绪",
            goal="保护遗嘱副本不被发现，完成顾言交代的任务",
            fear="被发现她与顾言有私下交易，被怀疑是共犯",
            secret="她受顾言委托转移了遗嘱副本，知道顾言失踪是自导自演",
            private_knowledge=[
                "知道书房被顾言本人进入过",
                "知道遗嘱副本已被她转移到安全位置",
                "知道顾言有一个'试探计划'但不知道全部细节",
            ],
            relation_map={
                "zhoumu": "不信任，认为他觊觎遗产",
                "songzhi": "警惕，担心她会挖出真相",
                "guyan": "忠诚，是她的雇主和信任者",
            },
            trust_to_player=35,
            suspicion=45,
            speaking_rules=(
                "永远不直接否认，而是用反问把球踢回去：'您为什么会这么想？''这个问题很有趣——但您确定问对人了吗？'"
                "永远称呼顾言为'顾先生'——这种刻意的距离感本身就是一种伪装。"
                "被逼急时不会慌，而是变得更冷：语速放慢，眼神直视，像一面墙。"
                "偶尔会暗示别人更可疑：'与其问我，不如去看看周牧昨晚到底在做什么。'"
            ),
            hard_boundaries=[
                "绝不主动提及遗嘱副本",
                "绝不承认知道顾言的下落",
                "绝不透露与顾言的私下交易内容",
            ],
            location="宴会厅",
        ),
        Character(
            id="zhoumu",
            name="周牧",
            public_role="顾言发小",
            style="表面大大咧咧爱开玩笑，但一提到钱和遗产就会紧张，笑容变得僵硬",
            goal="阻止顾言把遗产捐出去，保住自己那份",
            fear="被发现昨晚和顾言的争吵内容，被当成嫌疑人",
            secret="昨晚与顾言大吵一架，因为得知顾言要把大部分遗产捐给基金会",
            private_knowledge=[
                "知道顾言昨晚情绪异常激动",
                "知道遗嘱可能要被修改",
                "听到有人去过酒窖但没看清是谁",
            ],
            relation_map={
                "linlan": "怀疑她知道更多内幕",
                "songzhi": "讨厌记者，觉得她会搞事",
                "guyan": "表面兄弟情深，实际因为钱已经有裂痕",
            },
            trust_to_player=40,
            suspicion=55,
            speaking_rules=(
                "用玩笑和自嘲来回避严肃问题：'哈哈你这是审犯人呢？我又不是嫌疑人……吧？'"
                "每次说'说起来'三个字，后面跟的往往是半真半假的话。"
                "被逼急会突然提高音量：'你到底想怎样！'——然后立刻后悔，压低声音装没事。"
                "会主动甩锅给林岚：'你不觉得林岚知道得太多了吗？一个秘书为什么这么淡定？'"
                "喝酒喝得越多，说的真话越多——但他自己意识不到这一点。"
            ),
            hard_boundaries=[
                "绝不主动承认昨晚争吵的具体内容",
                "绝不透露自己知道遗嘱要修改",
                "绝不承认自己去过酒窖附近",
            ],
            location="宴会厅",
        ),
        Character(
            id="songzhi",
            name="宋知微",
            public_role="记者",
            style="说话像在采访——快速、精准、总是在追问。会用反复确认的方式逼人说出更多",
            goal="拿到顾家遗产丑闻的独家新闻素材",
            fear="被发现她提前就知道会出事，被怀疑是策划者",
            secret="她收到过匿名爆料信，信中暗示今晚顾家会有大事发生",
            private_knowledge=[
                "收到过匿名信提到'遗产'和'真相'",
                "知道顾家内部有激烈的遗产纠纷",
                "注意到林岚在晚宴开始前曾去过书房方向",
            ],
            relation_map={
                "linlan": "重要信息源，但对方很难撬开嘴",
                "zhoumu": "最容易突破的对象，情绪化",
                "guyan": "采访目标，但现在失踪了",
            },
            trust_to_player=50,
            suspicion=35,
            speaking_rules=(
                "像做采访一样说话——快节奏、精准、连续追问不给人喘息的机会。"
                "口头禅：'等一下——你刚才说……''这条信息很有趣。''我需要确认一下。'"
                "会主动抛出信息来诱导别人说更多：'我听说遗嘱的事了——你知道细节吗？'"
                "习惯性推眼镜——尤其是发现关键信息时，这个动作会变慢。"
                "对侦探有一种同行间的尊重，但也把他当作竞争对手——她也在'调查'。"
            ),
            hard_boundaries=[
                "绝不透露匿名信的存在",
                "绝不承认自己提前知道会出事",
                "绝不透露信息源",
            ],
            location="宴会厅",
        ),
    ]

    clues = [
        # ── 第一层：物理证据（容易发现，告诉你"发生了什么"）──
        Clue(
            id="study_scratches",
            text="书房门把手上有新鲜划痕，但奇怪的是——划痕是从里面刮出来的，像是有人急着从书房里出去",
            location="书房",
            discover_condition="search书房",
        ),
        Clue(
            id="wine_cellar_footprint",
            text="酒窖门口有一串新鲜脚印，脚印只有进去的方向，没有出来的",
            location="酒窖",
            discover_condition="search酒窖",
        ),
        Clue(
            id="torn_letter",
            text="花园灌木丛中有一封被撕碎的信，拼凑后能辨认出几个字：'……计划已经……今晚……配合……'",
            location="花园",
            discover_condition="search花园",
        ),
        Clue(
            id="anonymous_tip",
            text="大厅垃圾桶里有一个写着'今晚注意遗产'的纸条，笔迹工整——这不像是匆忙写下的，更像是提前准备好的",
            location="宴会厅",
            discover_condition="search宴会厅 或 observe仔细",
        ),

        # ── 第二层：关键证据（需要一定条件，告诉你"为什么"）──
        Clue(
            id="will_draft",
            text="书房抽屉深处有一份遗嘱修改草稿，顾言计划将大部分财产捐给慈善基金会。草稿旁边有一张便签：'看看他们的反应'",
            location="书房",
            discover_condition="search书房 且 tension>=30",
        ),
        Clue(
            id="cellar_provisions",
            text="酒窖角落里有人准备了矿泉水、三明治和一条毛毯——这不像是被绑架，更像是有人打算在这里待一段时间",
            location="酒窖",
            discover_condition="search酒窖 且 tension>=35",
        ),

        # ── 第三层：真相证据（需要深入调查，告诉你"是谁"）──
        Clue(
            id="linlan_phone_log",
            text="你瞥见林岚手机屏幕上的最后一条消息——发件人是'顾先生'，时间是今晚8:47，内容：'按计划行动'。但顾言不是已经失踪了吗？",
            location="宴会厅",
            discover_condition="search宴会厅 且 tension>=45",
        ),
        Clue(
            id="cellar_sound",
            text="酒窖最深处的墙壁后面传来微弱但有节奏的声响——那是呼吸声。有人活着，就在墙后面",
            location="酒窖",
            discover_condition="eavesdrop酒窖 或 search酒窖 且 tension>=50",
        ),
        Clue(
            id="staged_evidence",
            text="仔细检查后你发现，书房里'失踪现场'的痕迹太整齐了——翻倒的椅子、打翻的茶杯，每一处都像是被人精心摆放的，而不是真正挣扎的结果",
            location="书房",
            discover_condition="search书房 且 tension>=55",
        ),
    ]

    knowledge = KnowledgeGraph(
        public_facts=[
            "顾家继承人顾言在晚宴中途失踪",
            "所有人暂时不能离开老宅",
            "今晚是顾家每年一度的家族晚宴",
        ],
        player_known=[],
        character_beliefs={
            "linlan": [],
            "zhoumu": [],
            "songzhi": [],
        },
        facts=[
            _fact(
                "public_missing",
                "顾家继承人顾言在晚宴中途失踪",
                FactScope.public,
                holders=["linlan", "zhoumu", "songzhi", "player"],
                revealed_to_player=True,
                publicly_revealed=True,
                source="opening",
                related_characters=["linlan", "zhoumu", "songzhi", "guyan"],
                tags=["opening"],
            ),
            _fact(
                "public_lockdown",
                "所有人暂时不能离开老宅",
                FactScope.public,
                holders=["linlan", "zhoumu", "songzhi", "player"],
                revealed_to_player=True,
                publicly_revealed=True,
                source="opening",
                tags=["opening", "constraint"],
            ),
            _fact(
                "public_family_dinner",
                "今晚是顾家每年一度的家族晚宴",
                FactScope.public,
                holders=["linlan", "zhoumu", "songzhi", "player"],
                revealed_to_player=True,
                publicly_revealed=True,
                source="opening",
                tags=["opening"],
            ),
            _fact(
                "linlan_study_entry",
                "林岚知道书房在顾言失踪前被顾言本人进入过。",
                FactScope.npc_private,
                holders=["linlan"],
                source="backstory",
                related_characters=["linlan", "guyan"],
                tags=["study", "private"],
            ),
            _fact(
                "linlan_will_copy",
                "林岚已经转移了遗嘱副本，并打算继续隐瞒它的去向。",
                FactScope.npc_private,
                holders=["linlan"],
                source="backstory",
                related_characters=["linlan", "guyan"],
                tags=["will", "private"],
            ),
            _fact(
                "linlan_test_plan",
                "林岚知道顾言在执行一场试探计划，但她并不掌握全部细节。",
                FactScope.shared_secret,
                holders=["linlan"],
                source="backstory",
                related_characters=["linlan", "guyan"],
                tags=["plan", "secret"],
            ),
            _fact(
                "zhoumu_will_conflict",
                "周牧知道顾言准备修改遗嘱，把大部分财产捐给基金会。",
                FactScope.npc_private,
                holders=["zhoumu"],
                source="backstory",
                related_characters=["zhoumu", "guyan"],
                tags=["will", "private"],
            ),
            _fact(
                "zhoumu_argument",
                "周牧昨晚和顾言发生过一次激烈争吵。",
                FactScope.npc_private,
                holders=["zhoumu"],
                source="backstory",
                related_characters=["zhoumu", "guyan"],
                tags=["argument", "private"],
            ),
            _fact(
                "zhoumu_cellar_hint",
                "周牧听到过有人去过酒窖附近，但没看清是谁。",
                FactScope.npc_private,
                holders=["zhoumu"],
                source="backstory",
                related_characters=["zhoumu"],
                tags=["cellar", "private"],
            ),
            _fact(
                "songzhi_anonymous_tip",
                "宋知微收到过匿名爆料信，信中暗示今晚顾家会出事。",
                FactScope.npc_private,
                holders=["songzhi"],
                source="backstory",
                related_characters=["songzhi"],
                tags=["tip", "private"],
            ),
            _fact(
                "songzhi_estate_conflict",
                "宋知微已经判断顾家内部存在激烈的遗产纠纷。",
                FactScope.npc_private,
                holders=["songzhi"],
                source="backstory",
                related_characters=["songzhi", "zhoumu", "linlan"],
                tags=["estate", "private"],
            ),
            _fact(
                "songzhi_saw_linlan_study",
                "宋知微注意到林岚在晚宴开始前曾去过书房方向。",
                FactScope.npc_private,
                holders=["songzhi"],
                source="backstory",
                related_characters=["songzhi", "linlan"],
                tags=["study", "private"],
            ),
            _fact(
                "shared_estate_tension",
                "这场失踪案和顾家的遗产安排高度相关。",
                FactScope.shared_secret,
                holders=["zhoumu", "songzhi"],
                source="backstory",
                related_characters=["zhoumu", "songzhi", "guyan"],
                tags=["estate", "shared"],
            ),
            # ── Clue facts: 第一层（物理证据）──
            _fact(
                "clue_study_scratches",
                "书房门把手划痕是从里面刮出来的——说明有人从书房里急着出去，不是闯进来的。",
                FactScope.player_known,
                source="study_scratches",
                tags=["clue", "study"],
            ),
            _fact(
                "clue_wine_cellar_footprint",
                "酒窖的脚印只有进去的方向，没有出来的——有人进了酒窖但没有离开。",
                FactScope.player_known,
                source="wine_cellar_footprint",
                tags=["clue", "cellar"],
            ),
            _fact(
                "clue_torn_letter",
                "花园里被撕碎的信提到了'计划'和'配合'——今晚的事情是有人提前安排的。",
                FactScope.player_known,
                source="torn_letter",
                tags=["clue", "letter", "plan"],
            ),
            _fact(
                "clue_anonymous_tip",
                "纸条的笔迹工整、提前准备——写纸条的人早就知道今晚会出事。",
                FactScope.player_known,
                source="anonymous_tip",
                tags=["clue", "tip"],
            ),
            # ── Clue facts: 第二层（关键证据）──
            _fact(
                "clue_will_draft",
                "遗嘱草稿旁的便签写着'看看他们的反应'——顾言在故意测试身边人对遗产变动的反应。",
                FactScope.player_known,
                source="will_draft",
                tags=["clue", "will", "motive"],
            ),
            _fact(
                "clue_cellar_provisions",
                "酒窖里有人准备了食物和毛毯——这不是绑架现场，是有人自愿待在这里的。",
                FactScope.player_known,
                source="cellar_provisions",
                tags=["clue", "cellar", "voluntary"],
            ),
            # ── Clue facts: 第三层（真相证据）──
            _fact(
                "clue_linlan_phone_log",
                "林岚的手机上有顾言在'失踪后'发的消息'按计划行动'——顾言还活着，而且林岚是共谋者。",
                FactScope.player_known,
                source="linlan_phone_log",
                tags=["clue", "phone", "conspiracy"],
            ),
            _fact(
                "clue_cellar_sound",
                "酒窖墙壁后面是人的呼吸声——有人活着藏在那里，很可能就是顾言。",
                FactScope.player_known,
                source="cellar_sound",
                tags=["clue", "cellar", "alive"],
            ),
            _fact(
                "clue_staged_evidence",
                "书房的'失踪现场'是精心布置的——翻倒的椅子和打翻的茶杯都像道具，不是真正的挣扎痕迹。整场失踪是被导演的。",
                FactScope.player_known,
                source="staged_evidence",
                tags=["clue", "staged", "fake"],
            ),
            _fact(
                "truth_will_transfer",
                "真相是林岚受顾言委托转移了遗嘱副本，她不是凶手。",
                FactScope.truth,
                source="truth",
                related_characters=["linlan", "guyan"],
                tags=["truth", "will"],
            ),
            _fact(
                "truth_self_staged",
                "真相是顾言自导自演了这场失踪案，目的是试探所有人。",
                FactScope.truth,
                source="truth",
                related_characters=["guyan", "linlan", "zhoumu", "songzhi"],
                tags=["truth", "core"],
            ),
            _fact(
                "truth_cellar_hideout",
                "顾言目前藏在酒窖密室中观察所有人的反应。",
                FactScope.truth,
                source="truth",
                related_characters=["guyan"],
                tags=["truth", "cellar"],
            ),
        ],
    )

    events = [
        Event(
            round=0,
            type="opening",
            text=(
                "华灯初上，顾家老宅的年度晚宴正式开始。然而，主人顾言却在晚宴进行到一半时"
                "不知所踪。管家宣布所有人不得离开，等待事情水落石出。"
            ),
        ),
    ]

    return GameState(
        session_id=session_id,
        story_id="gu_family_case",
        title="豪门晚宴失踪案",
        scene="顾家老宅·宴会厅",
        phase="自由试探",
        round=0,
        tension=20,
        truth=truth,
        characters=characters,
        clues=clues,
        knowledge=knowledge,
        events=events,
        available_scenes=["宴会厅", "书房", "花园", "酒窖", "走廊"],
        game_over=False,
        ending=None,
        max_rounds=20,
    )

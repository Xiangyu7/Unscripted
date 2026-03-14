from schemas.game_state import (
    Character,
    Clue,
    Event,
    GameState,
    KnowledgeGraph,
    StoryTruth,
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
                "永远不直接否认，而是转移话题或反问。语气冷静到让人不舒服。"
                "偶尔会用'顾先生'而不是'顾言'来保持距离感。"
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
                "爱用反问句和玩笑来回避问题。被逼急了会提高音量但很快又装作没事。"
                "会主动把嫌疑引向林岚。"
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
                "连续追问，善用'所以你的意思是...'、'等一下，你刚才说...'来抓住别人的漏洞。"
                "会主动分享一些信息来换取更多信息。"
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
        Clue(
            id="study_scratches",
            text="书房门把手上有新鲜划痕",
            location="书房",
            discover_condition="search书房",
        ),
        Clue(
            id="wine_cellar_footprint",
            text="酒窖门口有一串新鲜脚印",
            location="酒窖",
            discover_condition="search酒窖",
        ),
        Clue(
            id="torn_letter",
            text="花园灌木丛中有一封被撕碎的信",
            location="花园",
            discover_condition="search花园",
        ),
        Clue(
            id="will_draft",
            text="书房抽屉里的遗嘱草稿有修改痕迹",
            location="书房",
            discover_condition="search书房 且 tension>=40",
        ),
        Clue(
            id="anonymous_tip",
            text="大厅垃圾桶里有一个写着'今晚注意遗产'的纸条",
            location="宴会厅",
            discover_condition="search宴会厅 或 observe仔细",
        ),
        Clue(
            id="cellar_sound",
            text="酒窖深处似乎有微弱的声响",
            location="酒窖",
            discover_condition="eavesdrop酒窖 或 search酒窖 且 tension>=60",
        ),
    ]

    knowledge = KnowledgeGraph(
        public_facts=[
            "顾家继承人顾言在晚宴中途失踪",
            "所有人暂时不能离开老宅",
            "今晚是顾家每年一度的家族晚宴",
        ],
        player_known=[],
        character_beliefs={},
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

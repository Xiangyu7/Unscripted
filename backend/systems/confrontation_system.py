"""
Confrontation System — Evidence-based NPC pressure.

Pure rules, zero LLM calls. When a player mentions a discovered clue
AND a character in the same action, trigger a confrontation with
pre-written pressure options.

Each scenario maps (clue_id, character_id) → list of pressure options,
each with an outcome_type (correct/wrong/risky).
"""

from typing import Dict, List, Optional, Tuple

from schemas.game_state import ConfrontationState, VoteOption


class ConfrontationOutcome:
    """Result of a confrontation choice."""
    def __init__(
        self,
        outcome_type: str,  # "correct" / "wrong" / "risky"
        result_text: str,
        trust_change: int = 0,
        suspicion_change: int = 0,
        tension_change: int = 0,
        reveals_clue: Optional[str] = None,
    ):
        self.outcome_type = outcome_type
        self.result_text = result_text
        self.trust_change = trust_change
        self.suspicion_change = suspicion_change
        self.tension_change = tension_change
        self.reveals_clue = reveals_clue


# ── Confrontation scenario definitions ──
# Key: (clue_id, character_id)
# Value: dict with "prompt", "options" list
#   Each option: {"id", "label", "kind": "pressure", "outcome": ConfrontationOutcome}

CONFRONTATION_SCENARIOS: Dict[Tuple[str, str], dict] = {
    # ═══ Will draft vs Zhou Mu ═══
    ("will_draft", "zhoumu"): {
        "prompt": "你拿出遗嘱草稿，直视周牧的眼睛——",
        "options": [
            {
                "id": "will_zhoumu_direct",
                "label": "你昨晚和顾言吵的就是这件事吧？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "周牧的表情僵住了。他猛地移开视线，声音发颤："
                        "「你怎么知道……是，我们吵了。但我没有——我不会——」"
                        "他的手开始不自觉地发抖。"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=8,
                ),
            },
            {
                "id": "will_zhoumu_money",
                "label": "你比谁都清楚钱的事。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "周牧的眼神变得危险起来。他压低了声音："
                        "「你以为你在跟谁说话？我和顾言的关系不是你能理解的。」"
                        "他虽然在逞强，但你注意到他的眼角在抽搐。"
                    ),
                    trust_change=-20,
                    suspicion_change=10,
                    tension_change=12,
                ),
            },
            {
                "id": "will_zhoumu_motive",
                "label": "你知道遗嘱要改——你有动机。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "周牧冷笑了一声：「动机？你知道多少人有动机？」"
                        "他反客为主：「你有没有想过，林岚才是最怕遗嘱改动的人？」"
                        "他的反击让你一时语塞。"
                    ),
                    trust_change=-15,
                    suspicion_change=-5,
                    tension_change=5,
                ),
            },
        ],
    },

    # ═══ Phone log vs Lin Lan ═══
    ("linlan_phone_log", "linlan"): {
        "prompt": "你翻出林岚的通话记录，语气平静——",
        "options": [
            {
                "id": "phone_linlan_still",
                "label": "顾言失踪后还给你发消息？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚的瞳孔微微收缩。她用了三秒钟让自己的表情恢复平静："
                        "「那些消息……是之前设定的定时发送。」"
                        "但她的声音比平时高了半个音调——她在撒谎。"
                    ),
                    trust_change=-10,
                    suspicion_change=20,
                    tension_change=10,
                ),
            },
            {
                "id": "phone_linlan_cover",
                "label": "你一直在替他隐瞒。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "林岚的嘴角勾起一丝苦笑：「隐瞒？你不了解我和他的关系。」"
                        "她顿了顿：「有些事情，不是隐瞒，是保护。」"
                        "这句话透露的信息远比她想说的多。"
                    ),
                    trust_change=-5,
                    suspicion_change=10,
                    tension_change=8,
                    reveals_clue="cellar_provisions",
                ),
            },
            {
                "id": "phone_linlan_where",
                "label": "他在哪？你知道的。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "林岚正色道：「如果我知道他在哪，为什么我比所有人都着急？」"
                        "她拿出自己的手机：「你看，我给他打了十七通电话。一个都没接。」"
                        "她的反应太自然了——也许这个方向是错的。"
                    ),
                    trust_change=-5,
                    suspicion_change=-10,
                    tension_change=3,
                ),
            },
        ],
    },

    # ═══ Torn letter vs Lin Lan ═══
    ("torn_letter", "linlan"): {
        "prompt": "你把拼凑起来的碎信放在桌上——",
        "options": [
            {
                "id": "letter_linlan_destroy",
                "label": "这封信是你撕的。为什么？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚看到信的一瞬间，手中的杯子微微倾斜。"
                        "「……那封信和这件事无关。」她的声音很轻。"
                        "但她伸手想把碎片拿走的动作出卖了她——这封信很重要。"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=8,
                ),
            },
            {
                "id": "letter_linlan_content",
                "label": "信的内容和遗嘱修改有关，对吧？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "林岚沉默了很长时间。最终她说："
                        "「……你比我想象的更接近真相。但真相不一定是你想要的。」"
                        "这句模棱两可的话，反而更让人不安。"
                    ),
                    trust_change=-5,
                    suspicion_change=12,
                    tension_change=10,
                ),
            },
            {
                "id": "letter_linlan_blame",
                "label": "你在销毁证据！",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "林岚冷冷地看着你：「证据？这是一封私人信件。」"
                        "「你没有任何权力指控我。」她转身离开，留你站在原地。"
                    ),
                    trust_change=-20,
                    suspicion_change=-5,
                    tension_change=5,
                ),
            },
        ],
    },

    # ═══ Wine cellar footprint vs Zhou Mu ═══
    ("wine_cellar_footprint", "zhoumu"): {
        "prompt": "你提到酒窖里的脚印，观察周牧的反应——",
        "options": [
            {
                "id": "foot_zhoumu_size",
                "label": "这个脚印的大小和你的鞋子很像。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "周牧下意识地把脚往后缩了一下。这个动作比任何言语都有说服力。"
                        "「……很多人的脚都差不多大小。」他勉强辩解。"
                        "但他的额头上已经冒出了冷汗。"
                    ),
                    trust_change=-10,
                    suspicion_change=18,
                    tension_change=8,
                ),
            },
            {
                "id": "foot_zhoumu_when",
                "label": "你昨晚去过酒窖，对吧？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "周牧犹豫了一下，然后出人意料地承认："
                        "「是，我去拿了瓶酒。但只待了两分钟。」"
                        "这个回答太快了——他显然排练过。但他为什么需要排练？"
                    ),
                    trust_change=-5,
                    suspicion_change=8,
                    tension_change=6,
                ),
            },
            {
                "id": "foot_zhoumu_drag",
                "label": "脚印很深——你在拖什么重东西？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "周牧的脸色瞬间变得苍白。他张了张嘴，什么也没说出来。"
                        "过了好几秒，他才哑声说：「你……你在胡说。」"
                        "但他的双手已经开始不受控制地颤抖。"
                    ),
                    trust_change=-15,
                    suspicion_change=20,
                    tension_change=12,
                ),
            },
        ],
    },

    # ═══ Anonymous tip vs Song Zhiwei ═══
    ("anonymous_tip", "songzhi"): {
        "prompt": "你拿出那张匿名纸条，看向宋知微——",
        "options": [
            {
                "id": "tip_songzhi_source",
                "label": "这张纸条是你提前放的吧？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "宋知微的职业笑容凝固了一秒。然后她恢复了镇定："
                        "「我是收到消息才来的——但不是通过这张纸条。」"
                        "她的回答巧妙地避开了核心问题。但你注意到她的笔记本合上了。"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=8,
                ),
            },
            {
                "id": "tip_songzhi_timing",
                "label": "一个记者恰好出现在失踪案现场？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "宋知微不慌不忙地推了推眼镜："
                        "「好记者永远在新闻发生之前到达。」"
                        "她的自信让你不确定这是坦荡还是伪装。"
                    ),
                    trust_change=-5,
                    suspicion_change=5,
                    tension_change=5,
                ),
            },
            {
                "id": "tip_songzhi_news",
                "label": "你需要这个独家新闻——不惜制造它。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "宋知微露出了被冒犯的表情：「我是记者，不是编剧。」"
                        "「我记录事实——不制造它们。」她的反驳有理有据。"
                        "也许你对她的怀疑太重了。"
                    ),
                    trust_change=-15,
                    suspicion_change=-8,
                    tension_change=3,
                ),
            },
        ],
    },

    # ═══ Study scratches vs Lin Lan ═══
    ("study_scratches", "linlan"): {
        "prompt": "你指着书房门上的划痕——",
        "options": [
            {
                "id": "scratch_linlan_drag",
                "label": "这些划痕像是有人被拖过门口。你知道些什么？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚的目光在划痕上停留了太久。"
                        "「……书房经常有人进出。这不说明什么。」"
                        "但她说完后不自觉地搓了搓右手手腕——那里有一道淡红色的印记。"
                    ),
                    trust_change=-8,
                    suspicion_change=12,
                    tension_change=6,
                ),
            },
            {
                "id": "scratch_linlan_key",
                "label": "你有书房的钥匙，对吗？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "「我是顾先生的秘书，当然有。」林岚的回答理所当然。"
                        "「但有钥匙不代表我做了什么。」她的逻辑无懈可击。"
                    ),
                    trust_change=-5,
                    suspicion_change=5,
                    tension_change=3,
                ),
            },
            {
                "id": "scratch_linlan_when",
                "label": "这些划痕是新的——就在昨晚留下的。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚轻轻吸了一口气。她没有反驳，只是说："
                        "「很多事情都发生在昨晚。不是所有事都和失踪有关。」"
                        "这个不太像否认的回答，反而印证了你的猜测。"
                    ),
                    trust_change=-8,
                    suspicion_change=12,
                    tension_change=7,
                ),
            },
        ],
    },

    # ═══ Cellar provisions vs Zhou Mu ═══
    ("cellar_provisions", "zhoumu"): {
        "prompt": "你提到酒窖里的食物和水——",
        "options": [
            {
                "id": "prov_zhoumu_care",
                "label": "你给他准备了食物。你不想他出事，但你害怕了。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "周牧的最后一道防线终于崩塌了。他的眼眶红了："
                        "「我没有……我没有想害他。我只是……推了一下……」"
                        "他双手捂住了脸，肩膀开始颤抖。"
                    ),
                    trust_change=-5,
                    suspicion_change=25,
                    tension_change=15,
                ),
            },
            {
                "id": "prov_zhoumu_who",
                "label": "这些东西不是给自己准备的——是给被困的人准备的。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "周牧沉默了很久。「也许……有人需要帮助。」"
                        "他的回答含糊不清，但已经不像之前那样坚决否认了。"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=10,
                ),
            },
            {
                "id": "prov_zhoumu_accuse",
                "label": "你把顾言关在酒窖里了！",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "周牧猛地站起来：「你凭什么这么说！」"
                        "他的愤怒看起来是真的——也许直接指控太早了。"
                        "「你没有证据！」他大声说，但所有人的目光都投向了他。"
                    ),
                    trust_change=-20,
                    suspicion_change=5,
                    tension_change=12,
                ),
            },
        ],
    },

    # ═══ Cellar sound vs Song Zhiwei ═══
    ("cellar_sound", "songzhi"): {
        "prompt": "你提到从酒窖深处传来的声音——",
        "options": [
            {
                "id": "sound_songzhi_know",
                "label": "你是不是早就知道顾言在酒窖里？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "宋知微的镇定出现了裂痕。她合上笔记本，深吸一口气："
                        "「我……我只是在做调查。但有些事情确实不该发生。」"
                        "她的话语暗示着更深层的真相。"
                    ),
                    trust_change=-10,
                    suspicion_change=18,
                    tension_change=10,
                ),
            },
            {
                "id": "sound_songzhi_record",
                "label": "你一直在记录——你到底知道多少？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "宋知微犹豫了一下，然后翻开笔记本给你看了一页："
                        "「我的笔记比你想象的多。但我不会把所有牌都摊开。」"
                        "你瞥到了几个关键词：「匿名信」「酒窖」「计划」。"
                    ),
                    trust_change=5,
                    suspicion_change=10,
                    tension_change=8,
                ),
            },
            {
                "id": "sound_songzhi_innocent",
                "label": "你听到声音了为什么不告诉大家？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "宋知微平静地回答：「我和你一样是刚刚才听到的。」"
                        "「不是所有事情都有阴谋论的解释。」她的语气很有说服力。"
                    ),
                    trust_change=-5,
                    suspicion_change=-5,
                    tension_change=3,
                ),
            },
        ],
    },

    # ═══ Will draft vs Lin Lan ═══
    ("will_draft", "linlan"): {
        "prompt": "你拿出遗嘱草稿上写着的批注——",
        "options": [
            {
                "id": "will_linlan_change",
                "label": "遗嘱要改了——你的利益会受损。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚的眼神锐利了起来。「你调查得很深。」"
                        "她深呼吸了一下：「是，如果遗嘱改了，基金会的管理权就不在我手里了。」"
                        "「但这不代表我会伤害顾言。有些东西比钱重要。」"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=10,
                ),
            },
            {
                "id": "will_linlan_note",
                "label": "「看看他们的反应」——顾言在试探你？",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "林岚的表情变得复杂。「顾言……他一直喜欢试探人。」"
                        "她低声说：「也许这一次，他试探过头了。」"
                        "这句话意味深长。"
                    ),
                    trust_change=0,
                    suspicion_change=10,
                    tension_change=8,
                ),
            },
            {
                "id": "will_linlan_destroy",
                "label": "你想销毁新遗嘱——所以你需要时间。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚猛地抬头看你。在那一瞬间，你看到了恐惧。"
                        "「……我没有销毁任何东西。」她的声音在发抖。"
                        "但她下意识地看了一眼自己的公文包——里面也许藏着什么。"
                    ),
                    trust_change=-15,
                    suspicion_change=20,
                    tension_change=12,
                ),
            },
        ],
    },

    # ═══ Staged evidence vs Song Zhiwei ═══
    ("staged_evidence", "songzhi"): {
        "prompt": "你指出书房的「犯罪现场」是伪造的——",
        "options": [
            {
                "id": "staged_songzhi_create",
                "label": "你需要一个完美的新闻素材——所以你帮忙布置了现场。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "宋知微的笔停在了半空中。"
                        "「你是第一个注意到这一点的人。」她慢慢说。"
                        "「但你弄错了一个细节——我没有布置现场。我只是……没有阻止它被布置。」"
                    ),
                    trust_change=-5,
                    suspicion_change=20,
                    tension_change=12,
                ),
            },
            {
                "id": "staged_songzhi_how",
                "label": "你怎么知道这是伪造的？除非你见过真正的现场。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "宋知微推了推眼镜，目光犀利："
                        "「我是调查记者——辨别真假是我的专业。但你说得对，"
                        "我来到这里之前就掌握了一些信息。」"
                    ),
                    trust_change=0,
                    suspicion_change=12,
                    tension_change=8,
                ),
            },
            {
                "id": "staged_songzhi_partner",
                "label": "你和顾言是同谋——这一切都是安排好的。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "宋知微露出了一个讽刺的微笑："
                        "「我和顾言？我们今晚之前从未见过面。」"
                        "她拿出了自己的记者证：「你可以查证。我是跟着线索来的——不是被邀请的。」"
                    ),
                    trust_change=-10,
                    suspicion_change=-10,
                    tension_change=3,
                ),
            },
        ],
    },

    # ═══ Cellar provisions vs Lin Lan ═══
    ("cellar_provisions", "linlan"): {
        "prompt": "你提到酒窖里有人准备的食物和水——",
        "options": [
            {
                "id": "prov_linlan_plan",
                "label": "这是你按照计划准备的——他在酒窖等你。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="correct",
                    result_text=(
                        "林岚闭上了眼睛，像是做出了一个艰难的决定。"
                        "「……我不会再撒谎了。」她的声音很轻。"
                        "「是，我知道他在哪。但事情不是你想的那样。」"
                    ),
                    trust_change=-5,
                    suspicion_change=25,
                    tension_change=15,
                ),
            },
            {
                "id": "prov_linlan_trapped",
                "label": "你把他锁在那里——然后又良心不安地送了食物。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="risky",
                    result_text=(
                        "林岚的嘴唇颤抖了一下。「你不了解整件事。」"
                        "「我做的每一件事……都是为了保护他。」"
                        "她的话让你更加困惑——但也更接近真相。"
                    ),
                    trust_change=-10,
                    suspicion_change=15,
                    tension_change=10,
                ),
            },
            {
                "id": "prov_linlan_deny",
                "label": "谁会给一个空酒窖准备食物？你在说谎。",
                "kind": "pressure",
                "outcome": ConfrontationOutcome(
                    outcome_type="wrong",
                    result_text=(
                        "林岚恢复了冷静：「也许那是顾言之前自己放的。」"
                        "「你知道他经常在酒窖待到很晚。」她的解释合情合理。"
                    ),
                    trust_change=-5,
                    suspicion_change=-5,
                    tension_change=3,
                ),
            },
        ],
    },
}


# ── Clue keyword mapping for trigger detection ──
CLUE_KEYWORDS: Dict[str, List[str]] = {
    "will_draft": ["遗嘱", "遗产", "草稿", "修改"],
    "linlan_phone_log": ["通话", "电话", "手机", "消息", "短信"],
    "torn_letter": ["碎信", "撕碎", "信件", "信"],
    "wine_cellar_footprint": ["脚印", "足迹", "痕迹"],
    "anonymous_tip": ["匿名", "纸条", "线报"],
    "study_scratches": ["划痕", "刮痕", "书房门"],
    "cellar_provisions": ["食物", "水", "物资", "准备"],
    "cellar_sound": ["声音", "呼吸", "酒窖深处"],
    "staged_evidence": ["伪造", "假现场", "布置"],
}

CHARACTER_KEYWORDS: Dict[str, List[str]] = {
    "linlan": ["林岚", "秘书"],
    "zhoumu": ["周牧", "老朋友"],
    "songzhi": ["宋知微", "记者"],
}


class ConfrontationSystem:
    """Pure-rule system for evidence confrontations."""

    def __init__(self):
        self._used_scenarios: Dict[str, set] = {}  # session_id → set of used (clue, char) keys

    def detect_confrontation(
        self,
        session_id: str,
        player_action: str,
        discovered_clue_ids: List[str],
        present_character_ids: List[str],
    ) -> Optional[ConfrontationState]:
        """
        Detect if a player action triggers a confrontation.
        Returns ConfrontationState if triggered, None otherwise.
        """
        action_lower = player_action.lower()
        used = self._used_scenarios.setdefault(session_id, set())

        # Find mentioned clue
        mentioned_clue_id = None
        for clue_id in discovered_clue_ids:
            keywords = CLUE_KEYWORDS.get(clue_id, [])
            if any(kw in action_lower for kw in keywords):
                mentioned_clue_id = clue_id
                break

        if not mentioned_clue_id:
            return None

        # Find mentioned character
        mentioned_char_id = None
        for char_id in present_character_ids:
            keywords = CHARACTER_KEYWORDS.get(char_id, [])
            if any(kw in action_lower for kw in keywords):
                mentioned_char_id = char_id
                break

        if not mentioned_char_id:
            return None

        # Check if scenario exists and hasn't been used
        key = (mentioned_clue_id, mentioned_char_id)
        if key in used:
            return None

        scenario = CONFRONTATION_SCENARIOS.get(key)
        if not scenario:
            return None

        # Mark as used
        used.add(key)

        # Find clue text
        options = [
            VoteOption(id=opt["id"], label=opt["label"], kind=opt["kind"])
            for opt in scenario["options"]
        ]

        return ConfrontationState(
            status="awaiting_player_choice",
            target_character_id=mentioned_char_id,
            target_character_name=CHARACTER_KEYWORDS.get(mentioned_char_id, [mentioned_char_id])[0],
            evidence_clue_id=mentioned_clue_id,
            evidence_text="",  # Will be filled by turn_engine from clue text
            prompt=scenario["prompt"],
            options=options,
        )

    def resolve(
        self,
        session_id: str,
        confrontation_state: ConfrontationState,
        choice_id: str,
    ) -> Optional[ConfrontationOutcome]:
        """Resolve a confrontation choice. Returns the outcome."""
        key = (confrontation_state.evidence_clue_id, confrontation_state.target_character_id)
        scenario = CONFRONTATION_SCENARIOS.get(key)
        if not scenario:
            return None

        for opt in scenario["options"]:
            if opt["id"] == choice_id:
                return opt["outcome"]

        return None

import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { MessageSquare, Drama, Search, AlertTriangle, Eye, Users, Sparkles } from "lucide-react";

const initialState = {
  storyTitle: "豪门晚宴失踪案",
  scene: "顾家老宅·宴会厅",
  round: 1,
  tension: 22,
  phase: "自由试探",
  cluesFound: [],
  publicFacts: ["顾家继承人顾言在晚宴开始后失踪。", "所有宾客都被要求留在宅内。"],
  hiddenTruth: "真正拿走遗嘱副本的人是林岚，她不是凶手，但她在掩盖自己与顾言的秘密交易。",
  ledger: [
    { round: 0, text: "晚宴开始，顾言失踪，众人被困在老宅中。" }
  ],
  characters: [
    {
      id: "linlan",
      name: "林岚",
      role: "顾家秘书",
      style: "冷静、克制、说话很稳",
      goal: "避免遗嘱副本曝光",
      secret: "她拿走了遗嘱副本，并与顾言私下有交易。",
      suspicion: 48,
      trust: 35,
      knowledge: ["知道书房曾被人进入", "知道遗嘱副本被拿走"],
    },
    {
      id: "zhoumu",
      name: "周牧",
      role: "顾言发小",
      style: "表面轻松，实际防备心强",
      goal: "把嫌疑引到林岚身上",
      secret: "他昨晚和顾言大吵一架。",
      suspicion: 54,
      trust: 42,
      knowledge: ["知道顾言昨晚情绪异常", "知道有人去过酒窖"],
    },
    {
      id: "songzhi",
      name: "宋知微",
      role: "记者",
      style: "敏锐、咄咄逼人、擅长追问",
      goal: "拿到独家新闻",
      secret: "她提前收到过匿名爆料，知道顾家遗产有问题。",
      suspicion: 39,
      trust: 46,
      knowledge: ["知道顾家内部有人争遗产", "知道今晚会出事但不知道细节"],
    },
  ],
};

const quickActions = [
  "我想先观察所有人的表情和站位",
  "我去问林岚，顾言失踪前最后见过谁",
  "我诈周牧，说我已经知道昨晚发生了什么",
  "我要求搜查书房",
  "我公开指出这件事和遗嘱有关",
];

function clamp(num, min, max) {
  return Math.max(min, Math.min(max, num));
}

function pickResponses(input, state) {
  const text = input.toLowerCase();
  const mentionsStudy = /书房|遗嘱|study/.test(text);
  const mentionsBluff = /诈|知道|隐瞒|昨晚|真相/.test(text);
  const mentionsObserve = /观察|表情|站位|看|偷听/.test(text);
  const mentionsSearch = /搜|调查|检查|查看|search/.test(text);
  const mentionsAccuse = /指控|就是你|嫌疑|凶手|公开/.test(text);

  const updates = {
    clues: [],
    tensionDelta: 0,
    phase: state.phase,
    ledger: [],
    characters: state.characters.map((c) => ({ ...c })),
    directorNote: "",
    npcReplies: [],
  };

  if (mentionsObserve) {
    updates.clues.push("你注意到林岚在听到“遗嘱”两个字时明显停顿。", "周牧一直避免靠近书房方向。");
    updates.tensionDelta += 4;
    updates.directorNote = "导演判断：玩家选择了低冲突侦查动作，系统投放了行为线索而非硬证据。";
  }

  if (mentionsStudy || mentionsSearch) {
    if (!state.cluesFound.includes("书房门把上有新划痕。")) {
      updates.clues.push("书房门把上有新划痕。");
    }
    updates.tensionDelta += 8;
    updates.phase = "搜证推进";
    updates.ledger.push("玩家将焦点推向书房，场景进入搜证推进。");
  }

  if (mentionsBluff) {
    updates.characters = updates.characters.map((c) => {
      if (c.id === "zhoumu") return { ...c, suspicion: clamp(c.suspicion + 8, 0, 100), trust: clamp(c.trust - 6, 0, 100) };
      if (c.id === "linlan") return { ...c, suspicion: clamp(c.suspicion + 6, 0, 100), trust: clamp(c.trust - 4, 0, 100) };
      return c;
    });
    updates.tensionDelta += 10;
    updates.directorNote = "导演判断：诈话术触发了高张力回应，优先提升人物失衡与相互猜疑。";
  }

  if (mentionsAccuse) {
    updates.phase = "公开对峙";
    updates.tensionDelta += 14;
    updates.ledger.push("玩家主动发动公开指控，晚宴气氛迅速恶化。");
    updates.directorNote = "导演判断：进入公开对峙阶段，后续更容易触发秘密外泄。";
  }

  const clueCountAfter = new Set([...state.cluesFound, ...updates.clues]).size;
  if (clueCountAfter >= 3 && state.phase !== "公开对峙" && !mentionsAccuse) {
    updates.phase = "临界对峙";
    updates.ledger.push("关键线索积累到一定程度，角色开始明显自保。");
  }

  const replies = updates.characters.map((c) => {
    if (c.id === "linlan") {
      if (mentionsStudy || mentionsSearch) return `${c.name}微微皱眉：“书房没什么好查的，顾先生失踪前并未留下正式说明。”`;
      if (mentionsBluff) return `${c.name}语气更冷：“你如果知道什么，就直接说，不要试探我。”`;
      if (mentionsAccuse) return `${c.name}盯着你：“你在没有证据的情况下公开引导舆论，这对谁有利？”`;
      return `${c.name}平静地看着你：“现在最重要的是先把时间线理清。”`;
    }
    if (c.id === "zhoumu") {
      if (mentionsBluff) return `${c.name}笑了一下，但手指明显收紧：“昨晚？昨晚每个人都不怎么干净吧。”`;
      if (mentionsSearch || mentionsStudy) return `${c.name}立刻接话：“查书房可以，但别只盯着一个地方。”`;
      if (mentionsAccuse) return `${c.name}向后靠了靠：“终于有人愿意把话说开了。”`;
      return `${c.name}耸肩：“你问我不如先问顾家自己人。”`;
    }
    if (c.id === "songzhi") {
      if (mentionsAccuse) return `${c.name}几乎立刻追问：“所以你是怀疑有人借失踪案转移遗产问题？”`;
      if (mentionsObserve) return `${c.name}注意到了你的视线：“你也发现不对劲了，对吗？”`;
      if (mentionsSearch || mentionsStudy) return `${c.name}掏出手机记下：“书房、遗嘱、失踪，这三个词应该有关联。”`;
      return `${c.name}眯起眼看你：“你不像普通宾客，你是在查案，还是在布局？”`;
    }
    return `${c.name}沉默地看着你。`;
  });

  updates.npcReplies = replies;

  if (!updates.directorNote) {
    updates.directorNote = clueCountAfter >= 2
      ? "导演判断：玩家已逐步逼近核心矛盾，系统维持悬疑但暂不直接放出真相。"
      : "导演判断：当前仍处于铺垫期，重点增加人物反应差异与轻线索。";
  }

  if (updates.tensionDelta >= 12) {
    updates.ledger.push("大厅中的谈话声戛然而止，所有人都意识到局势变得危险。");
  }

  return updates;
}

export default function AIMultiAgentMVP() {
  const [state, setState] = useState(initialState);
  const [input, setInput] = useState("");
  const [feed, setFeed] = useState([
    { type: "system", text: "你是主角。今晚，顾家继承人顾言在晚宴中途失踪。你可以自由观察、试探、搜证、指控。" },
    { type: "director", text: "导演提示：当前阶段适合先摸清人物关系，再决定是否公开冲突。" },
  ]);

  const dangerLevel = useMemo(() => {
    if (state.tension < 35) return "低";
    if (state.tension < 65) return "中";
    return "高";
  }, [state.tension]);

  function submitAction(actionText) {
    const trimmed = actionText.trim();
    if (!trimmed) return;

    const updates = pickResponses(trimmed, state);
    const newClues = Array.from(new Set([...state.cluesFound, ...updates.clues]));
    const newTension = clamp(state.tension + updates.tensionDelta, 0, 100);

    setState((prev) => ({
      ...prev,
      round: prev.round + 1,
      phase: updates.phase,
      tension: newTension,
      cluesFound: newClues,
      ledger: [
        ...prev.ledger,
        { round: prev.round + 1, text: `玩家行动：${trimmed}` },
        ...updates.ledger.map((text, idx) => ({ round: prev.round + 1, text: `${idx === 0 ? "系统事件" : "补充事件"}：${text}` })),
      ],
      characters: updates.characters,
    }));

    const newFeed = [
      ...feed,
      { type: "player", text: trimmed },
      { type: "director", text: updates.directorNote },
      ...updates.clues.map((c) => ({ type: "clue", text: c })),
      ...updates.npcReplies.map((r) => ({ type: "npc", text: r })),
    ];

    if (newTension >= 70) {
      newFeed.push({
        type: "system",
        text: "系统提示：紧张度已很高。下一轮更容易触发秘密曝光、公开对峙或关键证物掉落。"
      });
    }

    setFeed(newFeed);
    setInput("");
  }

  function resetGame() {
    setState(initialState);
    setFeed([
      { type: "system", text: "你是主角。今晚，顾家继承人顾言在晚宴中途失踪。你可以自由观察、试探、搜证、指控。" },
      { type: "director", text: "导演提示：当前阶段适合先摸清人物关系，再决定是否公开冲突。" },
    ]);
    setInput("");
  }

  const typeStyle = {
    system: "bg-slate-100 text-slate-800 border-slate-200",
    director: "bg-violet-50 text-violet-700 border-violet-200",
    player: "bg-blue-50 text-blue-700 border-blue-200",
    npc: "bg-white text-slate-800 border-slate-200",
    clue: "bg-amber-50 text-amber-700 border-amber-200",
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]"
        >
          <Card className="rounded-2xl shadow-sm border-0">
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 text-slate-500 text-sm">
                    <Drama className="h-4 w-4" />
                    多 Agent 互动叙事 MVP
                  </div>
                  <CardTitle className="mt-2 text-3xl font-semibold text-slate-900">
                    {state.storyTitle}
                  </CardTitle>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">场景：{state.scene}</Badge>
                    <Badge variant="secondary">阶段：{state.phase}</Badge>
                    <Badge variant="secondary">回合：{state.round}</Badge>
                  </div>
                </div>
                <Button variant="outline" className="rounded-xl" onClick={resetGame}>
                  重置故事
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-3">
                <StatCard icon={<AlertTriangle className="h-4 w-4" />} label="紧张度" value={`${state.tension}/100`} sub={`危险等级：${dangerLevel}`} />
                <StatCard icon={<Search className="h-4 w-4" />} label="已发现线索" value={`${state.cluesFound.length}`} sub="线索越多，越容易触发对峙" />
                <StatCard icon={<Users className="h-4 w-4" />} label="核心角色" value={`${state.characters.length}`} sub="每个角色都有自己的目标与秘密" />
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-2xl shadow-sm border-0">
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Sparkles className="h-5 w-5" />
                MVP 验证点
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-600">
              <div>1. 玩家可以自由输入动作，而不是点选固定选项。</div>
              <div>2. 导演层根据动作决定节奏、冲突和线索投放。</div>
              <div>3. 角色各自回应，同一动作会引发不同立场反应。</div>
              <div>4. 世界账本持续记录事件，线索和紧张度会累积。</div>
            </CardContent>
          </Card>
        </motion.div>

        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr_0.8fr]">
          <Card className="rounded-2xl shadow-sm border-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <MessageSquare className="h-5 w-5" />
                剧情演出区
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[560px] pr-3">
                <div className="space-y-3">
                  {feed.map((item, idx) => (
                    <motion.div
                      key={`${item.type}-${idx}`}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${typeStyle[item.type]}`}
                    >
                      <div className="mb-1 text-xs font-medium uppercase tracking-wide opacity-70">
                        {item.type === "system" && "系统"}
                        {item.type === "director" && "导演"}
                        {item.type === "player" && "主角"}
                        {item.type === "npc" && "角色"}
                        {item.type === "clue" && "线索"}
                      </div>
                      <div>{item.text}</div>
                    </motion.div>
                  ))}
                </div>
              </ScrollArea>

              <Separator className="my-4" />

              <div className="space-y-3">
                <div className="flex gap-2">
                  <Input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitAction(input);
                    }}
                    placeholder="例如：我要求搜查书房，并观察林岚的反应"
                    className="rounded-xl bg-white"
                  />
                  <Button className="rounded-xl" onClick={() => submitAction(input)}>
                    执行动作
                  </Button>
                </div>

                <div className="flex flex-wrap gap-2">
                  {quickActions.map((action) => (
                    <Button
                      key={action}
                      variant="outline"
                      className="rounded-full text-xs"
                      onClick={() => submitAction(action)}
                    >
                      {action}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="rounded-2xl shadow-sm border-0">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Users className="h-5 w-5" />
                角色状态
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {state.characters.map((char) => (
                <div key={char.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-slate-900">{char.name}</div>
                      <div className="text-sm text-slate-500">{char.role}</div>
                    </div>
                    <Badge variant="outline">{char.style}</Badge>
                  </div>
                  <div className="mt-3 space-y-2 text-sm text-slate-600">
                    <div>目标：{char.goal}</div>
                    <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
                      <span>嫌疑值</span>
                      <span className="font-medium">{char.suspicion}</span>
                    </div>
                    <div className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2">
                      <span>对主角信任</span>
                      <span className="font-medium">{char.trust}</span>
                    </div>
                    <div>
                      <div className="mb-2 text-slate-500">已知信息</div>
                      <div className="flex flex-wrap gap-2">
                        {char.knowledge.map((k) => (
                          <Badge key={k} variant="secondary" className="rounded-full">{k}</Badge>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card className="rounded-2xl shadow-sm border-0">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <Eye className="h-5 w-5" />
                  玩家已发现线索
                </CardTitle>
              </CardHeader>
              <CardContent>
                {state.cluesFound.length === 0 ? (
                  <div className="text-sm text-slate-500">暂无硬线索，先通过观察和试探打开局面。</div>
                ) : (
                  <div className="space-y-2">
                    {state.cluesFound.map((clue) => (
                      <div key={clue} className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-700">
                        {clue}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="rounded-2xl shadow-sm border-0">
              <CardHeader>
                <CardTitle className="text-lg">世界账本（简化）</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[220px] pr-3">
                  <div className="space-y-2 text-sm text-slate-600">
                    {state.ledger.map((entry, idx) => (
                      <div key={`${entry.round}-${idx}`} className="rounded-xl bg-slate-50 px-3 py-2">
                        <span className="mr-2 font-medium text-slate-800">R{entry.round}</span>
                        {entry.text}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            <Card className="rounded-2xl shadow-sm border-0 border-dashed border-slate-300">
              <CardHeader>
                <CardTitle className="text-lg">下一步该补什么</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-slate-600">
                <div>• 把当前规则判断替换成真实 LLM 导演 + 角色 Agent</div>
                <div>• 把世界账本迁移到后端数据库</div>
                <div>• 增加私聊、偷听、搜证地图、公开投票</div>
                <div>• 增加自动化测试，检查人设崩坏和线索穿帮</div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub }) {
  return (
    <div className="rounded-2xl bg-slate-100 p-4">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-3 text-2xl font-semibold text-slate-900">{value}</div>
      <div className="mt-1 text-sm text-slate-500">{sub}</div>
    </div>
  );
}

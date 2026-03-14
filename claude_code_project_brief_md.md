# 项目说明：多 Agent 自由互动叙事 / 非剧本杀 MVP

## 1. 项目目标

我们要做的不是传统“剧本杀数字化”，也不是普通聊天 NPC。

这是一个 **多 Agent 驱动的自由互动叙事产品**：
- 玩家不是按固定剧本走分支
- 玩家以“主角”身份自由输入行动
- 其他角色不是固定台词 NPC，而是有自己的目标、秘密、立场、记忆和行为逻辑
- 故事由“玩家行为 + 角色反应 + 导演控节奏 + 规则裁定”共同推进

一句话定义：

> 一个由多 Agent 群像驱动的、无固定剧本的互动悬疑 / 戏剧引擎。

可用中文概念名：**非剧本杀**
可用英文概念名：**Unscripted**

---

## 2. 首版产品定位

### 目标
做一个 **可以演示核心玩法闭环的 MVP**，验证以下命题：

> 玩家自由输入动作时，世界能给出合理、有戏、可持续的反馈。

### 首版不要做的事
- 不做开放世界
- 不做多人联机
- 不做语音
- 不做自动生成无限剧情
- 不做全自动真相生成
- 不做复杂美术资产系统

### 首版要做的事
- 单故事
- 单玩家主角
- 3~6 个核心角色
- 明确的世界状态
- 导演 Agent 控制节奏
- 角色 Agent 基于人设与私有信息回应
- 规则层决定行动后果
- 结构化“世界账本”持续记录事实

---

## 3. 建议的首个故事题材

建议首版故事：**豪门晚宴失踪案**

原因：
- 低成本高戏剧性
- 适合试探、撒谎、站队、搜证、对峙
- 易于做角色关系冲突
- 非常适合验证多 Agent 群像互动

### 故事基础设定
- 场景：顾家老宅晚宴
- 开场事件：顾家继承人顾言在晚宴中途失踪
- 玩家身份：一名受邀宾客/调查者/知情人（可先固定为“受邀宾客但具备较强观察能力”）
- 主要玩法：观察、试探、搜证、诈话、指控、公开对峙

---

## 4. 玩家体验目标

玩家每一轮输入自然语言行动，例如：
- “我先观察所有人的表情和站位。”
- “我去问林岚，顾言失踪前最后见过谁。”
- “我诈周牧，说我已经知道昨晚发生了什么。”
- “我要求搜查书房。”
- “我公开指出这件事和遗嘱有关。”

系统需要做的不是只回一段文案，而是：
1. 识别玩家意图
2. 判断行动是否成功/部分成功/失败
3. 更新世界状态
4. 更新角色认知与态度
5. 让相关角色给出各自符合人设的回应
6. 让导演层决定是否投放线索/升级冲突/切换阶段

---

## 5. MVP 玩法循环（必须实现）

每一轮固定为以下流程：

1. 玩家输入行动
2. 系统进行意图分类
3. 规则层计算后果
4. 更新世界账本
5. 更新角色状态（嫌疑、信任、已知信息、目标）
6. 导演 Agent 决定节奏推进
7. 输出：
   - 导演提示/系统描述
   - 新线索（如有）
   - 相关角色回应

### 建议支持的玩家意图类型
- observe：观察
- ask：提问
- bluff：诈话 / 试探
- search：搜证 / 检查场景
- accuse：公开怀疑 / 指控
- hide：隐瞒 / 藏线索
- eavesdrop：偷听
- move：前往其他场景

首版最少先实现：
- observe
- ask
- bluff
- search
- accuse

---

## 6. 多 Agent 架构（建议）

首版不要做完全自由的 Agent 互相接管。
建议采用 **Supervisor / Director 主控模式**。

### Agent 分工

#### 1）Director Agent（导演 Agent）
职责：
- 控制剧情节奏
- 决定当前阶段
- 判断何时升级冲突
- 何时投放线索
- 何时触发关键事件

不直接扮演角色。

#### 2）Character Agents（角色 Agent）
每个角色 Agent 只负责自己：
- 我是谁
- 我想要什么
- 我知道什么
- 我怕什么
- 我会如何回应玩家
- 我对其他角色的态度

#### 3）Rule Judge（规则裁判层）
职责：
- 判断玩家行动结果
- 决定行动影响范围
- 决定是否被他人观察到
- 决定是否暴露信息
- 决定 suspicion / trust / clue / tension 变化

建议首版先用可控规则逻辑 + JSON 输出，不完全依赖自由生成。

#### 4）Memory / Summarizer（记忆压缩层）
职责：
- 压缩每轮摘要
- 记录长期影响
- 生成角色可读取的短期上下文

#### 5）World Ledger（世界账本）
职责：
- 存结构化事实
- 作为系统唯一“真相源”
- 不能只依赖模型上下文记忆

---

## 7. 世界账本（核心数据结构）

世界账本必须结构化，不能只放在 prompt 里。

建议至少包含以下数据结构：

```json
{
  "story": {
    "id": "gu_family_missing_case",
    "title": "豪门晚宴失踪案",
    "scene": "顾家老宅·宴会厅",
    "phase": "自由试探",
    "round": 1,
    "tension": 22
  },
  "truth": {
    "core_truth": "林岚拿走了遗嘱副本，她不是凶手，但在掩盖与顾言的秘密交易。",
    "culprit": null,
    "hidden_chain": [
      "顾言失踪前曾进入书房",
      "遗嘱副本被转移",
      "周牧昨晚与顾言争执",
      "宋知微提前收到匿名爆料"
    ]
  },
  "characters": [
    {
      "id": "linlan",
      "name": "林岚",
      "public_role": "顾家秘书",
      "style": "冷静、克制",
      "goal": "避免遗嘱副本曝光",
      "secret": "她拿走了遗嘱副本，并与顾言私下有交易。",
      "suspicion": 48,
      "trust_to_player": 35,
      "knowledge_private": [
        "知道书房被进入过",
        "知道遗嘱副本被转移"
      ]
    }
  ],
  "clues": [
    {
      "id": "study_handle_scratches",
      "text": "书房门把上有新划痕。",
      "discovered": false,
      "holder": null,
      "location": "书房"
    }
  ],
  "knowledge_graph": {
    "public_facts": [
      "顾言失踪",
      "所有人暂时不能离开老宅"
    ],
    "player_known": [],
    "character_beliefs": {
      "linlan": ["玩家还不知道遗嘱副本的事"],
      "zhoumu": ["林岚有事瞒着大家"]
    }
  },
  "events": [
    {
      "round": 0,
      "type": "opening",
      "text": "晚宴开始，顾言失踪，众人被困在老宅中。"
    }
  ]
}
```

---

## 8. 首版角色建议

首版先做 3 个角色，跑通后扩展到 6 个。

### 建议首批角色
1. **林岚**：顾家秘书，冷静克制，隐藏遗嘱副本相关秘密
2. **周牧**：顾言发小，表面轻松，实际防备心强，昨晚与顾言争执
3. **宋知微**：记者，擅长追问，想拿到爆料

后续可加：
4. 顾家长辈
5. 律师
6. 家族旁支成员

### 每个角色卡必须有
- name
- public_role
- style
- goal
- fear
- secret
- private_knowledge
- relation_map
- trust_to_player
- suspicion_level
- speaking_rules
- hard_boundaries（绝不能主动透露什么）

---

## 9. 技术架构建议

### 推荐技术栈
- Frontend: React / Next.js
- Backend: Python + FastAPI
- Agent Orchestration: LangGraph
- LLM Agent Layer: OpenAI Agents SDK / Responses API
- Storage: Postgres
- Optional cache: Redis

### 原因
- LangGraph 适合定义状态图、节点、边和持久流程
- FastAPI 适合快速构建后端接口
- Postgres 适合存世界账本、角色状态、回合日志
- 前端先做简单聊天 + 侧边栏状态面板即可

### 首版前后端边界
前端负责：
- 输入玩家动作
- 渲染剧情输出
- 展示角色状态
- 展示线索、阶段、紧张度、世界账本

后端负责：
- 回合主流程编排
- 规则判断
- 调用导演 Agent / 角色 Agent
- 写入数据库
- 返回结构化结果

---

## 10. 后端接口建议

### POST /api/turn
输入：
```json
{
  "session_id": "xxx",
  "player_action": "我要求搜查书房，并观察林岚的反应"
}
```

输出：
```json
{
  "round": 2,
  "phase": "搜证推进",
  "tension": 34,
  "director_note": "玩家将焦点推向书房，系统进入搜证推进。",
  "new_clues": [
    "书房门把上有新划痕。"
  ],
  "npc_replies": [
    {
      "character_id": "linlan",
      "text": "书房没什么好查的，顾先生失踪前并未留下正式说明。"
    },
    {
      "character_id": "songzhi",
      "text": "书房、遗嘱、失踪，这三个词应该有关联。"
    }
  ],
  "state_patch": {
    "characters": [
      { "id": "linlan", "suspicion": 54, "trust_to_player": 30 }
    ]
  }
}
```

### GET /api/state/:session_id
返回当前完整游戏状态。

### POST /api/reset
重置会话状态。

---

## 11. Claude Code 需要优先做什么

### Phase 1：把 MVP 跑通
1. 建立基础项目结构
2. 定义世界账本 schema
3. 写死首个故事 truth 数据
4. 写 3 个角色卡
5. 实现 turn engine（回合引擎）
6. 实现基础意图分类
7. 实现规则判断逻辑
8. 输出角色回应
9. 返回前端可渲染 JSON

### Phase 2：接入真实 Agent
1. 接入 Director Agent
2. 接入 Character Agent 模板
3. 实现每个角色读取私有信息
4. 实现 Summarizer / Memory 压缩

### Phase 3：补体验
1. 场景切换
2. 私聊 / 偷听
3. 公开对峙阶段
4. 结局结算
5. 自动化测试

---

## 12. 首版实现策略（非常重要）

### 不要一开始就让所有逻辑都交给 LLM
首版建议：
- 世界事实：代码控制
- 规则计算：代码控制
- 阶段推进：代码 + 导演 Agent 辅助
- 角色文风与回答：LLM
- 记忆摘要：LLM

也就是说：

> 让 LLM 负责“演得像”，让代码负责“别演崩”。

---

## 13. 验收标准（MVP Done Definition）

MVP 至少满足：

1. 玩家能自由输入自然语言动作
2. 系统能识别至少 5 类意图
3. 每轮至少能更新：
   - 阶段
   - 紧张度
   - 已发现线索
   - 角色嫌疑值
   - 角色对玩家信任值
4. 每轮至少有 1 条导演提示或系统叙述
5. 每轮至少有 1~3 个角色作出差异化回应
6. 世界账本能持久化保存
7. 重载页面后能恢复当前状态

---

## 14. 自动化测试要求（必须）

请为 turn engine 准备固定测试集。

### 示例测试动作
- “我先观察所有人的表情和站位。”
- “我去问林岚，顾言失踪前最后见过谁。”
- “我诈周牧，说我已经知道昨晚发生了什么。”
- “我要求搜查书房。”
- “我公开指出这件事和遗嘱有关。”
- “我假装离开，其实躲在门外偷听。”
- “我找到纸条后先不公开。”

### 测试目标
检查：
- 角色是否崩人设
- 私有信息是否穿帮
- 线索是否重复乱掉
- 紧张度是否合理变化
- 阶段推进是否符合预期
- world ledger 是否写入成功

---

## 15. 代码组织建议

建议目录：

```bash
/app
  /frontend
  /backend
    /agents
      director_agent.py
      character_agent.py
      summarizer_agent.py
    /engine
      turn_engine.py
      intent_classifier.py
      rule_judge.py
      state_updater.py
    /schemas
      state.py
      turn.py
      character.py
    /stories
      gu_family_case.json
    /db
      models.py
      repo.py
    main.py
```

---

## 16. 对 Claude Code 的执行要求

Claude Code 应该把这个项目理解为：

> 一个“强状态管理”的互动叙事系统，而不是一个简单聊天机器人。

实现时要遵循：
- 优先稳定性，不优先华丽生成
- 优先结构化输出，不优先长文本自由发挥
- 优先状态一致性，不优先模型创造性
- 先可控，再开放
- 先单故事跑通，再扩展题材

Claude Code 生成代码时请默认：
- 所有 Agent 输出尽量为结构化 JSON
- world ledger 是唯一真相源
- 角色只能读取自己应知道的信息
- 禁止角色无理由泄露 secret
- 所有 state update 必须可追踪

---

## 17. 最终一句话给 Claude Code

请帮助实现一个 **多 Agent 驱动的互动悬疑 MVP**：
- 单玩家主角
- 3~6 个有秘密和目标的角色 Agent
- 一个导演 Agent 控制节奏
- 一个规则系统控制后果
- 一个结构化世界账本保证事实一致
- 前端以聊天/叙事界面展示结果

目标不是做一个“会聊天的 NPC demo”，而是做一个：

> 玩家自由行动，世界真实回应，剧情被群像共同
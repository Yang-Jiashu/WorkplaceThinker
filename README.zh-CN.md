# WorkplaceThinker

[English](README.md) | [中文](README.zh-CN.md)

**把混乱的职场上下文粘进去，得到有证据的人际关系网、工作内容网、风险图和人物档案。**

WorkplaceThinker 是基于 DocThinker agentic memory 能力做出来的职场上下文洞察应用。它面向刚入职场、刚进新团队、或者正在处理复杂协作关系的人：你可以直接粘贴聊天记录、会议纪要、组织架构、项目背景或上传文本，系统会把这些材料整理成几层可审计的职场图谱：

- **人际关系网**：谁汇报给谁，谁支持、阻塞、承诺、改口或卷入风险；
- **工作内容网**：项目、任务、决策、审批、交付物、截止时间、验收标准；
- **人物档案库**：类似“天眼查式”的人物入口，先看所有人，再点进单个人看证据和历史；
- **风险与隐藏假设图**：把风险信号和隐藏假设作为 graph 节点展示；
- **知识注入层**：内置 RACI、决策记录、边界设定、推断阶梯、互联网职场黑话语义和组织政治 / 权力动态。

它不是读心术，也不是教人搞办公室政治。它会把观察事实、行为信号、风险和假设分开，并尽量给每个判断挂上证据 id。它的目标是帮用户更清醒、更稳妥地确认问题，而不是让用户更焦虑。

## 为什么需要它

新人最难的往往不是做事，而是看不懂局势：

- 谁是真正 owner？
- 这是正式决策，还是私下口头安排？
- 对方是不是改口了？
- 我是不是在没有授权的情况下承担责任？
- 哪些话应该写下来确认？
- “对齐”“闭环”“owner”“push”“卡点”这些话在当前语境里到底意味着什么？

WorkplaceThinker 会把模糊担心拆成结构化链路：

```text
混乱职场上下文
  -> 稳定 evidence ids
  -> 人物 + 组织架构抽取
  -> 工作对象抽取
  -> 关系、风险、黑话语义信号
  -> 知识框架注入
  -> 图谱 + 人物档案 + 确认问题 + 用户控制
  -> 用户反馈与记忆控制
```

## 核心能力

### 一框输入

主路径只需要粘贴一坨信息，不需要用户先整理 JSON。

### 人际关系网

系统会识别人、正式汇报关系、合作、支持、阻塞/质疑、承诺/交付、风险关联等。每条关系都会尽量保留触发它的证据 id。

### 工作内容网

现在系统会显式建模工作内容，而不只是看人际关系。支持的工作对象包括：

- `project`：项目 / 事项
- `task`：任务
- `decision`：决策
- `approval`：审批 / 授权
- `deliverable`：交付物
- `deadline`：截止时间
- `acceptance`：验收标准

人物和工作对象之间也会有边，比如 owner、审批、验收、时间要求、依赖等。

### 人物档案库

Demo 里有一个独立的 **人物档案** tab，更像“查人”的入口：

1. 打开人物档案；
2. 先看到当前 case 里识别出的所有人；
3. 每个人有关系数、风险数、工作关联数、过往记录数；
4. 点进某个人，可以看 TA 的相关关系、风险信号、行为观察、工作关联、互联网语义、证据片段和过往分析。

人物档案是证据化互动记录，不是人格定性。系统不会直接说“这个人性格如何”，只会说“在已有证据中观察到哪些互动模式”。

### 知识注入

`workplace_thinker/knowledge_injection.py` 里放了一层显式职场知识，不让系统只靠关键词或自由发挥。

目前内置的框架包括：

- **RACI 责任澄清**：区分负责、批准、咨询、知会；
- **决策记录**：私下决策、流程例外和口径变化需要最小可审计记录；
- **边界设定**：把压力转成范围、资源、优先级和取舍；
- **推断阶梯**：区分观察事实、解释、假设和行动。

### 互联网职场黑话语义

系统会识别常见互联网职场表达，并把它们映射到真实协作含义：

- 对齐 / 拉齐 / align / 口径一致
- 闭环 / close the loop
- owner / 主责 / 牵头 / 兜底
- 推进 / push / 盯一下
- 拆解 / 颗粒度
- 排期 / 上线 / 提测 / 联调
- 卡点 / blocker / 阻塞
- 复盘 / 沉淀
- 抓手 / 赋能 / 打法 / 链路

这些会作为 `jargon_signals` 返回，包含命中的原词、归一化含义、映射到的职场概念、解释和安全确认问题。

### 组织政治 / 权力动态

系统也会识别一些可证据追溯的组织动态信号，例如：

- 信息门控；
- 影子决策链；
- 背书 / 保护伞；
- 功劳上收；
- 责任下放 / 甩锅；
- 资源控制；
- 联盟 / 派系信号；
- 绩效压力转嫁。

这些会作为 `org_dynamics_signals` 返回。它们是**信号，不是事实**。系统会用它们来提示用户确认授权、信息流、资源、信用和责任边界，但不会输出操纵、站队或攻击建议。

### 风险与隐藏假设

当前风险分类包括：

- 责任边界不清
- 信息不对称
- 流程绕过
- 功劳 / 责任归属风险
- 权力压力
- 立场反复

隐藏假设会作为 graph 节点出现，并且必须标记：

```text
status = hypothesis_not_fact
```

## 快速运行

启动独立 API：

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

Demo UI 有两个主要视图：

- **分析总览**：关系图、风险、隐藏假设、工作内容网、知识框架、建议确认问题；
- **人物档案**：先看所有人物，再点进单个人档案。

如果你直接打开 `apps/workplace_radar.html`，页面会使用内置 fallback 示例。要分析真实输入，需要先启动上面的 API。

## API 示例

推荐使用 raw endpoint，用户只需要传入一段信息：

```python
import httpx

payload = {
    "question": "我是不是有背锅风险？",
    "information": """
    组织架构：张伟 - 产品负责人 - Product 团队 - 汇报王强
    组织架构：王强 - 部门经理 - Platform 团队
    组织架构：李娜 - 资深同事 - Product 团队 - 汇报王强

    张伟说这个需求先对齐口径，周五上线，先不用审批，后面我来闭环。
    李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。
    张伟和王强私下沟通过，没有同步到项目群。
    """,
    "use_memory": True,
    "save_to_memory": True,
}

result = httpx.post(
    "http://127.0.0.1:8010/api/v1/workplace/analyze/raw",
    json=payload,
).json()

print(result["summary"])
print(result["person_histories"].keys())
print(result["work_graph"]["summary"])
print(result["jargon_signals"])
```

结构化客户端也可以调用：

```text
POST /api/v1/workplace/analyze
```

## Harness 使用

推荐的集成入口是 `WorkplaceInsightHarness`。

```python
from workplace_thinker import WorkplaceInsightHarness

harness = WorkplaceInsightHarness(
    session_id="my_workplace_journey",
    enable_memory=True,
)

result = await harness.analyze_information(
    information="组织架构：张伟 - 产品负责人 - 汇报王强\n张伟说先做，不用审批，后补流程。",
    question="有什么隐藏风险？",
    use_memory=True,
    save_to_memory=True,
)

print(result["person_histories"]["张伟"])
```

Harness 包了四层：

| 层 | 作用 |
| --- | --- |
| `InputHarness` | 接受一坨信息，自动拆成证据、组织架构线索和问题上下文 |
| `ReasoningHarness` | 基于证据规则推理，并可接 LLM 增强 |
| `GraphHarness` | 生成 graph legend、焦点节点、统计和默认视图 |
| `ControlHarness` | 生成确认、否定、提升记忆、排除敏感内容等用户控制动作 |

## 返回结构

典型返回包含：

```text
summary
graph
graph_view
people
person_histories
work_graph
relationships
risks
hidden_hypotheses
behavior_observations
jargon_signals
org_dynamics_signals
knowledge_context
recommended_questions
evidence
uncertainty_checklist
multiple_hypotheses
prioritized_results
action_scripts
temporal_analysis
control_manifest
persistent_graph
graph_timeline
memory_stats
harness
meta
```

重点字段：

| 字段 | 含义 |
| --- | --- |
| `person_histories` | 每个人的人物档案：当前证据、风险、关系、工作关联、黑话语义、长期画像和历史摘要。 |
| `work_graph` | 工作对象节点和人物到工作对象的边。 |
| `behavior_observations` | 基于证据的行为观察，不是人格标签。 |
| `jargon_signals` | 命中的互联网职场黑话、归一化语义和安全确认问题。 |
| `org_dynamics_signals` | 组织政治 / 权力动态信号，例如信息门控、影子决策、背书、责任转移、资源控制等。 |
| `knowledge_context` | 本轮触发的职场知识框架和安全边界。 |
| `control_manifest` | 用户控制动作和记忆策略。 |

## 图谱含义

节点：

- `person`：人物
- `work_object`：工作对象
- `risk_signal`：风险信号
- `hidden_hypothesis`：隐藏假设

边：

- `formal_reports_to`：正式汇报关系
- `collaborates_with`：合作关系
- `supports`：支持关系
- `blocks_or_challenges`：阻塞 / 质疑
- `commits_to`：承诺 / 交付
- `owns_work`：负责工作
- `approves_work`：审批 / 授权
- `validates_work`：验收
- `sets_deadline`：设定时间要求
- `depends_on`：依赖
- `mentions_risk`：人物涉及某风险
- `supports_hypothesis`：风险信号支持某个假设

视觉语言：

- 圆形 = 人物
- 六边形 = 工作对象
- 圆角方块 = 风险信号
- 菱形 = 隐藏假设
- 蓝色边 = 正式组织关系
- 绿色边 = 支持 / 协作
- 土黄色边 = 工作负责 / 审批 / 时间要求
- 铜色虚线 = 风险信号
- 紫色点线 = 假设支持

## 记忆系统 API

```python
# 获取记忆统计
stats = harness.get_memory_stats()

# 获取人物画像
profile = harness.get_person_profile("张伟")

# 导出记忆，包含图谱数据
memory_data = harness.export_memory()

# 导入记忆
harness.import_memory(memory_data)

# 获取两个人关系的历史
history = harness.get_relationship_history("张伟", "王强")

# 清空当前会话记忆
harness.clear_session_memory()
```

API 还提供：

```text
GET    /api/v1/memory/sessions
GET    /api/v1/memory/stats/{session_id}
GET    /api/v1/memory/profile/{session_id}/{person_name}
POST   /api/v1/memory/export
POST   /api/v1/memory/import
POST   /api/v1/memory/clear/{session_id}
DELETE /api/v1/memory/session/{session_id}
POST   /api/v1/workplace/feedback
GET    /api/v1/conversation/suggest/{session_id}
GET    /api/v1/conversation/summary/{session_id}
```

## 产品原则

WorkplaceThinker 应该让用户更清醒，而不是更焦虑。

- 没有证据，不输出强结论。
- 隐藏问题只能是 hypothesis，不是事实。
- 行为观察不是人格判断。
- 历史记忆只能提示“值得检查”，不能直接当作当前事实。
- 互联网黑话只是语义信号，不是证据本身。
- 组织政治只能作为可验证的权力、信息、资源、信用和责任流动信号，不输出阴谋论或人格定性。
- 建议应该偏向中性确认、书面留痕、边界澄清。
- 敏感内容应该可排除、可删除、可不进入长期记忆。

## 验证

当前重点验证命令：

```bash
python3 -m unittest tests.test_workplace_insights -v
python3 -m py_compile workplace_thinker/knowledge_injection.py workplace_thinker/insights.py workplace_thinker/harness.py workplace_thinker/api.py
```

检查 standalone HTML demo 的脚本语法：

```bash
python3 - <<'PY' > /tmp/workplace_radar_script.js
from pathlib import Path
text = Path('apps/workplace_radar.html').read_text()
start = text.index('<script>') + len('<script>')
end = text.index('</script>', start)
print(text[start:end])
PY
node --check /tmp/workplace_radar_script.js
```

## 文档

- [Agent 架构](docs/workplace/AGENT_ARCHITECTURE.md)
- [产品架构](docs/workplace/PRODUCT_ARCHITECTURE.md)
- [算法设计](docs/workplace/ALGORITHM_DESIGN.md)
- [长期组织政治 / 权力动态架构](docs/workplace/ORGANIZATIONAL_DYNAMICS_ARCHITECTURE.md)

## 下一步

- 更强的工作内容图谱抽取：owner / approver / reviewer / dependency / deadline。
- UI 中加入证据 hover 和 graph 过滤。
- 人物档案时间线和 case 历史搜索。
- 用户确认 / 否定后的记忆更新闭环。
- 面向敏感职场材料的私有本地存储模式。
- 更多知识包：新人 onboarding、项目交付、绩效沟通、跨团队协作。

底层能力来自 DocThinker 的 agentic memory、上传、聊天和图谱框架；WorkplaceThinker 是面向职场关系洞察的垂直产品 fork。

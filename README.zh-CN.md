# WorkplaceThinker

[English](README.md) | [中文](README.zh-CN.md)

**把一坨职场信息粘进去，自动生成有证据的人际关系图和风险图。**

WorkplaceThinker 是基于 DocThinker fork 出来的职场关系洞察应用。它面向刚入职场、刚进新团队、正在处理复杂协作关系的人：你可以直接粘贴聊天记录、会议纪要、组织架构、项目背景或上传材料，系统会把这些信息整理成一张可审计的关系图。

它不是“读心术”，也不是教你算计别人。它会把事实、风险信号和隐藏假设分开，每个风险和假设都尽量回到证据，并给出更稳妥的确认问题。

## 它解决什么问题

新人最难的不是做事，而是看不懂局势：

- 谁是真正 owner？
- 这件事是正式决策，还是私下口头安排？
- 对方是不是改口了？
- 我是不是在没有授权的情况下承担责任？
- 哪些话应该留痕确认？

WorkplaceThinker 的目标是把这些模糊担心变成结构化图谱。

## 核心能力

- **一框输入**：直接粘贴一坨信息，不需要先整理成 JSON。
- **人际关系图**：识别人、团队、正式汇报关系、协作关系、支持关系、阻塞关系。
- **风险图谱**：把流程绕过、信息不对称、责任边界不清、背锅风险、权力压力、立场反复等变成 graph 节点。
- **隐藏假设**：系统可以提出假设，但会明确标记为 hypothesis，不会当作事实。
- **证据链**：风险和假设尽量关联到原始证据片段。
- **用户控制**：用户可以确认、否定、提升为长期记忆，或者排除敏感内容。
- **记忆系统**：持续记忆人物特征、关系模式和风险信号。
- **持续图谱构建**：增量更新关系图谱，而不是每次都重建。
- **时间线视图**：查看关系和风险如何随时间演变。

## 快速运行

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

页面里直接粘贴信息即可生成关系图。

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

    张伟说这个需求先做，不用审批，后面再补流程。
    李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。
    张伟和王强私下沟通过，没有同步到项目群。
    """,
}

result = httpx.post(
    "http://127.0.0.1:8010/api/v1/workplace/analyze/raw",
    json=payload,
).json()

print(result["summary"])
print(result["graph"]["nodes"])
print(result["control_manifest"]["actions"])
```

## Harness 设计

对外推荐使用 `WorkplaceInsightHarness`，而不是直接调用底层抽取引擎。

```python
from workplace_thinker import WorkplaceInsightHarness

harness = WorkplaceInsightHarness()
result = await harness.analyze_information(
    information="组织架构：张伟 - 产品负责人 - 汇报王强\n张伟说先做，不用审批，后补流程。",
    question="有什么隐藏风险？",
)
```

它包装了四层：

| 层 | 作用 |
| --- | --- |
| `InputHarness` | 接受一坨信息，自动拆成证据、组织架构线索和问题上下文 |
| `ReasoningHarness` | 基于证据规则推理，并可接 LLM 增强 |
| `GraphHarness` | 生成 graph legend、焦点节点、统计和默认视图 |
| `ControlHarness` | 生成确认、否定、提升记忆、排除敏感内容等用户控制动作 |

## 记忆系统使用

启用记忆系统，支持持续构建关系图谱：

```python
from workplace_thinker import WorkplaceInsightHarness

# 启用记忆系统（同一个 session_id 会保留历史）
harness = WorkplaceInsightHarness(
    session_id="my_workplace_journey",
    enable_memory=True
)

# 第一天：了解团队
result1 = await harness.analyze_information(
    information="组织架构：张伟 - 产品负责人 - 汇报王强\n张伟说先做，不用审批，后补流程。",
    question="第一天入职，要注意什么？"
)

# 查看记忆中的当前图谱
current_graph = harness.get_current_graph()
print(current_graph["nodes"])

# 第二天：遇到问题（记忆会复用之前的信息）
result2 = await harness.analyze_information(
    information="李娜私下说，张伟之前也是这样，后来新人背锅了。",
    question="现在怎么办？"
)

# 查看图谱演变时间线
timeline = harness.get_graph_timeline()
print(timeline)
```

## 记忆系统 API

```python
# 获取记忆统计
stats = harness.get_memory_stats()

# 获取人物画像
profile = harness.get_person_profile("张伟")

# 导出记忆（包含图谱数据）
memory_data = harness.export_memory()

# 导入记忆
harness.import_memory(memory_data)

# 获取两个人关系的历史
history = harness.get_relationship_history("张伟", "王强")
```

## 图谱含义

节点：

- `person`：人物
- `risk_signal`：风险信号
- `hidden_hypothesis`：隐藏假设

边：

- `formal_reports_to`：正式汇报关系
- `collaborates_with`：合作关系
- `supports`：支持关系
- `blocks_or_challenges`：阻塞 / 质疑
- `commits_to`：承诺 / 交付
- `mentions_risk`：人物涉及某风险
- `supports_hypothesis`：风险信号支持某个假设

## 产品原则

WorkplaceThinker 应该让用户更清醒，而不是更焦虑。

- 没有证据，不输出强结论。
- 隐藏问题只能是 hypothesis，不是事实。
- 类比、归纳只能提示“值得确认”，不能直接定性。
- 建议应该偏向中性确认、书面留痕、边界澄清。
- 敏感内容应该可排除、可删除、可不进入长期记忆。

## 文档

- [Agent 架构](docs/workplace/AGENT_ARCHITECTURE.md)
- [产品架构](docs/workplace/PRODUCT_ARCHITECTURE.md)
- [算法设计](docs/workplace/ALGORITHM_DESIGN.md)

## 下一步

- 引入演绎推理、归纳推理、类比推理 trace。
- 接入长期 memory 的相似案例召回。
- 做用户确认/否定后的记忆更新。
- 增强 graph 交互：证据 hover、风险过滤、时间线模式。

底层能力来自 DocThinker 的 agentic memory、上传、聊天和图谱框架；WorkplaceThinker 是面向职场关系洞察的垂直产品 fork。

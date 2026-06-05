# WorkplaceThinker

WorkplaceThinker 是基于 DocThinker fork 出来的职场关系洞察应用。

它面向刚入职场、刚进新团队、或正在处理复杂合作关系的人：用户可以上传材料、贴聊天记录、补充组织架构，然后系统把这些信息整理成可审计的人际关系图、合作关系图和隐藏风险假设。

## 核心能力

- 从聊天和上传材料中识别人、团队、项目、承诺、协作和冲突信号。
- 支持“一坨信息直接粘贴”：用户不需要先整理成 API 结构。
- 结合组织架构，区分正式汇报关系和实际协作关系。
- 挖掘潜在风险：责任边界不清、信息不对称、流程绕过、功劳/责任归属风险、权力压力、立场反复。
- 把隐藏问题标记为 hypothesis，而不是事实。
- 风险和隐藏假设会进入 graph，用户能直接看见谁牵涉到什么风险。
- 每条风险和假设都回到证据片段。
- 输出建议确认问题，帮助用户留痕、澄清边界、减少误判。

## 运行

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

## 产品原则

WorkplaceThinker 不是教用户算计别人，也不是把猜测包装成事实。它的目标是帮助新人更清楚地理解协作结构、更稳妥地确认责任、更有证据意识地处理复杂职场信息。

底层能力来自 DocThinker 的 agentic memory、上传、聊天和图谱框架；本项目新增职场关系与风险洞察算法层。

完整 agent 架构图见：[docs/workplace/AGENT_ARCHITECTURE.md](docs/workplace/AGENT_ARCHITECTURE.md)。

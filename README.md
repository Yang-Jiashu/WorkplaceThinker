# WorkplaceThinker

**Paste messy workplace context. Get an evidence-grounded relationship graph.**

WorkplaceThinker is a workplace relationship and risk insight agent built on top
of DocThinker's agentic memory foundation. It is designed for people who are new
to a team, new to work, or stuck in a confusing collaboration: paste chats,
meeting notes, org lines, project context, or uploaded text, and WorkplaceThinker
turns the situation into a graph of people, collaboration signals, risks,
hidden hypotheses, evidence, and safe next questions.

It does **not** claim to read minds. It separates observed facts from hypotheses,
requires evidence for claims, and suggests neutral confirmation questions instead
of encouraging suspicion or workplace politics.

## What It Does

- **One-box input**: paste all information directly. No structured payload needed.
- **Relationship graph**: see people, reporting lines, support, collaboration,
  challenge, commitment, risk signals, and hidden hypotheses.
- **Evidence-first reasoning**: every risk or hypothesis points back to evidence ids.
- **Harness architecture**: input, reasoning, graph, and control are packaged as
  one product-facing interface.
- **User control**: verify, reject, promote confirmed facts, or exclude sensitive
  context from memory.
- **Memory-ready**: designed to reuse DocThinker's session memory, long-horizon
  memory, and knowledge graph substrate.

## Why This Exists

Early-career employees often lack the informal context that experienced people
take for granted:

- Who actually owns a task?
- Is this a formal decision or a private side-channel?
- Is someone changing commitments?
- Could I be carrying responsibility without authority?
- What should I confirm in writing?

WorkplaceThinker turns vague anxiety into a structured, evidence-backed view:

```text
raw workplace context
  -> evidence ids
  -> people + org extraction
  -> relationship and risk candidates
  -> LLM-assisted reasoning with evidence constraints
  -> graph + risk cards + confirmation questions
  -> user verification and memory control
```

## Demo

Start the standalone API:

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

Open:

```text
http://127.0.0.1:8010
```

The demo UI lets you paste one information bundle and returns a graph. Risk
signals are graph nodes, hidden hypotheses are graph nodes, and the side panel
shows evidence-backed risks plus user control actions.

## Quick API Example

Use the product-friendly raw endpoint:

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

Structured integrations can call:

```text
POST /api/v1/workplace/analyze
```

## Harness Interface

The recommended integration surface is `WorkplaceInsightHarness`.

```python
from workplace_thinker import WorkplaceInsightHarness

harness = WorkplaceInsightHarness()
result = await harness.analyze_information(
    information="组织架构：张伟 - 产品负责人 - 汇报王强\n张伟说先做，不用审批，后补流程。",
    question="有什么隐藏风险？",
)
```

The harness wraps four layers:

| Layer | Role |
| --- | --- |
| `InputHarness` | Accepts one messy bundle and auto-splits evidence, org lines, and question context. |
| `ReasoningHarness` | Runs evidence-first rules plus optional LLM enrichment. |
| `GraphHarness` | Returns graph legend, focus nodes, graph statistics, and default view hints. |
| `ControlHarness` | Returns safe user actions: verify, reject, promote, exclude, and memory policy controls. |

The response includes:

```text
summary
graph
graph_view
risks
hidden_hypotheses
recommended_questions
evidence
control_manifest
harness
meta
```

## Graph Semantics

Nodes:

- `person`
- `risk_signal`
- `hidden_hypothesis`

Edges:

- `formal_reports_to`
- `collaborates_with`
- `supports`
- `blocks_or_challenges`
- `commits_to`
- `mentions_risk`
- `supports_hypothesis`

Visual language:

- circle = person
- rounded square = risk signal
- diamond = hidden hypothesis
- blue edge = formal organization line
- sage edge = support or collaboration
- copper dashed edge = risk signal
- plum dotted edge = hypothesis support

## Safety Principle

WorkplaceThinker should make users more careful, not more paranoid.

Rules:

- No evidence, no claim.
- Hypotheses are not facts.
- Analogy and induction can suggest what to check, not what to believe.
- Advice should favor neutral confirmation, written clarity, and boundary setting.
- Sensitive context should be user-controlled and excludable from memory.

## Docs

- [Agent architecture](docs/workplace/AGENT_ARCHITECTURE.md)
- [Product architecture](docs/workplace/PRODUCT_ARCHITECTURE.md)
- [Algorithm design](docs/workplace/ALGORITHM_DESIGN.md)

## Roadmap

- Deductive, inductive, and analogical reasoning traces.
- Memory-backed similar case retrieval.
- User correction loop for confirmed/false hypotheses.
- Better graph interaction: evidence hover, filter by risk type, timeline mode.
- Optional private local storage for workplace cases.

## Relationship To DocThinker

DocThinker remains the lower-level agentic memory framework. WorkplaceThinker is
a vertical product fork that uses DocThinker's memory, upload, chat, and graph
ideas for workplace relationship intelligence.

# WorkplaceThinker

[English](README.md) | [中文](README.zh-CN.md)

**Paste messy workplace context. Get an evidence-grounded people, work, risk, and memory map.**

WorkplaceThinker is a workplace context intelligence agent built on top of
DocThinker's agentic memory foundation. It is designed for people who are new to
work, new to a team, or stuck in a confusing collaboration. Paste chats, meeting
notes, org lines, project context, or uploaded text; WorkplaceThinker turns the
mess into auditable workplace maps:

- a **people network**: who reports to whom, who supports, blocks, commits, or changes stance;
- an **organization structure module**: a dedicated place to view, edit, record, and store departments, roles, people, and formal reporting lines;
- a **work network**: projects, tasks, decisions, owners, approvals, deliverables, deadlines, and acceptance signals;
- a **person profile explorer**: a Tianyancha-style directory for people mentioned in the case;
- a **risk and hypothesis graph**: evidence-backed risks and clearly marked hypotheses;
- a **knowledge-injected reasoning layer**: RACI, decision records, boundary setting, inference discipline, internet-workplace jargon semantics, and organizational dynamics.

It is not a mind reader. It separates observed facts, behavior signals, risks,
and hypotheses. It keeps evidence ids attached to claims and pushes the user
toward neutral confirmation, written clarity, and safer next questions.

## Why This Exists

Early-career employees often lack the informal context that experienced people
take for granted:

- Who is the real owner?
- Is this a formal decision or a private side-channel?
- Is someone changing commitments?
- Am I carrying responsibility without authority?
- What should I confirm in writing?
- What does "align", "close the loop", "owner", "push", or "blocker" actually imply in this conversation?

WorkplaceThinker turns vague anxiety into a structured, evidence-backed view:

```text
messy workplace context
  -> stable evidence ids
  -> people + org extraction
  -> work-object extraction
  -> relationship, risk, and jargon signals
  -> knowledge-injected reasoning
  -> graph + person dossiers + questions + controls
  -> user verification and memory control
```

## Core Capabilities

### One-Box Input

Paste a raw bundle of chats, org lines, notes, and questions. No structured
payload is required for the main path.

### People Network

WorkplaceThinker extracts people, formal reporting lines, collaboration,
support, challenge, commitment, and risk involvement. Each relation keeps the
evidence ids that caused it to appear.

### Organization Structure Module

The demo includes a dedicated **Organization Structure** tab for relatively
stable organization facts:

- departments / teams;
- people, titles, departments;
- formal reporting lines;
- department tree and person reporting tree;
- editable JSON drafts that can be reused in the next analysis.
- image + text import: upload org-chart screenshots, directory screenshots, or
  reporting-line diagrams, then use a VLM API to extract the structure.

The backend returns `org_structure`, stores it in session memory, and exposes
`GET /api/v1/org-structure/{session_id}`, `POST /api/v1/org-structure`,
and `POST /api/v1/org-structure/import`.

Multimodal import input:

```json
{
  "session_id": "my_session",
  "text": "Additional note: Zhang Wei reports to Wang Qiang.",
  "images": [
    {
      "name": "org-chart.png",
      "mime_type": "image/png",
      "data_url": "data:image/png;base64,..."
    }
  ],
  "use_vlm": true
}
```

The output uses the same `org_structure` contract and adds `import_summary`
with image count, VLM usage, and extracted people / department / reporting-line
counts.

### Work Network

The system now models work content explicitly. It can identify work objects such
as:

- `project`
- `task`
- `decision`
- `approval`
- `deliverable`
- `deadline`
- `acceptance`

It also links people to work through signals like owner, approval, validation,
deadline pressure, and dependency.

### Person Profile Explorer

The demo includes a **People Profiles** tab. It works like a lightweight
workplace dossier directory:

1. Open the People Profiles tab.
2. See everyone detected in the case.
3. Click a person.
4. Inspect that person's related relationships, risks, behavior observations,
   work links, jargon signals, evidence snippets, and historical analysis.

The profile is evidence-based. It does **not** label someone's personality. It
records observable interaction patterns only.

### Knowledge Injection

WorkplaceThinker includes an explicit workplace knowledge layer in
`workplace_thinker/knowledge_injection.py`. It injects frames such as:

- **RACI responsibility clarification**: responsible, accountable, consulted, informed;
- **Decision records**: private decisions and process exceptions should become auditable;
- **Boundary setting**: convert pressure into scope, resources, priority, and trade-offs;
- **Ladder of inference**: separate observation, interpretation, hypothesis, and action.

This keeps the product from relying only on keyword matching or unconstrained LLM
interpretation.

### Internet Workplace Jargon Semantics

The knowledge layer also understands common workplace/internet-business terms:

- align / 对齐 / 拉齐 / 口径一致
- close the loop / 闭环
- owner / 主责 / 牵头 / 兜底
- push / 推进 / 盯一下
- breakdown / 拆解 / 颗粒度
- schedule / 排期 / 上线 / 提测 / 联调
- blocker / 卡点 / 阻塞
- review / 复盘 / 沉淀
- leverage / 抓手 / 赋能 / 打法 / 链路

These terms are returned as `jargon_signals` with the matched terms, normalized
meaning, mapped workplace concepts, interpretation, and safe confirmation
questions.

### Organizational Dynamics

WorkplaceThinker can also detect evidence-backed organizational dynamics, such
as:

- information gatekeeping;
- shadow decision chains;
- sponsorship and backing;
- credit capture;
- blame shifting;
- resource control;
- coalition signals;
- performance pressure transfer.

These are returned as `org_dynamics_signals`. They are **signals, not facts**.
The system uses them to ask safer questions about authority, information flow,
resources, credit, and accountability. It does not provide manipulation,
factional, or attack advice.

### Evidence-First Risks and Hypotheses

Risk categories include:

- ownership ambiguity
- information asymmetry
- process bypass
- credit/blame risk
- power pressure
- stance volatility

Hidden hypotheses are first-class graph nodes and always marked with
`status = hypothesis_not_fact`.

### Memory and Timeline

With memory enabled, the harness tracks people, recurring patterns,
relationships, graph snapshots, and user feedback across turns. Users can export,
import, clear, or inspect memory through the harness/API.

## Demo

Start the standalone API:

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

Open:

```text
http://127.0.0.1:8010
```

The demo UI is a workflow-oriented workspace:

- **Input Workspace**: paste workplace context, import org charts, or migrate old memory exports.
- **Settings Center**: configure API base, session, memory policy, model providers, model parameters, chat templates, and automatic provider failover.
- **Results**: relationship graph, risks, hidden hypotheses, work network, organization structure, knowledge frames, and click-through people dossiers.

If you open `apps/workplace_radar.html` directly as a file, it can still show the
built-in fallback demo. To analyze live input, run the API server above.

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

Structured integrations can call:

```text
POST /api/v1/workplace/analyze
```

## Harness Interface

The recommended integration surface is `WorkplaceInsightHarness`.

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

The harness wraps four layers:

| Layer | Role |
| --- | --- |
| `InputHarness` | Accepts one messy bundle and auto-splits evidence, org lines, and question context. |
| `ReasoningHarness` | Runs evidence-first rules plus optional LLM enrichment. |
| `GraphHarness` | Returns graph legend, focus nodes, graph statistics, and default view hints. |
| `ControlHarness` | Returns safe user actions: verify, reject, promote, exclude, and memory policy controls. |

## Response Shape

A typical response includes:

```text
summary
graph
graph_view
people
person_histories
org_structure
work_graph
relationships
risks
hidden_hypotheses
behavior_observations
jargon_signals
org_dynamics_signals
org_dynamics_patterns
responsibility_chain
decision_trail
resource_map
evidence_event_summary
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

Important fields:

| Field | Meaning |
| --- | --- |
| `person_histories` | Per-person dossier with current evidence, risks, relations, work links, jargon signals, memory profile, and historical summaries. |
| `org_structure` | Dedicated organization module with departments, people, titles, formal reporting lines, department tree, and reporting tree. |
| `work_graph` | Work-object nodes and person-to-work edges. |
| `behavior_observations` | Evidence-backed behavior signals, explicitly not personality labels. |
| `jargon_signals` | Matched workplace jargon with normalized meanings and safe confirmation questions. |
| `org_dynamics_signals` | Organizational dynamics signals such as information gatekeeping, shadow decisions, sponsorship, blame shifting, or resource control. |
| `org_dynamics_patterns` | Conservative long-horizon pattern candidates consolidated from repeated organizational dynamics signals. |
| `responsibility_chain` | Observed or hypothesized flows of execution, approval, acceptance, credit, blame, pressure, and risk. |
| `decision_trail` | Formal decisions, approvals, side-channel decisions, and process exceptions that need traceable records. |
| `resource_map` | Resource, dependency, priority, permission, and performance-pressure control signals. |
| `evidence_event_summary` | Evidence metadata summary by visibility, channel, directness, speaker, and sensitivity. |
| `knowledge_context` | Active workplace reasoning frames and guardrails injected into analysis. |
| `control_manifest` | User-safe controls and memory policy. |

## Graph Semantics

Nodes:

- `person`
- `work_object`
- `risk_signal`
- `hidden_hypothesis`

Edges:

- `formal_reports_to`
- `collaborates_with`
- `supports`
- `blocks_or_challenges`
- `commits_to`
- `owns_work`
- `approves_work`
- `validates_work`
- `sets_deadline`
- `depends_on`
- `mentions_risk`
- `supports_hypothesis`

Visual language:

- circle = person
- hexagon = work object
- rounded square = risk signal
- diamond = hidden hypothesis
- blue edge = formal organization line
- sage edge = support or collaboration
- ochre edge = work ownership / approval / deadline
- copper dashed edge = risk signal
- plum dotted edge = hypothesis support

## Memory System API

```python
# Get memory stats
stats = harness.get_memory_stats()

# Get person profile
profile = harness.get_person_profile("Zhang Wei")

# Export memory, including graph data
memory_data = harness.export_memory()

# Import memory
harness.import_memory(memory_data)

# Preview schema migration without writing into the session
migration_preview = harness.preview_memory_migration(memory_data)

# Get relationship history between two people
history = harness.get_relationship_history("Zhang Wei", "Wang Qiang")

# Clear current session memory
harness.clear_session_memory()
```

The API also exposes:

```text
GET    /api/v1/memory/sessions
GET    /api/v1/memory/stats/{session_id}
GET    /api/v1/memory/profile/{session_id}/{person_name}
POST   /api/v1/memory/export
POST   /api/v1/memory/import
POST   /api/v1/memory/migrate
POST   /api/v1/memory/clear/{session_id}
DELETE /api/v1/memory/session/{session_id}
POST   /api/v1/workplace/feedback
GET    /api/v1/conversation/suggest/{session_id}
GET    /api/v1/conversation/summary/{session_id}
```

### Schema Migration

Memory exports and organization-structure records include `schema_version`.
When old exports are imported, WorkplaceThinker runs them through
`WorkplaceMemoryMigrator` first, preserving legacy `org_chart`, person
profiles, relationships, and graph snapshots while normalizing them into the
current contracts. Concrete version steps live in
`workplace_thinker/migration_plugins/`, so future migrations can be added as
small registered modules instead of editing the API/UI flow. Use
`POST /api/v1/memory/migrate` or
`harness.preview_memory_migration(memory_data)` to inspect the upgraded payload
before importing it.

For end users, migration is folder-based. A portable migration package can be
dragged into the browser UI or sent to `POST /api/v1/memory/migrate` as
`migration_package_files`. The folder may contain:

```text
workplace-memory/
  manifest.json
  memory.json
  org_structure.json
  person_profiles.json
  relationships.json
  graph_snapshots.json
```

`memory.json` can hold a full export. The other files are optional slices that
make the package easy to inspect, copy, back up, or move across versions. The
API assembles the folder into one memory payload, reports which files were
consumed or ignored, previews the upgraded schema, and only writes it into a
session after `POST /api/v1/memory/import`.

## Safety Principle

WorkplaceThinker should make users more careful, not more paranoid.

Rules:

- No evidence, no claim.
- Hypotheses are not facts.
- Behavior observations are not personality judgments.
- Historical memory can suggest what to check, not what to believe.
- Internet workplace jargon is interpreted as a semantic signal, not as proof.
- Organizational dynamics are treated as verifiable power / information / resource signals, not as conspiracy or personality claims.
- Advice should favor neutral confirmation, written clarity, and boundary setting.
- Sensitive context should be user-controlled, excludable, and deletable.

## Validation

Current focused validation:

```bash
python3 -m unittest tests.test_workplace_insights -v
python3 -m py_compile workplace_thinker/knowledge_injection.py workplace_thinker/insights.py workplace_thinker/harness.py workplace_thinker/api.py
```

For the standalone HTML demo script:

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

## Docs

- [Agent architecture](docs/workplace/AGENT_ARCHITECTURE.md)
- [Product architecture](docs/workplace/PRODUCT_ARCHITECTURE.md)
- [Algorithm design](docs/workplace/ALGORITHM_DESIGN.md)
- [Long-horizon organizational dynamics architecture](docs/workplace/ORGANIZATIONAL_DYNAMICS_ARCHITECTURE.md)

## Roadmap

- Stronger work-graph extraction for owner / approver / reviewer / dependency / deadline.
- Evidence hover and graph filtering in the UI.
- Better person-profile timeline and case history search.
- User correction flow for confirmed or false hypotheses.
- Private local storage mode for sensitive workplace cases.
- More workplace knowledge packs for onboarding, project delivery, performance review, and cross-team collaboration.

## Relationship To DocThinker

DocThinker remains the lower-level agentic memory framework. WorkplaceThinker is
a vertical product fork that uses DocThinker's memory, upload, chat, and graph
ideas for workplace relationship intelligence.

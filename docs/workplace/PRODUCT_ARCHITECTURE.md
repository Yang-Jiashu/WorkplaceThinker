# WorkplaceThinker Product Architecture

## Product Goal

WorkplaceThinker turns messy workplace context into an evidence-grounded graph:

- who is involved;
- who formally reports to whom;
- what the stable organization structure looks like: departments, roles, people,
  and reporting lines;
- who collaborates, supports, blocks, commits, or changes stance;
- where unclear ownership, private decision loops, process bypass, pressure, or
  credit/blame risk may exist.

The target user is an early-career employee who needs clarity, not paranoia.

## Input Modes

- Raw information bundle: one pasted block containing notes, chats, org lines,
  meeting snippets, and the user's question.
- Structured chat messages: observations, questions, meeting notes, private doubts.
- Uploaded text: email snippets, meeting minutes, project plans, policy docs.
- Organization chart: people, roles, teams, managers, reporting lines.

## Why LLM + Memory + Graph

LLMs are good at interpreting soft workplace language, but they can over-infer.
Graphs are good at making structure visible, but they need typed evidence.
Agentic memory is what lets the system accumulate long-horizon patterns:

- "this person often changes commitments late";
- "this project has repeated owner ambiguity";
- "this manager uses private channels for key decisions";
- "this user prefers neutral confirmation language".

## LLM Collaboration Pattern

The LLM does not directly produce the final answer from raw chat. It works inside
a constrained pipeline:

1. Rule extraction creates candidate people, edges, and risk signals.
2. Evidence ids are assigned before any LLM call.
3. The LLM receives:
   - user question;
   - organization chart;
   - evidence snippets with ids;
   - candidate relationships and risks;
   - output schema and safety rules.
4. The LLM may enrich:
   - relationship labels;
   - missing soft ties;
   - hidden hypotheses;
   - recommended confirmation questions.
5. The validator rejects or downgrades any item without evidence ids.

The product-friendly endpoint is `/api/v1/workplace/analyze/raw`. It accepts a
single `information` field and auto-splits the bundle into evidence, org chart
candidates, and chat/material context. Structured clients can still call
`/api/v1/workplace/analyze`.

## Harness Packaging

`WorkplaceInsightHarness` is the recommended integration boundary. It hides the
agent's internal complexity behind four layers:

- `InputHarness`: raw user information -> evidence, org candidates, question.
- `ReasoningHarness`: evidence-first deterministic extraction + optional LLM.
- `GraphHarness`: graph legend, focus nodes, graph statistics, default view.
- `ControlHarness`: memory policy and user-safe next actions.

This keeps the user experience simple: paste context, inspect graph, confirm or
reject what should become memory.

## Graph Model

Nodes:

- Person
- Team
- Project
- Decision
- RiskSignal
- Hypothesis

Edges:

- `formal_reports_to`
- `collaborates_with`
- `supports`
- `blocks_or_challenges`
- `commits_to`
- `changed_stance`
- `mentions_risk`
- `evidenced_by`

Visual language:

- Blue line: formal org structure.
- Sage line: support / collaboration.
- Copper dashed line: risk signal.
- Plum dotted line: hypothesis.
- Thicker line: stronger confidence or repeated evidence.

Risk signals and hidden hypotheses are first-class graph nodes, not just side
panel text. This lets users see which people and observed relationships connect
to each possible problem.

## Organization Structure Module

Organization structure is separated from conversational relationship inference.
It stores relatively stable facts:

- departments / teams;
- people, titles, and department membership;
- formal reporting lines;
- department tree and person reporting tree;
- editable JSON that can be saved into session memory and reused in future
  analysis.
- multimodal import from org-chart screenshots plus text through a VLM API.

This keeps "who officially reports to whom" distinct from softer signals like
support, blocking, sponsorship, or shadow decision chains.

Multimodal organization import is intentionally scoped to organization facts.
Its output is normalized back into `org_structure`; it should not infer risk,
personality, motive, sponsorship, or hidden political dynamics from an image
alone.

## Output Contract

Every response contains:

- `summary`
- `graph.nodes`
- `graph.edges`
- `org_structure`
- `risks`
- `hidden_hypotheses`
- `org_dynamics_signals`
- `org_dynamics_patterns`
- `responsibility_chain`
- `decision_trail`
- `resource_map`
- `evidence_event_summary`
- `recommended_questions`
- `evidence`
- `meta`

Hidden hypotheses must use `status = hypothesis_not_fact`.
Organizational dynamics patterns are conservative long-horizon candidates; a
single observation remains a `signal_cluster` until recurrence, memory, or user
confirmation upgrades it.

## Memory Design

Short-horizon memory:

- current uploaded docs;
- current chat and extracted evidence;
- current graph state.

Long-horizon memory:

- recurring collaboration patterns;
- repeated risk categories;
- user preferences for communication style;
- confirmed corrections from the user.

User controls:

- choose which chats/docs are remembered;
- delete specific workplace memories;
- mark a hypothesis as wrong;
- promote a confirmed relationship into durable memory.

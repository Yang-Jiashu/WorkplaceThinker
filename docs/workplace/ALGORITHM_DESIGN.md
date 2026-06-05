# WorkplaceThinker Algorithm Design

WorkplaceThinker is a vertical product fork built on DocThinker. DocThinker remains
the memory, upload, chat, retrieval, and graph substrate. WorkplaceThinker adds a
career-context reasoning layer for people, collaboration, and workplace risk.

## Inputs

- Chat messages: observations, questions, meeting notes, private doubts.
- Uploaded text: email snippets, meeting minutes, project plans, policy docs.
- Organization chart: people, roles, teams, managers, reporting lines.
- Optional DocThinker memory: prior conversations, durable insights, KG entities.

## Pipeline

1. Evidence segmentation
   - Split every chat/upload item into evidence ids.
   - Preserve source and original text.

2. Candidate extraction
   - Detect people from organization chart and text mentions.
   - Detect relation signals: reporting, collaboration, support, challenge, commitment.
   - Detect risk signals: ownership ambiguity, information asymmetry, process bypass,
     credit/blame risk, power pressure, stance volatility.

3. LLM-assisted reasoning
   - Send evidence ids, org chart, and rule candidates to the LLM.
   - Ask the LLM to enrich relationship labels and hidden hypotheses.
   - Require all risks and hypotheses to cite evidence ids.
   - Require hidden issues to be marked as `hypothesis_not_fact`.

4. Graph assembly
   - Nodes: people and optionally teams/projects.
   - Edges: formal org lines, collaboration, support, challenge, commitment, risk links.
   - Edge style reflects type: formal, observed relation, risk/hypothesis.

5. User-facing output
   - Summary.
   - Relationship graph.
   - Risk cards with evidence.
   - Hidden hypotheses separated from facts.
   - Recommended confirmation questions.

## Product Boundary

The product should not encourage manipulation or unsupported accusations. It should
help new employees:

- clarify responsibilities;
- preserve process evidence;
- ask neutral confirmation questions;
- identify where more information is needed;
- avoid treating weak signals as facts.


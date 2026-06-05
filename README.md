# WorkplaceThinker

WorkplaceThinker is a DocThinker-based fork for workplace relationship intelligence.
It helps early-career employees upload work-related context, chat through confusing
situations, and visualize potential collaboration patterns, reporting lines, and
hidden risks as an evidence-grounded graph.

DocThinker remains the lower-level agentic memory framework. WorkplaceThinker adds
a vertical product layer for:

- people and organization-structure extraction;
- relationship mining from chats and uploaded notes;
- collaboration, commitment, support, challenge, and reporting edges;
- hidden-risk hypotheses such as information asymmetry, process bypass, credit/blame
  risk, unclear ownership, and pressure-driven commitments;
- graph visualization so users can immediately see who connects to whom and where
  the risk signals sit;
- evidence-first summaries and neutral confirmation questions.

## Why This Exists

New employees often lack the context to understand informal influence, unclear
ownership, private communication loops, and shifting commitments. WorkplaceThinker
does not claim to read minds. It separates observed facts from hypotheses, ties
each warning to evidence, and suggests safer ways to clarify the situation.

## Core Flow

```text
Uploads + Chat + Org Chart
        |
        v
Evidence segmentation with stable evidence ids
        |
        v
People / relationship / risk candidate extraction
        |
        v
LLM-assisted enrichment with evidence constraints
        |
        v
Relationship graph + risk cards + confirmation questions
```

## Run The Standalone API

```bash
python -m uvicorn workplace_thinker.api:app --host 0.0.0.0 --port 8010
```

Then open the local graph demo:

```text
http://127.0.0.1:8010
```

The demo calls:

```text
POST /api/v1/workplace/analyze
```

You can also open `apps/workplace_radar.html` directly. If the API is not
running, the page displays a built-in sample graph.

## API Example

```python
import httpx

payload = {
    "question": "我是不是有背锅风险？",
    "chat_messages": [
        {"role": "user", "content": "张伟说这个需求先做，不用审批，后面再补流程。"},
        {"role": "user", "content": "李娜提醒我，王强之前答应负责验收，但现在又改口说不是他负责。"},
    ],
    "org_chart": [
        {"name": "张伟", "title": "产品负责人", "team": "Product", "manager": "王强"},
        {"name": "王强", "title": "部门经理", "team": "Platform"},
        {"name": "李娜", "title": "资深同事", "team": "Product", "manager": "王强"},
    ],
}

print(httpx.post("http://127.0.0.1:8010/api/v1/workplace/analyze", json=payload).json())
```

## Design Principle

Hidden issues are hypotheses, not facts. WorkplaceThinker should make users more
careful, better prepared, and more evidence-based, not more paranoid.

See [docs/workplace/ALGORITHM_DESIGN.md](docs/workplace/ALGORITHM_DESIGN.md).
See also [docs/workplace/PRODUCT_ARCHITECTURE.md](docs/workplace/PRODUCT_ARCHITECTURE.md).

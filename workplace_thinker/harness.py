"""Product harness for WorkplaceThinker.

The harness wraps the lower-level insight engine into a user-friendly product
contract: one input bundle in, graph + risks + controls out.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from .insights import LLMFunc, WorkplaceInsightEngine


class InputHarness:
    """Normalize user-facing inputs into engine-ready context."""

    def __init__(self, engine: WorkplaceInsightEngine):
        self.engine = engine

    def normalize_information(self, information: str, *, question: str = "") -> Dict[str, Any]:
        return self.engine.parse_information(information, question=question)


class ReasoningHarness:
    """Run evidence-first reasoning behind a narrow product contract."""

    def __init__(self, engine: WorkplaceInsightEngine):
        self.engine = engine

    async def analyze(
        self,
        *,
        chat_messages: Sequence[Dict[str, Any]] = (),
        uploaded_texts: Sequence[Dict[str, str]] = (),
        org_chart: Sequence[Dict[str, Any]] = (),
        question: str = "",
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        return await self.engine.analyze(
            chat_messages=chat_messages,
            uploaded_texts=uploaded_texts,
            org_chart=org_chart,
            question=question,
            use_llm=use_llm,
        )


class GraphHarness:
    """Prepare graph metadata for visualization and product UX."""

    legend = [
        {"type": "person", "shape": "circle", "label": "人物", "color": "#4b6f8f"},
        {"type": "risk_signal", "shape": "rounded-square", "label": "风险信号", "color": "#b85c38"},
        {"type": "hidden_hypothesis", "shape": "diamond", "label": "隐藏假设", "color": "#8a5f87"},
        {"type": "formal_reports_to", "shape": "edge", "label": "正式汇报关系", "color": "#4b6f8f"},
        {"type": "supports", "shape": "edge", "label": "支持 / 协作", "color": "#54746b"},
        {"type": "mentions_risk", "shape": "dashed-edge", "label": "涉及风险", "color": "#b85c38"},
        {"type": "supports_hypothesis", "shape": "dotted-edge", "label": "支持假设", "color": "#8a5f87"},
    ]

    def summarize(self, result: Dict[str, Any]) -> Dict[str, Any]:
        graph = result.get("graph") or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        node_counts = Counter(str(node.get("type") or "person") for node in nodes)
        edge_counts = Counter(str(edge.get("type") or "unknown") for edge in edges)
        high_risk_nodes = [
            node for node in nodes
            if node.get("type") == "risk_signal" and float(node.get("severity") or 0) >= 0.75
        ]
        focus_node_ids = [str(node.get("id")) for node in high_risk_nodes[:5]]
        if not focus_node_ids:
            focus_node_ids = [str(node.get("id")) for node in nodes if node.get("type") == "hidden_hypothesis"][:3]
        return {
            "legend": self.legend,
            "node_counts": dict(node_counts),
            "edge_counts": dict(edge_counts),
            "high_risk_count": len(high_risk_nodes),
            "focus_node_ids": focus_node_ids,
            "default_view": "risk-first" if high_risk_nodes else "relationship-first",
        }


class ControlHarness:
    """Build user controls that keep claims auditable and memory controllable."""

    def build(self, result: Dict[str, Any]) -> Dict[str, Any]:
        risks = result.get("risks") or []
        hypotheses = result.get("hidden_hypotheses") or []
        relationships = result.get("relationships") or []
        actions: List[Dict[str, Any]] = []

        if risks:
            top = risks[0]
            actions.append(
                {
                    "id": "verify_top_risk",
                    "label": f"验证最高风险：{top.get('title', '风险信号')}",
                    "type": "verify",
                    "target_id": top.get("id"),
                    "description": top.get("suggestion") or "回到证据确认风险是否成立。",
                }
            )
        if hypotheses:
            top = hypotheses[0]
            actions.append(
                {
                    "id": "mark_hypothesis",
                    "label": f"确认或否定假设：{top.get('title', '隐藏假设')}",
                    "type": "confirm_or_reject",
                    "target_id": top.get("id"),
                    "description": "隐藏假设不会当作事实进入长期记忆，除非用户确认。",
                }
            )
        if relationships:
            actions.append(
                {
                    "id": "promote_confirmed_relationships",
                    "label": "把确认过的关系写入长期记忆",
                    "type": "promote_memory",
                    "target_id": None,
                    "description": "只提升已确认的人际/协作关系；风险和假设默认不自动记忆。",
                }
            )
        actions.append(
            {
                "id": "exclude_sensitive_context",
                "label": "排除敏感内容",
                "type": "exclude_memory",
                "target_id": None,
                "description": "涉及隐私、薪酬、绩效评价或个人攻击的内容可从记忆写入中排除。",
            }
        )

        return {
            "mode": "user-controlled",
            "memory_policy": {
                "persist_confirmed_facts": True,
                "persist_unconfirmed_hypotheses": False,
                "require_evidence_for_claims": True,
                "allow_user_delete": True,
            },
            "actions": actions,
        }


class WorkplaceInsightHarness:
    """One-box workplace insight harness.

    This is the recommended public facade for product integrations.
    """

    def __init__(self, llm_func: Optional[LLMFunc] = None, engine: Optional[WorkplaceInsightEngine] = None):
        self.engine = engine or WorkplaceInsightEngine(llm_func=llm_func)
        self.input = InputHarness(self.engine)
        self.reasoning = ReasoningHarness(self.engine)
        self.graph = GraphHarness()
        self.control = ControlHarness()

    async def analyze_information(
        self,
        information: str,
        *,
        question: str = "",
        org_chart: Sequence[Dict[str, Any]] = (),
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        parsed = self.input.normalize_information(information, question=question)
        merged_org = list(org_chart or []) or parsed["org_chart"]
        result = await self.reasoning.analyze(
            chat_messages=parsed["chat_messages"],
            uploaded_texts=parsed["uploaded_texts"],
            org_chart=merged_org,
            question=question or parsed["question"],
            use_llm=use_llm,
        )
        result.setdefault("meta", {})["input_mode"] = "raw_information"
        result["parsed_input"] = {
            "question": question or parsed["question"],
            "org_chart": merged_org,
            "chat_message_count": len(parsed["chat_messages"]),
            "uploaded_text_count": len(parsed["uploaded_texts"]),
        }
        return self._enhance(result)

    async def analyze_structured(
        self,
        *,
        chat_messages: Sequence[Dict[str, Any]] = (),
        uploaded_texts: Sequence[Dict[str, str]] = (),
        org_chart: Sequence[Dict[str, Any]] = (),
        question: str = "",
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        result = await self.reasoning.analyze(
            chat_messages=chat_messages,
            uploaded_texts=uploaded_texts,
            org_chart=org_chart,
            question=question,
            use_llm=use_llm,
        )
        result.setdefault("meta", {})["input_mode"] = "structured"
        return self._enhance(result)

    def _enhance(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result["graph_view"] = self.graph.summarize(result)
        result["control_manifest"] = self.control.build(result)
        result["harness"] = {
            "name": "Workplace Insight Harness",
            "layers": [
                "input_harness",
                "reasoning_harness",
                "graph_harness",
                "control_harness",
            ],
            "contract": "one_information_bundle_to_evidence_grounded_graph",
        }
        return result

"""Product harness for WorkplaceThinker.

The harness wraps the lower-level insight engine into a user-friendly product
contract: one input bundle in, graph + risks + controls out.

Enhanced with Memory System:
- Session-based memory management
- Person profile tracking
- Historical scenario recall
- Memory export/import
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from .insights import LLMFunc, WorkplaceInsightEngine

try:
    from .memory_engine import WorkplaceMemoryEngine
    HAS_MEMORY_ENGINE = True
except ImportError:
    HAS_MEMORY_ENGINE = False


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
        use_memory: bool = True,
        save_to_memory: bool = True,
    ) -> Dict[str, Any]:
        return await self.engine.analyze(
            chat_messages=chat_messages,
            uploaded_texts=uploaded_texts,
            org_chart=org_chart,
            question=question,
            use_llm=use_llm,
            use_memory=use_memory,
            save_to_memory=save_to_memory,
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
    
    Enhanced with Memory System:
    - Session-based memory management
    - Person profile tracking
    - Historical scenario recall
    """

    def __init__(
        self, 
        llm_func: Optional[LLMFunc] = None, 
        engine: Optional[WorkplaceInsightEngine] = None,
        memory_engine: Optional[WorkplaceMemoryEngine] = None,
        session_id: Optional[str] = None,
        enable_memory: bool = True,
    ):
        self.enable_memory = enable_memory and HAS_MEMORY_ENGINE
        
        if self.enable_memory:
            self.memory = memory_engine or WorkplaceMemoryEngine(session_id=session_id)
            self.engine = engine or WorkplaceInsightEngine(
                llm_func=llm_func,
                memory_engine=self.memory,
                session_id=session_id,
                enable_memory=True,
            )
        else:
            self.memory = None
            self.engine = engine or WorkplaceInsightEngine(
                llm_func=llm_func,
                enable_memory=False,
            )
        
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
            "memory_enabled": self.enable_memory,
        }
        
        # 添加记忆统计
        if self.enable_memory and self.memory:
            result["memory_stats"] = self.memory.get_stats()
        
        return result
    
    # === 记忆管理公共方法 ===
    
    def get_memory_stats(self) -> Optional[Dict[str, Any]]:
        """获取记忆系统统计信息"""
        if self.enable_memory and self.memory:
            return self.memory.get_stats()
        return None
    
    def export_memory(self) -> Optional[Dict[str, Any]]:
        """导出记忆到字典"""
        if self.enable_memory and self.memory:
            return self.memory.export_memory()
        return None
    
    def import_memory(self, memory_data: Dict[str, Any]) -> bool:
        """从字典导入记忆"""
        if self.enable_memory and self.memory:
            self.memory.import_memory(memory_data)
            return True
        return False
    
    def get_person_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """获取人物画像"""
        if self.enable_memory and self.memory:
            profile = self.memory.get_person_profile(name)
            if profile:
                return {
                    "name": profile.name,
                    "title": profile.title,
                    "team": profile.team,
                    "traits": profile.traits,
                    "risk_signals": profile.risk_signals,
                    "evidence_snippets": profile.evidence_snippets[-10:],
                }
        return None
    
    async def record_user_feedback(self, feedback: Dict[str, Any]) -> bool:
        """记录用户反馈，用于改进记忆"""
        if self.enable_memory and self.memory:
            self.memory._feedback_history.append(feedback)
            return True
        return False
    
    def clear_session_memory(self) -> bool:
        """清空当前会话的记忆"""
        if self.enable_memory and self.memory:
            # 重新初始化记忆
            session_id = self.memory.session_id
            self.memory = WorkplaceMemoryEngine(session_id=session_id)
            # 更新引擎中的记忆引用
            self.engine.memory = self.memory
            return True
        return False

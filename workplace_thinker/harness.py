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

try:
    from .conversation_engine import ConversationEngine
    HAS_CONVERSATION = True
except ImportError:
    HAS_CONVERSATION = False

try:
    from .privacy_engine import PrivacyEngine
    HAS_PRIVACY = True
except ImportError:
    HAS_PRIVACY = False


class InputHarness:
    """Normalize user-facing inputs into engine-ready context. Includes auto-redaction."""

    def __init__(self, engine: WorkplaceInsightEngine):
        self.engine = engine
        self.privacy = PrivacyEngine() if HAS_PRIVACY else None

    def normalize_information(self, information: str, *, question: str = "") -> Dict[str, Any]:
        if self.privacy:
            information = self.privacy.redact_text(information)
            question = self.privacy.redact_text(question)
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
        {"type": "work_object", "shape": "hexagon", "label": "工作对象", "color": "#b7892d"},
        {"type": "risk_signal", "shape": "rounded-square", "label": "风险信号", "color": "#b85c38"},
        {"type": "hidden_hypothesis", "shape": "diamond", "label": "隐藏假设", "color": "#8a5f87"},
        {"type": "formal_reports_to", "shape": "edge", "label": "正式汇报关系", "color": "#4b6f8f"},
        {"type": "supports", "shape": "edge", "label": "支持 / 协作", "color": "#54746b"},
        {"type": "owns_work", "shape": "edge", "label": "负责工作", "color": "#b7892d"},
        {"type": "approves_work", "shape": "edge", "label": "审批 / 授权", "color": "#b7892d"},
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
        
        # P0 改进: 对话引擎
        self.conversation = ConversationEngine() if HAS_CONVERSATION else None

    async def analyze_information(
        self,
        information: str,
        *,
        question: str = "",
        org_chart: Sequence[Dict[str, Any]] = (),
        use_llm: bool = True,
        use_memory: bool = True,
        save_to_memory: bool = True,
    ) -> Dict[str, Any]:
        parsed = self.input.normalize_information(information, question=question)
        merged_org = list(org_chart or []) or parsed["org_chart"]
        
        # P0: 如果有对话历史，合并上下文
        if self.conversation and self.conversation.conversation_history:
            information, question = self.conversation.merge_with_previous_context(
                information, question
            )
        
        result = await self.reasoning.analyze(
            chat_messages=parsed["chat_messages"],
            uploaded_texts=parsed["uploaded_texts"],
            org_chart=merged_org,
            question=question or parsed["question"],
            use_llm=use_llm,
            use_memory=use_memory,
            save_to_memory=save_to_memory,
        )
        result.setdefault("meta", {})["input_mode"] = "raw_information"
        result["parsed_input"] = {
            "question": question or parsed["question"],
            "org_chart": merged_org,
            "chat_message_count": len(parsed["chat_messages"]),
            "uploaded_text_count": len(parsed["uploaded_texts"]),
        }
        enhanced = self._enhance(result)
        
        # P0: 记录到对话历史
        if self.conversation:
            self.conversation.add_turn(
                user_message=information,
                user_question=question or parsed["question"],
                analysis_result=enhanced,
            )
            # 添加追问建议
            enhanced["follow_up_suggestions"] = self.conversation.suggest_follow_up_questions(enhanced)
        
        return enhanced

    async def analyze_structured(
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
        result = await self.reasoning.analyze(
            chat_messages=chat_messages,
            uploaded_texts=uploaded_texts,
            org_chart=org_chart,
            question=question,
            use_llm=use_llm,
            use_memory=use_memory,
            save_to_memory=save_to_memory,
        )
        result.setdefault("meta", {})["input_mode"] = "structured"
        return self._enhance(result)

    def _enhance(self, result: Dict[str, Any]) -> Dict[str, Any]:
        result["graph_view"] = self.graph.summarize(result)
        result["control_manifest"] = self.control.build(result)
        result["person_histories"] = self._build_person_histories(result)
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
        
        # 添加记忆统计和当前图谱
        if self.enable_memory and self.memory:
            result["memory_stats"] = self.memory.get_stats()
            # 自动添加当前完整图谱
            result["persistent_graph"] = self.memory.get_current_graph()
            # 添加时间线
            result["graph_timeline"] = self.memory.get_graph_timeline()
        
        return result

    def _build_person_histories(self, result: Dict[str, Any]) -> Dict[str, Any]:
        people = result.get("people") or []
        relationships = result.get("relationships") or []
        risks = result.get("risks") or []
        behaviors = result.get("behavior_observations") or []
        jargon_signals = result.get("jargon_signals") or []
        org_dynamics_signals = result.get("org_dynamics_signals") or []
        org_dynamics_patterns = result.get("org_dynamics_patterns") or []
        responsibility_chain = result.get("responsibility_chain") or []
        decision_trail = result.get("decision_trail") or []
        resource_map = result.get("resource_map") or []
        evidence_items = result.get("evidence") or []
        work_graph = result.get("work_graph") or {}
        work_edges = work_graph.get("edges") or []

        evidence_by_id = {str(item.get("id")): item for item in evidence_items}
        histories: Dict[str, Any] = {}

        for person in people:
            name = str(person.get("label") or person.get("name") or "").strip()
            if not name:
                continue

            related_relationships = [
                item for item in relationships
                if name in {str(item.get("source_name") or ""), str(item.get("target_name") or "")}
            ]
            related_risks = [
                item for item in risks
                if name in [str(p) for p in item.get("people", []) or []]
            ]
            related_behaviors = [
                item for item in behaviors
                if str(item.get("person") or "") == name
            ]
            related_work_edges = [
                item for item in work_edges
                if str(item.get("source_name") or "") == name
            ]
            related_jargon = [
                item for item in jargon_signals
                if name in [str(p) for p in item.get("people", []) or []]
            ]
            related_org_dynamics = [
                item for item in org_dynamics_signals
                if name in [str(p) for p in item.get("people", []) or []]
            ]
            related_org_patterns = [
                item for item in org_dynamics_patterns
                if name in [str(p) for p in item.get("actors", []) or []]
            ]
            related_responsibility = [
                item for item in responsibility_chain
                if name in {str(item.get("from_actor") or ""), str(item.get("to_actor") or "")}
            ]
            related_decisions = [
                item for item in decision_trail
                if name in [str(p) for p in item.get("actors", []) or []]
            ]
            related_resources = [
                item for item in resource_map
                if name in [str(p) for p in item.get("controllers", []) or []]
            ]

            evidence_ids: List[str] = []
            for collection in (
                related_relationships,
                related_risks,
                related_behaviors,
                related_work_edges,
                related_jargon,
                related_org_dynamics,
                related_org_patterns,
                related_responsibility,
                related_decisions,
                related_resources,
            ):
                for item in collection:
                    evidence_ids.extend(str(eid) for eid in item.get("evidence_ids", []) or [])
            evidence_ids.extend(str(eid) for eid in person.get("evidence_ids", []) or [])
            evidence_ids = list(dict.fromkeys(evidence_ids))

            memory_profile = None
            historical_summaries: List[Dict[str, Any]] = []
            if self.enable_memory and self.memory:
                profile = self.memory.get_person_profile(name)
                if profile:
                    memory_profile = {
                        "name": profile.name,
                        "title": profile.title,
                        "team": profile.team,
                        "traits": profile.traits,
                        "observed_patterns": getattr(profile, "observed_patterns", []),
                        "risk_signals": profile.risk_signals,
                        "collaboration_style": profile.collaboration_style,
                        "communication_preference": profile.communication_preference,
                        "evidence_snippets": profile.evidence_snippets[-10:],
                        "last_updated": profile.last_updated,
                    }

                for analysis in list(getattr(self.memory, "_historical_analyses", []))[-20:]:
                    analysis_people = {
                        str(p.get("label") or p.get("name") or "")
                        for p in analysis.get("people", []) or []
                    }
                    if name not in analysis_people:
                        continue
                    historical_summaries.append(
                        {
                            "id": analysis.get("id"),
                            "timestamp": analysis.get("timestamp"),
                            "summary": analysis.get("summary", ""),
                            "risk_titles": [r.get("title", "") for r in (analysis.get("risks") or []) if name in (r.get("people") or [])][:5],
                        }
                    )

            histories[name] = {
                "person": person,
                "memory_profile": memory_profile,
                "current": {
                    "relationships": related_relationships,
                    "risks": related_risks,
                    "behavior_observations": related_behaviors,
                    "work_edges": related_work_edges,
                    "jargon_signals": related_jargon,
                    "org_dynamics_signals": related_org_dynamics,
                    "org_dynamics_patterns": related_org_patterns,
                    "responsibility_chain": related_responsibility,
                    "decision_trail": related_decisions,
                    "resource_map": related_resources,
                    "evidence": [evidence_by_id[eid] for eid in evidence_ids if eid in evidence_by_id],
                },
                "history": historical_summaries[-10:],
                "safety_note": "这是基于证据的互动记录和行为信号，不是人格定性。",
            }

        return histories
    
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
                    "observed_patterns": getattr(profile, "observed_patterns", []),
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
    
    # ====== 持续图谱构建 ======
    
    def get_current_graph(self) -> Optional[Dict[str, Any]]:
        """获取当前最新的关系图谱（持续构建的版本）"""
        if self.enable_memory and self.memory:
            return self.memory.get_current_graph()
        return None
    
    def get_graph_timeline(self) -> Optional[List[Dict[str, Any]]]:
        """获取图谱的时间线演变记录"""
        if self.enable_memory and self.memory:
            return self.memory.get_graph_timeline()
        return None
    
    def get_relationship_history(self, person1: str, person2: str) -> Optional[List[Dict[str, Any]]]:
        """获取两个人之间的关系演变历史"""
        if self.enable_memory and self.memory:
            return self.memory.get_relationship_history(person1, person2)
        return None
    
    def record_user_feedback(self, feedback: Dict[str, Any]) -> Optional[str]:
        """
        记录用户反馈：
        - 对不确定性检查清单的选择
        - 对多重假设的选择
        - 用户自定义的理解
        """
        if self.enable_memory and self.memory:
            return self.memory.record_user_feedback(feedback)
        return None
    
    def get_user_feedback_history(self) -> Optional[List[Dict[str, Any]]]:
        """获取用户反馈历史"""
        if self.enable_memory and self.memory:
            return self.memory.get_user_feedback_history()
        return None
    
    # ====== P0: 对话式追问 ======
    
    def get_conversation_summary(self) -> Optional[Dict[str, Any]]:
        """
        获取对话总结
        包括: 对话轮数、话题、关键人物、关键风险、关键洞察
        """
        if self.conversation:
            return self.conversation.get_conversation_summary()
        return None
    
    def get_conversation_context(self) -> Optional[Dict[str, Any]]:
        """
        获取当前对话的上下文摘要
        """
        if self.conversation:
            return self.conversation.get_context_summary()
        return None
    
    def suggest_follow_up_questions(
        self, 
        last_analysis: Optional[Dict[str, Any]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取智能追问建议
        返回: [{question, reason, expected_value, difficulty}, ...]
        """
        if not self.conversation:
            return None
        
        if last_analysis is None and self.conversation.conversation_history:
            last_analysis = self.conversation.conversation_history[-1].analysis_result
        
        if last_analysis is None:
            return []
        
        return self.conversation.suggest_follow_up_questions(last_analysis)
    
    def clear_conversation(self) -> bool:
        """
        清空对话历史
        """
        if self.conversation:
            self.conversation = ConversationEngine()
            return True
        return False

"""
WorkplaceThinker Memory Engine - 集成 DocThinker 的 Agentic Memory System

这个模块将 DocThinker 的强大记忆能力集成到 WorkplaceThinker 中，包括：
- 长期记忆：保存职场模式、人物特征、历史风险
- 情节记忆：类比检索相似历史场景
- 会话记忆：跨回合的上下文延续
- 知识图谱：持久化的组织关系和风险模式
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

try:
    from docthinker.memory_core import AgentMemoryCore, RecallBundle
    from docthinker.memory_core.protocols import MemoryPolicy
    HAS_DOCTHINKER_MEMORY = True
except ImportError:
    HAS_DOCTHINKER_MEMORY = False
    print("[WorkplaceThinker] DocThinker memory not available, using fallback")


@dataclass
class WorkplaceMemoryPattern:
    """职场记忆模式 - 用于存储可复用的洞察"""
    pattern_type: str  # "person_trait", "risk_pattern", "team_dynamic", "org_trend"
    name: str
    description: str
    confidence: float = 0.5
    examples: List[str] = field(default_factory=list)
    evidence_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


@dataclass
class PersonProfile:
    """人物画像 - 存储人物特征和历史行为"""
    name: str
    title: str = ""
    team: str = ""
    traits: List[str] = field(default_factory=list)  # 性格、工作风格
    risk_signals: List[str] = field(default_factory=list)  # 历史风险模式
    collaboration_style: str = ""
    communication_preference: str = ""
    evidence_snippets: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


class WorkplaceMemoryEngine:
    """
    职场记忆引擎 - 管理 WorkplaceThinker 的所有记忆功能
    
    功能包括：
    1. 历史场景检索 - 找到相似的职场情况
    2. 人物画像积累 - 持续更新人物特征
    3. 风险模式识别 - 识别重复出现的风险模式
    4. 用户反馈学习 - 根据用户确认/否定调整记忆
    5. 记忆导出/导入 - 支持记忆的持久化
    """
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        use_docthinker_core: bool = True,
    ):
        self.session_id = session_id or f"workplace_{int(time.time())}"
        self.use_docthinker = use_docthinker_core and HAS_DOCTHINKER_MEMORY
        
        # 内存中的记忆存储（当 DocThinker 不可用时的后备方案）
        self._person_profiles: Dict[str, PersonProfile] = {}
        self._patterns: Dict[str, WorkplaceMemoryPattern] = {}
        self._historical_analyses: List[Dict[str, Any]] = []
        self._feedback_history: List[Dict[str, Any]] = []
        
        # DocThinker 记忆核心
        self._memory_core: Optional[AgentMemoryCore] = None
        if self.use_docthinker:
            self._init_docthinker_memory()
    
    def _init_docthinker_memory(self):
        """初始化 DocThinker 记忆核心"""
        if not HAS_DOCTHINKER_MEMORY:
            return
        
        try:
            policy = MemoryPolicy(
                long_horizon_top_k=5,
                long_horizon_min_confidence=0.4,
                long_horizon_write_scope="session",
                enabled_layers=["long_horizon", "episodic"],
            )
            
            # 目前使用默认的后端配置
            self._memory_core = AgentMemoryCore(policy=policy)
            print(f"[WorkplaceThinker] DocThinker memory initialized for session {self.session_id}")
        except Exception as e:
            print(f"[WorkplaceThinker] Failed to initialize DocThinker memory: {e}")
            self.use_docthinker = False
    
    async def recall_similar_scenarios(
        self,
        query: str,
        people: List[str] = None,
        risk_types: List[str] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        检索相似的历史职场场景
        
        Args:
            query: 当前场景的描述
            people: 相关人物
            risk_types: 风险类型
            top_k: 返回数量
            
        Returns:
            相似场景列表，包括当时的分析和结果
        """
        results: List[Dict[str, Any]] = []
        
        # 首先尝试 DocThinker 的情节记忆
        if self.use_docthinker and self._memory_core:
            try:
                recall_result = await self._memory_core.recall(
                    session_id=self.session_id,
                    query=query,
                    enable_thinking=True,
                )
                if recall_result.episodic_matches:
                    results.extend(recall_result.episodic_matches)
            except Exception as e:
                print(f"[WorkplaceThinker] DocThinker recall failed: {e}")
        
        # 然后使用本地存储的历史分析进行匹配
        local_matches = self._search_local_history(query, people, risk_types, top_k)
        results.extend(local_matches)
        
        # 去重并按相关性排序
        seen = set()
        unique_results = []
        for r in results[:top_k]:
            key = str(r.get("id") or r.get("summary", ""))
            if key not in seen:
                seen.add(key)
                unique_results.append(r)
        
        return unique_results
    
    def _search_local_history(
        self,
        query: str,
        people: List[str] = None,
        risk_types: List[str] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """在本地历史分析中搜索相似场景"""
        if not self._historical_analyses:
            return []
        
        query_lower = query.lower()
        people_set = set(people or [])
        risk_set = set(risk_types or [])
        
        scored = []
        for analysis in self._historical_analyses:
            score = 0.0
            
            # 文本相似度（简单的关键词匹配）
            summary = analysis.get("summary", "").lower()
            if query_lower in summary:
                score += 0.5
            
            # 人物匹配
            analysis_people = set(p.get("name", "") for p in analysis.get("people", []))
            if people_set and analysis_people & people_set:
                score += 0.3 * len(analysis_people & people_set) / max(len(analysis_people), len(people_set))
            
            # 风险类型匹配
            analysis_risks = set(r.get("category", "") for r in analysis.get("risks", []))
            if risk_set and analysis_risks & risk_set:
                score += 0.2 * len(analysis_risks & risk_set) / max(len(analysis_risks), len(risk_set))
            
            if score > 0:
                scored.append((-score, analysis))  # 负分用于升序排序
        
        scored.sort()
        return [a for (_, a) in scored[:top_k]]
    
    def get_person_profile(self, name: str) -> Optional[PersonProfile]:
        """获取人物画像"""
        return self._person_profiles.get(name)
    
    def update_person_profile(
        self,
        name: str,
        title: str = "",
        team: str = "",
        traits: List[str] = None,
        risk_signals: List[str] = None,
        evidence_snippet: str = "",
    ):
        """更新人物画像"""
        if name not in self._person_profiles:
            self._person_profiles[name] = PersonProfile(name=name)
        
        profile = self._person_profiles[name]
        if title:
            profile.title = title
        if team:
            profile.team = team
        if traits:
            for trait in traits:
                if trait not in profile.traits:
                    profile.traits.append(trait)
        if risk_signals:
            for risk in risk_signals:
                if risk not in profile.risk_signals:
                    profile.risk_signals.append(risk)
        if evidence_snippet:
            if evidence_snippet not in profile.evidence_snippets:
                profile.evidence_snippets.append(evidence_snippet)
                if len(profile.evidence_snippets) > 20:
                    profile.evidence_snippets = profile.evidence_snippets[-20:]
        
        profile.last_updated = time.time()
    
    def get_pattern(self, pattern_name: str) -> Optional[WorkplaceMemoryPattern]:
        """获取记忆模式"""
        return self._patterns.get(pattern_name)
    
    def record_pattern(
        self,
        pattern_type: str,
        name: str,
        description: str,
        example: str = "",
        confidence: float = 0.5,
    ):
        """记录一个观察到的模式"""
        key = f"{pattern_type}:{name}"
        if key not in self._patterns:
            self._patterns[key] = WorkplaceMemoryPattern(
                pattern_type=pattern_type,
                name=name,
                description=description,
                confidence=confidence,
            )
        
        pattern = self._patterns[key]
        if example and example not in pattern.examples:
            pattern.examples.append(example)
        pattern.evidence_count += 1
        pattern.last_used = time.time()
        pattern.confidence = min(0.95, pattern.confidence + 0.05)
    
    async def record_analysis(
        self,
        analysis_result: Dict[str, Any],
        user_feedback: Optional[Dict[str, Any]] = None,
    ):
        """
        记录一次分析结果，用于未来的类比检索
        
        Args:
            analysis_result: analyze() 方法的返回结果
            user_feedback: 用户的反馈（可选）
        """
        # 保存到历史分析
        record = {
            "id": f"analysis_{int(time.time())}",
            "timestamp": time.time(),
            "session_id": self.session_id,
            **analysis_result,
        }
        self._historical_analyses.append(record)
        
        # 限制历史记录数量
        if len(self._historical_analyses) > 100:
            self._historical_analyses = self._historical_analyses[-100:]
        
        # 记录反馈
        if user_feedback:
            self._feedback_history.append({
                "analysis_id": record["id"],
                "timestamp": time.time(),
                **user_feedback,
            })
        
        # 更新人物画像
        for person in analysis_result.get("people", []):
            name = person.get("label", person.get("name", ""))
            if name:
                signals = list(person.get("signals", {}).keys())
                evidence = person.get("evidence_ids", [])[:1]
                self.update_person_profile(
                    name=name,
                    title=person.get("title", ""),
                    team=person.get("team", ""),
                    risk_signals=signals,
                )
        
        # 记录风险模式
        for risk in analysis_result.get("risks", []):
            category = risk.get("category", "")
            if category:
                self.record_pattern(
                    pattern_type="risk_pattern",
                    name=category,
                    description=risk.get("title", category),
                    example=risk.get("evidence_text", ""),
                    confidence=risk.get("confidence", 0.5),
                )
        
        # 保存到 DocThinker 的长期记忆
        if self.use_docthinker and self._memory_core:
            await self._save_to_docthinker_memory(analysis_result)
    
    async def _save_to_docthinker_memory(self, analysis_result: Dict[str, Any]):
        """将分析结果保存到 DocThinker 的长期记忆中"""
        if not self._memory_core:
            return
        
        try:
            # 构建记忆条目
            summary = analysis_result.get("summary", "")
            risks = [r.get("title", "") for r in analysis_result.get("risks", [])[:3]]
            people = [p.get("label", "") for p in analysis_result.get("people", [])[:5]]
            
            memory_text = f"""职场洞察：{summary}
关键人物：{', '.join(people)}
主要风险：{', '.join(risks) if risks else '无明显风险'}"""
            
            # 提取概念
            concepts = people + risks
            
            # 调用 DocThinker 的记忆巩固
            await self._memory_core.after_response(
                session_id=self.session_id,
                question="职场关系分析",
                answer=memory_text,
                concepts=concepts,
            )
            
            print(f"[WorkplaceThinker] Saved analysis to DocThinker memory")
        except Exception as e:
            print(f"[WorkplaceThinker] Failed to save to DocThinker memory: {e}")
    
    def get_memory_context(self, query: str = "") -> Dict[str, Any]:
        """
        获取当前的记忆上下文，用于增强分析
        
        Returns:
            包含相关记忆的字典，可注入到分析过程中
        """
        context = {
            "has_memory": True,
            "person_profiles": {},
            "relevant_patterns": [],
            "similar_scenarios_count": len(self._historical_analyses),
        }
        
        # 人物画像摘要
        for name, profile in list(self._person_profiles.items())[:10]:
            context["person_profiles"][name] = {
                "title": profile.title,
                "team": profile.team,
                "traits": profile.traits[:5],
                "risk_signals": profile.risk_signals[:5],
                "evidence_count": len(profile.evidence_snippets),
            }
        
        # 高置信度的模式
        for key, pattern in self._patterns.items():
            if pattern.confidence >= 0.6:
                context["relevant_patterns"].append({
                    "type": pattern.pattern_type,
                    "name": pattern.name,
                    "description": pattern.description,
                    "confidence": pattern.confidence,
                    "evidence_count": pattern.evidence_count,
                })
        
        return context
    
    def export_memory(self) -> Dict[str, Any]:
        """导出记忆到字典，用于持久化"""
        return {
            "session_id": self.session_id,
            "exported_at": time.time(),
            "person_profiles": {
                name: {
                    "name": p.name,
                    "title": p.title,
                    "team": p.team,
                    "traits": p.traits,
                    "risk_signals": p.risk_signals,
                    "collaboration_style": p.collaboration_style,
                    "evidence_snippets": p.evidence_snippets,
                    "last_updated": p.last_updated,
                }
                for name, p in self._person_profiles.items()
            },
            "patterns": {
                key: {
                    "pattern_type": p.pattern_type,
                    "name": p.name,
                    "description": p.description,
                    "confidence": p.confidence,
                    "examples": p.examples,
                    "evidence_count": p.evidence_count,
                    "created_at": p.created_at,
                    "last_used": p.last_used,
                }
                for key, p in self._patterns.items()
            },
            "historical_analyses_count": len(self._historical_analyses),
        }
    
    def import_memory(self, data: Dict[str, Any]):
        """从字典导入记忆"""
        if "person_profiles" in data:
            for name, profile_data in data["person_profiles"].items():
                profile = PersonProfile(
                    name=profile_data["name"],
                    title=profile_data.get("title", ""),
                    team=profile_data.get("team", ""),
                    traits=profile_data.get("traits", []),
                    risk_signals=profile_data.get("risk_signals", []),
                    collaboration_style=profile_data.get("collaboration_style", ""),
                    evidence_snippets=profile_data.get("evidence_snippets", []),
                    last_updated=profile_data.get("last_updated", time.time()),
                )
                self._person_profiles[name] = profile
        
        if "patterns" in data:
            for key, pattern_data in data["patterns"].items():
                self._patterns[key] = WorkplaceMemoryPattern(
                    pattern_type=pattern_data["pattern_type"],
                    name=pattern_data["name"],
                    description=pattern_data["description"],
                    confidence=pattern_data.get("confidence", 0.5),
                    examples=pattern_data.get("examples", []),
                    evidence_count=pattern_data.get("evidence_count", 0),
                    created_at=pattern_data.get("created_at", time.time()),
                    last_used=pattern_data.get("last_used", time.time()),
                )
        
        if "session_id" in data and not self.session_id:
            self.session_id = data["session_id"]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        return {
            "session_id": self.session_id,
            "person_profiles_count": len(self._person_profiles),
            "patterns_count": len(self._patterns),
            "historical_analyses_count": len(self._historical_analyses),
            "feedback_count": len(self._feedback_history),
            "use_docthinker": self.use_docthinker,
            "docthinker_available": HAS_DOCTHINKER_MEMORY,
        }

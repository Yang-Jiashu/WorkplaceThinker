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
import copy
import time
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .migrations import (
    CURRENT_MEMORY_SCHEMA_VERSION,
    CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
    WorkplaceMemoryMigrator,
)

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
    """人物档案 - 存储可观察互动模式和历史信号，不做人格定性"""
    name: str
    title: str = ""
    team: str = ""
    traits: List[str] = field(default_factory=list)  # Deprecated: 仅兼容旧导出，不再主动写入人格标签
    observed_patterns: List[str] = field(default_factory=list)  # 可证据追溯的互动 / 工作模式
    risk_signals: List[str] = field(default_factory=list)  # 历史风险模式
    collaboration_style: str = ""
    communication_preference: str = ""
    evidence_snippets: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


@dataclass
class RelationshipEdge:
    """关系边 - 记录两个人之间的关系"""
    source: str
    target: str
    relationship_type: str  # "formal_reports_to", "collaborates_with", "supports", etc.
    label: str
    confidence: float = 0.5
    evidence_count: int = 0
    first_observed_at: float = field(default_factory=time.time)
    last_observed_at: float = field(default_factory=time.time)
    evidence_snippets: List[str] = field(default_factory=list)
    
    def get_key(self) -> str:
        return f"{self.source}|{self.target}|{self.relationship_type}"


@dataclass
class GraphSnapshot:
    """图谱快照 - 记录某个时间点的图谱状态"""
    timestamp: float
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    summary: str = ""


class WorkplaceMemoryEngine:
    """
    职场记忆引擎 - 管理 WorkplaceThinker 的所有记忆功能
    
    功能包括：
    1. 历史场景检索 - 找到相似的职场情况
    2. 人物画像积累 - 持续更新人物特征
    3. 风险模式识别 - 识别重复出现的风险模式
    4. 持续图谱构建 - 增量更新关系图谱，支持时间线
    5. 用户反馈学习 - 根据用户确认/否定调整记忆
    6. 记忆导出/导入 - 支持记忆的持久化
    """

    @staticmethod
    def default_memory_root() -> Path:
        return Path(
            os.getenv("WORKPLACE_THINKER_MEMORY_ROOT")
            or Path(__file__).resolve().parents[1] / "data" / "workplace_memory"
        )
    
    def __init__(
        self,
        session_id: Optional[str] = None,
        use_docthinker_core: bool = True,
        memory_root: Optional[str] = None,
        load_existing: bool = True,
    ):
        self.session_id = session_id or f"workplace_{int(time.time())}"
        self.use_docthinker = use_docthinker_core and HAS_DOCTHINKER_MEMORY
        self.memory_root = Path(memory_root) if memory_root else self.default_memory_root()
        self.session_dir = self.memory_root / self._safe_session_id(self.session_id)
        self._loading_from_disk = False
        
        # 内存中的记忆存储（当 DocThinker 不可用时的后备方案）
        self._person_profiles: Dict[str, PersonProfile] = {}
        self._patterns: Dict[str, WorkplaceMemoryPattern] = {}
        self._historical_analyses: List[Dict[str, Any]] = []
        self._feedback_history: List[Dict[str, Any]] = []
        
        # ====== 持续图谱构建 ======
        self._relationships: Dict[str, RelationshipEdge] = {}  # key: source|target|type
        self._graph_snapshots: List[GraphSnapshot] = []  # 时间线快照
        self._people: Dict[str, Dict[str, Any]] = {}  # 持久化的人物节点
        self._org_structure: Dict[str, Any] = {
            "schema_name": "workplace_org_structure",
            "schema_version": CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
            "departments": [],
            "people": [],
            "reporting_lines": [],
            "department_tree": [],
            "reporting_tree": [],
            "summary": {},
            "updated_at": None,
        }
        self._org_structure_versions: List[Dict[str, Any]] = []
        self._migrator = WorkplaceMemoryMigrator()

        self._init_memory_folder(load_existing=load_existing)
        
        # DocThinker 记忆核心
        self._memory_core: Optional[AgentMemoryCore] = None
        if self.use_docthinker:
            self._init_docthinker_memory()

    def _safe_session_id(self, session_id: str) -> str:
        """Keep user-visible session folders portable and path-safe."""
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(session_id or "").strip())
        return safe.strip("._") or "default_session"

    def _init_memory_folder(self, *, load_existing: bool) -> None:
        """Create and optionally hydrate the fixed portable memory folder."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        if load_existing:
            self.load_from_memory_folder()

    def load_from_memory_folder(self) -> bool:
        """Load this session from its fixed on-disk memory folder if present."""
        memory_file = self.session_dir / "memory.json"
        if not memory_file.exists():
            return False
        try:
            data = json.loads(memory_file.read_text(encoding="utf-8"))
            self._loading_from_disk = True
            self.import_memory(data)
            return True
        except Exception as exc:
            print(f"[WorkplaceThinker] Failed to load memory folder {self.session_dir}: {exc}")
            return False
        finally:
            self._loading_from_disk = False

    def persist_memory_folder(self) -> Path:
        """Write the current session into a portable folder package."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        memory_data = self.export_memory()
        package_files = {
            "manifest.json": {
                "schema_name": "workplace_migration_package",
                "schema_version": CURRENT_MEMORY_SCHEMA_VERSION,
                "session_id": self.session_id,
                "updated_at": time.time(),
                "files": [
                    "memory.json",
                    "org_structure.json",
                    "person_profiles.json",
                    "relationships.json",
                    "graph_snapshots.json",
                ],
            },
            "memory.json": memory_data,
            "org_structure.json": memory_data.get("org_structure", {}),
            "person_profiles.json": memory_data.get("person_profiles", {}),
            "relationships.json": memory_data.get("relationships", {}),
            "graph_snapshots.json": memory_data.get("graph_snapshots", []),
        }
        for filename, payload in package_files.items():
            self._write_json_atomic(self.session_dir / filename, payload)
        return self.session_dir

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    
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
                # 使用元组 (score, id) 来避免字典比较问题
                # 负分用于升序排序（高分在前）
                analysis_id = str(analysis.get("id", analysis.get("summary", "")))
                scored.append((-score, analysis_id, analysis))
        
        # 安全排序：使用分数和ID作为排序键
        scored.sort(key=lambda x: (x[0], x[1]))
        return [a for (_, _, a) in scored[:top_k]]
    
    def get_person_profile(self, name: str) -> Optional[PersonProfile]:
        """获取人物画像"""
        return self._person_profiles.get(name)
    
    def update_person_profile(
        self,
        name: str,
        title: str = "",
        team: str = "",
        traits: List[str] = None,
        observed_patterns: List[str] = None,
        risk_signals: List[str] = None,
        evidence_snippet: str = "",
    ):
        """更新人物档案。默认只写入可观察模式，不主动生成人格标签。"""
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
        if observed_patterns:
            for pattern in observed_patterns:
                if pattern not in profile.observed_patterns:
                    profile.observed_patterns.append(pattern)
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
                    observed_patterns=signals,
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

        for pattern in analysis_result.get("org_dynamics_patterns", []):
            kind = pattern.get("kind", "")
            if kind:
                self.record_pattern(
                    pattern_type="org_dynamics_pattern",
                    name=kind,
                    description=pattern.get("summary", kind),
                    example=", ".join(pattern.get("evidence_ids", [])[:3]),
                    confidence=pattern.get("confidence", 0.5),
                )

        if analysis_result.get("org_structure"):
            self.update_org_structure(analysis_result["org_structure"])
        
        # ====== 持续更新关系图谱 ======
        self.update_graph_from_analysis(analysis_result)
        
        # 保存到 DocThinker 的长期记忆
        if self.use_docthinker and self._memory_core:
            await self._save_to_docthinker_memory(analysis_result)

        if not self._loading_from_disk:
            self.persist_memory_folder()
    
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
            
            # 尝试调用 DocThinker 的记忆巩固（兼容性处理）
            try:
                await self._memory_core.after_response(
                    session_id=self.session_id,
                    question="职场关系分析",
                    answer=memory_text,
                )
            except TypeError:
                # 如果上面的调用失败，尝试更简单的方式
                await self._memory_core.after_response(
                    session_id=self.session_id,
                    input="职场关系分析",
                    output=memory_text,
                )
            
            print(f"[WorkplaceThinker] Saved analysis to DocThinker memory")
        except Exception as e:
            print(f"[WorkplaceThinker] Failed to save to DocThinker memory: {e}")
            # DocThinker 集成失败不影响核心功能
    
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
            "org_structure": self.get_org_structure(),
            "similar_scenarios_count": len(self._historical_analyses),
        }
        
        # 人物画像摘要
        for name, profile in list(self._person_profiles.items())[:10]:
            context["person_profiles"][name] = {
                "title": profile.title,
                "team": profile.team,
                "traits": profile.traits[:5],
                "observed_patterns": profile.observed_patterns[:8],
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
            "schema_name": "workplace_memory_export",
            "schema_version": CURRENT_MEMORY_SCHEMA_VERSION,
            "session_id": self.session_id,
            "exported_at": time.time(),
            "person_profiles": {
                name: {
                    "name": p.name,
                    "title": p.title,
                    "team": p.team,
                    "traits": p.traits,
                    "observed_patterns": p.observed_patterns,
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
            "org_structure": self.get_org_structure(),
            "org_structure_versions": self.get_org_structure_versions(),
            # ====== 图谱数据 ======
            "people": self._people,
            "relationships": {
                key: {
                    "source": rel.source,
                    "target": rel.target,
                    "relationship_type": rel.relationship_type,
                    "label": rel.label,
                    "confidence": rel.confidence,
                    "evidence_count": rel.evidence_count,
                    "first_observed_at": rel.first_observed_at,
                    "last_observed_at": rel.last_observed_at,
                    "evidence_snippets": rel.evidence_snippets,
                }
                for key, rel in self._relationships.items()
            },
            "graph_snapshots": [
                {
                    "timestamp": s.timestamp,
                    "nodes": s.nodes,
                    "edges": s.edges,
                    "summary": s.summary,
                }
                for s in self._graph_snapshots
            ],
            "historical_analyses_count": len(self._historical_analyses),
        }
    
    def import_memory(self, data: Dict[str, Any]):
        """从字典导入记忆"""
        data, _migration_report = self._migrator.migrate_memory(data)
        if "person_profiles" in data:
            for name, profile_data in data["person_profiles"].items():
                profile = PersonProfile(
                    name=profile_data["name"],
                    title=profile_data.get("title", ""),
                    team=profile_data.get("team", ""),
                    traits=profile_data.get("traits", []),
                    observed_patterns=profile_data.get("observed_patterns", []),
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

        if "org_structure" in data and isinstance(data["org_structure"], dict):
            self.update_org_structure(data["org_structure"])
        if isinstance(data.get("org_structure_versions"), list):
            self._org_structure_versions = list(data.get("org_structure_versions") or [])[-20:]
        
        # ====== 导入图谱数据 ======
        if "people" in data:
            self._people = data["people"]
        
        if "relationships" in data:
            self._relationships = {}
            for key, rel_data in data["relationships"].items():
                self._relationships[key] = RelationshipEdge(
                    source=rel_data["source"],
                    target=rel_data["target"],
                    relationship_type=rel_data["relationship_type"],
                    label=rel_data["label"],
                    confidence=rel_data.get("confidence", 0.5),
                    evidence_count=rel_data.get("evidence_count", 0),
                    first_observed_at=rel_data.get("first_observed_at", time.time()),
                    last_observed_at=rel_data.get("last_observed_at", time.time()),
                    evidence_snippets=rel_data.get("evidence_snippets", []),
                )
        
        if "graph_snapshots" in data:
            self._graph_snapshots = [
                GraphSnapshot(
                    timestamp=s["timestamp"],
                    nodes=s["nodes"],
                    edges=s["edges"],
                    summary=s.get("summary", ""),
                )
                for s in data["graph_snapshots"]
            ]
        
        if "session_id" in data and not self.session_id:
            self.session_id = data["session_id"]

        if not self._loading_from_disk:
            self.persist_memory_folder()

    def update_org_structure(self, org_structure: Dict[str, Any]) -> Dict[str, Any]:
        """更新 session 级组织架构记忆。"""
        if not isinstance(org_structure, dict):
            return self._org_structure
        self._archive_current_org_structure()
        stored, _migration_report = self._migrator.migrate_org_structure(org_structure)
        stored["updated_at"] = time.time()
        stored.setdefault("departments", [])
        stored.setdefault("people", [])
        stored.setdefault("reporting_lines", [])
        stored.setdefault("department_tree", [])
        stored.setdefault("reporting_tree", [])
        stored.setdefault("summary", {})
        stored.setdefault("storage", {})
        stored["storage"] = {
            **stored.get("storage", {}),
            "scope": "session_memory",
            "status": "stored",
            "editable": True,
        }
        self._org_structure = stored
        if not self._loading_from_disk:
            self.persist_memory_folder()
        return self.get_org_structure()

    def get_org_structure(self) -> Dict[str, Any]:
        """获取当前 session 的组织架构。"""
        migrated, _migration_report = self._migrator.migrate_org_structure(self._org_structure)
        self._org_structure = migrated
        result = dict(self._org_structure)
        result["versions"] = self.get_org_structure_versions()
        return result

    def get_org_structure_versions(self) -> List[Dict[str, Any]]:
        """获取组织架构历史版本，最近的版本排在前面。"""
        return list(reversed(self._org_structure_versions[-20:]))

    def _archive_current_org_structure(self) -> None:
        current = self._org_structure or {}
        if not current.get("people") and not current.get("departments") and not current.get("reporting_lines"):
            return
        snapshot = copy.deepcopy(current)
        snapshot.pop("versions", None)
        self._org_structure_versions.append(
            {
                "version_id": f"org_v{len(self._org_structure_versions) + 1}_{int(time.time())}",
                "archived_at": time.time(),
                "summary": copy.deepcopy(snapshot.get("summary") or {}),
                "org_structure": snapshot,
            }
        )
        self._org_structure_versions = self._org_structure_versions[-20:]

    def preview_memory_migration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """预览旧记忆导入后的新版结构，不写入当前 session。"""
        return self._migrator.preview_memory_migration(data)
    
    # ====== 持续图谱构建 ======
    
    def update_graph_from_analysis(self, analysis_result: Dict[str, Any]):
        """
        从分析结果中增量更新关系图谱
        
        Args:
            analysis_result: analyze() 方法的返回结果
        """
        current_time = time.time()
        
        # 更新人物节点
        for person in analysis_result.get("people", []):
            name = person.get("label", person.get("name", ""))
            if not name:
                continue
            
            if name not in self._people:
                self._people[name] = {
                    "name": name,
                    "title": person.get("title", ""),
                    "team": person.get("team", ""),
                    "first_observed_at": current_time,
                    "last_observed_at": current_time,
                    "observation_count": 0,
                }
            
            # 更新人物信息
            person_data = self._people[name]
            person_data["last_observed_at"] = current_time
            person_data["observation_count"] += 1
            if person.get("title"):
                person_data["title"] = person.get("title")
            if person.get("team"):
                person_data["team"] = person.get("team")
        
        # 更新关系边
        for edge in analysis_result.get("relationships", []):
            source = edge.get("source_name", edge.get("source", ""))
            target = edge.get("target_name", edge.get("target", ""))
            rel_type = edge.get("type", "related_to")
            label = edge.get("label", rel_type)
            confidence = edge.get("score", 0.5)
            
            if not source or not target:
                continue
            
            edge_key = f"{source}|{target}|{rel_type}"
            
            if edge_key not in self._relationships:
                # 新关系
                self._relationships[edge_key] = RelationshipEdge(
                    source=source,
                    target=target,
                    relationship_type=rel_type,
                    label=label,
                    confidence=confidence,
                    first_observed_at=current_time,
                    last_observed_at=current_time,
                )
            else:
                # 更新现有关系
                existing = self._relationships[edge_key]
                existing.last_observed_at = current_time
                existing.evidence_count += 1
                # 置信度更新：取平均，或者增加
                existing.confidence = min(0.95, (existing.confidence + confidence) / 2)
            
            # 添加证据片段
            evidence_snippet = edge.get("evidence_ids", [])
            if evidence_snippet:
                if isinstance(evidence_snippet, list):
                    self._relationships[edge_key].evidence_snippets.extend(
                        [str(s) for s in evidence_snippet]
                    )
                else:
                    self._relationships[edge_key].evidence_snippets.append(str(evidence_snippet))
        
        # 创建图谱快照
        self._create_snapshot(analysis_result.get("summary", ""))
    
    def _create_snapshot(self, summary: str = ""):
        """创建当前图谱的快照，用于时间线视图"""
        # 构建当前图谱
        nodes = []
        for name, person in self._people.items():
            nodes.append({
                "id": name,
                "label": name,
                "type": "person",
                "title": person.get("title", ""),
                "team": person.get("team", ""),
                "first_observed_at": person.get("first_observed_at"),
                "last_observed_at": person.get("last_observed_at"),
            })
        
        edges = []
        for edge_key, rel in self._relationships.items():
            edges.append({
                "id": edge_key,
                "source": rel.source,
                "target": rel.target,
                "type": rel.relationship_type,
                "label": rel.label,
                "confidence": rel.confidence,
                "evidence_count": rel.evidence_count,
                "first_observed_at": rel.first_observed_at,
                "last_observed_at": rel.last_observed_at,
            })
        
        # 保存快照
        snapshot = GraphSnapshot(
            timestamp=time.time(),
            nodes=nodes,
            edges=edges,
            summary=summary,
        )
        self._graph_snapshots.append(snapshot)
        
        # 限制快照数量，保留最近 50 个
        if len(self._graph_snapshots) > 50:
            self._graph_snapshots = self._graph_snapshots[-50:]
    
    def get_current_graph(self) -> Dict[str, Any]:
        """获取当前最新的关系图谱"""
        nodes = []
        for name, person in self._people.items():
            nodes.append({
                "id": name,
                "label": name,
                "type": "person",
                "title": person.get("title", ""),
                "team": person.get("team", ""),
                "first_observed_at": person.get("first_observed_at"),
                "last_observed_at": person.get("last_observed_at"),
            })
        
        edges = []
        for edge_key, rel in self._relationships.items():
            edges.append({
                "id": edge_key,
                "source": rel.source,
                "target": rel.target,
                "type": rel.relationship_type,
                "label": rel.label,
                "confidence": rel.confidence,
                "evidence_count": rel.evidence_count,
                "first_observed_at": rel.first_observed_at,
                "last_observed_at": rel.last_observed_at,
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "people_count": len(nodes),
                "relationships_count": len(edges),
                "snapshots_count": len(self._graph_snapshots),
                "session_id": self.session_id,
            }
        }
    
    def get_graph_timeline(self) -> List[Dict[str, Any]]:
        """获取图谱的时间线演变记录"""
        return [
            {
                "timestamp": snapshot.timestamp,
                "people_count": len(snapshot.nodes),
                "relationships_count": len(snapshot.edges),
                "summary": snapshot.summary,
            }
            for snapshot in self._graph_snapshots
        ]
    
    def get_relationship_history(self, person1: str, person2: str) -> List[Dict[str, Any]]:
        """获取两个人之间的关系演变历史"""
        history = []
        for snapshot in self._graph_snapshots:
            # 查找这两个人之间的关系
            rels = [
                e for e in snapshot.edges
                if (e.get("source") == person1 and e.get("target") == person2) or
                   (e.get("source") == person2 and e.get("target") == person1)
            ]
            if rels:
                history.append({
                    "timestamp": snapshot.timestamp,
                    "relationships": rels,
                })
        return history

    def record_user_feedback(self, feedback: Dict[str, Any]) -> str:
        """
        记录用户反馈：
        - 对不确定性检查清单的选择
        - 对多重假设的选择
        - 用户自定义的理解
        
        Args:
            feedback: {
                "analysis_id": "上次分析的ID",
                "item_type": "relationship|risk|hypothesis|interpretation",
                "item_id": "项目ID",
                "action": "confirm|reject|pending|accept|alternative|monitor",
                "user_note": "用户备注（可选）",
                "custom_hypothesis": "用户自定义假设（可选）"
            }
        
        Returns:
            反馈记录ID
        """
        feedback_id = f"feedback_{int(time.time())}"
        feedback_record = {
            "id": feedback_id,
            "timestamp": time.time(),
            **feedback
        }
        self._feedback_history.append(feedback_record)
        
        # 根据反馈更新记忆
        item_type = feedback.get("item_type", "")
        action = feedback.get("action", "")
        
        if item_type == "risk" and action == "confirm":
            # 用户确认风险，记录为模式
            self.record_pattern(
                pattern_type="user_confirmed_risk",
                name=feedback.get("item_id", ""),
                description="用户确认的风险信号",
                example=feedback.get("user_note", ""),
                confidence=0.95
            )
        elif item_type == "interpretation" and action == "accept":
            # 用户接受某个解释，记录为模式
            self.record_pattern(
                pattern_type="user_interpretation",
                name=feedback.get("item_id", ""),
                description="用户选择的解释角度",
                example=feedback.get("user_note", ""),
                confidence=0.85
            )

        if not self._loading_from_disk:
            self.persist_memory_folder()
        
        return feedback_id

    def get_user_feedback_history(self) -> List[Dict[str, Any]]:
        """获取用户反馈历史"""
        return list(self._feedback_history)
    
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
            "memory_root": str(self.memory_root),
            "memory_package_dir": str(self.session_dir),
            # 图谱相关统计
            "people_count": len(self._people),
            "relationships_count": len(self._relationships),
            "snapshots_count": len(self._graph_snapshots),
            "org_department_count": len(self._org_structure.get("departments", [])),
            "org_person_count": len(self._org_structure.get("people", [])),
            "org_reporting_line_count": len(self._org_structure.get("reporting_lines", [])),
        }

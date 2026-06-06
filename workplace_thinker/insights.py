"""LLM-assisted workplace relationship and hidden-risk intelligence.

The core design is evidence-first:
- deterministic extraction produces a stable graph even without an LLM;
- optional LLM reasoning can enrich labels, hidden hypotheses, and advice;
- every risk/hypothesis must point back to evidence ids;
- hypotheses are explicitly separated from observed facts.

Enhanced with Agentic Memory System:
- Recalls similar historical scenarios for context
- Builds and updates person profiles over time
- Recognizes recurring risk patterns
- Learns from user feedback to improve accuracy
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence

try:
    from .memory_engine import WorkplaceMemoryEngine
    HAS_MEMORY_ENGINE = True
except ImportError:
    HAS_MEMORY_ENGINE = False

from .knowledge_injection import (
    build_knowledge_context,
    build_prompt_section,
    infer_behavior_observations,
    match_jargon_terms,
    match_work_objects,
    match_work_relations,
)


LLMFunc = Callable[[str], Awaitable[str]]


RISK_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "ownership_ambiguity": {
        "label": "责任边界不清",
        "keywords": ["没人负责", "职责不清", "owner", "负责人", "口头", "没写清", "边界", "甩锅", "背锅"],
        "severity": 0.76,
        "advice": "把 owner、交付物、截止时间、依赖项、验收标准写下来。",
    },
    "information_asymmetry": {
        "label": "信息不对称",
        "keywords": ["私下", "背后", "没同步", "没告诉", "隐瞒", "只告诉", "单独找", "信息不透明"],
        "severity": 0.72,
        "advice": "把关键结论同步到共同频道，确认哪些人需要被纳入信息流。",
    },
    "process_bypass": {
        "label": "流程绕过",
        "keywords": ["不走流程", "绕过", "先做", "后补", "跳过", "不用审批", "别写邮件", "别留痕"],
        "severity": 0.84,
        "advice": "要求最小可审计记录，确认授权人和例外条件。",
    },
    "credit_blame": {
        "label": "功劳 / 责任归属风险",
        "keywords": ["抢功", "功劳", "credit", "blame", "甩锅", "背锅", "算你的", "不是我"],
        "severity": 0.82,
        "advice": "阶段性同步贡献、阻塞和待确认事项，保留过程记录。",
    },
    "power_pressure": {
        "label": "权力压力",
        "keywords": ["必须", "不然", "威胁", "暗示", "绩效", "KPI", "影响评价", "压力"],
        "severity": 0.68,
        "advice": "把压力话术转成具体优先级、资源条件和 trade-off。",
    },
    "stance_volatility": {
        "label": "立场反复",
        "keywords": ["改口", "反复", "突然变", "否认之前", "之前说", "现在又", "临时变更"],
        "severity": 0.7,
        "advice": "对变更点做简短复盘，确认新版本覆盖旧版本。",
    },
}


RELATION_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "reports_to": {"label": "汇报 / 管理", "keywords": ["汇报", "领导", "老板", "manager", "审批", "安排"], "weight": 0.55},
    "collaborates_with": {"label": "合作", "keywords": ["合作", "协作", "一起", "共同", "配合", "对接", "推进"], "weight": 0.52},
    "supports": {"label": "支持", "keywords": ["支持", "帮助", "协助", "提醒", "兜底", "help", "support"], "weight": 0.48},
    "blocks_or_challenges": {"label": "阻塞 / 质疑", "keywords": ["反对", "质疑", "不配合", "卡", "阻塞", "冲突", "否认"], "weight": 0.76},
    "commits_to": {"label": "承诺 / 交付", "keywords": ["承诺", "答应", "保证", "负责", "交付", "deadline"], "weight": 0.5},
}


CN_NAME_RE = re.compile(r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,4})(?=(说|表示|认为|负责|推进|支持|反对|提醒|要求|汇报|承诺|答应|私下|和|与|跟|，|。|：|:|\s))")
EN_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")
SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
NAME_TEMPORAL_SUFFIXES = ("之前", "现在", "后来", "刚才")
NAME_FALSE_POSITIVE_TOKENS = (
    "周一", "周二", "周三", "周四", "周五", "周六", "周日",
    "今天", "明天", "昨天", "上线", "验收", "审批", "需求", "方案",
    "文档", "口径", "卡点", "流程", "项目", "任务",
)


@dataclass
class Evidence:
    id: str
    text: str
    source: str
    kind: str = "text"


@dataclass
class OrgPerson:
    name: str
    title: str = ""
    team: str = ""
    manager: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{sha1(value.encode('utf-8')).hexdigest()[:10]}"


def split_evidence(text: str, source: str) -> List[Evidence]:
    parts = [p.strip() for p in SENTENCE_RE.split(text or "") if p and p.strip()]
    if not parts and text.strip():
        parts = [text.strip()]
    return [Evidence(id=stable_id("ev", f"{source}:{i}:{p}"), text=p, source=source) for i, p in enumerate(parts)]


def extract_people(text: str, org_names: Sequence[str] = ()) -> List[str]:
    names: List[str] = []

    def add_name(raw_name: str) -> None:
        name = raw_name.strip()
        for suffix in NAME_TEMPORAL_SUFFIXES:
            if len(name) > 2 and name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if any(token in name for token in NAME_FALSE_POSITIVE_TOKENS):
            return
        if name and name not in {"但是", "因为", "所以", "然后", "如果", "这个", "那个"} and name not in names:
            names.append(name)

    for name in org_names:
        if name and name in text and name not in names:
            names.append(name)
    for match in CN_NAME_RE.finditer(text):
        add_name(match.group(1))
    for match in EN_NAME_RE.finditer(text):
        add_name(match.group(1))
    return names[:10]


def contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in keywords)


def json_object_from_text(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if fenced:
        raw = fenced.group(1)
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


class WorkplaceInsightEngine:
    """Generate relationship/risk graph from chat, uploads, and org structure.
    
    Enhanced with memory capabilities:
    - Recalls similar historical scenarios
    - Builds person profiles over time
    - Recognizes recurring patterns
    """

    def __init__(
        self, 
        llm_func: Optional[LLMFunc] = None,
        memory_engine: Optional[WorkplaceMemoryEngine] = None,
        session_id: Optional[str] = None,
        enable_memory: bool = True,
    ):
        self.llm_func = llm_func
        self.enable_memory = enable_memory and HAS_MEMORY_ENGINE
        
        if self.enable_memory:
            self.memory = memory_engine or WorkplaceMemoryEngine(session_id=session_id)
        else:
            self.memory = None

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
        org_people = [OrgPerson(**{k: v for k, v in item.items() if k in {"name", "title", "team", "manager", "metadata"}}) for item in org_chart if item.get("name")]
        org_names = [p.name for p in org_people]
        evidence = self._collect_evidence(chat_messages, uploaded_texts)
        
        # 获取记忆上下文
        memory_context = None
        similar_scenarios = []
        if self.enable_memory and use_memory and self.memory:
            memory_context = self.memory.get_memory_context(question)
            similar_scenarios = await self.memory.recall_similar_scenarios(
                query=question,
                people=org_names,
                risk_types=list(RISK_TAXONOMY.keys()),
            )
        
        # 执行确定性分析
        deterministic = self._deterministic_graph(
            evidence, 
            org_people, 
            org_names, 
            question=question,
            memory_context=memory_context,
            similar_scenarios=similar_scenarios,
        )
        
        # LLM 增强（包含记忆上下文）
        if use_llm and self.llm_func and evidence:
            enriched = await self._llm_enrich(
            deterministic, 
            evidence, 
            org_people, 
            question,
            memory_context=memory_context,
            similar_scenarios=similar_scenarios,
        )
            if enriched:
                result = self._merge_llm_result(deterministic, enriched)
            else:
                result = deterministic
        else:
            result = deterministic
        
        # 保存到记忆
        if self.enable_memory and save_to_memory and self.memory:
            await self.memory.record_analysis(result)
        
        return result

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
        """Analyze a single user-provided information bundle.

        This is the product-friendly path: users can paste chat fragments,
        meeting notes, org chart lines, and their question into one box.
        """
        parsed = self.parse_information(information, question=question)
        merged_org = list(org_chart or []) or parsed["org_chart"]
        result = await self.analyze(
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
        return result

    def parse_information(self, information: str, *, question: str = "") -> Dict[str, Any]:
        raw = str(information or "").strip()
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        org_chart: List[Dict[str, Any]] = []
        content_lines: List[str] = []
        inferred_question = question.strip()

        for line in lines:
            if not inferred_question and ("?" in line or "？" in line) and len(line) <= 80:
                inferred_question = line
                continue
            org_item = self._parse_org_line(line)
            if org_item:
                org_chart.append(org_item)
            else:
                content_lines.append(line)

        if not content_lines and raw:
            content_lines = [raw]

        return {
            "question": inferred_question,
            "chat_messages": [{"role": "user", "content": "\n".join(content_lines)}] if content_lines else [],
            "uploaded_texts": [],
            "org_chart": self._dedupe_org_chart(org_chart),
        }

    def _parse_org_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not any(token in line for token in ("组织", "架构", "汇报", "上级", "manager", "Manager", "团队", "team", "Team", "title", "岗位", "角色", "负责人", "reports to", "Reports to")):
            return None
        body = re.sub(r"^\s*(?:组织架构|组织|人员|成员|org\s*chart|org)[:：]?\s*", "", line, flags=re.I).strip()
        if not body:
            return None
        parts = [p.strip() for p in re.split(r"[-—|,，;；]", body) if p.strip()]
        name = ""
        if parts:
            first = parts[0]
            direct = re.match(r"([\u4e00-\u9fff]{2,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", first)
            if direct:
                name = direct.group(1)
        if not name:
            names = extract_people(body)
            # 过滤掉常见的非人名误判
            names = [n for n in names if n not in ("组织架构", "组织", "架构", "人员", "团队")]
            name = names[0] if names else ""
        if not name or name in ("组织架构", "组织", "架构", "人员", "团队"):
            return None
        manager = ""
        manager_match = re.search(r"(?:汇报(?:给|到)?|上级[:：=]?|manager[:：=]?|reports\s*to[:：=]?)\s*([\u4e00-\u9fff]{2,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", line, flags=re.I)
        if manager_match:
            manager = manager_match.group(1)
        elif "汇报" in line or "上级" in line or "manager" in line.lower() or "reports to" in line.lower():
            names = [n for n in extract_people(body) if n != name]
            manager = names[0] if names else ""

        title = ""
        title_match = re.search(r"(?:岗位|职位|角色|title)[:：=]?\s*([^,，;；|]+)", line, flags=re.I)
        if title_match:
            title = title_match.group(1).strip()
        elif any(sep in line for sep in ("-", "—", "|", "，", ",")):
            for part in parts:
                if name not in part and not any(k in part for k in ("汇报", "上级", "manager", "reports to", "团队", "team", "组织", "架构")):
                    title = part
                    break

        team = ""
        for part in parts:
            if "团队" in part or "team" in part.lower():
                candidate = re.sub(r"(?i)团队|team", "", part).strip(" ：:=_-—")
                if candidate and name not in candidate:
                    team = candidate
                    break
        if not team:
            team_match = re.search(r"(?:团队|team)[:：=]\s*([^,，;；|\\-—]+)", line, flags=re.I)
            if team_match:
                team = team_match.group(1).strip()
        return {"name": name, "title": title, "team": team, "manager": manager}

    def _dedupe_org_chart(self, org_chart: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for item in org_chart:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            existing = merged.setdefault(name, {"name": name, "title": "", "team": "", "manager": ""})
            for key in ("title", "team", "manager"):
                value = str(item.get(key) or "").strip()
                if value and not existing.get(key):
                    existing[key] = value
        return list(merged.values())

    def _collect_evidence(self, chat_messages: Sequence[Dict[str, Any]], uploaded_texts: Sequence[Dict[str, str]]) -> List[Evidence]:
        evidence: List[Evidence] = []
        for idx, msg in enumerate(chat_messages):
            role = str(msg.get("role") or "unknown")
            content = str(msg.get("content") or "").strip()
            if content:
                evidence.extend(split_evidence(f"{role}: {content}", f"chat_{idx + 1}"))
        for idx, item in enumerate(uploaded_texts):
            source = str(item.get("source") or f"upload_{idx + 1}")
            text = str(item.get("text") or "").strip()
            if text:
                evidence.extend(split_evidence(text, source))
        return evidence[:120]

    def _deterministic_graph(
        self,
        evidence: Sequence[Evidence],
        org_people: Sequence[OrgPerson],
        org_names: Sequence[str],
        *,
        question: str,
        memory_context: Optional[Dict[str, Any]] = None,
        similar_scenarios: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        people_mentions: Counter = Counter()
        people_evidence: Dict[str, List[str]] = defaultdict(list)
        people_signals: Dict[str, Counter] = defaultdict(Counter)
        edge_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        risks: List[Dict[str, Any]] = []
        risk_counts: Counter = Counter()
        work_item_map: Dict[str, Dict[str, Any]] = {}
        work_edge_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        jargon_signal_map: Dict[tuple[str, str], Dict[str, Any]] = {}

        for item in evidence:
            names = extract_people(item.text, org_names)
            relation_types = [kind for kind, rule in RELATION_TAXONOMY.items() if contains_any(item.text, rule["keywords"])]
            work_matches = match_work_objects(item.text)
            work_relations = match_work_relations(item.text)
            jargon_matches = match_jargon_terms(item.text)
            for name in names:
                people_mentions[name] += 1
                people_evidence[name].append(item.id)
                for kind in relation_types:
                    people_signals[name][kind] += 1

            if len(names) >= 2:
                for kind in relation_types or ["co_mentioned"]:
                    src, tgt = names[0], names[1]
                    rule = RELATION_TAXONOMY.get(kind, {"label": "共同出现", "weight": 0.3})
                    key = (src, tgt, kind)
                    edge = edge_map.setdefault(
                        key,
                        {
                            "id": stable_id("edge", "|".join(key)),
                            "source": stable_id("person", src),
                            "target": stable_id("person", tgt),
                            "source_name": src,
                            "target_name": tgt,
                            "type": kind,
                            "label": rule["label"],
                            "score": 0.0,
                            "evidence_ids": [],
                        },
                    )
                    edge["score"] = min(1.0, float(edge["score"]) + float(rule["weight"]))
                    edge["evidence_ids"].append(item.id)

            for match in work_matches:
                work_key = f"{match['category']}:{item.id}"
                work_node = work_item_map.setdefault(
                    work_key,
                    {
                        "id": stable_id("work", work_key),
                        "label": match["label"],
                        "type": "work_object",
                        "category": match["category"],
                        "description": match["description"],
                        "evidence_ids": [],
                    },
                )
                work_node["evidence_ids"].append(item.id)

                for name in names[:4]:
                    for relation in work_relations or [{"type": "mentions_work", "label": "涉及工作", "description": "人物与工作对象共同出现。"}]:
                        edge_key = (name, work_node["id"], relation["type"])
                        work_edge = work_edge_map.setdefault(
                            edge_key,
                            {
                                "id": stable_id("work_edge", "|".join(edge_key)),
                                "source": stable_id("person", name),
                                "target": work_node["id"],
                                "source_name": name,
                                "target_name": work_node["label"],
                                "type": relation["type"],
                                "label": relation["label"],
                                "description": relation["description"],
                                "score": 0.46,
                                "evidence_ids": [],
                            },
                        )
                        work_edge["score"] = min(1.0, float(work_edge["score"]) + 0.12)
                        work_edge["evidence_ids"].append(item.id)

            for match in jargon_matches:
                jargon_key = (match["category"], item.id)
                signal = jargon_signal_map.setdefault(
                    jargon_key,
                    {
                        "id": stable_id("jargon", "|".join(jargon_key)),
                        "category": match["category"],
                        "label": match["label"],
                        "terms": [],
                        "maps_to": match["maps_to"],
                        "interpretation": match["interpretation"],
                        "safe_question": match["safe_question"],
                        "people": names,
                        "evidence_ids": [],
                        "status": "workplace_semantic_signal",
                    },
                )
                signal["terms"] = list(dict.fromkeys(signal["terms"] + match["terms"]))
                signal["evidence_ids"].append(item.id)

            for category, rule in RISK_TAXONOMY.items():
                if not contains_any(item.text, rule["keywords"]):
                    continue
                risk_counts[category] += 1
                risks.append(
                    {
                        "id": stable_id("risk", f"{category}:{item.id}"),
                        "category": category,
                        "title": rule["label"],
                        "severity": rule["severity"],
                        "confidence": min(0.95, 0.48 + 0.12 * risk_counts[category]),
                        "people": names,
                        "evidence_ids": [item.id],
                        "evidence_text": item.text,
                        "suggestion": rule["advice"],
                        "status": "evidence_signal",
                    }
                )

        for person in org_people:
            people_mentions.setdefault(person.name, 0)

        nodes = []
        org_by_name = {p.name: p for p in org_people}
        for name, mentions in people_mentions.most_common():
            org = org_by_name.get(name)
            nodes.append(
                {
                    "id": stable_id("person", name),
                    "label": name,
                    "type": "person",
                    "title": org.title if org else "",
                    "team": org.team if org else "",
                    "manager": org.manager if org else "",
                    "mentions": mentions,
                    "signals": dict(people_signals[name]),
                    "evidence_ids": list(dict.fromkeys(people_evidence[name]))[:8],
                }
            )

        # Add formal org-chart reporting edges so users can compare official vs observed networks.
        for person in org_people:
            if person.manager:
                key = (person.name, person.manager, "formal_reports_to")
                edge_map.setdefault(
                    key,
                    {
                        "id": stable_id("edge", "|".join(key)),
                        "source": stable_id("person", person.name),
                        "target": stable_id("person", person.manager),
                        "source_name": person.name,
                        "target_name": person.manager,
                        "type": "formal_reports_to",
                        "label": "组织架构汇报",
                        "score": 0.5,
                        "evidence_ids": [],
                    },
                )

        edges = sorted(edge_map.values(), key=lambda e: (-float(e["score"]), e["label"]))[:50]
        work_items = sorted(work_item_map.values(), key=lambda n: (n["category"], n["id"]))[:40]
        work_relationships = sorted(work_edge_map.values(), key=lambda e: (-float(e["score"]), e["label"]))[:80]
        jargon_signals = sorted(jargon_signal_map.values(), key=lambda s: (s["category"], s["id"]))[:40]
        risks = sorted(risks, key=lambda r: (-float(r["severity"]), -float(r["confidence"])))[:20]
        hypotheses = self._build_hypotheses(risk_counts, edges, risks)
        person_nodes = nodes
        augmented_graph = self._augment_graph(person_nodes, edges, risks, hypotheses, work_items, work_relationships)
        # 构建记忆增强的摘要（如果有记忆）
        summary = self._summary(nodes, edges, risks, hypotheses, question, similar_scenarios)
        
        # 检测低置信度项目，生成检查清单
        uncertainty_checklist = self._generate_uncertainty_checklist(edges, risks, hypotheses)
        # 生成多重假设分析
        multiple_hypotheses = self._generate_multiple_hypotheses(evidence, edges, risks, question)
        
        # Add behavioral styles
        from .conversation_engine import detect_behavioral_style
        for p_node in person_nodes:
            p_node["behavioral_style"] = detect_behavioral_style(p_node["label"], risks, edges)
        behavior_observations = infer_behavior_observations(person_nodes, edges, risks)
        knowledge_context = build_knowledge_context(risks, work_items, behavior_observations, jargon_signals)
        
        # P0 改进 1: 结果分级
        prioritized = self._prioritize_results(risks, hypotheses, [])
        # P0 改进 2: 行动建议（具体话术）
        action_scripts = self._generate_action_scripts(risks, top_n=3)
        # P0 改进 3: 时序分析
        temporal_analysis = self._analyze_temporal_patterns(risks, hypotheses)
        
        result = {
            "summary": summary,
            "graph": augmented_graph,
            "people": person_nodes,
            "relationships": edges,
            "work_graph": {
                "nodes": work_items,
                "edges": work_relationships,
                "summary": {
                    "work_object_count": len(work_items),
                    "work_relationship_count": len(work_relationships),
                },
            },
            "risks": risks,
            "hidden_hypotheses": hypotheses,
            "behavior_observations": behavior_observations,
            "jargon_signals": jargon_signals,
            "knowledge_context": knowledge_context,
            "recommended_questions": self._recommended_questions(risk_counts, risks),
            "evidence": [item.__dict__ for item in evidence],
            "uncertainty_checklist": uncertainty_checklist,
            "multiple_hypotheses": multiple_hypotheses,
            # P0 新增字段
            "prioritized_results": prioritized,
            "action_scripts": action_scripts,
            "temporal_analysis": temporal_analysis,
            "meta": {
                "method": "rules_plus_optional_llm",
                "llm_used": False,
                "evidence_count": len(evidence),
                "org_people_count": len(org_people),
                "memory_used": memory_context is not None,
                "uncertainty_count": len(uncertainty_checklist),
                "work_object_count": len(work_items),
                "behavior_observation_count": len(behavior_observations),
                "jargon_signal_count": len(jargon_signals),
                "knowledge_frame_count": len(knowledge_context.get("active_frames", [])),
            },
        }
        
        # 添加记忆相关信息
        if memory_context:
            result["memory_context"] = memory_context
        if similar_scenarios:
            result["similar_scenarios"] = [
                {
                    "summary": s.get("summary", ""),
                    "timestamp": s.get("timestamp"),
                    "id": s.get("id"),
                }
                for s in similar_scenarios[:3]
            ]
        
        return result

    def _augment_graph(
        self,
        people_nodes: Sequence[Dict[str, Any]],
        relation_edges: Sequence[Dict[str, Any]],
        risks: Sequence[Dict[str, Any]],
        hypotheses: Sequence[Dict[str, Any]],
        work_nodes: Sequence[Dict[str, Any]] = (),
        work_edges: Sequence[Dict[str, Any]] = (),
    ) -> Dict[str, List[Dict[str, Any]]]:
        nodes = [dict(node) for node in people_nodes] + [dict(node) for node in work_nodes]
        edges = [dict(edge) for edge in relation_edges] + [dict(edge) for edge in work_edges]
        person_by_name = {str(node.get("label")): str(node.get("id")) for node in people_nodes}

        risk_nodes: List[Dict[str, Any]] = []
        for risk in risks:
            risk_id = str(risk.get("id") or stable_id("risk", str(risk)))
            risk_nodes.append(
                {
                    "id": risk_id,
                    "label": risk.get("title") or risk.get("category") or "风险信号",
                    "type": "risk_signal",
                    "category": risk.get("category"),
                    "severity": risk.get("severity", 0),
                    "confidence": risk.get("confidence", 0),
                    "evidence_ids": risk.get("evidence_ids", []),
                }
            )
            linked = False
            for person in risk.get("people", []) or []:
                person_id = person_by_name.get(str(person))
                if not person_id:
                    continue
                linked = True
                edges.append(
                    {
                        "id": stable_id("edge", f"{person_id}:{risk_id}:mentions_risk"),
                        "source": person_id,
                        "target": risk_id,
                        "type": "mentions_risk",
                        "label": "涉及风险",
                        "score": risk.get("confidence", 0.5),
                        "risk": True,
                        "evidence_ids": risk.get("evidence_ids", []),
                    }
                )
            if not linked and people_nodes:
                edges.append(
                    {
                        "id": stable_id("edge", f"{people_nodes[0]['id']}:{risk_id}:case_risk"),
                        "source": str(people_nodes[0]["id"]),
                        "target": risk_id,
                        "type": "case_risk",
                        "label": "场景风险",
                        "score": risk.get("confidence", 0.4),
                        "risk": True,
                        "evidence_ids": risk.get("evidence_ids", []),
                    }
                )

        risk_by_evidence: Dict[str, List[str]] = defaultdict(list)
        for risk in risks:
            for ev in risk.get("evidence_ids", []) or []:
                risk_by_evidence[str(ev)].append(str(risk.get("id")))

        hyp_nodes: List[Dict[str, Any]] = []
        for hyp in hypotheses:
            hyp_id = str(hyp.get("id") or stable_id("hyp", str(hyp)))
            hyp_nodes.append(
                {
                    "id": hyp_id,
                    "label": hyp.get("title") or "隐藏假设",
                    "type": "hidden_hypothesis",
                    "confidence": hyp.get("confidence", 0),
                    "status": hyp.get("status", "hypothesis_not_fact"),
                    "evidence_ids": hyp.get("evidence_ids", []),
                }
            )
            linked_risks: List[str] = []
            for ev in hyp.get("evidence_ids", []) or []:
                linked_risks.extend(risk_by_evidence.get(str(ev), []))
            for risk_id in list(dict.fromkeys(linked_risks))[:4]:
                if not risk_id:
                    continue
                edges.append(
                    {
                        "id": stable_id("edge", f"{risk_id}:{hyp_id}:supports_hypothesis"),
                        "source": risk_id,
                        "target": hyp_id,
                        "type": "supports_hypothesis",
                        "label": "支持假设",
                        "score": hyp.get("confidence", 0.5),
                        "hypothesis": True,
                        "evidence_ids": hyp.get("evidence_ids", []),
                    }
                )

        return {"nodes": nodes + risk_nodes + hyp_nodes, "edges": edges}

    def _build_hypotheses(self, risk_counts: Counter, edges: Sequence[Dict[str, Any]], risks: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hypotheses: List[Dict[str, Any]] = []

        def add(title: str, rationale: str, cats: Sequence[str], base: float) -> None:
            evidence_ids: List[str] = []
            for risk in risks:
                if risk.get("category") in cats:
                    evidence_ids.extend(risk.get("evidence_ids", []))
            hypotheses.append(
                {
                    "id": stable_id("hyp", title + rationale),
                    "title": title,
                    "rationale": rationale,
                    "confidence": min(0.9, base + 0.08 * sum(risk_counts[c] for c in cats)),
                    "evidence_ids": list(dict.fromkeys(evidence_ids))[:6],
                    "status": "hypothesis_not_fact",
                }
            )

        if risk_counts["information_asymmetry"] and risk_counts["process_bypass"]:
            add("可能存在非正式决策链", "私下沟通和绕过流程同时出现，关键决策可能没有进入公开渠道。", ["information_asymmetry", "process_bypass"], 0.5)
        if risk_counts["ownership_ambiguity"] and risk_counts["credit_blame"]:
            add("可能存在背锅风险", "责任边界不清叠加功劳/责任归属信号，新人容易承担未被明确授权的结果。", ["ownership_ambiguity", "credit_blame"], 0.55)
        if any(e.get("type") == "blocks_or_challenges" for e in edges) and risk_counts["stance_volatility"]:
            add("关系稳定性需要观察", "摩擦关系和立场反复同时出现，后续协作需要更多书面确认。", ["stance_volatility"], 0.45)
        if risk_counts["power_pressure"] and risk_counts["process_bypass"]:
            add("可能存在被动承诺风险", "压力话术叠加流程绕过，容易让执行者在没有资源和授权时先承担承诺。", ["power_pressure", "process_bypass"], 0.52)
        return sorted(hypotheses, key=lambda h: -h["confidence"])[:8]

    def _generate_uncertainty_checklist(
        self,
        edges: Sequence[Dict[str, Any]],
        risks: Sequence[Dict[str, Any]],
        hypotheses: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        生成不确定性检查清单：
        - 检测低置信度的关系、风险、假设
        - 整理成清晰的列表给用户确认
        - 每种情况包含：类型、描述、置信度、证据、建议选项
        """
        checklist: List[Dict[str, Any]] = []
        confidence_threshold = 0.65
        
        # 检查低置信度的关系
        for edge in edges:
            score = float(edge.get("score", 0))
            if score < confidence_threshold and edge.get("type") != "formal_reports_to":
                checklist.append({
                    "id": edge.get("id"),
                    "type": "relationship",
                    "description": f"{edge.get('source_name', '')} 和 {edge.get('target_name', '')} 的关系：{edge.get('label', '')}",
                    "confidence": score,
                    "evidence_ids": edge.get("evidence_ids", []),
                    "options": [
                        {
                            "id": "confirm",
                            "label": "确认这个关系",
                            "suggestion": "如果确认无误，可以标记为已确认，提升置信度"
                        },
                        {
                            "id": "reject",
                            "label": "否定这个关系",
                            "suggestion": "如果这个关系不对，可以标记为否定"
                        },
                        {
                            "id": "pending",
                            "label": "先记录，后续确认",
                            "suggestion": "暂时标记为待确认，继续观察更多证据"
                        },
                    ]
                })
        
        # 检查低置信度的风险
        for risk in risks:
            confidence = float(risk.get("confidence", 0))
            if confidence < confidence_threshold:
                checklist.append({
                    "id": risk.get("id"),
                    "type": "risk",
                    "description": f"风险：{risk.get('title', '')}",
                    "confidence": confidence,
                    "evidence_ids": risk.get("evidence_ids", []),
                    "evidence_text": risk.get("evidence_text", ""),
                    "options": [
                        {
                            "id": "confirm",
                            "label": "确认存在这个风险",
                            "suggestion": "如果确实存在这个风险，可以标记并记录观察"
                        },
                        {
                            "id": "reject",
                            "label": "这个风险不适用",
                            "suggestion": "如果这个风险不适用当前情况，可以标记为排除"
                        },
                        {
                            "id": "monitor",
                            "label": "持续观察",
                            "suggestion": "先记录下来，后续看是否有更多证据支持"
                        },
                    ]
                })
        
        # 检查低置信度的假设
        for hyp in hypotheses:
            confidence = float(hyp.get("confidence", 0))
            if confidence < confidence_threshold:
                checklist.append({
                    "id": hyp.get("id"),
                    "type": "hypothesis",
                    "description": f"假设：{hyp.get('title', '')}",
                    "confidence": confidence,
                    "rationale": hyp.get("rationale", ""),
                    "evidence_ids": hyp.get("evidence_ids", []),
                    "options": [
                        {
                            "id": "accept",
                            "label": "接受这个假设",
                            "suggestion": "如果认为这个假设合理，可以标记为参考假设"
                        },
                        {
                            "id": "reject",
                            "label": "排除这个假设",
                            "suggestion": "如果认为这个假设不成立，可以标记为排除"
                        },
                        {
                            "id": "alternative",
                            "label": "我有其他理解",
                            "suggestion": "可以添加自己的理解或假设"
                        },
                    ]
                })
        
        return checklist[:15]  # 最多显示15个不确定性项目

    def _prioritize_results(
        self,
        risks: Sequence[Dict[str, Any]],
        hypotheses: Sequence[Dict[str, Any]],
        questions: Sequence[str],
    ) -> Dict[str, Any]:
        """
        P0 改进: 结果分级
        按紧急度/重要度排序，避免信息过载
        """
        from .conversation_engine import prioritize_results
        return prioritize_results(risks, hypotheses, questions)

    def _generate_action_scripts(
        self,
        risks: Sequence[Dict[str, Any]],
        top_n: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        P0 改进: 行动建议模板
        为高优先级风险生成具体话术
        """
        from .conversation_engine import generate_action_scripts
        return generate_action_scripts(risks, top_n)

    def _analyze_temporal_patterns(
        self,
        risks: Sequence[Dict[str, Any]],
        hypotheses: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        P0 改进: 时序分析
        识别反复出现的风险模式、立场变化、升级趋势
        """
        from .conversation_engine import analyze_temporal_patterns
        # 简化版：基于当前分析中的时序信号
        current_analysis = {
            "risks": risks,
            "hypotheses": hypotheses,
            "timestamp": __import__('time').time(),
        }
        # 从 memory 中获取历史
        historical_analyses = []
        if self.memory and hasattr(self.memory, '_historical_analyses'):
            historical_analyses = list(self.memory._historical_analyses)
        return analyze_temporal_patterns(historical_analyses, current_analysis)

    def _generate_multiple_hypotheses(
        self,
        evidence: Sequence[Evidence],
        edges: Sequence[Dict[str, Any]],
        risks: Sequence[Dict[str, Any]],
        question: str,
    ) -> List[Dict[str, Any]]:
        """
        生成多重假设分析：
        - 对同一情况给出几种可能的解释
        - 每种解释都有支持的证据和置信度
        - 用户可以选择最符合情况的解释
        """
        hypotheses_list: List[Dict[str, Any]] = []
        
        # 基于风险组合生成几种可能的解释
        risk_categories = [r.get("category") for r in risks]
        risk_texts = [r.get("evidence_text", "") for r in risks]
        
        # 假设1：最直接的解释
        if "process_bypass" in risk_categories or "ownership_ambiguity" in risk_categories:
            hypotheses_list.append({
                "id": "interpretation_direct",
                "title": "解释A：可能是流程不规范",
                "description": "可能是团队流程还在完善中，或者有临时的特殊安排",
                "confidence": 0.6,
                "supporting_evidence": [r.get("id") for r in risks if r.get("category") in ["process_bypass", "ownership_ambiguity"]][:3],
                "recommendation": "建议通过书面确认明确流程和责任边界",
                "tone": "neutral",
            })
        
        # 假设2：更谨慎的解释
        if "information_asymmetry" in risk_categories or "credit_blame" in risk_categories:
            hypotheses_list.append({
                "id": "interpretation_cautious",
                "title": "解释B：可能存在信息差",
                "description": "可能有些决策是在小范围做出的，需要更多背景信息才能完全理解",
                "confidence": 0.5,
                "supporting_evidence": [r.get("id") for r in risks if r.get("category") in ["information_asymmetry", "credit_blame"]][:3],
                "recommendation": "建议通过提问填补信息空白，不要假设自己完全理解",
                "tone": "cautious",
            })
        
        # 假设3：人际关系角度
        if any(e.get("type") in ["supports", "blocks_or_challenges"] for e in edges):
            hypotheses_list.append({
                "id": "interpretation_relationship",
                "title": "解释C：可能涉及人际协作模式",
                "description": "可能反映了团队中特定的协作方式或人际互动模式",
                "confidence": 0.45,
                "supporting_evidence": [e.get("id") for e in edges if e.get("type") in ["supports", "blocks_or_challenges"]][:3],
                "recommendation": "建议观察更多互动再下结论，保持开放态度",
                "tone": "observational",
            })
        
        # 如果没有生成任何假设，提供一个通用的
        if not hypotheses_list:
            hypotheses_list.append({
                "id": "interpretation_general",
                "title": "需要更多信息才能判断",
                "description": "当前信息还不足以形成明确判断，建议继续观察",
                "confidence": 0.3,
                "supporting_evidence": [],
                "recommendation": "建议记录观察，后续收集更多信息再分析",
                "tone": "neutral",
            })
        
        return hypotheses_list

    def _recommended_questions(self, risk_counts: Counter, risks: Sequence[Dict[str, Any]]) -> List[str]:
        questions = [
            "这件事最终 owner 是谁？验收标准和截止时间是什么？",
            "哪些人需要同步？我理解的结论可以发到群里确认吗？",
            "如果优先级变化，需要牺牲哪些任务或资源？",
        ]
        if risk_counts["process_bypass"]:
            questions.insert(0, "这次例外是否有明确授权人？是否需要补一条书面记录？")
        if risk_counts["credit_blame"] or risk_counts["ownership_ambiguity"]:
            questions.insert(0, "我负责的部分和其他人的交界在哪里？有哪些依赖需要对方确认？")
        if not risks:
            questions.insert(0, "目前材料风险信号不强，还需要补充哪些具体聊天、会议纪要或组织信息？")
        return list(dict.fromkeys(questions))[:8]

    def _summary(self, nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]], risks: Sequence[Dict[str, Any]], hypotheses: Sequence[Dict[str, Any]], question: str, similar_scenarios: Optional[List[Dict[str, Any]]] = None) -> str:
        people = "、".join(n["label"] for n in nodes[:5]) or "暂无明确人物"
        risk = "、".join(r["title"] for r in risks[:3]) or "暂无明显风险"
        hyp = f"；重点假设：{hypotheses[0]['title']}" if hypotheses else ""
        prefix = f"围绕“{question}”，" if question else ""
        
        memory_note = ""
        if similar_scenarios:
            memory_note = f"（注：发现 {len(similar_scenarios)} 个相似历史场景可供参考）"
        
        return f"{prefix}识别到 {len(nodes)} 个相关人物、{len(edges)} 条关系边。核心人物：{people}。主要风险：{risk}{hyp}。所有隐藏问题均以假设呈现，需要回到证据和确认问题验证。{memory_note}"

    def _build_llm_prompt(self, base: Dict[str, Any], evidence: Sequence[Evidence], org_people: Sequence[OrgPerson], question: str, memory_context: Optional[Dict[str, Any]] = None, similar_scenarios: Optional[List[Dict[str, Any]]] = None) -> str:
        evidence_lines = "\n".join(f"- {e.id}: {e.text}" for e in evidence[:80])
        org_lines = "\n".join(f"- {p.name} | {p.title} | {p.team} | manager={p.manager}" for p in org_people)
        knowledge_section = build_prompt_section(base.get("knowledge_context") or {})
        
        memory_section = ""
        if memory_context:
            profiles = memory_context.get("person_profiles", {})
            patterns = memory_context.get("relevant_patterns", [])
            if profiles or patterns:
                memory_lines = []
                if profiles:
                    memory_lines.append("已知人物画像：")
                    for name, p in profiles.items():
                        memory_lines.append(f"- {name}: {p.get('title', '')} | {p.get('team', '')} | 特征: {', '.join(p.get('traits', [])[:3])}")
                if patterns:
                    memory_lines.append("\n已知模式：")
                    for p in patterns[:3]:
                        memory_lines.append(f"- {p['name']}: {p['description']} (置信度: {p['confidence']:.2f})")
                memory_section = "\n\n历史记忆：\n" + "\n".join(memory_lines)
        
        scenarios_section = ""
        if similar_scenarios:
            scenarios_section = "\n\n相似历史场景：\n"
            for i, s in enumerate(similar_scenarios[:2]):
                scenarios_section += f"{i+1}. {s.get('summary', '')[:200]}...\n"
        
        return f"""
你是一个职场关系与风险分析助手，服务对象是刚入职场的人。
任务：基于聊天、上传材料和组织架构，补充人际关系、合作关系、潜在风险和隐藏假设。

硬性规则：
1. 不要把猜测写成事实；隐藏问题必须标记为 hypothesis_not_fact。
2. 每条 risk / hypothesis 必须引用 evidence_ids。
3. 输出建议要偏向确认、留痕、澄清边界，而不是鼓励算计或攻击别人。
4. 只输出 JSON，不要 markdown。
5. 如果有历史记忆，可将其作为参考但不要直接当成事实。
6. 只能输出可观察行为模式，不能输出人格定性或读心式结论。

用户关注：{question or "梳理职场关系和潜在风险"}

组织架构：
{org_lines or "未提供"}

证据：
{evidence_lines}{memory_section}{scenarios_section}

{knowledge_section}

当前规则抽取结果摘要：
{json.dumps({"summary": base.get("summary"), "risks": base.get("risks", [])[:8], "relationships": base.get("relationships", [])[:10], "work_graph": base.get("work_graph", {}), "behavior_observations": base.get("behavior_observations", [])[:8], "jargon_signals": base.get("jargon_signals", [])[:12]}, ensure_ascii=False)}

请输出 JSON：
{{
  "summary": "一句话总结",
  "relationship_notes": [{{"source_name": "...", "target_name": "...", "type": "...", "label": "...", "confidence": 0.0, "evidence_ids": ["..."]}}],
  "risks": [{{"title": "...", "category": "...", "severity": 0.0, "confidence": 0.0, "people": ["..."], "evidence_ids": ["..."], "suggestion": "..."}}],
  "hidden_hypotheses": [{{"title": "...", "rationale": "...", "confidence": 0.0, "evidence_ids": ["..."], "status": "hypothesis_not_fact"}}],
  "recommended_questions": ["..."]
}}
""".strip()

    async def _llm_enrich(self, base: Dict[str, Any], evidence: Sequence[Evidence], org_people: Sequence[OrgPerson], question: str, memory_context: Optional[Dict[str, Any]] = None, similar_scenarios: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        prompt = self._build_llm_prompt(base, evidence, org_people, question, memory_context, similar_scenarios)
        try:
            raw = await self.llm_func(prompt)
        except Exception:
            return None
        parsed = json_object_from_text(raw)
        return parsed

    def _merge_llm_result(self, base: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        if isinstance(llm.get("summary"), str) and llm["summary"].strip():
            merged["summary"] = llm["summary"].strip()
        if isinstance(llm.get("risks"), list):
            existing_ids = {r.get("id") for r in merged.get("risks", [])}
            for idx, item in enumerate(llm["risks"][:10]):
                if not isinstance(item, dict):
                    continue
                rid = stable_id("llm_risk", json.dumps(item, ensure_ascii=False, sort_keys=True))
                if rid in existing_ids:
                    continue
                item = dict(item)
                item.setdefault("id", rid)
                item.setdefault("status", "llm_hypothesis")
                merged.setdefault("risks", []).append(item)
        if isinstance(llm.get("hidden_hypotheses"), list):
            merged["hidden_hypotheses"] = (llm["hidden_hypotheses"] + merged.get("hidden_hypotheses", []))[:10]
        if isinstance(llm.get("recommended_questions"), list):
            merged["recommended_questions"] = list(dict.fromkeys(llm["recommended_questions"] + merged.get("recommended_questions", [])))[:10]
        merged.setdefault("meta", {})["llm_used"] = True
        merged["graph"] = self._augment_graph(
            merged.get("people", []),
            merged.get("relationships", []),
            merged.get("risks", []),
            merged.get("hidden_hypotheses", []),
            (merged.get("work_graph") or {}).get("nodes", []),
            (merged.get("work_graph") or {}).get("edges", []),
        )
        return merged

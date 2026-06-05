"""LLM-assisted workplace relationship and hidden-risk intelligence.

The core design is evidence-first:
- deterministic extraction produces a stable graph even without an LLM;
- optional LLM reasoning can enrich labels, hidden hypotheses, and advice;
- every risk/hypothesis must point back to evidence ids;
- hypotheses are explicitly separated from observed facts.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence


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
    for name in org_names:
        if name and name in text and name not in names:
            names.append(name)
    if names:
        return names[:10]
    for match in CN_NAME_RE.finditer(text):
        name = match.group(1)
        if name not in {"但是", "因为", "所以", "然后", "如果", "这个", "那个"} and name not in names:
            names.append(name)
    for match in EN_NAME_RE.finditer(text):
        name = match.group(1)
        if name not in names:
            names.append(name)
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
    """Generate relationship/risk graph from chat, uploads, and org structure."""

    def __init__(self, llm_func: Optional[LLMFunc] = None):
        self.llm_func = llm_func

    async def analyze(
        self,
        *,
        chat_messages: Sequence[Dict[str, Any]] = (),
        uploaded_texts: Sequence[Dict[str, str]] = (),
        org_chart: Sequence[Dict[str, Any]] = (),
        question: str = "",
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        org_people = [OrgPerson(**{k: v for k, v in item.items() if k in {"name", "title", "team", "manager", "metadata"}}) for item in org_chart if item.get("name")]
        org_names = [p.name for p in org_people]
        evidence = self._collect_evidence(chat_messages, uploaded_texts)
        deterministic = self._deterministic_graph(evidence, org_people, org_names, question=question)
        if use_llm and self.llm_func and evidence:
            enriched = await self._llm_enrich(deterministic, evidence, org_people, question)
            if enriched:
                return self._merge_llm_result(deterministic, enriched)
        return deterministic

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
    ) -> Dict[str, Any]:
        people_mentions: Counter = Counter()
        people_evidence: Dict[str, List[str]] = defaultdict(list)
        people_signals: Dict[str, Counter] = defaultdict(Counter)
        edge_map: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        risks: List[Dict[str, Any]] = []
        risk_counts: Counter = Counter()

        for item in evidence:
            names = extract_people(item.text, org_names)
            relation_types = [kind for kind, rule in RELATION_TAXONOMY.items() if contains_any(item.text, rule["keywords"])]
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
        risks = sorted(risks, key=lambda r: (-float(r["severity"]), -float(r["confidence"])))[:20]
        hypotheses = self._build_hypotheses(risk_counts, edges, risks)
        return {
            "summary": self._summary(nodes, edges, risks, hypotheses, question),
            "graph": {"nodes": nodes, "edges": edges},
            "people": nodes,
            "relationships": edges,
            "risks": risks,
            "hidden_hypotheses": hypotheses,
            "recommended_questions": self._recommended_questions(risk_counts, risks),
            "evidence": [item.__dict__ for item in evidence],
            "meta": {
                "method": "rules_plus_optional_llm",
                "llm_used": False,
                "evidence_count": len(evidence),
                "org_people_count": len(org_people),
            },
        }

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

    def _summary(self, nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]], risks: Sequence[Dict[str, Any]], hypotheses: Sequence[Dict[str, Any]], question: str) -> str:
        people = "、".join(n["label"] for n in nodes[:5]) or "暂无明确人物"
        risk = "、".join(r["title"] for r in risks[:3]) or "暂无明显风险"
        hyp = f"；重点假设：{hypotheses[0]['title']}" if hypotheses else ""
        prefix = f"围绕“{question}”，" if question else ""
        return f"{prefix}识别到 {len(nodes)} 个相关人物、{len(edges)} 条关系边。核心人物：{people}。主要风险：{risk}{hyp}。所有隐藏问题均以假设呈现，需要回到证据和确认问题验证。"

    def _build_llm_prompt(self, base: Dict[str, Any], evidence: Sequence[Evidence], org_people: Sequence[OrgPerson], question: str) -> str:
        evidence_lines = "\n".join(f"- {e.id}: {e.text}" for e in evidence[:80])
        org_lines = "\n".join(f"- {p.name} | {p.title} | {p.team} | manager={p.manager}" for p in org_people)
        return f"""
你是一个职场关系与风险分析助手，服务对象是刚入职场的人。
任务：基于聊天、上传材料和组织架构，补充人际关系、合作关系、潜在风险和隐藏假设。

硬性规则：
1. 不要把猜测写成事实；隐藏问题必须标记为 hypothesis_not_fact。
2. 每条 risk / hypothesis 必须引用 evidence_ids。
3. 输出建议要偏向确认、留痕、澄清边界，而不是鼓励算计或攻击别人。
4. 只输出 JSON，不要 markdown。

用户关注：{question or "梳理职场关系和潜在风险"}

组织架构：
{org_lines or "未提供"}

证据：
{evidence_lines}

当前规则抽取结果摘要：
{json.dumps({"summary": base.get("summary"), "risks": base.get("risks", [])[:8], "relationships": base.get("relationships", [])[:10]}, ensure_ascii=False)}

请输出 JSON：
{{
  "summary": "一句话总结",
  "relationship_notes": [{{"source_name": "...", "target_name": "...", "type": "...", "label": "...", "confidence": 0.0, "evidence_ids": ["..."]}}],
  "risks": [{{"title": "...", "category": "...", "severity": 0.0, "confidence": 0.0, "people": ["..."], "evidence_ids": ["..."], "suggestion": "..."}}],
  "hidden_hypotheses": [{{"title": "...", "rationale": "...", "confidence": 0.0, "evidence_ids": ["..."], "status": "hypothesis_not_fact"}}],
  "recommended_questions": ["..."]
}}
""".strip()

    async def _llm_enrich(self, base: Dict[str, Any], evidence: Sequence[Evidence], org_people: Sequence[OrgPerson], question: str) -> Optional[Dict[str, Any]]:
        prompt = self._build_llm_prompt(base, evidence, org_people, question)
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
        return merged

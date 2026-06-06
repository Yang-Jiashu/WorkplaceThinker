"""Workplace knowledge injection for evidence-grounded analysis.

This module keeps product knowledge explicit and auditable. It does not turn
observations into personality judgments; it provides frames that help the
analysis separate people, work objects, behavior signals, and safe next checks.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Sequence


WORK_OBJECT_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "project": {
        "label": "项目 / 事项",
        "keywords": ["项目", "事项", "需求", "case", "project", "initiative"],
        "description": "一组需要多人协作推进的工作对象。",
    },
    "task": {
        "label": "任务",
        "keywords": ["任务", "action item", "todo", "推进", "处理", "跟进", "做一下"],
        "description": "可执行的具体工作。",
    },
    "decision": {
        "label": "决策",
        "keywords": ["决定", "结论", "拍板", "定了", "decision", "final"],
        "description": "影响后续行动的明确选择。",
    },
    "approval": {
        "label": "审批 / 授权",
        "keywords": ["审批", "授权", "批准", "流程", "approval", "sign-off"],
        "description": "正式允许行动或例外处理的机制。",
    },
    "deliverable": {
        "label": "交付物",
        "keywords": ["交付", "产出", "文档", "方案", "报告", "版本", "上线", "deliverable"],
        "description": "需要被交付、验收或记录的工作结果。",
    },
    "deadline": {
        "label": "截止时间",
        "keywords": ["截止", "deadline", "周一", "周二", "周三", "周四", "周五", "今天", "明天", "月底", "上线"],
        "description": "对行动窗口和风险优先级有影响的时间约束。",
    },
    "acceptance": {
        "label": "验收标准",
        "keywords": ["验收", "标准", "通过", "验收标准", "acceptance", "criteria"],
        "description": "判断工作是否完成的标准。",
    },
}


WORK_RELATION_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "owns_work": {
        "label": "负责",
        "keywords": ["负责", "owner", "归我", "归你", "主责"],
        "description": "谁对某项工作结果负责。",
    },
    "approves_work": {
        "label": "审批 / 授权",
        "keywords": ["审批", "批准", "授权", "同意", "sign-off"],
        "description": "谁拥有授权或审批权。",
    },
    "validates_work": {
        "label": "验收",
        "keywords": ["验收", "验证", "review", "acceptance"],
        "description": "谁负责判断工作是否达标。",
    },
    "sets_deadline": {
        "label": "设定时间要求",
        "keywords": ["截止", "deadline", "必须", "上线", "今天", "明天", "周五"],
        "description": "谁提出时间约束或交付窗口。",
    },
    "depends_on": {
        "label": "依赖",
        "keywords": ["依赖", "等", "需要", "前置", "blocked by", "dependency"],
        "description": "工作推进需要依赖其他人、信息或条件。",
    },
}


INTERNET_WORKPLACE_JARGON: Dict[str, Dict[str, Any]] = {
    "alignment": {
        "label": "对齐 / 拉齐",
        "terms": ["对齐", "拉齐", "align", "alignment", "sync一下", "同步一下", "口径一致", "对一下口径"],
        "maps_to": ["information_flow", "decision_record"],
        "interpretation": "通常表示信息、目标或口径需要一致；需要确认对齐的是事实、决策还是责任边界。",
        "safe_question": "我们这次要对齐的是目标、方案、owner，还是对外口径？",
    },
    "closure": {
        "label": "闭环",
        "terms": ["闭环", "close loop", "loop一下", "有结论", "跟到完"],
        "maps_to": ["accountability", "follow_through"],
        "interpretation": "通常表示事情需要有明确 owner、下一步和结果反馈；如果 owner 不清，容易变成模糊责任。",
        "safe_question": "这个闭环的 owner、截止时间和验收标准分别是什么？",
    },
    "ownership": {
        "label": "Owner / 主责",
        "terms": ["owner", "Owner", "主责", "归口", "牵头", "负责到底", "兜底"],
        "maps_to": ["raci", "accountability_boundary"],
        "interpretation": "通常涉及责任归属；要区分牵头、执行、审批、验收和兜底责任。",
        "safe_question": "这里的 owner 是牵头推进，还是对最终结果负责？谁审批和验收？",
    },
    "execution_pressure": {
        "label": "推进 / Push",
        "terms": ["推进", "push", "Push", "催一下", "盯一下", "压一下", "强推", "落地"],
        "maps_to": ["execution", "pressure"],
        "interpretation": "通常表示推动执行；当和时间、绩效或流程绕过一起出现时，可能需要确认资源和授权。",
        "safe_question": "为了推进这件事，需要谁给资源、授权或优先级确认？",
    },
    "breakdown": {
        "label": "拆解 / 颗粒度",
        "terms": ["拆解", "颗粒度", "拆一下", "细化", "拆任务", "拆需求"],
        "maps_to": ["work_breakdown", "scope"],
        "interpretation": "通常表示把目标拆成任务、范围和验收标准；有助于降低责任模糊。",
        "safe_question": "我们按哪些子任务、交付物和验收标准来拆？",
    },
    "schedule": {
        "label": "排期 / 上线",
        "terms": ["排期", "上线", "发版", "release", "deadline", "卡排期", "提测", "联调"],
        "maps_to": ["deadline", "delivery"],
        "interpretation": "通常涉及交付窗口、依赖和风险优先级；需要确认范围、验收和降级方案。",
        "safe_question": "这个排期下哪些范围必须保留，哪些可以降级？验收人是谁？",
    },
    "blocker": {
        "label": "卡点 / 阻塞",
        "terms": ["卡点", "卡住", "阻塞", "blocker", "blocked", "依赖没到", "等别人"],
        "maps_to": ["dependency", "risk"],
        "interpretation": "通常表示依赖、权限、信息或资源不足；需要把阻塞项公开化。",
        "safe_question": "当前卡点是信息、权限、资源、依赖方，还是决策没定？",
    },
    "review": {
        "label": "复盘 / 沉淀",
        "terms": ["复盘", "沉淀", "方法论", "经验", "归因", "review", "retro"],
        "maps_to": ["learning", "accountability"],
        "interpretation": "通常用于总结经验；要避免把复盘变成单点追责。",
        "safe_question": "这次复盘是为了改进流程，还是确认责任归属？我们先看事实链可以吗？",
    },
    "leverage": {
        "label": "抓手 / 赋能",
        "terms": ["抓手", "赋能", "打法", "心智", "链路", "场景", "承接", "提效"],
        "maps_to": ["strategy_language"],
        "interpretation": "通常是抽象策略语言；需要落到具体动作、owner 和指标，否则容易空转。",
        "safe_question": "这个抓手具体对应哪个动作、哪个指标、谁来承接？",
    },
}


BEHAVIOR_SIGNAL_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "supportive_risk_awareness": {
        "label": "风险提醒 / 支持倾向",
        "source_relationships": ["supports"],
        "source_risks": [],
        "description": "观察到提醒、帮助或补充背景的行为信号；只能说明本次互动里出现支持性行为。",
    },
    "commitment_reliability_watch": {
        "label": "承诺稳定性待观察",
        "source_relationships": ["commits_to"],
        "source_risks": ["stance_volatility"],
        "description": "承诺、验收或口径发生变化时，需要把最新版本写清楚；不能直接推断人格不可靠。",
    },
    "information_flow_control": {
        "label": "信息流控制 / 小范围沟通",
        "source_relationships": [],
        "source_risks": ["information_asymmetry"],
        "description": "关键决策或背景没有进入共同频道时，应优先补齐信息流。",
    },
    "process_boundary_risk": {
        "label": "流程边界风险",
        "source_relationships": [],
        "source_risks": ["process_bypass", "ownership_ambiguity"],
        "description": "流程、授权、owner 或验收标准不清时，应优先建立最小书面记录。",
    },
    "pressure_communication": {
        "label": "压力型沟通信号",
        "source_relationships": [],
        "source_risks": ["power_pressure"],
        "description": "出现绩效、必须、威胁式时间压力时，应把压力转成优先级、资源和取舍问题。",
    },
    "credit_accountability_boundary": {
        "label": "贡献 / 责任边界信号",
        "source_relationships": [],
        "source_risks": ["credit_blame", "ownership_ambiguity"],
        "description": "贡献可见性或责任归属可能不清时，应用阶段性同步和 RACI 式确认降低误解。",
    },
}


KNOWLEDGE_FRAMES: Dict[str, Dict[str, Any]] = {
    "raci": {
        "label": "RACI 责任澄清",
        "trigger_risks": ["ownership_ambiguity", "credit_blame"],
        "principle": "把负责者、批准者、咨询者、知会者拆开，不把口头协助等同于最终责任。",
        "safe_question": "这件事谁负责交付，谁批准，谁验收，哪些人只需要被知会？",
    },
    "decision_record": {
        "label": "决策记录",
        "trigger_risks": ["process_bypass", "information_asymmetry", "stance_volatility"],
        "principle": "关键决策应留下最小可审计记录，尤其是例外流程、口径变化和私下沟通。",
        "safe_question": "我把当前结论整理到共同频道确认一下，可以吗？",
    },
    "boundary_setting": {
        "label": "边界设定",
        "trigger_risks": ["power_pressure", "ownership_ambiguity"],
        "principle": "把压力翻译成范围、资源、优先级和 trade-off，而不是直接接受模糊承诺。",
        "safe_question": "如果周五必须上线，哪些范围可以降级，哪些资源需要同步确认？",
    },
    "ladder_of_inference": {
        "label": "推断阶梯",
        "trigger_risks": ["information_asymmetry", "credit_blame", "stance_volatility"],
        "principle": "先区分观察事实、解释、假设和行动，不把一次互动上升为人格定性。",
        "safe_question": "我现在掌握的是哪些事实，哪些只是可能解释？还缺哪条证据？",
    },
}


GUARDRAILS = [
    "只记录可观察行为模式，不输出人格定性。",
    "关系强弱、偏好和风险必须关联证据或用户确认。",
    "历史记忆只能提示值得检查的模式，不能直接当作当前事实。",
    "建议优先落到中性确认、同步、留痕、边界澄清。",
]


def contains_any(text: str, keywords: Sequence[str]) -> bool:
    lowered = str(text or "").lower()
    return any(str(k).lower() in lowered for k in keywords)


def match_work_objects(text: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for category, spec in WORK_OBJECT_TAXONOMY.items():
        if contains_any(text, spec["keywords"]):
            matches.append(
                {
                    "category": category,
                    "label": spec["label"],
                    "description": spec["description"],
                }
            )
    return matches


def match_work_relations(text: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for relation_type, spec in WORK_RELATION_TAXONOMY.items():
        if contains_any(text, spec["keywords"]):
            matches.append(
                {
                    "type": relation_type,
                    "label": spec["label"],
                    "description": spec["description"],
                }
            )
    return matches


def match_jargon_terms(text: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for category, spec in INTERNET_WORKPLACE_JARGON.items():
        hit_terms = [term for term in spec["terms"] if term in str(text or "")]
        if not hit_terms:
            continue
        matches.append(
            {
                "category": category,
                "label": spec["label"],
                "terms": hit_terms,
                "maps_to": spec["maps_to"],
                "interpretation": spec["interpretation"],
                "safe_question": spec["safe_question"],
            }
        )
    return matches


def infer_behavior_observations(
    people: Sequence[Dict[str, Any]],
    relationships: Sequence[Dict[str, Any]],
    risks: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    relationship_by_person: Dict[str, Counter] = {}
    risk_by_person: Dict[str, Counter] = {}

    for person in people:
        name = str(person.get("label") or person.get("name") or "")
        if name:
            relationship_by_person.setdefault(name, Counter())
            risk_by_person.setdefault(name, Counter())

    for edge in relationships:
        for name_key in ("source_name", "target_name"):
            name = str(edge.get(name_key) or "")
            if name:
                relationship_by_person.setdefault(name, Counter())[str(edge.get("type") or "")] += 1

    for risk in risks:
        for name in risk.get("people", []) or []:
            risk_by_person.setdefault(str(name), Counter())[str(risk.get("category") or "")] += 1

    observations: List[Dict[str, Any]] = []
    for name in sorted(set(relationship_by_person) | set(risk_by_person)):
        for signal_id, spec in BEHAVIOR_SIGNAL_TAXONOMY.items():
            rel_hits = [
                rel for rel in spec["source_relationships"]
                if relationship_by_person.get(name, Counter()).get(rel, 0)
            ]
            risk_hits = [
                risk for risk in spec["source_risks"]
                if risk_by_person.get(name, Counter()).get(risk, 0)
            ]
            if not rel_hits and not risk_hits:
                continue
            evidence_ids: List[str] = []
            for edge in relationships:
                if edge.get("type") in rel_hits and name in {edge.get("source_name"), edge.get("target_name")}:
                    evidence_ids.extend(edge.get("evidence_ids", []) or [])
            for risk in risks:
                if risk.get("category") in risk_hits and name in (risk.get("people") or []):
                    evidence_ids.extend(risk.get("evidence_ids", []) or [])
            observations.append(
                {
                    "id": f"behavior:{name}:{signal_id}",
                    "person": name,
                    "signal": signal_id,
                    "label": spec["label"],
                    "description": spec["description"],
                    "relationship_signals": rel_hits,
                    "risk_signals": risk_hits,
                    "evidence_ids": list(dict.fromkeys(evidence_ids))[:8],
                    "status": "observable_pattern_not_personality",
                }
            )
    return observations[:30]


def build_knowledge_context(
    risks: Sequence[Dict[str, Any]],
    work_items: Sequence[Dict[str, Any]],
    behavior_observations: Sequence[Dict[str, Any]],
    jargon_signals: Sequence[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    risk_categories = {str(r.get("category") or "") for r in risks}
    active_frames: List[Dict[str, Any]] = []
    for frame_id, spec in KNOWLEDGE_FRAMES.items():
        if risk_categories & set(spec["trigger_risks"]):
            active_frames.append(
                {
                    "id": frame_id,
                    "label": spec["label"],
                    "principle": spec["principle"],
                    "safe_question": spec["safe_question"],
                    "triggered_by": sorted(risk_categories & set(spec["trigger_risks"])),
                }
            )

    work_categories = Counter(str(item.get("category") or "") for item in work_items)
    behavior_signals = Counter(str(item.get("signal") or "") for item in behavior_observations)
    jargon_categories = Counter(str(item.get("category") or "") for item in jargon_signals)

    return {
        "source": "built_in_workplace_knowledge_v1",
        "purpose": "inject workplace collaboration concepts while preserving evidence boundaries",
        "active_frames": active_frames,
        "work_object_coverage": dict(work_categories),
        "behavior_signal_coverage": dict(behavior_signals),
        "jargon_coverage": dict(jargon_categories),
        "guardrails": GUARDRAILS,
    }


def build_prompt_section(knowledge_context: Dict[str, Any]) -> str:
    frames = knowledge_context.get("active_frames") or []
    if not frames:
        frames_text = "- 暂无特定框架触发；仍需遵守事实/假设/行动分层。"
    else:
        frames_text = "\n".join(
            f"- {frame['label']}: {frame['principle']} 安全确认问题：{frame['safe_question']}"
            for frame in frames[:6]
        )
    guardrails = "\n".join(f"- {g}" for g in knowledge_context.get("guardrails", GUARDRAILS))
    jargon = knowledge_context.get("jargon_coverage") or {}
    jargon_text = "、".join(f"{key}={count}" for key, count in jargon.items()) or "暂无"
    return f"""
职场知识注入：
{frames_text}

互联网职场语义信号：
- {jargon_text}

行为画像边界：
{guardrails}
""".strip()

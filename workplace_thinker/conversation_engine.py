"""
WorkplaceThinker 对话式增强模块

实现 P0 级改进：
1. 对话式追问（多轮对话支持）
2. 行动建议模板（具体话术）
3. 结果分级（按紧急度/重要度排序）
4. 时序分析（立场变化检测）
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ===================================================================
# 1. 行动建议模板库 - 具体话术
# ===================================================================

ACTION_TEMPLATES = {
    "process_bypass": {
        "urgent": {
            "label": "立即书面确认流程",
            "scripts": [
                "我理解我们需要快速推进。我这边开始做，同时想确认一下：这个走的是哪个审批流？是走紧急通道还是事后补单？",
                "我已经按你的建议开始执行了，方便我同步给 [上级名字] 让他知情吗？这样后续补流程更顺畅。",
            ],
            "channel": "邮件或群消息（保留记录）",
            "best_practice": "NVC非暴力沟通 - 表达配合+明确需求+避免对抗",
        },
        "follow_up": {
            "label": "设置书面留痕机制",
            "scripts": [
                "为避免以后扯皮，今天起所有口头决定，我整理成会议纪要发出来确认，好吧？",
                "我建个项目群，把关键决策放进去，方便所有人追溯，你看可以吗？",
            ],
            "channel": "邮件",
            "best_practice": "SBI反馈 - 情况:口头决定多 / 行为:建议建群 / 影响:可追溯",
        },
    },
    "ownership_ambiguity": {
        "urgent": {
            "label": "明确责任边界",
            "scripts": [
                "这件事我负责 [具体范围]，[其他范围] 是 [其他人] 负责，对吗？我整理出来发邮件让大家确认。",
                "想确认下 owner 分工：我做A，你做B，验收标准是 [X]，可以这样吗？",
            ],
            "channel": "邮件 + 拉群确认",
            "best_practice": "RACI矩阵 - 明确谁负责/谁批准/咨询谁/知会谁",
        },
        "follow_up": {
            "label": "建立 owner 公开机制",
            "scripts": [
                "建议在项目群公开所有任务和 owner，避免私下口头安排。",
            ],
            "channel": "项目管理工具/群公告",
            "best_practice": "建立可视化任务追踪",
        },
    },
    "credit_blame": {
        "urgent": {
            "label": "建立工作日志",
            "scripts": [
                "为避免信息不对称，我每天下班前发一封进度邮件给 [上级] 和相关方，CC 你。今天先试试。",
                "以后所有口头安排，我都会补一份邮件确认，方便大家都有据可查。",
            ],
            "channel": "工作日志邮件",
            "best_practice": "CYA原则 - Cover Your Assets",
        },
        "follow_up": {
            "label": "建立周报机制",
            "scripts": [
                "建议团队建立周报机制，每周五同步进展，让所有人都能看到贡献。",
            ],
            "channel": "周报",
            "best_practice": "让工作可见",
        },
    },
    "information_asymmetry": {
        "urgent": {
            "label": "主动同步信息",
            "scripts": [
                "我可能信息不全，能给我讲讲背景吗？这样我做事更有针对性。",
                "方便我加入 [会议/群] 吗？这样我能更全面理解上下文。",
            ],
            "channel": "一对一或会议",
            "best_practice": "好奇心 + 谦逊姿态",
        },
        "follow_up": {
            "label": "建立信息同步机制",
            "scripts": [
                "建议每周有一次 15 分钟的跨组同步，避免信息断层。",
            ],
            "channel": "会议",
            "best_practice": "减少信息孤岛",
        },
    },
    "power_pressure": {
        "urgent": {
            "label": "保护性表达",
            "scripts": [
                "我理解时间紧。我可以 [具体能做的事]，需要 [具体资源/时间]。你看这样可行吗？",
                "我担心 [具体风险]。如果不能 [资源/条件]，我们可能要降低范围或者延后。",
            ],
            "channel": "邮件留痕",
            "best_practice": "SBI + 替代方案 - 拒绝说'不'，说'可以但需要'",
        },
        "follow_up": {
            "label": "建立边界",
            "scripts": [
                "如果这件事不在我职责范围内，我可以 [支持方式]，但 owner 还是 [谁]。",
            ],
            "channel": "书面",
            "best_practice": "温和但坚定的边界",
        },
    },
    "stance_volatility": {
        "urgent": {
            "label": "锁定最新共识",
            "scripts": [
                "我听到几个版本：[版本A]、[版本B]。我按 [最新版本] 走，对吗？我再邮件确认下避免误判。",
                "为了避免我理解错，我把最终版发出来请 [上级] 确认。",
            ],
            "channel": "邮件",
            "best_practice": "书面锁定 - Verbal is volatile, written is stable",
        },
        "follow_up": {
            "label": "建立决策记录",
            "scripts": [
                "所有重要决定我们都用邮件确认吧，我来做这件事。",
            ],
            "channel": "邮件",
            "best_practice": "建立团队习惯",
        },
    },
}

# 通用话术模板
GENERAL_SCRIPTS = {
    "first_meeting": [
        "我是 [名字]，刚加入 [团队]。我看了 [背景资料]，有几个想确认的点...",
        "想跟您 [一对一/咖啡] 15 分钟，了解您对我这个角色的期待。",
    ],
    "after_meeting": [
        "整理一下今天的纪要：[关键决策]，[行动项]，[owner]。如有偏差请指出。",
    ],
    "decline_politely": [
        "我现在 [具体任务]，如果接这个会牺牲 [X]。你看哪个优先？",
        "这件事我想做但需要 [资源/时间/支持]。我们一起想个方案？",
    ],
}


# ===================================================================
# 2. 结果分级器
# ===================================================================

URGENCY_LEVELS = {
    "P0_critical": {
        "label": "🚨 立即处理（24小时内）",
        "color": "#d32f2f",
        "description": "已经发生或即将发生，会直接造成伤害或背锅",
        "action_window": "今天/明天",
    },
    "P1_high": {
        "label": "⚠️  高度关注（本周内）",
        "color": "#f57c00",
        "description": "高概率会发生，需要主动管理",
        "action_window": "本周",
    },
    "P2_medium": {
        "label": "📋 持续观察（两周内）",
        "color": "#fbc02d",
        "description": "可能发生，需要保持警觉",
        "action_window": "两周内",
    },
    "P3_low": {
        "label": "💡 了解即可（背景信息）",
        "color": "#388e3c",
        "description": "背景知识，不需要立即行动",
        "action_window": "后续",
    },
}


def classify_risk_urgency(risk: Dict[str, Any]) -> str:
    """
    根据风险的多个维度分级
    
    考虑因素:
    - severity (严重度)
    - confidence (置信度)
    - 风险类别
    - 是否已经发生
    - 是否牵涉核心人物
    """
    severity = float(risk.get("severity", 0.5))
    confidence = float(risk.get("confidence", 0.5))
    category = str(risk.get("category", ""))
    
    # 计算综合分
    score = severity * 0.5 + confidence * 0.3
    
    # 关键类别加权
    if category in ("credit_blame", "process_bypass"):
        score += 0.2
    elif category in ("ownership_ambiguity", "power_pressure"):
        score += 0.15
    
    # 已经是事实的风险（比如明确发现了背锅信号）
    evidence_text = str(risk.get("evidence_text", ""))
    if any(indicator in evidence_text for indicator in ["已经", "发生", "发现", "问题"]):
        score += 0.1
    
    if score >= 0.85:
        return "P0_critical"
    elif score >= 0.7:
        return "P1_high"
    elif score >= 0.5:
        return "P2_medium"
    else:
        return "P3_low"


def prioritize_results(
    risks: Sequence[Dict[str, Any]],
    hypotheses: Sequence[Dict[str, Any]],
    questions: Sequence[str],
) -> Dict[str, Any]:
    """
    对结果进行分级和排序
    
    Returns:
        {
            "by_urgency": {
                "P0_critical": [...],
                "P1_high": [...],
                "P2_medium": [...],
                "P3_low": [...]
            },
            "top_actions": [...],  # 优先处理的前3项
            "summary": "..."
        }
    """
    # 对风险分级
    risk_by_urgency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for risk in risks:
        urgency = classify_risk_urgency(risk)
        risk_with_urgency = {**risk, "urgency": urgency, "urgency_label": URGENCY_LEVELS[urgency]["label"]}
        risk_by_urgency[urgency].append(risk_with_urgency)
    
    # 对每个urgency内部按severity排序
    for urgency in risk_by_urgency:
        risk_by_urgency[urgency].sort(
            key=lambda r: -float(r.get("severity", 0)) * float(r.get("confidence", 0))
        )
    
    # 对假设也分级
    hyp_by_urgency: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for hyp in hypotheses:
        confidence = float(hyp.get("confidence", 0.5))
        if confidence >= 0.7:
            urgency = "P1_high"
        elif confidence >= 0.5:
            urgency = "P2_medium"
        else:
            urgency = "P3_low"
        hyp_with_urgency = {**hyp, "urgency": urgency, "urgency_label": URGENCY_LEVELS[urgency]["label"]}
        hyp_by_urgency[urgency].append(hyp_with_urgency)
    
    # 提取 top actions（前3个高优先级项）
    top_actions = []
    for urgency in ["P0_critical", "P1_high"]:
        for risk in risk_by_urgency[urgency][:2]:
            top_actions.append({
                "id": risk.get("id"),
                "type": "risk",
                "urgency": urgency,
                "title": risk.get("title", ""),
                "urgency_label": URGENCY_LEVELS[urgency]["label"],
                "action_window": URGENCY_LEVELS[urgency]["action_window"],
            })
    
    # 总结
    critical_count = len(risk_by_urgency["P0_critical"])
    high_count = len(risk_by_urgency["P1_high"])
    
    if critical_count > 0:
        summary = f"🚨 紧急: {critical_count} 个需要立即处理的风险；⚠️ 关注: {high_count} 个高优先级风险"
    elif high_count > 0:
        summary = f"⚠️ 关注: {high_count} 个高优先级风险需要主动管理"
    else:
        summary = "📊 当前没有紧急风险，保持观察即可"
    
    return {
        "by_urgency": {
            "P0_critical": {
                "label": URGENCY_LEVELS["P0_critical"]["label"],
                "description": URGENCY_LEVELS["P0_critical"]["description"],
                "risks": risk_by_urgency["P0_critical"],
                "hypotheses": hyp_by_urgency["P0_critical"],
            },
            "P1_high": {
                "label": URGENCY_LEVELS["P1_high"]["label"],
                "description": URGENCY_LEVELS["P1_high"]["description"],
                "risks": risk_by_urgency["P1_high"],
                "hypotheses": hyp_by_urgency["P1_high"],
            },
            "P2_medium": {
                "label": URGENCY_LEVELS["P2_medium"]["label"],
                "description": URGENCY_LEVELS["P2_medium"]["description"],
                "risks": risk_by_urgency["P2_medium"],
                "hypotheses": hyp_by_urgency["P2_medium"],
            },
            "P3_low": {
                "label": URGENCY_LEVELS["P3_low"]["label"],
                "description": URGENCY_LEVELS["P3_low"]["description"],
                "risks": risk_by_urgency["P3_low"],
                "hypotheses": hyp_by_urgency["P3_low"],
            },
        },
        "top_actions": top_actions[:3],
        "summary": summary,
    }


def generate_action_scripts(
    risks: Sequence[Dict[str, Any]],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    为高优先级风险生成具体话术
    
    Returns:
        [
            {
                "risk_id": "...",
                "risk_title": "...",
                "action": {
                    "label": "...",
                    "scripts": ["话术1", "话术2"],
                    "channel": "...",
                    "best_practice": "..."
                }
            }
        ]
    """
    actions = []
    
    # 按urgency和severity排序
    sorted_risks = sorted(
        risks,
        key=lambda r: (
            -float(r.get("severity", 0)) * float(r.get("confidence", 0))
        )
    )
    
    for risk in sorted_risks[:top_n]:
        category = str(risk.get("category", ""))
        urgency = classify_risk_urgency(risk)
        
        # 获取对应的模板
        template = ACTION_TEMPLATES.get(category, {})
        action_type = "urgent" if urgency in ("P0_critical", "P1_high") else "follow_up"
        
        if action_type in template:
            action = template[action_type]
        elif template and "follow_up" in template:
            action = template["follow_up"]
        else:
            # 默认通用话术
            action = {
                "label": "确认情况",
                "scripts": [
                    "我想确认下 [具体事项]，能花 5 分钟聊聊吗？",
                    "我先理解下：[你的理解]。你看对吗？",
                ],
                "channel": "一对一",
                "best_practice": "好奇心 + 确认理解",
            }
        
        actions.append({
            "risk_id": risk.get("id"),
            "risk_title": risk.get("title", ""),
            "urgency": urgency,
            "urgency_label": URGENCY_LEVELS[urgency]["label"],
            "action": action,
        })
    
    return actions


# ===================================================================
# 3. 时序分析 - 立场变化检测
# ===================================================================

@dataclass
class StanceEvent:
    """立场事件"""
    timestamp: float
    person: str
    topic: str
    position: str
    evidence: str
    confidence: float = 0.5


@dataclass
class StanceChange:
    """立场变化记录"""
    person: str
    topic: str
    from_position: str
    to_position: str
    time_gap_hours: float
    evidence: List[str]
    severity: float  # 变化剧烈程度
    pattern: str  # 反复 / 软化 / 硬化 / 升级


def detect_stance_volatility(
    historical_analyses: Sequence[Dict[str, Any]],
    current_analysis: Dict[str, Any],
) -> List[StanceChange]:
    """
    检测立场反复
    
    比较历史分析中同一人物在同一话题上的立场变化
    """
    # 简化版实现：使用关键词匹配
    # 真实场景需要更精细的 NLP
    
    stance_keywords = {
        "positive": ["支持", "同意", "可以", "做", "好", "yes", "agree", "支持", "认可", "没问题"],
        "negative": ["反对", "不同意", "不能", "不做", "no", "disagree", "拒绝", "不行", "有问题"],
        "neutral": ["考虑", "再看看", "等等", "maybe", "考虑中"],
    }
    
    position_keywords = {
        "supports": ["支持", "协作", "一起", "合作", "认可", "没问题"],
        "blocks_or_challenges": ["反对", "质疑", "不同意", "拒绝", "不认可"],
    }
    
    changes: List[StanceChange] = []
    
    # 收集所有分析中的人物立场
    all_analyses = list(historical_analyses) + [current_analysis]
    person_stances: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for analysis in all_analyses:
        timestamp = analysis.get("timestamp", time.time())
        for risk in analysis.get("risks", []):
            for person in risk.get("people", []):
                category = risk.get("category", "")
                if category == "stance_volatility":
                    person_stances[str(person)].append({
                        "timestamp": timestamp,
                        "risk": risk,
                        "evidence": risk.get("evidence_text", ""),
                    })
    
    # 检测同一人物的立场变化
    for person, stances in person_stances.items():
        if len(stances) < 2:
            continue
        
        stances.sort(key=lambda x: x["timestamp"])
        
        for i in range(1, len(stances)):
            prev = stances[i-1]
            curr = stances[i]
            time_gap = (curr["timestamp"] - prev["timestamp"]) / 3600  # 转换为小时
            
            # 简化判断：如果两次都有立场相关风险
            prev_evidence = prev["evidence"]
            curr_evidence = curr["evidence"]
            
            # 检测变化类型
            pattern = "change"
            severity = 0.5
            
            if "改口" in curr_evidence or "反转" in curr_evidence:
                pattern = "反复"
                severity = 0.8
            elif "软化" in curr_evidence or "缓和" in curr_evidence:
                pattern = "软化"
                severity = 0.4
            elif "升级" in curr_evidence or "强硬" in curr_evidence:
                pattern = "硬化"
                severity = 0.7
            elif "再考虑" in curr_evidence or "重新" in curr_evidence:
                pattern = "犹豫"
                severity = 0.3
            
            changes.append(StanceChange(
                person=person,
                topic="未明确",  # 简化
                from_position=prev_evidence[:30],
                to_position=curr_evidence[:30],
                time_gap_hours=time_gap,
                evidence=[prev_evidence, curr_evidence],
                severity=severity,
                pattern=pattern,
            ))
    
    return changes


def analyze_temporal_patterns(
    historical_analyses: Sequence[Dict[str, Any]],
    current_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    时序分析：识别反复出现的模式
    
    Returns:
        {
            "stance_changes": [...],  # 立场变化列表
            "recurring_risks": [...],  # 反复出现的风险
            "escalation_patterns": [...],  # 升级模式
            "warnings": [...]  # 警告
        }
    """
    stance_changes = detect_stance_volatility(historical_analyses, current_analysis)
    
    # 反复出现的风险
    risk_counts: Counter = Counter()
    risk_examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for analysis in list(historical_analyses) + [current_analysis]:
        for risk in analysis.get("risks", []):
            key = f"{risk.get('category')}:{risk.get('title', '')[:30]}"
            risk_counts[key] += 1
            risk_examples[key].append(risk)
    
    recurring_risks = []
    for key, count in risk_counts.items():
        if count >= 2:
            recurring_risks.append({
                "category_and_title": key,
                "occurrences": count,
                "severity_score": min(count * 0.3, 1.0),  # 出现次数越多越严重
                "warning": f"这个风险在多次分析中反复出现，可能是一个固定模式",
                "examples": risk_examples[key][:3],
            })
    
    recurring_risks.sort(key=lambda x: -x["occurrences"])
    
    # 升级模式：风险严重度逐渐增加
    escalation_patterns = []
    risk_evolution: Dict[str, List[float]] = defaultdict(list)
    
    for analysis in list(historical_analyses) + [current_analysis]:
        timestamp = analysis.get("timestamp", time.time())
        for risk in analysis.get("risks", []):
            key = f"{risk.get('category')}:{risk.get('title', '')[:30]}"
            risk_evolution[key].append((timestamp, float(risk.get("severity", 0))))
    
    for key, evolution in risk_evolution.items():
        if len(evolution) >= 2:
            evolution.sort()  # 按时间排序
            severities = [s for _, s in evolution]
            # 检测升级趋势（后一次比前一次严重度增加）
            increasing_count = sum(1 for i in range(1, len(severities)) if severities[i] > severities[i-1])
            if increasing_count >= len(severities) / 2:
                escalation_patterns.append({
                    "risk": key,
                    "pattern": "escalation",
                    "trend": "风险严重度在增加",
                    "occurrences": len(evolution),
                    "severities": severities,
                    "warning": "⚠️ 这个风险呈现升级趋势，需要立即关注",
                })
    
    # 综合警告
    warnings = []
    if stance_changes:
        high_severity = [c for c in stance_changes if c.severity >= 0.7]
        if high_severity:
            warnings.append({
                "type": "stance_volatility",
                "message": f"检测到 {len(high_severity)} 个高严重度立场变化",
                "people": list(set(c.person for c in high_severity)),
            })
    
    if recurring_risks:
        top = recurring_risks[0]
        warnings.append({
            "type": "recurring_risk",
            "message": f"'{top['category_and_title']}' 已出现 {top['occurrences']} 次",
            "advice": "这是固定模式，需要系统性应对而不是单次处理",
        })
    
    if escalation_patterns:
        warnings.append({
            "type": "escalation",
            "message": f"检测到 {len(escalation_patterns)} 个风险在升级",
            "advice": "升级中的风险需要更主动的干预",
        })
    
    return {
        "stance_changes": [
            {
                "person": c.person,
                "topic": c.topic,
                "from": c.from_position,
                "to": c.to_position,
                "time_gap_hours": c.time_gap_hours,
                "severity": c.severity,
                "pattern": c.pattern,
                "evidence_count": len(c.evidence),
            }
            for c in stance_changes
        ],
        "recurring_risks": recurring_risks[:5],
        "escalation_patterns": escalation_patterns[:5],
        "warnings": warnings,
    }


# ===================================================================
# 4. 对话式追问支持
# ===================================================================

@dataclass
class ConversationTurn:
    """对话轮次"""
    timestamp: float
    user_message: str
    user_question: str
    analysis_result: Dict[str, Any]
    user_feedback: Optional[Dict[str, Any]] = None


class ConversationEngine:
    """
    对话式追问引擎
    
    支持:
    - 维护对话历史
    - 上下文复用
    - 智能追问建议
    - 渐进式分析
    """
    
    def __init__(self, max_history: int = 20):
        self.conversation_history: List[ConversationTurn] = []
        self.max_history = max_history
        self.pending_questions: List[str] = []
    
    def add_turn(
        self,
        user_message: str,
        user_question: str,
        analysis_result: Dict[str, Any],
        user_feedback: Optional[Dict[str, Any]] = None,
    ):
        """添加一轮对话"""
        turn = ConversationTurn(
            timestamp=time.time(),
            user_message=user_message,
            user_question=user_question,
            analysis_result=analysis_result,
            user_feedback=user_feedback,
        )
        self.conversation_history.append(turn)
        
        # 限制历史长度
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]
    
    def get_context_summary(self) -> Dict[str, Any]:
        """获取对话上下文摘要"""
        return {
            "turn_count": len(self.conversation_history),
            "topics": list(set(
                turn.user_question[:30] for turn in self.conversation_history[-5:]
            )),
            "key_people": self._extract_people(),
            "key_risks": self._extract_risks(),
        }
    
    def _extract_people(self) -> List[str]:
        """从历史中提取关键人物"""
        people_counter: Counter = Counter()
        for turn in self.conversation_history[-10:]:
            for person in turn.analysis_result.get("people", []):
                name = person.get("label", "")
                if name:
                    people_counter[name] += 1
        return [p for p, _ in people_counter.most_common(10)]
    
    def _extract_risks(self) -> List[str]:
        """从历史中提取关键风险"""
        risk_titles: List[str] = []
        for turn in self.conversation_history[-10:]:
            for risk in turn.analysis_result.get("risks", [])[:3]:
                title = risk.get("title", "")
                if title and title not in risk_titles:
                    risk_titles.append(title)
        return risk_titles[:10]
    
    def suggest_follow_up_questions(
        self,
        current_analysis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        基于当前分析智能建议追问
        
        Returns:
            [
                {
                    "question": "...",
                    "reason": "为什么推荐这个问题",
                    "expected_value": "能得到什么信息",
                    "difficulty": "easy|medium|hard"
                }
            ]
        """
        suggestions = []
        risks = current_analysis.get("risks", [])
        people = current_analysis.get("people", [])
        
        # 基于风险类别建议
        risk_categories = set(r.get("category") for r in risks)
        
        if "process_bypass" in risk_categories:
            suggestions.append({
                "question": "我想知道这个流程是不是有特殊豁免的情况，能给我讲讲历史吗？",
                "reason": "了解流程的历史豁免情况，能判断这次绕过是临时还是常态",
                "expected_value": "判断这是否是组织级别的'特殊通道'，还是个人决定",
                "difficulty": "easy",
            })
        
        if "credit_blame" in risk_categories:
            suggestions.append({
                "question": "我想跟上级 1-on-1 聊聊我的工作，怎么约比较合适？",
                "reason": "直接建立与上级的定期沟通，避免被中间人扭曲信息",
                "expected_value": "建立直接汇报通道，让工作可见",
                "difficulty": "medium",
            })
        
        if "ownership_ambiguity" in risk_categories:
            suggestions.append({
                "question": "我想确认下当前几个任务的 owner，能帮我列个清单发邮件吗？",
                "reason": "把责任明确化是消除模糊的关键",
                "expected_value": "把所有任务的 owner 公开化",
                "difficulty": "easy",
            })
        
        # 基于人物关系建议
        if len(people) >= 2:
            suggestions.append({
                "question": "这几个人之间的关系，你能给我画个图吗？",
                "reason": "可视化关系能帮助理解团队的权力结构",
                "expected_value": "看到'实际权力'和'正式架构'的差异",
                "difficulty": "easy",
            })
        
        # 基于对话历史建议
        if self.conversation_history:
            last_turn = self.conversation_history[-1]
            if last_turn.analysis_result.get("risks"):
                top_risk = last_turn.analysis_result["risks"][0]
                suggestions.append({
                    "question": f"关于 '{top_risk.get('title', '那个风险')}'，我具体该怎么应对？",
                    "reason": "在已知风险的基础上深入探讨",
                    "expected_value": "得到具体的行动方案",
                    "difficulty": "medium",
                })
        
        # 通用建议
        suggestions.append({
            "question": "你能给我一些具体的话术吗？我不太会表达。",
            "reason": "很多新人知道要做什么但不知道怎么开口",
            "expected_value": "得到可以直接使用的对话模板",
            "difficulty": "easy",
        })
        
        return suggestions[:5]
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """获取对话总结"""
        if not self.conversation_history:
            return {"message": "还没有对话历史"}
        
        return {
            "total_turns": len(self.conversation_history),
            "first_turn_time": self.conversation_history[0].timestamp,
            "last_turn_time": self.conversation_history[-1].timestamp,
            "duration_hours": (
                self.conversation_history[-1].timestamp - self.conversation_history[0].timestamp
            ) / 3600,
            "topics_covered": list(set(
                turn.user_question[:50] for turn in self.conversation_history
            ))[:10],
            "people_mentioned": self._extract_people(),
            "risks_identified": self._extract_risks(),
            "key_insights": self._extract_key_insights(),
        }
    
    def _extract_key_insights(self) -> List[str]:
        """从历史中提取关键洞察"""
        insights = []
        for turn in self.conversation_history[-5:]:
            summary = turn.analysis_result.get("summary", "")
            if summary and summary not in insights:
                insights.append(summary)
        return insights[:5]
    
    def merge_with_previous_context(
        self,
        new_message: str,
        new_question: str,
    ) -> Tuple[str, str]:
        """
        将新输入与历史上下文合并
        
        Returns:
            (合并后的信息, 合并后的问题)
        """
        if not self.conversation_history:
            return new_message, new_question
        
        # 收集历史中的关键上下文
        prev_people = self._extract_people()
        prev_risks = self._extract_risks()
        
        context_addition = ""
        if prev_people:
            context_addition += f"\n[历史中提到的人物: {', '.join(prev_people[:5])}]"
        if prev_risks:
            context_addition += f"\n[历史中识别的风险: {', '.join(prev_risks[:3])}]"
        
        merged_message = new_message + context_addition
        return merged_message, new_question

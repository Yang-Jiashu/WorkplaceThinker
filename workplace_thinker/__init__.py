"""
WorkplaceThinker - 职场关系和风险洞察工具

帮助职场新人更快了解情况，识别风险，保护自己。
P0 增强：对话式追问、行动话术、结果分级、时序分析
"""

from .insights import WorkplaceInsightEngine
from .harness import WorkplaceInsightHarness
from .memory_engine import WorkplaceMemoryEngine
from .migrations import (
    CURRENT_MEMORY_SCHEMA_VERSION,
    CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
    WorkplaceMemoryMigrator,
)
from .org_importer import OrgStructureImporter
from .conversation_engine import (
    ConversationEngine,
    prioritize_results,
    generate_action_scripts,
    analyze_temporal_patterns,
    URGENCY_LEVELS,
    ACTION_TEMPLATES,
)

__version__ = "0.3.0"
__all__ = [
    "WorkplaceInsightEngine",
    "WorkplaceInsightHarness",
    "WorkplaceMemoryEngine",
    "WorkplaceMemoryMigrator",
    "CURRENT_MEMORY_SCHEMA_VERSION",
    "CURRENT_ORG_STRUCTURE_SCHEMA_VERSION",
    "OrgStructureImporter",
    "ConversationEngine",
    "prioritize_results",
    "generate_action_scripts",
    "analyze_temporal_patterns",
    "URGENCY_LEVELS",
    "ACTION_TEMPLATES",
]

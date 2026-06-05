"""
WorkplaceThinker - 职场关系和风险洞察工具

帮助职场新人更快了解情况，识别风险，保护自己。
"""

from .insights import WorkplaceInsightEngine
from .harness import WorkplaceInsightHarness
from .memory_engine import WorkplaceMemoryEngine

__version__ = "0.2.0"
__all__ = [
    "WorkplaceInsightEngine",
    "WorkplaceInsightHarness",
    "WorkplaceMemoryEngine",
]

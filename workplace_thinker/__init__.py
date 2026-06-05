"""WorkplaceThinker product layer built on top of DocThinker."""

from .harness import WorkplaceInsightHarness
from .insights import WorkplaceInsightEngine

__all__ = ["WorkplaceInsightEngine", "WorkplaceInsightHarness"]

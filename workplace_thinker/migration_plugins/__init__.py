"""Pluggable migration steps for durable WorkplaceThinker data."""

from __future__ import annotations

from typing import List

from .memory_v1_to_v2 import MemoryV1ToV2


def memory_migration_steps() -> List[object]:
    """Return registered memory migration steps in execution order."""
    return [MemoryV1ToV2()]

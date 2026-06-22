"""Memory export migration from schema v1 to v2."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class MemoryV1ToV2:
    from_version = 1
    to_version = 2
    name = "memory_v1_to_v2"

    def applies(self, version: int, data: Dict[str, Any]) -> bool:
        return version < self.to_version

    def apply(self, migrator: Any, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        steps: List[str] = []

        if isinstance(data.get("person_profiles"), list):
            data["person_profiles"] = {
                item.get("name", f"person_{idx}"): item
                for idx, item in enumerate(data["person_profiles"])
                if isinstance(item, dict)
            }
            steps.append("converted_person_profiles_list_to_map")

        if isinstance(data.get("relationships"), list):
            data["relationships"] = {
                f"{item.get('source', '')}|{item.get('target', '')}|{item.get('relationship_type', item.get('type', 'related_to'))}": item
                for item in data["relationships"]
                if isinstance(item, dict)
            }
            steps.append("converted_relationships_list_to_map")

        if "org_chart" in data and "org_structure" not in data:
            data["org_structure"] = {"people": data.get("org_chart") or []}
            steps.append("promoted_org_chart_to_org_structure")

        org_structure, org_report = migrator.migrate_org_structure(data.get("org_structure", {}))
        data["org_structure"] = org_structure
        if org_report["changed"]:
            steps.append("migrated_org_structure")

        return data, steps

"""Schema migration helpers for durable WorkplaceThinker data.

The product treats memory, person dossiers, relationship graphs, and
organization structure as long-lived user assets. This module upgrades older
exports into the current contracts before they are imported or rendered.
"""

from __future__ import annotations

import copy
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple


CURRENT_MEMORY_SCHEMA_VERSION = 2
CURRENT_ORG_STRUCTURE_SCHEMA_VERSION = 2


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.md5(str(value or "").encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


class WorkplaceMemoryMigrator:
    """Upgrade exported memory and org-structure payloads across versions."""

    def migrate_memory(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        original_version = self._version(data)
        migrated = copy.deepcopy(data if isinstance(data, dict) else {})
        steps: List[str] = []

        if original_version < 2:
            migrated, v1_steps = self._memory_v1_to_v2(migrated)
            steps.extend(v1_steps)

        migrated.setdefault("schema_name", "workplace_memory_export")
        migrated["schema_version"] = CURRENT_MEMORY_SCHEMA_VERSION
        migrated.setdefault("exported_at", time.time())
        migrated.setdefault("person_profiles", {})
        migrated.setdefault("patterns", {})
        migrated.setdefault("people", {})
        migrated.setdefault("relationships", {})
        migrated.setdefault("graph_snapshots", [])
        migrated.setdefault("historical_analyses_count", 0)
        migrated.setdefault("migration_history", [])

        history_item = {
            "from_version": original_version,
            "to_version": CURRENT_MEMORY_SCHEMA_VERSION,
            "migrated_at": time.time(),
            "steps": steps or ["already_current"],
        }
        if original_version != CURRENT_MEMORY_SCHEMA_VERSION or steps:
            migrated["migration_history"] = [*migrated.get("migration_history", []), history_item]

        return migrated, {
            "schema_name": migrated["schema_name"],
            "from_version": original_version,
            "to_version": CURRENT_MEMORY_SCHEMA_VERSION,
            "changed": original_version != CURRENT_MEMORY_SCHEMA_VERSION or bool(steps),
            "steps": steps,
        }

    def migrate_org_structure(self, data: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        original_version = self._version(data)
        payload = copy.deepcopy(data)
        steps: List[str] = []

        if isinstance(payload, list):
            payload = {"people": payload}
            steps.append("wrapped_org_chart_list")
        elif not isinstance(payload, dict):
            payload = {}
            steps.append("initialized_empty_org_structure")

        if payload.get("org_chart") and not payload.get("people"):
            payload["people"] = payload.get("org_chart") or []
            steps.append("renamed_org_chart_to_people")

        people = self._normalize_people(payload.get("people") or [])
        departments = self._normalize_departments(payload.get("departments") or [], people)
        reporting_lines = self._normalize_reporting_lines(payload.get("reporting_lines") or [], people)
        reporting_lines = self._reporting_lines_from_people(people, reporting_lines)

        payload.update(
            {
                "schema_name": "workplace_org_structure",
                "schema_version": CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
                "departments": departments,
                "people": people,
                "reporting_lines": reporting_lines,
                "department_tree": payload.get("department_tree") or self._build_department_tree(departments),
                "reporting_tree": payload.get("reporting_tree") or self._build_reporting_tree(people),
                "summary": self._build_org_summary(departments, people, reporting_lines),
                "editable_schema": payload.get("editable_schema")
                or {
                    "person_fields": ["name", "title", "department", "manager"],
                    "department_fields": ["name", "parent_id"],
                    "line_fields": ["source_name", "target_name", "type"],
                },
                "updated_at": payload.get("updated_at") or time.time(),
            }
        )
        payload.setdefault("storage", {})
        payload["storage"] = {
            **payload.get("storage", {}),
            "scope": payload.get("storage", {}).get("scope", "session_memory"),
            "status": payload.get("storage", {}).get("status", "migrated"),
            "editable": payload.get("storage", {}).get("editable", True),
        }

        if original_version != CURRENT_ORG_STRUCTURE_SCHEMA_VERSION or steps:
            payload["migration_history"] = [
                *payload.get("migration_history", []),
                {
                    "from_version": original_version,
                    "to_version": CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
                    "migrated_at": time.time(),
                    "steps": steps or ["normalized_current_org_structure"],
                },
            ]

        return payload, {
            "schema_name": "workplace_org_structure",
            "from_version": original_version,
            "to_version": CURRENT_ORG_STRUCTURE_SCHEMA_VERSION,
            "changed": original_version != CURRENT_ORG_STRUCTURE_SCHEMA_VERSION or bool(steps),
            "steps": steps,
            "person_count": len(people),
            "department_count": len(departments),
            "reporting_line_count": len(reporting_lines),
        }

    def preview_memory_migration(self, data: Dict[str, Any]) -> Dict[str, Any]:
        migrated, report = self.migrate_memory(data)
        return {"migration": report, "memory_data": migrated}

    def _memory_v1_to_v2(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
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

        org_structure, org_report = self.migrate_org_structure(data.get("org_structure", {}))
        data["org_structure"] = org_structure
        if org_report["changed"]:
            steps.append("migrated_org_structure")

        return data, steps

    def _normalize_people(self, people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        for item in people or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("label") or item.get("person") or item.get("姓名") or "").strip()
            if not name:
                continue
            department = str(
                item.get("department")
                or item.get("team")
                or item.get("dept")
                or item.get("部门")
                or "未标注部门"
            ).strip()
            manager = str(
                item.get("manager")
                or item.get("reports_to")
                or item.get("target_name")
                or item.get("直属上级")
                or ""
            ).strip()
            normalized[name] = {
                **item,
                "id": str(item.get("id") or stable_id("org_person", name)),
                "name": name,
                "title": str(item.get("title") or item.get("role") or item.get("岗位") or "").strip(),
                "department": department,
                "manager": manager,
                "manager_id": str(item.get("manager_id") or (stable_id("org_person", manager) if manager else "")),
                "source": str(item.get("source") or "migrated_memory"),
                "metadata": dict(item.get("metadata") or {}),
            }
        return sorted(normalized.values(), key=lambda item: (item["department"], item["name"]))

    def _normalize_departments(self, departments: List[Dict[str, Any]], people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_name: Dict[str, Dict[str, Any]] = {}
        for item in departments or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("department") or item.get("部门") or "").strip()
            if not name:
                continue
            by_name[name] = {
                **item,
                "id": str(item.get("id") or stable_id("dept", name)),
                "name": name,
                "parent_id": str(item.get("parent_id") or item.get("parent") or ""),
                "people": list(item.get("people") or []),
                "people_count": int(item.get("people_count") or 0),
                "manager_names": list(item.get("manager_names") or []),
            }
        for person in people:
            name = person.get("department") or "未标注部门"
            dept = by_name.setdefault(
                name,
                {
                    "id": stable_id("dept", name),
                    "name": name,
                    "parent_id": "",
                    "people": [],
                    "people_count": 0,
                    "manager_names": [],
                },
            )
            if person["name"] not in dept["people"]:
                dept["people"].append(person["name"])
            manager = person.get("manager")
            if manager and manager not in dept["manager_names"]:
                dept["manager_names"].append(manager)
            dept["people_count"] = len(dept["people"])
        return sorted(by_name.values(), key=lambda item: item["name"])

    def _normalize_reporting_lines(self, lines: List[Dict[str, Any]], people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        people_by_id = {person.get("id"): person.get("name", "") for person in people}
        normalized: Dict[tuple[str, str], Dict[str, Any]] = {}
        for item in lines or []:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or people_by_id.get(item.get("source"), "") or "").strip()
            target_name = str(item.get("target_name") or people_by_id.get(item.get("target"), "") or "").strip()
            if not source_name or not target_name:
                continue
            normalized[(source_name, target_name)] = self._line(source_name, target_name, item)
        return list(normalized.values())

    def _reporting_lines_from_people(
        self,
        people: List[Dict[str, Any]],
        existing: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        by_pair = {(line["source_name"], line["target_name"]): line for line in existing}
        for person in people:
            manager = str(person.get("manager") or "").strip()
            if manager:
                by_pair.setdefault((person["name"], manager), self._line(person["name"], manager, {}))
        return sorted(by_pair.values(), key=lambda item: (item["target_name"], item["source_name"]))

    def _line(self, source_name: str, target_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **item,
            "id": str(item.get("id") or stable_id("org_line", f"{source_name}->{target_name}")),
            "source": str(item.get("source") or stable_id("org_person", source_name)),
            "target": str(item.get("target") or stable_id("org_person", target_name)),
            "source_name": source_name,
            "target_name": target_name,
            "type": str(item.get("type") or item.get("relationship_type") or "formal_reports_to"),
            "label": str(item.get("label") or "正式汇报线"),
            "status": str(item.get("status") or "stored_org_structure"),
        }

    def _build_department_tree(self, departments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "id": dept["id"],
                "name": dept["name"],
                "people_count": dept.get("people_count", 0),
                "people": dept.get("people", []),
                "children": [],
            }
            for dept in departments
        ]

    def _build_reporting_tree(self, people: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_name = {person["name"]: person for person in people}
        children: Dict[str, List[Dict[str, Any]]] = {}
        for person in people:
            manager = str(person.get("manager") or "").strip()
            if manager:
                children.setdefault(manager, []).append(person)

        def build(person: Dict[str, Any], seen: Optional[set] = None) -> Dict[str, Any]:
            seen = set(seen or set())
            name = person["name"]
            if name in seen:
                return {**self._tree_person(person), "children": [], "cycle_detected": True}
            seen.add(name)
            return {
                **self._tree_person(person),
                "children": [build(child, seen) for child in sorted(children.get(name, []), key=lambda item: item["name"])],
            }

        roots = [person for person in people if not person.get("manager") or person.get("manager") not in by_name]
        if not roots and people:
            roots = people[:1]
        return [build(person) for person in sorted(roots, key=lambda item: item["name"])]

    def _tree_person(self, person: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": person["id"],
            "name": person["name"],
            "title": person.get("title", ""),
            "department": person.get("department", ""),
        }

    def _build_org_summary(
        self,
        departments: List[Dict[str, Any]],
        people: List[Dict[str, Any]],
        reporting_lines: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        child_names = {line.get("source_name") for line in reporting_lines}
        people_names = {person["name"] for person in people}
        roots = [
            person for person in people
            if not person.get("manager") or person["name"] not in child_names or person.get("manager") not in people_names
        ]
        return {
            "department_count": len(departments),
            "person_count": len(people),
            "reporting_line_count": len(reporting_lines),
            "root_count": len(roots),
            "unassigned_people_count": sum(1 for person in people if person.get("department") == "未标注部门"),
        }

    def _version(self, data: Any) -> int:
        if not isinstance(data, dict):
            return 1
        try:
            return int(data.get("schema_version") or data.get("memory_schema_version") or 1)
        except Exception:
            return 1

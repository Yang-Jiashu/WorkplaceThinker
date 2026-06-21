"""Multimodal organization-structure importer.

This module turns org-chart screenshots plus optional text into the same
`org_structure` contract used by the organization structure module. The VLM
call is optional and injectable so tests and local demos can run without network
access.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from .insights import OrgPerson, WorkplaceInsightEngine, json_object_from_text, stable_id


VLMFunc = Callable[[str, Sequence[str]], Awaitable[str]]


ORG_IMPORT_SYSTEM_PROMPT = """你是组织架构 OCR 与结构化抽取助手。
任务：从组织架构截图、通讯录截图、部门说明或补充文本中抽取稳定组织事实。
只抽取可见或用户明确提供的信息，不要猜测政治关系、风险、人品或动机。
输出必须是 JSON，不要 markdown。
"""


def _strip_data_url(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    if raw.startswith("data:"):
        header, _, payload = raw.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        return payload, mime
    return raw, "image/png"


def _safe_image_suffix(mime_type: str, name: str = "") -> str:
    guessed = mimetypes.guess_extension(mime_type or "") or ""
    if guessed in {".jpe"}:
        guessed = ".jpg"
    if guessed:
        return guessed
    suffix = Path(name or "").suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} else ".png"


class OrgStructureImporter:
    """Import organization structure from image and text."""

    def __init__(
        self,
        *,
        vlm_func: Optional[VLMFunc] = None,
        engine: Optional[WorkplaceInsightEngine] = None,
    ) -> None:
        self.vlm_func = vlm_func
        self.engine = engine or WorkplaceInsightEngine(enable_memory=False)

    async def import_structure(
        self,
        *,
        text: str = "",
        images: Sequence[Dict[str, Any]] = (),
        existing_org_structure: Optional[Dict[str, Any]] = None,
        use_vlm: bool = True,
    ) -> Dict[str, Any]:
        image_paths = self._materialize_images(images)
        raw_vlm = ""
        vlm_error = ""

        if use_vlm and image_paths:
            try:
                raw_vlm = await self._call_vlm(text=text, image_paths=image_paths)
            except Exception as exc:
                vlm_error = str(exc)

        extracted = self._parse_vlm_payload(raw_vlm) if raw_vlm else {}
        org_chart = self._normalize_people(extracted.get("people") or extracted.get("org_chart") or [])
        if self._looks_like_org_text(text):
            org_chart.extend(self._extract_org_chart_from_text(text))

        if not org_chart and existing_org_structure:
            org_chart.extend(self._org_structure_to_chart(existing_org_structure))

        org_chart = self.engine._dedupe_org_chart(org_chart)
        org_people = [
            OrgPerson(
                name=str(item.get("name") or "").strip(),
                title=str(item.get("title") or item.get("role") or "").strip(),
                team=str(item.get("team") or item.get("department") or item.get("dept") or "").strip(),
                manager=str(item.get("manager") or item.get("reports_to") or "").strip(),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in org_chart
            if item.get("name")
        ]
        org_structure = self.engine._build_org_structure(org_people, [], [])
        org_structure.setdefault("storage", {})
        org_structure["storage"] = {
            **org_structure["storage"],
            "source": "multimodal_org_import",
            "status": "imported",
            "editable": True,
        }

        return {
            "org_structure": org_structure,
            "org_chart": org_chart,
            "import_summary": {
                "image_count": len(image_paths),
                "text_used": bool(str(text or "").strip()),
                "vlm_used": bool(raw_vlm),
                "vlm_error": vlm_error,
                "person_count": len(org_structure.get("people", [])),
                "department_count": len(org_structure.get("departments", [])),
                "reporting_line_count": len(org_structure.get("reporting_lines", [])),
                "imported_at": time.time(),
            },
            "raw_vlm_output": raw_vlm,
        }

    def _materialize_images(self, images: Sequence[Dict[str, Any]]) -> List[str]:
        paths: List[str] = []
        for idx, item in enumerate(images or []):
            if isinstance(item, str):
                item = {"data_url": item}
            path = str(item.get("path") or "").strip()
            if path and Path(path).exists():
                paths.append(path)
                continue

            payload = str(item.get("data_url") or item.get("base64") or "").strip()
            if not payload:
                continue
            b64, inferred_mime = _strip_data_url(payload)
            mime_type = str(item.get("mime_type") or inferred_mime or "image/png")
            suffix = _safe_image_suffix(mime_type, str(item.get("name") or ""))
            try:
                raw = base64.b64decode(b64, validate=False)
            except Exception:
                continue
            target = Path(tempfile.gettempdir()) / f"workplace_org_import_{int(time.time())}_{idx}{suffix}"
            target.write_bytes(raw)
            paths.append(str(target))
        return paths

    async def _call_vlm(self, *, text: str, image_paths: Sequence[str]) -> str:
        prompt = self._build_prompt(text)
        if self.vlm_func:
            return await self.vlm_func(prompt, image_paths)

        api_key = os.getenv("VLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_BINDING_API_KEY")
        if not api_key:
            raise RuntimeError("No VLM API key configured. Set VLM_API_KEY or OPENAI_API_KEY.")

        try:
            from docthinker.auto_thinking.vlm_client import VLMClient
        except Exception as exc:
            raise RuntimeError(f"VLM client is not available: {exc}") from exc

        client = VLMClient(
            api_key=api_key,
            api_base=os.getenv("LLM_VLM_HOST") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            model=os.getenv("VLM_MODEL") or "gpt-4o-mini",
        )
        try:
            return await client.generate(
                prompt,
                images=list(image_paths),
                system_prompt=ORG_IMPORT_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.0,
            )
        finally:
            await client.close()

    def _build_prompt(self, text: str) -> str:
        return f"""
请从图片和补充文本中抽取组织架构，输出 JSON：
{{
  "people": [
    {{"name": "姓名", "title": "岗位/职级", "department": "部门/团队", "manager": "直属上级姓名"}}
  ],
  "departments": [
    {{"name": "部门名", "parent": "上级部门，可空"}}
  ],
  "reporting_lines": [
    {{"source_name": "下属姓名", "target_name": "上级姓名", "type": "formal_reports_to"}}
  ],
  "notes": ["不确定或需要用户确认的点"]
}}

规则：
1. 只抽取组织事实：部门、岗位、人员、正式汇报线。
2. 不输出风险判断、性格判断、派系判断。
3. 看不清的名字不要编造；可以放入 notes。
4. manager 字段只填直属上级。

补充文本：
{text or "无"}
""".strip()

    def _parse_vlm_payload(self, raw: str) -> Dict[str, Any]:
        parsed = json_object_from_text(raw)
        if parsed:
            return parsed
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def _normalize_people(self, people: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in people or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("person") or item.get("姓名") or "").strip()
            if not name:
                continue
            department = str(
                item.get("department")
                or item.get("team")
                or item.get("dept")
                or item.get("部门")
                or item.get("团队")
                or ""
            ).strip()
            title = str(item.get("title") or item.get("role") or item.get("岗位") or item.get("职位") or "").strip()
            manager = str(
                item.get("manager")
                or item.get("reports_to")
                or item.get("直属上级")
                or item.get("汇报对象")
                or ""
            ).strip()
            normalized.append(
                {
                    "name": name,
                    "title": title,
                    "team": department,
                    "department": department,
                    "manager": manager,
                    "metadata": {"source": "vlm_org_import"},
                }
            )
        return normalized

    def _extract_org_chart_from_text(self, text: str) -> List[Dict[str, Any]]:
        parsed = self.engine.parse_information(text or "")
        return list(parsed.get("org_chart") or [])

    def _looks_like_org_text(self, text: str) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False
        explicit_markers = (
            "组织架构",
            "组织:",
            "组织：",
            "人员:",
            "人员：",
            "成员:",
            "成员：",
            "部门:",
            "部门：",
            "org chart",
        )
        lowered = raw.lower()
        if any(marker in lowered for marker in explicit_markers):
            return True

        for line in raw.splitlines():
            value = line.strip()
            if not value:
                continue
            has_reporting_word = "汇报" in value or "reports to" in value.lower() or "manager" in value.lower()
            has_structured_separator = any(separator in value for separator in (" - ", " — ", "|", ",", "，"))
            if has_reporting_word and has_structured_separator:
                return True
        return False

    def _org_structure_to_chart(self, org_structure: Dict[str, Any]) -> List[Dict[str, Any]]:
        chart: List[Dict[str, Any]] = []
        for person in org_structure.get("people", []) or []:
            chart.append(
                {
                    "name": person.get("name", ""),
                    "title": person.get("title", ""),
                    "team": person.get("department") or person.get("team") or "",
                    "department": person.get("department") or person.get("team") or "",
                    "manager": person.get("manager", ""),
                }
            )
        return chart

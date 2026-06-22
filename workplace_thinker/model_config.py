"""Runtime model settings and provider failover for WorkplaceThinker."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import aiohttp


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


@dataclass
class ProviderConfig:
    id: str
    label: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    enabled: bool = True
    priority: int = 10
    timeout_seconds: float = 45.0
    params: Dict[str, Any] = field(default_factory=dict)

    def resolved_api_key(self) -> str:
        return self.api_key or os.getenv(self.api_key_env, "")

    def endpoint(self) -> str:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        return endpoint

    def safe_dict(self) -> Dict[str, Any]:
        data = self.__dict__.copy()
        data["api_key"] = _mask_key(self.resolved_api_key())
        data["configured"] = bool(self.resolved_api_key())
        return data


@dataclass
class ChatTemplate:
    id: str
    label: str
    system_prompt: str
    user_prefix: str = ""

    def safe_dict(self) -> Dict[str, str]:
        return self.__dict__.copy()


DEFAULT_TEMPLATES: List[ChatTemplate] = [
    ChatTemplate(
        id="evidence_first",
        label="证据优先",
        system_prompt="你是证据优先的职场分析助手。只基于材料输出可审计判断，区分事实、风险信号和假设。",
    ),
    ChatTemplate(
        id="workplace_politics",
        label="懂组织政治",
        system_prompt=(
            "你是谨慎的组织动态分析助手。关注汇报线、决策链、资源控制、责任边界和长期模式；"
            "不得把单次信号当成人格定性或事实结论。"
        ),
    ),
    ChatTemplate(
        id="newcomer_safe",
        label="新人自保",
        system_prompt="你是面向职场新人的安全行动顾问。输出要强调确认问题、书面留痕、责任边界和低冲突沟通话术。",
    ),
]


def default_providers() -> List[ProviderConfig]:
    return [
        ProviderConfig(
            id="deepseek",
            label="DeepSeek",
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            api_key_env="DEEPSEEK_API_KEY",
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            priority=10,
        ),
        ProviderConfig(
            id="siliconflow",
            label="SiliconFlow",
            base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
            api_key_env="SILICONFLOW_API_KEY",
            model=os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3"),
            priority=20,
        ),
        ProviderConfig(
            id="openai_compatible",
            label="OpenAI-compatible",
            base_url=os.getenv("LLM_BINDING_HOST", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")),
            api_key_env=os.getenv("LLM_BINDING_API_KEY_ENV", "LLM_BINDING_API_KEY"),
            api_key=os.getenv("LLM_BINDING_API_KEY", ""),
            model=os.getenv("LLM_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")),
            priority=30,
        ),
    ]


class ModelConfigManager:
    """Mutable runtime model settings used by the standalone API."""

    def __init__(self) -> None:
        self.providers = default_providers()
        self.templates = copy.deepcopy(DEFAULT_TEMPLATES)
        self.active_template_id = os.getenv("WORKPLACE_CHAT_TEMPLATE", "evidence_first")
        self.auto_failover = os.getenv("WORKPLACE_AUTO_FAILOVER", "1") != "0"
        self.last_failover: Dict[str, Any] = {}

    def safe_dict(self) -> Dict[str, Any]:
        return {
            "providers": [provider.safe_dict() for provider in self.providers],
            "templates": [template.safe_dict() for template in self.templates],
            "active_template_id": self.active_template_id,
            "auto_failover": self.auto_failover,
            "last_failover": self.last_failover,
        }

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if "auto_failover" in payload:
            self.auto_failover = bool(payload["auto_failover"])
        if payload.get("active_template_id"):
            self.active_template_id = str(payload["active_template_id"])

        provider_updates = payload.get("providers")
        if isinstance(provider_updates, list):
            by_id = {provider.id: provider for provider in self.providers}
            for item in provider_updates:
                if not isinstance(item, dict):
                    continue
                provider_id = str(item.get("id") or "").strip()
                if not provider_id:
                    continue
                provider = by_id.get(provider_id) or ProviderConfig(id=provider_id, label=provider_id)
                if item.get("label"):
                    provider.label = str(item["label"])
                if "enabled" in item:
                    provider.enabled = bool(item["enabled"])
                if "priority" in item:
                    provider.priority = int(item["priority"])
                if "timeout_seconds" in item:
                    provider.timeout_seconds = float(item["timeout_seconds"])
                if item.get("base_url") or item.get("url"):
                    provider.base_url = str(item.get("base_url") or item.get("url")).strip()
                if item.get("api_key_env"):
                    provider.api_key_env = str(item["api_key_env"]).strip()
                if "api_key" in item:
                    api_key = str(item.get("api_key") or "").strip()
                    if api_key and set(api_key) != {"*"} and "..." not in api_key:
                        provider.api_key = api_key
                if item.get("model"):
                    provider.model = str(item["model"]).strip()
                if item.get("chat_model") and not item.get("model"):
                    provider.model = str(item["chat_model"]).strip()
                params = item.get("params", item.get("official_params", item.get("extra_body")))
                if isinstance(params, dict):
                    provider.params = params
                by_id[provider_id] = provider
            self.providers = list(by_id.values())

        template_updates = payload.get("templates")
        if isinstance(template_updates, list):
            by_id = {template.id: template for template in self.templates}
            for item in template_updates:
                if not isinstance(item, dict):
                    continue
                template_id = str(item.get("id") or "").strip()
                if not template_id:
                    continue
                by_id[template_id] = ChatTemplate(
                    id=template_id,
                    label=str(item.get("label") or template_id),
                    system_prompt=str(item.get("system_prompt") or ""),
                    user_prefix=str(item.get("user_prefix") or ""),
                )
            self.templates = list(by_id.values())
        return self.safe_dict()

    def template(self) -> ChatTemplate:
        for template in self.templates:
            if template.id == self.active_template_id:
                return template
        return self.templates[0]

    def ordered_providers(self, *, vision: bool = False) -> List[ProviderConfig]:
        providers = [provider for provider in self.providers if provider.enabled and provider.resolved_api_key() and provider.model]
        return sorted(providers, key=lambda item: item.priority)


class ModelRouter:
    """OpenAI-compatible chat/VLM router with failover."""

    def __init__(self, manager: ModelConfigManager) -> None:
        self.manager = manager

    async def generate_text(self, prompt: str) -> str:
        template = self.manager.template()
        final_prompt = f"{template.user_prefix}\n{prompt}".strip() if template.user_prefix else prompt
        messages = [
            {"role": "system", "content": template.system_prompt},
            {"role": "user", "content": final_prompt},
        ]
        return await self._generate(messages=messages, vision=False)

    async def generate_vision(self, prompt: str, image_paths: Sequence[str]) -> str:
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        return await self._generate(messages=messages, images=image_paths, vision=True)

    async def _generate(
        self,
        *,
        messages: List[Dict[str, Any]],
        images: Sequence[str] = (),
        vision: bool = False,
    ) -> str:
        providers = self.manager.ordered_providers(vision=vision)
        if not providers:
            raise RuntimeError("No configured model provider is available.")

        errors = []
        attempt_count = len(providers) if self.manager.auto_failover else 1
        for provider in providers[:attempt_count]:
            try:
                result = await self._call_provider(provider, messages=messages, images=images, vision=vision)
                self.manager.last_failover = {
                    "used_provider": provider.id,
                    "mode": "vision" if vision else "chat",
                    "failed_providers": errors,
                    "updated_at": time.time(),
                }
                return result
            except Exception as exc:
                errors.append({"provider": provider.id, "error": str(exc)})
                if not self.manager.auto_failover:
                    break
        self.manager.last_failover = {
            "used_provider": "",
            "mode": "vision" if vision else "chat",
            "failed_providers": errors,
            "updated_at": time.time(),
        }
        raise RuntimeError(f"All model providers failed: {errors}")

    async def _call_provider(
        self,
        provider: ProviderConfig,
        *,
        messages: List[Dict[str, Any]],
        images: Sequence[str],
        vision: bool,
    ) -> str:
        payload_messages = copy.deepcopy(messages)
        if vision and images:
            content = payload_messages[-1].setdefault("content", [])
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
                payload_messages[-1]["content"] = content
            for path in images:
                content.append(self._image_part(path))

        payload: Dict[str, Any] = {
            "model": provider.model,
            "messages": payload_messages,
        }
        payload.update(provider.params or {})

        headers = {"Authorization": f"Bearer {provider.resolved_api_key()}", "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=float(provider.timeout_seconds))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(provider.endpoint(), headers=headers, data=json.dumps(payload), timeout=timeout) as response:
                text = await response.text()
                if response.status >= 400:
                    raise RuntimeError(f"{response.status}: {text[:500]}")
                data = json.loads(text)
        return data["choices"][0]["message"]["content"]

    def _image_part(self, path: str) -> Dict[str, Any]:
        from docthinker.auto_thinking.vlm_client import VLMClient

        return VLMClient._encode_image(path)


runtime_model_config = ModelConfigManager()
runtime_model_router = ModelRouter(runtime_model_config)

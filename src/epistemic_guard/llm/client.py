from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional, TypeVar
import yaml
from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel

from epistemic_guard.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def clean_json_payload(raw: str) -> str:
    """Extract clean JSON string from raw text, stripping markdown code fences or conversational text."""
    trimmed = raw.strip()
    # Check for markdown code fences (```json ... ``` or ``` ... ```)
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", trimmed)
    if match:
        trimmed = match.group(1).strip()
        return trimmed

    # If starts with { and ends with } or [ and ]
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        return trimmed

    # Find first { and last }
    first_brace = trimmed.find("{")
    last_brace = trimmed.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return trimmed[first_brace : last_brace + 1]

    return trimmed


class StructuredLLMClient:
    """Model-agnostic structured LLM client.

    Interfaces with local models (Ollama, vLLM, llama.cpp) and cloud providers adhering to the
    OpenAI-compatible specification. Supports native JSON schema parsing with fallback for
    local endpoints that return raw or markdown-wrapped JSON text.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompts_path: Optional[Path | str] = None,
        client: Optional[OpenAI] = None,
        async_client: Optional[AsyncOpenAI] = None,
    ) -> None:
        self.settings = settings or get_settings()

        # Resolve prompts configuration
        if prompts_path is not None:
            self._prompts_path = Path(prompts_path)
        else:
            self._prompts_path = self._resolve_prompts_path()

        self._prompts: dict[str, Any] = {}
        self._load_prompts()

        # Initialize clients (allow dependency injection for testing)
        api_key_val = (
            self.settings.openai_api_key.get_secret_value()
            if self.settings.openai_api_key
            else "dummy-local-key"
        )

        self._client = client or OpenAI(
            base_url=self.settings.openai_base_url,
            api_key=api_key_val,
            timeout=self.settings.request_timeout,
        )

        self._async_client = async_client or AsyncOpenAI(
            base_url=self.settings.openai_base_url,
            api_key=api_key_val,
            timeout=self.settings.request_timeout,
        )

    def _resolve_prompts_path(self) -> Path:
        """Resolve path to prompts.yaml."""
        cwd_path = Path.cwd() / "config" / "prompts.yaml"
        if cwd_path.exists():
            return cwd_path
        package_root = Path(__file__).resolve().parent.parent.parent.parent
        pkg_path = package_root / "config" / "prompts.yaml"
        if pkg_path.exists():
            return pkg_path
        return cwd_path

    def _load_prompts(self) -> None:
        """Load versioned prompt templates from prompts.yaml."""
        if self._prompts_path.exists():
            with open(self._prompts_path, "r", encoding="utf-8") as f:
                self._prompts = yaml.safe_load(f) or {}

    def get_prompt_template(self, prompt_name: str) -> dict[str, str]:
        """Retrieve a specific prompt definition by key."""
        if prompt_name not in self._prompts:
            raise KeyError(f"Prompt template '{prompt_name}' not found in {self._prompts_path}")
        return self._prompts[prompt_name]

    def render_messages(self, prompt_name: str, **kwargs: Any) -> list[dict[str, str]]:
        """Render system and user messages from prompt template."""
        template = self.get_prompt_template(prompt_name)
        system_text = template.get("system", "").strip()
        user_template = template.get("user", "").strip()
        user_text = user_template.format(**kwargs)

        messages = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        messages.append({"role": "user", "content": user_text})
        return messages

    def generate_structured(
        self,
        prompt_name: str,
        response_model: type[T],
        prompt_vars: Optional[dict[str, Any]] = None,
    ) -> T:
        """Generate structured data conforming to a Pydantic model.

        Attempts native beta.chat.completions.parse first, with robust fallback to standard
        chat completions and JSON parsing for local engines like Ollama, vLLM, and llama.cpp.
        """
        vars_dict = prompt_vars or {}
        messages = self.render_messages(prompt_name, **vars_dict)

        # 1. Try native Pydantic parse (supported on OpenAI and modern vLLM)
        try:
            completion = self._client.beta.chat.completions.parse(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                response_format=response_model,
                temperature=self.settings.temperature,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception as e:
            logger.debug("Native parse failed or unsupported on this endpoint (%s); falling back to raw JSON mode.", e)

        # 2. Fallback: Standard completion with json_object format or raw text
        raw_text = ""
        try:
            completion_fallback = self._client.chat.completions.create(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                temperature=self.settings.temperature,
            )
            raw_text = completion_fallback.choices[0].message.content or ""
        except Exception as e2:
            logger.debug("json_object format failed (%s); trying plain completion.", e2)
            completion_raw = self._client.chat.completions.create(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.settings.temperature,
            )
            raw_text = completion_raw.choices[0].message.content or ""

        # Clean and parse JSON
        cleaned = clean_json_payload(raw_text)
        try:
            return response_model.model_validate_json(cleaned)
        except Exception as parse_err:
            # Try json.loads first to give clearer error or handle subtle dict conversion
            data = json.loads(cleaned)
            return response_model.model_validate(data)

    async def async_generate_structured(
        self,
        prompt_name: str,
        response_model: type[T],
        prompt_vars: Optional[dict[str, Any]] = None,
    ) -> T:
        """Asynchronous structured generation conforming to a Pydantic model."""
        vars_dict = prompt_vars or {}
        messages = self.render_messages(prompt_name, **vars_dict)

        try:
            completion = await self._async_client.beta.chat.completions.parse(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                response_format=response_model,
                temperature=self.settings.temperature,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is not None:
                return parsed
        except Exception as e:
            logger.debug("Async native parse failed (%s); falling back to raw completion.", e)

        raw_text = ""
        try:
            completion_fallback = await self._async_client.chat.completions.create(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                temperature=self.settings.temperature,
            )
            raw_text = completion_fallback.choices[0].message.content or ""
        except Exception:
            completion_raw = await self._async_client.chat.completions.create(
                model=self.settings.openai_model_name,
                messages=messages,  # type: ignore[arg-type]
                temperature=self.settings.temperature,
            )
            raw_text = completion_raw.choices[0].message.content or ""

        cleaned = clean_json_payload(raw_text)
        try:
            return response_model.model_validate_json(cleaned)
        except Exception:
            data = json.loads(cleaned)
            return response_model.model_validate(data)

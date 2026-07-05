from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

from agents.shared import text


class AgenticAIClient:
    """Shared AI client for agents that need structured JSON reasoning."""

    def __init__(
        self,
        provider: str | None = None,
        provider_env: str | None = None,
        api_key_env: str | None = None,
        model_env: str | None = None,
        base_url_env: str | None = None,
        ssl_verify_env: str | None = None,
    ) -> None:
        load_dotenv(override=True)
        configured_provider = (
            provider
            or (os.getenv(provider_env) if provider_env else None)
            or os.getenv("AI_PROVIDER", "groq")
        )
        self.provider = configured_provider.strip().lower()
        if self.provider not in {"openai", "gemini", "groq"}:
            self.provider = "groq"
        self.api_key_env = api_key_env
        self.model_env = model_env
        self.base_url_env = base_url_env
        self.ssl_verify_env = ssl_verify_env

    def complete_json(
        self,
        system_prompt: str,
        task_prompt: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        prompt_bytes = len(system_prompt.encode("utf-8")) + len(
            task_prompt.encode("utf-8")
        )
        try:
            if self.provider == "gemini":
                result = self._call_gemini(system_prompt, task_prompt)
            elif self.provider == "groq":
                result = self._call_groq(system_prompt, task_prompt)
            else:
                result = self._call_openai(system_prompt, task_prompt)
            result["ai_used"] = True
            result["provider"] = self.provider
            result["mode"] = self.provider
            result["prompt_bytes"] = prompt_bytes
            return result
        except Exception as exc:
            result = dict(fallback)
            result["ai_used"] = False
            result["provider"] = self.provider
            result["mode"] = "fallback"
            result["error"] = str(exc)
            result["friendly_error"] = self._friendly_error(exc)
            result["prompt_bytes"] = prompt_bytes
            return result

    def _call_openai(self, system_prompt: str, task_prompt: str) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        verify_ssl = os.getenv("OPENAI_SSL_VERIFY", "true").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        return self._chat_completions(
            url=f"{base_url}/chat/completions",
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            verify_ssl=verify_ssl,
        )

    def _call_groq(self, system_prompt: str, task_prompt: str) -> dict[str, Any]:
        api_key_env = self.api_key_env or "GROQ_API_KEY"
        api_key = os.getenv(api_key_env) or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(f"{api_key_env} is missing.")
        model = (
            os.getenv(self.model_env or "GROQ_MODEL")
            or os.getenv("GROQ_MODEL")
            or "llama-3.1-8b-instant"
        )
        base_url = self._groq_base_url(
            os.getenv(self.base_url_env or "GROQ_BASE_URL", "https://api.groq.com")
        )
        verify_ssl = os.getenv(
            self.ssl_verify_env or "GROQ_SSL_VERIFY", "false"
        ).strip().lower() not in {
            "0",
            "false",
            "no",
        }
        return self._chat_completions(
            url=f"{base_url}/chat/completions",
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            verify_ssl=verify_ssl,
        )

    def _groq_base_url(self, value: str) -> str:
        base_url = (value or "https://api.groq.com").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url.removesuffix("/chat/completions")
        if base_url.endswith("/openai/v1") or base_url.endswith("/v1"):
            return base_url
        return f"{base_url}/openai/v1"

    def _chat_completions(
        self,
        url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        task_prompt: str,
        verify_ssl: bool,
    ) -> dict[str, Any]:
        body = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ],
        }
        with httpx.Client(verify=verify_ssl, timeout=25) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
        return self._parse_json(data["choices"][0]["message"]["content"])

    def _call_gemini(self, system_prompt: str, task_prompt: str) -> dict[str, Any]:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing.")
        model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        verify_ssl = os.getenv("GEMINI_SSL_VERIFY", "false").strip().lower() not in {
            "0",
            "false",
            "no",
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"{system_prompt}\n\n{task_prompt}\n\n"
                                "Return JSON only. Do not use markdown."
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
            },
        }
        with httpx.Client(verify=verify_ssl, timeout=25) as client:
            response = client.post(url, params={"key": api_key}, json=body)
            response.raise_for_status()
            data = response.json()
        return self._parse_json(data["candidates"][0]["content"]["parts"][0]["text"])

    def _parse_json(self, content: Any) -> dict[str, Any]:
        raw = text(content)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _friendly_error(self, exc: Exception) -> str:
        message = str(exc)
        if "413" in message or "Payload Too Large" in message:
            return (
                "AI request payload was too large. Agent should send a compact "
                "handoff with only relevant fields/rules."
            )
        if "429" in message or "Too Many Requests" in message:
            return (
                "AI provider is rate-limiting requests. Retry after a short wait "
                "or switch provider/model; deterministic guardrails are used as fallback."
            )
        if "401" in message or "403" in message:
            return "AI provider rejected the API key or permission."
        return "AI provider call failed; deterministic guardrails are used as fallback."

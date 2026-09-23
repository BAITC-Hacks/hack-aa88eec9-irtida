"""Small server-only NVIDIA adapter; no retries, redirects or implicit .env reads."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

import httpx


NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
MAX_CONTEXT_BYTES = 65_536
MAX_PROMPT_BYTES = 32_768
MAX_RESPONSE_BYTES = 131_072


class NvidiaAPIError(RuntimeError):
    """Safe public error: provider bodies, credentials and employee data are omitted."""

    MESSAGES = {
        "configuration": "Invalid NVIDIA configuration. Check the module environment variables.",
        "missing_key": "NVIDIA_API_KEY is missing. Configure a server key or explicitly enable mock mode.",
        "invalid_context": "NVIDIA context must be a finite JSON object within the request size limit.",
        "unauthorized": "NVIDIA rejected the API key (401). Check the server-side key.",
        "forbidden": "NVIDIA denied access (403). Check account and model permissions.",
        "rate_limited": "NVIDIA request limit reached (429). Wait and check account quota.",
        "invalid_model": "NVIDIA model or endpoint is unavailable (404). Check NVIDIA_MODEL and catalog access.",
        "invalid_request": "NVIDIA rejected the request. Check model availability and supported parameters.",
        "unavailable": "NVIDIA is temporarily unavailable. Retry later explicitly.",
        "pending": "NVIDIA returned a pending result. This one-request adapter does not poll.",
        "redirect": "NVIDIA returned a redirect, which this adapter will not follow.",
        "http_error": "NVIDIA returned an unexpected HTTP status.",
        "timeout": "NVIDIA request exceeded the configured total timeout.",
        "network": "Could not connect to NVIDIA. Check the network and try again later.",
        "response_too_large": "NVIDIA response exceeded the configured size limit.",
        "invalid_response": "NVIDIA returned an invalid chat response.",
        "truncated": "NVIDIA output was incomplete. Reduce requested content or increase the token limit.",
        "refused": "NVIDIA could not produce a recommendation for this request.",
    }

    def __init__(self, code: str, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(self.MESSAGES.get(code, "NVIDIA request failed."))


@dataclass(frozen=True)
class NvidiaSettings:
    api_key: str = field(default="", repr=False)
    model: str = DEFAULT_MODEL
    mock: bool = False
    timeout_seconds: float = 20.0
    max_tokens: int = 1800

    def __post_init__(self) -> None:
        valid_key = (
            isinstance(self.api_key, str)
            and len(self.api_key) <= 4096
            and (not self.api_key or all(33 <= ord(char) <= 126 for char in self.api_key))
        )
        valid_model = isinstance(self.model, str) and re.fullmatch(
            r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", self.model
        ) is not None and len(self.model) <= 200
        valid_timeout = (
            type(self.timeout_seconds) in (int, float)
            and math.isfinite(self.timeout_seconds)
            and 0.05 <= self.timeout_seconds <= 120
        )
        valid_tokens = type(self.max_tokens) is int and 128 <= self.max_tokens <= 4096
        if not all((valid_key, valid_model, valid_timeout, valid_tokens, type(self.mock) is bool)):
            raise NvidiaAPIError("configuration")

    @classmethod
    def from_env(cls) -> "NvidiaSettings":
        """Read process variables only. The caller explicitly chooses any .env file."""
        try:
            raw_mock = os.getenv("NVIDIA_AI_MOCK", "false").strip().lower()
            if raw_mock not in {"true", "false", "1", "0"}:
                raise NvidiaAPIError("configuration")
            return cls(
                api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
                model=os.getenv("NVIDIA_MODEL", DEFAULT_MODEL).strip(),
                mock=raw_mock in {"true", "1"},
                timeout_seconds=float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "20")),
                max_tokens=int(os.getenv("NVIDIA_MAX_TOKENS", "1800")),
            )
        except (ValueError, TypeError, OverflowError):
            raise NvidiaAPIError("configuration") from None


class NvidiaClient:
    """One bounded hosted inference call. Mock personalization belongs to the service."""

    def __init__(
        self,
        settings: NvidiaSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    async def complete(self, system_prompt: str, context: dict[str, Any]) -> str:
        if not self.settings.api_key:
            raise NvidiaAPIError("missing_key")
        if not isinstance(context, dict) or not isinstance(system_prompt, str) or not system_prompt.strip():
            raise NvidiaAPIError("invalid_context")
        try:
            context_json = json.dumps(context, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            if len(context_json.encode("utf-8")) > MAX_CONTEXT_BYTES:
                raise NvidiaAPIError("invalid_context")
            if len(system_prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
                raise NvidiaAPIError("invalid_context")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise NvidiaAPIError("invalid_context") from None

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_json},
            ],
            "max_tokens": self.settings.max_tokens,
            "stream": False,
            "temperature": 0.2,
        }
        if self.settings.model == DEFAULT_MODEL:
            # Official Nemotron 3 Super serving recommendation; disable reasoning
            # so the small completion budget is reserved for the JSON answer.
            payload.update(
                temperature=1.0,
                top_p=0.95,
                chat_template_kwargs={"enable_thinking": False},
            )
        try:
            # Outer deadline includes receiving the body and closing HTTP resources.
            async with asyncio.timeout(self.settings.timeout_seconds):
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=httpx.Timeout(self.settings.timeout_seconds),
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        NVIDIA_URL,
                        headers={
                            "Authorization": f"Bearer {self.settings.api_key}",
                            "Accept": "application/json",
                        },
                        json=payload,
                    ) as response:
                        self._check_status(response.status_code)
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                                raise NvidiaAPIError("response_too_large")
                            body.extend(chunk)
                        result = self._parse_envelope(bytes(body))
                return result
        except (TimeoutError, httpx.TimeoutException):
            raise NvidiaAPIError("timeout") from None
        except httpx.RequestError:
            raise NvidiaAPIError("network") from None

    @staticmethod
    def _check_status(status: int) -> None:
        if status == 200:
            return
        code = {
            202: "pending", 400: "invalid_request", 401: "unauthorized",
            403: "forbidden", 404: "invalid_model", 422: "invalid_request",
            429: "rate_limited",
        }.get(status)
        if code is None:
            code = "redirect" if 300 <= status < 400 else "unavailable" if status >= 500 else "http_error"
        raise NvidiaAPIError(code, status_code=status)

    @staticmethod
    def _parse_envelope(body: bytes) -> str:
        try:
            payload = json.loads(body)
            choices = payload["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise NvidiaAPIError("invalid_response")
            choice = choices[0]
            message = choice["message"]
            if not isinstance(message, dict) or message.get("role") != "assistant":
                raise NvidiaAPIError("invalid_response")
            if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                raise NvidiaAPIError("refused")
            if choice.get("finish_reason") == "length":
                raise NvidiaAPIError("truncated")
            if choice.get("finish_reason") != "stop" or message.get("tool_calls"):
                raise NvidiaAPIError("invalid_response")
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise NvidiaAPIError("invalid_response")
            return content
        except (ValueError, TypeError, KeyError, IndexError, UnicodeError, RecursionError):
            raise NvidiaAPIError("invalid_response") from None

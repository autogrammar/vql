"""OpenRouter-compatible vision LLM client for VQL extraction."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from img2vql.contracts import response_format
from img2vql.pipeline.config import DEFAULT_VQL_VISION_MODEL, PipelineLLMConfig

try:
    from subllm import complete as subllm_complete
except ImportError:
    subllm_complete = None


class LLMClientError(RuntimeError):
    pass


def _image_to_data_url(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower().lstrip(".") or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(
        suffix, "png"
    )
    raw = p.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def _messages_have_image(messages: Sequence[Mapping[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "image_url":
                return True
    return False


def chat_completion(
    config: PipelineLLMConfig,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    if not config.configured:
        raise LLMClientError(
            "LLM not configured: set VQL_LLM_ENABLED=1 and OPENROUTER_API_KEY in .env"
        )

    if _messages_have_image(messages):
        if subllm_complete is None:
            raise LLMClientError("subactor-subllm is not installed")
        try:
            response = subllm_complete(
                "autogrammar-vql",
                "vision",
                messages,
                response_format=response_format(),
                timeout_seconds=float(config.timeout_s),
                credentials={"openrouter": config.api_key},
            )
        except Exception as exc:
            raise LLMClientError(f"SubLLM vision request failed: {exc}") from exc
        return {
            "content": response.content,
            "model": response.model,
            "usage": dict(response.usage),
            "raw": {},
        }

    body = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": response_format(),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
            "HTTP-Referer": os.environ.get("OPENROUTER_APP_URL", "").strip()
            or os.environ.get("OPENROUTER_SITE_URL", "").strip()
            or "https://github.com/oqlos/vql",
            "X-OpenRouter-Title": os.environ.get("OPENROUTER_APP_NAME", "").strip()
            or Path.cwd().name
            or "vql",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code == 400 and "not a valid model" in detail.lower():
            hint = (
                f" Set VQL_LLM_MODEL to a valid OpenRouter vision slug, e.g. "
                f"{DEFAULT_VQL_VISION_MODEL} (not openrouter/... prefix)."
            )
        raise LLMClientError(f"LLM HTTP {exc.code}: {detail}{hint}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"LLM request failed: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise LLMClientError(f"LLM empty response: {payload}")
    message = choices[0].get("message") or {}
    return {
        "content": message.get("content", ""),
        "model": payload.get("model", config.model),
        "usage": payload.get("usage", {}),
        "raw": payload,
    }


def build_vision_user_message(
    *,
    text: str,
    image_path: str | Path | None,
    use_vision: bool,
) -> dict[str, Any]:
    if use_vision and image_path and Path(image_path).is_file():
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": _image_to_data_url(image_path)},
                },
            ],
        }
    return {"role": "user", "content": text}

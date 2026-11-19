"""OpenRouter client wrapper; credentials are read only from the environment."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import APIError, OpenAI

load_dotenv()


class LLMConfigurationError(RuntimeError):
    """Raised when required AI credentials are not configured."""


class LLMServiceError(RuntimeError):
    """Raised when the model cannot return usable JSON."""


def generate_json(prompt: str) -> dict[str, Any]:
    """Generate a JSON object with OpenRouter; no API key is stored in source."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "AI analysis requires OPENROUTER_API_KEY. Add an OpenRouter API key "
            "to your local .env file or set it as an environment variable."
        )

    model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except APIError as exc:
        raise LLMServiceError(f"OpenRouter request failed: {exc}") from exc

    choices = response.choices
    response_text = choices[0].message.content if choices else None
    if not response_text or not response_text.strip():
        raise LLMServiceError("OpenRouter returned an empty response.")
    cleaned = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$", "", response_text, flags=re.IGNORECASE
    )
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMServiceError("OpenRouter did not return valid JSON.") from exc
    if not isinstance(result, dict):
        raise LLMServiceError("OpenRouter response must be a JSON object.")
    return result

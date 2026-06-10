"""
anthropic_client.py (replaces xai_client.py)
Thin wrapper around the Anthropic Messages API.
"""

import os

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class AnthropicConfigError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is not set."""


def chat_completion(messages: list[dict], max_tokens: int = 1000, temperature: float = 0.2) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise AnthropicConfigError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]

    kwargs: dict = {
        "model": os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": user_messages,
    }
    if system_parts:
        kwargs["system"] = system_parts[0]

    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()

"""LLM client with multi-provider support (Anthropic, Upstage fallback).

Prioritizes Anthropic API via Prism, falls back to Upstage if ANTHROPIC_API_KEY
is not available but UPSTAGE_API_KEY is present.

Environment variables:
    ANTHROPIC_API_KEY   — Primary (Prism gateway)
    UPSTAGE_API_KEY     — Fallback
    LLM_BASE_URL        — Override base URL (default: https://prism.ch.dev)
    JUDGE_MODEL         — Override model (default: anthropic/claude-sonnet-4-6)
"""

from __future__ import annotations

import os
import sys
from typing import Any, Literal

from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()

# Provider detection
ProviderType = Literal["anthropic", "upstage"]


def detect_provider() -> tuple[ProviderType, str]:
    """Detect available LLM provider and return (provider_type, api_key).

    Returns:
        (provider_type, api_key): "anthropic" or "upstage" and the API key

    Raises:
        RuntimeError: If neither API key is available
    """
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    upstage_key = os.environ.get("UPSTAGE_API_KEY")

    if anthropic_key:
        return ("anthropic", anthropic_key)
    elif upstage_key:
        print("[llm_client] ANTHROPIC_API_KEY not found, using UPSTAGE_API_KEY fallback", file=sys.stderr)
        return ("upstage", upstage_key)
    else:
        raise RuntimeError(
            "No LLM API key found. Set ANTHROPIC_API_KEY or UPSTAGE_API_KEY in .env or environment."
        )


def get_base_url(provider: ProviderType) -> str:
    """Get base URL for the provider.

    Args:
        provider: Provider type

    Returns:
        Base URL string
    """
    # Allow explicit override
    if override := os.environ.get("LLM_BASE_URL"):
        return override

    # Provider defaults
    if provider == "anthropic":
        return "https://prism.ch.dev"
    elif provider == "upstage":
        return "https://api.upstage.ai/v1/solar"

    return "https://prism.ch.dev"  # fallback


def get_model_name(provider: ProviderType) -> str:
    """Get default model name for the provider.

    Args:
        provider: Provider type

    Returns:
        Model name string
    """
    # Allow explicit override
    if override := os.environ.get("JUDGE_MODEL"):
        return override

    # Provider defaults
    if provider == "anthropic":
        return "anthropic/claude-sonnet-4-6"
    elif provider == "upstage":
        return "solar-pro"  # Upstage's flagship model

    return "anthropic/claude-sonnet-4-6"  # fallback


def create_llm_client() -> tuple[AsyncAnthropic, str, ProviderType]:
    """Create LLM client with automatic provider detection.

    Returns:
        (client, model_name, provider_type)

    Raises:
        RuntimeError: If no API key is available
    """
    provider, api_key = detect_provider()
    base_url = get_base_url(provider)
    model_name = get_model_name(provider)

    # Create client (Anthropic SDK is compatible with OpenAI-like APIs)
    client = AsyncAnthropic(
        api_key=api_key,
        base_url=base_url,
    )

    print(f"[llm_client] Using provider={provider}, model={model_name}, base_url={base_url}")

    return client, model_name, provider


def prepare_messages_for_provider(
    provider: ProviderType,
    system: str,
    user: str,
) -> dict[str, Any]:
    """Prepare message format for the provider.

    Args:
        provider: Provider type
        system: System prompt
        user: User prompt

    Returns:
        Dict with provider-specific message format
    """
    # Both Anthropic and Upstage use the same format
    return {
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": user,
            }
        ],
    }


async def call_llm(
    client: AsyncAnthropic,
    provider: ProviderType,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4000,
    temperature: float = 1.0,
) -> str:
    """Call LLM with provider-specific handling.

    Args:
        client: AsyncAnthropic client
        provider: Provider type
        model: Model name
        system: System prompt
        user: User prompt
        max_tokens: Max tokens to generate
        temperature: Temperature (0.0 - 2.0)

    Returns:
        Generated text string
    """
    message_params = prepare_messages_for_provider(provider, system, user)

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        **message_params,
    )

    # Extract text from response
    if response.content and len(response.content) > 0:
        return response.content[0].text

    return ""

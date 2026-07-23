"""
Provider configuration — deduplicated from config.py and llm/__init__.py.
Single source of truth for provider detection, credentials, and model resolution.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ── Provider constants ────────────────────────────────────────────────

VALID_PROVIDERS = {"openai", "anthropic", "google", "ollama", "deepseek", "zai", "openrouter"}

PROVIDER_NAMES = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "ollama": "Ollama",
    "zai": "Z.ai (GLM)",
    "openrouter": "OpenRouter",
}

PROVIDER_DEFAULTS = {
    "openai": {
        "env_key": "OPENAI_API_KEY",
        "env_base": "OPENAI_BASE_URL",
        "env_model": "OPENAI_MODEL",
        "default_base": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "env_base": "ANTHROPIC_BASE_URL",
        "env_model": "ANTHROPIC_MODEL",
        "default_base": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
    },
    "google": {
        "env_key": "GOOGLE_API_KEY",
        "env_base": "GOOGLE_BASE_URL",
        "env_model": "GOOGLE_MODEL",
        "default_base": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.0-flash",
    },
    "ollama": {
        "env_key": None,
        "env_base": "OLLAMA_HOST",
        "env_model": "OLLAMA_MODEL",
        "default_base": "http://localhost:11434",
        "default_model": "codellama",
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "env_base": "CODING_AGENT_BASE_URL",
        "env_model": "CODING_AGENT_MODEL",
        "default_base": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "zai": {
        "env_key": "ZAI_API_KEY",
        "env_base": "ZAI_BASE_URL",
        "env_model": "ZAI_MODEL",
        "default_base": "https://api.z.ai/api/paas/v4",
        "default_model": "glm-4.5",
    },
    "openrouter": {
        "env_key": "OPENROUTER_API_KEY",
        "env_base": "OPENROUTER_BASE_URL",
        "env_model": "OPENROUTER_MODEL",
        "default_base": "https://openrouter.ai/api/v1",
        "default_model": "deepseek/deepseek-chat-v3.1",
    },
}


# ── Configuration data class ──────────────────────────────────────────


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 8192
    thinking: bool = False
    provider: str = "deepseek"


# ── Detection logic ───────────────────────────────────────────────────


def detect_provider() -> str | None:
    """Auto-detect which provider to use based on environment variables.
    Returns provider name or None if DeepSeek (fallback) should be used."""
    explicit = os.environ.get("CODING_AGENT_PROVIDER", "").lower().strip()
    if explicit in VALID_PROVIDERS:
        return explicit

    # Check env vars in priority order
    checks = [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
        ("zai", "ZAI_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("ollama", "OLLAMA_MODEL"),
    ]
    for provider, env_var in checks:
        if os.environ.get(env_var):
            return provider

    # Check DeepSeek
    if os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("CODING_AGENT_API_KEY"):
        return "deepseek"

    return None


def resolve_provider_config(provider: str | None = None) -> dict:
    """Build a full provider config dict. Returns the standard config fields."""
    if not provider:
        provider = detect_provider() or "deepseek"

    provider = provider.lower()
    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["deepseek"])

    api_key = ""
    if defaults["env_key"]:
        api_key = os.environ.get(defaults["env_key"], "") or os.environ.get(
            "CODING_AGENT_API_KEY", ""
        )

    base_url = os.environ.get(defaults["env_base"], defaults["default_base"])
    model_name = os.environ.get(defaults["env_model"], defaults["default_model"])

    # For DeepSeek, resolve "auto" model
    if provider == "deepseek":
        raw_model = os.environ.get("CODING_AGENT_MODEL", "auto")
        if raw_model == "auto" or raw_model.lower() == "auto":
            try:
                from model_resolver import resolve_model as resolve_deepseek_model

                model_name = resolve_deepseek_model(
                    api_key=api_key or os.environ.get("CODING_AGENT_API_KEY", ""),
                    base_url=base_url,
                    preferred="auto",
                    thinking=os.environ.get("CODING_AGENT_THINKING", "").lower()
                    in ("1", "true", "yes"),
                )
            except Exception:
                model_name = defaults["default_model"]
        else:
            model_name = raw_model

    thinking = os.environ.get("CODING_AGENT_THINKING", "").lower() in ("1", "true", "yes")

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model_name,
        "raw_model": os.environ.get(defaults["env_model"], defaults["default_model"]),
        "provider": provider,
        "thinking": thinking,
    }


def build_llm_config(provider: str | None = None) -> LLMConfig:
    """Build an LLMConfig from environment variables."""
    cfg = resolve_provider_config(provider)
    return LLMConfig(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
        provider=cfg["provider"],
        thinking=cfg.get("thinking", False),
    )


def detect_api_format(provider: str) -> str:
    """Determine the API format for a provider."""
    formats = {
        "openai": "openai",  # OpenAI-compatible chat completions
        "anthropic": "anthropic",  # Anthropic Messages API
        "google": "google",  # Google Generative AI
        "ollama": "openai",  # Ollama uses OpenAI-compatible
        "deepseek": "openai",  # DeepSeek uses OpenAI-compatible
        "zai": "openai",  # Z.ai GLM uses OpenAI-compatible endpoint
        "openrouter": "openai",  # OpenRouter uses OpenAI-compatible
    }
    return formats.get(provider, "openai")

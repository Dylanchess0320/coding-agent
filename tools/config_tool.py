"""
Config tool - read/write LuckyD Code settings mid-session.
"""

from __future__ import annotations

from .base import ToolBase, ToolOutput
from .registry import register_tool

# Supported settings and their defaults
_SUPPORTED = {"model", "max_tokens", "temperature", "theme", "verify_edits", "max_turns", "effort"}
_DEFAULTS = {
    "model": "deepseek",
    "max_tokens": 4096,
    "temperature": 0.7,
    "theme": "dark",
    "verify_edits": True,
    "max_turns": 15,
    "effort": "normal",
}

# In-memory overrides (doesn't persist to config.py)
_overrides: dict = {}


def get_config_overrides() -> dict:
    return dict(_overrides)


class ConfigTool(ToolBase):
    name = "Config"
    description = "Read or write LuckyD Code settings mid-session. Omit value to read, provide value to update. Supported: model, max_tokens, temperature, theme, verify_edits, max_turns, effort."
    aliases = ["Settings", "SetConfig"]
    parameters = {
        "setting": {
            "type": "string",
            "description": "The setting key. Supported: model, max_tokens, temperature, theme, verify_edits, max_turns, effort",
        },
        "value": {
            "type": ["string", "boolean", "number", "null"],
            "description": "New value to set. Omit to read current.",
        },
    }

    async def execute(self, setting: str, value=None) -> ToolOutput:
        if setting not in _SUPPORTED:
            return ToolOutput(
                text=f"Unknown setting: '{setting}'. Supported: {', '.join(sorted(_SUPPORTED))}",
                error=True,
            )

        if value is None:
            # Read mode
            current = _overrides.get(setting, _DEFAULTS.get(setting, "N/A"))
            return ToolOutput(
                text=f"**{setting}** = `{current!r}`",
                title=f"Config: {setting}",
                metadata={"setting": setting, "value": current},
            )

        # Write mode
        _overrides[setting] = value
        return ToolOutput(
            text=f"**{setting}** set to `{value!r}`",
            title="Config Updated",
            metadata={"setting": setting, "value": value},
        )


register_tool(ConfigTool())

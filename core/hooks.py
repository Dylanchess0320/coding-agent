"""
Hook system — before/after hooks for tool execution and model calls.
Borrows the pattern from Cline's AgentRuntimeHooks (beforeTool, afterTool, beforeModel, afterModel).

Hooks can:
- Intercept/deny tool calls (by returning a ToolOutput)
- Transform tool arguments
- Transform tool results
- Modify messages before they're sent to the model
- Transform model responses
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .types import HookContext

# ── Hook type aliases ─────────────────────────────────────────────────

BeforeToolHook = Callable[[str, dict[str, Any], HookContext], Any | None]
AfterToolHook = Callable[[str, dict[str, Any], Any, HookContext], Any]
BeforeModelHook = Callable[[list[dict], HookContext], list[dict]]
AfterModelHook = Callable[[dict | None, HookContext], dict | None]
OnEventHook = Callable[[Any], None]  # Generic event listener


@dataclass
class Hooks:
    """Collection of all hooks. Each is a list so multiple hooks can be registered."""

    before_tool: list[BeforeToolHook] = field(default_factory=list)
    after_tool: list[AfterToolHook] = field(default_factory=list)
    before_model: list[BeforeModelHook] = field(default_factory=list)
    after_model: list[AfterModelHook] = field(default_factory=list)
    on_event: list[OnEventHook] = field(default_factory=list)

    def register_before_tool(self, hook: BeforeToolHook):
        self.before_tool.append(hook)

    def register_after_tool(self, hook: AfterToolHook):
        self.after_tool.append(hook)

    def register_before_model(self, hook: BeforeModelHook):
        self.before_model.append(hook)

    def register_after_model(self, hook: AfterModelHook):
        self.after_model.append(hook)

    def register_on_event(self, hook: OnEventHook):
        self.on_event.append(hook)


# ── Plugin base class ─────────────────────────────────────────────────


class AgentPlugin:
    """Base class for agent plugins. Override the methods you need."""

    name: str = ""

    def before_tool(self, tool_name: str, tool_args: dict, ctx: HookContext) -> Any | None:
        return None

    def after_tool(self, tool_name: str, tool_args: dict, result: Any, ctx: HookContext) -> Any:
        return result

    def before_model(self, messages: list[dict], ctx: HookContext) -> list[dict]:
        return messages

    def after_model(self, message: dict | None, ctx: HookContext) -> dict | None:
        return message

    def on_event(self, event: Any):
        pass

    def install(self, hooks: Hooks):
        """Register this plugin's hooks into the hook system."""
        hooks.register_before_tool(self.before_tool)
        hooks.register_after_tool(self.after_tool)
        hooks.register_before_model(self.before_model)
        hooks.register_after_model(self.after_model)
        hooks.register_on_event(self.on_event)


# ── Global hook registry ──────────────────────────────────────────────

_hooks: Hooks | None = None


def get_hooks() -> Hooks:
    """Get the global hook registry (singleton)."""
    global _hooks
    if _hooks is None:
        _hooks = Hooks()
    return _hooks


def reset_hooks():
    """Reset all hooks (useful for testing)."""
    global _hooks
    _hooks = Hooks()


def register_plugin(plugin: AgentPlugin):
    """Register an agent plugin into the global hook system."""
    plugin.install(get_hooks())

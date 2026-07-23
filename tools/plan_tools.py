"""
Plan mode tools: EnterPlanMode and ExitPlanMode.
Enables read-only exploration phase before writing code.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .base import ToolBase, ToolOutput
from .registry import register_tool

# ── plan mode state ────────────────────────────────────────────────

_plan_mode: bool = False
_plan_context: dict = {}


def is_plan_mode() -> bool:
    return _plan_mode


def get_plan_context() -> dict:
    return _plan_context


class EnterPlanModeTool(ToolBase):
    name = "EnterPlanMode"
    description = "Enter plan mode: a read-only exploration and design phase BEFORE writing any code. In plan mode, you MUST NOT write or edit files. Explore the codebase, consider approaches, and when ready call ExitPlanMode."
    aliases = ["PlanMode", "DesignPhase"]
    parameters = {}

    async def execute(self) -> ToolOutput:
        global _plan_mode, _plan_context
        _plan_mode = True
        _plan_context = {
            "entered_at": datetime.now(timezone.utc).isoformat(),
            "files_examined": [],
        }
        return ToolOutput(
            text="""Plan mode ACTIVE. You are in a read-only exploration phase.

Rules:
  - DO NOT write or edit any files
  - Explore the codebase thoroughly
  - Identify similar features and architectural approaches
  - Consider multiple approaches and their trade-offs
  - Use AskUserQuestion to clarify requirements
  - Design a concrete implementation strategy
  - When ready, call ExitPlanMode to present the plan for approval""",
            title="Plan Mode Active",
            metadata={"plan_mode": True},
        )


class ExitPlanModeTool(ToolBase):
    name = "ExitPlanMode"
    description = "Exit plan mode and present your implementation plan to the user for approval. Only call when you have a complete, concrete plan ready."
    aliases = ["ExitPlan", "ProposePlan"]
    parameters = {
        "plan": {
            "type": "string",
            "description": "Your complete implementation plan. Be specific: list files, functions, and approaches.",
        },
    }

    async def execute(self, plan: str) -> ToolOutput:
        global _plan_mode
        _plan_mode = False
        return ToolOutput(
            text=f"Plan mode EXITED. Here is the proposed plan:\n\n{plan}\n\n---\nWaiting for user approval before proceeding.",
            title="Plan Proposed",
            metadata={"plan_mode": False, "plan": plan},
        )


register_tool(EnterPlanModeTool())
register_tool(ExitPlanModeTool())

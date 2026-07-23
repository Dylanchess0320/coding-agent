"""
Sub-agent spawning tool — launches a child agent for focused subtasks.
The sub-agent inherits the same model, tools, and memory but runs independently.
"""

from __future__ import annotations

from .base import ToolBase, ToolOutput
from .registry import register_tool


class SubAgentTool(ToolBase):
    name = "SubAgent"
    description = "Spawn a child agent to work independently on a focused subtask."
    aliases = ["Delegate", "SpawnAgent"]
    parameters = {
        "task": {"type": "string", "description": "The task for the sub-agent to complete"},
        "max_turns": {"type": "integer", "description": "Max turns for the sub-agent (default: 5)"},
    }

    async def execute(self, task: str, max_turns: int = 5) -> ToolOutput:
        """Run a sub-agent asynchronously and return its result."""
        from agent import CodingAgent
        from config import get_config

        cfg = get_config()
        agent = CodingAgent(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=cfg["model"],
            temperature=cfg["temperature"],
            max_tokens=cfg["max_tokens"],
        )

        try:
            result = await agent.run(task, max_turns=min(max_turns, 10))
            return ToolOutput(
                text=result,
                title="SubAgent Result",
                metadata={"task": task[:100], "turns_used": agent.turn_count},
            )
        except Exception as e:
            return ToolOutput(
                text=f"SubAgent error: {e}",
                error=True,
                metadata={"task": task[:100]},
            )


register_tool(SubAgentTool())

"""
DateTime and Sleep utility tools.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from .base import ToolBase, ToolOutput
from .registry import register_tool


class DateTimeTool(ToolBase):
    name = "DateTime"
    description = (
        "Get the current local date and time. Use instead of running 'date' or 'time' in a shell."
    )
    aliases = ["Now", "CurrentTime"]
    parameters = {
        "format": {
            "type": "string",
            "description": "Optional strftime format string (e.g. '%Y-%m-%d %H:%M:%S'). Defaults to human-readable.",
        },
    }

    async def execute(self, format: str = "") -> ToolOutput:
        now = datetime.now()
        text = now.strftime(format) if format else now.strftime("%A, %B %d, %Y  %I:%M:%S %p")
        return ToolOutput(text=text, title="Current Time", metadata={"iso": now.isoformat()})


class SleepTool(ToolBase):
    name = "Sleep"
    description = "Pause the agent for a specified number of seconds. Use for polling loops, rate limiting, or waiting for background processes."
    aliases = ["Wait", "Pause"]
    parameters = {
        "seconds": {
            "type": "number",
            "description": "How long to sleep in seconds (min 0.1, max 300)",
        },
        "reason": {"type": "string", "description": "Why the agent is sleeping (shown to user)"},
    }

    async def execute(self, seconds: float = 1.0, reason: str = "") -> ToolOutput:
        seconds = max(0.1, min(300.0, seconds))
        await asyncio.sleep(seconds)
        return ToolOutput(
            text=f"Slept {seconds:.1f}s" + (f": {reason}" if reason else ""),
            title=f"Slept {seconds:.1f}s",
            metadata={"seconds": seconds},
        )


register_tool(DateTimeTool())
register_tool(SleepTool())

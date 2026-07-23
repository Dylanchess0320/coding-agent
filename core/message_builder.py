"""
Message builder — system prompt construction and memory injection.
Extracted from agent.py's _build_system and _inject_memories methods.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_SYSTEM_PROMPT = """You are LuckyD Code, an AI coding assistant in a terminal.

Answer concisely. For code: use Bash/Read/Write/Edit/Glob/Grep tools. For questions: answer directly.

CRITICAL: If the user asks a question that is NOT about this project or codebase
(e.g., general knowledge, trivia, opinions, factual questions), answer it directly
and immediately. Do NOT search the codebase first.

## Freshness Rule (MANDATORY)
For ANY factual, time-sensitive, or knowledge-based question:
  1. Use WebSearch FIRST to check for current information
  2. Read the search results
  3. Then answer using ONLY the fresh data you just retrieved
  4. Cite your source when possible

## Agents
- Use AgentHandoff for specialist roles: researcher → coder → reviewer
- Use SubAgent for self-contained subtasks
- Skip agents for simple Q&A or 1-2 tool edits

## Code Rules
1. Read file before editing
2. Match existing patterns
3. Minimal diffs only
4. Verify changes work
5. No dead code, no silent errors

Current directory: {cwd}
"""


class MessageBuilder:
    """Builds system prompts with tool descriptions, project info, and memory context."""

    def __init__(self):
        self._project_info = None
        self._try_load_project_info()

    def _try_load_project_info(self):
        """Auto-detect project information on startup."""
        try:
            from config import PROJECT_DIR
            from project import ProjectDetector
            detector = ProjectDetector()
            self._project_info = detector.detect(PROJECT_DIR)
        except Exception:
            self._project_info = None

    def build_system(
        self,
        provider_name: str,
        model_name: str,
        tools_description: str,
        memory_context: str | None = None,
        project_rules: str | None = None,
    ) -> str:
        """Build the full system prompt with tools, context, memories, and rules."""
        cwd = str(Path.cwd())
        base = DEFAULT_SYSTEM_PROMPT.format(cwd=cwd) + f"\nAvailable tools:\n{tools_description}"

        # Append project intelligence
        if self._project_info and hasattr(self._project_info, 'is_empty') and not self._project_info.is_empty():
            base += "\n\n## Project Context\n" + self._project_info.to_prompt()

        base += f"\n\n## Model\nProvider: {provider_name} | Model: {model_name}"

        # Inject project rules (AGENTS.md etc.)
        if project_rules:
            base += "\n\n" + project_rules

        # Inject memories
        if memory_context:
            base += "\n\n## Long-Term Memory Context\n" + memory_context

        return base

    @staticmethod
    def build_memory_system_message(memories: str) -> dict:
        """Build a system message for memory injection."""
        return {
            "role": "system",
            "content": f"Relevant memories from past sessions:\n{memories}",
        }

    @staticmethod
    def build_truncation_notice() -> dict:
        """Build a system message for context truncation."""
        return {
            "role": "system",
            "content": "[Context truncated — keeping most recent messages only]",
        }

    @staticmethod
    def build_memory_refresh_message(memories: str) -> dict:
        """Build a system message for mid-conversation memory refresh."""
        return {
            "role": "system",
            "content": f"[Updated relevant memories]\n{memories}",
        }

    @staticmethod
    def build_max_turns_message() -> dict:
        """Build the user message for max turns reached."""
        return {
            "role": "user",
            "content": "You've reached the maximum number of turns. Summarize what you've done and what remains.",
        }

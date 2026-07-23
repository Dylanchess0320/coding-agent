"""
Project rules loader — injects repo-level agent instructions into the system prompt.

Industry-standard pattern (AGENTS.md is supported by OpenAI Codex, Cursor, Jules,
Antigravity; Cline uses .clinerules; goose uses .goosehints; Claude Code uses
CLAUDE.md). We read all of them so LuckyD Code drops into any repo that already
has rules written for another agent.

Search order (both in the current working directory and the agent's project dir):
  AGENTS.md, agents.md, .agents.md, CLAUDE.md, .clinerules, .goosehints,
  LUCKYD.md, .luckyd/rules.md, .luckyd-code/rules.md
"""

from __future__ import annotations

from pathlib import Path

RULE_FILE_NAMES = [
    "AGENTS.md",
    "agents.md",
    ".agents.md",
    "CLAUDE.md",
    ".clinerules",
    ".goosehints",
    "LUCKYD.md",
    ".luckyd/rules.md",
    ".luckyd-code/rules.md",
]

_MAX_CHARS_PER_FILE = 6000
_MAX_CHARS_TOTAL = 12000


def _read_capped(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        return ""
    if len(text) > _MAX_CHARS_PER_FILE:
        text = text[:_MAX_CHARS_PER_FILE] + "\n... [rules truncated]"
    return text


def find_rule_files(directories: list[Path]) -> list[Path]:
    """All rule files present in the given directories (deduped, stable order)."""
    found: list[Path] = []
    seen: set[str] = set()
    for directory in directories:
        if not directory:
            continue
        for name in RULE_FILE_NAMES:
            candidate = directory / name
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in seen or not candidate.is_file():
                continue
            seen.add(key)
            found.append(candidate)
    return found


def load_project_rules(extra_dirs: list[Path] | None = None) -> str:
    """Load and format project rules for the system prompt. '' if none found."""
    from config import PROJECT_DIR

    directories: list[Path] = [Path.cwd(), PROJECT_DIR]
    if extra_dirs:
        directories.extend(extra_dirs)

    files = find_rule_files(directories)
    if not files:
        return ""

    sections: list[str] = []
    total = 0
    for f in files:
        text = _read_capped(f)
        if not text:
            continue
        remaining = _MAX_CHARS_TOTAL - total
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + "\n... [rules truncated]"
        try:
            rel = f.relative_to(Path.cwd())
        except ValueError:
            rel = f
        sections.append(f"### From `{rel}`\n{text}")
        total += len(text)

    if not sections:
        return ""

    return (
        "## Project Rules\n"
        "The following repo-level instructions MUST be followed — they override "
        "default behavior when in conflict:\n\n" + "\n\n".join(sections)
    )

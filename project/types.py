"""Project data types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProjectInfo:
    """Detected project metadata."""

    name: str = "unknown"
    language: str = ""
    framework: str = ""
    build_system: str = ""
    test_framework: str = ""
    linter: str = ""
    formatter: str = ""
    package_manager: str = ""
    language_version: str = ""
    has_docker: bool = False
    has_ci: bool = False
    has_readme: bool = False
    has_tests: bool = False
    has_docs: bool = False
    key_files: list[str] = field(default_factory=list)
    entry_point: str = ""
    config_files: dict = field(default_factory=dict)
    root: str = ""
    total_files: int = 0
    total_dirs: int = 0

    def to_prompt(self) -> str:
        """Format as a context string for the system prompt."""
        parts = [f"## Project: {self.name}", f"Language: {self.language}"]
        if self.framework:
            parts.append(f"Framework: {self.framework}")
        if self.build_system:
            parts.append(f"Build: {self.build_system}")
        if self.test_framework:
            parts.append(f"Tests: {self.test_framework}")
        if self.package_manager:
            parts.append(f"Package Manager: {self.package_manager}")
        if self.entry_point:
            parts.append(f"Entry: {self.entry_point}")
        if self.key_files:
            parts.append(f"Key files: {', '.join(self.key_files[:8])}")
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return self.language == "" and not self.key_files

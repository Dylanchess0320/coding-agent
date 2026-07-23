"""Project Intelligence Engine — auto-detect project type, framework, conventions."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .types import ProjectInfo


class ProjectDetector:
    """Detects project type and gathers key context."""

    FRAMEWORK_SIGS = {
        "Python": [
            ("django", "Django"),
            ("flask", "Flask"),
            ("fastapi", "FastAPI"),
            ("tornado", "Tornado"),
            ("starlette", "Starlette"),
            ("aiohttp", "aiohttp"),
            ("pytest", "pytest"),
            ("sqlalchemy", "SQLAlchemy"),
            ("numpy", "NumPy"),
            ("pandas", "Pandas"),
            ("torch", "PyTorch"),
            ("tensorflow", "TensorFlow"),
        ],
        "JavaScript": [
            ("react", "React"),
            ("vue", "Vue.js"),
            ("angular", "Angular"),
            ("svelte", "Svelte"),
            ("next", "Next.js"),
            ("nuxt", "Nuxt.js"),
            ("express", "Express.js"),
            ("nestjs", "NestJS"),
            ("jest", "Jest"),
        ],
        "TypeScript": [
            ("react", "React"),
            ("vue", "Vue.js"),
            ("angular", "Angular"),
            ("next", "Next.js"),
            ("nuxt", "Nuxt.js"),
            ("express", "Express.js"),
            ("nestjs", "NestJS"),
            ("typeorm", "TypeORM"),
            ("prisma", "Prisma"),
        ],
        "Rust": [
            ("axum", "Axum"),
            ("actix", "Actix-web"),
            ("rocket", "Rocket"),
            ("tokio", "Tokio"),
            ("serde", "Serde"),
        ],
        "Go": [
            ("gin", "Gin"),
            ("echo", "Echo"),
            ("fiber", "Fiber"),
            ("cobra", "Cobra"),
            ("gorm", "GORM"),
        ],
    }

    BUILD_SYSTEMS = {
        "pyproject.toml": "poetry/pdm",
        "setup.py": "setuptools",
        "setup.cfg": "setuptools",
        "requirements.txt": "pip",
        "Pipfile": "pipenv",
        "Cargo.toml": "cargo",
        "go.mod": "go mod",
        "package.json": "npm",
        "yarn.lock": "yarn",
        "pnpm-lock.yaml": "pnpm",
        "Gemfile": "bundler",
        "composer.json": "composer",
        "build.gradle": "gradle",
        "build.gradle.kts": "gradle",
        "pom.xml": "maven",
        "Makefile": "make",
        "CMakeLists.txt": "cmake",
        "mix.exs": "mix",
    }

    def detect(self, path: str | Path) -> ProjectInfo:
        """Detect project information from a directory."""
        root = Path(path).resolve()
        if not root.exists():
            return ProjectInfo(root=str(root))

        info = ProjectInfo(root=str(root))
        info.name = root.name

        # Walk files
        dirs_walked = 0
        files_walked = 0
        all_files = []

        for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(
                    (
                        ".",
                        "__",
                        "node_modules",
                        "venv",
                        ".venv",
                        ".git",
                        "target",
                        "build",
                        "dist",
                        ".next",
                        ".nuxt",
                        "__pycache__",
                    )
                )
            ]
            dirs_walked += 1
            for f in filenames:
                files_walked += 1
                fp = Path(dirpath) / f
                try:
                    all_files.append(str(fp.relative_to(root)))
                except ValueError:
                    continue
            if dirs_walked > 200 or files_walked > 2000:
                break

        info.total_files = files_walked
        info.total_dirs = dirs_walked

        info.language = self._detect_language(root, all_files)
        info.framework = self._detect_framework(root, info.language)
        info.build_system = self._detect_build_system(root)
        info.package_manager = self._detect_package_manager(root, info.language)
        info.test_framework = self._detect_test_framework(root, info.language)
        info.linter, info.formatter = self._detect_lint_format(root, info.language)
        info.key_files = self._find_key_files(root, info.language)
        info.entry_point = self._find_entry_point(root, info.language)
        info.has_tests = any("test" in f.lower() for f in all_files[:100])
        info.has_docs = (
            any(f.startswith("docs/") for f in all_files[:100]) or (root / "docs").is_dir()
        )
        info.has_docker = (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists()
        info.has_ci = (
            any(f.startswith(".github/") for f in all_files[:50])
            or (root / ".gitlab-ci.yml").exists()
        )
        info.has_readme = any(f.lower().startswith("readme") for f in os.listdir(root))

    def _detect_language(self, root: Path, files: list[str]) -> str:
        """Detect primary language from file extensions and manifest files."""
        ext_counts: dict[str, int] = {}
        for f in files:
            ext = Path(f).suffix.lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".rb": "Ruby",
            ".php": "PHP",
            ".c": "C",
            ".h": "C",
            ".cpp": "C++",
            ".hpp": "C++",
            ".cs": "C#",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".kts": "Kotlin",
        }

        lang_scores: dict[str, int] = {}
        for ext, count in ext_counts.items():
            lang = ext_map.get(ext)
            if lang:
                lang_scores[lang] = lang_scores.get(lang, 0) + count

        if (root / "Cargo.toml").exists():
            lang_scores["Rust"] = lang_scores.get("Rust", 0) + 100
        if (root / "go.mod").exists():
            lang_scores["Go"] = lang_scores.get("Go", 0) + 100
        if (root / "package.json").exists():
            if (root / "tsconfig.json").exists():
                lang_scores["TypeScript"] = lang_scores.get("TypeScript", 0) + 100
            else:
                lang_scores["JavaScript"] = lang_scores.get("JavaScript", 0) + 100
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            lang_scores["Python"] = lang_scores.get("Python", 0) + 50

        if not lang_scores:
            return ""
        return max(lang_scores, key=lang_scores.get)

    def _detect_framework(self, root: Path, language: str) -> str:
        if not language:
            return ""
        deps_content = ""
        if (root / "package.json").exists() and language in ("JavaScript", "TypeScript"):
            try:
                data = json.loads((root / "package.json").read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                deps_content = " ".join(deps.keys()).lower()
            except (json.JSONDecodeError, OSError):
                pass
        elif language == "Python":
            for fname in ["requirements.txt", "pyproject.toml"]:
                fp = root / fname
                if fp.exists():
                    deps_content += fp.read_text().lower()
        elif language == "Rust" and (root / "Cargo.toml").exists():
            deps_content = (root / "Cargo.toml").read_text().lower()
        elif language == "Go" and (root / "go.mod").exists():
            deps_content = (root / "go.mod").read_text().lower()

        for pattern, fw_name in self.FRAMEWORK_SIGS.get(language, []):
            if pattern in deps_content:
                return fw_name
        return ""

    def _detect_build_system(self, root: Path) -> str:
        for filename, build in self.BUILD_SYSTEMS.items():
            if (root / filename).exists():
                return build
        return ""

    def _detect_lang_version(self, root: Path, language: str) -> str:
        if language == "Python":
            pf = root / "pyproject.toml"
            if pf.exists():
                m = re.search(r'requires-python\s*=\s*["\']([^"\']+)', pf.read_text())
                if m:
                    return m.group(1)
        if language in ("JavaScript", "TypeScript"):
            pf = root / "package.json"
            if pf.exists():
                try:
                    eng = json.loads(pf.read_text()).get("engines", {})
                    return eng.get("node", "")
                except json.JSONDecodeError:
                    pass
        if language == "Rust":
            for fname in ["rust-toolchain.toml", "rust-toolchain"]:
                fp = root / fname
                if fp.exists():
                    return fp.read_text().strip()[:20]
        return ""

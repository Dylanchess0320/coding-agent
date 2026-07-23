"""
Sandboxed command execution for Windows.
Guards against destructive operations — the heart of principle #3.
"""

import platform
import re
import subprocess
from typing import NamedTuple

from config import COMMAND_TIMEOUT_SEC, MAX_OUTPUT_CHARS, PROJECT_DIR

# ── Safety: Blocklist ──────────────────────────────────────────────────
# Any command containing these patterns is blocked (case-insensitive)
BLOCKLIST = [
    # Destructive filesystem ops
    r"rm\s+-rf\s+/",
    r"rd\s+/s\s+/q\s+c:\\",
    r"format\s",
    r"del\s+/f\s+/s",
    r"deltree",
    # Dangerous system ops
    r"shutdown",
    r"restart-computer",
    r"stop-computer",
    r"bcdedit",
    r">\s*/dev/sda",
    r"dd\s+if=",
    r"mkfs",
    # Fork bombs / resource exhaustion
    r":\(\)\s*\{",
    r"while\s*\(\s*1\s*\)",
    r"%0\|%0",
    # Privilege escalation
    r"sudo\s",
    r"runas\s+/user:",
    # Network havoc
    r"netsh\s+.*delete",
    r"ipconfig\s+/release",
    r"wmic\s+.*delete",
    # Registry destruction
    r"reg\s+delete\s+hklm",
    r"reg\s+delete\s+/f",
    # Python self-destruct
    r"os\.remove\(",
    r"shutil\.rmtree\(['\"]/['\"]",
]

# Patterns that are allowed (these override the blocklist)
ALLOWLIST = [
    # Allow deleting files in project dir (not system)
    # handled by path checks below
]


class CommandResult(NamedTuple):
    exit_code: int
    stdout: str
    stderr: str
    blocked: bool
    duration_ms: int


def is_safe(command: str, cwd: str | None = None) -> tuple[bool, str]:
    """
    Check if a command is safe to execute.
    Returns (is_safe, reason).
    """
    cmd_lower = command.lower().strip()

    # ── Check blocklist ────────────────────────────────────────────
    for pattern in BLOCKLIST:
        if re.search(pattern, cmd_lower):
            return False, f"BLOCKED: matches dangerous pattern '{pattern}'"

    # ── Check for path escapes ─────────────────────────────────────
    # Prevent writing outside project dir
    dangerous_paths = [
        r"C:\Windows",
        r"C:\WINDOWS",
        r"/Windows",
        r"C:\Program Files",
        r"C:\ProgramData",
        r"/etc/",
        r"/bin/",
        r"/boot/",
        r"/root",
        r"~/",
        r"$HOME",
        r"%SystemRoot%",
        r"%ProgramFiles%",
        r"%AppData%",
    ]

    # Only flag path escapes if they're in write/destructive context
    destructive_ops = r"(>|>>|rm\s|del\s|rd\s|rmdir|mv\s|move\s|copy\s|xcopy)"  # Added delete ops
    if re.search(destructive_ops, cmd_lower):
        for path in dangerous_paths:
            if path.lower() in cmd_lower:
                return False, f"BLOCKED: references system path '{path}'"

    return True, "ok"


def execute(command: str, cwd: str | None = None, timeout: int | None = None) -> CommandResult:
    """
    Execute a shell command safely.
    Returns a CommandResult with exit_code, stdout, stderr, and blocked flag.
    """
    if timeout is None:
        timeout = COMMAND_TIMEOUT_SEC

    cwd = cwd or str(PROJECT_DIR)

    # Safety check
    safe, reason = is_safe(command, cwd)
    if not safe:
        return CommandResult(-1, "", reason, True, 0)

    import time

    start = time.time()

    try:
        # Use the native shell: PowerShell on Windows, bash on Linux/macOS
        if platform.system() == "Windows":
            shell_cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
        else:
            shell_cmd = ["bash", "-c", command]

        proc = subprocess.run(
            shell_cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        elapsed = int((time.time() - start) * 1000)

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # Truncate
        if len(stdout) > MAX_OUTPUT_CHARS:
            stdout = (
                stdout[:MAX_OUTPUT_CHARS]
                + f"\n... [truncated {len(stdout) - MAX_OUTPUT_CHARS} chars]"
            )
        if len(stderr) > MAX_OUTPUT_CHARS:
            stderr = (
                stderr[:MAX_OUTPUT_CHARS]
                + f"\n... [truncated {len(stderr) - MAX_OUTPUT_CHARS} chars]"
            )

        return CommandResult(proc.returncode, stdout, stderr, False, elapsed)

    except subprocess.TimeoutExpired:
        elapsed = int((time.time() - start) * 1000)
        return CommandResult(-1, "", f"TIMEOUT: command exceeded {timeout}s limit", False, elapsed)
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return CommandResult(-1, "", f"ERROR: {e}", False, elapsed)


def execute_batch(commands: list[str], cwd: str | None = None) -> list[CommandResult]:
    """Execute a list of commands sequentially, stopping on first failure."""
    results = []
    for cmd in commands:
        result = execute(cmd, cwd=cwd)
        results.append(result)
        if result.exit_code != 0 and not result.blocked:
            break  # stop on first failure
    return results

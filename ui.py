"""
Terminal UI — clean LuckyD Code design with Rich or ANSI fallback.
"""

from __future__ import annotations

import contextlib
import platform
import re
import shutil
import sys
import time

# ── Rich detection ────────────────────────────────────────────────────

_RICH_AVAILABLE = False
try:
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme

    _RICH_AVAILABLE = True
except ImportError:
    pass

# ── ANSI color codes (fallback) ───────────────────────────────────────

ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "white": "\033[37m",
    "gray": "\033[90m",
}

# ── Brand colors ──────────────────────────────────────────────────────

BRAND = {
    "primary": "#00E5FF",
    "dim": "#4DD0E1",
    "muted": "#64748B",
    "success": "#34D399",
    "error": "#F87171",
    "warn": "#FBBF24",
    "surface": "#1E293B",
}

if _RICH_AVAILABLE:
    JCODE_THEME = Theme(
        {
            "markdown.code": f"bold {BRAND['primary']}",
            "markdown.code_block": f"{BRAND['dim']}",
            "markdown.h1": f"bold {BRAND['primary']}",
            "markdown.h2": f"bold {BRAND['primary']}",
            "markdown.h3": f"bold {BRAND['dim']}",
            "markdown.link": f"underline {BRAND['primary']}",
            "markdown.item.bullet": BRAND["muted"],
            "repr.string": BRAND["success"],
            "repr.number": BRAND["warn"],
            "repr.bool_true": BRAND["success"],
            "repr.bool_false": BRAND["error"],
            "repr.none": BRAND["muted"],
        }
    )


class TerminalUI:
    """Clean terminal UI for LuckyD Code — Rich or ANSI fallback."""

    def __init__(self) -> None:
        self.rich = _RICH_AVAILABLE
        self._console = (
            Console(theme=JCODE_THEME, highlight=True, soft_wrap=True)
            if self.rich
            else None
        )
        self._stream_buffer = ""
        self._live: Live | None = None
        self._streaming = False
        self._thinking = False
        self._think_buffer = ""
        self._tool_count = 0
        self._last_action_time = time.time()
        self._width = shutil.get_terminal_size((100, 40)).columns
        self._session_start = time.time()
        self._cost_summary = ""
        self._project_name = ""
        self._provider_name = ""
        self._model_name = ""

    # ── Helpers ────────────────────────────────────────────────────

    def _dim(self, text: str) -> str:
        return f"[{BRAND['muted']}]{text}[/]" if self.rich else f"{ANSI['dim']}{text}{ANSI['reset']}"

    def _primary(self, text: str) -> str:
        return (
            f"[{BRAND['primary']}]{text}[/]"
            if self.rich
            else f"{ANSI['cyan']}{text}{ANSI['reset']}"
        )

    def _sep(self, width: int | None = None) -> str:
        w = width or min(self._width - 4, 64)
        return "─" * max(w, 24)

    # ── Session info ────────────────────────────────────────────────

    def set_session_info(
        self,
        project_name: str = "",
        provider: str = "",
        cost: str = "",
        model: str = "",
    ) -> None:
        """Update session header info."""
        if project_name:
            self._project_name = project_name
        if provider:
            self._provider_name = provider
        if cost:
            self._cost_summary = cost
        if model:
            self._model_name = model

    def _session_header(self) -> str:
        """Build a compact session status line."""
        parts: list[str] = []
        if self._project_name:
            parts.append(self._project_name)
        if self._provider_name:
            label = self._provider_name
            if self._model_name:
                label = f"{label}/{self._model_name}"
            parts.append(label)
        elif self._model_name:
            parts.append(self._model_name)
        return " · ".join(parts)

    # ── Banner ─────────────────────────────────────────────────────

    def enhanced_banner(self) -> None:
        """Startup banner with project and provider context."""
        self.banner()

    def banner(self) -> None:
        """Clean startup banner."""
        header = self._session_header()
        tip = "Type a task, or /help for commands"

        if self.rich:
            self._console.print()
            title = Text()
            title.append("  LuckyD Code", style=f"bold {BRAND['primary']}")
            title.append("  v2.0", style=BRAND["muted"])
            self._console.print(title)
            if header:
                self._console.print(f"  {self._dim(header)}")
            self._console.print(f"  {self._dim(self._sep())}")
            self._console.print(f"  {self._dim(tip)}")
            self._console.print()
        else:
            print(f"\n  {ANSI['bold']}{ANSI['cyan']}LuckyD Code{ANSI['reset']} {ANSI['dim']}v2.0{ANSI['reset']}")
            if header:
                print(f"  {ANSI['dim']}{header}{ANSI['reset']}")
            print(f"  {ANSI['dim']}{self._sep()}{ANSI['reset']}")
            print(f"  {ANSI['dim']}{tip}{ANSI['reset']}\n")

    def goodbye(self, cost_summary: str = "") -> None:
        summary_parts = [f"{self._tool_count} tools"]
        if cost_summary:
            summary_parts.append(cost_summary)
        elapsed = int(time.time() - self._session_start)
        if elapsed >= 60:
            summary_parts.append(f"{elapsed // 60}m {elapsed % 60}s")
        elif elapsed > 0:
            summary_parts.append(f"{elapsed}s")
        summary = " · ".join(summary_parts)

        if self.rich:
            self._console.print()
            self._console.print(f"  {self._dim(self._sep(40))}")
            self._console.print(f"  {self._dim(summary)}")
            self._console.print(f"  {self._dim('Goodbye.')}\n")
        else:
            print(f"\n  {ANSI['dim']}{summary}{ANSI['reset']}")
            print(f"  {ANSI['dim']}Goodbye.{ANSI['reset']}\n")

    # ── Status ─────────────────────────────────────────────────────

    def _status_line(self, msg: str) -> None:
        if self.rich:
            self._console.print(f"  {self._dim(msg)}")
        else:
            print(f"  {ANSI['dim']}{msg}{ANSI['reset']}")

    # ── Streaming ──────────────────────────────────────────────────

    def start_streaming(self) -> None:
        """Begin streaming a response (incremental plain text)."""
        self._stream_buffer = ""
        self._streaming = True
        self._thinking = False
        self._think_buffer = ""
        if self.rich and self._live:
            self._live.stop()
            self._live = None
        # Visual breathing room before the answer
        if self.rich:
            self._console.print()
        else:
            print()

    def show_question(self, question: str) -> None:
        """Echo the user question before streaming the response."""
        if self.rich:
            self._console.print(f"\n  {self._dim('you')}  {question}")
        else:
            print(f"\n  {ANSI['dim']}you{ANSI['reset']}  {question}")

    def begin_thinking(self) -> None:
        """Start the thinking section before reasoning tokens arrive."""
        self._thinking = True
        self._think_buffer = ""
        if self.rich:
            if self._live:
                self._live.stop()
                self._live = None
            self._live = Live(
                Markdown(""),
                console=self._console,
                refresh_per_second=12,
                transient=True,
            )
            self._live.start()
            self._live.update(
                Panel(
                    Text("…", style=BRAND["muted"]),
                    title="thinking",
                    border_style=BRAND["muted"],
                    title_align="left",
                    padding=(0, 1),
                )
            )
        else:
            print(f"  {ANSI['dim']}thinking…{ANSI['reset']}")

    def stream_think_token(self, token: str) -> None:
        """Push a reasoning token to the thinking display."""
        if not self._thinking:
            self.begin_thinking()
        self._think_buffer += token
        # Keep panel compact — show a short tail only
        preview = self._think_buffer[-400:]
        if self.rich and self._live:
            with contextlib.suppress(Exception):
                self._live.update(
                    Panel(
                        Text(preview, style=BRAND["muted"]),
                        title="thinking",
                        border_style=BRAND["muted"],
                        title_align="left",
                        padding=(0, 1),
                    )
                )
        elif not self.rich:
            sys.stdout.write(f"{ANSI['dim']}{token}{ANSI['reset']}")
            sys.stdout.flush()

    def end_thinking(self) -> None:
        """Close the thinking section."""
        self._thinking = False
        if self.rich and self._live:
            self._live.stop()
            self._live = None
        elif not self.rich:
            print()

    def stream_token(self, token: str) -> None:
        """Push a token directly to the terminal as plain, incremental text."""
        if self._thinking:
            self.end_thinking()
        self._stream_buffer += token
        sys.stdout.write(token)
        sys.stdout.flush()

    def play_done_sound(self) -> None:
        """Soft completion cue (non-blocking)."""
        try:
            if platform.system() == "Windows":
                import winsound

                winsound.MessageBeep(winsound.MB_OK)
            else:
                print("\a", end="", flush=True)
        except Exception:
            pass

    def end_streaming(self) -> None:
        """Finish the plain-text stream."""
        self._streaming = False
        if self.rich and self._live:
            self._live.stop()
            self._live = None
        print()
        print()

    def finish_response(self, full_text: str) -> None:
        """Render a full response when streaming was not used."""
        if self._streaming:
            return
        if full_text and self.rich:
            self._console.print(Markdown(full_text))
        elif full_text:
            self._ansi_markdown(full_text)

    # ── Markdown ───────────────────────────────────────────────────

    def markdown(self, text: str) -> None:
        if not text:
            return
        if self.rich:
            self._console.print(Markdown(text))
        else:
            self._ansi_markdown(text)

    def _ansi_markdown(self, text: str) -> None:
        lines = text.split("\n")
        in_code_block = False
        for line in lines:
            if line.startswith("```"):
                if in_code_block:
                    in_code_block = False
                    continue
                in_code_block = True
                lang = line[3:].strip()
                print(f"{ANSI['dim']}── {lang or 'code'} ──{ANSI['reset']}")
                continue
            if in_code_block:
                print(f"  {ANSI['cyan']}{line}{ANSI['reset']}")
                continue
            if line.startswith("### "):
                print(f"\n{ANSI['bold']}{ANSI['yellow']}{line[4:]}{ANSI['reset']}")
            elif line.startswith("## "):
                print(f"\n{ANSI['bold']}{ANSI['magenta']}{line[3:]}{ANSI['reset']}")
            elif line.startswith("# "):
                print(f"\n{ANSI['bold']}{ANSI['cyan']}{line[2:]}{ANSI['reset']}")
            elif "**" in line:
                line = re.sub(
                    r"\*\*(.*?)\*\*",
                    f"{ANSI['bold']}\\1{ANSI['reset']}",
                    line,
                )
                print(line)
            elif "`" in line:
                line = re.sub(
                    r"`(.*?)`",
                    f"{ANSI['cyan']}\\1{ANSI['reset']}",
                    line,
                )
                print(line)
            elif line.strip().startswith("- "):
                print(f"  {ANSI['dim']}•{ANSI['reset']} {line.strip()[2:]}")
            else:
                print(line)

    # ── Tool calls ─────────────────────────────────────────────────

    def tool_call_start(self, tool_name: str, args: dict | None = None) -> None:
        """Show a tool is starting."""
        self._tool_count += 1
        arg_preview = ""
        if args:
            if "file_path" in args:
                arg_preview = f"  {args['file_path']}"
            elif "path" in args:
                arg_preview = f"  {args['path']}"
            elif "command" in args:
                arg_preview = f"  {str(args['command'])[:56]}"
            elif "url" in args:
                arg_preview = f"  {str(args['url'])[:56]}"
            elif "query" in args:
                arg_preview = f"  {str(args['query'])[:56]}"

        if self.rich:
            self._console.print(
                f"  {self._dim('›')} {self._primary(tool_name)}{self._dim(arg_preview)}"
            )
        else:
            print(
                f"  {ANSI['dim']}›{ANSI['reset']} "
                f"{ANSI['cyan']}{tool_name}{ANSI['reset']}"
                f"{ANSI['dim']}{arg_preview}{ANSI['reset']}"
            )

    def tool_call_result(
        self, tool_name: str, elapsed: float, ok: bool, preview: str
    ) -> None:
        status = "ok" if ok else "fail"
        color = BRAND["success"] if ok else BRAND["error"]
        snippet = (preview or "").replace("\n", " ").strip()[:48]
        if self.rich:
            self._console.print(
                f"    [{color}]{status}[/] "
                f"{self._dim(f'{elapsed:.1f}s')}"
                + (f"  {self._dim(snippet)}" if snippet else "")
            )
        else:
            c = ANSI["green"] if ok else ANSI["red"]
            print(
                f"    {c}{status}{ANSI['reset']} "
                f"{ANSI['dim']}{elapsed:.1f}s{ANSI['reset']}"
                + (f"  {ANSI['dim']}{snippet}{ANSI['reset']}" if snippet else "")
            )

    # ── Messages ───────────────────────────────────────────────────

    def info(self, msg: str) -> None:
        self._status_line(msg)

    def warn(self, msg: str) -> None:
        if self.rich:
            self._console.print(f"  [{BRAND['warn']}]! {msg}[/]")
        else:
            print(f"  {ANSI['yellow']}! {msg}{ANSI['reset']}")

    def error(self, msg: str) -> None:
        if self.rich:
            self._console.print(f"  [{BRAND['error']}]x {msg}[/]")
        else:
            print(f"  {ANSI['red']}x {msg}{ANSI['reset']}")

    def success(self, msg: str) -> None:
        if self.rich:
            self._console.print(f"  [{BRAND['success']}]✓ {msg}[/]")
        else:
            print(f"  {ANSI['green']}✓ {msg}{ANSI['reset']}")

    # ── Help ───────────────────────────────────────────────────────

    def show_help(self) -> None:
        cmds = [
            ("/help", "Show this help"),
            ("/clear", "Clear conversation + screen"),
            ("/history", "Conversation summary"),
            ("/tools", "List available tools"),
            ("/memory", "Show stored memories"),
            ("/model", "Show or switch model"),
            ("/refresh", "Refresh model cache"),
            ("/save", "Save conversation to JSON"),
            ("/cost", "Show token usage and cost"),
            ("/undo", "Undo last file change"),
            ("/sessions", "List saved sessions"),
            ("/resume", "Resume a saved session"),
            ("/mcp", "Show MCP server status"),
            ("/version", "Show version"),
            ("/quit", "Exit"),
        ]
        if self.rich:
            table = Table(box=None, show_header=False, padding=(0, 2))
            table.add_column(style=BRAND["primary"], no_wrap=True)
            table.add_column(style="white")
            for cmd, desc in cmds:
                table.add_row(cmd, desc)
            self._console.print()
            self._console.print(f"  {self._primary('Commands')}")
            self._console.print(table)
            self._console.print()
        else:
            print(f"\n{ANSI['bold']}{ANSI['cyan']}  Commands{ANSI['reset']}")
            for cmd, desc in cmds:
                print(f"  {ANSI['cyan']}{cmd:<12}{ANSI['reset']} {desc}")
            print()

    def show_tools(self, tools: list[str]) -> None:
        if self.rich:
            self._console.print(
                f"\n  {self._primary('Tools')} {self._dim(f'({len(tools)})')}"
            )
            # Compact multi-column-ish list
            for name in tools:
                self._console.print(f"    {self._dim('•')} {name}")
            self._console.print()
        else:
            print(
                f"\n  {ANSI['bold']}{ANSI['cyan']}Tools{ANSI['reset']} "
                f"{ANSI['dim']}({len(tools)}){ANSI['reset']}"
            )
            for name in tools:
                print(f"    {ANSI['dim']}•{ANSI['reset']} {name}")
            print()

    def show_models(self, options: list[tuple[str, list[str]]]) -> None:
        """Display available model options by provider."""
        if self.rich:
            self._console.print()
            self._console.print(f"  {self._primary('Models')}")
            for provider, models in options:
                self._console.print(f"    {self._dim(provider)}")
                for m in models:
                    self._console.print(f"      {self._primary(m)}")
            self._console.print()
            self._console.print(f"  {self._dim('Usage: /model <provider> <model>')}")
            self._console.print(f"  {self._dim('Example: /model openai gpt-4o')}")
            self._console.print()
        else:
            print(f"\n  {ANSI['bold']}{ANSI['cyan']}Models{ANSI['reset']}")
            for provider, models in options:
                print(f"    {ANSI['dim']}{provider}{ANSI['reset']}")
                for m in models:
                    print(f"      {ANSI['cyan']}{m}{ANSI['reset']}")
            print(f"\n  {ANSI['dim']}Usage: /model <provider> <model>{ANSI['reset']}")
            print(f"  {ANSI['dim']}Example: /model openai gpt-4o{ANSI['reset']}\n")

    # ── Input prompt ───────────────────────────────────────────────

    def prompt(self) -> str:
        if self.rich:
            from rich.prompt import Prompt

            return Prompt.ask(
                f"[{BRAND['primary']}]›[/{BRAND['primary']}]",
                console=self._console,
            )
        try:
            return input(f"{ANSI['bold']}{ANSI['cyan']}› {ANSI['reset']}")
        except (EOFError, KeyboardInterrupt):
            return ""


# ── Global instance ──────────────────────────────────────────────────

ui = TerminalUI()

#!/usr/bin/env python3
"""
LuckyD Code — AI coding agent with streaming and rich terminal UI.

Usage:
  lucky-code                        Interactive REPL
  lucky-code "fix the bug"          One-shot
  lucky-code --model auto --thinking
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path

# Ensure the coding-agent dir is on the path
AGENT_DIR = Path(__file__).parent
sys.path.insert(0, str(AGENT_DIR))

from agent import CodingAgent
from config import PROJECT_DIR, get_config
from core.approval_hook import ApprovalHook
from core.hooks import get_hooks, register_plugin
from core.mcp_client import MCPManager
from core.session_store import get_session_store
from model_resolver import invalidate_cache, resolve_model
from tools.mcp_tools import register_mcp_tools
from tools.registry import registry
from ui import ui

_PROVIDER_DISPLAY_NAMES = {
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "ollama": "Ollama",
    "zai": "Z.ai",
    "openrouter": "OpenRouter",
}


def _prompt_and_save_api_key(env_var: str, provider_name: str) -> str:
    """Interactively prompt the user for an API key and persist it to .env."""
    ui.warn(f"No API key found for {provider_name}.")
    print(f"  Paste your {provider_name} API key below (or press Enter to cancel):")
    print(f"    {env_var}= ", end="")
    key = sys.stdin.readline().strip()
    if not key:
        ui.error("No key provided -- cannot continue without an API key.")
        sys.exit(1)

    env_path = PROJECT_DIR / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    else:
        lines = []

    key_prefix = f"{env_var}="
    replaced = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(key_prefix) and not stripped.startswith("#"):
            new_lines.append(f"{env_var}={key}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("\n")
        new_lines.append(f"# {provider_name}\n")
        new_lines.append(f"{env_var}={key}\n")

    env_path.write_text("".join(new_lines), encoding="utf-8")
    os.environ[env_var] = key
    ui.success(f"Saved {env_var} to .env  (available now -- no restart needed)")
    return key


def _resolve_provider(provider_hint: str | None, model_name: str) -> dict:
    """Build an LLMConfig for the requested provider+model.

    If a required API key is missing and we are in an interactive terminal,
    the user will be prompted to enter one.
    """
    cfg = get_config()

    # Map provider names to their alias + env vars
    provider_map = {
        "openai": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
        "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"),
        "google": ("GOOGLE_API_KEY", "GOOGLE_BASE_URL", "GOOGLE_MODEL"),
        "ollama": (None, "OLLAMA_HOST", "OLLAMA_MODEL"),
        "zai": ("ZAI_API_KEY", "ZAI_BASE_URL", "ZAI_MODEL"),
        "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "OPENROUTER_MODEL"),
    }

    if provider_hint and provider_hint in provider_map:
        env_key, env_base, env_model = provider_map[provider_hint]
        api_key = os.environ.get(env_key, "") if env_key else ""
        # If a key-required provider is selected and key is missing, prompt interactively
        if env_key and not api_key and sys.stdin.isatty():
            api_key = _prompt_and_save_api_key(
                env_key,
                _PROVIDER_DISPLAY_NAMES.get(provider_hint, provider_hint),
            )
        base_url = os.environ.get(env_base, "")
        resolved_model = model_name or os.environ.get(env_model, "")
        if not resolved_model:
            ui.warn(f"{provider_hint} model name required. Try: /model {provider_hint} <name>")
            return None
        return {
            "api_key": api_key,
            "base_url": base_url,
            "model": resolved_model,
            "provider": provider_hint,
            "thinking": False,
        }

    # No provider hint — try to detect from model name itself
    model_lower = (model_name or "").lower()
    for p in ("openai", "anthropic", "google", "ollama"):
        if model_lower.startswith(p):
            return _resolve_provider(p, model_name[len(p) + 1 :].strip())

    # Default: DeepSeek current config
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("CODING_AGENT_API_KEY", "")
    if not api_key and sys.stdin.isatty():
        api_key = _prompt_and_save_api_key("DEEPSEEK_API_KEY", "DeepSeek")
    return {
        "api_key": api_key,
        "base_url": cfg.get("base_url", "https://api.deepseek.com/v1"),
        "model": model_name or cfg.get("model", "deepseek-chat"),
        "provider": "deepseek",
        "thinking": cfg.get("thinking", False),
    }


def _switch_model(agent, provider: str | None = None, model_name: str = ""):
    """Switch agent to a new provider and/or model at runtime."""
    from llm import LLMConfig

    new_cfg = _resolve_provider(provider, model_name)
    if not new_cfg:
        return

    provider = new_cfg["provider"]
    model = new_cfg["model"]

    # Update the agent via its public API (no poking at internals)
    agent.switch_provider(
        LLMConfig(
            api_key=new_cfg["api_key"],
            base_url=new_cfg["base_url"],
            model=model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
            provider=provider,
            thinking=new_cfg.get("thinking", False),
        )
    )

    # Update the UI session info
    ui.set_session_info(
        project_name=(
            agent._project_info.name
            if agent._project_info and not agent._project_info.is_empty()
            else ""
        ),
        provider=agent.provider_name,
        model=model,
    )
    ui.success(f"Switched to {agent.provider_name} / {model}")


# ── Slash commands ────────────────────────────────────────────────────

# ── Approval callback ───────────────────────────────────────────────


def _console_approval(request) -> type(None):
    """Prompt user for tool approval in REPL. Returns None to proceed; returning a dict blocks the tool."""
    from core.types import ToolPermissionLevel

    preview = request.tool_args.get("command", request.tool_name)[:120]
    print(f"\n  [APPROVAL] {request.tool_name}: {preview}")
    print("  Approve? [y]es/[n]o/[a]lways-allow: ", end="")
    ans = sys.stdin.readline().strip().lower() or "n"
    if ans == "a":
        for p in get_hooks().before_tool:
            if hasattr(p, "set_permission"):
                p.set_permission(request.tool_name, ToolPermissionLevel.ALWAYS_ALLOW)
                break
        return None
    if ans in ("y", "yes"):
        return None
    return {
        "role": "tool",
        "tool_call_id": request.call_id,
        "content": "Tool execution denied by user.",
    }


async def handle_command(agent: CodingAgent, cmd: str) -> bool:
    """
    Handle a slash command. Returns True if the REPL should exit,
    False otherwise.
    """
    cmd = cmd[1:].strip().lower()  # strip leading '/'

    if cmd in ("q", "quit", "exit"):
        ui.goodbye()
        return True

    elif cmd in ("h", "help"):
        ui.show_help()

    elif cmd == "clear":
        agent.reset()
        # Also clear the terminal screen so you truly start fresh
        os.system("cls" if os.name == "nt" else "clear")
        project_name = (
            agent._project_info.name
            if agent._project_info and not agent._project_info.is_empty()
            else ""
        )
        ui.set_session_info(
            project_name=project_name,
            provider=agent.provider_name,
            model=getattr(agent, "model", "") or "",
        )
        ui.enhanced_banner()

    elif cmd == "history":
        ui.markdown(
            f"**Conversation:** {agent.conversation_id}\n**Turns:** {agent.turn_count}\n**Messages:** {len(agent.messages)}"
        )

    elif cmd == "tools":
        ui.show_tools(sorted(registry.list_tools()))

    elif cmd == "memory":
        try:
            from memory.store import get_memory

            ui.markdown(get_memory().summarize())
        except Exception as e:
            ui.error(f"Memory error: {e}")

    elif cmd.startswith("model"):
        parts = cmd.split(maxsplit=1)
        if len(parts) > 1:
            raw = parts[1].strip()
            # Parse "provider model_id" or just "model_id"
            provider = None
            desired = raw
            for p in ("openai", "anthropic", "google", "ollama", "deepseek", "zai", "openrouter"):
                if raw.lower().startswith(p + " "):
                    provider = p
                    desired = raw[len(p) + 1 :].strip()
                    break
            _switch_model(agent, provider=provider, model_name=desired)
        else:
            ui.info(f"Model: {agent.model}")
            ui.show_models(
                [
                    ("OpenAI", ["gpt-4o", "gpt-4o-mini", "o1-preview", "o1-mini"]),
                    (
                        "Anthropic",
                        [
                            "claude-sonnet-4-20250514",
                            "claude-opus-4-20250514",
                            "claude-3-5-haiku-20241022",
                        ],
                    ),
                    ("Google", ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]),
                    ("Ollama", ["codellama", "llama3.1", "mistral", "phi3"]),
                    ("DeepSeek", ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"]),
                    ("Z.ai", ["glm-4.6", "glm-4.5", "glm-4.5-air"]),
                    (
                        "OpenRouter",
                        [
                            "deepseek/deepseek-chat-v3.1",
                            "anthropic/claude-sonnet-4",
                            "google/gemini-2.0-flash-001",
                        ],
                    ),
                ]
            )

    elif cmd == "refresh":
        invalidate_cache()
        _switch_model(agent, model_name="auto")
        ui.success(f"Cache cleared. Model: {agent.model}")

    elif cmd == "save":
        save_path = PROJECT_DIR / f"conversation_{agent.conversation_id}.json"
        save_path.write_text(json.dumps(agent.messages, indent=2, default=str))
        ui.success(f"Saved to: {save_path}")

    elif cmd == "cost":
        ui.markdown(agent.cost_tracker.summary())

    elif cmd == "undo":
        from core.checkpoint import get_checkpoint_manager

        cm = get_checkpoint_manager()
        diff = cm.undo_last()
        if diff:
            adds = diff.additions
            dels = diff.deletions
            ui.success(f"Undid changes to {diff.file_path} ({adds}+ / {dels}-)")
        else:
            ui.warn("Nothing to undo")

    elif cmd == "sessions":
        sessions = get_session_store().list(limit=10)
        if not sessions:
            ui.info("No saved sessions")
        else:
            parts = []
            for s in sessions:
                sid = s.get("conversation_id", "?")
                ts = (s.get("updated_at") or "")[-19:] if s.get("updated_at") else "---"
                prev = (s.get("preview") or "")[:80]
                mod = s.get("model", "?")
                parts.append(f"  {sid}  {ts}  {mod}  | {prev}")
            ui.markdown("**Recent Sessions:**\n" + "\n".join(parts))

    elif cmd.startswith("resume"):
        parts = cmd.split(maxsplit=1)
        sid = parts[1] if len(parts) > 1 else "latest"
        sess = get_session_store().latest() if sid == "latest" else get_session_store().load(sid)
        if sess:
            agent.restore_session(sess)
            prev = (sess.get("preview") or "")[:80]
            ui.success(f"Resumed: {prev}")
        else:
            ui.error(f"Session not found: {sid}")

    elif cmd == "mcp":
        mgr = getattr(agent, "_mcp_manager", None)
        if mgr and mgr.is_connected:
            ui.markdown("**MCP Status**\n" + mgr.status_report())
        else:
            ui.warn("MCP not configured or no servers connected")

    elif cmd == "version":
        ui.info("LuckyD Code 2.1.0")

    elif cmd == "":
        pass  # Empty command

    else:
        ui.warn(f"Unknown command: /{cmd}. Try /help")

    return False


# ── Main application ──────────────────────────────────────────────────


async def run_one_shot(agent: CodingAgent, message: str):
    """Single query mode with streaming."""
    agent.stream_callback = ui.stream_token
    agent.think_callback = ui.stream_think_token
    ui.start_streaming()
    result = ""
    try:
        result = await agent.run(message)
    except Exception as e:
        ui.error(f"Agent error: {e}")
        result = ""
    finally:
        ui.end_streaming()
    if result and not ui.streamed_chars:
        ui.markdown(result)


async def run_one_shot_json(agent: CodingAgent, message: str):
    """Single query mode -- clean JSON-line output for editor extensions."""
    agent.stream_callback = lambda token: (
        sys.stdout.write(json.dumps({"type": "token", "text": token}) + chr(10))
    )
    agent.think_callback = lambda token: (
        sys.stdout.write(json.dumps({"type": "thinking", "text": token}) + chr(10))
    )
    result = ""
    try:
        result = await agent.run(message)
    except Exception as e:
        json.dump({"type": "error", "text": str(e)}, sys.stdout)
        sys.stdout.write(chr(10))
        sys.stdout.flush()
        return
    finally:
        sys.stdout.flush()
    if result:
        json.dump({"type": "result", "text": result[:100000]}, sys.stdout)
        sys.stdout.write(chr(10))
    json.dump({"type": "done"}, sys.stdout)
    sys.stdout.write(chr(10))
    sys.stdout.flush()


async def run_repl(agent: CodingAgent):
    """Interactive REPL with streaming and session info."""

    # Show enhanced banner with project info
    project_name = (
        agent._project_info.name
        if agent._project_info and not agent._project_info.is_empty()
        else ""
    )
    ui.set_session_info(
        project_name=project_name,
        provider=agent.provider_name,
        model=getattr(agent, "model", "") or "",
    )
    ui.enhanced_banner()

    while True:
        try:
            user_input = ui.prompt()
        except (KeyboardInterrupt, EOFError):
            cost = agent.cost_tracker.summary() if hasattr(agent, "cost_tracker") else ""
            ui.goodbye(cost_summary=cost)
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            should_exit = await handle_command(agent, user_input)
            if should_exit:
                cost = agent.cost_tracker.summary() if hasattr(agent, "cost_tracker") else ""
                ui.goodbye(cost_summary=cost)
                break
            continue

        # Normal message — stream response
        agent.stream_callback = ui.stream_token
        agent.think_callback = ui.stream_think_token
        ui.start_streaming()
        result = ""
        try:
            result = await agent.run(user_input)
        except Exception as e:
            ui.error(f"Agent error: {e}")
            result = ""
        finally:
            ui.end_streaming()
        if result and not ui.streamed_chars:
            ui.markdown(result)


# ── Entry point ────────────────────────────────────────────────────────


def main():
    # Parse CLI args
    args = sys.argv[1:]
    cfg = get_config()
    model = cfg["model"]
    temperature = cfg["temperature"]
    one_shot = ""
    auto_approve = False
    resume_session_id = ""

    json_mode = False
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model = resolve_model(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                preferred=args[i + 1],
                thinking=cfg.get("thinking", False),
            )
            i += 2
        elif args[i] == "--provider" and i + 1 < len(args):
            os.environ["CODING_AGENT_PROVIDER"] = args[i + 1]
            cfg = get_config()
            i += 2
        elif args[i] == "--thinking":
            os.environ["CODING_AGENT_THINKING"] = "true"
            cfg = get_config()
            model = cfg["model"]
            i += 1
        elif args[i] == "--temp" and i + 1 < len(args):
            temperature = float(args[i + 1])
            i += 2
        elif args[i] in ("-y", "--yes", "--auto-approve"):
            auto_approve = True
            os.environ["CODING_AGENT_AUTO_APPROVE"] = "1"
            i += 1
        elif args[i] == "--max-turns" and i + 1 < len(args):
            os.environ["CODING_AGENT_MAX_TURNS"] = args[i + 1]
            cfg = get_config()
            i += 2
        elif args[i] in ("-c", "--continue"):
            resume_session_id = "latest"
            i += 1
        elif args[i] == "--resume" and i + 1 < len(args):
            resume_session_id = args[i + 1]
            i += 2
        elif args[i] in ("-v", "--version"):
            print("LuckyD Code 2.1.0")
            sys.exit(0)
        elif args[i] == "--help":
            print(
                """
LuckyD Code — AI Coding Agent  v2.1.0

Usage:
  lucky-code                       Interactive REPL
  lucky-code "your query"          One-shot mode
  lucky-code -c                    Continue last session
  lucky-code --resume <id>         Resume specific session

Options:
  --model NAME       Model: auto (default), flash, pro, or specific name
  --provider NAME    Set provider: deepseek, openai, anthropic, google,
                     ollama, zai, openrouter
  --thinking         Use the thinking/reasoning model (pro)
  --temp FLOAT       Temperature (default: 0.0)
  -y, --yes          Auto-approve all tool calls (non-interactive mode)
  --max-turns N      Override max agent turns (default: 30)
  -c, --continue     Resume most recent session
  --resume <id>      Resume a specific session by ID or prefix
  --json             Structured JSON-line output (for extensions)
  -v, --version      Show version
  --help             Show this help

Environment:
  <PROVIDER>_API_KEY   Set in .env for your provider
  CODING_AGENT_PROVIDER Explicit provider override
  CODING_AGENT_AUTO_APPROVE=1   Bypass all tool approvals
"""
            )
            sys.exit(0)
        elif args[i] == "--json":
            json_mode = True
            i += 1
        else:
            one_shot = " ".join(args[i:])
            break

    # Validate API key
    if not cfg["api_key"] or cfg["api_key"] == "sk-your-api-key-here":
        if one_shot:
            # One-shot mode -- cannot interact; exit with instructions
            ui.error("DEEPSEEK_API_KEY not set.")
            print(f"  Set it in {PROJECT_DIR / '.env'} or as an environment variable.")
            print("  Get a key: https://platform.deepseek.com/api_keys")
            sys.exit(1)
        else:
            # REPL mode -- prompt the user interactively
            _prompt_and_save_api_key("DEEPSEEK_API_KEY", "DeepSeek")
            # Re-resolve config with the new key and model
            cfg = get_config()
            model = cfg["model"]

    # Create agent
    agent = CodingAgent(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=model,
        temperature=temperature,
        max_tokens=cfg["max_tokens"],
    )

    # Wire approval hook
    if auto_approve or not sys.stdin.isatty():
        hook = ApprovalHook(session_id=agent.conversation_id)
        hook.auto_approve_all = True
        register_plugin(hook)
    else:
        register_plugin(
            ApprovalHook(
                approval_callback=_console_approval,
                session_id=agent.conversation_id,
            )
        )

    # Connect MCP servers
    mcp_manager = MCPManager()
    try:
        loop = asyncio.new_event_loop()
        n_srv = loop.run_until_complete(mcp_manager.connect_all())
        if n_srv:
            n_tools = register_mcp_tools(mcp_manager)
            print(f"  [MCP] {n_srv} server(s), {n_tools} tool(s) registered")
        loop.close()
        agent._mcp_manager = mcp_manager
    except Exception as e:
        print(f"  [MCP] Connection: {e}")
        agent._mcp_manager = mcp_manager

    # Session resume
    if resume_session_id == "latest":
        sess = get_session_store().latest()
        if sess:
            agent.restore_session(sess)
            print(f"  [Session] Resumed: {(sess.get('preview') or '')[:60]}")
    elif resume_session_id:
        sess = get_session_store().load(resume_session_id)
        if sess:
            agent.restore_session(sess)
            print(f"  [Session] Resumed: {(sess.get('preview') or '')[:60]}")

    try:
        if one_shot:
            if json_mode:
                asyncio.run(run_one_shot_json(agent, one_shot))
            else:
                asyncio.run(run_one_shot(agent, one_shot))
        else:
            asyncio.run(run_repl(agent))
    finally:
        with contextlib.suppress(Exception):
            agent.save_session()
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(mcp_manager.close_all())
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()

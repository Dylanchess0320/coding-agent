# LuckyD Code

> AI-powered coding agent for Windows — work in your terminal or VS Code.

**Version:** 2.1.0

## Quick Start

| Step | Command |
|------|---------|
| **Run** | `run.bat` or `python main.py` |
| **One-shot** | `python main.py "refactor this file"` |
| **Help** | `python main.py --help` |

```
run.bat  → interactive REPL
  type /help for commands
  type /model to switch providers
```

## Requirements

- Python 3.10 – 3.12
- Git (for repo-aware features)
- Set `DEEPSEEK_API_KEY` (or your LLM provider key) in `.env`

## Project Layout

```
coding-agent/
├── main.py              ← Entry point
├── ui.py                ← Terminal UI
├── config.py            ← Paths + runtime settings
├── agent.py             ← Core agent logic
├── core/                ← Agent loop, LLM client, providers
├── tools/               ← Tool registry (bash, files, web, git, LSP, memory, …)
├── vscode-extension/    ← VS Code webview extension
├── assets/              ← Static assets (chat.html)
├── data/                ← Runtime data (memory, tasks, workspace, checkpoints)
├── scripts/             ← Helper scripts (auth, build)
├── installers/          ← Python / Git installers
├── docs/                ← Documentation source
├── tests/               ← Test suite
├── .env                 ← Your API keys (create from .env.example)
└── run.bat              ← Windows launcher
```

## Multiple Providers

Configure in `.env` — uncomment **one**:

| Provider | Key | Default Model |
|----------|-----|---------------|
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| OpenAI | `OPENAI_API_KEY` | gpt-4o |
| Anthropic | `ANTHROPIC_API_KEY` | claude-sonnet-4 |
| Google | `GOOGLE_API_KEY` | gemini-2.0-flash |
| Ollama | *(none)* | codellama |
| Z.ai (GLM) | `ZAI_API_KEY` | glm-4.5 |
| OpenRouter | `OPENROUTER_API_KEY` | deepseek/deepseek-chat-v3.1 |

Swap models at runtime inside the REPL:
```
/model openai gpt-4o
/model anthropic claude-sonnet-4-20250514
/model zai glm-4.6
```

## MCP (Model Context Protocol)

Connect to any MCP server for extensible tooling:

1. Copy `mcp_config.example.json` to `mcp_config.json`
2. Add your servers (filesystem, github, playwright, etc.)
3. Tools auto-register as `mcp__<server>__<tool>`

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/project"]
    }
  }
}
```

## Sessions & Resume

Every run is auto-saved. Resume with:
```
lucky-code --continue          # resume most recent
lucky-code --resume conv_2025  # resume by ID prefix
/sessions                      # list in REPL
/resume conv_2025              # switch mid-REPL
```

## Project Rules (AGENTS.md)

LuckyD Code auto-loads `AGENTS.md`, `.clinerules`, `.goosehints`, and
`CLAUDE.md` from your workspace into the system prompt.

## License

Proprietary. All rights reserved.





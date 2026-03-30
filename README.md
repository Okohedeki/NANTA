# Nexus

An agentic desktop app that gives you remote access to Claude Code through Telegram and Discord, with a built-in knowledge graph that automatically extracts and connects entities from everything you share.

## Features

- **Multi-platform** - Control Claude Code from Telegram, Discord, or both simultaneously
- **Knowledge Graph** - Share URLs, audio, video, or PDFs and Nexus auto-extracts entities, relationships, and summaries into a searchable graph
- **Desktop UI** - Native desktop window with interactive D3.js graph visualization, notes editor, and category management
- **Shell Access** - Execute shell commands remotely from your phone
- **Session Management** - Per-user Claude sessions with cost tracking, model switching, and working directory control
- **Setup Wizard** - First-run guided setup in the desktop UI, no manual config needed
- **Standalone Build** - Package as a Windows desktop app with PyInstaller

## Quick Start

### 1. Install

```bash
git clone <your-repo-url>
cd Nexus
pip install -r requirements.txt
```

### 2. Launch

```bash
python launcher.py
```

On first launch, the desktop app opens a setup wizard where you can configure your Telegram and/or Discord bot tokens. Follow the step-by-step instructions to create your bots.

### 3. Use

Send messages to your bot on Telegram or Discord:

```
Hello, can you help me write a Python script?   (plain text → Claude)
/sh ls -la                                       (shell command)
/status                                          (session info)
https://example.com/article                      (auto-ingest URL)
```

## Commands

| Command | Description |
|---------|-------------|
| *(plain text)* | Chat with Claude Code |
| `/claude <prompt>` | Send prompt to Claude (alias: `/cl`) |
| `/sh <command>` | Execute shell command |
| `/cancel` | Kill running Claude process |
| `/status` | Show session info |
| `/cwd [path]` | Get/set working directory |
| `/model [name]` | Get/set Claude model |
| `/newsession` | Start fresh Claude session |
| `/mcp <subcommand>` | Manage MCP servers |
| `/kg <question>` | Query knowledge graph |
| `/kgsearch <term>` | Search entities |
| `/kgstats` | Graph statistics |
| `/kgrecent` | Recent ingestions |

## Architecture

```
Nexus
├── launcher.py              # Entry point: starts all processes
├── config.py                # Multi-platform config loader
├── core/                    # Platform-agnostic business logic
│   ├── auth.py              # Authorization decorator
│   └── commands.py          # All command handlers
├── platforms/               # Platform adapters
│   ├── base.py              # PlatformContext protocol
│   ├── telegram/            # Telegram bot + adapter
│   └── discord/             # Discord bot + adapter
├── services/                # Shared services (no platform deps)
│   ├── claude_runner.py     # Claude Code session management
│   ├── shell_runner.py      # Shell command execution
│   ├── content_extractor.py # URL/media content extraction
│   ├── entity_extractor.py  # Claude-powered entity extraction
│   ├── ingestion_service.py # Ingestion pipeline orchestrator
│   ├── knowledge_graph.py   # SQLite knowledge graph
│   ├── transcriber.py       # Whisper audio transcription
│   └── output_formatter.py  # Message chunking
└── web/                     # Desktop UI
    ├── server.py            # FastAPI backend + setup API
    └��─ static/index.html    # Knowledge graph viewer
```

## Configuration

All settings are stored in `.env` (created by the setup wizard or manually from `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | *(optional)* |
| `TELEGRAM_ALLOWED_IDS` | Allowed Telegram chat IDs | |
| `DISCORD_BOT_TOKEN` | Discord bot token | *(optional)* |
| `DISCORD_ALLOWED_IDS` | Allowed Discord user/channel IDs | |
| `DEFAULT_CWD` | Working directory | `.` |
| `DEFAULT_MODEL` | Claude model | `sonnet` |
| `CLAUDE_TIMEOUT` | Claude timeout (seconds) | `300` |
| `SHELL_TIMEOUT` | Shell timeout (seconds) | `60` |
| `MAX_BUDGET_USD` | Max budget per request | `1.0` |

At least one platform token must be configured.

## Building

Build a standalone Windows desktop app:

```bash
python build.py
```

Output: `dist/Nexus/Nexus.exe`

To auto-start on login:

```bash
python install_startup.py        # Python mode
python install_startup.py --exe  # Built exe mode
python install_startup.py --remove
```

## Prerequisites

- Python 3.11+
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- A Telegram and/or Discord bot token

## License

MIT

# ToolKinetik

A self-extending agent framework built on Agno. The system detects missing capabilities autonomously, generates new skills via a coding agent, validates them in a Docker sandbox using TDD, and permanently registers them into its own tool registry at runtime.

## Features

- **Dynamic Tool Registry** — Skills are loaded from the filesystem at runtime using `importlib`. New skills are hot-reloadable without restarting the system.
- **Autonomous Skill Creation** — When a user request requires a capability the system does not have, the master agent detects the gap and triggers a coding agent to build the missing skill.
- **Sandboxed TDD Pipeline** — Generated code is executed and tested inside an isolated Docker container (network disabled, memory and CPU limited). Only skills that pass all tests and security checks are promoted.
- **Dual Storage** — Skill code lives on the filesystem (`skills/*.py`); metadata (version, author, status, git commit) is tracked in an SQLite database.
- **Multi-Interface** — Control the system via FastAPI REST/WebSocket API, a Typer CLI, or a NiceGUI web dashboard with ARIA accessibility support.
- **OpenAI-Compatible LLM Backend** — Any OpenAI-compatible endpoint works (OpenAI, Ollama, Azure, local models). Configured via environment variables.
- **Safety Checks** — AST-based validation forbids `os.system`, `subprocess`, `eval`, `exec`, and dangerous imports in generated skills. Git-based rollback for faulty skills.

## Architecture

```
User Interfaces (NiceGUI / CLI)
        |
  FastAPI Hub (:8000)
        |
  Agno Master Router
        |
  +----------------+----------------+
  |                 |                |
  v                 v                v
Execution       Coding Agent      Sandbox (Docker)
Runtime         (Claude Code)     TDD + Security
(Dynamic        -> Plan           -> Test
 Skills)        -> TDD            -> Promote
                -> Review         -> Rollback
```

### Skill-Creation Loop

1. User sends a request the system cannot fulfill.
2. Intent detector identifies the missing capability and generates a skill specification.
3. Coding agent (Claude Code CLI, with Codex/OpenCode fallback) writes code and tests following TDD methodology.
4. Sandbox runs pytest and security checks in an isolated Docker container.
5. On success: skill is promoted to the production registry, hot-reloaded, and the original request is executed.
6. On failure: traceback is fed back to the coding agent for debugging (up to 3 retries).

## Project Structure

```
toolkinetik/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── src/toolkinetik/
│   ├── config.py          # Environment-based configuration
│   ├── registry.py        # Dynamic tool registry with hot-reload
│   ├── db.py              # SQLite metadata store
│   ├── coding_agent.py    # Claude Code wrapper + CLI delegation
│   ├── sandbox.py         # Docker sandbox runner
│   ├── tdd_loop.py        # TDD loop with security checks
│   ├── promotion.py       # Skill promotion and rollback
│   ├── intent.py          # Intent detection + skill creation orchestrator
│   ├── safety.py          # Safety checker + version manager
│   ├── auto_docs.py       # Automatic documentation generator
│   ├── app.py             # FastAPI core engine (API-key auth, WebSocket)
│   ├── cli.py             # Typer + Rich CLI
│   └── ui.py              # NiceGUI dashboard (ARIA accessibility)
├── skills/
│   ├── __init__.py
│   ├── weather_skill.py
│   └── math_skill.py
├── data/
│   └── .gitkeep
└── tests/
    └── (13 test modules, 126 tests)
```

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for sandbox execution)

### Installation

```bash
git clone <repo-url> toolkinetik
cd toolkinetik
uv sync
uv sync --extra dev
```

### Configuration

```bash
cp .env.example .env
```

Edit `.env` with your settings:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_BASE` | `http://localhost:11434/v1` | OpenAI-compatible API endpoint |
| `OPENAI_API_KEY` | (empty) | API key for the LLM endpoint |
| `OPENAI_MODEL` | `gpt-4o` | Model identifier |
| `AGNO_API_KEY` | (auto-generated) | API key for FastAPI authentication |
| `SANDBOX_IMAGE` | `python:3.12-slim` | Docker image for sandbox containers |
| `SKILLS_DIR` | `skills/` | Directory for skill modules |
| `DB_PATH` | `data/toolkinetik.db` | SQLite database path |

### Running Tests

```bash
uv run pytest tests/ -v
```

### Starting the System

FastAPI backend:

```bash
uv run uvicorn toolkinetik.app:app --host 0.0.0.0 --port 8000
```

NiceGUI dashboard:

```bash
uv run python -m toolkinetik.ui
```

CLI:

```bash
uv run python -m toolkinetik.cli health
uv run python -m toolkinetik.cli skills list
uv run python -m toolkinetik.cli skills reload
```

### Docker

```bash
docker compose up -d
```

Services:

| Service | Port | Description |
|---|---|---|
| `core` | 8000 | FastAPI backend |
| `ui` | 8080 | NiceGUI dashboard |
| `sandbox` | — | Docker-in-Docker for isolated test execution |

## Tech Stack

| Component | Technology |
|---|---|
| Agent Core | Agno (formerly Phidata) |
| LLM Backend | OpenAI-compatible endpoint (user-configurable) |
| Coding Agent | Claude Code CLI (primary), Codex/OpenCode (fallback) |
| Sandbox | Docker SDK for Python |
| API | FastAPI + WebSockets + API-key auth |
| Web UI | NiceGUI + public-ui (accessibility) |
| CLI | Typer + Rich |
| Testing | Pytest, Ruff, Mypy |
| Storage | Filesystem + SQLite |
| Package Manager | uv |

## License

MIT
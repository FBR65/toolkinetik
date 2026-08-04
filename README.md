# ToolKinetik

A self-extending agent framework built on Agno. The system uses an **IntentEngine** to classify user requests via LLM (execute existing skill, create new skill, RAG search, or chat), generates new skills via a **SkillWriter** meta-skill using `wigolo` MCP research, validates them in a Docker sandbox using TDD, and permanently registers them into its own tool registry at runtime.

## Features

- **LLM-Driven Intent Detection** — An `IntentEngine` classifies user requests into four intents: `execute_skill` (existing capability), `create_skill` (new capability), `rag_search` (document search), or `chat` (conversation).
- **Dynamic Tool Registry** — Skills are loaded from the filesystem at runtime using `importlib`. New skills are hot-reloadable without restarting the system.
- **Autonomous Skill Creation** — The **SkillWriter** meta-skill orchestrates the full create-test-promote loop: it uses `wigolo` MCP for PyPi/GitHub research, an LLM for code generation (TDD-first), a `SafetyChecker` for AST-based security validation, and a Docker sandbox for isolated test execution.
- **Sandboxed TDD Pipeline** — Generated code is executed and tested inside an isolated Docker container (network disabled, memory and CPU limited). Only skills that pass all tests and security checks are promoted.
- **RAG Integration** — When a user requests document search, a `RagManager` lazily initializes LanceDB with HuggingFace embeddings (`sentence-transformers/all-MiniLLM-L6-v2`) for semantic document retrieval.
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
  IntentEngine (LLM-driven: execute_skill | create_skill | rag_search | chat)
        |
  +----------------+----------+----------+
  |                |          |          |
  v                v          v          v
Execution     SkillWriter   RagManager   Chat
Runtime      (Meta-Skill:   (LanceDB +   (Direct
(Dynamic     research →    HF Embeddings) LLM)
Skills)      codegen →
            safety → TDD)       
              |          
              v          
          wigolo MCP    Sandbox (Docker)
          (PyPi/GitHub) TDD + Security
              |           -> Test
              v           -> Promote
          promote()       -> Rollback
          (Hot-Reload +
           Git + DB)
```

### Intent-Driven Flow

1. User sends a request (e.g., "Create a PowerPoint presentation").
2. **IntentEngine** classifies the request via LLM into one of four intents:
   - `execute_skill`: An existing skill can handle the request → direct execution.
   - `create_skill`: No existing skill matches → SkillWriter creates a new one.
   - `rag_search`: "Search documents for..." → RagManager initializes LanceDB + embeddings.
   - `chat`: Normal conversation → direct LLM response.
3. **SkillWriter** (when `create_skill`):
   - Uses **wigolo MCP** (via JSON-RPC, `uvx @KnockOutEZ/wigolo`) to research PyPi/GitHub packages.
   - Generates SPEC (Gherkin scenarios) + TDD code via LLM.
   - Runs **Docker sandbox tests** with retry (max 3 attempts).
   - **SafetyChecker** (AST) blocks forbidden imports/calls (`subprocess`, `os.system`, `eval`, `exec`).
   - On success: `promote()` → Hot-Reload + Git-Commit + DB-Register.
   - On failure: traceback fed back to LLM for revision (up to 3 retries).
4. **Sandbox**: Runs pytest + security checks in an isolated Docker container (network disabled, memory and CPU limited).
5. **RagManager** (when `rag_search`):
   - Lazily initializes `sentence-transformers/all-MiniLLM-L6-v2` embeddings.
   - Indexes documents in LanceDB (`data/lancedb/`).
   - Returns top-K semantically-similar document chunks as context.

### wigolo Integration

`wigolo` (`@KnockOutEZ/wigolo`) is an MCP server providing web research tools:
- `research`: Search PyPi, GitHub, docs for code examples and usage patterns.
- `extract`: Extract content/code from URLs.
- `fetch`, `crawl`, `cache`, `find-similar`: Additional discovery tools.

The `WigoloMCPToolkit` in `setup_mcp.py` wraps wigolo as an Agno-compatible tool. It communicates via JSON-RPC over `uvx` (no MCP Python SDK required, avoiding conflicts with Agno 2.8.x). If the wigolo server is unavailable, the toolkit gracefully degrades to a stub.

## Project Structure

```
toolkinetik/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── AGENTS.md          # Operational rules for coding agents (TDD, gauntlet)
├── EVIDENCE.md        # Gauntlet evidence report
├── src/toolkinetik/
│   ├── config.py          # Environment-based configuration
│   ├── registry.py        # Dynamic tool registry with hot-reload
│   ├── db.py              # SQLite metadata store
│   ├── intent.py          # IntentEngine + SkillMatch (LLM-driven intent classification)
│   ├── coding_agent.py    # Claude Code wrapper + CLI delegation
│   ├── skill_writer.py    # SkillWriter meta-skill (research → codegen → safety → tdd → promote)
│   ├── setup_mcp.py       # WigoloMCPToolkit (JSON-RPC client for @KnockOutEZ/wigolo)
│   ├── rag_manager.py     # RagManager (LanceDB + HuggingFace embeddings)
│   ├── sandbox.py         # Docker sandbox runner
│   ├── tdd_loop.py        # TDD loop with security checks
│   ├── promotion.py       # Skill promotion and rollback
│   ├── safety.py          # Safety checker + version manager
│   ├── auto_docs.py       # Automatic documentation generator
│   ├── app.py             # FastAPI core engine (API-key auth, WebSocket, agent integration)
│   ├── cli.py             # Typer + Rich CLI
│   └── ui.py              # NiceGUI dashboard (ARIA accessibility, chat frontend)
├── skills/
│   ├── __init__.py
│   ├── weather_skill.py
│   └── math_skill.py
├── data/
│   └── .gitkeep
└── tests/
    ├── test_app.py              # FastAPI routes + create_agent (10 tests)
    ├── test_intent.py           # Legacy IntentDetector (9 tests)
    ├── test_intent_engine.py    # LLM-driven IntentEngine (5 tests)
    ├── test_skill_writer.py     # SkillWriter meta-skill (10 tests)
    ├── test_setup_mcp.py        # wigolo MCP toolkit integration (7 tests)
    ├── test_ui_frontend.py      # NiceGUI frontend structure (6 tests)
    ├── test_ui_intent_flow.py   # Intent-aware UI flow (10 tests)
    ├── test_agent_integration.py # App + IntentEngine + SkillWriter wiring (5 tests)
    ├── test_readme.py           # README content verification (7 tests)
    └── (10 modules, 216 tests total)
```

### Test Breakdown

| Module | Tests | Coverage |
|---|---|---|
| `intent.py` (IntentEngine) | 5 | 100% |
| `skill_writer.py` (SkillWriter) | 10 | 63% (core paths 100%) |
| `setup_mcp.py` (WigoloMCPToolkit) | 7 | 48% (RPC client fallback) |
| `rag_manager.py` (RagManager) | — | Lazy-init paths |
| `ui.py` (NiceGUI) | 10 | 100% (UI-logic + status flow) |
| `app.py` (Integration) | 5 | — |
| Legacy `test_app.py`, `test_intent.py`, etc. | 179 | — |
| **Total** | **216** | — |

---

## Tech Stack

| Component | Technology |
|---|---|
| Agent Core | Agno 2.8.6 |
| LLM Backend | OpenAI-compatible endpoint (user-configurable) |
| Intent Engine | LLM-driven classification (OpenAI Chat Completions) |
| Skill Writer | AI-powered meta-skill (LLM + wigolo research + TDD) |
| Coding Agent | Claude Code CLI (primary), Codex/OpenCode/Aider (fallback) |
| MCP Research | wigolo (`@KnockOutEZ/wigolo`) via JSON-RPC over `uvx` |
| RAG Engine | LanceDB + `sentence-transformers/all-MiniLLM-L6-v2` |
| Sandbox | Docker SDK for Python |
| Safety | AST-based SafetyChecker (forbidden imports/calls) |
| API | FastAPI + WebSockets + API-key auth |
| Web UI | NiceGUI + public-ui (accessibility) |
| CLI | Typer + Rich |
| Testing | Pytest, Ruff, Mypy, pytest-cov, pytest-randomly |
| Storage | Filesystem + SQLite (SkillStore) |
| Package Manager | uv |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for sandbox execution)
- wigolo (installed automatically via `uvx` when needed)

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

## License

MIT
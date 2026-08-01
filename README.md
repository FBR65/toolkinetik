# ToolKinetik

Selbsterweiterndes Agentenframework.

## Quick Start

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest tests/ -v

# Configuration
cp .env.example .env
```

## Architecture

- **src/toolkinetik/** — Core framework
- **skills/** — Dynamic skill modules (hot-reloadable)
- **data/** — SQLite metadata store
- **tests/** — Test suite
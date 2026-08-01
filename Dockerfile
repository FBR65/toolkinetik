# ---- Builder stage ----
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first for better caching
COPY pyproject.toml ./

# Install dependencies into a virtual env
RUN uv sync --no-dev --no-install-project

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy virtual env from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:${PATH}"

# Copy application source
COPY pyproject.toml ./
COPY src/ ./src/
COPY skills/ ./skills/
COPY data/ ./data/

# Install the project itself
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv sync --no-dev --no-install-project

# Expose core API (8000) and UI (8080)
EXPOSE 8000 8080

# Default command
CMD ["uv", "run", "uvicorn", "agno_agent_os.main:app", "--host", "0.0.0.0", "--port", "8000"]
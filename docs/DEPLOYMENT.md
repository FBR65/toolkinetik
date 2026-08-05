# Deployment Guide — ToolKinetik

## Quick Start (Docker Compose)

```bash
# 1. Konfiguration
cp .env.example .env
# Edit .env — set AGNO_API_KEY (required in production!)

# 2. Build & Start
docker compose up -d

# 3. Verify
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/deep
```

Services:
| Service | Port | Description |
|---|---|---|
| `core` | 8000 | FastAPI backend (REST + WebSocket) |
| `ui` | 8080 | NiceGUI dashboard |
| `sandbox` | — | Docker-in-Docker for skill tests |

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AGNO_API_KEY` | **Yes (prod)** | (auto-gen in dev) | API key for authentication. In production, MUST be set explicitly. |
| `TOOLKINETIK_DEV` | No | (empty) | Set to `1` for development (allows API-key auto-gen). |
| `OPENAI_API_BASE` | No | `http://localhost:11434/v1` | OpenAI-compatible LLM endpoint. |
| `OPENAI_API_KEY` | No | (empty) | API key for the LLM endpoint. |
| `OPENAI_MODEL` | No | `gpt-4o` | Model identifier. |
| `LLM_TIMEOUT` | No | `60` | LLM call timeout in seconds. |
| `SANDBOX_IMAGE` | No | `python:3.12-slim` | Docker image for sandbox containers. |
| `SKILLS_DIR` | No | `skills/` | Directory for skill modules. |
| `DB_PATH` | No | `data/toolkinetik.db` | SQLite database path. |
| `TOOLKINETIK_API_URL` | No | `http://localhost:8000` | API URL for CLI/UI. |
| `TOOLKINETIK_LOG_LEVEL` | No | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR). |

## Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl;
    server_name toolkinetik.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Metrics (restrict access)
    location /metrics {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://localhost:8000;
    }

    # UI
    location / {
        proxy_pass http://localhost:8080;
    }
}
```

## TLS

Use Let's Encrypt with certbot:
```bash
sudo certbot --nginx -d toolkinetik.example.com
```

## Health Checks

```bash
# Liveness (process only)
curl http://localhost:8000/api/health

# Readiness (checks Docker, LLM, RAG)
curl http://localhost:8000/api/health/deep
```

The deep health endpoint returns:
```json
{
  "status": "healthy|degraded|unhealthy",
  "checks": {
    "docker": {"status": "healthy", "detail": "..."},
    "llm": {"status": "healthy", "detail": "..."},
    "rag": {"status": "healthy", "detail": "..."}
  }
}
```

## Metrics (Prometheus)

```bash
curl http://localhost:8000/metrics
```

Configure in `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: toolkinetik
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
```

## Rate Limits

Default: 60 requests/minute per API key. WebSocket: 20 messages/minute.
Configurable via code (`set_rate_limit()`).

## Production Checklist

- [ ] `AGNO_API_KEY` set as environment variable (NOT auto-generated)
- [ ] `TOOLKINETIK_DEV` NOT set (or empty)
- [ ] `OPENAI_API_BASE` points to a reachable LLM endpoint
- [ ] Docker daemon running (for sandbox)
- [ ] Reverse proxy configured with TLS
- [ ] `/metrics` endpoint access restricted
- [ ] Backup strategy for `data/` and `skills/` in place
- [ ] Log aggregation configured (structured JSON logs to stdout)
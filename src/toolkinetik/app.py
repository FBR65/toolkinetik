"""FastAPI core engine for ToolKinetik.

Endpoints:
    GET  /api/health       — no auth, returns {"status": "healthy"}
    POST /api/reload-skills — auth required, hot-reloads skills
    GET  /api/skills        — auth required, lists loaded skills
    WS   /ws/chat           — auth via ?api_key= query param, streams responses
"""

from __future__ import annotations

import json
import secrets
import threading
from collections import defaultdict

from fastapi import Depends, FastAPI, Security, WebSocket, WebSocketDisconnect
from fastapi.security import APIKeyHeader

from toolkinetik.config import get_settings
from toolkinetik.intent import IntentEngine
from toolkinetik.rag_manager import RagManager
from toolkinetik.registry import DynamicToolRegistry
from toolkinetik.skill_writer import SkillWriter

# --- WebSocket connection tracking (P2.3) ---
_ws_connections: dict[str, int] = defaultdict(int)
_ws_max_per_key: int = 5
_ws_conn_lock = threading.Lock()


def get_max_ws_connections() -> int:
    return _ws_max_per_key


def set_max_ws_connections(limit: int) -> None:
    global _ws_max_per_key
    _ws_max_per_key = limit


def get_active_ws_connections(api_key: str) -> int:
    return _ws_connections.get(api_key, 0)


def increment_ws_connection(api_key: str) -> None:
    with _ws_conn_lock:
        _ws_connections[api_key] += 1


def decrement_ws_connection(api_key: str) -> None:
    with _ws_conn_lock:
        _ws_connections[api_key] = max(0, _ws_connections.get(api_key, 0) - 1)


def reset_ws_connections() -> None:
    with _ws_conn_lock:
        _ws_connections.clear()

# --- Settings & registry --------------------------------------------------
settings = get_settings()
registry = DynamicToolRegistry(settings.SKILLS_DIR)

# --- FastAPI app -----------------------------------------------------------
app = FastAPI(title="ToolKinetik", version="0.1.0")

# Rate limiting middleware (P1.3)
from toolkinetik.rate_limiter import rate_limit_middleware

app.middleware("http")(rate_limit_middleware)

# API-Key security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency that validates the X-API-Key header."""
    if api_key is None or not secrets.compare_digest(api_key, settings.AGNO_API_KEY):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


def _tool_names() -> list[str]:
    """Return the names of currently registered tools."""
    return [t.__name__ for t in registry.registered_tools.values()]


# --- Integrated components (lazy singletons) ---------------------------------

_intent_engine: IntentEngine | None = None
_skill_writer: SkillWriter | None = None
_rag_manager: RagManager | None = None
_agent: object | None = None
_singleton_lock = threading.Lock()


def get_intent_engine() -> IntentEngine:
    """Return the singleton IntentEngine, initializing lazily (thread-safe)."""
    global _intent_engine
    if _intent_engine is None:
        with _singleton_lock:
            if _intent_engine is None:
                _intent_engine = IntentEngine(registry=registry)
    return _intent_engine


def get_skill_writer() -> SkillWriter:
    """Return the singleton SkillWriter (thread-safe)."""
    global _skill_writer
    if _skill_writer is None:
        with _singleton_lock:
            if _skill_writer is None:
                _skill_writer = SkillWriter()
    return _skill_writer


def get_rag_manager() -> RagManager:
    """Return the singleton RagManager (thread-safe)."""
    global _rag_manager
    if _rag_manager is None:
        with _singleton_lock:
            if _rag_manager is None:
                _rag_manager = RagManager()
    return _rag_manager


def get_agent():
    """Return the cached Agno Agent, creating it lazily on first use (thread-safe)."""
    global _agent
    if _agent is None:
        with _singleton_lock:
            if _agent is None:
                _agent = create_agent()
    return _agent


def invalidate_agent_cache() -> None:
    """Drop the cached Agent so the next get_agent() rebuilds it (after reload)."""
    global _agent
    with _singleton_lock:
        _agent = None


def create_agent():  # pragma: no cover — lazy import, needs LLM backend
    """Create an Agno Agent with IntentEngine + SkillWriter wired in.

    The agent gets:
      - All tools from the DynamicToolRegistry (existing skills)
      - The SkillWriter as a tool for autonomous skill creation
    Intent classification is handled separately via get_intent_engine().
    """
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    tools = registry.get_tools()
    skill_writer = get_skill_writer()
    # Register the skill_writer.write_skill as a callable tool
    tools.append(skill_writer.write_skill)

    model = OpenAIChat(
        id=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY or None,
        base_url=settings.OPENAI_API_BASE,
    )
    return Agent(model=model, tools=tools)


# --- Routes ----------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    """No-auth health check."""
    return {"status": "healthy"}


@app.get("/api/health/deep")
async def deep_health() -> dict:
    """Deep health check — checks Docker, LLM, and RAG subsystems.

    No auth required (like /api/health) so load balancers can probe it.
    """
    from toolkinetik.health import deep_health_check
    return deep_health_check()


@app.get("/metrics")
async def metrics() -> str:
    """Prometheus-format metrics endpoint (P1.5)."""
    from toolkinetik.metrics import get_metrics_text
    return get_metrics_text()


@app.post("/api/reload-skills", dependencies=[Depends(verify_api_key)])
async def reload_skills() -> dict:
    """Hot-reload skills from the skills directory."""
    registry.get_tools()
    invalidate_agent_cache()
    return {"status": "success", "loaded_tools": _tool_names()}


@app.get("/api/skills", dependencies=[Depends(verify_api_key)])
async def list_skills() -> dict:
    """List currently loaded skills."""
    # Ensure tools are loaded
    if not registry.registered_tools:
        registry.get_tools()
    return {"tools": _tool_names()}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    """WebSocket chat endpoint — auth via ?api_key= query param."""
    api_key = websocket.query_params.get("api_key")
    if api_key is None or not secrets.compare_digest(api_key, settings.AGNO_API_KEY):
        await websocket.close(code=1008)  # policy violation
        return

    # Connection limit per API key (P2.3)
    if get_active_ws_connections(api_key) >= _ws_max_per_key:
        await websocket.close(code=1008)  # policy violation
        return

    increment_ws_connection(api_key)
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Use cached agent; cache is invalidated on reload-skills.
            try:
                agent = get_agent()
                response = agent.run(data)
                content = response.content if hasattr(response, "content") else str(response)
                await websocket.send_text(json.dumps({"type": "response", "content": content}))
            except Exception as exc:  # pragma: no cover — needs LLM
                await websocket.send_text(json.dumps({"type": "error", "content": str(exc)}))
    except WebSocketDisconnect:
        pass
    finally:
        decrement_ws_connection(api_key)
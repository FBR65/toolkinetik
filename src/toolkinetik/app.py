"""FastAPI core engine for ToolKinetik.

Endpoints:
    GET  /api/health       — no auth, returns {"status": "healthy"}
    POST /api/reload-skills — auth required, hot-reloads skills
    GET  /api/skills        — auth required, lists loaded skills
    WS   /ws/chat           — auth via ?api_key= query param, streams responses
"""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Security, WebSocket, WebSocketDisconnect
from fastapi.security import APIKeyHeader

from toolkinetik.config import get_settings
from toolkinetik.registry import DynamicToolRegistry

# --- Settings & registry --------------------------------------------------
settings = get_settings()
registry = DynamicToolRegistry(settings.SKILLS_DIR)

# --- FastAPI app -----------------------------------------------------------
app = FastAPI(title="ToolKinetik", version="0.1.0")

# API-Key security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Dependency that validates the X-API-Key header."""
    if api_key is None or api_key != settings.AGNO_API_KEY:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


def _tool_names() -> list[str]:
    """Return the names of currently registered tools."""
    return [t.__name__ for t in registry.registered_tools.values()]


def create_agent():  # pragma: no cover — lazy import, needs LLM backend
    """Create an Agno Agent lazily (avoids importing agno.agent at module level).

    Importing ``agno.agent.Agent`` at module level would require a configured
    LLM backend even for simple health/skill requests, so we defer it here.

    Agno >= 2.x configures the LLM endpoint via an ``OpenAIChat`` model, not
    via ``Agent(api_key=..., base_url=...)``.
    """
    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    tools = registry.get_tools()
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


@app.post("/api/reload-skills", dependencies=[Depends(verify_api_key)])
async def reload_skills() -> dict:
    """Hot-reload skills from the skills directory."""
    registry.get_tools()
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
    if api_key is None or api_key != settings.AGNO_API_KEY:
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Create agent lazily and stream response
            try:
                agent = create_agent()
                response = agent.run(data)
                content = response.content if hasattr(response, "content") else str(response)
                await websocket.send_text(json.dumps({"type": "response", "content": content}))
            except Exception as exc:  # pragma: no cover — needs LLM
                await websocket.send_text(json.dumps({"type": "error", "content": str(exc)}))
    except WebSocketDisconnect:
        return
"""NiceGUI dashboard for ToolKinetik Control Center.

Structure:
    - Header (role="banner"): title + "Skills Neuladen" button
    - Left column 2/3 (role="main"): chat interface
    - Right column 1/3 (role="complementary"): skill monitor

All ui.run() calls are guarded by ``if __name__ == "__main__"`` so the
module is importable without starting a server.
"""

from __future__ import annotations

from toolkinetik.config import get_settings

# --- Constants (module level, importable without starting a server) --------

settings = get_settings()

API_BASE = settings.api_base_url
WS_URL = f"{API_BASE.replace('http', 'ws', 1)}/ws/chat?api_key={settings.AGNO_API_KEY}"
HEADERS = {"X-API-Key": settings.AGNO_API_KEY}

# Theme colours
THEME_PRIMARY = "#0284c7"
THEME_DARK = "#0f172a"

# --- Status indicators (module-level, reactive via NiceGUI) ------------------
# These are updated by send_message and the WebSocket handler to reflect
# the current agent state in the UI.
_agent_status: str = "Bereit"
_rag_status: str = "Aus"

# Phase-specific status messages
_PHASE_STATUS = {
    "chat": "Bereit",
    "execute_skill": "Führe Skill aus...",
    "create_skill": "Erstelle neuen Skill...",
    "rag_search": "Durchsuche Dokumente...",
    "research": "Suche auf PyPi/GitHub...",
    "generate": "Generiere Code...",
    "tdd": "Teste im Docker-Sandbox...",
    "promote": "Registriere Skill...",
}
_RAG_PHASE_STATUS = {
    "chat": "Aus",
    "rag_search": "Aktiv",
    "research": "Lade Embeddings...",
}


def _agent_status_label() -> str:
    """Return the current agent status text for the UI."""
    return f"Agent: {_agent_status}"


def _rag_status_label() -> str:
    """Return the current RAG status text for the UI."""
    return f"RAG: {_rag_status}"


def set_agent_status(status: str) -> None:
    """Update the agent status for the frontend display.

    Called by WebSocket handler when receiving phase updates.
    """
    global _agent_status
    _agent_status = status


def set_rag_status(status: str) -> None:
    """Update the RAG status for the frontend display."""
    global _rag_status
    _rag_status = status


def set_intent_phase(phase: str) -> None:
    """Update UI status based on the current intent phase.

    Maps phase names to human-readable status strings.
    """
    global _agent_status, _rag_status
    _agent_status = _PHASE_STATUS.get(phase, "Verarbeite...")
    _rag_status = _RAG_PHASE_STATUS.get(phase, _rag_status)


def reset_status() -> None:
    """Reset all status indicators to defaults."""
    global _agent_status, _rag_status
    _agent_status = "Bereit"
    _rag_status = "Aus"


# --- Page setup function (defined but not registered until run) ------------

def main_page() -> None:
    """Build the dashboard page.

    Uses NiceGUI components with ARIA attributes for accessibility.
    This function is registered with ``ui.page('/')`` only inside ``run()``.
    """
    from nicegui import ui

    # --- Dark theme -------------------------------------------------------
    ui.colors(primary=THEME_PRIMARY, dark=THEME_DARK)
    ui.dark_mode()

    # --- Header (role="banner") ------------------------------------------
    with ui.header().props('role="banner"'):
        ui.label("ToolKinetik Control Center").classes("text-xl font-bold")
        ui.button("Skills Neuladen", on_click=reload_skills).props(
            'aria-label="Skills neu laden"'
        ).classes("ml-auto")

    # --- Main layout: 2/3 chat + 1/3 sidebar ------------------------------
    with ui.row().classes("w-full"):
        # Left column — chat (role="main")
        with ui.column().classes("col-span-8").props('role="main"'):
            chat_container = ui.scroll_area().classes("h-96 w-full").props(
                'aria-live="polite" aria-label="Chat Nachrichten"'
            )
            with chat_container:
                ui.label("Willkommen im ToolKinetik Chat.").classes("text-gray-400")

            with ui.row().classes("w-full"):
                chat_input = ui.input(
                    placeholder="Nachricht eingeben...",
                ).props('aria-label="Chat Eingabefeld"').classes("flex-grow")
                ui.button("Senden", on_click=lambda: send_message(chat_input, chat_container)).props(
                    'aria-label="Nachricht senden"'
                )

        # Right column — skill monitor (role="complementary")
        with ui.column().classes("col-span-4").props('role="complementary"'):
            ui.label("Skill Monitor").classes("text-lg font-bold")
            ui.label("Status: Aktiv").props('aria-label="System Status"')
            ui.label(_rag_status_label())
            ui.label(_agent_status_label()).props('aria-label="Agent Status"')
            ui.label(f"Docker: configured (image: {settings.SANDBOX_IMAGE})").props(
                'aria-label="Sandbox Status"'
            )
            ui.label("Geladene Skills:").classes("mt-4")
            skill_list_container = ui.column().props('aria-label="Skill Liste"')
            with skill_list_container:
                ui.label("(Neu laden fuer Aktualisierung)")


# --- Action helpers --------------------------------------------------------

async def reload_skills() -> None:
    """Trigger skill reload via the API."""
    import httpx
    from nicegui import ui

    try:
        response = await httpx.AsyncClient().post(
            f"{API_BASE}/api/reload-skills",
            headers=HEADERS,
            timeout=10.0,
        )
        if response.status_code == 200:
            data = response.json()
            ui.notify(f"Skills neu geladen: {data.get('loaded_tools', [])}", color="positive")
        else:
            ui.notify(f"Reload failed: {response.status_code}", color="negative")
    except Exception as exc:
        ui.notify(f"Reload error: {exc}", color="negative")


async def send_message(chat_input, chat_container) -> None:
    """Send a chat message via WebSocket and display the response.

    Handles two message types from the server:
      - {"type": "response", "content": "..."}  — normal chat reply
      - {"type": "status", "phase": "...", "message": "..."}  — agent phase update
    """
    import json

    import websockets
    from nicegui import ui

    text = chat_input.value
    if not text:
        return
    chat_input.value = ""
    set_intent_phase("chat")
    try:
        with chat_container:
            ui.chat_message(text, name="User", sent=True)
        async with websockets.connect(WS_URL) as ws:
            await ws.send(text)
            while True:
                response = await ws.recv()
                data = json.loads(response)
                if isinstance(data, dict):
                    msg_type = data.get("type", "response")
                    if msg_type == "status":
                        phase = data.get("phase", "")
                        message = data.get("message", "")
                        set_intent_phase(phase)
                        if message:
                            set_agent_status(message)
                    elif msg_type == "response":
                        content = data.get("content", str(data))
                        with chat_container:
                            ui.chat_message(content, name="ToolKinetik", avatar="robot", sent=False)
                        reset_status()
                        break
                    elif msg_type == "error":
                        content = data.get("content", "Unknown error")
                        with chat_container:
                            ui.chat_message(content, name="Error", avatar="warning", sent=False)
                        reset_status()
                        break
                else:
                    content = str(data)
                    with chat_container:
                        ui.chat_message(content, name="ToolKinetik", avatar="robot", sent=False)
                    reset_status()
                    break
    except Exception as exc:
        ui.notify(f"Chat error: {exc}", color="negative")
        reset_status()


def run() -> None:
    """Register the page and start the NiceGUI server."""
    from nicegui import ui

    ui.page("/")(main_page)
    ui.run(
        title="ToolKinetik Control Center",
        dark=True,
        reload=False,
        port=8080,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
"""NiceGUI dashboard for Agno Agent OS Control Center.

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

API_BASE = "http://localhost:8000"
WS_URL = f"ws://localhost:8000/ws/chat?api_key={settings.AGNO_API_KEY}"
HEADERS = {"X-API-Key": settings.AGNO_API_KEY}

# Theme colours
THEME_PRIMARY = "#0284c7"
THEME_DARK = "#0f172a"


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
        ui.label("Agno Agent OS Control Center").classes("text-xl font-bold")
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
                ui.label("Willkommen im Agno Agent OS Chat.").classes("text-gray-400")

            with ui.row().classes("w-full"):
                chat_input = ui.input(
                    placeholder="Nachricht eingeben...",
                ).props('aria-label="Chat Eingabefeld"').classes("flex-grow")
                ui.button("Senden", on_click=lambda: send_message(chat_input)).props(
                    'aria-label="Nachricht senden"'
                )

        # Right column — skill monitor (role="complementary")
        with ui.column().classes("col-span-4").props('role="complementary"'):
            ui.label("Skill Monitor").classes("text-lg font-bold")
            ui.label("Status: Aktiv").props('aria-label="System Status"')
            ui.label(f"Docker: configured (image: {settings.SANDBOX_IMAGE})").props(
                'aria-label="Sandbox Status"'
            )
            ui.label("Geladene Skills:").classes("mt-4")
            skill_list_container = ui.column().props('aria-label="Skill Liste"')
            with skill_list_container:
                ui.label("(Neu laden für Aktualisierung)")


# --- Action helpers --------------------------------------------------------

async def reload_skills() -> None:
    """Trigger skill reload via the API."""
    import httpx

    try:
        response = await httpx.AsyncClient().post(
            f"{API_BASE}/api/reload-skills",
            headers=HEADERS,
            timeout=10.0,
        )
        if response.status_code == 200:
            data = response.json()
            print(f"Skills reloaded: {data.get('loaded_tools', [])}")
        else:
            print(f"Reload failed: {response.status_code}")
    except Exception as exc:
        print(f"Reload error: {exc}")


async def send_message(chat_input) -> None:
    """Send a chat message via WebSocket."""
    import json
    import websockets

    text = chat_input.value
    if not text:
        return
    chat_input.value = ""
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(text)
            response = await ws.recv()
            print(json.loads(response))
    except Exception as exc:
        print(f"Chat error: {exc}")


def run() -> None:
    """Register the page and start the NiceGUI server."""
    from nicegui import ui

    ui.page("/")(main_page)
    ui.run(
        title="Agno Agent OS Control Center",
        dark=True,
        reload=False,
        port=8080,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
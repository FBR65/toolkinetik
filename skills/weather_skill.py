"""Weather skill — example skill for the Agno Agent OS."""


def get_current_weather(location: str) -> str:
    """Ruft das aktuelle Wetter fuer einen bestimmten Ort ab.
    Args:
        location (str): Der Name der Stadt (z.B. 'Berlin', 'Muenchen').
    """
    return f"Das Wetter in {location} ist aktuell sonnig bei 22C."
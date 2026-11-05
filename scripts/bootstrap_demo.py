"""Create a disposable, ready-to-play demo campaign through the local API.

Run the backend first, then execute:
    python scripts/bootstrap_demo.py
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def build_demo_payloads(campaign_name: str, character_name: str, tone: str):
    """Return the API payloads used to create the demo campaign."""
    return {
        "campaign": {
            "name": campaign_name,
            "system": "D&D 5e 2014",
            "tone": tone,
            "summary": (
                "Campaña de demostración para probar el flujo de juego "
                "de Campaign Manager."
            ),
        },
        "session": {
            "number": 1,
            "title": "La posada del camino",
            "summary": (
                "Una primera sesión breve para probar exploración, "
                "interacción y tiradas."
            ),
            "start_location": "Posada del Camino",
            "end_location": "",
            "notes": "Escenario de demostración; puedes modificarlo libremente.",
        },
        "character": {
            "name": character_name,
            "class_name": "Fighter",
            "level": 1,
            "max_hp": 12,
            "current_hp": 12,
            "armor_class": 16,
            "strength": 16,
            "dexterity": 12,
            "constitution": 14,
            "intelligence": 10,
            "wisdom": 10,
            "charisma": 8,
            "proficiency_bonus": 2,
            "skill_proficiencies": ["athletics", "perception"],
            "saving_throw_proficiencies": ["strength", "constitution"],
            "armor_proficiencies": ["light", "medium", "heavy", "shields"],
        },
    }


def request_json(base_url: str, path: str, *, method: str = "GET", payload=None,
                 campaign_id: int | None = None):
    """Send one JSON request to the local Campaign Manager API."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if campaign_id is not None:
        headers["X-Campaign-Id"] = str(campaign_id)

    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"API request {method} {path} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            f"Cannot reach Campaign Manager at {base_url}: {exc}"
        ) from exc

    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"API returned invalid JSON for {path}") from exc


def bootstrap(base_url: str, campaign_name: str, character_name: str, tone: str):
    """Create a campaign, its first session, and an active demo character."""
    payloads = build_demo_payloads(campaign_name, character_name, tone)

    campaign = request_json(
        base_url, "/campaigns", method="POST", payload=payloads["campaign"]
    )
    campaign_id = campaign.get("id")
    if not isinstance(campaign_id, int):
        raise RuntimeError("Campaign creation response did not include an integer id")

    session = request_json(
        base_url,
        "/sessions",
        method="POST",
        payload=payloads["session"],
        campaign_id=campaign_id,
    )
    session_id = session.get("id")
    if not isinstance(session_id, int):
        raise RuntimeError("Session creation response did not include an integer id")

    request_json(
        base_url,
        "/campaign/session",
        method="PATCH",
        payload={"session_id": session_id},
        campaign_id=campaign_id,
    )
    character_result = request_json(
        base_url,
        "/campaign/bootstrap",
        method="POST",
        payload=payloads["character"],
        campaign_id=campaign_id,
    )
    character_id = character_result.get("active_character_id")
    if not isinstance(character_id, int):
        raise RuntimeError("Character bootstrap response did not include an active character id")

    return {
        "campaign_id": campaign_id,
        "session_id": session_id,
        "character_id": character_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a demo D&D campaign for testing Campaign Manager."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--campaign-name", default="Campaign Manager — Demo")
    parser.add_argument("--character-name", default="Arin")
    parser.add_argument("--tone", default="Aventura de fantasía clásica")
    args = parser.parse_args()

    try:
        result = bootstrap(
            args.base_url,
            args.campaign_name,
            args.character_name,
            args.tone,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Demo campaign created successfully.")
    print(f"Campaign ID: {result['campaign_id']}")
    print(f"Session ID:  {result['session_id']}")
    print(f"Character ID: {result['character_id']}")
    print()
    print("Configure the SillyTavern extension with this Campaign ID.")
    print("Use the local backend URL shown above and start a new chat.")
    print("This script creates a new campaign each time it is run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

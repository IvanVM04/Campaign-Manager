"""Create a disposable, ready-to-play demo campaign through the local API.

Run the backend first, then execute:
    python scripts/bootstrap_demo.py
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


DEMO_CAMPAIGN_SUMMARY = """Aventura inicial: Las campanas de Puenteviejo.

PREMISA
El personaje llega a la Posada del Camino, en el pequeño pueblo de
Puenteviejo, durante una noche de lluvia. Desde hace tres noches se oye
una campana bajo el viejo puente, aunque la campana de la capilla lleva
años desaparecida. Esta tarde no ha regresado Nilo, el correo local.

PERSONAJES
- Mara: posadera práctica y hospitalaria. Vio a Nilo salir hacia el puente
  con una bolsa de cuero. Está preocupada, pero no quiere alarmar al pueblo.
- Bram: carretero nervioso que afirma haber visto una luz azul junto al río.
  No vio quién la llevaba.
- Nilo: correo desaparecido. Es curioso, algo imprudente y conoce un acceso
  de mantenimiento bajo el puente.

VERDAD PARA EL DIRECTOR DE JUEGO (NO REVELAR SIN DESCUBRIRLA)
Nilo encontró la entrada a una cámara de mantenimiento bajo el puente.
La campana suena cuando el agua mueve un mecanismo antiguo. Nilo quedó
atrapado al ceder una escalera podrida; está vivo y tiene la bolsa consigo.
La luz azul procede de un hongo luminiscente. No hay un enemigo obligatorio:
el problema puede resolverse investigando, hablando, improvisando o usando
la fuerza para retirar los restos que bloquean la salida.

ESTRUCTURA ABIERTA
- En la posada se puede hablar con Mara y Bram, examinar la bolsa de viaje
  abandonada de Nilo o preguntar a otros viajeros.
- En el puente se pueden seguir huellas, examinar la piedra húmeda y localizar
  una corriente de aire o el sonido de la campana.
- Bajo el puente hay un acceso estrecho, una escalera rota y obstáculos que
  requieren una solución razonable. Premia enfoques distintos; no fuerces
  una única habilidad ni una única secuencia.
- Al encontrar a Nilo, permite decidir cómo ayudarle y qué hacer con la bolsa.
  La vuelta a la posada cierra la primera aventura y deja consecuencias para
  futuras sesiones.

DIRECCIÓN
Presenta solo lo que el personaje puede percibir. No reveles la verdad oculta
ni resuelvas decisiones del jugador por él. Pide aclaraciones si una acción
es ambigua. Usa pruebas solo cuando haya incertidumbre significativa y
consecuencias relevantes; las acciones rutinarias no requieren tirada.
No fuerces combate: esta aventura sirve para probar conversación,
exploración, investigación, pruebas y consecuencias persistentes.
"""


DEMO_SESSION_SUMMARY = """Objetivo de esta sesión: averiguar qué ocurrió con Nilo, el correo,
y regresar con él o descubrir su destino.

Comienza con el personaje entrando en la Posada del Camino mientras la lluvia
golpea los postigos. Mara, la posadera, comenta que Nilo no ha vuelto. El
jugador decide libremente qué investigar y en qué orden. Mantén abiertas varias
soluciones y deja que las acciones tengan consecuencias. La sesión puede
terminar cuando el personaje vuelva a la posada con Nilo o con información
fiable sobre su destino."""


DEMO_SESSION_NOTES = """Escenario de demostración para una primera partida.
PNJ conocidos: Mara (posadera), Bram (carretero), Nilo (correo desaparecido).
Pistas iniciales: lluvia reciente, huellas embarradas hacia el puente, bolsa
de viaje abandonada en la posada, campana audible bajo el puente.
No reveles los secretos de la aventura hasta que el personaje los descubra.
No presupongas combate ni una solución única. Registra PNJ, lugares, pistas,
relaciones y eventos importantes como estado persistente cuando corresponda."""


def build_demo_payloads(campaign_name: str, character_name: str, tone: str):
    """Return the API payloads used to create the demo campaign."""
    return {
        "campaign": {
            "name": campaign_name,
            "system": "D&D 5e 2014",
            "tone": tone,
            "summary": DEMO_CAMPAIGN_SUMMARY,
        },
        "session": {
            "number": 1,
            "title": "Las campanas de Puenteviejo",
            "summary": DEMO_SESSION_SUMMARY,
            "start_location": "Posada del Camino, Puenteviejo",
            "end_location": "",
            "notes": DEMO_SESSION_NOTES,
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

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"API request {method} {path} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
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
        raise TypeError("Campaign creation response did not include an integer id")

    session = request_json(
        base_url,
        "/sessions",
        method="POST",
        payload=payloads["session"],
        campaign_id=campaign_id,
    )
    session_id = session.get("id")
    if not isinstance(session_id, int):
        raise TypeError("Session creation response did not include an integer id")

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
        raise TypeError("Character bootstrap response did not include an active character id")

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
    except (RuntimeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("Demo campaign created successfully.")
    print(f"Campaign ID: {result['campaign_id']}")
    print(f"Session ID:  {result['session_id']}")
    print(f"Character ID: {result['character_id']}")
    print()
    print("Configure the SillyTavern extension with this Campaign ID.")
    print("Your first adventure is 'Las campanas de Puenteviejo'.")
    print("This script creates a new campaign each time it is run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

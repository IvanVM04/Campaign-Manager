from models.turn_record import TurnRecord
from services.context.context_ranker import ContextRanker
from services.context.context_renderer import ContextRenderer


def build_renderer(max_context_chars=6000, max_recent_turns_chars=2000):
    return ContextRenderer(
        ranker=ContextRanker(),
        max_context_chars=max_context_chars,
        max_recent_turns_chars=max_recent_turns_chars,
    )


def test_renderer_builds_ranked_candidates_for_structured_categories():
    renderer = build_renderer()

    candidates = renderer._build_context_candidates(
        {
            "entities": [
                {
                    "name": "Fungoso",
                    "entity_type": "character",
                    "description": "Aventurero",
                }
            ],
            "relations": [
                {
                    "relation_type": "ally",
                    "subject_id": 1,
                    "target_id": 2,
                }
            ],
        },
        "fungoso",
    )

    assert [candidate["category"] for candidate in candidates] == [
        "entities",
        "relations",
    ]
    assert candidates[0]["text"] == "- Fungoso (character): Aventurero"
    assert candidates[0]["score"] > candidates[1]["score"]


def test_renderer_keeps_structured_and_recent_turn_budgets_independent():
    renderer = build_renderer(
        max_context_chars=80,
        max_recent_turns_chars=100,
    )
    result = {
        "query": "posadero",
        "entities": [
            {
                "name": "Posadero",
                "entity_type": "npc",
                "description": "Un hombre que trabaja en la taberna.",
            }
        ],
        "relations": [],
        "events": [],
        "items": [],
        "item_instances": [],
        "resources": [],
        "resource_balances": [],
        "recent_turns": [
            TurnRecord(
                id=1,
                session_id=1,
                player_input="Pregunto por el posadero.",
                narrative="El posadero guarda silencio.",
            )
        ],
    }

    context = renderer._build_text_context(result)

    assert "[ENTIDADES]" in context
    assert "HISTORIAL RECIENTE" in context
    assert "Pregunto por el posadero." in context


def test_renderer_strips_internal_relevance_fields_without_mutating_other_data():
    result = {
        "entities": [
            {
                "id": 1,
                "name": "Fungoso",
                "_relevance": 1.0,
                "_depth": 0,
            }
        ],
        "events": [{"id": "event-1"}],
    }

    ContextRenderer._strip_internal_context_fields(result)

    assert result["entities"] == [
        {"id": 1, "name": "Fungoso"}
    ]
    assert result["events"] == [{"id": "event-1"}]

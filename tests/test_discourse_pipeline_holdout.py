"""Deterministic integrity and contract tests for the PR #227 discourse holdout."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from pathlib import Path

from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.player_intent_analysis import PlayerIntentAnalysis
from models.resolved_conversation_reference import (
    ResolvedConversationGroupReference,
    ResolvedConversationReference,
)
from models.turn_context import TurnContext
from models.turn_record import TurnRecord
from models.world_state import WorldState
from services.context import ContextBuilder
from services.context.conversation_reference_resolver import (
    ConversationReferenceResolver,
)
from services.discourse_context import DiscourseContextBuilder
from services.providers import FakeLLMProvider
from services.turns import IntentInterpreter, MechanicsAdjudicator

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "discourse_pipeline_corpus_holdout_v1.json"
EXISTING_HELD_OUT = (
    "language_understanding_corpus_holdout_v1.json",
    "semantic_frame_corpus_holdout_v1.json",
    "conversation_understanding_corpus_holdout_v1.json",
)
EXPECTED_FAMILIES = {
    "topic_boundary",
    "explicit_callback",
    "ellipsis_pending_action",
    "long_distance_reference",
    "local_grammatical_agreement",
    "npc_attribution_quoted_speech",
    "multi_turn_correction",
}


def _read_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _turns(scenario: dict) -> list[TurnRecord]:
    return [
        TurnRecord(
            id=item["id"],
            player_input=item.get("player_input", ""),
            narrative=item.get("narrative", ""),
        )
        for item in scenario["recent_turns"]
    ]


def _world(entities: list[dict]) -> WorldState:
    return WorldState(
        entities={
            item["id"]: Entity(
                id=item["id"],
                name=item["name"],
                entity_type=item.get("entity_type", "npc"),
                description=item.get("description", ""),
                active=item.get("active", True),
                aliases=item.get("aliases", []),
            )
            for item in entities
        }
    )


def _analysis(utterance: str, mention: str) -> PlayerIntentAnalysis:
    return PlayerIntentAnalysis.from_payload(
        {
            "schema_version": 1,
            "category": "action",
            "steps": [
                {
                    "index": 0,
                    "source_excerpt": utterance,
                    "actor": "player",
                    "action": "interactuar con el objetivo mencionado",
                    "modality": "attempted",
                    "polarity": "positive",
                    "reported_outcome": "not_claimed",
                    "target_mentions": [mention],
                    "attributed_to": None,
                }
            ],
            "active_step_index": 0,
            "requires_clarification": False,
            "clarification_question": None,
        },
        source_text=utterance,
    )


def test_discourse_pipeline_holdout_has_twenty_eight_balanced_cases():
    corpus = _read_fixture()
    scenarios = corpus["scenarios"]
    family_counts = Counter(item["family"] for item in scenarios)

    assert corpus["schema_version"] == 1
    assert corpus["split"] == "held_out"
    assert len(scenarios) == 28
    assert set(family_counts) == EXPECTED_FAMILIES
    assert set(family_counts.values()) == {4}
    assert len({item["id"] for item in scenarios}) == len(scenarios)
    assert all(isinstance(item["critical"], bool) for item in scenarios)


def test_discourse_pipeline_holdout_does_not_duplicate_existing_held_out_inputs_or_ids():
    corpus = _read_fixture()
    seen_inputs: dict[str, str] = {}
    seen_ids: dict[str, str] = {}

    for filename in EXISTING_HELD_OUT:
        existing = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        for item in existing["scenarios"]:
            scenario_id = item["id"]
            assert scenario_id not in seen_ids, (
                f"{filename}:{scenario_id} duplicates {seen_ids[scenario_id]}"
                if scenario_id in seen_ids
                else ""
            )
            seen_ids[scenario_id] = filename
            utterance = item.get("input") or item.get("utterance")
            if not isinstance(utterance, str) or not utterance.strip():
                continue
            key = " ".join(utterance.casefold().split())
            seen_inputs[key] = f"{filename}:{scenario_id}"

    for item in corpus["scenarios"]:
        scenario_id = item["id"]
        assert scenario_id not in seen_ids, (
            f"{scenario_id} duplicates held-out ID {seen_ids.get(scenario_id)}"
        )
        seen_ids[scenario_id] = "discourse_pipeline_corpus_holdout_v1.json"
        key = " ".join(item["input"].casefold().split())
        assert key not in seen_inputs, (
            f"{scenario_id} duplicates held-out input {seen_inputs.get(key)}"
        )
        seen_inputs[key] = scenario_id


def test_discourse_pipeline_topic_scope_and_ellipsis_cues_match_fixture():
    builder = DiscourseContextBuilder()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        expected = scenario["expected"]
        recent_turns = _turns(scenario)
        actual_scope = [
            item.id
            for item in builder.scope_history(recent_turns, scenario["input"])
        ]
        if actual_scope != expected["scoped_turn_ids"]:
            failures.append(
                f"{scenario['id']}: scope expected={expected['scoped_turn_ids']} "
                f"observed={actual_scope}"
            )
        if "current_topic_shift" in expected:
            actual = builder.has_topic_shift(scenario["input"])
            if actual is not expected["current_topic_shift"]:
                failures.append(
                    f"{scenario['id']}: topic_shift expected="
                    f"{expected['current_topic_shift']} observed={actual}"
                )
        if "callback" in expected:
            actual = builder.reactivates_prior_topic(scenario["input"])
            if actual is not expected["callback"]:
                failures.append(
                    f"{scenario['id']}: callback expected={expected['callback']} "
                    f"observed={actual}"
                )
        if "topic_segments" in expected:
            actual = list(builder.topic_segments(recent_turns))
            if actual != expected["topic_segments"]:
                failures.append(
                    f"{scenario['id']}: segments expected="
                    f"{expected['topic_segments']} observed={actual}"
                )
        if "ellipsis_hint" in expected:
            rendered = builder.render(scenario["input"], recent_turns)
            actual = "Posible elipsis" in rendered
            if actual is not expected["ellipsis_hint"]:
                failures.append(
                    f"{scenario['id']}: ellipsis_hint expected="
                    f"{expected['ellipsis_hint']} observed={actual}"
                )

    assert not failures, "\n".join(failures)


def test_discourse_pipeline_local_grammar_and_npc_attribution_match_fixture():
    builder = DiscourseContextBuilder()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        expected = scenario["expected"]
        grammar = expected.get("grammatical_features")
        if grammar is not None:
            actual = builder.grammatical_features(
                grammar["text"],
                grammar["alias"],
            )
            wanted = (grammar["gender"], grammar["number"])
            if actual != wanted:
                failures.append(
                    f"{scenario['id']}: grammar expected={wanted} observed={actual}"
                )

        if "npc_speaker_ids" in expected:
            visible = [
                Entity(
                    id=item["id"],
                    name=item["name"],
                    entity_type=item.get("entity_type", "npc"),
                    active=item.get("active", True),
                    aliases=item.get("aliases", []),
                )
                for item in scenario["npc_entities"]
            ]
            utterances = builder.extract_npc_utterances(
                scenario["npc_narrative"],
                700,
                visible,
            )
            actual = sorted({item.speaker_entity_id for item in utterances})
            wanted = sorted(expected["npc_speaker_ids"])
            if actual != wanted:
                failures.append(
                    f"{scenario['id']}: npc_speakers expected={wanted} observed={actual}"
                )

    assert not failures, "\n".join(failures)


def test_discourse_pipeline_deterministic_reference_cases_match_expected_abstention():
    resolver = ConversationReferenceResolver()
    failures = []

    for scenario in _read_fixture()["scenarios"]:
        reference = scenario["expected"].get("reference")
        if reference is None:
            continue
        world = _world(scenario["visible_entities"])
        result = resolver.resolve(
            world,
            _analysis(scenario["input"], reference["mention"]),
            recent_turns=_turns(scenario),
            current_input=scenario["input"],
        )
        resolved = result.references[0] if len(result.references) == 1 else None
        observed_id = (
            resolved.entity_id
            if isinstance(resolved, ResolvedConversationReference)
            else None
        )
        observed_group_ids = (
            resolved.entity_ids
            if isinstance(resolved, ResolvedConversationGroupReference)
            else ()
        )
        expected_group_ids = tuple(reference.get("entity_ids", ()))
        clarification = result.clarification_question is not None
        reference_matches = (
            observed_group_ids == expected_group_ids
            if expected_group_ids
            else observed_id == reference.get("entity_id")
        )
        if (
            not reference_matches
            or clarification is not reference["clarification"]
        ):
            failures.append(
                f"{scenario['id']}: expected_id={reference.get('entity_id')}, "
                f"expected_group_ids={expected_group_ids}, observed_id={observed_id}, "
                f"observed_group_ids={observed_group_ids}, "
                f"expected_clarification={reference['clarification']} "
                f"observed={clarification}, reason={result.abstention_reason}"
            )

    assert not failures, "\n".join(failures)


def test_discourse_pipeline_correction_fixtures_keep_player_evidence_separate():
    scenarios = [
        item
        for item in _read_fixture()["scenarios"]
        if item["family"] == "multi_turn_correction"
    ]
    assert len(scenarios) == 4

    for scenario in scenarios:
        rounds = scenario["correction_rounds"]
        assert rounds
        for correction_round in rounds:
            question = correction_round["dm_question"]
            answer = correction_round["player_answer"]
            expected = correction_round["expected"]
            assert question.strip()
            assert answer.strip()
            assert question != answer
            if expected["accepted"]:
                assert expected["replacement"]
                assert expected["replacement"].casefold() in answer.casefold()
            else:
                assert expected["replacement"] is None
                assert expected["rejection_reason"] == "ambiguous_or_ungrounded"



def test_discourse_pipeline_correction_rounds_match_the_pending_slot_values():
    from models.pending_intent_correction import (
        PendingCorrectionSlot,
        PendingIntentCorrection,
        build_pending_correction_candidates,
    )
    from models.semantic_frames import SemanticArgumentRole
    from tests.test_real_llm_discourse_pipeline import _pending_analysis

    scenarios = [
        item
        for item in _read_fixture()["scenarios"]
        if item["family"] == "multi_turn_correction"
    ]

    for scenario in scenarios:
        rounds = scenario["correction_rounds"]
        pending = _pending_analysis(
            rounds[0]["prior_player_input"],
            rounds[0]["expected"],
        )
        for round_index, correction_round in enumerate(rounds):
            expected = correction_round["expected"]
            if not expected["accepted"]:
                continue

            slot = PendingCorrectionSlot(expected["slot"])
            expected_role = expected.get("role")
            if slot is PendingCorrectionSlot.ACTION_ARGUMENT:
                assert expected_role is not None
                assert "endpoint" not in expected
                argument_role = SemanticArgumentRole(expected_role)
            elif slot in {
                PendingCorrectionSlot.RELATION_SUBJECT,
                PendingCorrectionSlot.RELATION_OBJECT,
            }:
                expected_endpoint = expected.get("endpoint")
                assert expected_endpoint == slot.value.removeprefix("relation_")
                assert "role" not in expected
                assert isinstance(expected.get("relation_claim_index"), int)
                argument_role = None
            else:
                argument_role = None
            candidates = build_pending_correction_candidates(pending)
            matching = [
                candidate
                for candidate in candidates
                if candidate.step_index == 0
                and candidate.slot is slot
                and candidate.argument_role is argument_role
                and candidate.current_value.casefold()
                == expected["previous_value"].casefold()
            ]
            assert len(matching) == 1, (
                f"{scenario['id']} round={round_index + 1}: "
                f"expected one catalogue candidate, observed {len(matching)}"
            )
            kind_hint = (
                "item_instance"
                if (
                    slot is PendingCorrectionSlot.ACTION_ARGUMENT
                    and expected_role == "theme"
                )
                else "character"
            )
            answer = correction_round["player_answer"]
            correction = PendingIntentCorrection.from_intent_payload(
                {
                    "slot_id": matching[0].slot_id,
                    "previous_value": expected["previous_value"],
                    "replacement": {
                        "text": expected["replacement"],
                        "kind_hint": kind_hint,
                    },
                    "source_excerpt": answer,
                },
                evidence_text=answer,
                pending_analysis=pending,
            )
            if slot is PendingCorrectionSlot.ACTION_ARGUMENT:
                assert correction.argument_role is argument_role
                assert correction.relation_claim_index is None
            elif slot in {
                PendingCorrectionSlot.RELATION_SUBJECT,
                PendingCorrectionSlot.RELATION_OBJECT,
            }:
                assert correction.argument_role is None
                assert (
                    correction.relation_claim_index
                    == expected["relation_claim_index"]
                )
            pending = correction.apply(
                pending,
                player_evidence_text=answer,
                resolution_pending=True,
                committed=False,
            )

        final_expected = scenario["expected"]["correction"]
        if final_expected["accepted"]:
            last_accepted = next(
                round_item["expected"]
                for round_item in reversed(rounds)
                if round_item["expected"]["accepted"]
            )
            assert final_expected["slot"] == last_accepted["slot"]
            assert (
                final_expected["previous_value"]
                == last_accepted["previous_value"]
            )
            assert final_expected["replacement"] == last_accepted["replacement"]


def test_intent_prompt_keeps_discourse_hints_separate_from_player_evidence():
    context = TurnContext(
        campaign=CampaignState(campaign_id=1, name="Discourse prompt test"),
        current_session=None,
        active_character=CharacterState(entity_id=77),
        world=WorldState(
            entities={
                77: Entity(
                    id=77,
                    name="Aldric",
                    entity_type="npc",
                    active=True,
                )
            }
        ),
    )
    interpreter = IntentInterpreter(
        FakeLLMProvider(response="{}"),
        context_builder=ContextBuilder(),
    )
    recent_turns = [
        TurnRecord(
            id=77,
            player_input="Hablo con Aldric.",
            narrative='Aldric pregunta: «¿Vienes conmigo?»',
        )
    ]

    prompt, section_sizes = interpreter._build_prompt(
        context,
        "Le digo que sí.",
        recent_turns=recent_turns,
        evidence_text="Le digo que sí.",
    )

    assert "=== ÍNDICE DISCURSIVO" in prompt
    assert "NPC Aldric (turno 77)" in prompt
    assert section_sizes["discourse"] > 0
    assert prompt.index("=== EVIDENCIA ESCRITA POR EL JUGADOR") > prompt.index(
        "=== ÍNDICE DISCURSIVO"
    )


def test_mechanics_prompt_uses_only_active_step_canonical_references():
    player_input = "Intento abrir la puerta de roble con cuidado."
    world = WorldState(
        entities={
            101: Entity(
                id=101,
                name="Puerta de roble",
                entity_type="door",
                description="Puerta pesada con un cerrojo antiguo.",
                active=True,
            ),
            102: Entity(
                id=102,
                name="Aldric",
                entity_type="npc",
                description="Tabernero que vende pociones en el mercado.",
                active=True,
            ),
        }
    )
    context = TurnContext(
        campaign=CampaignState(campaign_id=1, name="Mechanics prompt test"),
        current_session=None,
        active_character=CharacterState(entity_id=77),
        world=world,
    )
    analysis = _analysis(player_input, "la puerta de roble")
    active_reference = ResolvedConversationReference(
        mention="la puerta de roble",
        entity_id=101,
        entity_name="Puerta de roble",
        match_kind="canonical_name",
        confidence_score=100,
        resolution_signals=("canonical_name",),
    )
    unrelated_reference = ResolvedConversationReference(
        mention="Aldric",
        entity_id=102,
        entity_name="Aldric",
        match_kind="canonical_name",
        confidence_score=100,
        resolution_signals=("canonical_name",),
    )
    provider = FakeLLMProvider(response='{"decision": "none"}')
    adjudicator = MechanicsAdjudicator(
        provider,
        context_builder=ContextBuilder(),
    )

    decision = adjudicator.adjudicate_analysis(
        context,
        analysis,
        resolved_references=(active_reference, unrelated_reference),
    )

    assert decision.decision.value == "none"
    prompt = provider.prompts[0]
    references_section = prompt.split(
        "=== REFERENCIAS CANÓNICAS RESUELTAS POR EL BACKEND "
        "(EVIDENCIA, NO PERMISOS) ===",
        1,
    )[1].split("=== HECHOS RELEVANTES Y VISIBLES ===", 1)[0]
    assert "Puerta de roble" in references_section
    assert "Aldric" not in references_section

def test_discourse_holdout_indirect_question_to_a_person_is_dialogue():
    scenario = next(
        item
        for item in _read_fixture()["scenarios"]
        if item["id"] == "dp-distance-equal-focus-16"
    )

    assert scenario["input"] == "Le pregunto si conoce la ruta."
    assert scenario["expected"]["reference"]["mention"] == "le"
    assert scenario["expected"]["reference"]["clarification"] is True
    assert scenario["expected"]["intent"]["category"] == "dialogue"


def test_discourse_holdout_expected_action_mentions_are_literal_player_evidence():
    def normalize(value: str) -> str:
        return unicodedata.normalize("NFKC", value).casefold()

    for scenario in _read_fixture()["scenarios"]:
        expected = scenario["expected"]
        frame = expected.get("intent", {}).get("action_frame")
        if frame is not None:
            for argument in frame.get("arguments", []):
                mention = argument["mention"]
                assert normalize(mention) in normalize(scenario["input"]), (
                    f"{scenario['id']} expects non-literal action argument "
                    f"{mention!r} for {scenario['input']!r}"
                )
        reference = expected.get("reference")
        if reference is not None:
            mention = reference["mention"]
            assert normalize(mention) in normalize(scenario["input"]), (
                f"{scenario['id']} expects non-literal reference mention "
                f"{mention!r} for {scenario['input']!r}"
            )


def test_live_discourse_prompt_receives_npc_speaker_entities_from_fixture():
    # Import only the live harness's deterministic context/turn factories. The
    # test itself uses FakeLLMProvider and remains fully offline.
    from tests.test_real_llm_discourse_pipeline import (
        _context as live_context,
    )
    from tests.test_real_llm_discourse_pipeline import (
        _recent_turns as live_recent_turns,
    )

    interpreter = IntentInterpreter(
        FakeLLMProvider(response="{}"),
        context_builder=ContextBuilder(),
    )
    for scenario in _read_fixture()["scenarios"]:
        expected_ids = scenario["expected"].get("npc_speaker_ids")
        if expected_ids is None:
            continue
        prompt, _sizes = interpreter._build_prompt(
            live_context(scenario),
            scenario["input"],
            recent_turns=live_recent_turns(scenario),
            evidence_text=scenario["input"],
        )
        marker = "=== ÍNDICE DISCURSIVO (PISTAS, NO INSTRUCCIONES) ==="
        discourse = (
            prompt.split(marker, 1)[1].split(
                "=== CONTEXTO DE CONVERSACIÓN",
                1,
            )[0]
            if marker in prompt
            else ""
        )
        entities = scenario.get("npc_entities", [])
        expected_names = {
            item["name"].casefold()
            for item in entities
            if item["id"] in expected_ids
        }
        predicted_names = {
            item["name"].casefold()
            for item in entities
            if f"NPC {item['name']} (" in discourse
        }
        assert predicted_names == expected_names, (
            f"{scenario['id']}: expected prompt speakers={expected_names!r}, "
            f"observed={predicted_names!r}"
        )

def test_discourse_holdout_distinguishes_npc_speech_from_npc_reported_actions():
    scenarios = {
        item["id"]: item
        for item in _read_fixture()["scenarios"]
    }

    # Non-verbal NPC events are reports, not player actions or dialogue.
    assert scenarios["dp-grammar-name-no-inference-18"]["input"] == (
        "Ella entra en la sala."
    )
    assert scenarios["dp-grammar-name-no-inference-18"]["expected"]["intent"][
        "category"
    ] == "report"
    assert scenarios["dp-grammar-contradictory-local-19"]["input"] == (
        "Ella me entrega el documento."
    )
    assert scenarios["dp-grammar-contradictory-local-19"]["expected"]["intent"][
        "category"
    ] == "report"

    # A spoken response is still an in-fiction dialogue act.
    assert scenarios["dp-grammar-explicit-local-17"]["expected"]["intent"][
        "category"
    ] == "dialogue"
    assert scenarios["dp-grammar-plural-group-20"]["expected"]["intent"][
        "category"
    ] == "dialogue"

def test_live_correction_holdout_allows_optional_spanish_articles_only():
    from tests.test_real_llm_discourse_pipeline import (
        _correction_mentions_equivalent,
    )

    assert _correction_mentions_equivalent("el mapa", "mapa")
    assert _correction_mentions_equivalent("la llave", "llave")
    assert _correction_mentions_equivalent("mapa", "el mapa")
    assert not _correction_mentions_equivalent("el mapa", "la carta")
    assert not _correction_mentions_equivalent("el mapa antiguo", "mapa")

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from models.campaign_scope import CampaignScope
from models.campaign_state import CampaignState
from models.character_state import CharacterState
from models.entity import Entity
from models.player_action_checkpoint import PlayerActionCheckpoint
from models.turn_context import TurnContext
from models.world_context_projection import (
    ContextProjectionDiagnostics,
    WorldContextProjection,
)
from models.world_state import WorldState
from services.context import ContextBuilder
from services.providers import FakeLLMProvider
from services.turns.durable_turn_execution_service import (
    DurableTurnExecutionService,
)
from services.turns.intent_interpreter import IntentInterpreter
from services.turns.player_action_selector import ActionSelectionStatus
from services.turns.turn_resolution_service import (
    TurnResolutionPlan,
    TurnResolutionService,
)
from services.turns.v3_action_planning_adapter import (
    V3ActionPlanningAdapter,
    V3ActionPlanningError,
)
from services.turns.v3_action_preview_service import (
    V3ActionPreviewError,
    V3ActionPreviewService,
)
from services.turns.v3_action_progress_codec import V3ActionProgressSnapshot


def _span(source: str) -> dict[str, object]:
    return {
        "start": 0,
        "end": len(source),
        "text": source,
        "source": "current_utterance",
    }


def _v3_response(
    source: str,
    *,
    actor: str = "Yo",
    speaker_role: str = "player",
) -> str:
    span = _span(source)
    payload = {
        "schema_version": 3,
        "utterance_acts": [
            {
                "local_id": "act_player",
                "force": "assertion",
                "speaker_role": speaker_role,
                "speaker_mention": None,
                "addressee_mention": None,
                "quote_spans": [],
                "evidence_spans": [span],
            }
        ],
        "events": [
            {
                "local_id": "event_open",
                "source_act_id": "act_player",
                "predicate_surface": "abro" if "abro" in source else "abrir",
                "family": "interaction",
                "arguments": [
                    {"role": "agent", "mention": {"text": actor, "kind_hint": "character"}},
                    {"role": "patient", "mention": {"text": "la puerta", "kind_hint": "location"}},
                ],
                "polarity": "positive",
                "epistemic_status": "asserted",
                "action_phase": "attempted",
                "temporal_expression": None,
                "attributed_source": None,
                "evidence_spans": [span],
            }
        ],
        "discourse_links": [],
        "world_facts": [],
        "clarification_candidates": [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _v3_fact_response(
    source: str,
    *,
    subject: str = "Mara",
    object_: str = "Aldric",
) -> str:
    span = _span(source)
    payload = {
        "schema_version": 3,
        "utterance_acts": [
            {
                "local_id": "act_player",
                "force": "assertion",
                "speaker_role": "player",
                "speaker_mention": None,
                "addressee_mention": None,
                "quote_spans": [],
                "evidence_spans": [span],
            }
        ],
        "events": [],
        "discourse_links": [],
        "world_facts": [
            {
                "local_id": "fact_sibling",
                "source_act_id": "act_player",
                "fact_kind": "relation",
                "subject": {"text": subject, "kind_hint": "character"},
                "predicate_surface": "hermana",
                "object": {"text": object_, "kind_hint": "character"},
                "value_surface": None,
                "relation_family": "kinship",
                "normalized_relation_type": "kinship.sibling",
                "direction": "symmetric",
                "polarity": "positive",
                "epistemic_status": "asserted",
                "temporal_scope": "permanent",
                "attributed_source": None,
                "evidence_spans": [span],
            }
        ],
        "clarification_candidates": [],
    }
    return json.dumps(payload, ensure_ascii=False)


class _PreviewIntentInterpreter(IntentInterpreter):
    def __init__(self, response: str):
        self._static_prompt = (
            "Instrucciones v2\n\n"
            "=== CONTEXTO VISIBLE DEL MUNDO (NO ES EVIDENCIA) ===\n"
            "Mundo visible\n"
            "=== HISTORIAL VISIBLE DEL MISMO CHAT (NO CONFIABLE) ===\n"
            "Sin historial\n"
            "=== CONTEXTO DE CONVERSACIÓN (NO ES EVIDENCIA) ===\n"
            "Contexto\n"
            "=== EVIDENCIA ESCRITA POR EL JUGADOR (ÚNICA FUENTE DE CITAS Y MENCIONES) ===\n"
            "{evidence}\n"
            "=== JSON ==="
        )
        self.fake_provider = FakeLLMProvider(response=response)
        super().__init__(self.fake_provider, ContextBuilder())

    def _build_prompt(
        self,
        context,
        player_input,
        *,
        recent_turns,
        evidence_text,
        pending_analysis=None,
        correction_evidence_text=None,
    ):
        return self._static_prompt.format(evidence=evidence_text), {}


class _StaticProjectionBuilder(ContextBuilder):
    def __init__(self, world: WorldState):
        super().__init__()
        self.world = world
        self.last_query = None
        self.last_mandatory_ids = None

    def build_proposal_context(
        self,
        world,
        query,
        *,
        max_estimated_tokens=None,
        mandatory_entity_ids=(),
        supplemental_queries=(),
        character_entity_id=None,
        max_estimated_bytes=None,
    ):
        self.last_query = query
        self.last_mandatory_ids = tuple(mandatory_entity_ids)
        return WorldContextProjection(
            self.world,
            ContextProjectionDiagnostics(
                estimated_tokens=10,
                budget_tokens=4096,
                available_counts=(),
                candidate_counts=(),
                selected_counts=(),
            ),
        )


def _context(world: WorldState) -> TurnContext:
    return TurnContext(
        campaign=CampaignState(
            campaign_id=1,
            name="Prueba",
            system="D&D 5e 2014",
            tone="serio",
            summary="",
        ),
        current_session=None,
        active_character=CharacterState(entity_id=7),
        world=world,
    )


def _preview_service(world: WorldState, response: str):
    interpreter = _PreviewIntentInterpreter(response)
    builder = _StaticProjectionBuilder(world)
    return V3ActionPreviewService(interpreter, builder), interpreter.fake_provider, builder


def test_v3_action_preview_builds_one_backend_resolved_candidate_without_execution():
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    service, provider, builder = _preview_service(world, _v3_response(source))

    result = service.preview(
        _context(world),
        source,
        resolution_id=41,
        context_revision=9,
    )

    assert result.selection.status is ActionSelectionStatus.READY
    assert result.selection.candidate is not None
    assert result.selection.candidate.action_type == "interaction"
    assert result.checkpoint.resolution_id == 41
    assert result.checkpoint.context_revision == 9
    assert result.event_count == 1
    assert len(result.checkpoint.nodes) == 1
    references = result.selection.candidate.resolved_references
    assert {item.referent_id for item in references} == {7, 8}
    assert builder.last_mandatory_ids == (7,)
    assert provider.call_count == 1
    assert "=== EVIDENCIA ESCRITA POR EL JUGADOR" in provider.last_prompt


def test_v3_action_preview_restores_persisted_interpretation_without_llm_call():
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    service, provider, _builder = _preview_service(world, _v3_response(source))
    original = service.preview(
        _context(world),
        source,
        resolution_id=45,
        context_revision=12,
    )
    call_count = provider.call_count

    restored = service.restore(
        original.checkpoint,
        _context(world),
        source,
    )

    assert provider.call_count == call_count
    assert restored.checkpoint == original.checkpoint
    assert restored.interpretation == original.interpretation
    assert restored.selection.status is ActionSelectionStatus.READY
    assert restored.selection.candidate == original.selection.candidate
    assert restored.visible_projection.world is world


def test_v3_restore_accepts_backend_resolved_target_from_a_prior_clarification():
    from dataclasses import replace

    from models.player_turn_interpretation_v3 import (
        GameplayActionEligibility,
        GameplayActionReason,
        GameplayProcessingState,
        GameplayResolvedReference,
        GameplayResolvedReferenceKind,
        GameplayUnlockCondition,
        GameplayWorkflow,
    )
    from models.semantic_frames import SemanticMention
    from services.turns.player_action_selector import resume_after_clarification

    source = "Yo intento abrir la puerta y la cosa"
    payload = json.loads(_v3_response(source))
    payload["events"][0]["arguments"][1]["mention"]["text"] = "la cosa"
    payload["events"][0]["arguments"].append(
        {
            "role": "theme",
            "mention": {"text": "la puerta", "kind_hint": "location"},
        }
    )
    response = json.dumps(payload, ensure_ascii=False)
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
            9: Entity(
                id=9,
                name="Caja antigua",
                entity_type="object",
                aliases=["la caja"],
            ),
        }
    )
    service, provider, _builder = _preview_service(world, response)
    original = service.preview(
        _context(world),
        source,
        resolution_id=46,
        context_revision=13,
    )

    node = original.checkpoint.nodes[0]
    assert node.state.value == "awaiting_input"
    candidate = node.candidate
    clarified_mention = SemanticMention("la caja")
    updated_candidate = replace(
        candidate,
        target_mentions=(
            SemanticMention("la puerta"),
            clarified_mention,
        ),
        resolved_references=(
            *candidate.resolved_references,
            GameplayResolvedReference(
                mention=clarified_mention,
                category=GameplayResolvedReferenceKind.ENTITY,
                referent_id=9,
                name="Caja antigua",
            ),
        ),
        eligibility=GameplayActionEligibility.ELIGIBLE,
        reason=GameplayActionReason.ELIGIBLE,
        workflow=GameplayWorkflow.MECHANICS,
        unlock_condition=GameplayUnlockCondition.NONE,
        processing_state=GameplayProcessingState.PENDING,
    )
    clarified = resume_after_clarification(
        original.checkpoint,
        "event_open",
        updated_candidate,
    ).checkpoint
    call_count = provider.call_count

    restored = service.restore(
        clarified,
        _context(world),
        source,
    )

    assert provider.call_count == call_count
    assert restored.checkpoint == clarified
    assert restored.selection.status is ActionSelectionStatus.READY
    assert restored.selection.candidate is not None
    assert restored.selection.candidate.target_mentions == (
        SemanticMention("la puerta"),
        clarified_mention,
    )
    assert {
        item.referent_id
        for item in restored.selection.candidate.resolved_references
    } == {7, 8, 9}


def _v3_restore_fixture():
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
            9: Entity(id=9, name="Mara", entity_type="character"),
        }
    )
    service, provider, _builder = _preview_service(world, _v3_response(source))
    context = _context(world)
    preview = service.preview(
        context,
        source,
        resolution_id=47,
        context_revision=14,
    )
    return source, world, service, provider, context, preview


def test_v3_restore_rejects_legacy_checkpoint_and_source_rebinding():
    from dataclasses import replace

    source, _world, service, _provider, context, preview = _v3_restore_fixture()
    legacy = replace(
        preview.checkpoint,
        schema_version=1,
        interpretation_json=None,
    )
    with pytest.raises(V3ActionPreviewError) as legacy_error:
        service.restore(legacy, context, source)
    assert legacy_error.value.code == "legacy_checkpoint_not_resumable"

    with pytest.raises(V3ActionPreviewError) as source_error:
        service.restore(preview.checkpoint, context, source + " ahora")
    assert source_error.value.code == "checkpoint_source_mismatch"


def test_v3_restore_rejects_interpretation_with_invalid_v3_contract():
    from dataclasses import replace

    source, _world, service, _provider, context, preview = _v3_restore_fixture()
    payload = '{"schema_version":99}'
    corrupted = replace(
        preview.checkpoint,
        interpretation_json=payload,
        interpretation_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )

    with pytest.raises(V3ActionPreviewError) as error:
        service.restore(corrupted, context, source)

    assert error.value.code == "stored_interpretation_invalid"


def test_v3_restore_rejects_checkpoint_when_active_character_is_missing():
    from dataclasses import replace

    source, _world, service, _provider, context, preview = _v3_restore_fixture()
    context_without_actor = replace(context, active_character=None)

    with pytest.raises(V3ActionPreviewError) as error:
        service.restore(preview.checkpoint, context_without_actor, source)

    assert error.value.code == "active_character_unavailable"


def test_v3_restore_rejects_visible_but_unbound_canonical_target_reference():
    from dataclasses import replace

    from models.player_turn_interpretation_v3 import (
        GameplayResolvedReference,
        GameplayResolvedReferenceKind,
    )
    from models.semantic_frames import SemanticMention

    source, _world, service, _provider, context, preview = _v3_restore_fixture()
    node = preview.checkpoint.nodes[0]
    unbound = GameplayResolvedReference(
        mention=SemanticMention("Mara"),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=9,
        name="Mara",
    )
    candidate = replace(
        node.candidate,
        resolved_references=(*node.candidate.resolved_references, unbound),
    )
    corrupted = replace(
        preview.checkpoint,
        nodes=(replace(node, candidate=candidate),),
    )

    with pytest.raises(V3ActionPreviewError) as error:
        service.restore(corrupted, context, source)

    assert error.value.code == "stored_references_invalid"


def test_v3_restore_rejects_reference_rebound_to_another_visible_entity():
    from dataclasses import replace

    from models.player_turn_interpretation_v3 import (
        GameplayResolvedReference,
        GameplayResolvedReferenceKind,
    )
    from models.semantic_frames import SemanticMention

    source, _world, service, _provider, context, preview = _v3_restore_fixture()
    node = preview.checkpoint.nodes[0]
    rebound_actor = GameplayResolvedReference(
        mention=SemanticMention("Yo"),
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=9,
        name="Mara",
    )
    candidate = replace(
        node.candidate,
        resolved_references=(*node.candidate.resolved_references, rebound_actor),
    )
    corrupted = replace(
        preview.checkpoint,
        nodes=(replace(node, candidate=candidate),),
    )

    with pytest.raises(V3ActionPreviewError) as error:
        service.restore(corrupted, context, source)

    assert error.value.code == "stored_references_invalid"


def test_v3_restore_reference_validator_rejects_action_identity_changes():
    from dataclasses import replace

    _source, world, service, _provider, _context_value, preview = _v3_restore_fixture()
    baseline = preview.checkpoint.nodes[0].candidate
    rebound = replace(baseline, action_type="movement")

    with pytest.raises(ValueError, match="action identity"):
        service._validate_restored_candidate_references(
            rebound,
            baseline,
            world,
            7,
        )


def test_v3_restore_reference_validator_rejects_dropped_original_references():
    from dataclasses import replace

    _source, world, service, _provider, _context_value, preview = _v3_restore_fixture()
    baseline = preview.checkpoint.nodes[0].candidate
    dropped = replace(
        baseline,
        resolved_references=tuple(
            item for item in baseline.resolved_references
            if item.mention.text != "Yo"
        ),
    )

    with pytest.raises(ValueError, match="discarded"):
        service._validate_restored_candidate_references(
            dropped,
            baseline,
            world,
            7,
        )


def test_v3_restore_reference_validator_rejects_non_entity_references():
    from dataclasses import replace

    from models.player_turn_interpretation_v3 import (
        GameplayResolvedReference,
        GameplayResolvedReferenceKind,
    )
    from models.semantic_frames import SemanticMention

    _source, world, service, _provider, _context_value, preview = _v3_restore_fixture()
    baseline = preview.checkpoint.nodes[0].candidate
    unsupported = GameplayResolvedReference(
        mention=SemanticMention("Mara"),
        category=GameplayResolvedReferenceKind.RESOURCE,
        referent_id=9,
        name="Mara",
    )
    candidate = replace(
        baseline,
        resolved_references=(*baseline.resolved_references, unsupported),
    )

    with pytest.raises(ValueError, match="unsupported category"):
        service._validate_restored_candidate_references(
            candidate,
            baseline,
            world,
            7,
        )


def test_v3_restore_reference_validator_rejects_stale_entity_name():
    from dataclasses import replace

    _source, world, service, _provider, _context_value, preview = _v3_restore_fixture()
    baseline = preview.checkpoint.nodes[0].candidate
    door = next(
        item for item in baseline.resolved_references
        if item.referent_id == 8
    )
    stale = replace(door, name="Puerta destruida")
    stale_candidate = replace(
        baseline,
        resolved_references=tuple(
            stale if item == door else item
            for item in baseline.resolved_references
        ),
    )
    # Use the candidate as the expected baseline here to isolate the final
    # visibility/name check from the earlier immutable-reference subset gate.

    with pytest.raises(ValueError, match="visible and active"):
        service._validate_restored_candidate_references(
            stale_candidate,
            stale_candidate,
            world,
            7,
        )


def test_v3_action_planning_uses_only_selected_event_excerpt_without_reinterpreting():
    from models.player_intent_analysis import IntentModality
    class RecordingResolver(TurnResolutionService):
        def __init__(self):
            self.calls = []

        def prepare_turn(
            self,
            turn_context: TurnContext,
            player_input: str,
            **kwargs: Any,
        ) -> TurnResolutionPlan:
            self.calls.append(
                {
                    "turn_context": turn_context,
                    "player_input": player_input,
                    **kwargs,
                }
            )
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
            )

    source = "Yo intento abrir la puerta y después examino la caja"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
            9: Entity(
                id=9,
                name="Caja antigua",
                entity_type="object",
                aliases=["la caja"],
            ),
        }
    )
    preview_service, provider, _builder = _preview_service(world, _v3_response(source))
    preview = preview_service.preview(
        _context(world),
        source,
        resolution_id=51,
        context_revision=15,
    )
    call_count = provider.call_count
    resolver = RecordingResolver()

    result = V3ActionPlanningAdapter().prepare_next_action(
        resolver,
        preview,
        _context(world),
        source,
    )

    assert len(resolver.calls) == 1
    call = resolver.calls[0]
    assert call["player_input"] == "Yo intento abrir la puerta"
    assert "examino la caja" not in call["player_input"]
    assert call["intent_analysis_override"] == result.intent_analysis
    assert result.intent_analysis.active_step is not None
    assert result.intent_analysis.active_step.modality is IntentModality.ATTEMPTED
    assert result.intent_analysis.active_step.action_frame is not None
    assert result.intent_analysis.active_step.action_frame.predicate == "abrir"
    assert {item.entity_id for item in call["resolved_references_override"]} == {7, 8}
    assert provider.call_count == call_count
    assert result.plan.player_input == source
    assert result.plan.intent_evidence_text == source


def test_v3_action_planning_builds_an_idempotent_checkpoint_cas_progress_update():
    class RecordingResolver(TurnResolutionService):
        def __init__(self) -> None:
            self.calls = []

        def prepare_turn(
            self,
            turn_context: TurnContext,
            player_input: str,
            **kwargs: Any,
        ) -> TurnResolutionPlan:
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                intent_analysis=kwargs["intent_analysis_override"],
                intent_evidence_text=kwargs["intent_evidence_text"],
            )

    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    preview_service, _provider, _builder = _preview_service(
        world,
        _v3_response(source),
    )
    preview = preview_service.preview(
        _context(world),
        source,
        resolution_id=54,
        context_revision=18,
    )
    planned = V3ActionPlanningAdapter().prepare_next_action(
        RecordingResolver(),
        preview,
        _context(world),
        source,
    )

    execution_key = preview.checkpoint.nodes[0].execution_key
    updates = planned.progress_updates(execution_key=execution_key)
    snapshot = V3ActionProgressSnapshot.from_json(updates["proposal_json"])
    assert snapshot.resolution_id == 54
    assert snapshot.context_revision == 18
    assert snapshot.source_sha256 == preview.checkpoint.source_sha256
    assert len(snapshot.entries) == 1
    staged = snapshot.entries[0]
    assert staged.event_id == "event_open"
    assert staged.action_id == planned.candidate.local_id
    assert staged.source_order == 0
    assert staged.execution_key == execution_key
    assert staged.evidence_excerpt == "Yo intento abrir la puerta"
    assert json.loads(staged.operations_json) == {"operations": []}
    assert json.loads(staged.intent_json)["source_text"] == source

    from services.turns.turn_resolution_codec import TurnResolutionCodec

    restored_plan = TurnResolutionCodec.plan_from_v3_action_progress_entry(
        staged,
        original_input=source,
        operation_parser=SimpleNamespace(parse=lambda _payload: []),
    )
    assert restored_plan.player_input == source
    assert restored_plan.intent_analysis == planned.intent_analysis
    assert restored_plan.intent_evidence_text == source
    assert restored_plan.ordered_operations == ()

    replayed = planned.progress_updates(
        execution_key=execution_key,
        previous_progress_json=updates["proposal_json"],
    )
    assert replayed == updates

    with pytest.raises(V3ActionPlanningError) as rebound:
        planned.progress_updates(
            execution_key="f" * 64,
            previous_progress_json=updates["proposal_json"],
        )
    assert rebound.value.code == "staged_progress_rejected"

    from services.turns.player_action_selector import mark_action_started

    in_progress, stable_key, resumed = mark_action_started(
        preview.checkpoint,
        "event_open",
    )
    assert stable_key == execution_key
    assert resumed is False
    recovered = V3ActionPlanningAdapter().restore_staged_action(
        replace(preview, checkpoint=in_progress),
        _context(world),
        "  " + source + "  ",
        progress_json=updates["proposal_json"],
        event_id="event_open",
        execution_key=stable_key,
        operation_parser=SimpleNamespace(parse=lambda _payload: []),
    )
    assert recovered.plan == planned.plan
    assert recovered.intent_analysis == planned.intent_analysis
    assert recovered.evidence_excerpt == planned.evidence_excerpt

    with pytest.raises(V3ActionPlanningError) as wrong_source:
        V3ActionPlanningAdapter().restore_staged_action(
            replace(preview, checkpoint=in_progress),
            _context(world),
            source + " ahora",
            progress_json=updates["proposal_json"],
            event_id="event_open",
            execution_key=stable_key,
            operation_parser=SimpleNamespace(parse=lambda _payload: []),
        )
    assert wrong_source.value.code == "checkpoint_source_mismatch"


def test_v3_action_planning_passes_resolved_callback_mentions_separately_from_current_evidence():
    from dataclasses import replace

    from models.player_turn_interpretation_v3 import (
        GameplayResolvedReference,
        GameplayResolvedReferenceKind,
    )
    from models.semantic_frames import SemanticMention

    class RecordingResolver(TurnResolutionService):
        def __init__(self):
            self.calls = []

        def prepare_turn(
            self,
            turn_context: TurnContext,
            player_input: str,
            **kwargs: Any,
        ) -> TurnResolutionPlan:
            self.calls.append({"player_input": player_input, **kwargs})
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
            )

    source = "Yo intento abrir la puerta y luego me acerco a ella"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
            9: Entity(id=9, name="Caja antigua", entity_type="object"),
        }
    )
    preview_service, _provider, _builder = _preview_service(world, _v3_response(source))
    preview = preview_service.preview(
        _context(world),
        source,
        resolution_id=52,
        context_revision=16,
    )
    node = preview.checkpoint.nodes[0]
    callback_mention = SemanticMention("la caja")
    callback_reference = GameplayResolvedReference(
        mention=callback_mention,
        category=GameplayResolvedReferenceKind.ENTITY,
        referent_id=9,
        name="Caja antigua",
    )
    candidate = replace(
        node.candidate,
        target_mentions=(*node.candidate.target_mentions, callback_mention),
        resolved_references=(
            *node.candidate.resolved_references,
            callback_reference,
        ),
    )
    checkpoint = replace(
        preview.checkpoint,
        nodes=(replace(node, candidate=candidate),),
    )
    preview = replace(preview, checkpoint=checkpoint)
    resolver = RecordingResolver()

    result = V3ActionPlanningAdapter().prepare_next_action(
        resolver,
        preview,
        _context(world),
        source,
    )

    call = resolver.calls[0]
    assert result.additional_reference_mentions == ("la caja",)
    assert call["additional_resolved_reference_mentions"] == ("la caja",)
    assert {
        item.entity_id for item in call["resolved_references_override"]
    } == {7, 8, 9}
    assert "la caja" not in result.evidence_excerpt


def test_v3_action_planning_fails_closed_when_callback_reference_is_not_resolved():
    from dataclasses import replace

    from models.semantic_frames import SemanticMention

    class RecordingResolver(TurnResolutionService):
        def __init__(self) -> None:
            pass

        def prepare_turn(
            self,
            turn_context: TurnContext,
            player_input: str,
            **kwargs: Any,
        ) -> TurnResolutionPlan:
            return TurnResolutionPlan(
                player_input=player_input,
                narrative="",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
            )

    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(
                id=8,
                name="Puerta de hierro",
                entity_type="location",
                aliases=["la puerta"],
            ),
        }
    )
    preview_service, _provider, _builder = _preview_service(world, _v3_response(source))
    preview = preview_service.preview(
        _context(world),
        source,
        resolution_id=53,
        context_revision=17,
    )
    node = preview.checkpoint.nodes[0]
    candidate = replace(
        node.candidate,
        target_mentions=(*node.candidate.target_mentions, SemanticMention("la ventana")),
    )
    preview = replace(
        preview,
        checkpoint=replace(
            preview.checkpoint,
            nodes=(replace(node, candidate=candidate),),
        ),
    )

    with pytest.raises(V3ActionPlanningError) as error:
        V3ActionPlanningAdapter().prepare_next_action(
            RecordingResolver(),
            preview,
            _context(world),
            source,
        )

    assert error.value.code == "callback_reference_not_resolved"


def test_v3_action_preview_abstains_on_ambiguous_visible_target():
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(id=8, name="Puerta norte", entity_type="location", aliases=["la puerta"]),
            9: Entity(id=9, name="Puerta sur", entity_type="location", aliases=["la puerta"]),
        }
    )
    service, _provider, _builder = _preview_service(world, _v3_response(source))

    result = service.preview(
        _context(world),
        source,
        resolution_id=42,
        context_revision=10,
    )

    assert result.selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION
    assert result.selection.candidate is not None
    assert result.selection.candidate.eligibility.value == "requires_clarification"


def test_v3_action_preview_rejects_missing_controlled_character():
    source = "Yo intento abrir la puerta"
    world = WorldState(
        entities={8: Entity(id=8, name="Puerta", entity_type="location")}
    )
    service, provider, _builder = _preview_service(world, _v3_response(source))

    with pytest.raises(V3ActionPreviewError) as error:
        service.preview(
            _context(world),
            source,
            resolution_id=43,
            context_revision=11,
        )

    assert error.value.code == "active_character_not_visible"
    assert provider.call_count == 1


def test_v3_action_preview_lease_timeout_is_extended_only_when_enabled():
    disabled = object.__new__(DurableTurnExecutionService)
    disabled.v3_action_preview_service = None
    assert disabled._planning_lease_timeout_seconds() == 180

    enabled = object.__new__(DurableTurnExecutionService)
    enabled.v3_action_preview_service = object()
    enabled.resolver = SimpleNamespace(
        intent_interpreter=SimpleNamespace(provider=SimpleNamespace(timeout=30)),
        mechanics_adjudicator=SimpleNamespace(provider=SimpleNamespace(timeout=40)),
        extractor=SimpleNamespace(provider=SimpleNamespace(timeout=50)),
    )
    assert enabled._planning_lease_timeout_seconds() == 600


def test_shadow_checkpoint_save_uses_current_lease_and_cas():
    source = "Yo intento abrir la puerta"
    checkpoint = PlayerActionCheckpoint(
        resolution_id=51,
        context_revision=12,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        interpretation_sha256=hashlib.sha256(b"{}").hexdigest(),
        nodes=(),
    )
    preview = SimpleNamespace(checkpoint=checkpoint)
    saved = SimpleNamespace(action_checkpoint_json=checkpoint.to_json())
    captured = {}

    class Repository:
        def save_action_checkpoint(self, resolution_id, checkpoint_json, **kwargs):
            captured.update({
                "resolution_id": resolution_id,
                "checkpoint_json": checkpoint_json,
                **kwargs,
            })
            return saved

    service = object.__new__(DurableTurnExecutionService)
    service.resolution_repository = Repository()
    service.scope = CampaignScope(1)
    record = SimpleNamespace(
        id=51,
        context_revision=None,
        action_checkpoint_json=None,
    )

    result = service._save_v3_action_checkpoint(
        record,
        preview,
        revision=12,
        lease_token="lease-token",
        conn="connection",
    )

    assert result is saved
    assert captured["resolution_id"] == 51
    assert captured["expected_state"] == "planning"
    assert captured["expected_lease_token"] == "lease-token"
    assert captured["expected_context_revision"] is None
    assert captured["expected_checkpoint_json"] is None
    assert captured["checkpoint_json"] == checkpoint.to_json()
    assert captured["conn"] == "connection"


def test_v3_preview_never_regenerates_an_existing_checkpoint():
    class Preview:
        calls = 0

        def preview(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("existing checkpoint must be reused")

    service = object.__new__(DurableTurnExecutionService)
    preview = Preview()
    service.v3_action_preview_service = preview
    record = SimpleNamespace(action_checkpoint_json='{"existing":true}')

    result = service._build_v3_action_preview(
        record,
        context=object(),
        player_input="texto",
        recent=[],
        revision=12,
        lease_token="lease-token",
    )

    assert result is None
    assert preview.calls == 0



def test_v3_action_preview_does_not_map_plural_first_person_to_single_active_character():
    source = "Nosotros intentamos abrir la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(id=8, name="Puerta", entity_type="location", aliases=["la puerta"]),
        }
    )
    service, _provider, _builder = _preview_service(
        world,
        _v3_response(source, actor="Nosotros"),
    )

    result = service.preview(
        _context(world),
        source,
        resolution_id=44,
        context_revision=12,
    )

    # A player speaking in first-person plural does not identify a single actor.
    # Keep the action pending clarification instead of binding the active PC.
    assert result.selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION
    assert result.selection.candidate is not None
    assert result.selection.candidate.reason.value == "unresolved_reference"
    assert result.selection.candidate.resolved_references == ()


def test_v3_action_preview_does_not_bind_npc_first_person_to_player_character():
    source = "Yo abro la puerta"
    world = WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(id=8, name="Puerta", entity_type="location", aliases=["la puerta"]),
        }
    )
    service, _provider, _builder = _preview_service(
        world,
        _v3_response(source, actor="Yo", speaker_role="npc"),
    )

    result = service.preview(
        _context(world),
        source,
        resolution_id=45,
        context_revision=13,
    )

    # An NPC-attributed event is outside the player's action scope.
    # It must be skipped, never rebound or clarified as the player's action.
    assert result.selection.status is ActionSelectionStatus.EXHAUSTED
    assert result.selection.candidate is None
    assert len(result.checkpoint.nodes) == 1
    npc_action = result.checkpoint.nodes[0]
    assert npc_action.state.value == "skipped"
    assert npc_action.candidate.reason.value == "outside_player_scope"
    assert npc_action.candidate.resolved_references == ()





def _world_with_fact_endpoints():
    return WorldState(
        entities={
            7: Entity(id=7, name="Arin", entity_type="character"),
            8: Entity(id=8, name="Mara", entity_type="npc"),
            9: Entity(id=9, name="Aldric", entity_type="npc"),
        }
    )


def test_v3_fact_preview_emits_validated_receipt_and_typed_operation_when_enabled():
    from operations.world_operations import CreateRelationOperation

    source = "Mara es hermana de Aldric."
    world = _world_with_fact_endpoints()
    interpreter = _PreviewIntentInterpreter(_v3_fact_response(source))
    builder = _StaticProjectionBuilder(world)
    service = V3ActionPreviewService(
        interpreter,
        builder,
        world_facts_enabled=True,
    )

    result = service.preview(
        _context(world),
        source,
        resolution_id=61,
        context_revision=21,
    )

    assert result.fact_candidate_count == 1
    assert result.fact_accepted_count == 1
    assert result.fact_already_present_count == 0
    assert result.fact_pending_count == 0
    assert result.fact_rejected_count == 0
    assert len(result.checkpoint.fact_validation_receipts) == 1
    receipt = result.checkpoint.fact_validation_receipts[0]
    assert receipt.fact_local_id == "fact_sibling"
    assert receipt.source_act_id == "act_player"
    assert receipt.state.value == "validated"
    assert len(result.world_fact_operations) == 1
    assert isinstance(result.world_fact_operations[0], CreateRelationOperation)
    assert (
        result.world_fact_operations[0].subject_id,
        result.world_fact_operations[0].target_id,
    ) == (8, 9)
    assert builder.last_mandatory_ids == (7,)


def test_v3_fact_preview_keeps_unresolved_endpoint_pending_without_operation():
    source = "Mara es hermana de Neria."
    world = _world_with_fact_endpoints()
    service = V3ActionPreviewService(
        _PreviewIntentInterpreter(
            _v3_fact_response(source, object_="Neria")
        ),
        _StaticProjectionBuilder(world),
        world_facts_enabled=True,
    )

    result = service.preview(
        _context(world),
        source,
        resolution_id=62,
        context_revision=22,
    )

    assert result.fact_candidate_count == 1
    assert result.fact_accepted_count == 0
    assert result.fact_pending_count == 1
    assert result.fact_rejected_count == 0
    assert result.world_fact_operations == ()
    assert len(result.checkpoint.fact_validation_receipts) == 1
    assert result.checkpoint.fact_validation_receipts[0].state.value == "pending"


def test_v3_fact_preview_is_disabled_by_default_even_with_fact_candidates():
    source = "Mara es hermana de Aldric."
    world = _world_with_fact_endpoints()
    service = V3ActionPreviewService(
        _PreviewIntentInterpreter(_v3_fact_response(source)),
        _StaticProjectionBuilder(world),
    )

    result = service.preview(
        _context(world),
        source,
        resolution_id=63,
        context_revision=23,
    )

    assert result.fact_candidate_count == 0
    assert result.checkpoint.fact_validation_receipts == ()
    assert result.world_fact_operations == ()



def test_v3_fact_operations_are_independent_of_a_failed_mechanics_result():
    from operations.world_operations import CreateRelationOperation

    operation = CreateRelationOperation(
        relation_id="fact_kinship_failed_check",
        subject_id=8,
        relation_type="kinship.sibling",
        target_id=9,
    )
    mechanics_result = SimpleNamespace(
        check=SimpleNamespace(success=False),
        decision=SimpleNamespace(decision=SimpleNamespace(value="skill_check")),
    )
    plan = TurnResolutionPlan(
        player_input="Mara es hermana de Aldric, pero fallo la tirada.",
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
        mechanics_result=mechanics_result,
    )
    preview = SimpleNamespace(world_fact_operations=(operation,))

    updated = DurableTurnExecutionService._append_world_fact_operations(
        plan,
        preview,
    )

    assert updated.mechanics_result is mechanics_result
    assert updated.world_operations == (operation,)
    assert updated.ordered_operations == (operation,)
    assert updated.character_operations == ()



def test_world_fact_feature_gate_requires_an_enabled_preview_service():
    service = object.__new__(DurableTurnExecutionService)
    service.v3_action_preview_service = None
    assert service._world_facts_enabled() is False

    service.v3_action_preview_service = SimpleNamespace()
    assert service._world_facts_enabled() is False

    service.v3_action_preview_service = SimpleNamespace(world_facts_enabled=True)
    assert service._world_facts_enabled() is True


def test_build_v3_action_preview_passes_durable_identity_and_returns_preview():
    service = object.__new__(DurableTurnExecutionService)
    context = object()
    recent = [object()]
    expected = object()
    captured = {}

    class Preview:
        def preview(self, received_context, player_input, **kwargs):
            captured.update(kwargs)
            assert received_context is context
            assert player_input == "Miro la sala."
            return expected

    service.v3_action_preview_service = Preview()
    record = SimpleNamespace(id=71, action_checkpoint_json=None)

    result = service._build_v3_action_preview(
        record,
        context,
        "Miro la sala.",
        recent,
        revision=12,
        lease_token="lease-71",
    )

    assert result is expected
    assert captured == {
        "resolution_id": 71,
        "context_revision": 12,
        "recent_turns": recent,
    }


@pytest.mark.parametrize(
    ("failure", "expected_stage", "expected_code"),
    [
        (
            V3ActionPreviewError("provider_error", "provider"),
            "provider",
            "provider_error",
        ),
        (ValueError("invalid checkpoint"), "checkpoint_encoding", "invalid_preview"),
        (RuntimeError("unexpected provider failure"), "preview", "unexpected_failure"),
    ],
)
def test_build_v3_action_preview_fails_open_with_safe_diagnostic(
    failure,
    expected_stage,
    expected_code,
    caplog,
):
    import logging

    service = object.__new__(DurableTurnExecutionService)

    class Preview:
        def preview(self, *args, **kwargs):
            raise failure

    service.v3_action_preview_service = Preview()
    record = SimpleNamespace(id=72, action_checkpoint_json=None)

    with caplog.at_level(logging.WARNING):
        result = service._build_v3_action_preview(
            record,
            object(),
            "Miro la sala.",
            [],
            revision=13,
            lease_token="lease-72",
        )

    assert result is None
    assert caplog.records[-1].getMessage() == "turn.v3_action_preview.skipped"
    assert caplog.records[-1].preview_stage == expected_stage
    assert caplog.records[-1].preview_code == expected_code


@pytest.mark.parametrize(
    ("preview_service", "checkpoint_json", "lease_token"),
    [
        (None, None, "lease-73"),
        (SimpleNamespace(), '{"existing":true}', "lease-73"),
        (SimpleNamespace(), None, None),
        (SimpleNamespace(), None, ""),
    ],
)
def test_build_v3_action_preview_skips_missing_service_checkpoint_or_lease(
    preview_service,
    checkpoint_json,
    lease_token,
):
    service = object.__new__(DurableTurnExecutionService)
    service.v3_action_preview_service = preview_service
    record = SimpleNamespace(id=73, action_checkpoint_json=checkpoint_json)

    result = service._build_v3_action_preview(
        record,
        object(),
        "Miro la sala.",
        [],
        revision=14,
        lease_token=lease_token,
    )

    assert result is None


def test_append_world_fact_operations_preserves_plan_when_preview_has_no_facts():
    plan = TurnResolutionPlan(
        player_input="Miro la sala.",
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
    )

    assert DurableTurnExecutionService._append_world_fact_operations(
        plan, None
    ) is plan
    assert DurableTurnExecutionService._append_world_fact_operations(
        plan, SimpleNamespace()
    ) is plan


@pytest.mark.parametrize(
    "operations",
    [
        [object()],
        (object(),),
    ],
)
def test_append_world_fact_operations_rejects_non_world_operation_payloads(
    operations,
):
    plan = TurnResolutionPlan(
        player_input="Miro la sala.",
        narrative="",
        world_operations=(),
        character_operations=(),
        ordered_operations=(),
    )

    with pytest.raises(TypeError, match="invalid operations"):
        DurableTurnExecutionService._append_world_fact_operations(
            plan,
            SimpleNamespace(world_fact_operations=operations),
        )


def test_log_v3_action_preview_handles_missing_and_selected_action(caplog):
    import logging

    DurableTurnExecutionService._log_v3_action_preview(None)
    preview = SimpleNamespace(
        selection=SimpleNamespace(
            candidate=SimpleNamespace(action_type="interaction"),
            status=SimpleNamespace(value="selected"),
        ),
        event_count=2,
        checkpoint=SimpleNamespace(nodes=(object(), object())),
        excluded_event_count=1,
        fact_candidate_count=3,
        fact_accepted_count=1,
        fact_already_present_count=0,
        fact_pending_count=1,
        fact_rejected_count=1,
        world_fact_operations=(object(),),
    )

    with caplog.at_level(logging.INFO):
        DurableTurnExecutionService._log_v3_action_preview(preview)

    assert caplog.records[-1].getMessage() == "turn.v3_action_preview.completed"
    assert caplog.records[-1].preview_status == "selected"
    assert caplog.records[-1].preview_selected_action_type == "interaction"
    assert caplog.records[-1].preview_action_node_count == 2
    assert caplog.records[-1].preview_fact_operation_count == 1


def test_log_v3_action_preview_records_unknown_status_without_candidate(caplog):
    import logging

    preview = SimpleNamespace(
        selection=SimpleNamespace(candidate=None, status=object()),
        event_count=0,
        checkpoint=SimpleNamespace(nodes=()),
        excluded_event_count=0,
        fact_candidate_count=0,
        fact_accepted_count=0,
        fact_already_present_count=0,
        fact_pending_count=0,
        fact_rejected_count=0,
        world_fact_operations=(),
    )

    with caplog.at_level(logging.INFO):
        DurableTurnExecutionService._log_v3_action_preview(preview)

    assert caplog.records[-1].message == "turn.v3_action_preview.completed"
    assert caplog.records[-1].preview_status == "unknown"
    assert caplog.records[-1].preview_selected_action_type is None


def test_v3_preview_constructor_rejects_invalid_dependencies_and_options():
    interpreter = _PreviewIntentInterpreter("{}")
    builder = ContextBuilder()

    with pytest.raises(TypeError, match="intent_interpreter"):
        V3ActionPreviewService(cast(IntentInterpreter, object()), builder)
    with pytest.raises(TypeError, match="context_builder"):
        V3ActionPreviewService(interpreter, cast(ContextBuilder, object()))
    with pytest.raises(ValueError, match="max_context_bytes"):
        V3ActionPreviewService(interpreter, builder, max_context_bytes=True)
    with pytest.raises(ValueError, match="max_context_bytes"):
        V3ActionPreviewService(interpreter, builder, max_context_bytes=0)
    with pytest.raises(TypeError, match="reference_resolver"):
        V3ActionPreviewService(interpreter, builder, reference_resolver=cast(Any, object()))
    with pytest.raises(TypeError, match="world_facts_enabled"):
        V3ActionPreviewService(interpreter, builder, world_facts_enabled=cast(bool, 1))


def test_v3_preview_interpretation_fails_closed_when_prompt_construction_fails(
    monkeypatch,
):
    source = "Yo intento abrir la puerta"
    world = WorldState(entities={7: Entity(id=7, name="Arin", entity_type="character")})
    interpreter = _PreviewIntentInterpreter(_v3_response(source))

    def fail_prompt(*args, **kwargs):
        raise RuntimeError("private prompt details")

    monkeypatch.setattr(interpreter, "_build_prompt", fail_prompt)
    service = V3ActionPreviewService(interpreter, _StaticProjectionBuilder(world))

    with pytest.raises(V3ActionPreviewError) as error:
        service._interpret(_context(world), source, None)

    assert error.value.code == "prompt_construction_failed"
    assert error.value.stage == "prompt"
    assert "private prompt details" not in str(error.value)


def test_v3_preview_interpretation_fails_closed_on_provider_exception(monkeypatch):
    source = "Yo intento abrir la puerta"
    world = WorldState(entities={7: Entity(id=7, name="Arin", entity_type="character")})
    interpreter = _PreviewIntentInterpreter(_v3_response(source))

    def fail_provider(*args, **kwargs):
        raise RuntimeError("private provider details")

    monkeypatch.setattr(interpreter.fake_provider, "generate_structured", fail_provider)
    service = V3ActionPreviewService(interpreter, _StaticProjectionBuilder(world))

    with pytest.raises(V3ActionPreviewError) as error:
        service._interpret(_context(world), source, None)

    assert error.value.code == "provider_error"
    assert error.value.stage == "provider"
    assert "private provider details" not in str(error.value)


def test_v3_preview_interpretation_rejects_non_text_provider_response(monkeypatch):
    source = "Yo intento abrir la puerta"
    world = WorldState(entities={7: Entity(id=7, name="Arin", entity_type="character")})
    interpreter = _PreviewIntentInterpreter(_v3_response(source))
    monkeypatch.setattr(
        interpreter.fake_provider,
        "generate_structured",
        lambda *args, **kwargs: {"not": "text"},
    )
    service = V3ActionPreviewService(interpreter, _StaticProjectionBuilder(world))

    with pytest.raises(V3ActionPreviewError) as error:
        service._interpret(_context(world), source, None)

    assert error.value.code == "provider_returned_non_text"
    assert error.value.stage == "provider"


def test_v3_preview_rejects_invalid_context_and_empty_input():
    source = "Yo intento abrir la puerta"
    world = WorldState(entities={7: Entity(id=7, name="Arin", entity_type="character")})
    service, _provider, _builder = _preview_service(world, _v3_response(source))

    with pytest.raises(TypeError, match="context"):
        service.preview(
            cast(TurnContext, object()), source, resolution_id=81, context_revision=1
        )
    with pytest.raises(ValueError, match="player_input"):
        service.preview(
            _context(world), "   ", resolution_id=82, context_revision=1
        )


def test_v3_preview_fails_closed_when_visible_projection_cannot_be_built():
    source = "Yo intento abrir la puerta"
    world = WorldState(entities={7: Entity(id=7, name="Arin", entity_type="character")})

    class FailingProjectionBuilder(_StaticProjectionBuilder):
        def build_proposal_context(self, *args, **kwargs):
            raise RuntimeError("private projection details")

    interpreter = _PreviewIntentInterpreter(_v3_response(source))
    service = V3ActionPreviewService(
        interpreter,
        FailingProjectionBuilder(world),
    )

    with pytest.raises(V3ActionPreviewError) as error:
        service.preview(
            _context(world), source, resolution_id=83, context_revision=1
        )

    assert error.value.code == "visible_context_failed"
    assert error.value.stage == "reference_resolution"
    assert "private projection details" not in str(error.value)

import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace

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
from services.turns import durable_turn_execution_service as module
from services.turns.durable_turn_execution_service import (
    DurableTurnExecutionService,
)
from services.turns.intent_interpreter import IntentInterpreter
from services.turns.player_action_selector import ActionSelectionStatus
from services.turns.v3_action_preview_service import (
    V3ActionPreviewError,
    V3ActionPreviewService,
)


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


def test_shadow_checkpoint_persistence_uses_current_lease_and_cas(monkeypatch):
    source = "Yo intento abrir la puerta"
    checkpoint = PlayerActionCheckpoint(
        resolution_id=51,
        context_revision=12,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        interpretation_sha256=hashlib.sha256(b"{}").hexdigest(),
        nodes=(),
    )
    selection = SimpleNamespace(status=SimpleNamespace(value="exhausted"), candidate=None)
    preview = SimpleNamespace(
        checkpoint=checkpoint,
        selection=selection,
        event_count=0,
        excluded_event_count=0,
    )

    class Preview:
        def preview(self, *args, **kwargs):
            assert kwargs["resolution_id"] == 51
            assert kwargs["context_revision"] == 12
            return preview

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
    service.v3_action_preview_service = Preview()
    service.resolution_repository = Repository()
    service.scope = CampaignScope(1)
    monkeypatch.setattr(module, "transaction", lambda _mode: nullcontext("connection"))
    record = SimpleNamespace(
        id=51,
        context_revision=None,
        action_checkpoint_json=None,
    )

    result = service._persist_v3_action_checkpoint(
        record,
        context=object(),
        player_input=source,
        recent=[],
        revision=12,
        lease_token="lease-token",
    )

    assert result is saved
    assert captured["expected_state"] == "planning"
    assert captured["expected_lease_token"] == "lease-token"
    assert captured["expected_context_revision"] is None
    assert captured["expected_checkpoint_json"] is None
    assert captured["checkpoint_json"] == checkpoint.to_json()
    assert captured["conn"] == "connection"


def test_shadow_checkpoint_persistence_never_regenerates_an_existing_checkpoint():
    class Preview:
        calls = 0

        def preview(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("existing checkpoint must be reused")

    service = object.__new__(DurableTurnExecutionService)
    preview = Preview()
    service.v3_action_preview_service = preview
    record = SimpleNamespace(action_checkpoint_json='{"existing":true}')

    result = service._persist_v3_action_checkpoint(
        record,
        context=object(),
        player_input="texto",
        recent=[],
        revision=12,
        lease_token="lease-token",
    )

    assert result is record
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

    assert result.selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION
    assert result.selection.candidate is not None
    assert result.selection.candidate.reason.value == "unresolved_reference"
    assert result.selection.candidate.resolved_references == ()



def test_shadow_preview_unexpected_failure_does_not_poison_v2_plan():
    class Preview:
        def preview(self, *args, **kwargs):
            raise RuntimeError("private provider exception must not escape")

    service = object.__new__(DurableTurnExecutionService)
    service.v3_action_preview_service = Preview()
    record = SimpleNamespace(
        id=52,
        action_checkpoint_json=None,
        context_revision=None,
    )

    result = service._persist_v3_action_checkpoint(
        record,
        context=object(),
        player_input="Yo intento abrir la puerta",
        recent=[],
        revision=12,
        lease_token="lease-token",
    )

    assert result is record



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

    assert result.selection.status is ActionSelectionStatus.NEEDS_CLARIFICATION
    assert result.selection.candidate is not None
    assert result.selection.candidate.reason.value == "unresolved_reference"
    assert result.selection.candidate.resolved_references == ()

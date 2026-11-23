import json

import pytest

from models.character_state import CharacterState
from models.entity import Entity
from models.mechanics import (
    MechanicsDecision,
    MechanicsDecisionType,
    MechanicsResult,
)
from models.player_action_checkpoint import PlayerActionCheckpoint
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from repositories.turn_resolution_repository import TurnResolutionRepository
from rules_engine.dnd5e_2014.character_checks import ability_check_for_character
from rules_engine.dnd5e_2014.core.dice import DiceRoller
from rules_engine.dnd5e_2014.core.skills import Skill
from services.turns import MechanicsAdjudicator
from services.turns.durable_native_turn_service import DurableNativeTurnError
from services.turns.turn_resolution_service import TurnResolutionPlan
from services.turns.v3_action_progress_codec import V3ActionProgressSnapshot
from tests.durable_turn_test_support import (
    CombinedMechanicsFakeProvider,
    service_with_fake_models,
)
from tests.test_v3_action_preview_service import _preview_service, _v3_response


def _activate_character(service):
    entity = EntityRepository().save_entity(
        Entity(name="Mira", entity_type="player_character"),
        campaign_id=1,
    )
    character = CharacterRepository().save_character(
        CharacterState(
            entity_id=entity.id,
            level=1,
            dexterity=16,
            skill_proficiencies=frozenset({"stealth"}),
        ),
        campaign_id=1,
    )
    service.context_service.set_active_character(
        character.entity_id,
        campaign_id=1,
    )


def _install_manual_skill_check(service, *, advantage=False):
    service.resolver.mechanics_adjudicator = MechanicsAdjudicator(
        CombinedMechanicsFakeProvider(
            response=json.dumps(
                {
                    "decision": "skill_check",
                    "skill": "stealth",
                    "ability": None,
                    "dc": 15,
                    "advantage": advantage,
                    "disadvantage": False,
                    "modifier": 0,
                    "reason": "Evitar al guardia",
                }
            )
        )
    )


def test_silly_tavern_manual_roll_submission_resolves_and_replays_idempotently():
    service, proposal_calls, _ = service_with_fake_models()
    _activate_character(service)
    _install_manual_skill_check(service)

    pending = service.prepare_external_turn(
        "Me escondo del guardia.",
        external_turn_id="st-manual-roll-success-001",
        dice_mode="manual",
    )

    assert pending.lifecycle_state == "awaiting_input"
    assert pending.pending_roll_id is not None
    assert pending.pending_roll["count"] == 1

    resolved = service.submit_manual_roll(
        pending.pending_roll_id,
        (12,),
        adapter_namespace="sillytavern",
        defer_narration=True,
        answer_external_turn_id="st-manual-roll-answer-001",
    )

    assert resolved.lifecycle_state == "narration_pending"
    assert resolved.pending_roll_id is None
    assert resolved.pending_roll is None

    record = service.resolution_repository.get_by_idempotency_key(
        "sillytavern",
        "st-manual-roll-success-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "narration_pending"
    persisted = json.loads(record.adjudication_json)["manual_roll"]
    assert persisted["submitted_rolls"] == [12]
    assert persisted["submitted_external_turn_id"] == (
        "st-manual-roll-answer-001"
    )

    replay = service.submit_manual_roll(
        pending.pending_roll_id,
        (12,),
        adapter_namespace="sillytavern",
        defer_narration=True,
        answer_external_turn_id="st-manual-roll-answer-001",
    )

    assert replay.resolution_id == resolved.resolution_id
    assert replay.lifecycle_state == "narration_pending"
    assert len(proposal_calls) == 1

    with pytest.raises(
        DurableNativeTurnError,
        match="already submitted with different results",
    ):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (13,),
            adapter_namespace="sillytavern",
            defer_narration=True,
            answer_external_turn_id="st-manual-roll-answer-001",
        )

    with pytest.raises(
        DurableNativeTurnError,
        match="different chat message",
    ):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
            answer_external_turn_id="st-different-reply",
        )

    service.complete_external_narration(
        external_turn_id="st-manual-roll-success-001",
        player_input="Me escondo del guardia.",
        narrative="Te ocultas tras una columna.",
        turn_version=1,
    )
    completed_replay = service.submit_manual_roll(
        pending.pending_roll_id,
        (12,),
        adapter_namespace="sillytavern",
        answer_external_turn_id="st-manual-roll-answer-001",
    )
    assert completed_replay.narrative == "Te ocultas tras una columna."
    assert completed_replay.already_processed is True
    assert len(proposal_calls) == 1


def test_silly_tavern_manual_roll_rejects_wrong_number_of_dice():
    service, _, _ = service_with_fake_models()
    _activate_character(service)
    _install_manual_skill_check(service, advantage=True)

    pending = service.prepare_external_turn(
        "Me escondo del guardia con ventaja.",
        external_turn_id="st-manual-roll-count-001",
        dice_mode="manual",
    )

    assert pending.pending_roll["count"] == 2
    with pytest.raises(DurableNativeTurnError, match="invalid number of dice"):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
        )


@pytest.mark.parametrize(
    ("challenge_id", "rolls", "kwargs"),
    [
        ("not-a-challenge", (12,), {}),
        ("42:", (12,), {}),
        (":challenge", (12,), {}),
        ("42:challenge", [], {}),
        ("42:challenge", (), {}),
        ("42:challenge", (True,), {}),
        ("42:challenge", (0,), {}),
        ("42:challenge", (21,), {}),
        ("42:challenge", (12, 13, 14), {}),
        ("42:challenge", (12,), {"answer_external_turn_id": ""}),
        ("42:challenge", (12,), {"answer_external_turn_id": "x" * 501}),
    ],
)
def test_manual_roll_submission_rejects_malformed_input(
    challenge_id, rolls, kwargs
):
    service, _, _ = service_with_fake_models()

    with pytest.raises(DurableNativeTurnError):
        service.submit_manual_roll(challenge_id, rolls, **kwargs)


def test_manual_roll_submission_rejects_unknown_resolution(monkeypatch):
    service, _, _ = service_with_fake_models()
    monkeypatch.setattr(
        service.resolution_repository,
        "get",
        lambda *args, **kwargs: None,
    )

    with pytest.raises(DurableNativeTurnError, match="not found"):
        service.submit_manual_roll("42:challenge", (12,))


def test_manual_roll_submission_rejects_wrong_adapter_namespace(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = service_with_fake_models()
    monkeypatch.setattr(
        service.resolution_repository,
        "get",
        lambda *args, **kwargs: SimpleNamespace(adapter_namespace="native"),
    )

    with pytest.raises(DurableNativeTurnError, match="different adapter"):
        service.submit_manual_roll(
            "42:challenge",
            (12,),
            adapter_namespace="sillytavern",
        )


def test_manual_roll_submission_rejects_stale_or_missing_challenge(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = service_with_fake_models()
    record = SimpleNamespace(
        adapter_namespace="sillytavern",
        adjudication_json=json.dumps(
            {"manual_roll": {"challenge_id": "current"}}
        ),
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get",
        lambda *args, **kwargs: record,
    )

    with pytest.raises(DurableNativeTurnError, match="invalid or stale"):
        service.submit_manual_roll(
            "42:stale",
            (12,),
            adapter_namespace="sillytavern",
        )


def test_manual_roll_submission_rejects_terminal_challenge_state(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = service_with_fake_models()
    record = SimpleNamespace(
        adapter_namespace="sillytavern",
        adjudication_json=json.dumps(
            {"manual_roll": {"challenge_id": "current"}}
        ),
        lifecycle_state="rejected",
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get",
        lambda *args, **kwargs: record,
    )

    with pytest.raises(DurableNativeTurnError, match="no longer pending"):
        service.submit_manual_roll(
            "42:current",
            (12,),
            adapter_namespace="sillytavern",
        )


def test_manual_roll_recovers_prepared_resolution_after_commit_interruption(
    monkeypatch,
):
    service, _, _ = service_with_fake_models()
    _activate_character(service)
    _install_manual_skill_check(service)
    pending = service.prepare_external_turn(
        "Me escondo del guardia.",
        external_turn_id="st-manual-roll-recovery-001",
        dice_mode="manual",
    )

    original_commit = service.prepared_commit_service.commit_prepared_plan
    calls = 0

    def fail_first_commit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("simulated process interruption")
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(
        service.prepared_commit_service,
        "commit_prepared_plan",
        fail_first_commit,
    )
    with pytest.raises(RuntimeError, match="simulated process interruption"):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
            answer_external_turn_id="st-manual-roll-recovery-reply",
        )

    record = service.resolution_repository.get_by_idempotency_key(
        "sillytavern",
        "st-manual-roll-recovery-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "prepared"

    original_get_revision = service.revision_repository.get_revision
    current_revision = record.context_revision
    monkeypatch.setattr(
        service.revision_repository,
        "get_revision",
        lambda *args, **kwargs: current_revision + 1,
    )
    with pytest.raises(
        DurableNativeTurnError,
        match="prepared manual roll became stale before commit",
    ):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
            answer_external_turn_id="st-manual-roll-recovery-reply",
        )

    monkeypatch.setattr(
        service.revision_repository,
        "get_revision",
        original_get_revision,
    )
    recovered = service.submit_manual_roll(
        pending.pending_roll_id,
        (12,),
        adapter_namespace="sillytavern",
        defer_narration=True,
        answer_external_turn_id="st-manual-roll-recovery-reply",
    )

    assert recovered.lifecycle_state == "narration_pending"
    assert calls == 2


def test_manual_roll_rejects_challenge_after_campaign_context_changes():
    service, _, _ = service_with_fake_models()
    _activate_character(service)
    _install_manual_skill_check(service)
    pending = service.prepare_external_turn(
        "Me escondo del guardia.",
        external_turn_id="st-manual-roll-stale-001",
        dice_mode="manual",
    )

    service.context_service.set_active_character(None, campaign_id=1)

    with pytest.raises(
        DurableNativeTurnError,
        match="campaign state changed while waiting for the manual roll",
    ):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
        )

    record = service.resolution_repository.get_by_idempotency_key(
        "sillytavern",
        "st-manual-roll-stale-001",
        scope=service.scope,
    )
    assert record.lifecycle_state == "rejected"
    assert record.last_error_code == "stale_manual_roll"


def test_manual_roll_rejects_a_concurrent_submission_lease(monkeypatch):
    service, _, _ = service_with_fake_models()
    _activate_character(service)
    _install_manual_skill_check(service)
    pending = service.prepare_external_turn(
        "Me escondo del guardia.",
        external_turn_id="st-manual-roll-busy-001",
        dice_mode="manual",
    )

    def already_claimed(*args, **kwargs):
        raise ValueError("planning lease is already held")

    monkeypatch.setattr(
        service.resolution_repository,
        "claim_for_planning",
        already_claimed,
    )
    with pytest.raises(
        DurableNativeTurnError,
        match="manual roll is already being submitted; retry",
    ):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (12,),
            adapter_namespace="sillytavern",
            defer_narration=True,
        )


def test_manual_roll_rejects_missing_pending_state(monkeypatch):
    from types import SimpleNamespace

    service, _, _ = service_with_fake_models()
    record = SimpleNamespace(
        adapter_namespace="sillytavern",
        adjudication_json=json.dumps({}),
    )
    monkeypatch.setattr(
        service.resolution_repository,
        "get",
        lambda *args, **kwargs: record,
    )

    with pytest.raises(DurableNativeTurnError, match="invalid or stale"):
        service.submit_manual_roll(
            "42:challenge",
            (12,),
            adapter_namespace="sillytavern",
        )



def test_native_v3_manual_roll_pauses_and_resumes_same_staged_action(
    monkeypatch,
):
    service, proposal_calls, narrative_calls = service_with_fake_models()
    _activate_character(service)
    target = EntityRepository().save_entity(
        Entity(
            name="Puerta de roble",
            entity_type="location",
            aliases=["la puerta"],
        ),
        campaign_id=service.scope.campaign_id,
    )
    world = service.world_service.load()
    assert target.id in world.entities

    source = "Mira intenta abrir la puerta."
    preview_service, interpreter_provider, _builder = _preview_service(
        world,
        _v3_response(source, actor="Mira"),
    )
    service.execution_service.v3_action_preview_service = preview_service
    service.execution_service.v3_action_execution_enabled = True

    decision = MechanicsDecision(
        decision=MechanicsDecisionType.SKILL_CHECK,
        skill=Skill.STEALTH,
        dc=15,
        reason="Resolver la acción con tirada manual",
    )
    planning_calls = []

    def prepare_action(turn_context, evidence, **kwargs):
        rolls = kwargs.get("manual_rolls")
        planning_calls.append((evidence, rolls))
        analysis = kwargs.get("intent_analysis_override")
        if rolls is None:
            return TurnResolutionPlan(
                player_input=evidence,
                narrative="",
                world_operations=(),
                character_operations=(),
                ordered_operations=(),
                mechanics_decision=decision,
                intent_analysis=analysis,
                intent_evidence_text=kwargs.get("intent_evidence_text"),
                awaiting_manual_roll=True,
            )
        check = ability_check_for_character(
            character=turn_context.active_character,
            roller=DiceRoller(),
            skill=Skill.STEALTH,
            dc=15,
            manual_rolls=rolls,
        )
        return TurnResolutionPlan(
            player_input=evidence,
            narrative="",
            world_operations=(),
            character_operations=(),
            ordered_operations=(),
            mechanics_decision=decision,
            mechanics_result=MechanicsResult(decision, check),
            intent_analysis=analysis,
            intent_evidence_text=kwargs.get("intent_evidence_text"),
        )

    monkeypatch.setattr(service.resolver, "prepare_turn", prepare_action)

    pending = service.play_turn(
        source,
        idempotency_key="native-v3-manual-roll-001",
        dice_mode="manual",
    )
    assert pending.pending_roll_id is not None
    assert pending.pending_roll["count"] == 1
    assert interpreter_provider.call_count == 1
    assert planning_calls == [(source, None)]
    assert proposal_calls == []
    assert narrative_calls == []

    record = TurnResolutionRepository().get_by_idempotency_key(
        "native",
        "native-v3-manual-roll-001",
        scope=service.scope,
    )
    assert record is not None
    assert record.lifecycle_state == "awaiting_input"
    checkpoint = PlayerActionCheckpoint.from_json(record.action_checkpoint_json)
    assert checkpoint.nodes[0].state.value == "in_progress"
    execution_key = checkpoint.nodes[0].execution_key
    staged = V3ActionProgressSnapshot.from_json(record.proposal_json)
    assert staged.entries[0].awaiting_manual_roll is True
    assert staged.entries[0].execution_key == execution_key

    with pytest.raises(DurableNativeTurnError, match="invalid number of dice"):
        service.submit_manual_roll(
            pending.pending_roll_id,
            (15, 16),
        )
    still_pending = service.resolution_repository.get(record.id, scope=service.scope)
    assert still_pending.lifecycle_state == "awaiting_input"
    assert interpreter_provider.call_count == 1
    assert planning_calls == [(source, None)]

    completed = service.submit_manual_roll(
        pending.pending_roll_id,
        (15,),
    )
    assert completed.narrative == "El personaje observa su entorno."
    assert interpreter_provider.call_count == 1
    assert planning_calls == [(source, None), (source, (15,))]
    assert proposal_calls == []
    assert len(narrative_calls) == 1

    saved = service.resolution_repository.get(record.id, scope=service.scope)
    assert saved.lifecycle_state == "completed"
    final_checkpoint = PlayerActionCheckpoint.from_json(saved.action_checkpoint_json)
    assert final_checkpoint.nodes[0].state.value == "resolved"
    assert final_checkpoint.nodes[0].execution_key == execution_key
    assert final_checkpoint.nodes[0].outcome.value == "success"
    adjudication = json.loads(saved.adjudication_json)
    assert adjudication["v3_action_outcomes"][0]["outcome"] == "success"
    assert adjudication["manual_roll"]["submitted_rolls"] == [15]
    final_progress = V3ActionProgressSnapshot.from_json(saved.proposal_json)
    assert final_progress.entries[0].awaiting_manual_roll is False
    assert final_progress.entries[0].execution_key == execution_key

    replay = service.submit_manual_roll(
        pending.pending_roll_id,
        (15,),
    )
    assert replay.narrative == completed.narrative
    assert replay.already_processed is True
    assert interpreter_provider.call_count == 1
    assert planning_calls == [(source, None), (source, (15,))]
    assert len(narrative_calls) == 1

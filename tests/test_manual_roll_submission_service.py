import json

import pytest

from models.character_state import CharacterState
from models.entity import Entity
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.providers import FakeLLMProvider
from services.turns import MechanicsAdjudicator
from services.turns.durable_native_turn_service import DurableNativeTurnError
from tests.durable_turn_test_support import service_with_fake_models


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
        FakeLLMProvider(
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

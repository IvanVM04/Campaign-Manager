import hashlib
import json
from dataclasses import replace

import pytest

from services.turns.v3_action_progress_codec import (
    V3ActionProgressEntry,
    V3ActionProgressSnapshot,
)


def _entry(
    *,
    event_id="event_open",
    action_id="action_open",
    source_order=0,
    execution_key="a" * 64,
    evidence_excerpt="Yo intento abrir la puerta",
    operations_json='{"operations":[]}',
    intent_json='{"schema_version":1}',
    mechanics_json=None,
    mechanics_decision_json=None,
    awaiting_manual_roll=False,
    clarification_question=None,
):
    return V3ActionProgressEntry(
        event_id=event_id,
        action_id=action_id,
        source_order=source_order,
        execution_key=execution_key,
        evidence_excerpt=evidence_excerpt,
        operations_json=operations_json,
        intent_json=intent_json,
        mechanics_json=mechanics_json,
        mechanics_decision_json=mechanics_decision_json,
        awaiting_manual_roll=awaiting_manual_roll,
        clarification_question=clarification_question,
    )


def _snapshot(*entries):
    source = "Yo intento abrir la puerta y examino la caja"
    return V3ActionProgressSnapshot(
        resolution_id=12,
        context_revision=7,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        entries=tuple(entries),
    )


def test_v3_action_progress_snapshot_round_trips_canonical_json_and_repository_update():
    first = _entry()
    second = _entry(
        event_id="event_enter",
        action_id="action_enter",
        source_order=1,
        execution_key="b" * 64,
        evidence_excerpt="entro",
        operations_json='{"operations":[{"type":"MoveEntity"}]}',
        mechanics_json='{"decision":{},"check":{}}',
    )
    snapshot = _snapshot(first).append(second)

    serialized = snapshot.to_json()
    restored = V3ActionProgressSnapshot.from_json(serialized)

    assert restored == snapshot
    assert restored.to_json() == serialized
    assert restored.to_repository_progress_updates() == {
        "proposal_json": serialized
    }
    assert [item.event_id for item in restored.entries] == [
        "event_open",
        "event_enter",
    ]


def test_v3_action_progress_append_is_idempotent_for_the_same_execution_result():
    snapshot = _snapshot(_entry())

    assert snapshot.append(_entry()) is snapshot
    assert V3ActionProgressSnapshot.from_json(snapshot.to_json()).append(
        _entry()
    ) == snapshot


def test_v3_action_progress_rejects_rebound_event_action_or_execution_key():
    snapshot = _snapshot(_entry())

    with pytest.raises(ValueError, match="cannot be rebound"):
        snapshot.append(_entry(operations_json='{"operations":[{"type":"CloseDoor"}]}'))

    with pytest.raises(ValueError, match="execution key"):
        snapshot.append(
            _entry(
                event_id="event_enter",
                action_id="action_enter",
                source_order=1,
            )
        )

    with pytest.raises(ValueError, match="source order"):
        snapshot.append(
            _entry(
                event_id="event_enter",
                action_id="action_enter",
                source_order=0,
                execution_key="b" * 64,
            )
        )


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"event_id": "bad"}, ValueError, "event_id"),
        ({"action_id": "bad"}, ValueError, "action_id"),
        ({"source_order": True}, TypeError, "source_order"),
        ({"source_order": 12}, ValueError, "source_order"),
        ({"execution_key": "bad"}, ValueError, "execution_key"),
        ({"evidence_excerpt": ""}, ValueError, "evidence_excerpt"),
        ({"operations_json": "not json"}, ValueError, "operations_json"),
        ({"operations_json": "[]"}, TypeError, "operations_json"),
        ({"operations_json": '{"unexpected":true}'}, ValueError, "operations_json"),
        ({"intent_json": "[]"}, TypeError, "intent_json"),
        ({"intent_json": '{"schema_version":2}'}, ValueError, "intent_json"),
        ({"mechanics_json": '{"unexpected":true}'}, ValueError, "mechanics_json"),
        (
            {"awaiting_manual_roll": True},
            ValueError,
            "manual roll staging",
        ),
        ({"clarification_question": " "}, ValueError, "clarification_question"),
    ],
)
def test_v3_action_progress_entry_rejects_malformed_fields(kwargs, error, message):
    with pytest.raises(error, match=message):
        _entry(**kwargs)


def test_v3_action_progress_manual_roll_entry_requires_and_preserves_decision():
    decision = '{"decision":"skill_check","dc":14}'
    entry = _entry(
        awaiting_manual_roll=True,
        mechanics_decision_json=decision,
    )
    restored = V3ActionProgressEntry.from_payload(entry.to_dict())

    assert restored.awaiting_manual_roll is True
    assert restored.mechanics_decision_json == decision


def test_v3_action_progress_snapshot_rejects_bad_identity_order_and_schema():
    first = _entry()
    with pytest.raises(ValueError, match="unique"):
        _snapshot(first, replace(first, source_order=1, execution_key="b" * 64))

    with pytest.raises(ValueError, match="unique"):
        _snapshot(
            first,
            _entry(
                event_id="event_enter",
                action_id="action_enter",
                source_order=1,
                execution_key="a" * 64,
            ),
        )

    with pytest.raises(ValueError, match="unsupported"):
        V3ActionProgressSnapshot(
            resolution_id=12,
            context_revision=7,
            source_sha256="c" * 64,
            schema_version=2,
        )

    with pytest.raises(ValueError, match="unsupported"):
        V3ActionProgressSnapshot(
            resolution_id=12,
            context_revision=7,
            source_sha256="c" * 64,
            schema_version=True,
        )


def test_v3_action_progress_decoder_rejects_unknown_and_malformed_payloads():
    snapshot = _snapshot(_entry())
    payload = snapshot.to_dict()
    payload["unexpected"] = True

    with pytest.raises(ValueError, match="missing or unexpected"):
        V3ActionProgressSnapshot.from_payload(payload)

    with pytest.raises(ValueError, match="bounded JSON array"):
        V3ActionProgressSnapshot.from_payload({
            **snapshot.to_dict(),
            "entries": {},
        })

    with pytest.raises(ValueError, match="valid JSON"):
        V3ActionProgressSnapshot.from_json("{")

    with pytest.raises(TypeError, match="text"):
        V3ActionProgressSnapshot.from_json(None)


def test_v3_action_progress_snapshot_enforces_byte_budget():
    # Entry budget is checked at construction, before it can be appended
    # to a snapshot or persisted in the repository.
    with pytest.raises(ValueError, match="entry exceeds"):
        _entry(
            evidence_excerpt="x" * 300,
            operations_json=json.dumps(
                {"operations": [{"payload": "x" * 33_000}]},
                separators=(",", ":"),
            ),
        )



def test_v3_action_progress_replaces_only_a_pending_manual_roll_with_same_identity():
    pending = _entry(
        awaiting_manual_roll=True,
        mechanics_decision_json=(
            '{"decision":"skill_check","skill":"stealth","dc":15,'
            '"ability":null,"advantage":false,"disadvantage":false,'
            '"situational_modifier":0,"reason":"Evitar al guardia","question":null}'
        ),
    )
    snapshot = _snapshot(pending)
    resolved = replace(
        pending,
        operations_json='{"operations":[{"type":"UpdateEntity","entity_id":7}]}',
        mechanics_json='{"decision":{},"check":{}}',
        awaiting_manual_roll=False,
    )

    updated = snapshot.replace_manual_roll_entry(resolved)

    assert updated.entry_for_event("event_open") == resolved
    assert updated.entry_for_event("event_open").awaiting_manual_roll is False
    assert updated.entry_for_event("event_open").execution_key == pending.execution_key
    assert V3ActionProgressSnapshot.from_json(updated.to_json()) == updated


def test_v3_action_progress_rejects_manual_roll_replacement_for_non_pending_or_rebound_entry():
    resolved = _entry(mechanics_json='{"decision":{},"check":{}}')
    with pytest.raises(ValueError, match="not awaiting a manual roll"):
        _snapshot(resolved).replace_manual_roll_entry(resolved)

    pending = _entry(
        awaiting_manual_roll=True,
        mechanics_decision_json='{"decision":"skill_check"}',
    )
    rebound = replace(
        pending,
        awaiting_manual_roll=False,
        mechanics_json='{"decision":{},"check":{}}',
        execution_key="b" * 64,
    )
    with pytest.raises(ValueError, match="cannot rebind"):
        _snapshot(pending).replace_manual_roll_entry(rebound)

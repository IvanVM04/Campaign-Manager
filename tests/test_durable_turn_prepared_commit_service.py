from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from services.turns import durable_turn_prepared_commit_service as commit_module
from services.turns.durable_native_turn_service import DurableNativeTurnError
from services.turns.durable_turn_prepared_commit_service import (
    DurableTurnPreparedCommitService,
)


def test_prepared_commit_service_advances_resolution_atomically(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from services.turns import durable_turn_prepared_commit_service as commit_module
    from services.turns.durable_turn_prepared_commit_service import (
        DurableTurnPreparedCommitService,
    )

    transitions = []
    record = SimpleNamespace(id=17)
    context = object()
    recent = [object()]

    class RevisionRepository:
        def __init__(self):
            self.values = iter([8, 9])

        def get_revision(self, campaign_id, *, conn):
            return next(self.values)

    class ResolutionRepository:
        def transition(self, record_id, state, **kwargs):
            transitions.append((record_id, state, kwargs))

        def get(self, record_id, *, scope):
            return record

    class Resolver:
        def apply_plan(self, current_context, plan, *, conn):
            assert current_context is context
            return SimpleNamespace(all_operations_succeeded=True)

    monkeypatch.setattr(
        commit_module,
        "transaction",
        lambda _mode: nullcontext(object()),
    )
    service = DurableTurnPreparedCommitService(
        scope=SimpleNamespace(campaign_id=3),
        resolver=Resolver(),
        revision_repository=RevisionRepository(),
        resolution_repository=ResolutionRepository(),
        context_loader=lambda _conn: (context, recent),
        operation_results_serializer=lambda _result: "[]",
        error_type=DurableNativeTurnError,
    )

    saved = service.commit_prepared_plan(
        record,
        object(),
        context=context,
        recent=recent,
        revision=8,
        revision_error_message="stale revision",
        context_error_message="stale context",
    )

    assert saved is record
    assert [state for _, state, _ in transitions] == [
        "committed",
        "narration_pending",
    ]
    assert transitions[0][2]["expected_state"] == "prepared"
    assert transitions[0][2]["updates"]["resulting_revision"] == 9
    assert transitions[0][2]["updates"]["operation_results_json"] == "[]"
    assert transitions[1][2]["expected_state"] == "committed"


def test_prepared_commit_service_rejects_stale_revision_before_applying(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from services.turns import durable_turn_prepared_commit_service as commit_module
    from services.turns.durable_turn_prepared_commit_service import (
        DurableTurnPreparedCommitService,
    )

    applied = []
    transitions = []

    class RevisionRepository:
        def get_revision(self, campaign_id, *, conn):
            return 10

    class Resolver:
        def apply_plan(self, *args, **kwargs):
            applied.append(True)
            return SimpleNamespace(all_operations_succeeded=True)

    class ResolutionRepository:
        def transition(self, *args, **kwargs):
            transitions.append(True)

    monkeypatch.setattr(
        commit_module,
        "transaction",
        lambda _mode: nullcontext(object()),
    )
    service = DurableTurnPreparedCommitService(
        scope=SimpleNamespace(campaign_id=3),
        resolver=Resolver(),
        revision_repository=RevisionRepository(),
        resolution_repository=ResolutionRepository(),
        context_loader=lambda _conn: (object(), []),
        operation_results_serializer=lambda _result: "[]",
        error_type=DurableNativeTurnError,
    )

    with pytest.raises(DurableNativeTurnError, match="stale revision") as raised:
        service.commit_prepared_plan(
            SimpleNamespace(id=18),
            object(),
            context=object(),
            recent=[],
            revision=9,
            revision_error_message="stale revision",
            context_error_message="stale context",
        )

    assert raised.value.code == "stale_context"
    assert applied == []
    assert transitions == []


def test_prepared_commit_service_does_not_advance_failed_consequences(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from services.turns import durable_turn_prepared_commit_service as commit_module
    from services.turns.durable_turn_prepared_commit_service import (
        DurableTurnPreparedCommitService,
    )

    transitions = []
    context = object()
    recent = []

    class RevisionRepository:
        def get_revision(self, campaign_id, *, conn):
            return 10

    class Resolver:
        def apply_plan(self, *args, **kwargs):
            return SimpleNamespace(all_operations_succeeded=False)

    class ResolutionRepository:
        def transition(self, *args, **kwargs):
            transitions.append(True)

    monkeypatch.setattr(
        commit_module,
        "transaction",
        lambda _mode: nullcontext(object()),
    )
    service = DurableTurnPreparedCommitService(
        scope=SimpleNamespace(campaign_id=3),
        resolver=Resolver(),
        revision_repository=RevisionRepository(),
        resolution_repository=ResolutionRepository(),
        context_loader=lambda _conn: (context, recent),
        operation_results_serializer=lambda _result: "[]",
        error_type=DurableNativeTurnError,
    )

    with pytest.raises(
        DurableNativeTurnError,
        match="proposed consequences failed validation",
    ) as raised:
        service.commit_prepared_plan(
            SimpleNamespace(id=19),
            object(),
            context=context,
            recent=recent,
            revision=10,
            revision_error_message="stale revision",
            context_error_message="stale context",
        )

    assert raised.value.code == "operation_validation_failed"
    assert transitions == []


@pytest.mark.parametrize(
    ("current_context", "current_recent"),
    [
        ("changed context", []),
        ("original context", ["newer history"]),
    ],
)
def test_prepared_commit_service_rejects_stale_context_or_history(
    monkeypatch,
    current_context,
    current_recent,
):
    applied = []
    transitions = []
    original_context = "original context"
    original_recent = []

    class RevisionRepository:
        def get_revision(self, campaign_id, *, conn):
            return 10

    class Resolver:
        def apply_plan(self, *args, **kwargs):
            applied.append(True)
            return SimpleNamespace(all_operations_succeeded=True)

    class ResolutionRepository:
        def transition(self, *args, **kwargs):
            transitions.append(True)

    monkeypatch.setattr(
        commit_module,
        "transaction",
        lambda _mode: nullcontext(object()),
    )
    service = DurableTurnPreparedCommitService(
        scope=SimpleNamespace(campaign_id=3),
        resolver=Resolver(),
        revision_repository=RevisionRepository(),
        resolution_repository=ResolutionRepository(),
        context_loader=lambda _conn: (current_context, current_recent),
        operation_results_serializer=lambda _result: "[]",
        error_type=DurableNativeTurnError,
    )

    with pytest.raises(DurableNativeTurnError, match="stale context"):
        service.commit_prepared_plan(
            SimpleNamespace(id=20),
            object(),
            context=original_context,
            recent=original_recent,
            revision=10,
            revision_error_message="stale revision",
            context_error_message="stale context",
        )

    assert applied == []
    assert transitions == []

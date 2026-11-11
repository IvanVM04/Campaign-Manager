# ruff: noqa: F401, I001

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

import services.silly_tavern_integration_service as integration_module
from models.campaign_scope import CampaignScope
from models.character_state import CharacterState
from models.entity import Entity
from models.schemas import (
    SillyTavernClarificationIn,
    SillyTavernContextIn,
    SillyTavernTurnIn,
)
from operations.world_operations import CreateEntityOperation
from repositories.campaign_repository import CampaignRepository
from repositories.character_repository import CharacterRepository
from repositories.entity_repository import EntityRepository
from services.silly_tavern_integration_service import (
    SillyTavernIntegrationService,
    SillyTavernIntegrationServiceConflictError,
)
from services.turns import TurnExecutionLock
from services.world import WorldService

from tests.silly_tavern_integration_support import _build_service


def test_integration_service_uses_context_builder_for_context(
    monkeypatch,
):
    (
        service,
        context_builder,
        _extractor,
        _world_service,
        _turn_repository,
    ) = _build_service()

    calls = []

    def fake_build(
        world,
        query,
        recent_turns=None,
    ):
        calls.append(
            {
                "world": world,
                "query": query,
                "recent_turns": recent_turns,
            }
        )

        return {
            "query": query,
            "context": "CONTEXTO",
        }

    monkeypatch.setattr(
        context_builder,
        "build",
        fake_build,
    )

    result = service.get_context(
        "Entro en la taberna."
    )

    assert result["query"] == (
        "Entro en la taberna."
    )

    assert result["context"] == {
        "query": "Entro en la taberna.",
        "context": "CONTEXTO",
    }

    assert len(calls) == 1

    assert calls[0]["query"] == (
        "Entro en la taberna."
    )

    assert isinstance(
        calls[0]["recent_turns"],
        list,
    )


# ============================================================
# SERVICE - NARRATIVE
# ============================================================

def test_integration_service_does_not_generate_narrative(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10, scope=None: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        lambda world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None: (),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
    )

    assert result.narrative == (
        "La puerta se abre."
    )

def test_integration_service_passes_silly_tavern_narrative_to_extractor(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    captured = {}

    def fake_extract(
        text,
        context,
    ):
        captured["text"] = text
        captured["context"] = context

        return []

    monkeypatch.setattr(
        extractor,
        "extract",
        fake_extract,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        lambda world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None: (),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative=(
            "La puerta se abre lentamente."
        ),
    )

    assert captured["text"] == (
        "La puerta se abre lentamente."
    )

    assert captured["context"] is not None

    assert result.narrative == (
        "La puerta se abre lentamente."
    )


# ============================================================
# SERVICE - OPERATIONS
# ============================================================

def test_integration_service_applies_extracted_operations(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    operations = []

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    captured = {}

    def fake_apply_turn_operations(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        captured["world_operations"] = tuple(
            world_operations
        )

        captured["character_operations"] = tuple(
            character_operations
        )

        captured["ordered_operations"] = tuple(
            ordered_operations
        )

        captured["conn"] = conn

        return ()

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        fake_apply_turn_operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: (
            captured.__setitem__(
                "save_conn",
                conn,
            )
            or turn
        ),
    )

    result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
    )

    assert result.operation_count == 0

    assert captured["world_operations"] == ()

    assert captured["character_operations"] == ()

    assert captured["ordered_operations"] == ()

    assert captured["conn"] is not None

    assert captured["save_conn"] is (
        captured["conn"]
    )


# ============================================================
# SERVICE - OPERATION ORDER
# ============================================================

def test_integration_service_preserves_operation_order(
    monkeypatch,
):
    from operations.character_operations import (
        ChangeCharacterHpOperation,
    )
    from operations.referenced_operation import (
        ReferencedOperation,
    )

    (
        service,
        _context_builder,
        extractor,
        world_service,
        turn_repository,
    ) = _build_service()

    # --------------------------------------------------------
    # Operaciones en el orden exacto producido por el extractor.
    #
    # World -> Character -> World
    # --------------------------------------------------------

    operation_a = ReferencedOperation(
        ref="first",
        operation=CreateEntityOperation(
            name="Aldren",
            entity_type="npc",
        ),
    )

    operation_b = ReferencedOperation(
        ref="second",
        operation=ChangeCharacterHpOperation(
            entity_id=1,
            amount=-2,
        ),
    )

    operation_c = ReferencedOperation(
        ref="third",
        operation=CreateEntityOperation(
            name="Marta",
            entity_type="npc",
        ),
    )

    operations = [
        operation_a,
        operation_b,
        operation_c,
    ]

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "list_recent_turns",
        lambda session_id=None, limit=10: [],
    )

    captured = {}

    def fake_apply_turn_operations(
        world_operations,
        character_operations,
        *,
        campaign_id,
        conn=None,
        ordered_operations=None,
    ):
        captured["world_operations"] = tuple(
            world_operations
        )

        captured["character_operations"] = tuple(
            character_operations
        )

        captured["ordered_operations"] = tuple(
            ordered_operations
        )

        captured["conn"] = conn

        # Este test NO pretende probar el contenido de los
        # OperationResult. Solo necesitamos devolver tres
        # elementos para que el resultado del turno tenga
        # la misma cardinalidad que las operaciones.
        return (
            None,
            None,
            None,
        )

    monkeypatch.setattr(
        world_service,
        "apply_turn_operations",
        fake_apply_turn_operations,
    )

    monkeypatch.setattr(
        turn_repository,
        "save_turn",
        lambda turn, *, scope=None, conn=None: turn,
    )

    service.process_turn(
        player_input="Hago algo.",
        narrative="Ocurre algo.",
    )

    # --------------------------------------------------------
    # Las operaciones siguen separadas por tipo.
    # --------------------------------------------------------

    assert captured["world_operations"] == (
        operation_a,
        operation_c,
    )

    assert captured["character_operations"] == (
        operation_b,
    )

    # --------------------------------------------------------
    # ESTA ES LA COMPROBACIÓN IMPORTANTE:
    #
    # El orden original producido por el extractor se conserva
    # aunque las operaciones se separen internamente por tipo.
    # --------------------------------------------------------

    assert captured["ordered_operations"] == (
        operation_a,
        operation_b,
        operation_c,
    )

    # --------------------------------------------------------
    # WorldService recibió una conexión.
    # --------------------------------------------------------

    assert captured["conn"] is not None

def test_integration_service_returns_missing_external_turn_state(
    isolated_database,
):
    (
        service,
        _context_builder,
        _extractor,
        _world_service,
        _turn_repository,
    ) = _build_service()

    result = (
        service.get_external_turn_state(
            "missing-turn"
        )
    )

    assert result == {
        "external_turn_id": "missing-turn",
        "exists": False,
        "active_version": 0,
        "next_version": 1,
        "narrative": None,
    }

def test_integration_service_returns_active_external_turn_state(
    isolated_database,
):
    from models.turn_record import (
        TurnRecord,
    )

    (
        service,
        _context_builder,
        _extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    turn_repository.save_turn(
        TurnRecord(
            session_id=None,
            player_input="Abro la puerta.",
            narrative="La puerta se abre.",
            operation_count=0,
            successful_operation_count=0,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=False,
            external_turn_id="external-turn-123",
            version=4,
            status="active",
            snapshot=None,
        ),
    
        scope=CampaignScope(1),
    )

    result = (
        service.get_external_turn_state(
            "external-turn-123"
        )
    )

    assert result == {
        "external_turn_id": "external-turn-123",
        "exists": True,
        "active_version": 4,
        "next_version": 5,
        "narrative": "La puerta se abre.",
    }

def test_external_turn_state_skips_persisted_failed_narrative_versions(
    isolated_database,
):
    from models.turn_record import TurnRecord

    service, _context_builder, _extractor, _world_service, repository = _build_service()
    repository.save_turn(
        TurnRecord(
            player_input="Abro la puerta.",
            narrative="Versión activa.",
            external_turn_id="turn-with-failed-version",
            version=1,
            status="active",
        ),
        scope=CampaignScope(1),
    )
    repository.save_turn(
        TurnRecord(
            player_input="Abro la puerta.",
            narrative="Versión fallida.",
            operation_count=1,
            successful_operation_count=0,
            failed_operation_count=1,
            all_operations_succeeded=False,
            external_turn_id="turn-with-failed-version",
            version=2,
            status="failed",
        ),
        scope=CampaignScope(1),
    )

    result = service.get_external_turn_state("turn-with-failed-version")

    assert result["active_version"] == 1
    assert result["next_version"] == 3
    assert result["narrative"] == "Versión activa."

def test_integration_service_rejects_non_sequential_turn_version(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    first_result = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        external_turn_id="sequential-version-test",
        turn_version=1,
    )

    assert first_result.narrative == (
        "La puerta se abre."
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="must be the next sequential version",
    ):
        service.process_turn(
            player_input="Abro la puerta de nuevo.",
            narrative="La puerta se abre otra vez.",
            external_turn_id="sequential-version-test",
            turn_version=3,
        )

    active_turn = (
        turn_repository.get_active_by_external_turn_id(
            "sequential-version-test",
        
            scope=CampaignScope(1),
        )
    )

    assert active_turn is not None
    assert active_turn.version == 1

def test_integration_service_allows_next_sequential_version(
    monkeypatch,
):
    (
        service,
        _context_builder,
        extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    monkeypatch.setattr(
        extractor,
        "extract",
        lambda narrative, context: [],
    )

    v1 = service.process_turn(
        player_input="Abro la puerta.",
        narrative="La puerta se abre.",
        external_turn_id="sequential-version-test-2",
        turn_version=1,
    )

    assert v1.narrative == (
        "La puerta se abre."
    )

    v2 = service.process_turn(
        player_input="Miro dentro.",
        narrative="Dentro hay una habitación oscura.",
        external_turn_id="sequential-version-test-2",
        turn_version=2,
    )

    assert v2.narrative == (
        "Dentro hay una habitación oscura."
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="must be the next sequential version",
    ):
        service.process_turn(
            player_input="Entro directamente.",
            narrative="Entras directamente.",
            external_turn_id="sequential-version-test-2",
            turn_version=4,
        )

    active_turn = (
        turn_repository.get_active_by_external_turn_id(
            "sequential-version-test-2",
        
            scope=CampaignScope(1),
        )
    )

    assert active_turn is not None
    assert active_turn.version == 2

def test_silly_tavern_rejects_operations_extracted_from_stale_campaign_state(
    monkeypatch,
):

    (
        service,
        _context_builder,
        extractor,
        _world_service,
        turn_repository,
    ) = _build_service()

    campaign_repository = CampaignRepository()
    campaign = campaign_repository.get_campaign(1)

    def mutate_campaign_during_extraction(_narrative, _context):
        campaign_repository.update_campaign(
            campaign_id=1,
            name="Changed during extraction",
            system=campaign["system"],
            tone=campaign["tone"] or "",
            summary=campaign["summary"] or "",
        )
        return []

    monkeypatch.setattr(
        extractor,
        "extract",
        mutate_campaign_during_extraction,
    )

    with pytest.raises(
        SillyTavernIntegrationServiceConflictError,
        match="campaign state changed while turn operations were being extracted",
    ):
        service.process_turn(
            player_input="Miro alrededor.",
            narrative="La escena continúa.",
            external_turn_id="stale-campaign-state",
            turn_version=1,
        )

    assert turn_repository.list_turns(
        scope=CampaignScope(1),
    ) == []

import pytest

from models.campaign_scope import CampaignScope
from models.turn_record import TurnRecord
from repositories.campaign_repository import CampaignRepository
from repositories.turn_repository import TurnRepository


def test_save_turn_and_get_turn(
    isolated_database,
):
    repository = TurnRepository()

    turn = repository.save_turn(
        TurnRecord(
            session_id=None,
            player_input="Exploro la mina.",
            narrative="La oscuridad de la mina parece observarte.",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
        ),
    
        scope=CampaignScope(1),
    )

    assert turn.id is not None
    assert turn.player_input == (
        "Exploro la mina."
    )
    assert turn.narrative == (
        "La oscuridad de la mina parece observarte."
    )
    assert turn.operation_count == 1
    assert turn.world_changed is True


def test_get_missing_turn_returns_none(
    isolated_database,
):
    repository = TurnRepository()

    assert repository.get_turn(999999,
        scope=CampaignScope(1),
    ) is None


def test_list_turns_returns_saved_turns(
    isolated_database,
):
    repository = TurnRepository()

    repository.save_turn(
        TurnRecord(
            player_input="Primera acción",
            narrative="Primera respuesta",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            player_input="Segunda acción",
            narrative="Segunda respuesta",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_turns(
        scope=CampaignScope(1),
    )

    assert len(turns) == 2
    assert turns[0].player_input == (
        "Primera acción"
    )
    assert turns[1].player_input == (
        "Segunda acción"
    )


def test_list_turns_filters_by_session(
    isolated_database,
):
    from repositories.campaign_repository import CampaignRepository

    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session_one = campaign_repository.create_session(
        campaign_id=1,
        number=1,
        title="Session One",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_two = campaign_repository.create_session(
        campaign_id=1,
        number=2,
        title="Session Two",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Sesión uno",
            narrative="Respuesta uno",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_two["id"],
            player_input="Sesión dos",
            narrative="Respuesta dos",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_turns(
        session_id=session_one["id"],
    
        scope=CampaignScope(1),
    )

    assert len(turns) == 1
    assert turns[0].session_id == session_one["id"]
    assert turns[0].player_input == (
        "Sesión uno"
    )

def test_list_recent_turns_returns_latest_turns_in_chronological_order(
    isolated_database,
):
    repository = TurnRepository()

    for index in range(1, 6):
        repository.save_turn(
            TurnRecord(
                player_input=f"Acción {index}",
                narrative=f"Narrativa {index}",
            ),
        
            scope=CampaignScope(1),
        )

    turns = repository.list_recent_turns(
        limit=3,
    
        scope=CampaignScope(1),
    )

    assert len(turns) == 3

    assert [
        turn.player_input
        for turn in turns
    ] == [
        "Acción 3",
        "Acción 4",
        "Acción 5",
    ]


def test_list_recent_turns_filters_by_session(
    isolated_database,
):
    from repositories.campaign_repository import CampaignRepository

    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session_one = campaign_repository.create_session(
        campaign_id=1,
        number=1,
        title="Session One",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_two = campaign_repository.create_session(
        campaign_id=1,
        number=2,
        title="Session Two",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Uno",
            narrative="Narrativa uno",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_two["id"],
            player_input="Dos",
            narrative="Narrativa dos",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Tres",
            narrative="Narrativa tres",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_recent_turns(
        session_id=session_one["id"],
        limit=10,
    
        scope=CampaignScope(1),
    )

    assert [
        turn.player_input
        for turn in turns
    ] == [
        "Uno",
        "Tres",
    ]


def test_list_recent_turns_rejects_invalid_limit(
    isolated_database,
):
    repository = TurnRepository()

    try:
        repository.list_recent_turns(
            limit=0,
        
            scope=CampaignScope(1),
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected ValueError"
        )


def test_list_recent_turns_rejects_limit_above_maximum(
    isolated_database,
):
    repository = TurnRepository()

    try:
        repository.list_recent_turns(
            limit=101,
        
            scope=CampaignScope(1),
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected ValueError"
        )


def test_list_recent_turns_rejects_non_integer_limit(
    isolated_database,
):
    repository = TurnRepository()

    try:
        repository.list_recent_turns(
            limit="10",
        
            scope=CampaignScope(1),
        )
    except TypeError:
        pass
    else:
        raise AssertionError(
            "Expected TypeError"
        )

def test_list_turns_with_session_id_returns_failed_operation_count(
    isolated_database,
):
    from database import execute, one
    from models.turn_record import TurnRecord
    from repositories.turn_repository import TurnRepository

    execute(
        """
        INSERT INTO sessions (
            number,
            title
        )
        VALUES (?, ?)
        """,
        (999, "test-session"),
    )

    session = one(
        """
        SELECT id
        FROM sessions
        WHERE number=?
        """,
        (999,),
    )

    assert session is not None

    repository = TurnRepository()

    turn = TurnRecord(
        session_id=session["id"],
        player_input="attack",
        narrative="The goblin attacks.",
        operation_count=2,
        successful_operation_count=1,
        failed_operation_count=1,
        all_operations_succeeded=False,
        world_changed=False,
    )

    saved = repository.save_turn(turn,
        scope=CampaignScope(1),
    )

    assert saved.id is not None

    turns = repository.list_turns(
        session_id=session["id"],
    
        scope=CampaignScope(1),
    )

    assert len(turns) == 1
    assert turns[0].failed_operation_count == 1

def test_save_turn_can_use_existing_connection():
    from database import get_conn
    from models.turn_record import TurnRecord
    from repositories.turn_repository import TurnRepository

    repository = TurnRepository()

    turn = TurnRecord(
        session_id=None,
        player_input="attack",
        narrative="The goblin raises its blade.",
        operation_count=1,
        successful_operation_count=1,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=True,
    )

    with get_conn() as conn:
        saved = repository.save_turn(
            turn,
            conn=conn,
        
            scope=CampaignScope(1),
        )

        assert saved.id is not None
        assert saved.player_input == "attack"
        assert saved.operation_count == 1
        assert saved.successful_operation_count == 1
        assert saved.failed_operation_count == 0
        assert saved.all_operations_succeeded is True
        assert saved.world_changed is True

def test_save_turn_with_existing_connection_does_not_commit_independently():
    from database import get_conn
    from models.turn_record import TurnRecord
    from repositories.turn_repository import TurnRepository

    repository = TurnRepository()

    turn = TurnRecord(
        session_id=None,
        player_input="test transaction",
        narrative="Transaction test.",
        operation_count=0,
        successful_operation_count=0,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=False,
    )

    with get_conn() as conn:
        repository.save_turn(
            turn,
            conn=conn,
        
            scope=CampaignScope(1),
        )

        row = conn.execute(
            """
            SELECT
                player_input
            FROM turns
            WHERE player_input=?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("test transaction",),
        ).fetchone()

        assert row is not None

        conn.rollback()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                player_input
            FROM turns
            WHERE player_input=?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("test transaction",),
        ).fetchone()

        assert row is None

def test_list_turns_by_session_returns_complete_turn_record(
    isolated_database,
):
    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session = campaign_repository.create_session(
        campaign_id=1,
        number=9001,
        title="Test Session",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_id = session["id"]

    saved = repository.save_turn(
        TurnRecord(
            session_id=session_id,
            player_input="Pregunto por Aldric.",
            narrative="El tabernero señala una mesa.",
            operation_count=2,
            successful_operation_count=2,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
        ),
    
        scope=CampaignScope(1),
    )

    result = repository.list_turns(
        session_id=session_id,
    
        scope=CampaignScope(1),
    )

    assert len(result) == 1

    turn = result[0]

    assert turn.id == saved.id
    assert turn.session_id == session_id
    assert turn.player_input == "Pregunto por Aldric."
    assert turn.narrative == "El tabernero señala una mesa."

    assert turn.operation_count == 2
    assert turn.successful_operation_count == 2
    assert turn.failed_operation_count == 0

    assert turn.all_operations_succeeded is True
    assert turn.world_changed is True


def test_list_turns_by_session_does_not_return_other_sessions(
    isolated_database,
):
    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session_one = campaign_repository.create_session(
        campaign_id=1,
        number=9002,
        title="Session One",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_two = campaign_repository.create_session(
        campaign_id=1,
        number=9003,
        title="Session Two",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Turno sesión uno.",
            narrative="Narrativa uno.",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_two["id"],
            player_input="Turno sesión dos.",
            narrative="Narrativa dos.",
        ),
    
        scope=CampaignScope(1),
    )

    result = repository.list_turns(
        session_id=session_one["id"],
    
        scope=CampaignScope(1),
    )

    assert len(result) == 1

    assert result[0].session_id == session_one["id"]
    assert result[0].player_input == (
        "Turno sesión uno."
    )


def test_list_recent_turns_by_session_preserves_complete_metadata(
    isolated_database,
):
    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session = campaign_repository.create_session(
        campaign_id=1,
        number=9004,
        title="Test Session",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_id = session["id"]

    repository.save_turn(
        TurnRecord(
            session_id=session_id,
            player_input="Primer turno.",
            narrative="Primera escena.",
            operation_count=3,
            successful_operation_count=3,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_id,
            player_input="Segundo turno.",
            narrative="Segunda escena.",
            operation_count=1,
            successful_operation_count=0,
            failed_operation_count=1,
            all_operations_succeeded=False,
            world_changed=False,
        ),
    
        scope=CampaignScope(1),
    )

    result = repository.list_recent_turns(
        session_id=session_id,
        limit=2,
    
        scope=CampaignScope(1),
    )

    assert len(result) == 2

    first = result[0]
    second = result[1]

    assert first.player_input == "Primer turno."
    assert first.operation_count == 3
    assert first.successful_operation_count == 3
    assert first.failed_operation_count == 0
    assert first.all_operations_succeeded is True
    assert first.world_changed is True

    assert second.player_input == "Segundo turno."
    assert second.operation_count == 1
    assert second.successful_operation_count == 0
    assert second.failed_operation_count == 1
    assert second.all_operations_succeeded is False
    assert second.world_changed is False


def test_list_turns_returns_turns_in_ascending_order(
    isolated_database,
):
    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session = campaign_repository.create_session(
        campaign_id=1,
        number=9005,
        title="Test Session",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_id = session["id"]

    first = repository.save_turn(
        TurnRecord(
            session_id=session_id,
            player_input="Primero.",
            narrative="Primero.",
        ),
    
        scope=CampaignScope(1),
    )

    second = repository.save_turn(
        TurnRecord(
            session_id=session_id,
            player_input="Segundo.",
            narrative="Segundo.",
        ),
    
        scope=CampaignScope(1),
    )

    result = repository.list_turns(
        session_id=session_id,
    
        scope=CampaignScope(1),
    )

    assert [turn.id for turn in result] == [
        first.id,
        second.id,
    ]

def test_get_turn_rejects_invalid_turn_id_type(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.get_turn("1",
            scope=CampaignScope(1),
        )


def test_get_turn_rejects_non_positive_turn_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(ValueError):
        repository.get_turn(0,
            scope=CampaignScope(1),
        )


def test_get_turn_rejects_boolean_turn_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.get_turn(True,
            scope=CampaignScope(1),
        )


def test_list_turns_rejects_invalid_session_id_type(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.list_turns(
            session_id="1",
        
            scope=CampaignScope(1),
        )


def test_list_turns_rejects_non_positive_session_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(ValueError):
        repository.list_turns(
            session_id=0,
        
            scope=CampaignScope(1),
        )


def test_list_turns_rejects_boolean_session_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.list_turns(
            session_id=True,
        
            scope=CampaignScope(1),
        )


def test_list_recent_turns_rejects_invalid_session_id_type(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.list_recent_turns(
            session_id="1",
        
            scope=CampaignScope(1),
        )


def test_list_recent_turns_rejects_non_positive_session_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(ValueError):
        repository.list_recent_turns(
            session_id=0,
        
            scope=CampaignScope(1),
        )


def test_list_recent_turns_rejects_boolean_session_id(
    isolated_database,
):
    repository = TurnRepository()

    with pytest.raises(TypeError):
        repository.list_recent_turns(
            session_id=True,
        
            scope=CampaignScope(1),
        )

def test_save_turn_with_connection_does_not_commit_transaction(
    isolated_database,
):
    from database import get_conn
    from models.turn_record import TurnRecord
    from repositories.turn_repository import TurnRepository

    repository = TurnRepository()

    with get_conn() as conn:
        turn = TurnRecord(
            session_id=None,
            player_input="Exploro.",
            narrative="Encuentras una puerta.",
            operation_count=0,
            successful_operation_count=0,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=False,
        )

        saved = repository.save_turn(
            turn,
            conn=conn,
        
            scope=CampaignScope(1),
        )

        assert saved.id is not None

        row = conn.execute(
            """
            SELECT id
            FROM turns
            WHERE id=?
            """,
            (saved.id,),
        ).fetchone()

        assert row is not None

        # La transacción debe seguir bajo control del caller.
        conn.rollback()

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM turns
            WHERE id=?
            """,
            (saved.id,),
        ).fetchone()

        assert row is None

def test_save_turn_without_connection_persists_turn(
    isolated_database,
):
    from models.turn_record import TurnRecord
    from repositories.turn_repository import TurnRepository

    repository = TurnRepository()

    turn = TurnRecord(
        session_id=None,
        player_input="Espero.",
        narrative="Pasa una hora.",
        operation_count=0,
        successful_operation_count=0,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=False,
    )

    saved = repository.save_turn(turn,
        scope=CampaignScope(1),
    )

    assert saved.id is not None

    loaded = repository.get_turn(saved.id,
        scope=CampaignScope(1),
    )

    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.player_input == "Espero."
    assert loaded.narrative == "Pasa una hora."

def test_get_active_by_external_turn_id_returns_turn_record(
    isolated_database,
):
    repository = TurnRepository()

    turn = repository.save_turn(
        TurnRecord(
            player_input="Cojo la espada.",
            narrative="Narrativa v1",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
            external_turn_id="external-123",
            version=1,
            status="active",
        ),
    
        scope=CampaignScope(1),
    )

    active_turn = (
        repository.get_active_by_external_turn_id(
            "external-123",
        
            scope=CampaignScope(1),
        )
    )

    assert active_turn is not None
    assert active_turn.id == turn.id
    assert active_turn.external_turn_id == "external-123"
    assert active_turn.version == 1
    assert active_turn.status == "active"


def test_get_versions_by_external_turn_id_returns_all_versions(
    isolated_database,
):
    repository = TurnRepository()

    repository.save_turn(
        TurnRecord(
            player_input="Cojo la espada.",
            narrative="Narrativa v1",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
            external_turn_id="external-123",
            version=1,
            status="superseded",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            player_input="Cojo la espada.",
            narrative="Narrativa v2",
            operation_count=0,
            successful_operation_count=0,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=False,
            external_turn_id="external-123",
            version=2,
            status="active",
        ),
    
        scope=CampaignScope(1),
    )

    versions = (
        repository.get_versions_by_external_turn_id(
            "external-123",
        
            scope=CampaignScope(1),
        )
    )

    assert len(versions) == 2

    assert versions[0].version == 1
    assert versions[0].status == "superseded"

    assert versions[1].version == 2
    assert versions[1].status == "active"


def test_turn_repository_preserves_version_status(
    isolated_database,
):
    repository = TurnRepository()

    original = TurnRecord(
        session_id=None,
        player_input="Regenero el turno.",
        narrative="Una nueva escena.",
        operation_count=1,
        successful_operation_count=1,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=True,
        external_turn_id="turn-123",
        version=2,
        status="active",
    )

    saved = repository.save_turn(original,
        scope=CampaignScope(1),
    )

    assert saved.version == 2
    assert saved.status == "active"

    loaded = repository.get_turn(saved.id,
        scope=CampaignScope(1),
    )

    assert loaded is not None
    assert loaded.version == 2
    assert loaded.status == "active"

def test_list_turns_preserves_version_status(
    isolated_database,
):
    repository = TurnRepository()

    repository.save_turn(
        TurnRecord(
            player_input="Turno v2",
            narrative="Narrativa v2",
            operation_count=1,
            successful_operation_count=1,
            failed_operation_count=0,
            all_operations_succeeded=True,
            world_changed=True,
            external_turn_id="turn-456",
            version=2,
            status="superseded",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_turns(
        scope=CampaignScope(1),
    )

    assert len(turns) == 1
    assert turns[0].version == 2
    assert turns[0].status == "superseded"

def test_list_recent_active_turns_excludes_superseded_turns(
    isolated_database,
):
    repository = TurnRepository()

    active_turn = repository.save_turn(
        TurnRecord(
            player_input="Acción activa",
            narrative="Narrativa activa",
            version=2,
            status="active",
        ),
    
        scope=CampaignScope(1),
    )

    superseded_turn = repository.save_turn(
        TurnRecord(
            player_input="Acción antigua",
            narrative="Narrativa antigua",
            version=1,
            status="superseded",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_recent_active_turns(
        limit=10,
    
        scope=CampaignScope(1),
    )

    assert len(turns) == 1

    assert turns[0].id == active_turn.id
    assert turns[0].player_input == "Acción activa"
    assert turns[0].status == "active"

    assert all(
        turn.id != superseded_turn.id
        for turn in turns
    )

def test_list_recent_active_turns_filters_by_session(
    isolated_database,
):
    repository = TurnRepository()
    campaign_repository = CampaignRepository()

    session_one = campaign_repository.create_session(
        campaign_id=1,
        number=1,
        title="Session One",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    session_two = campaign_repository.create_session(
        campaign_id=1,
        number=2,
        title="Session Two",
        summary="",
        start_location="",
        end_location="",
        notes="",
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Activo uno",
            narrative="Narrativa uno",
            status="active",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_one["id"],
            player_input="Superado uno",
            narrative="Narrativa superada",
            status="superseded",
        ),
    
        scope=CampaignScope(1),
    )

    repository.save_turn(
        TurnRecord(
            session_id=session_two["id"],
            player_input="Activo dos",
            narrative="Narrativa dos",
            status="active",
        ),
    
        scope=CampaignScope(1),
    )

    turns = repository.list_recent_active_turns(
        session_id=session_one["id"],
        limit=10,
    
        scope=CampaignScope(1),
    )

    assert [
        turn.player_input
        for turn in turns
    ] == [
        "Activo uno",
    ]

def test_list_recent_turns_uses_supplied_connection(
    isolated_database,
):
    from database import get_conn

    repository = TurnRepository()

    turn = TurnRecord(
        session_id=None,
        player_input="transactional recent turn",
        narrative="Narrativa.",
        operation_count=0,
        successful_operation_count=0,
        failed_operation_count=0,
        all_operations_succeeded=True,
        world_changed=False,
    )

    with get_conn() as conn:
        repository.save_turn(
            turn,
            conn=conn,
        
            scope=CampaignScope(1),
        )

        recent_turns = repository.list_recent_turns(
            limit=10,
            conn=conn,
        
            scope=CampaignScope(1),
        )

        assert any(
            item.player_input == "transactional recent turn"
            for item in recent_turns
        )


def test_turns_with_same_external_id_are_isolated_by_campaign(
    isolated_database,
):
    from database import get_conn

    repository = TurnRepository()
    campaign_one = CampaignScope(1)
    campaign_two = CampaignScope(2)

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO campaign (id, name, system) VALUES (2, ?, ?)",
            ("Campaign Two", "D&D 5e 2014"),
        )

    for scope, narrative in (
        (campaign_one, "Narrative one"),
        (campaign_two, "Narrative two"),
    ):
        repository.save_turn(
            TurnRecord(
                player_input="Same player input",
                narrative=narrative,
                external_turn_id="shared-external-id",
                version=1,
            ),
            scope=scope,
        )

    active_one = repository.get_active_by_external_turn_id(
        "shared-external-id",
        scope=campaign_one,
    )
    active_two = repository.get_active_by_external_turn_id(
        "shared-external-id",
        scope=campaign_two,
    )

    assert active_one is not None
    assert active_two is not None
    assert active_one.narrative == "Narrative one"
    assert active_two.narrative == "Narrative two"
    assert [
        turn.narrative
        for turn in repository.list_turns(scope=campaign_one)
    ] == ["Narrative one"]
    assert [
        turn.narrative
        for turn in repository.list_turns(scope=campaign_two)
    ] == ["Narrative two"]
    assert [
        turn.narrative
        for turn in repository.list_recent_active_turns(
            scope=campaign_one
        )
    ] == ["Narrative one"]
    assert len(
        repository.get_versions_by_external_turn_id(
            "shared-external-id",
            scope=campaign_one,
        )
    ) == 1
    assert len(
        repository.get_versions_by_external_turn_id(
            "shared-external-id",
            scope=campaign_two,
        )
    ) == 1


def test_supersede_turn_cannot_change_another_campaign(
    isolated_database,
):
    from database import get_conn

    repository = TurnRepository()
    campaign_one = CampaignScope(1)
    campaign_two = CampaignScope(2)

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO campaign (id, name, system) VALUES (2, ?, ?)",
            ("Campaign Two", "D&D 5e 2014"),
        )

    turn_two = repository.save_turn(
        TurnRecord(
            player_input="Second campaign turn",
            narrative="Must remain active",
            external_turn_id="campaign-two-turn",
            version=1,
        ),
        scope=campaign_two,
    )

    with get_conn() as conn, pytest.raises(LookupError):
        repository.supersede_turn(
            turn_two.id,
            scope=campaign_one,
            conn=conn,
        )

    unchanged = repository.get_active_by_external_turn_id(
        "campaign-two-turn",
        scope=campaign_two,
    )
    assert unchanged is not None
    assert unchanged.status == "active"



def test_list_turns_supports_offset_without_changing_order(isolated_database):
    repository = TurnRepository()
    scope = CampaignScope(1)
    saved = []
    for index in range(3):
        saved.append(
            repository.save_turn(
                TurnRecord(
                    player_input=f"Action {index}",
                    narrative=f"Narrative {index}",
                ),
                scope=scope,
            )
        )

    page = repository.list_turns(scope=scope, limit=2, offset=1)

    assert [turn.id for turn in page] == [saved[1].id, saved[2].id]


def test_list_turns_rejects_invalid_offset(isolated_database):
    repository = TurnRepository()
    with pytest.raises(ValueError, match="offset must not be negative"):
        repository.list_turns(scope=CampaignScope(1), offset=-1)
    with pytest.raises(TypeError, match="offset must be an integer"):
        repository.list_turns(scope=CampaignScope(1), offset=True)

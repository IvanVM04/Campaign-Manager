import sqlite3

from migrations import (
    migration_001,
    migration_002,
    migration_003,
    migration_004,
    migration_005,
    migration_006,
    migration_007,
    migration_008,
    migration_009,
    migration_010,
    migration_011,
)


def create_version_10_database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrations = (
        migration_001,
        migration_002,
        migration_003,
        migration_004,
        migration_005,
        migration_006,
        migration_007,
        migration_008,
        migration_009,
        migration_010,
    )

    for migration in migrations:
        migration(conn)

    conn.execute("PRAGMA user_version = 10")

    return conn


def test_migration_011_preserves_existing_data():
    conn = create_version_10_database()

    entity_id = conn.execute(
        """
        INSERT INTO entities (
            name,
            entity_type
        )
        VALUES (?, ?)
        """,
        ("Darian", "character"),
    ).lastrowid

    session_id = conn.execute(
        """
        INSERT INTO sessions (
            number,
            title
        )
        VALUES (?, ?)
        """,
        (1, "Primera sesión"),
    ).lastrowid

    turn_id = conn.execute(
        """
        INSERT INTO turns (
            session_id,
            player_input,
            narrative,
            external_turn_id
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            session_id,
            "Entro en la taberna",
            "La taberna está llena de viajeros",
            "turn-001",
        ),
    ).lastrowid

    migration_011(conn)

    entity = conn.execute(
        "SELECT * FROM entities WHERE id = ?",
        (entity_id,),
    ).fetchone()

    session = conn.execute(
        "SELECT * FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()

    turn = conn.execute(
        "SELECT * FROM turns WHERE id = ?",
        (turn_id,),
    ).fetchone()

    assert entity["name"] == "Darian"
    assert entity["campaign_id"] == 1

    assert session["number"] == 1
    assert session["campaign_id"] == 1

    assert turn["external_turn_id"] == "turn-001"
    assert turn["campaign_id"] == 1

    assert conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []

    conn.close()


def test_migration_011_allows_multiple_campaigns():
    conn = create_version_10_database()

    migration_011(conn)

    conn.execute(
        """
        INSERT INTO campaign (
            id,
            name
        )
        VALUES (?, ?)
        """,
        (2, "Segunda campaña"),
    )

    campaigns = conn.execute(
        "SELECT id, name FROM campaign ORDER BY id"
    ).fetchall()

    assert [(row["id"], row["name"]) for row in campaigns] == [
        (1, "Nueva campaña"),
        (2, "Segunda campaña"),
    ]

    conn.close()


def test_migration_011_scopes_active_external_turns_by_campaign():
    conn = create_version_10_database()

    migration_011(conn)

    conn.execute(
        """
        INSERT INTO campaign (
            id,
            name
        )
        VALUES (?, ?)
        """,
        (2, "Segunda campaña"),
    )

    conn.execute(
        """
        INSERT INTO turns (
            campaign_id,
            player_input,
            narrative,
            external_turn_id,
            version,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (1, "Input A", "Narrativa A", "same-id", 1, "active"),
    )

    conn.execute(
        """
        INSERT INTO turns (
            campaign_id,
            player_input,
            narrative,
            external_turn_id,
            version,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (2, "Input B", "Narrativa B", "same-id", 1, "active"),
    )

    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM turns
        WHERE external_turn_id = ?
        """,
        ("same-id",),
    ).fetchone()[0]

    assert count == 2

    conn.close()
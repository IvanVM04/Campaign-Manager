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
    migration_012,
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

def create_version_11_database():
    conn = create_version_10_database()
    migration_011(conn)
    conn.execute("PRAGMA user_version = 11")
    return conn

def test_migration_012_preserves_existing_items_and_resources():
    conn = create_version_11_database()

    item_id = conn.execute(
        """
        INSERT INTO items (
            name,
            description,
            campaign_id
        )
        VALUES (?, ?, ?)
        """,
        ("Espada de hierro", "Una espada antigua", 1),
    ).lastrowid

    resource_id = conn.execute(
        """
        INSERT INTO resources (
            name,
            resource_type,
            campaign_id
        )
        VALUES (?, ?, ?)
        """,
        ("Oro", "currency", 1),
    ).lastrowid

    migration_012(conn)

    item = conn.execute(
        "SELECT * FROM items WHERE id = ?",
        (item_id,),
    ).fetchone()

    resource = conn.execute(
        "SELECT * FROM resources WHERE id = ?",
        (resource_id,),
    ).fetchone()

    assert item["name"] == "Espada de hierro"
    assert item["description"] == "Una espada antigua"
    assert item["campaign_id"] == 1

    assert resource["name"] == "Oro"
    assert resource["resource_type"] == "currency"
    assert resource["campaign_id"] == 1

    assert conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []

    conn.close()


def test_migration_012_allows_same_item_and_resource_names_in_different_campaigns():
    conn = create_version_11_database()
    migration_012(conn)

    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (?, ?)",
        (2, "Segunda campaña"),
    )

    conn.execute(
        """
        INSERT INTO items (name, campaign_id)
        VALUES (?, ?)
        """,
        ("Espada de hierro", 1),
    )

    conn.execute(
        """
        INSERT INTO items (name, campaign_id)
        VALUES (?, ?)
        """,
        ("Espada de hierro", 2),
    )

    conn.execute(
        """
        INSERT INTO resources (name, campaign_id)
        VALUES (?, ?)
        """,
        ("Oro", 1),
    )

    conn.execute(
        """
        INSERT INTO resources (name, campaign_id)
        VALUES (?, ?)
        """,
        ("Oro", 2),
    )

    assert conn.execute(
        "SELECT COUNT(*) FROM items WHERE name = ?",
        ("Espada de hierro",),
    ).fetchone()[0] == 2

    assert conn.execute(
        "SELECT COUNT(*) FROM resources WHERE name = ?",
        ("Oro",),
    ).fetchone()[0] == 2

    conn.close()


def test_migration_012_rejects_cross_campaign_item_instance_references():
    conn = create_version_11_database()
    migration_012(conn)

    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (?, ?)",
        (2, "Segunda campaña"),
    )

    entity_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES (?, ?, ?)
        """,
        ("Personaje campaña 1", "character", 1),
    ).lastrowid

    item_id = conn.execute(
        """
        INSERT INTO items (name, campaign_id)
        VALUES (?, ?)
        """,
        ("Espada", 2),
    ).lastrowid

    import pytest

    with pytest.raises(
        sqlite3.IntegrityError,
        match="cross-campaign reference",
    ):
        conn.execute(
            """
            INSERT INTO item_instances (
                item_id,
                owner_id,
                campaign_id
            )
            VALUES (?, ?, ?)
            """,
            (item_id, entity_id, 1),
        )

    conn.close()


def test_migration_012_rejects_records_for_nonexistent_campaign():
    conn = create_version_11_database()
    migration_012(conn)

    import pytest

    with pytest.raises(
        sqlite3.IntegrityError,
        match="campaign_id does not exist",
    ):
        conn.execute(
            """
            INSERT INTO entities (
                name,
                entity_type,
                campaign_id
            )
            VALUES (?, ?, ?)
            """,
            ("Personaje inexistente", "character", 999),
        )

    conn.close()

def test_migration_012_allows_same_session_number_in_different_campaigns():
    import sqlite3

    import pytest

    conn = create_version_11_database()
    migration_012(conn)

    conn.execute("""
        INSERT INTO campaign (id, name)
        VALUES (2, 'Campaign 2')
    """)

    conn.execute("""
        INSERT INTO sessions (number, title, campaign_id)
        VALUES (1, 'Session 1 - Campaign 1', 1)
    """)

    conn.execute("""
        INSERT INTO sessions (number, title, campaign_id)
        VALUES (1, 'Session 1 - Campaign 2', 2)
    """)

    count = conn.execute("""
        SELECT COUNT(*)
        FROM sessions
        WHERE number = 1
    """).fetchone()[0]

    assert count == 2

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO sessions (number, title, campaign_id)
            VALUES (1, 'Duplicate session', 1)
        """)

    conn.close()
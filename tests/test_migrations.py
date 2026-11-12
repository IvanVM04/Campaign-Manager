import sqlite3

from migrations import (
    CURRENT_VERSION,
    MIGRATIONS,
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
    migration_013,
    migration_014,
    migration_015,
    migration_016,
    migration_017,
    migration_018,
    migration_019,
    migration_020,
    migration_021,
    migration_022,
    migration_026,
    migration_029,
    migration_030,
    migration_031,
    run_migrations,
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


def create_version_12_database():
    conn = create_version_11_database()
    migration_012(conn)
    conn.execute("PRAGMA user_version = 12")
    return conn


def test_migration_013_rejects_cross_campaign_current_location():
    import pytest

    conn = create_version_12_database()
    migration_013(conn)

    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')"
    )
    location_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Location 1', 'location', 1)
        """
    ).lastrowid

    with pytest.raises(
        sqlite3.IntegrityError,
        match="same campaign",
    ):
        conn.execute(
            "UPDATE campaign SET current_location_id = ? WHERE id = 2",
            (location_id,),
        )

    conn.close()


def test_migration_013_rejects_cross_campaign_current_session():
    import pytest

    conn = create_version_12_database()
    migration_013(conn)

    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')"
    )
    session_id = conn.execute(
        """
        INSERT INTO sessions (number, title, campaign_id)
        VALUES (1, 'Session 1', 1)
        """
    ).lastrowid

    with pytest.raises(
        sqlite3.IntegrityError,
        match="same campaign",
    ):
        conn.execute(
            "UPDATE campaign SET current_session_id = ? WHERE id = 2",
            (session_id,),
        )

    conn.close()


def test_migration_013_rejects_cross_campaign_active_character():
    import pytest

    conn = create_version_12_database()
    migration_013(conn)

    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')"
    )
    entity_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Character 1', 'character', 1)
        """
    ).lastrowid
    conn.execute(
        """
        INSERT INTO character_states (entity_id, campaign_id)
        VALUES (?, 1)
        """,
        (entity_id,),
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match="same campaign",
    ):
        conn.execute(
            "UPDATE campaign SET active_character_id = ? WHERE id = 2",
            (entity_id,),
        )

    conn.close()


def test_migration_013_allows_campaign_to_select_its_own_state():
    conn = create_version_12_database()
    migration_013(conn)

    entity_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Character 1', 'character', 1)
        """
    ).lastrowid
    conn.execute(
        """
        INSERT INTO character_states (entity_id, campaign_id)
        VALUES (?, 1)
        """,
        (entity_id,),
    )
    session_id = conn.execute(
        """
        INSERT INTO sessions (number, title, campaign_id)
        VALUES (1, 'Session 1', 1)
        """
    ).lastrowid

    conn.execute(
        """
        UPDATE campaign
        SET active_character_id = ?,
            current_session_id = ?,
            current_location_id = ?
        WHERE id = 1
        """,
        (entity_id, session_id, entity_id),
    )

    row = conn.execute(
        """
        SELECT active_character_id, current_session_id, current_location_id
        FROM campaign WHERE id = 1
        """
    ).fetchone()

    assert tuple(row) == (entity_id, session_id, entity_id)
    conn.close()



def create_version_13_database():
    conn = create_version_12_database()
    migration_013(conn)
    conn.execute("PRAGMA user_version = 13")
    return conn


def test_migration_014_clears_campaign_pointers_when_targets_are_deleted():
    conn = create_version_13_database()
    migration_014(conn)

    character_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Character 1', 'character', 1)
        """
    ).lastrowid
    conn.execute(
        """
        INSERT INTO character_states (entity_id, campaign_id)
        VALUES (?, 1)
        """,
        (character_id,),
    )
    location_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Location 1', 'location', 1)
        """
    ).lastrowid
    session_id = conn.execute(
        """
        INSERT INTO sessions (number, title, campaign_id)
        VALUES (1, 'Session 1', 1)
        """
    ).lastrowid

    conn.execute(
        """
        UPDATE campaign
        SET active_character_id = ?,
            current_location_id = ?,
            current_session_id = ?
        WHERE id = 1
        """,
        (character_id, location_id, session_id),
    )

    # Character deletion through CharacterRepository removes only
    # character_states, not the identity entity.
    conn.execute(
        "DELETE FROM character_states WHERE entity_id = ? AND campaign_id = 1",
        (character_id,),
    )
    row = conn.execute(
        "SELECT active_character_id FROM campaign WHERE id = 1"
    ).fetchone()
    assert row[0] is None

    conn.execute(
        "DELETE FROM sessions WHERE id = ? AND campaign_id = 1",
        (session_id,),
    )
    row = conn.execute(
        "SELECT current_session_id FROM campaign WHERE id = 1"
    ).fetchone()
    assert row[0] is None

    # Deleting an entity used as the current location clears that pointer.
    conn.execute(
        "DELETE FROM entities WHERE id = ? AND campaign_id = 1",
        (location_id,),
    )
    row = conn.execute(
        "SELECT current_location_id FROM campaign WHERE id = 1"
    ).fetchone()
    assert row[0] is None

    conn.close()


def test_migration_015_adds_empty_proficiencies_without_losing_characters():
    conn = create_version_13_database()
    migration_014(conn)
    conn.execute("PRAGMA user_version = 14")
    entity_id = conn.execute(
        "INSERT INTO entities (name, entity_type, campaign_id) VALUES ('Hero', 'character', 1)"
    ).lastrowid
    conn.execute(
        "INSERT INTO character_states (entity_id, campaign_id) VALUES (?, 1)",
        (entity_id,),
    )
    conn.commit()
    migration_015(conn)
    row = conn.execute(
        "SELECT skill_proficiencies, skill_expertise, saving_throw_proficiencies FROM character_states WHERE entity_id = ?",
        (entity_id,),
    ).fetchone()
    assert tuple(row) == ("[]", "[]", "[]")
    conn.close()


def create_version_20_database():
    conn = create_version_13_database()
    migrations = (
        migration_014,
        migration_015,
        migration_016,
        migration_017,
        migration_018,
        migration_019,
        migration_020,
    )
    for version, migration in enumerate(migrations, start=14):
        migration(conn)
        conn.execute(f"PRAGMA user_version = {version}")
    return conn


def test_migration_021_initializes_revisions_and_tracks_existing_campaigns():
    conn = create_version_20_database()
    conn.execute(
        "INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')"
    )
    entity_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, campaign_id)
        VALUES ('Existing NPC', 'npc', 1)
        """
    ).lastrowid

    migration_021(conn)

    revisions = conn.execute(
        "SELECT campaign_id, revision FROM campaign_state_versions ORDER BY campaign_id"
    ).fetchall()
    assert [tuple(row) for row in revisions] == [(1, 1), (2, 1)]

    conn.execute(
        "UPDATE entities SET name = 'Updated NPC' WHERE id = ? AND campaign_id = 1",
        (entity_id,),
    )
    revision = conn.execute(
        "SELECT revision FROM campaign_state_versions WHERE campaign_id = 1"
    ).fetchone()[0]
    assert revision == 2

    conn.execute("PRAGMA user_version = 21")
    conn.close()


def test_migration_022_creates_durable_turn_resolution_table():
    conn = create_version_20_database()
    migration_021(conn)
    migration_022(conn)

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(turn_resolutions)")
    }
    assert {
        "id", "campaign_id", "idempotency_key", "request_fingerprint",
        "lifecycle_state", "context_revision", "proposal_json",
        "attempt_count", "lease_token", "lease_expires_at",
        "committed_at", "completed_at",
    } <= columns

    indexes = {
        row["name"]
        for row in conn.execute("PRAGMA index_list(turn_resolutions)")
    }
    assert "idx_turn_resolutions_campaign_state" in indexes
    assert "idx_turn_resolutions_expired_lease" in indexes
    conn.close()


def test_migration_022_enforces_campaign_scoped_idempotency():
    import pytest

    conn = create_version_20_database()
    migration_021(conn)
    migration_022(conn)

    values = (1, "open door", "native", "req-1", "sha256:a")
    conn.execute(
        """
        INSERT INTO turn_resolutions (
            campaign_id, player_input, adapter_namespace,
            idempotency_key, request_fingerprint
        ) VALUES (?, ?, ?, ?, ?)
        """,
        values,
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO turn_resolutions (
                campaign_id, player_input, adapter_namespace,
                idempotency_key, request_fingerprint
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (1, "open door differently", "native", "req-1", "sha256:b"),
        )

    conn.execute("INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')")
    conn.execute(
        """
        INSERT INTO turn_resolutions (
            campaign_id, player_input, adapter_namespace,
            idempotency_key, request_fingerprint
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (2, "open door", "native", "req-1", "sha256:a"),
    )
    conn.close()


def test_migration_022_guards_invalid_lifecycle_transitions():
    import pytest

    conn = create_version_20_database()
    migration_021(conn)
    migration_022(conn)
    cursor = conn.execute(
        """
        INSERT INTO turn_resolutions (
            campaign_id, player_input, adapter_namespace,
            idempotency_key, request_fingerprint
        ) VALUES (1, 'look around', 'native', 'req-2', 'sha256:c')
        """
    )
    resolution_id = cursor.lastrowid

    with pytest.raises(sqlite3.IntegrityError, match="invalid"):
        conn.execute(
            "UPDATE turn_resolutions SET lifecycle_state='completed' WHERE id=?",
            (resolution_id,),
        )
    conn.close()


def test_migration_022_rejects_cross_campaign_turn_link():
    import pytest

    conn = create_version_20_database()
    migration_021(conn)
    migration_022(conn)

    conn.execute("INSERT INTO campaign (id, name) VALUES (2, 'Campaign 2')")
    session_id = conn.execute(
        "INSERT INTO sessions (number, title, campaign_id) VALUES (1, 'S1', 1)"
    ).lastrowid
    turn_id = conn.execute(
        """
        INSERT INTO turns (
            session_id, player_input, narrative, campaign_id
        ) VALUES (?, 'input', 'narrative', 1)
        """,
        (session_id,),
    ).lastrowid

    with pytest.raises(sqlite3.IntegrityError, match="same campaign"):
        conn.execute(
            """
            INSERT INTO turn_resolutions (
                campaign_id, turn_id, player_input, adapter_namespace,
                idempotency_key, request_fingerprint
            ) VALUES (2, ?, 'input', 'native', 'req-3', 'sha256:d')
            """,
            (turn_id,),
        )
    conn.close()


def test_migration_022_lifecycle_checks_and_revision_isolation():
    import pytest

    conn = create_version_20_database()
    migration_021(conn)
    migration_022(conn)
    revision_before = conn.execute(
        "SELECT revision FROM campaign_state_versions WHERE campaign_id = 1"
    ).fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO turn_resolutions (
                campaign_id, player_input, adapter_namespace,
                idempotency_key, request_fingerprint, lifecycle_state
            ) VALUES (1, 'input', 'native', 'bad-prepared', 'sha256:x', 'prepared')
            """
        )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO turn_resolutions (
                campaign_id, player_input, adapter_namespace,
                idempotency_key, request_fingerprint, lifecycle_state,
                attempt_count
            ) VALUES (1, 'input', 'native', 'bad-planning', 'sha256:y', 'planning', 1)
            """
        )

    cursor = conn.execute(
        """
        INSERT INTO turn_resolutions (
            campaign_id, player_input, adapter_namespace,
            idempotency_key, request_fingerprint
        ) VALUES (1, 'input', 'native', 'valid', 'sha256:z')
        """
    )
    conn.execute(
        "UPDATE turn_resolutions SET last_error_code='provider_timeout' WHERE id=?",
        (cursor.lastrowid,),
    )
    revision_after = conn.execute(
        "SELECT revision FROM campaign_state_versions WHERE campaign_id = 1"
    ).fetchone()[0]
    assert revision_after == revision_before
    conn.close()


def test_run_migrations_upgrades_version_21_to_latest_schema():
    conn = create_version_20_database()
    migration_021(conn)
    conn.execute("PRAGMA user_version = 21")

    run_migrations(conn)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='turn_resolutions'"
    ).fetchone() is not None
    conn.close()


def test_migration_023_adds_resulting_revision_to_turn_resolutions():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(turn_resolutions)").fetchall()
    }

    assert "resulting_revision" in columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    conn.close()


def test_migration_024_adds_campaign_scoped_creature_state_and_revision_triggers():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("DROP TABLE creature_states")
    conn.execute("PRAGMA user_version = 23")

    run_migrations(conn)

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(creature_states)")
    }
    assert {
        "entity_id", "campaign_id", "current_hp", "max_hp",
        "armor_class", "strength", "dexterity", "constitution",
        "intelligence", "wisdom", "charisma", "proficiency_bonus",
    } <= columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION

    entity_id = conn.execute(
        "INSERT INTO entities (name, entity_type, campaign_id) VALUES ('Goblin', 'creature', 1)"
    ).lastrowid
    before = conn.execute(
        "SELECT revision FROM campaign_state_versions WHERE campaign_id = 1"
    ).fetchone()["revision"]
    conn.execute(
        """
        INSERT INTO creature_states (
            entity_id, campaign_id, current_hp, max_hp, armor_class
        ) VALUES (?, 1, 7, 7, 15)
        """,
        (entity_id,),
    )
    after = conn.execute(
        "SELECT revision FROM campaign_state_versions WHERE campaign_id = 1"
    ).fetchone()["revision"]
    assert after == before + 1

    conn.execute("INSERT INTO campaign (id, name) VALUES (2, 'Other')")
    other_entity_id = conn.execute(
        "INSERT INTO entities (name, entity_type, campaign_id) VALUES ('Orc', 'creature', 2)"
    ).lastrowid
    import pytest
    with pytest.raises(sqlite3.IntegrityError, match="same campaign"):
        conn.execute(
            """
            INSERT INTO creature_states (
                entity_id, campaign_id, current_hp, max_hp, armor_class
            ) VALUES (?, 1, 10, 10, 13)
            """,
            (other_entity_id,),
        )
    conn.close()



def test_migration_025_adds_encounter_scoped_effect_timer_columns():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(persistent_effect_timers)")
    }
    assert {
        "encounter_id", "duration_rounds", "expires_at_round",
        "duration_turns", "expires_at_turn", "expired_at_round", "expired_at_turn",
    } <= columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    trigger = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_effect_timer_encounter_campaign'"
    ).fetchone()
    assert trigger is not None
    conn.close()



def test_migration_026_creates_slot_projection_and_migrates_legacy_weapon():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(equipped_items)")
    }
    assert {
        "campaign_id", "character_entity_id", "slot", "item_instance_id"
    } <= columns
    item_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(items)")
    }
    assert "equipment_slot" in item_columns

    conn.execute(
        "INSERT INTO entities (id, name, entity_type, campaign_id) VALUES (1, 'Hero', 'character', 1)"
    )
    conn.execute(
        "INSERT INTO character_states (entity_id, campaign_id) VALUES (1, 1)"
    )
    conn.execute(
        "INSERT INTO items (id, name, weapon_key, campaign_id) VALUES (1, 'Longsword', 'longsword', 1)"
    )
    conn.execute(
        "INSERT INTO item_instances (id, item_id, owner_id, campaign_id) VALUES (1, 1, 1, 1)"
    )
    conn.execute(
        "INSERT INTO equipped_weapons (campaign_id, character_entity_id, item_instance_id) VALUES (1, 1, 1)"
    )

    # Re-running the idempotent migration simulates upgrading a database
    # that already contains legacy equipped_weapons rows.
    migration_026(conn)
    row = conn.execute(
        "SELECT slot, item_instance_id FROM equipped_items WHERE campaign_id=1 AND character_entity_id=1"
    ).fetchone()
    assert tuple(row) == ("main_hand", 1)
    assert conn.execute(
        "SELECT equipment_slot FROM items WHERE id=1"
    ).fetchone()[0] == "main_hand"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    conn.close()


def test_migration_027_adds_typed_armor_metadata_and_slot_guards():
    import pytest

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()
    }
    assert "armor_key" in columns

    with pytest.raises(sqlite3.IntegrityError, match="armor items require"):
        conn.execute("""
            INSERT INTO items (name, armor_key, equipment_slot, campaign_id)
            VALUES ('Mis-slotted shield', 'shield', 'body', 1)
        """)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO items (name, weapon_key, armor_key, equipment_slot, campaign_id)
            VALUES ('Weapon armor hybrid', 'longsword', 'leather', 'body', 1)
        """)

    conn.execute("""
        INSERT INTO items (name, armor_key, equipment_slot, campaign_id)
        VALUES ('Leather armor', 'leather', 'body', 1)
    """)
    conn.execute("""
        INSERT INTO items (name, armor_key, equipment_slot, campaign_id)
        VALUES ('Shield', 'shield', 'off_hand', 1)
    """)
    conn.close()


def test_migration_028_persists_armor_proficiencies_with_empty_legacy_default():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(character_states)")
    }
    assert "armor_proficiencies" in columns
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    conn.execute("""
        INSERT INTO entities (id, name, entity_type, campaign_id)
        VALUES (1, 'Legacy hero', 'player_character', 1)
    """)
    conn.execute("""
        INSERT INTO character_states (entity_id, campaign_id)
        VALUES (1, 1)
    """)
    assert conn.execute(
        "SELECT armor_proficiencies FROM character_states WHERE entity_id=1"
    ).fetchone()[0] == "[]"
    conn.close()


def test_migration_029_archives_turn_snapshots_and_removes_runtime_column():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER NOT NULL,
            player_input TEXT NOT NULL,
            snapshot TEXT
        )
    """)
    conn.execute(
        "INSERT INTO turns (id, campaign_id, player_input, snapshot) VALUES (1, 7, 'Exploro', ?)",
        ('{"entities": [{"id": 12}]}',),
    )
    conn.execute(
        "INSERT INTO turns (id, campaign_id, player_input, snapshot) VALUES (2, 7, 'Espero', NULL)"
    )

    migration_029(conn)

    turn_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(turns)")
    }
    assert "snapshot" not in turn_columns

    archived = conn.execute(
        "SELECT turn_id, campaign_id, snapshot_json FROM turn_snapshot_archive"
    ).fetchall()
    assert [tuple(row) for row in archived] == [
        (1, 7, '{"entities": [{"id": 12}]}')
    ]

    # The migration is safe to re-run and never duplicates archived payloads.
    migration_029(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM turn_snapshot_archive"
    ).fetchone()[0] == 1
    conn.close()

def test_migration_registry_is_contiguous_named_and_documented():
    assert tuple(item.version for item in MIGRATIONS) == tuple(
        range(1, CURRENT_VERSION + 1)
    )
    assert len(MIGRATIONS) == CURRENT_VERSION
    assert all(item.name == item.apply.__name__ for item in MIGRATIONS)
    assert all(item.description.strip() for item in MIGRATIONS)


def test_run_migrations_uses_registry_and_leaves_current_database_unchanged():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    run_migrations(conn)
    schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
    table_count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
    ).fetchone()[0]

    run_migrations(conn)

    assert schema_version == CURRENT_VERSION
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CURRENT_VERSION
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
    ).fetchone()[0] == table_count
    conn.close()


def test_migration_030_backfills_class_hit_dice_without_losing_character_state():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    from migrations import MIGRATIONS

    for definition in MIGRATIONS[:-2]:
        definition.apply(conn)

    for name, class_name in (
        ("Wizard", "Wizard"),
        ("Barbarian", "Barbarian"),
        ("Fighter", "Fighter"),
        ("Unknown", "Homebrew class"),
    ):
        entity_id = conn.execute(
            """
            INSERT INTO entities (name, entity_type, campaign_id)
            VALUES (?, 'player_character', 1)
            """,
            (name,),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO character_states (
                entity_id, campaign_id, class_name, current_hp, max_hp
            ) VALUES (?, 1, ?, 7, 12)
            """,
            (entity_id, class_name),
        )

    migration_030(conn)

    rows = conn.execute(
        """
        SELECT entity_id, class_name, current_hp, max_hp, hit_die_sides,
               hit_dice_used, last_long_rest_elapsed_minutes
        FROM character_states
        ORDER BY entity_id
        """
    ).fetchall()
    values = {row["class_name"]: row for row in rows}

    assert values["Wizard"]["hit_die_sides"] == 6
    assert values["Barbarian"]["hit_die_sides"] == 12
    assert values["Fighter"]["hit_die_sides"] == 10
    assert values["Homebrew class"]["hit_die_sides"] == 8
    assert all(row["hit_dice_used"] == 0 for row in rows)
    assert all(row["last_long_rest_elapsed_minutes"] is None for row in rows)
    assert all((row["current_hp"], row["max_hp"]) == (7, 12) for row in rows)

    # Re-running the migration must not reset per-character die choices or use.
    wizard_id = values["Wizard"]["entity_id"]
    conn.execute(
        """
        UPDATE character_states
        SET hit_die_sides = 10,
            hit_dice_used = 1,
            last_long_rest_elapsed_minutes = 120
        WHERE entity_id = ?
        """,
        (wizard_id,),
    )
    migration_030(conn)
    persisted = conn.execute(
        """
        SELECT hit_die_sides, hit_dice_used, last_long_rest_elapsed_minutes
        FROM character_states WHERE entity_id = ?
        """,
        (wizard_id,),
    ).fetchone()
    assert tuple(persisted) == (10, 1, 120)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_migration_031_persists_entity_aliases_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for definition in MIGRATIONS[:-1]:
        definition.apply(conn)

    entity_id = conn.execute(
        """
        INSERT INTO entities (name, entity_type, description, campaign_id)
        VALUES ('Aldric', 'npc', 'Tabernero de la posada.', 1)
        """
    ).lastrowid
    migration_031(conn)

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(entities)")
    }
    assert "aliases" in columns
    row = conn.execute(
        "SELECT name, description, aliases FROM entities WHERE id = ?",
        (entity_id,),
    ).fetchone()
    assert tuple(row) == ("Aldric", "Tabernero de la posada.", "[]")

    conn.execute(
        "UPDATE entities SET aliases = ? WHERE id = ?",
        ('["el tabernero","el posadero"]', entity_id),
    )
    migration_031(conn)
    aliases = conn.execute(
        "SELECT aliases FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()["aliases"]
    assert aliases == '["el tabernero","el posadero"]'
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()

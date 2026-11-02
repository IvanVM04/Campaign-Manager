import sqlite3

CURRENT_VERSION = 11

def migration_001(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ============================================================
        -- CAMPAIGN
        -- ============================================================

        CREATE TABLE IF NOT EXISTS campaign (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL,
            system TEXT NOT NULL DEFAULT 'D&D 5e 2014',
            tone TEXT,
            current_location_id INTEGER,
            current_session_id INTEGER,
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- ============================================================
        -- ENTITIES
        -- ============================================================

        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_entities_name
            ON entities(name);

        CREATE INDEX IF NOT EXISTS idx_entities_type
            ON entities(entity_type);

        -- ============================================================
        -- ITEMS
        -- ============================================================

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            significance TEXT DEFAULT '',
            unique_item INTEGER NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_items_name
            ON items(name);

        -- ============================================================
        -- ITEM INSTANCES
        -- ============================================================

        CREATE TABLE IF NOT EXISTS item_instances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            instance_number INTEGER NOT NULL DEFAULT 1,
            owner_id INTEGER,
            location_id INTEGER,
            condition TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (item_id)
                REFERENCES items(id)
                ON DELETE CASCADE,

            FOREIGN KEY (owner_id)
                REFERENCES entities(id)
                ON DELETE SET NULL,

            FOREIGN KEY (location_id)
                REFERENCES entities(id)
                ON DELETE SET NULL,

            UNIQUE(item_id, instance_number)
        );

        CREATE INDEX IF NOT EXISTS idx_item_instances_item
            ON item_instances(item_id);

        CREATE INDEX IF NOT EXISTS idx_item_instances_owner
            ON item_instances(owner_id);

        CREATE INDEX IF NOT EXISTS idx_item_instances_location
            ON item_instances(location_id);

        -- ============================================================
        -- RESOURCES
        -- ============================================================

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            resource_type TEXT NOT NULL DEFAULT 'generic',
            unit TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_resources_name
            ON resources(name);

        -- ============================================================
        -- RESOURCE BALANCES
        -- ============================================================

        CREATE TABLE IF NOT EXISTS resource_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resource_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (resource_id)
                REFERENCES resources(id)
                ON DELETE CASCADE,

            FOREIGN KEY (owner_id)
                REFERENCES entities(id)
                ON DELETE CASCADE,

            UNIQUE(resource_id, owner_id)
        );

        CREATE INDEX IF NOT EXISTS idx_resource_balances_resource
            ON resource_balances(resource_id);

        CREATE INDEX IF NOT EXISTS idx_resource_balances_owner
            ON resource_balances(owner_id);

        -- ============================================================
        -- RELATIONS
        -- ============================================================

        CREATE TABLE IF NOT EXISTS relations (
            id TEXT PRIMARY KEY,
            subject_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            metadata TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (subject_id)
                REFERENCES entities(id)
                ON DELETE CASCADE,

            FOREIGN KEY (target_id)
                REFERENCES entities(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_relations_subject
            ON relations(subject_id);

        CREATE INDEX IF NOT EXISTS idx_relations_target
            ON relations(target_id);

        CREATE INDEX IF NOT EXISTS idx_relations_type
            ON relations(relation_type);

        -- ============================================================
        -- EVENTS
        -- ============================================================

        CREATE TABLE IF NOT EXISTS world_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            consequences TEXT DEFAULT '',
            session_id INTEGER,
            secret INTEGER NOT NULL DEFAULT 0,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_world_events_session
            ON world_events(session_id);

        CREATE INDEX IF NOT EXISTS idx_world_events_type
            ON world_events(event_type);

        -- ============================================================
        -- SESSIONS
        -- ============================================================

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number INTEGER NOT NULL UNIQUE,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            start_location TEXT DEFAULT '',
            end_location TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_number
            ON sessions(number);
        """
    )


def migration_002(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ============================================================
        -- REMOVE LEGACY TABLES
        -- ============================================================

        DROP TABLE IF EXISTS characters;
        DROP TABLE IF EXISTS events;
        DROP TABLE IF EXISTS factions;
        DROP TABLE IF EXISTS locations;
        DROP TABLE IF EXISTS quests;
        DROP TABLE IF EXISTS relationships;
        """
    )


def migration_003(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_states (
            entity_id INTEGER PRIMARY KEY,
            level INTEGER NOT NULL DEFAULT 1,
            class_name TEXT,
            current_hp INTEGER NOT NULL DEFAULT 0,
            max_hp INTEGER NOT NULL DEFAULT 0,
            armor_class INTEGER NOT NULL DEFAULT 10,
            strength INTEGER NOT NULL DEFAULT 10,
            dexterity INTEGER NOT NULL DEFAULT 10,
            constitution INTEGER NOT NULL DEFAULT 10,
            intelligence INTEGER NOT NULL DEFAULT 10,
            wisdom INTEGER NOT NULL DEFAULT 10,
            charisma INTEGER NOT NULL DEFAULT 10,
            proficiency_bonus INTEGER NOT NULL DEFAULT 2,
            metadata TEXT NOT NULL DEFAULT '{}',

            FOREIGN KEY (entity_id)
                REFERENCES entities(id)
                ON DELETE CASCADE
        );
        """
    )


def migration_004(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        ALTER TABLE campaign
        ADD COLUMN active_character_id INTEGER
        """
    )

def migration_005(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO campaign (
            id,
            name,
            system,
            tone,
            current_location_id,
            current_session_id,
            active_character_id,
            summary
        )
        VALUES (
            1,
            'Nueva campaña',
            'D&D 5e 2014',
            '',
            NULL,
            NULL,
            NULL,
            ''
        )
        """
    )

def migration_006(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            session_id INTEGER,

            player_input TEXT NOT NULL,
            narrative TEXT NOT NULL,

            operation_count INTEGER NOT NULL DEFAULT 0,
            successful_operation_count INTEGER NOT NULL DEFAULT 0,
            failed_operation_count INTEGER NOT NULL DEFAULT 0,

            all_operations_succeeded INTEGER NOT NULL DEFAULT 1,
            world_changed INTEGER NOT NULL DEFAULT 0,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (session_id)
                REFERENCES sessions(id)
                ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_turns_session
            ON turns(session_id);

        CREATE INDEX IF NOT EXISTS idx_turns_created_at
            ON turns(created_at);
        """
    )

def migration_007(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        ALTER TABLE turns
        ADD COLUMN external_turn_id TEXT;

        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_turns_external_turn_id
        ON turns(external_turn_id)
        WHERE external_turn_id IS NOT NULL;
        """
    )

def migration_008(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ============================================================
        -- TURN VERSIONING / RECONCILIATION
        -- ============================================================

        ALTER TABLE turns
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

        ALTER TABLE turns
            ADD COLUMN status TEXT NOT NULL DEFAULT 'active';

        ALTER TABLE turns
            ADD COLUMN snapshot TEXT;

        CREATE INDEX IF NOT EXISTS idx_turns_external_turn_id
            ON turns(external_turn_id);

        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_external_turn_version
            ON turns(external_turn_id, version)
            WHERE external_turn_id IS NOT NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_active_external_turn
            ON turns(external_turn_id)
            WHERE external_turn_id IS NOT NULL
              AND status = 'active';
        """
    )

def migration_009(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ============================================================
        -- FIX TURN VERSIONING
        -- ============================================================

        DROP INDEX IF EXISTS idx_turns_external_turn_id;

        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_external_turn_version
            ON turns(external_turn_id, version)
            WHERE external_turn_id IS NOT NULL;

        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_active_external_turn
            ON turns(external_turn_id)
            WHERE external_turn_id IS NOT NULL
              AND status = 'active';
        """
    )

def migration_010(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- ============================================================
        -- ALLOW RETRIES OF FAILED TURN VERSIONS
        -- ============================================================

        DROP INDEX IF EXISTS idx_turns_external_turn_version;

        CREATE INDEX IF NOT EXISTS
            idx_turns_external_turn_version
            ON turns(external_turn_id, version);

        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_active_external_turn
            ON turns(external_turn_id)
            WHERE external_turn_id IS NOT NULL
              AND status = 'active';
        """
    )

def migration_011(conn: sqlite3.Connection) -> None:
    """
    Prepara el esquema para soportar varias campañas.

    Todos los datos existentes se asignan a la campaña 1.
    Esta migración no cambia todavía los repositorios: la aplicación
    seguirá utilizando el runtime antiguo hasta completar esa fase.
    """

    # ------------------------------------------------------------
    # CAMPAIGN: eliminar la restricción CHECK (id = 1)
    # ------------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE campaign_new (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            system TEXT NOT NULL DEFAULT 'D&D 5e 2014',
            tone TEXT,
            current_location_id INTEGER,
            current_session_id INTEGER,
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            active_character_id INTEGER
        )
        """
    )

    conn.execute(
        """
        INSERT INTO campaign_new (
            id,
            name,
            system,
            tone,
            current_location_id,
            current_session_id,
            summary,
            created_at,
            updated_at,
            active_character_id
        )
        SELECT
            id,
            name,
            system,
            tone,
            current_location_id,
            current_session_id,
            summary,
            created_at,
            updated_at,
            active_character_id
        FROM campaign
        """
    )

    conn.execute("DROP TABLE campaign")
    conn.execute("ALTER TABLE campaign_new RENAME TO campaign")

    # ------------------------------------------------------------
    # AÑADIR campaign_id A LAS TABLAS DE DATOS
    # ------------------------------------------------------------

    campaign_tables = (
        "entities",
        "items",
        "item_instances",
        "resources",
        "resource_balances",
        "relations",
        "world_events",
        "character_states",
        "sessions",
        "turns",
    )

    for table in campaign_tables:
        columns = {
            row[1]
            for row in conn.execute(
                f'PRAGMA table_info("{table}")'
            ).fetchall()
        }

        if "campaign_id" not in columns:
            conn.execute(
                f"""
                ALTER TABLE "{table}"
                ADD COLUMN campaign_id INTEGER NOT NULL DEFAULT 1
                """
            )

    # ------------------------------------------------------------
    # ÍNDICES DE CAMPAÑA
    # ------------------------------------------------------------

    for table in campaign_tables:
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS
                idx_{table}_campaign
            ON "{table}" (campaign_id)
            """
        )

    # ------------------------------------------------------------
    # TURNOS: external_turn_id deja de ser globalmente único.
    # La unicidad de la versión y del turno activo se limita
    # a una campaña.
    # ------------------------------------------------------------

    conn.execute(
        "DROP INDEX IF EXISTS idx_turns_active_external_turn"
    )

    conn.execute(
        "DROP INDEX IF EXISTS idx_turns_external_turn_version"
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS
            idx_turns_campaign_external_version
        ON turns (
            campaign_id,
            external_turn_id,
            version
        )
        WHERE external_turn_id IS NOT NULL
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            idx_turns_campaign_active_external
        ON turns (
            campaign_id,
            external_turn_id
        )
        WHERE external_turn_id IS NOT NULL
          AND status = 'active'
        """
    )

def run_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute(
        "PRAGMA user_version"
    ).fetchone()[0]

    if version < 1:
        migration_001(conn)
        conn.execute("PRAGMA user_version = 1")
        version = 1

    if version < 2:
        migration_002(conn)
        conn.execute("PRAGMA user_version = 2")
        version = 2

    if version < 3:
        migration_003(conn)
        conn.execute("PRAGMA user_version = 3")
        version = 3

    if version < 4:
        migration_004(conn)
        conn.execute("PRAGMA user_version = 4")
        version = 4

    if version < 5:
        migration_005(conn)
        conn.execute("PRAGMA user_version = 5")
        version = 5

    if version < 6:
        migration_006(conn)
        conn.execute("PRAGMA user_version = 6")
        version = 6

    if version < 7:
        migration_007(conn)
        conn.execute("PRAGMA user_version = 7")
        version = 7

    if version < 8:
        migration_008(conn)
        conn.execute("PRAGMA user_version = 8")
        version = 8

    if version < 9:
        migration_009(conn)
        conn.execute("PRAGMA user_version = 9")
        version = 9

    if version < 10:
        migration_010(conn)
        conn.execute("PRAGMA user_version = 10")
        version = 10

    if version < 11:
        migration_011(conn)
        conn.execute("PRAGMA user_version = 11")
        version = 11

    if version != CURRENT_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is not supported. "
            f"Expected {CURRENT_VERSION}."
        )

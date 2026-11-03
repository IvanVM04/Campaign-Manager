import sqlite3

CURRENT_VERSION = 15

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

def migration_012(conn: sqlite3.Connection) -> None:
    """
    Refuerza el aislamiento entre campañas.

    - Permite repetir nombres de items y resources en campañas distintas.
    - Permite repetir números de sesión en campañas distintas.
    - Conserva los IDs globales existentes.
    - Impide referencias entre registros de campañas diferentes.
    - Comprueba que cada registro pertenece a una campaña existente.
    - Impide cambiar un registro de campaña una vez creado.
    """

    # ------------------------------------------------------------
    # 1. RECONSTRUIR ITEMS, RESOURCES Y SESSIONS
    # ------------------------------------------------------------
    # Es necesario confirmar cualquier transacción previa antes de
    # cambiar PRAGMA foreign_keys: SQLite ignora ese cambio dentro
    # de una transacción activa.

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        # -------------------------
        # ITEMS
        # -------------------------

        conn.execute("""
            CREATE TABLE items_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                significance TEXT DEFAULT '',
                unique_item INTEGER NOT NULL DEFAULT 0,
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                campaign_id INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            INSERT INTO items_new (
                id, name, description, significance, unique_item,
                notes, created_at, updated_at, campaign_id
            )
            SELECT
                id, name, description, significance, unique_item,
                notes, created_at, updated_at, campaign_id
            FROM items
        """)

        conn.execute("DROP TABLE items")
        conn.execute("ALTER TABLE items_new RENAME TO items")

        conn.execute("""
            CREATE INDEX idx_items_name ON items(name)
        """)
        conn.execute("""
            CREATE INDEX idx_items_campaign ON items(campaign_id)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_items_campaign_name
            ON items(campaign_id, name)
        """)

        # -------------------------
        # RESOURCES
        # -------------------------

        conn.execute("""
            CREATE TABLE resources_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                resource_type TEXT NOT NULL DEFAULT 'generic',
                unit TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                campaign_id INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            INSERT INTO resources_new (
                id, name, resource_type, unit, notes,
                created_at, updated_at, campaign_id
            )
            SELECT
                id, name, resource_type, unit, notes,
                created_at, updated_at, campaign_id
            FROM resources
        """)

        conn.execute("DROP TABLE resources")
        conn.execute("ALTER TABLE resources_new RENAME TO resources")

        conn.execute("""
            CREATE INDEX idx_resources_name ON resources(name)
        """)
        conn.execute("""
            CREATE INDEX idx_resources_campaign ON resources(campaign_id)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_resources_campaign_name
            ON resources(campaign_id, name)
        """)

        # -------------------------
        # SESSIONS
        # -------------------------
        # Antes number era UNIQUE globalmente.
        # Ahora solo debe ser único dentro de cada campaña.

        conn.execute("""
            CREATE TABLE sessions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER NOT NULL,
                title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                start_location TEXT DEFAULT '',
                end_location TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                campaign_id INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            INSERT INTO sessions_new (
                id, number, title, summary,
                start_location, end_location, notes,
                created_at, updated_at, campaign_id
            )
            SELECT
                id, number, title, summary,
                start_location, end_location, notes,
                created_at, updated_at, campaign_id
            FROM sessions
        """)

        conn.execute("DROP TABLE sessions")
        conn.execute("ALTER TABLE sessions_new RENAME TO sessions")

        conn.execute("""
            CREATE INDEX idx_sessions_number ON sessions(number)
        """)
        conn.execute("""
            CREATE INDEX idx_sessions_campaign ON sessions(campaign_id)
        """)
        conn.execute("""
            CREATE UNIQUE INDEX idx_sessions_campaign_number
            ON sessions(campaign_id, number)
        """)

        # Confirmamos la reconstrucción de las tres tablas.
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------
    # 2. CREAR TRIGGERS DE VALIDACIÓN
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

    conn.execute("BEGIN")

    try:
        # -------------------------
        # 2.1. LA CAMPAÑA DEBE EXISTIR
        # -------------------------

        for table in campaign_tables:
            for operation in ("INSERT", "UPDATE"):
                trigger_name = (
                    f"trg_{table}_campaign_{operation.lower()}"
                )

                conn.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    BEFORE {operation} ON {table}
                    FOR EACH ROW
                    WHEN NOT EXISTS (
                        SELECT 1
                        FROM campaign
                        WHERE id = NEW.campaign_id
                    )
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'campaign_id does not exist'
                        );
                    END
                """)

        # -------------------------
        # 2.2. CAMPAIGN_ID ES INMUTABLE
        # -------------------------
        # Evita mover un registro a otra campaña y dejar referencias
        # que terminen conectando datos de campañas diferentes.

        for table in campaign_tables:
            trigger_name = f"trg_{table}_campaign_immutable"

            conn.execute(f"""
                CREATE TRIGGER IF NOT EXISTS {trigger_name}
                BEFORE UPDATE OF campaign_id ON {table}
                FOR EACH ROW
                WHEN NEW.campaign_id != OLD.campaign_id
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'campaign_id is immutable'
                    );
                END
            """)

        # -------------------------
        # 2.3. REFERENCIAS ENTRE CAMPAÑAS
        # -------------------------

        references = (
            # item_instances
            ("item_instances", "item_id", "items", "id"),
            ("item_instances", "owner_id", "entities", "id"),
            ("item_instances", "location_id", "entities", "id"),

            # resource_balances
            ("resource_balances", "resource_id", "resources", "id"),
            ("resource_balances", "owner_id", "entities", "id"),

            # relations
            ("relations", "subject_id", "entities", "id"),
            ("relations", "target_id", "entities", "id"),

            # character_states
            ("character_states", "entity_id", "entities", "id"),

            # world_events y turns
            ("world_events", "session_id", "sessions", "id"),
            ("turns", "session_id", "sessions", "id"),
        )

        for child_table, child_column, parent_table, parent_column in references:
            for operation in ("INSERT", "UPDATE"):
                trigger_name = (
                    f"trg_{child_table}_{child_column}_campaign_"
                    f"{operation.lower()}"
                )

                conn.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    BEFORE {operation} ON {child_table}
                    FOR EACH ROW
                    WHEN NEW.{child_column} IS NOT NULL
                     AND NOT EXISTS (
                        SELECT 1
                        FROM {parent_table}
                        WHERE {parent_table}.{parent_column}
                            = NEW.{child_column}
                          AND {parent_table}.campaign_id
                            = NEW.campaign_id
                    )
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'cross-campaign reference is not allowed'
                        );
                    END
                """)

        # -------------------------
        # 2.4. COMPROBAR FOREIGN KEYS
        # -------------------------

        violations = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if violations:
            raise RuntimeError(
                "Migration 012 produced foreign key violations: "
                f"{violations}"
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise


def migration_013(conn: sqlite3.Connection) -> None:
    """
    Impide que una campaña apunte a ubicaciones, sesiones o personajes
    pertenecientes a otra campaña.

    campaign.current_location_id y current_session_id son referencias
    de estado; active_character_id apunta a character_states.entity_id.
    """
    references = (
        (
            "current_location_id",
            "entities",
            "id",
        ),
        (
            "current_session_id",
            "sessions",
            "id",
        ),
        (
            "active_character_id",
            "character_states",
            "entity_id",
        ),
    )

    conn.execute("BEGIN")

    try:
        for column, table, target_column in references:
            for operation in ("INSERT", "UPDATE"):
                trigger_name = (
                    f"trg_campaign_{column}_scope_"
                    f"{operation.lower()}"
                )

                conn.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS {trigger_name}
                    BEFORE {operation} ON campaign
                    FOR EACH ROW
                    WHEN NEW.{column} IS NOT NULL
                     AND NOT EXISTS (
                        SELECT 1
                        FROM {table}
                        WHERE {table}.{target_column} = NEW.{column}
                          AND {table}.campaign_id = NEW.id
                    )
                    BEGIN
                        SELECT RAISE(
                            ABORT,
                            'campaign reference must belong to same campaign'
                        );
                    END
                """)

        violations = []
        for column, table, target_column in references:
            violations.extend(
                conn.execute(
                    f"""
                    SELECT campaign.id, campaign.{column}
                    FROM campaign
                    WHERE campaign.{column} IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1
                        FROM {table}
                        WHERE {table}.{target_column} = campaign.{column}
                          AND {table}.campaign_id = campaign.id
                      )
                    """
                ).fetchall()
            )

        if violations:
            raise RuntimeError(
                "Migration 013 found cross-campaign campaign references: "
                f"{violations}"
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise



def migration_014(conn: sqlite3.Connection) -> None:
    """
    Limpia los punteros de campaña cuando se elimina su registro objetivo.

    Evita que current_location_id, current_session_id o
    active_character_id queden apuntando a registros inexistentes.
    """
    conn.execute("BEGIN")

    try:
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS
                trg_campaign_clear_location_after_entity_delete
            AFTER DELETE ON entities
            FOR EACH ROW
            BEGIN
                UPDATE campaign
                SET current_location_id = NULL
                WHERE id = OLD.campaign_id
                  AND current_location_id = OLD.id;
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS
                trg_campaign_clear_active_character_after_state_delete
            AFTER DELETE ON character_states
            FOR EACH ROW
            BEGIN
                UPDATE campaign
                SET active_character_id = NULL
                WHERE id = OLD.campaign_id
                  AND active_character_id = OLD.entity_id;
            END
        """)

        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS
                trg_campaign_clear_session_after_session_delete
            AFTER DELETE ON sessions
            FOR EACH ROW
            BEGIN
                UPDATE campaign
                SET current_session_id = NULL
                WHERE id = OLD.campaign_id
                  AND current_session_id = OLD.id;
            END
        """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise



def migration_015(conn: sqlite3.Connection) -> None:
    """Persist D&D 5e skill, expertise and saving-throw proficiencies."""
    conn.execute("BEGIN")
    try:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(character_states)")
        }
        additions = {
            "skill_proficiencies": "TEXT NOT NULL DEFAULT '[]'",
            "skill_expertise": "TEXT NOT NULL DEFAULT '[]'",
            "saving_throw_proficiencies": "TEXT NOT NULL DEFAULT '[]'",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(
                    f"ALTER TABLE character_states ADD COLUMN {name} {definition}"
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


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

    if version < 12:
        migration_012(conn)
        conn.execute("PRAGMA user_version = 12")
        version = 12

    if version < 13:
        migration_013(conn)
        conn.execute("PRAGMA user_version = 13")
        version = 13

    if version < 14:
        migration_014(conn)
        conn.execute("PRAGMA user_version = 14")
        version = 14

    if version < 15:
        migration_015(conn)
        conn.execute("PRAGMA user_version = 15")
        version = 15

    if version != CURRENT_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is not supported. "
            f"Expected {CURRENT_VERSION}."
        )

import sqlite3

CURRENT_VERSION = 23

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

    if version < 16:
        migration_016(conn)
        conn.execute("PRAGMA user_version = 16")
        version = 16

    if version < 17:
        migration_017(conn)
        conn.execute("PRAGMA user_version = 17")
        version = 17

    if version < 18:
        migration_018(conn)
        conn.execute("PRAGMA user_version = 18")
        version = 18

    if version < 19:
        migration_019(conn)
        conn.execute("PRAGMA user_version = 19")
        version = 19

    if version < 20:
        migration_020(conn)
        conn.execute("PRAGMA user_version = 20")
        version = 20

    if version < 21:
        migration_021(conn)
        conn.execute("PRAGMA user_version = 21")
        version = 21

    if version < 22:
        migration_022(conn)
        conn.execute("PRAGMA user_version = 22")
        version = 22

    if version < 23:
        migration_023(conn)
        conn.execute("PRAGMA user_version = 23")
        version = 23

    if version != CURRENT_VERSION:
        raise RuntimeError(
            f"Database schema version {version} is not supported. "
            f"Expected {CURRENT_VERSION}."
        )



def migration_016(conn: sqlite3.Connection) -> None:
    """Persist typed combat encounter snapshots per campaign."""
    conn.execute("BEGIN")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS combat_encounters (
                encounter_id TEXT NOT NULL,
                campaign_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('preparing', 'active', 'completed')),
                round_number INTEGER NOT NULL CHECK (round_number >= 0),
                turn_index INTEGER NOT NULL CHECK (turn_index >= 0),
                initiative_order TEXT NOT NULL,
                combatants TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (encounter_id, campaign_id),
                FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_combat_encounters_campaign
            ON combat_encounters(campaign_id, created_at)
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise




def migration_017(conn: sqlite3.Connection) -> None:
    """Add weapon metadata, proficiencies and equipped item references."""
    conn.execute("BEGIN")
    try:
        item_columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        if "weapon_key" not in item_columns:
            conn.execute("ALTER TABLE items ADD COLUMN weapon_key TEXT")
        character_columns = {row["name"] for row in conn.execute("PRAGMA table_info(character_states)")}
        if "weapon_proficiencies" not in character_columns:
            conn.execute("ALTER TABLE character_states ADD COLUMN weapon_proficiencies TEXT NOT NULL DEFAULT '[]'")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS equipped_weapons (
                campaign_id INTEGER NOT NULL,
                character_entity_id INTEGER NOT NULL,
                item_instance_id INTEGER NOT NULL,
                PRIMARY KEY (campaign_id, character_entity_id),
                UNIQUE (campaign_id, item_instance_id),
                FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapons_validate_insert
            BEFORE INSERT ON equipped_weapons
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM character_states cs
                JOIN item_instances ii ON ii.id = NEW.item_instance_id
                    AND ii.campaign_id = NEW.campaign_id
                    AND ii.owner_id = NEW.character_entity_id AND ii.active = 1
                JOIN items i ON i.id = ii.item_id AND i.campaign_id = NEW.campaign_id
                WHERE cs.entity_id = NEW.character_entity_id
                    AND cs.campaign_id = NEW.campaign_id AND i.weapon_key IS NOT NULL
            )
            BEGIN SELECT RAISE(ABORT, 'equipped weapon must be owned by character in same campaign'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapons_validate_update
            BEFORE UPDATE ON equipped_weapons
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM character_states cs
                JOIN item_instances ii ON ii.id = NEW.item_instance_id
                    AND ii.campaign_id = NEW.campaign_id
                    AND ii.owner_id = NEW.character_entity_id AND ii.active = 1
                JOIN items i ON i.id = ii.item_id AND i.campaign_id = NEW.campaign_id
                WHERE cs.entity_id = NEW.character_entity_id
                    AND cs.campaign_id = NEW.campaign_id AND i.weapon_key IS NOT NULL
            )
            BEGIN SELECT RAISE(ABORT, 'equipped weapon must be owned by character in same campaign'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapon_owner_cleanup
            AFTER UPDATE OF owner_id, active ON item_instances
            FOR EACH ROW WHEN NEW.owner_id IS NULL OR NEW.owner_id != OLD.owner_id OR NEW.active = 0
            BEGIN
                DELETE FROM equipped_weapons
                WHERE campaign_id = OLD.campaign_id AND item_instance_id = OLD.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapon_definition_guard
            BEFORE UPDATE OF weapon_key ON items
            FOR EACH ROW WHEN NEW.weapon_key IS NULL AND EXISTS (
                SELECT 1 FROM item_instances ii
                JOIN equipped_weapons ew
                  ON ew.item_instance_id = ii.id AND ew.campaign_id = ii.campaign_id
                WHERE ii.item_id = OLD.id AND ii.campaign_id = OLD.campaign_id
            )
            BEGIN SELECT RAISE(ABORT, 'unequip weapon before removing its weapon definition'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapon_instance_guard
            BEFORE UPDATE OF item_id ON item_instances
            FOR EACH ROW WHEN EXISTS (
                SELECT 1 FROM equipped_weapons ew
                WHERE ew.campaign_id = OLD.campaign_id AND ew.item_instance_id = OLD.id
            )
            BEGIN SELECT RAISE(ABORT, 'unequip weapon before changing its item definition'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapon_instance_cleanup
            AFTER DELETE ON item_instances FOR EACH ROW BEGIN
                DELETE FROM equipped_weapons WHERE campaign_id = OLD.campaign_id
                    AND item_instance_id = OLD.id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapon_character_cleanup
            AFTER DELETE ON character_states FOR EACH ROW BEGIN
                DELETE FROM equipped_weapons WHERE campaign_id = OLD.campaign_id
                    AND character_entity_id = OLD.entity_id;
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapons_campaign_insert
            BEFORE INSERT ON equipped_weapons FOR EACH ROW
            WHEN NOT EXISTS (SELECT 1 FROM campaign WHERE id = NEW.campaign_id)
            BEGIN SELECT RAISE(ABORT, 'campaign_id does not exist'); END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_equipped_weapons_campaign_immutable
            BEFORE UPDATE OF campaign_id ON equipped_weapons FOR EACH ROW
            WHEN NEW.campaign_id != OLD.campaign_id
            BEGIN SELECT RAISE(ABORT, 'campaign_id is immutable'); END
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_equipped_weapons_item ON equipped_weapons(campaign_id, item_instance_id)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise



def migration_018(conn: sqlite3.Connection) -> None:
    """Persist campaign-entity effects independently from combat snapshots."""
    conn.execute("BEGIN")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS persistent_effects (
                id TEXT PRIMARY KEY,
                campaign_id INTEGER NOT NULL,
                entity_id INTEGER NOT NULL,
                effect_type TEXT NOT NULL
                    CHECK (effect_type IN ('condition', 'exhaustion', 'narrative')),
                effect_key TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source_type TEXT NOT NULL
                    CHECK (source_type IN (
                        'creature', 'item', 'spell', 'environment',
                        'narrative', 'system', 'unknown'
                    )),
                source_entity_id INTEGER,
                source_reference TEXT,
                duration_type TEXT NOT NULL
                    CHECK (duration_type IN ('permanent', 'conditional')),
                duration_condition TEXT,
                level INTEGER,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'removed')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                removed_at TEXT,
                CHECK (
                    (duration_type = 'permanent' AND duration_condition IS NULL)
                    OR
                    (duration_type = 'conditional'
                        AND duration_condition IS NOT NULL
                        AND length(trim(duration_condition)) > 0)
                ),
                CHECK (
                    (effect_type = 'condition'
                        AND effect_key IN (
                            'blinded', 'charmed', 'deafened', 'frightened',
                            'grappled', 'incapacitated', 'invisible',
                            'paralyzed', 'petrified', 'poisoned', 'prone',
                            'restrained', 'stunned', 'unconscious'
                        )
                        AND level IS NULL)
                    OR
                    (effect_type = 'exhaustion'
                        AND effect_key = 'exhaustion'
                        AND level IS NOT NULL
                        AND level BETWEEN 1 AND 6)
                    OR
                    (effect_type = 'narrative'
                        AND length(trim(effect_key)) BETWEEN 1 AND 80
                        AND level IS NULL)
                ),
                FOREIGN KEY (campaign_id)
                    REFERENCES campaign(id) ON DELETE CASCADE,
                FOREIGN KEY (entity_id)
                    REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY (source_entity_id)
                    REFERENCES entities(id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_persistent_effects_entity_status
            ON persistent_effects(campaign_id, entity_id, status, created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_persistent_effects_campaign_status
            ON persistent_effects(campaign_id, status, created_at)
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_campaign_insert
            BEFORE INSERT ON persistent_effects
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM campaign WHERE id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'campaign_id does not exist');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_campaign_immutable
            BEFORE UPDATE OF campaign_id ON persistent_effects
            FOR EACH ROW
            WHEN NEW.campaign_id != OLD.campaign_id
            BEGIN
                SELECT RAISE(ABORT, 'campaign_id is immutable');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_entity_scope_insert
            BEFORE INSERT ON persistent_effects
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM entities
                WHERE id = NEW.entity_id
                  AND campaign_id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'effect entity must belong to same campaign');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_entity_scope_update
            BEFORE UPDATE OF entity_id, campaign_id ON persistent_effects
            FOR EACH ROW
            WHEN NOT EXISTS (
                SELECT 1 FROM entities
                WHERE id = NEW.entity_id
                  AND campaign_id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'effect entity must belong to same campaign');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_source_scope_insert
            BEFORE INSERT ON persistent_effects
            FOR EACH ROW
            WHEN NEW.source_entity_id IS NOT NULL
             AND NOT EXISTS (
                SELECT 1 FROM entities
                WHERE id = NEW.source_entity_id
                  AND campaign_id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'effect source must belong to same campaign');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_persistent_effects_source_scope_update
            BEFORE UPDATE OF source_entity_id, campaign_id ON persistent_effects
            FOR EACH ROW
            WHEN NEW.source_entity_id IS NOT NULL
             AND NOT EXISTS (
                SELECT 1 FROM entities
                WHERE id = NEW.source_entity_id
                  AND campaign_id = NEW.campaign_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'effect source must belong to same campaign');
            END
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def migration_019(conn: sqlite3.Connection) -> None:
    """Add an authoritative, campaign-scoped fictional-time clock."""
    conn.execute("BEGIN")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_clocks (
                campaign_id INTEGER PRIMARY KEY,
                elapsed_minutes INTEGER NOT NULL DEFAULT 0
                    CHECK (elapsed_minutes >= 0),
                version INTEGER NOT NULL DEFAULT 1
                    CHECK (version >= 1),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (campaign_id)
                    REFERENCES campaign(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO campaign_clocks (campaign_id)
            SELECT id FROM campaign
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise



def migration_020(conn: sqlite3.Connection) -> None:
    """Store campaign-time deadlines separately, preserving existing effect rows."""
    conn.execute("BEGIN")
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS persistent_effect_timers (effect_id TEXT PRIMARY KEY, campaign_id INTEGER NOT NULL, duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0), expires_at_minute INTEGER NOT NULL CHECK (expires_at_minute > 0), expired_at_minute INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, CHECK (expired_at_minute IS NULL OR expired_at_minute >= expires_at_minute), FOREIGN KEY (effect_id) REFERENCES persistent_effects(id) ON DELETE CASCADE, FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_persistent_effect_timers_due ON persistent_effect_timers(campaign_id, expires_at_minute) WHERE expired_at_minute IS NULL")
        conn.execute("CREATE TRIGGER IF NOT EXISTS trg_persistent_effect_timer_campaign BEFORE INSERT ON persistent_effect_timers FOR EACH ROW WHEN NOT EXISTS (SELECT 1 FROM persistent_effects WHERE id = NEW.effect_id AND campaign_id = NEW.campaign_id) BEGIN SELECT RAISE(ABORT, 'timer campaign must match effect campaign'); END")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def migration_021(conn: sqlite3.Connection) -> None:
    """Track monotonic revisions for every campaign-scoped state mutation."""
    conn.execute("SAVEPOINT migration_021")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_state_versions (
                campaign_id INTEGER PRIMARY KEY,
                revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
                FOREIGN KEY (campaign_id)
                    REFERENCES campaign(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO campaign_state_versions (campaign_id, revision)
            SELECT id, 1 FROM campaign
        """)

        tables = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        for row in tables:
            table = row["name"] if isinstance(row, sqlite3.Row) else row[0]
            if table == "campaign_state_versions":
                continue

            quoted_table = '"' + table.replace('"', '""') + '"'
            columns = {
                column["name"] if isinstance(column, sqlite3.Row) else column[1]
                for column in conn.execute(
                    f"PRAGMA table_info({quoted_table})"
                ).fetchall()
            }

            if table == "campaign":
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS trg_campaign_state_revision_insert
                    AFTER INSERT ON campaign
                    FOR EACH ROW
                    BEGIN
                        INSERT OR IGNORE INTO campaign_state_versions (
                            campaign_id, revision
                        ) VALUES (NEW.id, 1);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS trg_campaign_state_revision_update
                    AFTER UPDATE ON campaign
                    FOR EACH ROW
                    BEGIN
                        UPDATE campaign_state_versions
                        SET revision = revision + 1
                        WHERE campaign_id = NEW.id;
                    END
                """)
                continue

            if "campaign_id" not in columns:
                continue

            trigger_table = table.replace('"', '""')
            for event in ("INSERT", "UPDATE", "DELETE"):
                reference = "OLD" if event == "DELETE" else "NEW"
                trigger_name = (
                    f"trg_state_revision_{table}_{event.lower()}"
                    .replace('"', '""')
                )
                conn.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS "{trigger_name}"
                    AFTER {event} ON "{trigger_table}"
                    FOR EACH ROW
                    BEGIN
                        UPDATE campaign_state_versions
                        SET revision = revision + 1
                        WHERE campaign_id = {reference}.campaign_id;
                    END
                """)

        conn.execute("RELEASE SAVEPOINT migration_021")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT migration_021")
        conn.execute("RELEASE SAVEPOINT migration_021")
        raise


def migration_022(conn: sqlite3.Connection) -> None:
    """Persist recoverable turn-resolution attempts separately from turn history."""
    conn.execute("SAVEPOINT migration_022")
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turn_resolutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                session_id INTEGER,
                turn_id INTEGER,
                player_input TEXT NOT NULL CHECK (length(trim(player_input)) > 0),
                adapter_namespace TEXT NOT NULL CHECK (
                    length(trim(adapter_namespace)) BETWEEN 1 AND 100
                ),
                idempotency_key TEXT NOT NULL CHECK (
                    length(trim(idempotency_key)) BETWEEN 1 AND 500
                ),
                request_fingerprint TEXT NOT NULL CHECK (
                    length(trim(request_fingerprint)) BETWEEN 1 AND 128
                ),
                lifecycle_state TEXT NOT NULL DEFAULT 'accepted'
                    CHECK (lifecycle_state IN (
                        'accepted', 'planning', 'awaiting_input', 'prepared',
                        'committed', 'narration_pending', 'completed', 'rejected'
                    )),
                context_revision INTEGER CHECK (
                    context_revision IS NULL OR context_revision >= 1
                ),
                proposal_json TEXT,
                adjudication_json TEXT,
                mechanics_json TEXT,
                operation_results_json TEXT,
                narrative TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                lease_token TEXT,
                lease_expires_at TEXT,
                last_error_code TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                committed_at TEXT,
                completed_at TEXT,
                CHECK (
                    (lease_token IS NULL AND lease_expires_at IS NULL)
                    OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
                ),
                CHECK (
                    lifecycle_state != 'planning'
                    OR (lease_token IS NOT NULL AND attempt_count > 0)
                ),
                CHECK (
                    lifecycle_state != 'prepared'
                    OR (context_revision IS NOT NULL AND proposal_json IS NOT NULL)
                ),
                CHECK (
                    lifecycle_state NOT IN ('committed', 'narration_pending', 'completed')
                    OR committed_at IS NOT NULL
                ),
                CHECK (
                    lifecycle_state != 'completed'
                    OR (completed_at IS NOT NULL AND narrative IS NOT NULL)
                ),
                UNIQUE (campaign_id, adapter_namespace, idempotency_key),
                FOREIGN KEY (campaign_id) REFERENCES campaign(id) ON DELETE CASCADE,
                FOREIGN KEY (turn_id) REFERENCES turns(id) ON DELETE SET NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_turn_resolutions_campaign_state
            ON turn_resolutions(campaign_id, lifecycle_state, created_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_turn_resolutions_expired_lease
            ON turn_resolutions(lifecycle_state, lease_expires_at)
            WHERE lifecycle_state = 'planning'
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_identity_immutable
            BEFORE UPDATE OF campaign_id, adapter_namespace, idempotency_key,
                request_fingerprint, player_input ON turn_resolutions
            FOR EACH ROW
            WHEN NEW.campaign_id != OLD.campaign_id
              OR NEW.adapter_namespace != OLD.adapter_namespace
              OR NEW.idempotency_key != OLD.idempotency_key
              OR NEW.request_fingerprint != OLD.request_fingerprint
              OR NEW.player_input != OLD.player_input
            BEGIN
                SELECT RAISE(ABORT, 'turn resolution request identity is immutable');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_transition_guard
            BEFORE UPDATE OF lifecycle_state ON turn_resolutions
            FOR EACH ROW
            WHEN NEW.lifecycle_state != OLD.lifecycle_state
              AND NOT (
                (OLD.lifecycle_state = 'accepted'
                    AND NEW.lifecycle_state IN ('planning', 'rejected'))
                OR (OLD.lifecycle_state = 'planning'
                    AND NEW.lifecycle_state IN ('accepted', 'awaiting_input', 'prepared', 'rejected'))
                OR (OLD.lifecycle_state = 'awaiting_input'
                    AND NEW.lifecycle_state IN ('planning', 'rejected'))
                OR (OLD.lifecycle_state = 'prepared'
                    AND NEW.lifecycle_state IN ('committed', 'rejected'))
                OR (OLD.lifecycle_state = 'committed'
                    AND NEW.lifecycle_state = 'narration_pending')
                OR (OLD.lifecycle_state = 'narration_pending'
                    AND NEW.lifecycle_state = 'completed')
              )
            BEGIN
                SELECT RAISE(ABORT, 'invalid turn resolution lifecycle transition');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_turn_campaign
            BEFORE INSERT ON turn_resolutions
            FOR EACH ROW
            WHEN NEW.turn_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM turns
                WHERE id = NEW.turn_id AND campaign_id = NEW.campaign_id
              )
            BEGIN
                SELECT RAISE(ABORT, 'turn resolution turn must belong to same campaign');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_turn_campaign_update
            BEFORE UPDATE OF turn_id ON turn_resolutions
            FOR EACH ROW
            WHEN NEW.turn_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM turns
                WHERE id = NEW.turn_id AND campaign_id = NEW.campaign_id
              )
            BEGIN
                SELECT RAISE(ABORT, 'turn resolution turn must belong to same campaign');
            END
        """)
        conn.execute("RELEASE SAVEPOINT migration_022")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT migration_022")
        conn.execute("RELEASE SAVEPOINT migration_022")
        raise


def migration_023(conn: sqlite3.Connection) -> None:
    """Record the campaign revision produced by a committed turn."""
    conn.execute("SAVEPOINT migration_023")
    try:
        columns = {
            row["name"] if isinstance(row, sqlite3.Row) else row[1]
            for row in conn.execute("PRAGMA table_info(turn_resolutions)").fetchall()
        }
        if "resulting_revision" not in columns:
            conn.execute("""
                ALTER TABLE turn_resolutions
                ADD COLUMN resulting_revision INTEGER
                CHECK (resulting_revision IS NULL OR resulting_revision >= 1)
            """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_committed_revision
            BEFORE UPDATE OF lifecycle_state ON turn_resolutions
            FOR EACH ROW
            WHEN NEW.lifecycle_state IN ('committed', 'narration_pending', 'completed')
              AND NEW.resulting_revision IS NULL
            BEGIN
                SELECT RAISE(ABORT, 'committed resolution requires resulting revision');
            END
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_turn_resolutions_committed_evidence_immutable
            BEFORE UPDATE OF context_revision, resulting_revision, proposal_json,
                adjudication_json, mechanics_json, operation_results_json
            ON turn_resolutions
            FOR EACH ROW
            WHEN OLD.lifecycle_state IN ('committed', 'narration_pending', 'completed')
              AND (
                NEW.context_revision IS NOT OLD.context_revision
                OR NEW.resulting_revision IS NOT OLD.resulting_revision
                OR NEW.proposal_json IS NOT OLD.proposal_json
                OR NEW.adjudication_json IS NOT OLD.adjudication_json
                OR NEW.mechanics_json IS NOT OLD.mechanics_json
                OR NEW.operation_results_json IS NOT OLD.operation_results_json
              )
            BEGIN
                SELECT RAISE(ABORT, 'committed resolution evidence is immutable');
            END
        """)
        conn.execute("RELEASE SAVEPOINT migration_023")
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT migration_023")
        conn.execute("RELEASE SAVEPOINT migration_023")
        raise

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from migrations import run_migrations

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "campaign.db"
SQLITE_TIMEOUT_SECONDS = 10.0
SQLITE_BUSY_TIMEOUT_MS = 10_000


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Open one configured connection and own its commit/rollback lifecycle."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH,
        timeout=SQLITE_TIMEOUT_SECONDS,
    )

    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def transaction(mode: str = "DEFERRED") -> Iterator[sqlite3.Connection]:
    """Own one explicit SQLite transaction and its connection lifecycle.

    The yielded connection is valid only inside this context. Repositories
    participating in the use case must receive it explicitly. Nested
    transactions are intentionally unsupported; compose work on this
    connection instead.
    """
    normalized_mode = mode.upper()
    if normalized_mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
        raise ValueError("transaction mode must be DEFERRED, IMMEDIATE or EXCLUSIVE")

    with get_conn() as conn:
        conn.execute(f"BEGIN {normalized_mode}")
        yield conn


def init_db() -> None:
    """Enable persistent WAL mode once, then apply pending schema migrations."""
    with get_conn() as conn:
        current_mode = conn.execute("PRAGMA journal_mode").fetchone()
        if current_mode is None or str(current_mode[0]).lower() != "wal":
            selected_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
            if selected_mode is None or str(selected_mode[0]).lower() != "wal":
                actual_mode = (
                    str(selected_mode[0])
                    if selected_mode is not None
                    else "unknown"
                )
                raise RuntimeError(
                    f"SQLite WAL mode could not be enabled (actual mode: {actual_mode})"
                )
        run_migrations(conn)


def rows(query, params=()):
    with get_conn() as conn:
        return [
            dict(row)
            for row in conn.execute(query, params).fetchall()
        ]


def one(query, params=()):
    with get_conn() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def execute(query, params=()):
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.lastrowid


def execute_in_conn(
    conn,
    query,
    params=(),
):
    cur = conn.execute(query, params)
    return cur.lastrowid


def rows_in_conn(
    conn,
    query,
    params=(),
):
    return [
        dict(row)
        for row in conn.execute(query, params).fetchall()
    ]


def one_in_conn(
    conn,
    query,
    params=(),
):
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None

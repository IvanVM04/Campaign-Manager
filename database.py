import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from migrations import run_migrations

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "campaign.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    conn.row_factory = sqlite3.Row

    # Permitir lecturas mientras se realizan escrituras.
    conn.execute("PRAGMA journal_mode=WAL")

    # Esperar hasta 10 segundos si SQLite está ocupado.
    conn.execute("PRAGMA busy_timeout=10000")

    # Activar integridad referencial.
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()

    except Exception:
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


def init_db():
    with get_conn() as conn:
        run_migrations(conn)


def rows(query, params=()):

    with get_conn() as conn:

        return [
            dict(row)
            for row in conn.execute(
                query,
                params
            ).fetchall()
        ]


def one(query, params=()):

    with get_conn() as conn:

        row = conn.execute(
            query,
            params
        ).fetchone()

        return dict(row) if row else None


def execute(query, params=()):

    with get_conn() as conn:

        cur = conn.execute(
            query,
            params
        )

        return cur.lastrowid

def execute_in_conn(
    conn,
    query,
    params=(),
):
    cur = conn.execute(
        query,
        params,
    )

    return cur.lastrowid

def rows_in_conn(
    conn,
    query,
    params=(),
):
    return [
        dict(row)
        for row in conn.execute(
            query,
            params,
        ).fetchall()
    ]

def one_in_conn(
    conn,
    query,
    params=(),
):
    row = conn.execute(
        query,
        params,
    ).fetchone()

    return dict(row) if row else None
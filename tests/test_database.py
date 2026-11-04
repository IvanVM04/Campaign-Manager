import pytest

from database import (
    execute_in_conn,
    get_conn,
    one_in_conn,
    transaction,
)


def test_execute_in_conn_and_one_in_conn_share_transaction():
    with get_conn() as conn:

        execute_in_conn(
            conn,
            """
            CREATE TEMP TABLE test_transaction (
                id INTEGER PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
        )

        execute_in_conn(
            conn,
            """
            INSERT INTO test_transaction (
                id,
                value
            )
            VALUES (?, ?)
            """,
            (1, "ok"),
        )

        row = one_in_conn(
            conn,
            """
            SELECT
                id,
                value
            FROM test_transaction
            WHERE id=?
            """,
            (1,),
        )

        assert row == {
            "id": 1,
            "value": "ok",
        }

def test_transaction_commits_on_success_and_rolls_back_on_error():
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE transaction_probe (value TEXT NOT NULL)"
        )

    with transaction("IMMEDIATE") as conn:
        conn.execute(
            "INSERT INTO transaction_probe (value) VALUES (?)",
            ("committed",),
        )

    with pytest.raises(RuntimeError, match="abort transaction"):
        with transaction("IMMEDIATE") as conn:
            conn.execute(
                "INSERT INTO transaction_probe (value) VALUES (?)",
                ("rolled back",),
            )
            raise RuntimeError("abort transaction")

    with get_conn() as conn:
        values = [
            row["value"]
            for row in conn.execute(
                "SELECT value FROM transaction_probe ORDER BY rowid"
            )
        ]

    assert values == ["committed"]


@pytest.mark.parametrize("mode", ["invalid", ""])
def test_transaction_rejects_unsupported_modes(mode):
    with pytest.raises(ValueError, match="transaction mode"):
        with transaction(mode):
            pytest.fail("invalid transaction mode must not open a transaction")

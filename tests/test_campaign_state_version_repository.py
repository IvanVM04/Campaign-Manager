from __future__ import annotations

import pytest

from database import get_conn, transaction
from migrations import migration_021
from repositories.campaign_state_version_repository import (
    CampaignStateVersionRepository,
)


def test_campaign_revision_tracks_all_campaign_scoped_mutations():
    repository = CampaignStateVersionRepository()

    with transaction("IMMEDIATE") as conn:
        conn.execute(
            "INSERT INTO campaign (id, name) VALUES (2, ?)",
            ("Second campaign",),
        )
        initial = repository.get_revision(2, conn=conn)
        other_initial = repository.get_revision(1, conn=conn)

        entity_id = conn.execute(
            """
            INSERT INTO entities (name, entity_type, campaign_id)
            VALUES (?, ?, ?)
            """,
            ("Guard", "npc", 2),
        ).lastrowid
        after_insert = repository.get_revision(2, conn=conn)

        conn.execute(
            "UPDATE entities SET name = ? WHERE id = ? AND campaign_id = ?",
            ("Guard Captain", entity_id, 2),
        )
        after_update = repository.get_revision(2, conn=conn)

        conn.execute(
            "DELETE FROM entities WHERE id = ? AND campaign_id = ?",
            (entity_id, 2),
        )
        after_delete = repository.get_revision(2, conn=conn)
        other_after = repository.get_revision(1, conn=conn)

    assert after_insert == initial + 1
    assert after_update == after_insert + 1
    assert after_delete == after_update + 1
    assert other_after == other_initial


def test_campaign_revision_rolls_back_with_failed_transaction():
    repository = CampaignStateVersionRepository()
    with get_conn() as conn:
        before = repository.get_revision(1, conn=conn)

    with (
        pytest.raises(RuntimeError, match="abort"),
        transaction("IMMEDIATE") as conn,
    ):
        conn.execute(
            """
            INSERT INTO entities (name, entity_type, campaign_id)
            VALUES (?, ?, ?)
            """,
            ("Transient", "npc", 1),
        )
        raise RuntimeError("abort")

    with get_conn() as conn:
        after = repository.get_revision(1, conn=conn)
        found = conn.execute(
            "SELECT 1 FROM entities WHERE name = ? AND campaign_id = ?",
            ("Transient", 1),
        ).fetchone()

    assert after == before
    assert found is None


def test_campaign_revision_migration_is_idempotent():
    repository = CampaignStateVersionRepository()
    with get_conn() as conn:
        before = repository.get_revision(1, conn=conn)

    with get_conn() as conn:
        migration_021(conn)

    with get_conn() as conn:
        after = repository.get_revision(1, conn=conn)

    assert after == before

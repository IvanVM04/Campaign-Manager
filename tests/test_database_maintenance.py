import sqlite3
from pathlib import Path

import pytest

import database
from migrations import CURRENT_VERSION
from scripts.db_maintenance import (
    DatabaseMaintenanceError,
    backup_database,
    inspect_database,
    restore_database,
)


def _entity_names(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {
            str(row[0])
            for row in conn.execute("SELECT name FROM entities").fetchall()
        }
    finally:
        conn.close()


def test_inspect_database_reports_current_schema_and_integrity():
    report = inspect_database(database.DB_PATH)

    assert report.schema_version == CURRENT_VERSION
    assert report.integrity_messages == ("ok",)
    assert report.foreign_key_violations == ()
    assert report.healthy is True


def test_backup_includes_committed_wal_data_and_is_verifiable(tmp_path):
    database.execute(
        "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
        ("Backup Hero", "player_character"),
    )
    destination = tmp_path / "backups" / "campaign.sqlite3"

    result = backup_database(database.DB_PATH, destination)
    report = inspect_database(result)

    assert result == destination
    assert report.healthy is True
    assert report.schema_version == CURRENT_VERSION
    assert "Backup Hero" in _entity_names(result)


def test_backup_does_not_overwrite_existing_destination(tmp_path):
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"preserve me")

    with pytest.raises(FileExistsError):
        backup_database(database.DB_PATH, destination)

    assert destination.read_bytes() == b"preserve me"


def test_restore_requires_explicit_confirmation(tmp_path):
    backup = backup_database(
        database.DB_PATH,
        tmp_path / "campaign-backup.sqlite3",
    )

    with pytest.raises(PermissionError, match="explicit confirmation"):
        restore_database(
            backup,
            database.DB_PATH,
        )


def test_restore_preserves_pre_restore_backup_and_replaces_database(tmp_path):
    database.execute(
        "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
        ("Before Backup", "npc"),
    )
    backup = backup_database(
        database.DB_PATH,
        tmp_path / "campaign-backup.sqlite3",
    )
    database.execute(
        "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
        ("After Backup", "npc"),
    )

    result = restore_database(
        backup,
        database.DB_PATH,
        confirm=True,
    )

    assert result.database_path == database.DB_PATH
    assert result.pre_restore_backup is not None
    assert result.pre_restore_backup.is_file()
    assert "Before Backup" in _entity_names(database.DB_PATH)
    assert "After Backup" not in _entity_names(database.DB_PATH)
    assert "After Backup" in _entity_names(result.pre_restore_backup)
    assert inspect_database(database.DB_PATH).healthy is True


def test_restore_rejects_wrong_schema_without_changing_destination(tmp_path):
    database.execute(
        "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
        ("Must Survive", "npc"),
    )
    backup = backup_database(
        database.DB_PATH,
        tmp_path / "old-schema.sqlite3",
    )
    conn = sqlite3.connect(backup)
    try:
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(DatabaseMaintenanceError, match="schema version"):
        restore_database(
            backup,
            database.DB_PATH,
            confirm=True,
        )

    assert "Must Survive" in _entity_names(database.DB_PATH)

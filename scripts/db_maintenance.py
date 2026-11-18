"""Offline SQLite integrity, backup and restore utilities.

Stop the Campaign Manager API before restoring a database. Backups use
SQLite's online backup API so committed WAL content is included consistently.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import DB_PATH, SQLITE_BUSY_TIMEOUT_MS, SQLITE_TIMEOUT_SECONDS
from migrations import CURRENT_VERSION


class DatabaseMaintenanceError(RuntimeError):
    """A database could not be safely inspected, backed up or restored."""


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    schema_version: int
    integrity_messages: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]

    @property
    def healthy(self) -> bool:
        return self.integrity_messages == ("ok",) and not self.foreign_key_violations


@dataclass(frozen=True, slots=True)
class RestoreResult:
    database_path: Path
    pre_restore_backup: Path | None


def _readonly_connection(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {resolved}")
    encoded_path = quote(resolved.as_posix(), safe="/:")
    uri = f"file:{encoded_path}?mode=ro"
    conn = sqlite3.connect(
        uri,
        uri=True,
        timeout=SQLITE_TIMEOUT_SECONDS,
    )
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def inspect_database(path: Path) -> DatabaseHealth:
    """Run SQLite integrity and foreign-key checks without modifying the file."""
    conn = _readonly_connection(Path(path))
    try:
        integrity_messages = tuple(
            str(row[0]) for row in conn.execute("PRAGMA integrity_check").fetchall()
        )
        foreign_key_violations = tuple(
            tuple(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        schema_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        return DatabaseHealth(
            schema_version=schema_version,
            integrity_messages=integrity_messages,
            foreign_key_violations=foreign_key_violations,
        )
    except sqlite3.DatabaseError as exc:
        raise DatabaseMaintenanceError(
            f"SQLite integrity inspection failed: {exc}"
        ) from exc
    finally:
        conn.close()


def _require_healthy(path: Path) -> DatabaseHealth:
    report = inspect_database(path)
    if not report.healthy:
        raise DatabaseMaintenanceError(
            "database failed integrity validation "
            f"(integrity={report.integrity_messages!r}, "
            f"foreign_key_violations={len(report.foreign_key_violations)})"
        )
    return report


def _temporary_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    return Path(name)


def backup_database(
    source: Path,
    destination: Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Create a consistent SQLite backup and publish it atomically."""
    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()

    if source == destination:
        raise ValueError("backup source and destination must be different files")
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(destination)
    try:
        source_conn = sqlite3.connect(
            source,
            timeout=SQLITE_TIMEOUT_SECONDS,
        )
        target_conn = sqlite3.connect(temporary)
        try:
            source_conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
            source_conn.backup(target_conn)
            target_conn.commit()
        finally:
            target_conn.close()
            source_conn.close()

        _require_healthy(temporary)
        if overwrite:
            os.replace(temporary, destination)
        else:
            # A same-directory hard link publishes without a check/replace race.
            # The temporary file is on the same filesystem as the destination.
            os.link(temporary, destination)
            temporary.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def _checkpoint_database(path: Path) -> None:
    """Checkpoint WAL and fail if SQLite reports a busy checkpoint."""
    conn = sqlite3.connect(path, timeout=SQLITE_TIMEOUT_SECONDS)
    try:
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("ROLLBACK")
        result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if result is not None and int(result[0]) != 0:
            raise DatabaseMaintenanceError(
                "could not checkpoint the destination database; "
                "ensure the application is stopped and retry"
            )
    except sqlite3.OperationalError as exc:
        raise DatabaseMaintenanceError(
            "could not obtain exclusive writer access to the destination database; "
            "stop the application before restoring"
        ) from exc
    finally:
        conn.close()


def _pre_restore_path(destination: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return destination.with_name(
        f"{destination.stem}.pre-restore-{stamp}{destination.suffix or '.sqlite3'}"
    )


def restore_database(
    source: Path,
    destination: Path,
    *,
    confirm: bool = False,
    expected_schema_version: int = CURRENT_VERSION,
) -> RestoreResult:
    """Restore a verified current-schema backup, preserving the previous DB.

    The API process must be stopped. The replacement is staged and verified
    beside the destination before the database file is atomically replaced.
    """
    if not confirm:
        raise PermissionError(
            "restore requires explicit confirmation (pass confirm=True or CLI --confirm)"
        )

    source = Path(source).expanduser().resolve()
    destination = Path(destination).expanduser().resolve()
    if source == destination:
        raise ValueError("restore source and destination must be different files")

    source_report = _require_healthy(source)
    if source_report.schema_version != expected_schema_version:
        raise DatabaseMaintenanceError(
            "backup schema version does not match this application "
            f"(backup={source_report.schema_version}, expected={expected_schema_version})"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = _temporary_path(destination)
    pre_restore: Path | None = None
    try:
        backup_database(source, staged, overwrite=True)

        if destination.exists():
            pre_restore = _pre_restore_path(destination)
            backup_database(destination, pre_restore)
            _checkpoint_database(destination)
            for suffix in ("-wal", "-shm", "-journal"):
                Path(f"{destination}{suffix}").unlink(missing_ok=True)

        os.replace(staged, destination)
        try:
            restored_report = _require_healthy(destination)
            if restored_report.schema_version != expected_schema_version:
                raise DatabaseMaintenanceError(
                    "restored database schema version changed unexpectedly"
                )
        except Exception:
            if pre_restore is not None:
                backup_database(pre_restore, destination, overwrite=True)
            else:
                destination.unlink(missing_ok=True)
            raise

        return RestoreResult(
            database_path=destination,
            pre_restore_backup=pre_restore,
        )
    finally:
        staged.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, back up and restore the Campaign Manager SQLite database."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="run integrity checks")
    check_parser.add_argument("--database", type=Path, default=DB_PATH)

    backup_parser = subparsers.add_parser("backup", help="create a consistent backup")
    backup_parser.add_argument("--database", type=Path, default=DB_PATH)
    backup_parser.add_argument("--output", type=Path, required=True)
    backup_parser.add_argument("--overwrite", action="store_true")

    restore_parser = subparsers.add_parser("restore", help="restore a verified backup")
    restore_parser.add_argument("--database", type=Path, default=DB_PATH)
    restore_parser.add_argument("--input", type=Path, required=True)
    restore_parser.add_argument(
        "--confirm",
        action="store_true",
        help="required acknowledgement that the API process is stopped",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            report = inspect_database(args.database)
            print(f"schema_version: {report.schema_version}")
            print(f"integrity_check: {', '.join(report.integrity_messages)}")
            print(f"foreign_key_violations: {len(report.foreign_key_violations)}")
            if report.schema_version != CURRENT_VERSION:
                print(
                    f"expected_schema_version: {CURRENT_VERSION}",
                    file=sys.stderr,
                )
            return 0 if report.healthy and report.schema_version == CURRENT_VERSION else 1

        if args.command == "backup":
            path = backup_database(
                args.database,
                args.output,
                overwrite=args.overwrite,
            )
            report = _require_healthy(path)
            print(f"backup: {path}")
            print(f"schema_version: {report.schema_version}")
            return 0

        if args.command == "restore":
            result = restore_database(
                args.input,
                args.database,
                confirm=args.confirm,
            )
            print(f"restored_database: {result.database_path}")
            if result.pre_restore_backup is not None:
                print(f"pre_restore_backup: {result.pre_restore_backup}")
            print(f"schema_version: {CURRENT_VERSION}")
            return 0

    except (DatabaseMaintenanceError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"database maintenance failed: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

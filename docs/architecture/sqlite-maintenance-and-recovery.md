# SQLite maintenance and recovery

**Scope:** offline integrity checks, consistent backups and guarded restoration for the local single-process deployment.

## Operating constraints

- Stop the Campaign Manager API before restoring a database. The application maintains process-local world caches and campaign locks; replacing SQLite while the API is running is unsupported.
- Backups are full database copies and may include GM-only material. Store them with the same care as the original database. Do not expose them through player-safe export endpoints or commit them to Git.
- Restore accepts only a backup whose SQLite user_version equals the schema version supported by the running checkout. Upgrade an old database with the application migration runner before using this restore workflow.
- The tool never deletes the source backup. When restoring over an existing database, it creates a separately verified pre-restore backup first.

## Integrity check

Run from the repository root:

~~~powershell
python scripts/db_maintenance.py check
~~~

The command reports the schema version, SQLite integrity_check result and foreign-key violations. A zero exit code requires a healthy database at the current schema version.

You can target an alternate database file with --database:

~~~powershell
python scripts/db_maintenance.py check --database .\data\campaign.db
~~~

## Create a consistent backup

~~~powershell
python scripts/db_maintenance.py backup --output .\data\backups\campaign-before-update.sqlite3
~~~

The backup is produced with Python's SQLite online backup API. This includes committed content in WAL mode without copying a live -wal sidecar by hand. The staged backup is integrity-checked before it is published. Existing destinations are not overwritten unless --overwrite is supplied.

## Restore a backup

1. Stop the API process (for example, close the terminal running start.bat).
2. Keep the source backup outside the live database path.
3. Run:

~~~powershell
python scripts/db_maintenance.py restore --input .\data\backups\campaign-before-update.sqlite3 --confirm
~~~

The tool:

1. Requires the explicit --confirm acknowledgement.
2. Checks SQLite integrity, foreign keys and exact schema version.
3. Stages and verifies the replacement in the destination directory.
4. Creates a timestamped pre-restore backup of the current database, if one exists.
5. Obtains exclusive writer access, checkpoints WAL and removes stale SQLite sidecars.
6. Atomically replaces the database file and verifies the restored copy again.

If the restored file fails its post-replacement check, the verified pre-restore backup is copied back. The pre-restore backup remains available for manual recovery.

## Connection and WAL policy

- Every application connection enables foreign keys and sets the configured busy timeout.
- WAL is persistent database state and is enabled during init_db(), not negotiated on every connection.
- Explicit transactions continue to use caller-owned connections and the existing DEFERRED / IMMEDIATE boundaries.
- The application remains single-process/single-worker. WAL does not provide coordination for multiple independent in-memory campaign runtimes.

## Recovery limitations

This is local file-level backup and restore, not a cloud backup service, encrypted archive format, point-in-time recovery system or multi-process deployment feature. Keep additional copies on separate storage for disaster recovery. Do not place database backups in a publicly served directory.

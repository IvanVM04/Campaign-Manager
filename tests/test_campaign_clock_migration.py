import sqlite3

from migrations import migration_019


def test_migration_019_creates_clock_for_existing_campaigns():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE campaign (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("INSERT INTO campaign (id, name) VALUES (1, 'Existing')")
    conn.commit()
    migration_019(conn)
    row = conn.execute("SELECT * FROM campaign_clocks WHERE campaign_id = 1").fetchone()
    assert row["elapsed_minutes"] == 0
    assert row["version"] == 1
    conn.close()

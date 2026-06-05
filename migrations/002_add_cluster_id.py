"""Migration 002 — Add cluster_id column to machine table.

Adds ``cluster_id`` (TEXT, NOT NULL, default 'default') to support a single
attestation service instance managing multiple independent Talos clusters.

All existing rows are assigned to the ``default`` cluster.
"""
import sqlite3
import sys


def upgrade(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Check if column already exists (idempotent)
    cur.execute("PRAGMA table_info(machine)")
    columns = {row[1] for row in cur.fetchall()}
    if "cluster_id" in columns:
        print("cluster_id column already exists — skipping")
        con.close()
        return

    cur.execute("ALTER TABLE machine ADD COLUMN cluster_id TEXT NOT NULL DEFAULT 'default'")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_machine_cluster_id ON machine (cluster_id)")
    con.commit()
    con.close()
    print("Migration 002 applied: cluster_id column added")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "/var/lib/itl-reg/db/machines.db"
    upgrade(db)

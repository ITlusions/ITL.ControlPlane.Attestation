"""Migration 001 — Add ek_fingerprint_sha384 column (CNSA 1.0, issue #8).

Background
----------
In releases prior to this migration the ``ek_fingerprint`` column stored a
64-character SHA-256 hex digest.  CNSA 1.0 requires SHA-384 (96-character
hex).  The application code was updated to compute SHA-384 fingerprints for
all *new* registrations, but existing rows in the ``machine`` table still
carry the old SHA-256 value.

This migration:
1. Adds the nullable ``ek_fingerprint_sha384`` column (TEXT, indexed).
2. Populates it for every row that has a stored ``ek_cert_pem`` by
   recomputing the SHA-384 fingerprint from the raw certificate bytes.
3. For rows without ``ek_cert_pem`` (registered via the ``pub`` path), the
   column is left NULL — those machines must re-attest to update the value.

After running this migration, new attestations will automatically set both
``ek_fingerprint`` (SHA-384) and ``ek_fingerprint_sha384`` (SHA-384, same
value) when the machine re-registers or re-attests.

Usage
-----
    python migrations/001_add_ek_fingerprint_sha384.py [DB_PATH]

If DB_PATH is not supplied, the value of ITL_DB_URL is used (stripping the
leading ``sqlite:////`` prefix).  The migration is idempotent: re-running it
on an already-migrated database is safe.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import sys
from pathlib import Path


def _sha384_from_b64_pem(b64_pem: str) -> str:
    """Return the SHA-384 hex digest of the raw (base64-decoded) EK bytes."""
    try:
        raw = base64.b64decode(b64_pem)
    except Exception as exc:
        raise ValueError(
            f"Invalid base64-encoded PEM data: {exc}. "
            "Ensure ek_cert_pem is a base64-encoded DER/PEM certificate."
        ) from exc
    return hashlib.sha384(raw).hexdigest()


def migrate(db_path: str) -> None:
    path = Path(db_path)
    if not path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. Add column if absent
    cur.execute("PRAGMA table_info(machine)")
    existing_cols = {row["name"] for row in cur.fetchall()}
    if "ek_fingerprint_sha384" not in existing_cols:
        print("Adding column ek_fingerprint_sha384 …")
        cur.execute(
            "ALTER TABLE machine ADD COLUMN ek_fingerprint_sha384 TEXT"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS ix_machine_ek_fingerprint_sha384 "
            "ON machine (ek_fingerprint_sha384)"
        )
        con.commit()
        print("Column added.")
    else:
        print("Column ek_fingerprint_sha384 already present — skipping ALTER TABLE.")

    # 2. Populate from ek_cert_pem for rows that don't have sha384 yet
    cur.execute(
        "SELECT id, ek_cert_pem, ek_fingerprint "
        "FROM machine "
        "WHERE ek_fingerprint_sha384 IS NULL"
    )
    rows = cur.fetchall()
    updated = 0
    skipped = 0
    for row in rows:
        row_id        = row["id"]
        ek_cert_pem   = row["ek_cert_pem"]
        ek_fingerprint = row["ek_fingerprint"]

        if ek_cert_pem:
            try:
                sha384_fp = _sha384_from_b64_pem(ek_cert_pem)
            except Exception as exc:
                print(
                    f"  WARN: row id={row_id} — cannot compute SHA-384 from ek_cert_pem: {exc}",
                    file=sys.stderr,
                )
                skipped += 1
                continue
        elif len(ek_fingerprint) == 96:
            # Already a SHA-384 value (96 hex chars) stored in ek_fingerprint —
            # copy it directly.
            sha384_fp = ek_fingerprint
        else:
            # SHA-256 fingerprint with no cert PEM — cannot recompute.
            print(
                f"  WARN: row id={row_id} — no ek_cert_pem and ek_fingerprint looks like "
                f"SHA-256 ({len(ek_fingerprint)} chars); machine must re-attest.",
                file=sys.stderr,
            )
            skipped += 1
            continue

        cur.execute(
            "UPDATE machine SET ek_fingerprint_sha384 = ? WHERE id = ?",
            (sha384_fp, row_id),
        )
        updated += 1

    con.commit()
    con.close()

    print(
        f"Migration complete: {updated} row(s) updated, {skipped} row(s) skipped "
        f"(re-attestation required for skipped machines)."
    )


def _resolve_db_path() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    db_url = os.environ.get("ITL_DB_URL", "sqlite:////var/lib/itl-reg/db/machines.db")
    # Only SQLite is supported by this migration script.
    for prefix in ("sqlite:////", "sqlite:///"):
        if db_url.startswith(prefix):
            return db_url[len(prefix):]
    print(
        f"ERROR: ITL_DB_URL='{db_url}' does not look like a SQLite URL. "
        "This migration script only supports SQLite databases. "
        "Pass the path to the SQLite file as the first argument.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    migrate(_resolve_db_path())

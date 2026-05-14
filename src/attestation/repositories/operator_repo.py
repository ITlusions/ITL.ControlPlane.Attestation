"""Repositories for audit-log and approval-request tables.

Operator identity is managed entirely in Keycloak — there is no local operator
repository.  These repositories only handle the state that *must* be persisted
on the service side: the append-only audit log and pending dual-control votes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..models.operator import ApprovalRequestRow, AuditLogRow

# ---------------------------------------------------------------------------
# Cryptographic chain helpers
# ---------------------------------------------------------------------------

#: SHA-256 hex string used as the ``prev_hash`` of the very first (genesis) entry.
GENESIS_HASH: str = "0" * 64


def compute_entry_hash(entry: AuditLogRow) -> str:
    """Return the SHA-256 hex digest of *entry*'s canonical form.

    The canonical form is a compact, deterministically sorted JSON object that
    includes every field **except** ``id`` (assigned by the DB after insert) and
    ``entry_hash`` (the field being computed).  ``datetime`` values are
    normalised to UTC-naive ISO 8601 strings (``YYYY-MM-DDTHH:MM:SS.ffffff``)
    so the representation is identical whether the datetime was just created
    (timezone-aware) or read back from SQLite (which strips timezone info).
    """
    ts = entry.timestamp
    if isinstance(ts, datetime):
        # Normalise: strip timezone offset so the string is the same regardless
        # of whether the datetime came from Python (timezone-aware) or was read
        # back from SQLite (which stores all datetimes as UTC-naive text).
        ts = ts.replace(tzinfo=None).isoformat()

    data: dict = {
        "action":      entry.action,
        "detail":      entry.detail,
        "machine_id":  entry.machine_id,
        "new_state":   entry.new_state,
        "operator_cn": entry.operator_cn,
        "prev_hash":   entry.prev_hash,
        "prev_state":  entry.prev_state,
        "timestamp":   ts,
    }
    canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AuditRepository:
    """Append-only data access for AuditLogRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _last_entry_hash(self) -> str:
        """Return the ``entry_hash`` of the most-recently inserted row.

        Returns ``GENESIS_HASH`` when the table is empty (first entry).
        """
        row = self.db.exec(
            select(AuditLogRow).order_by(AuditLogRow.id.desc()).limit(1)  # type: ignore[attr-defined]
        ).first()
        return row.entry_hash if row else GENESIS_HASH

    def append(self, entry: AuditLogRow) -> AuditLogRow:
        """Insert a new audit log entry, computing the cryptographic chain hashes.

        Sets ``entry.prev_hash`` to the previous row's ``entry_hash`` (or
        ``GENESIS_HASH`` for the first row), then computes and sets
        ``entry.entry_hash`` before persisting.  Never updates or deletes existing
        rows.
        """
        entry.prev_hash  = self._last_entry_hash()
        entry.entry_hash = compute_entry_hash(entry)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_page(self, page: int = 1, per_page: int = 50) -> list[AuditLogRow]:
        offset = (page - 1) * per_page
        return list(
            self.db.exec(
                select(AuditLogRow)
                .order_by(AuditLogRow.id.desc())  # type: ignore[attr-defined]
                .offset(offset)
                .limit(per_page)
            ).all()
        )

    def count(self) -> int:
        from sqlmodel import func
        result = self.db.exec(select(func.count()).select_from(AuditLogRow)).one()
        return result

    def verify_chain(self) -> dict:
        """Walk every entry in insertion order and verify the hash chain.

        Returns a dict with keys:
          - ``valid``            — ``True`` iff every entry hash is correct and the
                                   chain is unbroken from the genesis sentinel.
          - ``entries``          — total number of entries inspected.
          - ``root_hash``        — ``entry_hash`` of the last entry (current chain tip);
                                   ``None`` when the table is empty.
          - ``first_invalid_id`` — ``id`` of the first entry with a bad hash, or ``None``.
          - ``error``            — human-readable description of the first failure, or ``None``.
        """
        rows = list(
            self.db.exec(
                select(AuditLogRow).order_by(AuditLogRow.id.asc())  # type: ignore[attr-defined]
            ).all()
        )

        if not rows:
            return {
                "valid":            True,
                "entries":          0,
                "root_hash":        None,
                "first_invalid_id": None,
                "error":            None,
            }

        expected_prev = GENESIS_HASH
        for row in rows:
            if row.prev_hash != expected_prev:
                return {
                    "valid":            False,
                    "entries":          len(rows),
                    "root_hash":        None,
                    "first_invalid_id": row.id,
                    "error":            f"prev_hash mismatch at entry id={row.id}",
                }
            computed = compute_entry_hash(row)
            if row.entry_hash != computed:
                return {
                    "valid":            False,
                    "entries":          len(rows),
                    "root_hash":        None,
                    "first_invalid_id": row.id,
                    "error":            f"entry_hash mismatch at entry id={row.id}",
                }
            expected_prev = row.entry_hash

        return {
            "valid":            True,
            "entries":          len(rows),
            "root_hash":        rows[-1].entry_hash,
            "first_invalid_id": None,
            "error":            None,
        }



# ---------------------------------------------------------------------------
# Approval request repository
# ---------------------------------------------------------------------------

class ApprovalRepository:
    """Data access for ApprovalRequestRow (dual-control pending approvals)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, row: ApprovalRequestRow) -> ApprovalRequestRow:
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_pending_for_machine(self, machine_id: str) -> list[ApprovalRequestRow]:
        """Return all non-consumed, non-expired pending approvals for a machine."""
        now = datetime.now(timezone.utc)
        return list(
            self.db.exec(
                select(ApprovalRequestRow).where(
                    ApprovalRequestRow.machine_id == machine_id,
                    ApprovalRequestRow.consumed == False,  # noqa: E712
                    ApprovalRequestRow.expires_at > now,
                )
            ).all()
        )

    def mark_consumed(self, approval_id: int) -> None:
        row = self.db.get(ApprovalRequestRow, approval_id)
        if row:
            row.consumed = True
            self.db.add(row)
            self.db.commit()

    def list_for_machine(self, machine_id: str) -> list[ApprovalRequestRow]:
        """Return all approval requests for a machine (including expired/consumed)."""
        return list(
            self.db.exec(
                select(ApprovalRequestRow).where(
                    ApprovalRequestRow.machine_id == machine_id
                ).order_by(ApprovalRequestRow.id.desc())  # type: ignore[attr-defined]
            ).all()
        )

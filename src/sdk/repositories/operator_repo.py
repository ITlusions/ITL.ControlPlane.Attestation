"""Repositories for audit-log and approval-request tables.

Operator identity is managed entirely in Keycloak — there is no local operator
repository.  These repositories only handle the state that *must* be persisted
on the service side: the append-only audit log and pending dual-control votes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlmodel import Session, func, select

from sdk.models.operator import ApprovalRequestRow, AuditLogRow

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
        "action": entry.action,
        "detail": entry.detail,
        "machine_id": entry.machine_id,
        "new_state": entry.new_state,
        "operator_cn": entry.operator_cn,
        "prev_hash": entry.prev_hash,
        "prev_state": entry.prev_state,
        "source_ip": entry.source_ip,
        "timestamp": ts,
    }
    canonical = json.dumps(data, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AuditRepository:
    """Append-only data access for AuditLogRow.

    This repository implements a cryptographically-chained audit log where each
    entry contains a hash of the previous entry, forming a tamper-evident chain.
    """

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
        entry.prev_hash = self._last_entry_hash()
        entry.entry_hash = compute_entry_hash(entry)
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list_page(self, page: int = 1, per_page: int = 50) -> list[AuditLogRow]:
        """List audit log entries with pagination (newest first)."""
        offset = (page - 1) * per_page
        return list(
            self.db.exec(
                select(AuditLogRow)
                .order_by(AuditLogRow.id.desc())  # type: ignore[attr-defined]
                .offset(offset)
                .limit(per_page)
            ).all()
        )

    def list_all(self) -> list[AuditLogRow]:
        """List all audit log entries (no pagination, newest first)."""
        return list(
            self.db.exec(
                select(AuditLogRow).order_by(AuditLogRow.id.desc())  # type: ignore[attr-defined]
            ).all()
        )

    def count(self) -> int:
        """Count total audit log entries."""
        result = self.db.exec(select(func.count()).select_from(AuditLogRow)).one()
        return result

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the entire audit log chain for integrity.

        Returns:
            (is_valid, errors) — if is_valid is False, errors contains descriptions
            of which entries failed validation.
        """
        entries = list(
            self.db.exec(
                select(AuditLogRow).order_by(AuditLogRow.id.asc())  # type: ignore[attr-defined]
            ).all()
        )

        if not entries:
            return (True, [])

        errors: list[str] = []
        expected_prev_hash = GENESIS_HASH

        for entry in entries:
            # Check prev_hash matches expected
            if entry.prev_hash != expected_prev_hash:
                errors.append(
                    f"Entry #{entry.id}: expected prev_hash={expected_prev_hash[:16]}..., "
                    f"got {entry.prev_hash[:16]}..."
                )

            # Recompute entry_hash and check it matches
            computed_hash = compute_entry_hash(entry)
            if entry.entry_hash != computed_hash:
                errors.append(
                    f"Entry #{entry.id}: expected entry_hash={computed_hash[:16]}..., "
                    f"got {entry.entry_hash[:16]}..."
                )

            expected_prev_hash = entry.entry_hash

        return (len(errors) == 0, errors)


class ApprovalRequestRepository:
    """Data access for dual-control approval requests."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, request: ApprovalRequestRow) -> ApprovalRequestRow:
        """Create a new approval request."""
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def get_active_for_machine(
        self, machine_id: str, exclude_operator: str | None = None
    ) -> ApprovalRequestRow | None:
        """Get an active (non-consumed, non-expired) approval request for a machine.

        If exclude_operator is provided, only returns requests from other operators
        (required for dual-control validation).
        """
        query = select(ApprovalRequestRow).where(
            ApprovalRequestRow.machine_id == machine_id,
            ApprovalRequestRow.consumed == False,  # noqa: E712
            ApprovalRequestRow.expires_at > datetime.now(timezone.utc),
        )

        if exclude_operator:
            query = query.where(ApprovalRequestRow.operator_cn != exclude_operator)

        return self.db.exec(query).first()

    def consume(self, request: ApprovalRequestRow) -> ApprovalRequestRow:
        """Mark an approval request as consumed."""
        request.consumed = True
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def cleanup_expired(self) -> int:
        """Delete expired approval requests.

        Returns the number of rows deleted.
        """
        stmt = select(ApprovalRequestRow).where(
            ApprovalRequestRow.expires_at <= datetime.now(timezone.utc)
        )
        expired = list(self.db.exec(stmt).all())

        for request in expired:
            self.db.delete(request)

        self.db.commit()
        return len(expired)

"""Repositories for audit-log and approval-request tables.

Operator identity is managed entirely in Keycloak — there is no local operator
repository.  These repositories only handle the state that *must* be persisted
on the service side: the append-only audit log and pending dual-control votes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from ..models.operator import ApprovalRequestRow, AuditLogRow

class AuditRepository:
    """Append-only data access for AuditLogRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, entry: AuditLogRow) -> AuditLogRow:
        """Insert a new audit log entry.  Never updates or deletes existing rows."""
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

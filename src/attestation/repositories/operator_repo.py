"""Repositories for operator, audit-log, and approval-request tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..models.operator import ApprovalRequestRow, AuditLogRow, OperatorRow


# ---------------------------------------------------------------------------
# Operator repository
# ---------------------------------------------------------------------------

class OperatorRepository:
    """Data access layer for OperatorRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, operator_id: str) -> Optional[OperatorRow]:
        return self.db.exec(
            select(OperatorRow).where(OperatorRow.operator_id == operator_id)
        ).first()

    def get_by_name(self, name: str) -> Optional[OperatorRow]:
        return self.db.exec(
            select(OperatorRow).where(OperatorRow.name == name)
        ).first()

    def get_by_oidc_sub(self, oidc_sub: str) -> Optional[OperatorRow]:
        return self.db.exec(
            select(OperatorRow).where(OperatorRow.oidc_sub == oidc_sub)
        ).first()

    def list_all(self) -> list[OperatorRow]:
        return list(self.db.exec(select(OperatorRow)).all())

    def save(self, operator: OperatorRow) -> OperatorRow:
        self.db.add(operator)
        self.db.commit()
        self.db.refresh(operator)
        return operator


# ---------------------------------------------------------------------------
# Audit log repository  (INSERT-only — no update/delete)
# ---------------------------------------------------------------------------

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
        now = datetime.utcnow()
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

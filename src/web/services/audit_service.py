"""Audit log business logic."""
from __future__ import annotations

from sqlmodel import Session

from sdk.models import AuditLogRow
from sdk.repositories import AuditRepository


class AuditService:
    def __init__(self, db_session: Session) -> None:
        self._repo = AuditRepository(db_session)

    def all(self) -> list[AuditLogRow]:
        return self._repo.list_all()

    def log(
        self,
        action: str,
        machine_id: str,
        detail: str = "",
        operator: str = "dashboard",
        prev_state: str = "",
        new_state: str = "",
    ) -> None:
        self._repo.append(
            operator_cn=operator,
            action=action.upper(),
            machine_id=machine_id,
            prev_state=prev_state,
            new_state=new_state,
            detail=detail,
        )

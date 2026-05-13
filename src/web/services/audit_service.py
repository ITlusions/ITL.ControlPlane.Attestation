"""Audit log business logic."""
from __future__ import annotations

from typing import Any

from repositories.audit_repo import InMemoryAuditRepository


class AuditService:
    def __init__(self, audit_repo: InMemoryAuditRepository) -> None:
        self._repo = audit_repo

    def all(self) -> list[dict[str, Any]]:
        return self._repo.all()

    def log(
        self,
        action: str,
        machine_id: str,
        detail: str = "",
        actor: str = "dashboard",
        result: str = "success",
    ) -> None:
        self._repo.log(action=action, machine_id=machine_id, detail=detail, actor=actor, result=result)

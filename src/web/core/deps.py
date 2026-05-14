"""Dependency injection helpers for Flask routes."""
from __future__ import annotations

from flask import g

from sdk.repositories import AuditRepository, SqlMachineRepository


class AuditRepositoryWrapper:
    """Wrapper for AuditRepository to add list_all() method."""
    
    def __init__(self, audit_repo: AuditRepository):
        self._repo = audit_repo
    
    def list_all(self):
        """Get all audit entries (uses list_page with large limit)."""
        return self._repo.list_page(page=1, per_page=10000)
    
    def save(self, entry):
        """Save audit entry (delegates to append)."""
        return self._repo.append(entry)


def get_machine_repo() -> SqlMachineRepository:
    """Get a machine repository for the current request."""
    if not hasattr(g, "machine_repo"):
        g.machine_repo = SqlMachineRepository(g.db_session)
    return g.machine_repo


def get_audit_repo() -> AuditRepositoryWrapper:
    """Get an audit repository for the current request."""
    if not hasattr(g, "audit_repo"):
        g.audit_repo = AuditRepositoryWrapper(AuditRepository(g.db_session))
    return g.audit_repo

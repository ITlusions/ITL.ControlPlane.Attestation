"""Routes for the append-only audit log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..core.deps import get_audit_repo, resolve_operator
from ..repositories.operator_repo import AuditRepository
from ..schemas.responses import AuditLogEntry, AuditVerifyResult

router = APIRouter(tags=["audit"])


@router.get("/verify", response_model=AuditVerifyResult)
def verify_audit_chain(
    operator_cn: str = Depends(resolve_operator),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Walk the full audit log and verify the cryptographic hash chain (admin).

    Re-computes every entry's SHA-256 hash and checks that each ``prev_hash``
    field matches the previous entry's ``entry_hash``.  Reports the first broken
    link, if any.

    Returns ``valid: true`` when the chain is intact, or ``valid: false`` with
    ``first_invalid_id`` and ``error`` identifying the first tampered entry.
    """
    return audit_repo.verify_chain()


@router.get("", response_model=list[AuditLogEntry])
def list_audit_log(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(default=50, ge=1, le=200, description="Entries per page"),
    operator_cn: str = Depends(resolve_operator),
    audit_repo: AuditRepository = Depends(get_audit_repo),
):
    """Return a paginated, newest-first view of the append-only audit log (admin).

    The log is append-only: no entry is ever updated or deleted.
    Each entry includes ``prev_hash`` and ``entry_hash`` fields that form a
    cryptographically chained sequence — use ``GET /api/v1/audit/verify`` to
    validate the full chain.
    ``operator_cn`` is ``SYSTEM`` for actions performed with the break-glass token.
    """
    rows = audit_repo.list_page(page=page, per_page=per_page)
    return [
        AuditLogEntry(
            id          = r.id,
            timestamp   = r.timestamp,
            operator_cn = r.operator_cn,
            action      = r.action,
            machine_id  = r.machine_id,
            prev_state  = r.prev_state,
            new_state   = r.new_state,
            detail      = r.detail,
            prev_hash   = r.prev_hash,
            entry_hash  = r.entry_hash,
        )
        for r in rows
    ]

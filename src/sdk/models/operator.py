"""Audit-log and dual-control approval models.

Operator identity is managed entirely in Keycloak — there is no local operator
table.  The JWT ``preferred_username`` (or ``sub``) claim is used as the
canonical operator identity string throughout.

These tables support:
  - append-only audit log  (AuditLogRow)
  - dual-control approvals (ApprovalRequestRow)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AuditLogRow(SQLModel, table=True):
    """Append-only audit log entry for every admin operation.

    This table must never be updated or deleted from — only INSERTs are allowed.
    operator_cn is "SYSTEM" for break-glass (ITL_ADMIN_TOKEN) actions.

    The log forms a cryptographically chained sequence:
      prev_hash   — SHA-256 of the previous row's canonical form; "0"*64 for the genesis entry.
      entry_hash  — SHA-256 of this row's canonical form (all fields except id and entry_hash).

    Any modification to a historical entry invalidates all subsequent hashes, making tampering
    detectable by re-walking the chain via GET /api/v1/audit/verify.
    """

    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    operator_cn: str  # "SYSTEM" | operator name/CN | Keycloak preferred_username
    action: str  # "approve", "revoke", "lock", "unlock", "wipe", "import", "register", "attest"
    machine_id: Optional[str] = Field(default=None)
    prev_state: Optional[str] = Field(default=None)
    new_state: Optional[str] = Field(default=None)
    detail: Optional[str] = Field(default=None)  # free-text note / reason
    source_ip: Optional[str] = Field(default=None)  # Client IP address
    prev_hash: str = Field(default="")  # SHA-256 of previous entry; "0"*64 for genesis
    entry_hash: str = Field(default="")  # SHA-256 of this entry (excl. id + entry_hash)


class ApprovalRequestRow(SQLModel, table=True):
    """Pending dual-control approval step.

    When a dual-control role's first approve arrives a row is written here.
    The second operator's approve checks for an active (non-expired, non-consumed)
    row from a *different* operator and, if found, proceeds with actual approval.
    """

    __tablename__ = "approval_request"

    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: str = Field(index=True)
    operator_cn: str
    role: str
    hostname: Optional[str] = Field(default=None)
    assigned_ip: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    consumed: bool = Field(default=False)

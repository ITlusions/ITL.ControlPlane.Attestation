"""Operator, audit-log, and dual-control approval models.

These tables support:
  - per-operator identity (OperatorRow)
  - append-only audit log  (AuditLogRow)
  - dual-control approvals (ApprovalRequestRow)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class OperatorRow(SQLModel, table=True):
    """Persisted operator record.

    operator_id is a UUID assigned at creation.
    name        is the human-readable display name / login (used as CN in issued certs).
    cert_pem    stores the most-recently issued mTLS client cert PEM (nullable).
    cert_serial stores the serial number of that cert as a decimal string.
    oidc_sub    stores the Keycloak subject claim so OIDC tokens can be mapped here.
    """

    __tablename__ = "operator"

    id:          Optional[int] = Field(default=None, primary_key=True)
    operator_id: str           = Field(index=True, unique=True)
    name:        str           = Field(index=True, unique=True)
    cert_pem:    Optional[str] = Field(default=None)
    cert_serial: Optional[str] = Field(default=None)
    oidc_sub:    Optional[str] = Field(default=None, index=True)
    created_at:  datetime      = Field(default_factory=datetime.utcnow)


class AuditLogRow(SQLModel, table=True):
    """Append-only audit log entry for every admin operation.

    This table must never be updated or deleted from — only INSERTs are allowed.
    operator_cn is "SYSTEM" for break-glass (ITL_ADMIN_TOKEN) actions.
    """

    __tablename__ = "audit_log"

    id:          Optional[int] = Field(default=None, primary_key=True)
    timestamp:   datetime      = Field(default_factory=datetime.utcnow)
    operator_cn: str           # "SYSTEM" | operator name/CN | Keycloak preferred_username
    action:      str           # "approve", "revoke", "lock", "unlock", "wipe", "import"
    machine_id:  Optional[str] = Field(default=None)
    prev_state:  Optional[str] = Field(default=None)
    new_state:   Optional[str] = Field(default=None)
    detail:      Optional[str] = Field(default=None)  # free-text note / reason


class ApprovalRequestRow(SQLModel, table=True):
    """Pending dual-control approval step.

    When a dual-control role's first approve arrives a row is written here.
    The second operator's approve checks for an active (non-expired, non-consumed)
    row from a *different* operator and, if found, proceeds with actual approval.
    """

    __tablename__ = "approval_request"

    id:          Optional[int] = Field(default=None, primary_key=True)
    machine_id:  str           = Field(index=True)
    operator_cn: str
    role:        str
    hostname:    Optional[str] = Field(default=None)
    assigned_ip: Optional[str] = Field(default=None)
    created_at:  datetime      = Field(default_factory=datetime.utcnow)
    expires_at:  datetime
    consumed:    bool          = Field(default=False)

"""ORM row for machine records — SQLModel table definition."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NodeRole(str, enum.Enum):
    controlplane = "controlplane"
    worker_infra = "worker-infra"
    worker_app   = "worker-app"


class MachineStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    registered       = "registered"
    attested         = "attested"
    rejected         = "rejected"
    locked           = "locked"   # temporary suspension — unlockable without fresh USB
    revoked          = "revoked"  # permanent removal; attest returns action=wipe when wipe_pending=True


class MachineRow(SQLModel, table=True):
    """Persisted machine record keyed on TPM EK fingerprint."""

    __tablename__ = "machine"  # preserve existing DB table name on rename from Machine

    id:             Optional[int] = Field(default=None, primary_key=True)
    machine_id:     str           = Field(index=True, unique=True)   # UUID v4
    ek_fingerprint: str           = Field(index=True, unique=True)   # SHA-384 hex (CNSA 1.0)
    ek_source:      str           = Field(default="cert")            # "cert" | "pub"

    hw_uuid:        str           = Field(default="unknown")
    hw_mac:         str           = Field(default="unknown")
    hw_serial:      str           = Field(default="unknown")
    hw_product:     str           = Field(default="unknown")

    role:           NodeRole      = Field(default=NodeRole.worker_app)
    status:         MachineStatus = Field(default=MachineStatus.pending_approval)

    hostname:       Optional[str] = Field(default=None)
    assigned_ip:    Optional[str] = Field(default=None)

    # One-time config token — consumed on first Talos config fetch
    config_token:   Optional[str] = Field(default=None, index=True)
    token_consumed: bool          = Field(default=False)

    registered_at:  datetime           = Field(default_factory=datetime.utcnow)
    attested_at:    Optional[datetime] = Field(default=None)
    locked_at:      Optional[datetime] = Field(default=None)
    revoked_at:     Optional[datetime] = Field(default=None)

    # When True and status=revoked, the next POST /attest returns action=wipe
    # so the extension triggers a Talos reset (STATE + EPHEMERAL wipe).
    wipe_pending:   bool = Field(default=False)

    # AK (Attestation Key) public key — SubjectPublicKeyInfo PEM; populated by
    # POST /api/v1/machines/{id}/ak-activate (issue #6).
    # NOTE: add Alembic migration when adding this column to an existing DB.
    ak_pub:         Optional[str] = Field(default=None)

    # EK certificate PEM (base64-encoded) — stored for EK-bound config encryption (issue #9).
    # NOTE: add Alembic migration when adding this column to an existing DB.
    ek_cert_pem:    Optional[str] = Field(default=None)

    # SHA-384 EK fingerprint (CNSA 1.0, issue #8) — canonical identity for new registrations.
    # Populated by the migration script (migrations/001_add_ek_fingerprint_sha384.py) for
    # existing rows.  New rows have this set equal to ek_fingerprint (both are SHA-384).
    # NOTE: add Alembic migration when adding this column to an existing DB.
    ek_fingerprint_sha384: Optional[str] = Field(default=None, index=True)

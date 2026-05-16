"""ORM models for machines — SQLModel table definitions."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class NodeRole(str, enum.Enum):
    """Node role — covers Talos cluster nodes and generic/OS-specific bare-metal nodes."""

    # Talos / Kubernetes roles
    controlplane = "controlplane"
    worker_infra = "worker-infra"
    worker_app = "worker-app"

    # Generic / OS-specific roles (non-Talos)
    generic = "generic"
    windows = "windows"
    linux = "linux"


class MachineStatus(str, enum.Enum):
    """Machine attestation lifecycle status."""

    pending_approval = "pending_approval"  # Awaiting operator approval
    registered = "registered"  # Approved but not yet attested
    attested = "attested"  # Successfully attested
    rejected = "rejected"  # Operator rejected
    locked = "locked"  # Temporary suspension — unlockable
    revoked = "revoked"  # Permanent removal; attest returns action=wipe when wipe_pending=True


class MachineRow(SQLModel, table=True):
    """Persisted machine record keyed on TPM EK fingerprint.

    This is the central identity record for a bare-metal node seeking to join
    the Talos cluster.  The machine_id is a stable UUID v4 assigned at first
    registration; ek_fingerprint is the SHA-384 fingerprint of the TPM EK cert
    (or EK public key if no cert is available).

    Lifecycle:
      1. Machine boots with USB Attestation Extension, sends POST /register
      2. Operator approves via web UI, status becomes 'registered'
      3. Machine sends POST /attest with TPM quote, status becomes 'attested'
      4. Machine fetches Talos config via GET /config with config_token
      5. Machine joins cluster and runs workloads

    Status transitions:
      - pending_approval -> registered  (operator approval)
      - registered       -> attested    (successful attestation)
      - attested         -> locked      (operator suspends temporarily)
      - locked           -> attested    (operator unlocks)
      - *                -> revoked     (permanent removal, optionally with wipe)
    """

    __tablename__ = "machine"  # Preserve existing DB table name

    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: str = Field(index=True, unique=True)  # UUID v4
    ek_fingerprint: str = Field(index=True, unique=True)  # SHA-384 hex (CNSA 1.0)
    ek_source: str = Field(default="cert")  # "cert" | "pub"

    hw_uuid: str = Field(default="unknown")
    hw_mac: str = Field(default="unknown")
    hw_serial: str = Field(default="unknown")
    hw_product: str = Field(default="unknown")

    role: NodeRole = Field(default=NodeRole.worker_app)
    status: MachineStatus = Field(default=MachineStatus.pending_approval)

    hostname: Optional[str] = Field(default=None)
    assigned_ip: Optional[str] = Field(default=None)

    # One-time config token — consumed on first Talos config fetch
    config_token: Optional[str] = Field(default=None, index=True)
    token_consumed: bool = Field(default=False)

    registered_at: datetime = Field(default_factory=datetime.utcnow)
    attested_at: Optional[datetime] = Field(default=None)
    locked_at: Optional[datetime] = Field(default=None)
    revoked_at: Optional[datetime] = Field(default=None)

    # When True and status=revoked, the next POST /attest returns action=wipe
    # so the extension triggers a Talos reset (STATE + EPHEMERAL wipe).
    wipe_pending: bool = Field(default=False)

    # AK (Attestation Key) public key — SubjectPublicKeyInfo PEM
    ak_pub: Optional[str] = Field(default=None)

    # EK certificate PEM (base64-encoded) — stored for EK-bound config encryption
    ek_cert_pem: Optional[str] = Field(default=None)

    # SHA-384 EK fingerprint (CNSA 1.0) — canonical identity for new registrations
    ek_fingerprint_sha384: Optional[str] = Field(default=None, index=True)

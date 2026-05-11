"""Pydantic schemas and SQLModel database models for the Attestation Service."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator
from sqlmodel import Field, SQLModel


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class NodeRole(str, enum.Enum):
    controlplane = "controlplane"
    worker_infra = "worker-infra"
    worker_app   = "worker-app"


class MachineStatus(str, enum.Enum):
    pending_approval = "pending_approval"
    registered       = "registered"
    attested         = "attested"
    rejected         = "rejected"
    locked           = "locked"     # temporary suspension — unlockable without fresh USB
    revoked          = "revoked"    # permanent removal; attest returns action=wipe when wipe_pending=True


# ─────────────────────────────────────────────────────────────────────────────
# Database model
# ─────────────────────────────────────────────────────────────────────────────

class Machine(SQLModel, table=True):
    """Persisted machine record keyed on TPM EK fingerprint."""

    id:             Optional[int] = Field(default=None, primary_key=True)
    machine_id:     str           = Field(index=True, unique=True)   # UUID v4
    ek_fingerprint: str           = Field(index=True, unique=True)   # SHA-256 hex
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

    registered_at:  datetime      = Field(default_factory=datetime.utcnow)
    attested_at:    Optional[datetime] = Field(default=None)
    locked_at:      Optional[datetime] = Field(default=None)
    revoked_at:     Optional[datetime] = Field(default=None)

    # When True and status=revoked, the next POST /attest returns action=wipe
    # so the extension triggers a Talos reset (STATE + EPHEMERAL wipe).
    wipe_pending:   bool              = Field(default=False)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response schemas
# ─────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    ek_fingerprint: str
    ek_cert_pem:    str           = ""    # base64-encoded PEM; empty when no TPM present
    ek_source:      str           = "cert"
    hw_uuid:        str           = "unknown"
    hw_mac:         str           = "unknown"
    hw_serial:      str           = "unknown"
    hw_product:     str           = "unknown"
    desired_role:   Optional[str] = None

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char hex SHA-256 digest")
        return v


class RegisterResponse(BaseModel):
    machine_id:   str
    role:         str
    status:       str
    iso_url:      str
    config_token: str
    config_url:   str
    message:      str


class SelfRegisterRequest(BaseModel):
    """Registration request sent by the itl-tpm-register Talos extension.

    Unlike RegisterRequest (USB agent), this does not trigger an Image Factory
    call — the machine is already booted.  After approval the extension calls
    POST /api/v1/attest periodically; when the response is 'attested' it uses
    the returned config_token to fetch and apply the full MachineConfig via
    talosctl apply-config.
    """
    ek_fingerprint: str
    ek_cert_pem:    str
    ek_source:      str           = "cert"
    hw_uuid:        str           = "unknown"
    hw_mac:         str           = "unknown"
    hw_serial:      str           = "unknown"
    hw_product:     str           = "unknown"
    desired_role:   Optional[str] = None

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char hex SHA-256 digest")
        return v


class SelfRegisterResponse(BaseModel):
    machine_id:   str
    role:         str
    status:       str
    config_token: Optional[str]
    config_url:   Optional[str]
    message:      str


class AttestRequest(BaseModel):
    ek_fingerprint: str
    ek_cert_pem:    str
    ek_source:      str           = "cert"
    pcr_quote:      Optional[str] = None  # base64-encoded TPM2B_ATTEST
    pcr_signature:  Optional[str] = None  # base64-encoded TPMT_SIGNATURE
    pcr_nonce:      Optional[str] = None
    hw_uuid:        str           = "unknown"
    hw_mac:         str           = "unknown"
    hw_serial:      str           = "unknown"
    hw_product:     str           = "unknown"

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char hex SHA-256 digest")
        return v


class AttestResponse(BaseModel):
    machine_id:   str
    status:       str
    hostname:     Optional[str]
    role:         str
    message:      str
    # action instructs the Talos extension what to do after attestation.
    # "none"       — normal operation
    # "apply-config" — machine just attested; fetch config_url and apply with talosctl
    # "wipe"       — machine revoked with wipe_pending=True; extension calls talosctl reset
    # "lock"       — machine locked; extension writes lock flag and halts enrollment
    action:       str           = "none"
    # Populated when action="apply-config" — one-time URL for the full MachineConfig YAML.
    # Extension should call: talosctl apply-config --insecure --file <(curl -sf config_url)
    config_url:   Optional[str] = None
    config_token: Optional[str] = None


class RevokeRequest(BaseModel):
    """Operator request to revoke a machine.

    wipe: bool — when True, the next POST /attest returns action=wipe.
          The Talos extension will call talosctl reset --graceful=false on receipt,
          wiping STATE and EPHEMERAL and rebooting the node into maintenance mode.
          When False, the machine is simply blocked from re-attesting without
          triggering a destructive operation.
    reason: optional free-text audit note.
    """
    wipe:   bool          = False
    reason: Optional[str] = None


class LockRequest(BaseModel):
    """Operator request to temporarily lock a machine.

    Locking is a reversible suspension — the machine is blocked from attestation
    and cert issuance until an operator calls POST /unlock.  No data is destroyed.
    reason: optional free-text audit note.
    """
    reason: Optional[str] = None


class MachineDetail(BaseModel):
    machine_id:     str
    ek_fingerprint: str
    hw_uuid:        str
    hw_mac:         str
    hw_serial:      str
    hw_product:     str
    role:           str
    status:         str
    hostname:       Optional[str]
    assigned_ip:    Optional[str]
    registered_at:  datetime
    attested_at:    Optional[datetime]
    locked_at:      Optional[datetime]
    revoked_at:     Optional[datetime]
    wipe_pending:   bool


class ApproveRequest(BaseModel):
    role:        NodeRole
    hostname:    Optional[str] = None
    assigned_ip: Optional[str] = None


class CertRequest(BaseModel):
    """Machine-authenticated cert request — no admin token required.

    The machine re-presents its EK material to prove it is the same physical
    hardware that originally registered.  The service verifies the EK cert
    signature and fingerprint against the stored record before issuing a cert.

    Transport encryption (Layer 1)
    ──────────────────────────────
    If wrapping_key_pem is supplied, the service encrypts the enrollment private
    key with RSA-OAEP-SHA256 before returning it.  The wrapping key must be a
    TPM-resident unrestricted RSA-2048 decrypt key (fixedtpm|fixedparent|noda)
    whose private component never leaves the TPM.  The client decrypts with:

      tpm2_rsadecrypt --key-context <ctx> --input enrollment.key.enc --output enrollment.key

    When wrapping_key_pem is empty the enrollment key is returned as plaintext
    PEM (protected only by TLS).
    """
    ek_fingerprint:   str
    ek_cert_pem:      str = ""  # base64-encoded PEM — re-verified server-side; empty for no-TPM nodes
    ek_source:        str = "cert"
    wrapping_key_pem: str = ""  # SubjectPublicKeyInfo PEM of client TPM RSA-2048 OAEP decrypt key

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char hex SHA-256 digest")
        return v


class CertResponse(BaseModel):
    """Enrollment certificate + CA cert returned to the requesting machine.

    Exactly one of enrollment_key_pem / enrollment_key_encrypted_b64 is populated:
      enrollment_key_pem           non-empty when no wrapping key was provided (TLS-only protection)
      enrollment_key_encrypted_b64 non-empty when the client supplied wrapping_key_pem;
                                   contains the RSA-OAEP-SHA256 ciphertext of the key PEM (base64).
    """
    machine_id:                   str
    role:                         str
    enrollment_cert_pem:          str
    enrollment_key_pem:           str
    enrollment_key_encrypted_b64: str
    enrollment_ca_pem:            str
    valid_days:                   int
    message:                      str

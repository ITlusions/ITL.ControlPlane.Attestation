"""Pydantic response schemas for the Attestation Service."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RegisterResponse(BaseModel):
    machine_id:   str
    role:         str
    status:       str
    iso_url:      str
    config_token: str
    config_url:   str
    message:      str


class SelfRegisterResponse(BaseModel):
    machine_id:   str
    role:         str
    status:       str
    config_token: Optional[str]
    config_url:   Optional[str]
    message:      str


class AttestResponse(BaseModel):
    machine_id:   str
    status:       str
    hostname:     Optional[str]
    role:         str
    message:      str
    # action instructs the Talos extension what to do after attestation.
    # "none"         — normal operation
    # "apply-config" — machine just attested; fetch config_url and apply with talosctl
    # "wipe"         — machine revoked with wipe_pending=True; extension calls talosctl reset
    # "lock"         — machine locked; extension writes lock flag and halts enrollment
    action:       str           = "none"
    # Populated when action="apply-config" — one-time URL for the full MachineConfig YAML.
    config_url:   Optional[str] = None
    config_token: Optional[str] = None


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


class PendingApprovalResponse(BaseModel):
    """Returned (HTTP 202) when the first operator approves a dual-control machine."""

    machine_id:         str
    status:             str       # always "pending_second_approval"
    message:            str
    approvals_received: int
    approvals_required: int
    expires_at:         datetime


class AuditLogEntry(BaseModel):
    """A single entry from the append-only audit log."""

    id:          int
    timestamp:   datetime
    operator_cn: str
    action:      str
    machine_id:  Optional[str]
    prev_state:  Optional[str]
    new_state:   Optional[str]
    detail:      Optional[str]
    prev_hash:   str
    entry_hash:  str


class AuditVerifyResult(BaseModel):
    """Result of walking the full audit log hash chain."""

    valid:            bool
    entries:          int
    root_hash:        Optional[str]
    first_invalid_id: Optional[int] = None
    error:            Optional[str] = None


class ApprovalDetail(BaseModel):
    """A pending or historical dual-control approval request."""

    id:          int
    machine_id:  str
    operator_cn: str
    role:        str
    hostname:    Optional[str]
    assigned_ip: Optional[str]
    created_at:  datetime
    expires_at:  datetime
    consumed:    bool

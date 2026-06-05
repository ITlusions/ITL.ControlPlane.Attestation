"""Pydantic request schemas for the Attestation Service."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator

from ..models.machine import NodeRole


class RegisterRequest(BaseModel):
    ek_fingerprint: str
    ek_cert_pem:    str           # base64-encoded PEM/DER; required — no TPM-less registration
    ek_source:      str           = "cert"
    hw_uuid:        str           = "unknown"
    hw_mac:         str           = "unknown"
    hw_serial:      str           = "unknown"
    hw_product:     str           = "unknown"
    desired_role:   Optional[str] = None
    cluster_id:     str           = "default"  # target cluster for this machine

    @field_validator("ek_source")
    @classmethod
    def validate_ek_source(cls, v: str) -> str:
        if v not in ("cert", "pub"):
            raise ValueError("ek_source must be 'cert' or 'pub'")
        return v

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        # Accept SHA-384 (96 chars, CNSA 2.0) and legacy SHA-256 (64 chars)
        if len(v) not in (64, 96) or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char (SHA-256) or 96-char (SHA-384) hex digest")
        return v


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
    cluster_id:     str           = "default"  # target cluster for this machine

    @field_validator("ek_source")
    @classmethod
    def validate_ek_source(cls, v: str) -> str:
        if v not in ("cert", "pub"):
            raise ValueError("ek_source must be 'cert' or 'pub'")

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) not in (64, 96) or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char (SHA-256) or 96-char (SHA-384) hex digest")
        return v


class AttestRequest(BaseModel):
    ek_fingerprint: str
    ek_cert_pem:    str
    ek_source:      str           = "cert"
    nonce_id:       Optional[str] = None  # issue #7: server-issued challenge nonce ID
    nonce_signature: Optional[str] = None  # base64 ECDSA-SHA384 or RSA-PKCS1v15 sig over nonce
    pcr_quote:      Optional[str] = None  # base64-encoded TPM2B_ATTEST (issue #6)
    pcr_signature:  Optional[str] = None  # base64-encoded TPMT_SIGNATURE
    hw_uuid:        str           = "unknown"
    hw_mac:         str           = "unknown"
    hw_serial:      str           = "unknown"
    hw_product:     str           = "unknown"

    @field_validator("ek_source")
    @classmethod
    def validate_ek_source(cls, v: str) -> str:
        if v not in ("cert", "pub"):
            raise ValueError("ek_source must be 'cert' or 'pub'")
        return v

    @field_validator("ek_fingerprint")
    @classmethod
    def validate_fingerprint(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) not in (64, 96) or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char (SHA-256) or 96-char (SHA-384) hex digest")
        return v


class ApproveRequest(BaseModel):
    role:        NodeRole
    hostname:    Optional[str] = None
    assigned_ip: Optional[str] = None


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
        if len(v) not in (64, 96) or not all(c in "0123456789abcdef" for c in v):
            raise ValueError("ek_fingerprint must be a 64-char (SHA-256) or 96-char (SHA-384) hex digest")
        return v

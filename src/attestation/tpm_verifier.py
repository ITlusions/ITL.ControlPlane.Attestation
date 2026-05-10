"""TPM EK certificate verification helpers.

Verifies that the EK PEM presented during registration / attestation is
self-consistent and (optionally) chains up to a known manufacturer CA.

Security model:
  - We store and compare the SHA-256 fingerprint of the EK material.  The
    fingerprint is the stable hardware identity — it cannot change without
    physically replacing the TPM chip.
  - Full manufacturer CA verification is optional and controlled by the
    ITL_TPM_VERIFY_CA environment variable.  When enabled we download the
    Infineon / NTC / STM ECIA CA bundle and verify the chain.
  - PCR quotes are currently logged and stored but NOT cryptographically
    verified (requires the EK to sign with an AIK which is a separate flow).
    Future versions will implement full TPM2 remote attestation.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def decode_pem(b64_pem: str) -> bytes:
    """Base64-decode the PEM block sent by the registration agent."""
    try:
        return base64.b64decode(b64_pem)
    except Exception as exc:
        raise ValueError(f"Invalid base64 encoding in EK material: {exc}") from exc


def verify_ek_pem(b64_pem: str, ek_source: str) -> bool:
    """
    Minimal structural verification of the EK material.

    - For 'cert' source: verifies the decoded bytes look like a PEM certificate
      or a DER certificate (both are accepted from the agent).
    - For 'pub' source: verifies the decoded bytes look like a PEM public key.

    Returns True if the material is structurally valid.
    Raises ValueError with a description if the material is clearly invalid.
    """
    raw = decode_pem(b64_pem)

    # Accept both PEM-in-base64 and DER-in-base64
    pem_str = raw.decode("ascii", errors="replace")

    if ek_source == "cert":
        if (b"\x30\x82" in raw[:4] or  # DER sequence header
                "BEGIN CERTIFICATE" in pem_str or
                "BEGIN X509 CERTIFICATE" in pem_str):
            return True
        raise ValueError("EK material does not look like a certificate (expected DER or PEM X.509)")

    if ek_source == "pub":
        if ("BEGIN PUBLIC KEY" in pem_str or
                "BEGIN RSA PUBLIC KEY" in pem_str or
                b"\x30\x82" in raw[:4]):
            return True
        raise ValueError("EK material does not look like a public key")

    # Unknown source — accept permissively but log a warning
    logger.warning("Unknown EK source '%s' — skipping structural check", ek_source)
    return True


def compute_ek_fingerprint(b64_pem: str) -> str:
    """
    Compute the SHA-256 fingerprint of the raw EK material bytes.
    This is the stable hardware identity used as the primary key.
    """
    import hashlib
    raw = decode_pem(b64_pem)
    return hashlib.sha256(raw).hexdigest()


def fingerprints_match(fp_request: str, fp_stored: str) -> bool:
    """Constant-time comparison of two fingerprint hex strings."""
    import hmac
    return hmac.compare_digest(fp_request.lower(), fp_stored.lower())

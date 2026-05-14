"""TPM EK certificate verification helpers.

Verifies that the EK PEM presented during registration / attestation is
structurally valid and (optionally) chains up to a known manufacturer CA.

Security model:
  - EK certificates are fully parsed using ``cryptography.x509``; header-
    sniffing is not used.  This closes a bypass where crafted material with
    the right magic bytes would pass validation.
  - Key Usage ``keyEncipherment`` is enforced per TCG EK Credential Profile.
  - Certificate validity dates (notBefore / notAfter) are enforced.
  - We store and compare a SHA-384 fingerprint (CNSA 2.0) of the raw EK
    material.  The fingerprint is the stable hardware identity — it cannot
    change without physically replacing the TPM chip.
  - Full manufacturer CA verification is optional and controlled by the
    ``ITL_TPM_VERIFY_CA`` environment variable.  When enabled the service
    verifies the chain against DER/PEM CA certificates in
    ``ITL_TPM_CA_BUNDLE_DIR``.
  - If ``ITL_TPM_VERIFY_CA_STRICT=true`` and the bundle dir is empty the
    service will raise on startup via ``check_ca_bundle_on_startup()``.

Issue refs: #1 (X.509 parse), #3 (CA chain), #8 (SHA-384 fingerprint)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CA bundle configuration (issue #3)
# ---------------------------------------------------------------------------
_VERIFY_CA       = os.environ.get("ITL_TPM_VERIFY_CA",        "false").lower() == "true"
_VERIFY_CA_STRICT = os.environ.get("ITL_TPM_VERIFY_CA_STRICT", "false").lower() == "true"
_CA_BUNDLE_DIR   = Path(os.environ.get("ITL_TPM_CA_BUNDLE_DIR", "/var/lib/itl-reg/ca-bundles"))

_ca_certs: Optional[list[x509.Certificate]] = None


def _load_ca_bundle() -> list[x509.Certificate]:
    """Load all DER/PEM CA certs from ``_CA_BUNDLE_DIR`` (cached)."""
    global _ca_certs
    if _ca_certs is not None:
        return _ca_certs
    certs: list[x509.Certificate] = []
    if not _CA_BUNDLE_DIR.exists():
        return certs
    for path in _CA_BUNDLE_DIR.iterdir():
        if not path.is_file():
            continue
        data = path.read_bytes()
        try:
            certs.append(x509.load_der_x509_certificate(data))
            continue
        except Exception:
            pass
        try:
            certs.append(x509.load_pem_x509_certificate(data))
        except Exception:
            logger.warning("Cannot load CA cert from %s — skipping", path)
    _ca_certs = certs
    return certs


def check_ca_bundle_on_startup() -> None:
    """Call at application startup when ``ITL_TPM_VERIFY_CA=true``.

    Logs a warning if the bundle dir is empty and raises ``RuntimeError`` when
    ``ITL_TPM_VERIFY_CA_STRICT=true``.
    """
    if not _VERIFY_CA:
        return
    certs = _load_ca_bundle()
    if not certs:
        msg = (
            f"ITL_TPM_VERIFY_CA=true but no CA certs found in {_CA_BUNDLE_DIR}. "
            "EK chain verification will always fail."
        )
        if _VERIFY_CA_STRICT:
            raise RuntimeError(msg)
        logger.warning(msg)
    else:
        logger.info("TPM manufacturer CA bundle loaded: %d cert(s) from %s", len(certs), _CA_BUNDLE_DIR)


def _verify_ek_cert_chain(cert: x509.Certificate) -> None:
    """Verify that ``cert`` chains to one of the loaded manufacturer CAs.

    Raises ``ValueError`` if no chain can be established.
    Only performs issuer/subject matching + signature verification — full
    path-building (intermediates) is not yet supported.
    """
    ca_certs = _load_ca_bundle()
    if not ca_certs:
        raise ValueError(
            "EK CA chain verification enabled but bundle is empty — "
            "populate ITL_TPM_CA_BUNDLE_DIR with manufacturer CA certs"
        )
    for ca in ca_certs:
        if ca.subject != cert.issuer:
            continue
        # Verify the certificate signature against this CA's public key
        try:
            ca_pub = ca.public_key()
            if isinstance(ca_pub, RSAPublicKey):
                from cryptography.hazmat.primitives.asymmetric import padding as _p, hashes as _h
                ca_pub.verify(cert.signature, cert.tbs_certificate_bytes, _p.PKCS1v15(), cert.signature_hash_algorithm)  # type: ignore[arg-type]
            elif isinstance(ca_pub, EllipticCurvePublicKey):
                from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
                ca_pub.verify(cert.signature, cert.tbs_certificate_bytes, ECDSA(cert.signature_hash_algorithm))  # type: ignore[arg-type]
            else:
                continue  # unsupported key type — skip
            return  # chain established
        except Exception:
            continue  # signature did not verify — try next CA
    raise ValueError(
        f"EK certificate issuer '{cert.issuer.rfc4514_string()}' "
        "does not match any trusted manufacturer CA"
    )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def decode_pem(b64_pem: str) -> bytes:
    """Base64-decode the PEM/DER block sent by the registration agent."""
    try:
        return base64.b64decode(b64_pem)
    except Exception as exc:
        raise ValueError(f"Invalid base64 encoding in EK material: {exc}") from exc


def _parse_ek_cert(raw: bytes) -> x509.Certificate:
    """Parse raw bytes as DER (preferred) or PEM X.509 certificate."""
    try:
        return x509.load_der_x509_certificate(raw)
    except Exception:
        pass
    try:
        return x509.load_pem_x509_certificate(raw)
    except Exception as exc:
        raise ValueError(f"Cannot parse EK certificate: {exc}") from exc


def verify_ek_pem(b64_pem: str, ek_source: str) -> bool:
    """Verify EK material structurally and (optionally) against manufacturer CAs.

    For ``ek_source == 'cert'``:
      - Fully parses the X.509 certificate (DER or PEM)
      - Enforces Key Usage ``keyEncipherment`` (TCG EK Credential Profile)
      - Enforces certificate validity dates
      - When ``ITL_TPM_VERIFY_CA=true``, verifies chain against manufacturer CAs

    For ``ek_source == 'pub'``:
      - Decodes and parses the SubjectPublicKeyInfo structure

    Returns ``True`` on success.  Raises ``ValueError`` on any failure.
    """
    raw = decode_pem(b64_pem)

    if ek_source == "cert":
        cert = _parse_ek_cert(raw)

        # Enforce Key Usage: keyEncipherment required per TCG EK Credential Profile
        try:
            ku = cert.extensions.get_extension_for_class(x509.KeyUsage)
            if not ku.value.key_encipherment:
                raise ValueError("EK cert Key Usage does not include keyEncipherment")
        except x509.ExtensionNotFound:
            logger.warning("EK cert has no Key Usage extension — proceeding with warning")

        # Enforce certificate validity window
        now = datetime.now(timezone.utc)
        if now > cert.not_valid_after_utc:
            raise ValueError(
                f"EK certificate expired at {cert.not_valid_after_utc.isoformat()}"
            )
        if now < cert.not_valid_before_utc:
            raise ValueError(
                f"EK certificate not yet valid (valid from {cert.not_valid_before_utc.isoformat()})"
            )

        # Optional CA chain verification (issue #3)
        if _VERIFY_CA:
            _verify_ek_cert_chain(cert)

        return True

    if ek_source == "pub":
        from cryptography.hazmat.primitives.serialization import load_der_public_key, load_pem_public_key
        try:
            load_der_public_key(raw)
            return True
        except Exception:
            pass
        try:
            load_pem_public_key(raw)
            return True
        except Exception as exc:
            raise ValueError(f"Cannot parse EK public key: {exc}") from exc

    # HIGH-02/RT-04: Reject unknown ek_source immediately — do not silently pass
    raise ValueError(
        f"Unknown ek_source value '{ek_source}' \u2014 expected 'cert' or 'pub'"
    )


def compute_ek_fingerprint(b64_pem: str) -> str:
    """Compute the SHA-384 fingerprint of the raw EK material bytes.

    SHA-384 is used per CNSA 2.0 (issue #8).  The fingerprint is the stable
    hardware identity stored as the primary DB key.
    """
    raw = decode_pem(b64_pem)
    return hashlib.sha384(raw).hexdigest()


def fingerprints_match(fp_request: str, fp_stored: str) -> bool:
    """Constant-time comparison of two fingerprint hex strings."""
    return hmac.compare_digest(fp_request.lower(), fp_stored.lower())


def load_ek_public_key(b64_pem: str) -> RSAPublicKey | EllipticCurvePublicKey:
    """Extract the public key from a base64-encoded EK certificate or SubjectPublicKeyInfo PEM.

    Tries X.509 certificate parsing first (``ek_source='cert'``), then falls
    back to bare SubjectPublicKeyInfo DER/PEM (``ek_source='pub'``).

    Returns a ``cryptography`` public key object suitable for RSA-OAEP-SHA256
    key wrapping or EC operations.

    Raises ``ValueError`` if the material cannot be parsed.
    """
    raw = decode_pem(b64_pem)

    # Try X.509 certificate first
    try:
        cert = _parse_ek_cert(raw)
        return cert.public_key()  # type: ignore[return-value]
    except ValueError:
        pass

    # Fall back to bare SubjectPublicKeyInfo (DER then PEM)
    from cryptography.hazmat.primitives.serialization import load_der_public_key, load_pem_public_key
    try:
        return load_der_public_key(raw)  # type: ignore[return-value]
    except Exception:
        pass
    try:
        return load_pem_public_key(raw)  # type: ignore[return-value]
    except Exception as exc:
        raise ValueError(f"Cannot extract public key from EK material: {exc}") from exc

"""Enrollment Certificate Authority for offline machine provisioning.

Generates a self-signed Enrollment CA and issues short-lived (30-day) client
certificates for offline USB bundles.  The issued certs are used by the
itl-tpm-register Talos extension to self-enroll into the Attestation Service
without requiring an admin token or prior manual import.

Security model
──────────────
- The enrollment cert is embedded in the Talos machineconfig as a file entry,
  so it is written to disk on the target machine during Talos install.
- The matching private key is also embedded (under /var/lib/itl-tpm/).
- On first boot, tpm-attest.sh signs a random nonce with the private key and
  sends the cert + signature to POST /api/v1/machines/enroll.
- The Attestation Service verifies the cert chain against the Enrollment CA
  and verifies the nonce signature against the cert's public key.
- This proves the caller *possesses the private key*, not just the cert PEM.
- After successful enrollment the private key file is deleted by the script.
- Certs are valid for 30 days (configurable via ITL_ENROLLMENT_CERT_DAYS).

CA key material
───────────────
Persisted at ITL_ENROLLMENT_CA_DIR (default: /var/lib/itl-reg/ca/).
A new CA is auto-generated on first startup and reused on subsequent starts.
The CA is valid for 10 years.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, generate_private_key
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

logger = logging.getLogger(__name__)

CA_DIR       = Path(os.environ.get("ITL_ENROLLMENT_CA_DIR", "/var/lib/itl-reg/ca"))
CA_KEY_PATH  = CA_DIR / "enrollment-ca.key"
CA_CERT_PATH = CA_DIR / "enrollment-ca.crt"

CERT_VALID_DAYS = int(os.environ.get("ITL_ENROLLMENT_CERT_DAYS", "30"))

_ca_key:  Optional[object] = None
_ca_cert: Optional[x509.Certificate] = None


def init_enrollment_ca() -> None:
    """Load or generate the Enrollment CA.  Call once at application startup."""
    global _ca_key, _ca_cert

    CA_DIR.mkdir(parents=True, exist_ok=True)

    if CA_KEY_PATH.exists() and CA_CERT_PATH.exists():
        _ca_key  = serialization.load_pem_private_key(CA_KEY_PATH.read_bytes(), password=None)
        _ca_cert = x509.load_pem_x509_certificate(CA_CERT_PATH.read_bytes())
        logger.info("Enrollment CA loaded from %s (serial=%s)", CA_DIR, _ca_cert.serial_number)
        return

    logger.info("Generating new Enrollment CA at %s", CA_DIR)
    _ca_key = generate_private_key(public_exponent=65537, key_size=4096)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME,      "NL"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ITL Usions"),
        x509.NameAttribute(NameOID.COMMON_NAME,       "ITL Machine Enrollment CA"),
    ])

    now = datetime.now(timezone.utc)
    _ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(_ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False,
                data_encipherment=False,  key_agreement=False,
                encipher_only=False,      decipher_only=False,
            ),
            critical=True,
        )
        .sign(_ca_key, hashes.SHA256())
    )

    CA_KEY_PATH.write_bytes(
        _ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CA_KEY_PATH.chmod(0o600)
    CA_CERT_PATH.write_bytes(_ca_cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Enrollment CA generated (serial=%s)", _ca_cert.serial_number)


def get_ca_cert_pem() -> str:
    """Return the Enrollment CA certificate as a PEM string."""
    if _ca_cert is None:
        raise RuntimeError("Enrollment CA not initialised — call init_enrollment_ca() first")
    return _ca_cert.public_bytes(serialization.Encoding.PEM).decode()


def issue_enrollment_cert(
    machine_id: str,
    role: str,
    ek_fingerprint: str = "",
) -> tuple[str, str]:
    """Issue a short-lived enrollment certificate for a machine.

    Returns (cert_pem, key_pem) as strings.
    The certificate encodes CN=machine_id, OU=role, EKU=clientAuth,
    and a URI SAN binding it to the TPM EK fingerprint.
    """
    if _ca_key is None or _ca_cert is None:
        raise RuntimeError("Enrollment CA not initialised")

    key = generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME,             "NL"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME,        "ITL Usions"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, role),
        x509.NameAttribute(NameOID.COMMON_NAME,              machine_id),
    ])

    now = datetime.now(timezone.utc)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(_ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=CERT_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,  key_cert_sign=False, crl_sign=False,
                content_commitment=False, key_encipherment=True,
                data_encipherment=False,  key_agreement=False,
                encipher_only=False,      decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(_ca_cert.public_key()),
            critical=False,
        )
    )

    if ek_fingerprint:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([
                x509.UniformResourceIdentifier(f"urn:itl:ek:{ek_fingerprint}"),
            ]),
            critical=False,
        )

    cert = builder.sign(_ca_key, hashes.SHA256())

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem  = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()

    logger.info(
        "Enrollment cert issued: machine_id=%s role=%s serial=%s valid_days=%d ek_bound=%s",
        machine_id, role, cert.serial_number, CERT_VALID_DAYS, bool(ek_fingerprint),
    )
    return cert_pem, key_pem


def verify_enrollment_cert(cert_pem: str) -> dict:
    """Verify an enrollment certificate and extract its claims.

    Returns a dict with: machine_id, role, serial, not_valid_after
    Raises ValueError on any verification failure.
    """
    if _ca_cert is None:
        raise RuntimeError("Enrollment CA not initialised")

    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
    except Exception as exc:
        raise ValueError(f"Cannot parse certificate: {exc}") from exc

    if cert.issuer != _ca_cert.subject:
        raise ValueError("Certificate not issued by ITL Enrollment CA")

    ca_pub = _ca_cert.public_key()
    if not isinstance(ca_pub, RSAPublicKey):
        raise ValueError("Unexpected CA key type")
    try:
        ca_pub.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            asym_padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
    except InvalidSignature as exc:
        raise ValueError("Certificate signature invalid") from exc

    now = datetime.now(timezone.utc)
    if now < cert.not_valid_before_utc:
        raise ValueError("Certificate not yet valid")
    if now > cert.not_valid_after_utc:
        raise ValueError("Certificate has expired")

    def _attr(oid) -> str:
        attrs = cert.subject.get_attributes_for_oid(oid)
        return attrs[0].value if attrs else ""

    machine_id = _attr(NameOID.COMMON_NAME)
    role       = _attr(NameOID.ORGANIZATIONAL_UNIT_NAME)

    if not machine_id:
        raise ValueError("Certificate missing CN (machine_id)")

    return {
        "machine_id":      machine_id,
        "role":            role or "worker-app",
        "serial":          str(cert.serial_number),
        "not_valid_after": cert.not_valid_after_utc.isoformat(),
    }


def verify_nonce_signature(cert_pem: str, nonce: str, nonce_signature_b64: str) -> None:
    """Verify that the caller possesses the private key for the given cert.

    Raises ValueError if the signature is invalid.
    """
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        sig  = base64.b64decode(nonce_signature_b64)
    except Exception as exc:
        raise ValueError(f"Cannot decode cert or signature: {exc}") from exc

    pub_key = cert.public_key()
    if not isinstance(pub_key, RSAPublicKey):
        raise ValueError("Unexpected public key type in enrollment cert")

    try:
        pub_key.verify(
            sig,
            nonce.encode("utf-8"),
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise ValueError("Nonce signature invalid — key mismatch or tampered nonce") from exc


def encrypt_with_rsa_pubkey(plaintext: bytes, rsa_pub_pem: str) -> str:
    """Encrypt plaintext with a client-supplied RSA public key using OAEP-SHA256.

    Returns base64-encoded ciphertext.
    Raises ValueError if the PEM cannot be parsed or is not RSA.
    """
    try:
        pub = serialization.load_pem_public_key(rsa_pub_pem.encode())
    except Exception as exc:
        raise ValueError(f"Cannot parse RSA public key PEM: {exc}") from exc

    if not isinstance(pub, RSAPublicKey):
        raise ValueError("Wrapping key must be RSA — got non-RSA key type")

    ciphertext = pub.encrypt(
        plaintext,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode()

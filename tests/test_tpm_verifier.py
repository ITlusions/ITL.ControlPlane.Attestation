"""Tests for pki/tpm_verifier.py — issue #1, #3."""
from __future__ import annotations

import datetime
import hashlib
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15


def _make_self_signed_cert(
    key,
    *,
    cn: str = "TPM EK",
    key_usage_kwargs: dict | None = None,
    not_before_delta: datetime.timedelta | None = None,
    not_after_delta: datetime.timedelta | None = None,
) -> x509.Certificate:
    ku_kwargs = {
        "digital_signature": False,
        "key_cert_sign": False,
        "crl_sign": False,
        "content_commitment": False,
        "key_encipherment": True,   # required for EK
        "data_encipherment": False,
        "key_agreement": False,
        "encipher_only": False,
        "decipher_only": False,
    }
    if key_usage_kwargs:
        ku_kwargs.update(key_usage_kwargs)

    now = datetime.datetime.now(datetime.timezone.utc)
    nb  = now + (not_before_delta or datetime.timedelta(0))
    na  = now + (not_after_delta  or datetime.timedelta(days=365))

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(nb)
        .not_valid_after(na)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(**ku_kwargs), critical=True)
        .sign(key, hashes.SHA256())
    )


@pytest.fixture()
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def valid_ek_cert_pem(rsa_key):
    cert = _make_self_signed_cert(rsa_key)
    return cert.public_bytes(serialization.Encoding.PEM).decode()


# ------------------------------------------------------------------
# compute_ek_fingerprint — SHA-384 (issue #1 + #8)
# ------------------------------------------------------------------

class TestComputeEkFingerprint:
    def test_returns_96_hex_chars(self, valid_ek_cert_pem):
        from attestation.pki.tpm_verifier import compute_ek_fingerprint
        fp = compute_ek_fingerprint(valid_ek_cert_pem)
        assert len(fp) == 96
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic(self, valid_ek_cert_pem):
        from attestation.pki.tpm_verifier import compute_ek_fingerprint
        assert compute_ek_fingerprint(valid_ek_cert_pem) == compute_ek_fingerprint(valid_ek_cert_pem)

    def test_different_certs_differ(self, rsa_key):
        from attestation.pki.tpm_verifier import compute_ek_fingerprint
        key2   = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert1  = _make_self_signed_cert(rsa_key).public_bytes(serialization.Encoding.PEM).decode()
        cert2  = _make_self_signed_cert(key2).public_bytes(serialization.Encoding.PEM).decode()
        assert compute_ek_fingerprint(cert1) != compute_ek_fingerprint(cert2)


# ------------------------------------------------------------------
# verify_ek_pem — validity + Key Usage (issue #1)
# ------------------------------------------------------------------

class TestVerifyEkPem:
    def test_valid_cert_returns_true(self, valid_ek_cert_pem):
        from attestation.pki.tpm_verifier import verify_ek_pem
        assert verify_ek_pem(valid_ek_cert_pem) is True

    def test_expired_cert_raises(self, rsa_key):
        from attestation.pki.tpm_verifier import verify_ek_pem
        cert = _make_self_signed_cert(
            rsa_key,
            not_before_delta=datetime.timedelta(days=-10),
            not_after_delta=datetime.timedelta(days=-1),
        )
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        with pytest.raises(ValueError, match="expired"):
            verify_ek_pem(pem)

    def test_not_yet_valid_cert_raises(self, rsa_key):
        from attestation.pki.tpm_verifier import verify_ek_pem
        cert = _make_self_signed_cert(
            rsa_key,
            not_before_delta=datetime.timedelta(days=1),
            not_after_delta=datetime.timedelta(days=365),
        )
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        with pytest.raises(ValueError, match="not yet valid"):
            verify_ek_pem(pem)

    def test_missing_key_encipherment_raises(self, rsa_key):
        from attestation.pki.tpm_verifier import verify_ek_pem
        cert = _make_self_signed_cert(
            rsa_key,
            key_usage_kwargs={"key_encipherment": False, "digital_signature": True},
        )
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        with pytest.raises(ValueError, match="[Kk]ey.*[Ee]ncipherment|[Kk]ey[Uu]sage"):
            verify_ek_pem(pem)

    def test_garbage_input_raises(self):
        from attestation.pki.tpm_verifier import verify_ek_pem
        with pytest.raises((ValueError, Exception)):
            verify_ek_pem("not-a-cert")

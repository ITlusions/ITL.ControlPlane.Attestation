"""Tests for schemas/requests.py — fingerprint validator + EK cert requirement.

Issue ref: #2, #8
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from attestation.schemas.requests import (
    AttestRequest,
    CertRequest,
    RegisterRequest,
)

SHA256_FP = "a" * 64
SHA384_FP = "b" * 96


# ------------------------------------------------------------------
# RegisterRequest
# ------------------------------------------------------------------

class TestRegisterRequest:
    def test_accepts_sha256_fingerprint(self):
        req = RegisterRequest(
            ek_fingerprint=SHA256_FP,
            ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
            hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
        )
        assert req.ek_fingerprint == SHA256_FP

    def test_accepts_sha384_fingerprint(self):
        req = RegisterRequest(
            ek_fingerprint=SHA384_FP,
            ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
            hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
        )
        assert req.ek_fingerprint == SHA384_FP

    def test_rejects_missing_ek_cert_pem(self):
        with pytest.raises((ValidationError, TypeError)):
            RegisterRequest(
                ek_fingerprint=SHA256_FP,
                hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
            )

    def test_rejects_invalid_fingerprint_length(self):
        with pytest.raises(ValidationError, match="ek_fingerprint"):
            RegisterRequest(
                ek_fingerprint="abc123",
                ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
                hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
            )

    def test_rejects_non_hex_fingerprint(self):
        with pytest.raises(ValidationError, match="ek_fingerprint"):
            RegisterRequest(
                ek_fingerprint="z" * 64,
                ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
                hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
            )


# ------------------------------------------------------------------
# AttestRequest
# ------------------------------------------------------------------

class TestAttestRequest:
    def test_accepts_sha384_fingerprint(self):
        req = AttestRequest(
            ek_fingerprint=SHA384_FP,
            ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
            hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
        )
        assert req.ek_fingerprint == SHA384_FP

    def test_nonce_id_optional(self):
        req = AttestRequest(
            ek_fingerprint=SHA256_FP,
            ek_cert_pem="-----BEGIN CERTIFICATE-----\ndummy\n-----END CERTIFICATE-----",
            hw_uuid="u", hw_mac="m", hw_serial="s", hw_product="p",
        )
        assert req.nonce_id is None


# ------------------------------------------------------------------
# CertRequest
# ------------------------------------------------------------------

class TestCertRequest:
    def test_accepts_sha384_fingerprint(self):
        req = CertRequest(ek_fingerprint=SHA384_FP)
        assert req.ek_fingerprint == SHA384_FP

    def test_rejects_short_fingerprint(self):
        with pytest.raises(ValidationError):
            CertRequest(ek_fingerprint="a" * 10)

"""Tests for extract_ek_fingerprint_from_cert and EK fingerprint cross-check in enroll.

Issue ref: #4 — security: cross-check EK fingerprint from enrollment cert URI SAN during /enroll
"""
from __future__ import annotations

import base64
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives import hashes, serialization
from fastapi import HTTPException

from attestation.pki.enrollment_ca import (
    extract_ek_fingerprint_from_cert,
    issue_enrollment_cert,
)
from attestation.handlers.enrollment import EnrollmentHandler
from attestation.models.machine import MachineRow, MachineStatus, NodeRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sign_nonce(key, nonce: str) -> str:
    """Sign a nonce string with an ECDSA P-384 private key; return base64."""
    sig = key.sign(nonce.encode("utf-8"), ECDSA(hashes.SHA384()))
    return base64.b64encode(sig).decode()


def _make_machine(
    machine_id: str = "test-machine",
    ek_fingerprint: str = "a" * 96,
    status: MachineStatus = MachineStatus.attested,
) -> MachineRow:
    return MachineRow(
        machine_id=machine_id,
        ek_fingerprint=ek_fingerprint,
        ek_source="cert",
        role=NodeRole.worker_app,
        status=status,
        config_token="tok",
        attested_at=datetime.now(timezone.utc),
    )


def _mock_repo(existing: Optional[MachineRow] = None) -> MagicMock:
    repo = MagicMock()
    repo.get_by_id.return_value = existing
    repo.save.side_effect = lambda m: m
    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def enrollment_ca(tmp_path_factory):
    """Initialise the enrollment CA in a temporary directory."""
    import os
    ca_dir = tmp_path_factory.mktemp("ca")
    os.environ["ITL_ENROLLMENT_CA_DIR"] = str(ca_dir)
    # Re-import to pick up the env var, then re-init
    import attestation.pki.enrollment_ca as ca_mod
    ca_mod._ca_key = None
    ca_mod._ca_cert = None
    ca_mod.CA_DIR = ca_dir
    ca_mod.CA_KEY_PATH = ca_dir / "enrollment-ca.key"
    ca_mod.CA_CERT_PATH = ca_dir / "enrollment-ca.crt"
    ca_mod.init_enrollment_ca()


@pytest.fixture()
def machine_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture()
def cert_with_ek(machine_id):
    """Return (cert_pem, key_pem, ek_fingerprint) for a cert that embeds an EK fingerprint."""
    ek_fp = "b" * 96
    cert_pem, key_pem = issue_enrollment_cert(
        machine_id=machine_id,
        role="worker-app",
        ek_fingerprint=ek_fp,
    )
    # Reload the private key so we can sign with it
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return cert_pem, key, ek_fp


@pytest.fixture()
def cert_without_ek(machine_id):
    """Return (cert_pem, key) for a cert issued without an EK fingerprint SAN."""
    cert_pem, key_pem = issue_enrollment_cert(
        machine_id=machine_id,
        role="worker-app",
        ek_fingerprint="",
    )
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return cert_pem, key


# ---------------------------------------------------------------------------
# extract_ek_fingerprint_from_cert
# ---------------------------------------------------------------------------

class TestExtractEkFingerprintFromCert:
    def test_returns_fingerprint_when_present(self, cert_with_ek):
        cert_pem, _, ek_fp = cert_with_ek
        result = extract_ek_fingerprint_from_cert(cert_pem)
        assert result == ek_fp

    def test_returns_none_when_absent(self, cert_without_ek):
        cert_pem, _ = cert_without_ek
        result = extract_ek_fingerprint_from_cert(cert_pem)
        assert result is None

    def test_returns_none_for_garbage_input(self):
        result = extract_ek_fingerprint_from_cert("not-a-cert")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = extract_ek_fingerprint_from_cert("")
        assert result is None


# ---------------------------------------------------------------------------
# EnrollmentHandler.enroll — EK fingerprint cross-check
# ---------------------------------------------------------------------------

class TestEnrollEkFingerprintCheck:
    def test_enroll_matching_ek_fingerprint_succeeds(self, machine_id, cert_with_ek):
        """Cert EK fingerprint matches machine record → enrollment succeeds (200)."""
        cert_pem, key, ek_fp = cert_with_ek
        nonce = secrets.token_hex(20)  # 40 chars >= 32
        sig = _sign_nonce(key, nonce)

        existing = _make_machine(machine_id=machine_id, ek_fingerprint=ek_fp)
        handler = EnrollmentHandler(_mock_repo(existing))

        result = handler.enroll({
            "cert_pem": cert_pem,
            "nonce": nonce,
            "nonce_signature": sig,
        })
        assert result.machine_id == machine_id

    def test_enroll_mismatched_ek_fingerprint_raises_403(self, machine_id, cert_with_ek):
        """Cert EK fingerprint differs from machine record → 403."""
        cert_pem, key, _cert_ek_fp = cert_with_ek
        nonce = secrets.token_hex(20)
        sig = _sign_nonce(key, nonce)

        # Machine has a *different* EK fingerprint than the cert
        existing = _make_machine(machine_id=machine_id, ek_fingerprint="c" * 96)
        handler = EnrollmentHandler(_mock_repo(existing))

        with pytest.raises(HTTPException) as exc_info:
            handler.enroll({
                "cert_pem": cert_pem,
                "nonce": nonce,
                "nonce_signature": sig,
            })
        assert exc_info.value.status_code == 403
        assert "EK fingerprint" in exc_info.value.detail

    def test_enroll_no_ek_san_succeeds_with_warning(self, machine_id, cert_without_ek, caplog):
        """Cert has no EK SAN → warns but enrollment succeeds (backwards compat)."""
        import logging
        cert_pem, key = cert_without_ek
        nonce = secrets.token_hex(20)
        sig = _sign_nonce(key, nonce)

        # Machine has a registered EK fingerprint but cert has no SAN
        existing = _make_machine(machine_id=machine_id, ek_fingerprint="d" * 96)
        handler = EnrollmentHandler(_mock_repo(existing))

        with caplog.at_level(logging.WARNING):
            result = handler.enroll({
                "cert_pem": cert_pem,
                "nonce": nonce,
                "nonce_signature": sig,
            })

        assert result.machine_id == machine_id
        assert any("no EK SAN" in r.message for r in caplog.records)

    def test_enroll_new_machine_with_ek_san_succeeds(self, machine_id, cert_with_ek):
        """Cert has EK SAN but no existing machine record → enrollment succeeds."""
        cert_pem, key, ek_fp = cert_with_ek
        nonce = secrets.token_hex(20)
        sig = _sign_nonce(key, nonce)

        # No existing machine record
        handler = EnrollmentHandler(_mock_repo(None))

        result = handler.enroll({
            "cert_pem": cert_pem,
            "nonce": nonce,
            "nonce_signature": sig,
        })
        assert result.machine_id == machine_id

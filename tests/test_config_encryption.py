"""Tests for EK-bound AES-256-GCM config encryption (issue #9).

Covers:
- ``load_ek_public_key`` — extraction from EK certificate and bare SPKI
- ``encrypt_config_for_machine`` — envelope structure, decryptability, wrong-key failure
- ``ConfigDeliveryHandler._deliver_config`` — content negotiation and 406 enforcement
"""
from __future__ import annotations

import base64
import datetime
import json
import uuid
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from attestation.handlers.config_delivery import (
    ENCRYPTED_ACCEPT,
    ConfigDeliveryHandler,
    encrypt_config_for_machine,
)
from attestation.models.machine import MachineRow, MachineStatus, NodeRole
from attestation.pki.tpm_verifier import load_ek_public_key


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_rsa_key(key_size: int = 2048) -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=key_size)


def _make_ek_cert(key: rsa.RSAPrivateKey) -> x509.Certificate:
    """Build a minimal self-signed EK certificate (keyEncipherment KU)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TPM EK")])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, key_cert_sign=False, crl_sign=False,
                content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )


def _b64_cert_pem(key: rsa.RSAPrivateKey) -> str:
    """Return a base64-encoded PEM EK cert (as stored in MachineRow.ek_cert_pem)."""
    cert = _make_ek_cert(key)
    pem = cert.public_bytes(serialization.Encoding.PEM)
    return base64.b64encode(pem).decode()


def _b64_spki_pem(key: rsa.RSAPrivateKey) -> str:
    """Return a base64-encoded SubjectPublicKeyInfo PEM (ek_source='pub' format)."""
    spki = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(spki).decode()


def _make_machine(
    ek_cert_pem: str | None = None,
    status: MachineStatus = MachineStatus.attested,
) -> MachineRow:
    return MachineRow(
        machine_id     = str(uuid.uuid4()),
        ek_fingerprint = "a" * 96,
        ek_source      = "cert",
        ek_cert_pem    = ek_cert_pem,
        role           = NodeRole.worker_app,
        status         = status,
    )


# ---------------------------------------------------------------------------
# load_ek_public_key
# ---------------------------------------------------------------------------

class TestLoadEkPublicKey:
    def test_extracts_from_cert_pem(self):
        key = _make_rsa_key()
        pub = load_ek_public_key(_b64_cert_pem(key))
        assert isinstance(pub, rsa.RSAPublicKey)

    def test_extracts_from_spki_pem(self):
        key = _make_rsa_key()
        pub = load_ek_public_key(_b64_spki_pem(key))
        assert isinstance(pub, rsa.RSAPublicKey)

    def test_cert_and_spki_yield_same_key(self):
        key = _make_rsa_key()
        pub_cert = load_ek_public_key(_b64_cert_pem(key))
        pub_spki = load_ek_public_key(_b64_spki_pem(key))
        assert pub_cert.public_numbers() == pub_spki.public_numbers()

    def test_garbage_raises_value_error(self):
        with pytest.raises(ValueError, match="[Cc]annot"):
            load_ek_public_key(base64.b64encode(b"not-a-key-at-all").decode())


# ---------------------------------------------------------------------------
# encrypt_config_for_machine
# ---------------------------------------------------------------------------

class TestEncryptConfigForMachine:
    def test_envelope_structure(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        envelope = encrypt_config_for_machine(machine, "payload: test")

        assert envelope["format"] == "ek-aes256gcm-v1"
        assert envelope["machine_id"] == machine.machine_id
        # base64-decodeable fields
        for field in ("wrapped_key", "iv", "ciphertext"):
            assert base64.b64decode(envelope[field])  # no exception

    def test_wrapped_key_length_matches_rsa_key_size(self):
        key = _make_rsa_key(2048)
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        envelope = encrypt_config_for_machine(machine, "x")
        wrapped = base64.b64decode(envelope["wrapped_key"])
        # RSA-2048 OAEP output is 256 bytes
        assert len(wrapped) == 256

    def test_iv_is_96_bits(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        envelope = encrypt_config_for_machine(machine, "x")
        assert len(base64.b64decode(envelope["iv"])) == 12

    def test_decrypt_with_correct_key_recovers_plaintext(self):
        """Full round-trip: encrypt → RSA-OAEP unwrap → AES-GCM decrypt."""
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        plaintext = "version: v1alpha1\nkind: MachineConfig\n"
        envelope = encrypt_config_for_machine(machine, plaintext)

        # Unwrap AES key with the EK private key (simulating TPM RSA decrypt)
        wrapped_key = base64.b64decode(envelope["wrapped_key"])
        aes_key = key.decrypt(
            wrapped_key,
            OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
        )
        assert len(aes_key) == 32

        # Decrypt config
        iv = base64.b64decode(envelope["iv"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
        recovered = AESGCM(aes_key).decrypt(iv, ciphertext, None).decode()
        assert recovered == plaintext

    def test_decrypt_with_wrong_key_fails(self):
        """Decryption with a different RSA key must fail (auth tag or OAEP error)."""
        key_correct = _make_rsa_key()
        key_wrong   = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key_correct))
        envelope = encrypt_config_for_machine(machine, "secret config")

        wrapped_key = base64.b64decode(envelope["wrapped_key"])
        # RSA OAEP decryption with wrong key must raise ValueError
        with pytest.raises(ValueError):
            key_wrong.decrypt(
                wrapped_key,
                OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
            )

    def test_no_ek_cert_raises_value_error(self):
        machine = _make_machine(ek_cert_pem=None)
        with pytest.raises(ValueError, match="No EK cert"):
            encrypt_config_for_machine(machine, "payload")

    def test_each_call_uses_fresh_iv_and_key(self):
        """Nonces and ciphertexts must differ between calls (probabilistic encryption)."""
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        e1 = encrypt_config_for_machine(machine, "same payload")
        e2 = encrypt_config_for_machine(machine, "same payload")
        assert e1["iv"] != e2["iv"]
        assert e1["ciphertext"] != e2["ciphertext"]
        assert e1["wrapped_key"] != e2["wrapped_key"]


# ---------------------------------------------------------------------------
# ConfigDeliveryHandler._deliver_config — content negotiation
# ---------------------------------------------------------------------------

class TestDeliverConfig:
    """Unit tests for _deliver_config without hitting the DB or config generator."""

    def _settings(self, require_encrypted: bool = False):
        s = MagicMock()
        s.require_encrypted_delivery = require_encrypted
        return s

    def test_plaintext_by_default(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        resp = ConfigDeliveryHandler._deliver_config(machine, "config: x", "", self._settings())
        assert resp.media_type == "application/yaml"
        assert b"config: x" in resp.body

    def test_encrypted_when_accept_header_set(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        resp = ConfigDeliveryHandler._deliver_config(
            machine, "config: x", ENCRYPTED_ACCEPT, self._settings()
        )
        assert ENCRYPTED_ACCEPT in resp.media_type
        body = json.loads(resp.body)
        assert body["format"] == "ek-aes256gcm-v1"

    def test_406_when_require_encrypted_and_no_accept(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        with pytest.raises(HTTPException) as exc_info:
            ConfigDeliveryHandler._deliver_config(
                machine, "config: x", "", self._settings(require_encrypted=True)
            )
        assert exc_info.value.status_code == 406

    def test_406_message_mentions_accept_header(self):
        key = _make_rsa_key()
        machine = _make_machine(ek_cert_pem=_b64_cert_pem(key))
        with pytest.raises(HTTPException) as exc_info:
            ConfigDeliveryHandler._deliver_config(
                machine, "config: x", "", self._settings(require_encrypted=True)
            )
        assert ENCRYPTED_ACCEPT in exc_info.value.detail

    def test_no_ek_cert_falls_back_to_plaintext(self):
        """If encryption fails (no EK cert stored), fall back to plaintext unless forbidden."""
        machine = _make_machine(ek_cert_pem=None)
        resp = ConfigDeliveryHandler._deliver_config(
            machine, "config: x", ENCRYPTED_ACCEPT, self._settings(require_encrypted=False)
        )
        # Falls back to plaintext since encryption is not possible
        assert resp.media_type == "application/yaml"

    def test_no_ek_cert_with_require_encrypted_returns_406(self):
        """No EK cert + require_encrypted → 406 after encryption fallback."""
        machine = _make_machine(ek_cert_pem=None)
        with pytest.raises(HTTPException) as exc_info:
            ConfigDeliveryHandler._deliver_config(
                machine, "config: x", ENCRYPTED_ACCEPT, self._settings(require_encrypted=True)
            )
        assert exc_info.value.status_code == 406

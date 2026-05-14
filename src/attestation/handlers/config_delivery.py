"""Config delivery handler — one-time token and MAC-based MachineConfig endpoints."""

from __future__ import annotations

import base64
import logging
import os

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from ..core.config import get_settings
from ..talos.config_generator import generate_machine_config, generate_pending_config
from ..models.machine import MachineRow, MachineStatus
from ..repositories.machine_repo import SqlMachineRepository

logger = logging.getLogger(__name__)

# Accept header value that triggers EK-bound encrypted delivery
ENCRYPTED_ACCEPT = "application/vnd.itl.config.encrypted+json"


def encrypt_config_for_machine(machine: MachineRow, config_yaml: str) -> dict:
    """Wrap a per-delivery AES-256 key with the machine's EK public key (RSA-OAEP-SHA256).

    Returns a JSON-serialisable envelope dict::

        {
            "format":      "ek-aes256gcm-v1",
            "machine_id":  "<uuid>",
            "wrapped_key": "<base64>",
            "iv":          "<base64>",
            "ciphertext":  "<base64>"
        }

    Only the TPM that owns the registered EK private key can decrypt
    ``wrapped_key`` and therefore recover the AES key to decrypt
    ``ciphertext``.

    Raises:
        ValueError: if no EK cert is stored for the machine, or if the
            EK public key is not RSA (EC EK keys are not yet supported for
            key wrapping).
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric.padding import MGF1, OAEP
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
    from cryptography.hazmat.primitives.hashes import SHA256

    from ..pki.tpm_verifier import load_ek_public_key

    if not machine.ek_cert_pem:
        raise ValueError(
            f"No EK cert stored for machine {machine.machine_id} — cannot produce encrypted envelope"
        )

    aes_key = os.urandom(32)  # AES-256
    iv = os.urandom(12)       # GCM nonce (96-bit)
    ciphertext = AESGCM(aes_key).encrypt(iv, config_yaml.encode(), None)

    ek_pub = load_ek_public_key(machine.ek_cert_pem)
    if not isinstance(ek_pub, RSAPublicKey):
        raise ValueError(
            f"EK public key for machine {machine.machine_id} is not RSA — "
            "EC EK key wrapping is not yet supported"
        )

    wrapped_key = ek_pub.encrypt(
        aes_key,
        OAEP(mgf=MGF1(algorithm=SHA256()), algorithm=SHA256(), label=None),
    )

    return {
        "format":      "ek-aes256gcm-v1",
        "machine_id":  machine.machine_id,
        "wrapped_key": base64.b64encode(wrapped_key).decode(),
        "iv":          base64.b64encode(iv).decode(),
        "ciphertext":  base64.b64encode(ciphertext).decode(),
    }


class ConfigDeliveryHandler:
    """Handles GET /api/v1/config and GET /api/v1/config/{token}."""

    def __init__(self, machine_repo: SqlMachineRepository) -> None:
        self.machine_repo = machine_repo

    def get_config_by_mac(self, mac: str, accept: str = "") -> Response:
        """Resolve MachineConfig by MAC address (generic ISO boot flow).

        Security model: MAC is a routing key only — TPM attestation is the real
        auth gate.  Only attested machines receive the full MachineConfig; all
        others get a safe pending config with no cluster secrets.
        """
        settings = get_settings()

        mac_normalised = mac.strip().lower().replace("-", ":")

        machine = self.machine_repo.get_by_mac(mac_normalised)

        if not machine:
            logger.warning(
                "Config request from unknown MAC %s — returning pending config", mac_normalised
            )
            return Response(
                content=generate_pending_config(settings.service_base_url),
                media_type="text/plain",
            )

        if machine.status in (
            MachineStatus.pending_approval,
            MachineStatus.registered,
            MachineStatus.locked,
            MachineStatus.revoked,
            MachineStatus.rejected,
        ):
            logger.info(
                "Config request from %s machine %s (MAC %s) — returning pending config",
                machine.status.value, machine.machine_id, mac_normalised,
            )
            return Response(
                content=generate_pending_config(settings.service_base_url),
                media_type="text/plain",
            )

        logger.info(
            "Generic ISO config served: machine=%s role=%s MAC=%s",
            machine.machine_id, machine.role.value, mac_normalised,
        )

        try:
            config_yaml = generate_machine_config(
                role           = machine.role.value,
                machine_id     = machine.machine_id,
                ek_fingerprint = machine.ek_fingerprint,
                hostname       = machine.hostname,
                assigned_ip    = machine.assigned_ip,
            )
            return self._deliver_config(machine, config_yaml, accept, settings)
        except FileNotFoundError as exc:
            logger.error("Base config not found: %s", exc)
            raise HTTPException(
                503, "Base config not available — ensure CI configs are downloaded"
            ) from exc

    def get_config_by_token(self, token: str, accept: str = "") -> Response:
        """One-time Talos MachineConfig endpoint keyed on a single-use token."""
        settings = get_settings()

        machine = self.machine_repo.get_by_config_token(token)

        if not machine:
            raise HTTPException(404, "Config token not found")

        if machine.token_consumed:
            logger.info(
                "Config re-fetch for machine %s (token already consumed)", machine.machine_id
            )
        else:
            machine.token_consumed = True
            self.machine_repo.save(machine)
            logger.info("Config token consumed for machine %s", machine.machine_id)

        if machine.status == MachineStatus.pending_approval:
            return Response(
                content=generate_pending_config(settings.service_base_url),
                media_type="text/plain",
            )

        try:
            config_yaml = generate_machine_config(
                role           = machine.role.value,
                machine_id     = machine.machine_id,
                ek_fingerprint = machine.ek_fingerprint,
                hostname       = machine.hostname,
                assigned_ip    = machine.assigned_ip,
            )
            return self._deliver_config(machine, config_yaml, accept, settings)
        except FileNotFoundError as exc:
            logger.error("Base config not found: %s", exc)
            raise HTTPException(
                503, "Base config not available — ensure CI configs are downloaded"
            ) from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deliver_config(machine: MachineRow, config_yaml: str, accept: str, settings) -> Response:
        """Choose plaintext or encrypted delivery based on Accept header and settings."""
        wants_encrypted = ENCRYPTED_ACCEPT in accept

        if wants_encrypted:
            try:
                envelope = encrypt_config_for_machine(machine, config_yaml)
                logger.info(
                    "Encrypted config delivered: machine=%s format=%s",
                    machine.machine_id, envelope["format"],
                )
                return JSONResponse(content=envelope, media_type=ENCRYPTED_ACCEPT)
            except ValueError as exc:
                logger.warning(
                    "Cannot encrypt config for machine %s: %s — falling back to plaintext",
                    machine.machine_id, exc,
                )
                # Fall through to plaintext if encryption is not possible
                # (e.g. no EK cert stored for older machines)

        if settings.require_encrypted_delivery:
            logger.warning(
                "Plaintext config delivery rejected for machine %s "
                "(ITL_REQUIRE_ENCRYPTED_DELIVERY=true)",
                machine.machine_id,
            )
            raise HTTPException(
                406,
                "Plaintext config delivery is disabled — "
                f"set Accept: {ENCRYPTED_ACCEPT} to receive the encrypted envelope",
            )

        logger.warning(
            "Plaintext config delivered for machine %s — "
            "set Accept: %s to enable EK-bound encryption",
            machine.machine_id, ENCRYPTED_ACCEPT,
        )
        return Response(content=config_yaml, media_type="application/yaml")

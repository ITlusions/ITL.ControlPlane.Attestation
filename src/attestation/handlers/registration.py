"""Registration handler — USB agent and self-registration flows."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Optional

from fastapi import HTTPException

from ..core.config import get_settings
from ..talos.iso_factory import get_itl_iso_url
from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import RegisterRequest, SelfRegisterRequest
from ..schemas.responses import RegisterResponse, SelfRegisterResponse
from ..pki.tpm_verifier import compute_ek_fingerprint, fingerprints_match, verify_ek_pem

logger = logging.getLogger(__name__)


class RegistrationHandler:
    """Handles USB-agent registration and extension self-registration."""

    def __init__(self, machine_repo: SqlMachineRepository) -> None:
        self.machine_repo = machine_repo

    def register(self, req: RegisterRequest) -> RegisterResponse:
        """Register a machine by TPM EK fingerprint (USB agent flow)."""
        if not req.ek_cert_pem or not req.ek_cert_pem.strip():
            raise HTTPException(
                422,
                "EK certificate material is required — registration without TPM evidence is not permitted",
            )

        try:
            verify_ek_pem(req.ek_cert_pem, req.ek_source)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid EK material: {exc}") from exc

        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(
                422,
                f"EK fingerprint mismatch: agent reported {req.ek_fingerprint[:12]}... "
                f"but computed {computed_fp[:12]}...",
            )
        ek_fingerprint = computed_fp

        existing = self.machine_repo.get_by_ek_fingerprint(ek_fingerprint)

        config_token = secrets.token_urlsafe(32)

        if existing:
            logger.info(
                "Re-registration of machine %s (ek=%s...)", existing.machine_id, ek_fingerprint[:12]
            )
            existing.config_token   = config_token
            existing.token_consumed = False
            existing.hw_uuid        = req.hw_uuid
            existing.hw_mac         = req.hw_mac
            existing.hw_serial      = req.hw_serial
            existing.hw_product     = req.hw_product
            existing.ek_cert_pem    = req.ek_cert_pem
            machine = self.machine_repo.save(existing)
        else:
            role = (
                NodeRole(req.desired_role)
                if req.desired_role in NodeRole.__members__
                else NodeRole.worker_app
            )
            machine = self.machine_repo.save(MachineRow(
                machine_id     = str(uuid.uuid4()),
                ek_fingerprint = ek_fingerprint,
                ek_source      = req.ek_source,
                ek_cert_pem    = req.ek_cert_pem,
                hw_uuid        = req.hw_uuid,
                hw_mac         = req.hw_mac,
                hw_serial      = req.hw_serial,
                hw_product     = req.hw_product,
                role           = role,
                status         = MachineStatus.registered,
                config_token   = config_token,
            ))
            logger.info(
                "New machine registered: id=%s role=%s ek=%s...",
                machine.machine_id, machine.role, ek_fingerprint[:12],
            )

        settings = get_settings()
        config_url = f"{settings.service_base_url}/api/v1/config/{config_token}"
        iso_url    = get_itl_iso_url(config_url)

        return RegisterResponse(
            machine_id   = machine.machine_id,
            role         = machine.role.value,
            status       = machine.status.value,
            iso_url      = iso_url,
            config_token = config_token,
            config_url   = config_url,
            message      = "Machine registered — download ISO and boot to continue",
        )

    def self_register(self, req: SelfRegisterRequest) -> SelfRegisterResponse:
        """Extension-initiated registration — no USB agent required."""
        if not req.ek_cert_pem:
            raise HTTPException(
                422,
                "EK certificate material is required — self-registration without TPM evidence is not permitted",
            )

        try:
            verify_ek_pem(req.ek_cert_pem, req.ek_source)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid EK material: {exc}") from exc

        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(
                422,
                f"EK fingerprint mismatch: agent reported {req.ek_fingerprint[:12]}... "
                f"but computed {computed_fp[:12]}...",
            )
        ek_fingerprint = computed_fp

        existing = self.machine_repo.get_by_ek_fingerprint(ek_fingerprint)

        if existing:
            logger.info(
                "Self-registration of already known machine %s (status=%s ek=%s...)",
                existing.machine_id, existing.status.value, ek_fingerprint[:12],
            )
            config_url = (
                f"{settings.service_base_url}/api/v1/config/{existing.config_token}"
                if existing.config_token
                else None
            )
            return SelfRegisterResponse(
                machine_id   = existing.machine_id,
                role         = existing.role.value,
                status       = existing.status.value,
                config_token = existing.config_token,
                config_url   = config_url,
                message      = (
                    "Machine already registered — call POST /api/v1/attest to continue"
                    if existing.status != MachineStatus.attested
                    else "Machine already attested — re-apply config via config_url if needed"
                ),
            )

        role = (
            NodeRole(req.desired_role)
            if req.desired_role in NodeRole.__members__
            else NodeRole.worker_app
        )
        machine = self.machine_repo.save(MachineRow(
            machine_id     = str(uuid.uuid4()),
            ek_fingerprint = ek_fingerprint,
            ek_source      = req.ek_source,
            ek_cert_pem    = req.ek_cert_pem,
            hw_uuid        = req.hw_uuid,
            hw_mac         = req.hw_mac,
            hw_serial      = req.hw_serial,
            hw_product     = req.hw_product,
            role           = role,
            status         = MachineStatus.pending_approval,
        ))
        logger.info(
            "Self-registration: new machine id=%s role=%s ek=%s... — awaiting operator approval",
            machine.machine_id, machine.role, ek_fingerprint[:12],
        )

        return SelfRegisterResponse(
            machine_id   = machine.machine_id,
            role         = machine.role.value,
            status       = machine.status.value,
            config_token = None,
            config_url   = None,
            message      = (
                "Machine registered — awaiting operator approval. "
                "Poll POST /api/v1/attest every 60 s; when action=apply-config, "
                "fetch config_url and run: talosctl apply-config --insecure --file <(curl -sf <config_url>)"
            ),
        )

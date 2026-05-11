"""Attestation handler — TPM EK-based node identity verification."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from ..core.config import settings
from ..core.models import AttestRequest, AttestResponse, Machine, MachineStatus, NodeRole
from ..tpm_verifier import compute_ek_fingerprint, fingerprints_match

logger = logging.getLogger(__name__)


class AttestationHandler:
    """Handles POST /api/v1/attest — TPM EK identity verification."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def attest(self, req: AttestRequest) -> AttestResponse:
        """Attest a node's TPM identity after first boot."""
        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(422, "EK fingerprint mismatch")

        machine: Optional[Machine] = self.db.exec(
            select(Machine).where(Machine.ek_fingerprint == computed_fp)
        ).first()

        if not machine:
            logger.warning(
                "Attestation from unknown EK %s... — creating pending record", computed_fp[:12]
            )
            machine = Machine(
                machine_id     = str(uuid.uuid4()),
                ek_fingerprint = computed_fp,
                ek_source      = req.ek_source,
                hw_uuid        = req.hw_uuid,
                hw_mac         = req.hw_mac,
                hw_serial      = req.hw_serial,
                hw_product     = req.hw_product,
                role           = NodeRole.worker_app,
                status         = MachineStatus.pending_approval,
            )
            self.db.add(machine)
            self.db.commit()
            self.db.refresh(machine)
            return AttestResponse(
                machine_id = machine.machine_id,
                status     = "pending_approval",
                hostname   = None,
                role       = machine.role.value,
                message    = "Machine not pre-registered — awaiting operator approval",
                action     = "none",
            )

        if machine.status == MachineStatus.rejected:
            raise HTTPException(403, f"Machine {machine.machine_id} has been rejected")

        if machine.status == MachineStatus.locked:
            logger.warning("Locked machine contacted: id=%s", machine.machine_id)
            return AttestResponse(
                machine_id = machine.machine_id,
                status     = "locked",
                hostname   = machine.hostname,
                role       = machine.role.value,
                message    = "Machine is temporarily locked — contact operator to unlock",
                action     = "lock",
            )

        if machine.status == MachineStatus.revoked:
            action  = "wipe" if machine.wipe_pending else "none"
            message = (
                "Machine has been revoked — wipe initiated"
                if machine.wipe_pending
                else "Machine has been revoked"
            )
            logger.warning("Revoked machine contacted: id=%s action=%s", machine.machine_id, action)
            return AttestResponse(
                machine_id = machine.machine_id,
                status     = "revoked",
                hostname   = machine.hostname,
                role       = machine.role.value,
                message    = message,
                action     = action,
            )

        if machine.status == MachineStatus.attested:
            config_url = (
                f"{settings.service_base_url}/api/v1/config/{machine.config_token}"
                if machine.config_token
                else None
            )
            return AttestResponse(
                machine_id   = machine.machine_id,
                status       = "already_attested",
                hostname     = machine.hostname,
                role         = machine.role.value,
                message      = "Machine already attested",
                action       = "none",
                config_url   = config_url,
                config_token = machine.config_token,
            )

        config_token = secrets.token_urlsafe(32)
        machine.status         = MachineStatus.attested
        machine.attested_at    = datetime.utcnow()
        machine.config_token   = config_token
        machine.token_consumed = False
        self.db.add(machine)
        self.db.commit()
        logger.info("Machine attested: id=%s role=%s", machine.machine_id, machine.role)

        config_url = f"{settings.service_base_url}/api/v1/config/{config_token}"

        return AttestResponse(
            machine_id   = machine.machine_id,
            status       = "attested",
            hostname     = machine.hostname,
            role         = machine.role.value,
            message      = "Attestation successful — fetch config_url and apply with talosctl apply-config",
            action       = "apply-config",
            config_url   = config_url,
            config_token = config_token,
        )

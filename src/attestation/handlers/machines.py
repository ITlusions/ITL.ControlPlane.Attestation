"""Machine administration handler — approve, revoke, lock, unlock, bundle, import."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from ..core.config import get_settings
from ..talos.config_generator import generate_machine_config
from ..pki.enrollment_ca import issue_enrollment_cert
from ..talos.iso_factory import get_itl_iso_url
from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import ApproveRequest, LockRequest, RevokeRequest
from ..schemas.responses import MachineDetail

logger = logging.getLogger(__name__)


class MachineAdminHandler:
    """Handles all admin operations on machine records."""

    def __init__(self, machine_repo: SqlMachineRepository) -> None:
        self.machine_repo = machine_repo

    @staticmethod
    def _machine_detail(m: MachineRow) -> MachineDetail:
        return MachineDetail(
            machine_id     = m.machine_id,
            ek_fingerprint = m.ek_fingerprint,
            hw_uuid        = m.hw_uuid,
            hw_mac         = m.hw_mac,
            hw_serial      = m.hw_serial,
            hw_product     = m.hw_product,
            role           = m.role.value,
            status         = m.status.value,
            hostname       = m.hostname,
            assigned_ip    = m.assigned_ip,
            registered_at  = m.registered_at,
            attested_at    = m.attested_at,
            locked_at      = m.locked_at,
            revoked_at     = m.revoked_at,
            wipe_pending   = m.wipe_pending,
        )

    def _get_or_404(self, machine_id: str) -> MachineRow:
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise HTTPException(404, f"Machine {machine_id} not found")
        return machine

    def list_machines(self) -> list[MachineDetail]:
        return [self._machine_detail(m) for m in self.machine_repo.list_all()]

    def approve(self, machine_id: str, req: ApproveRequest) -> MachineDetail:
        machine = self._get_or_404(machine_id)
        config_token = secrets.token_urlsafe(32)
        machine.role           = req.role
        machine.status         = MachineStatus.registered
        machine.hostname       = req.hostname
        machine.assigned_ip    = req.assigned_ip
        machine.config_token   = config_token
        machine.token_consumed = False
        machine = self.machine_repo.save(machine)
        logger.info("Machine %s approved with role=%s hostname=%s", machine_id, req.role, req.hostname)
        return self._machine_detail(machine)

    def revoke(self, machine_id: str, req: RevokeRequest) -> MachineDetail:
        machine = self._get_or_404(machine_id)
        machine.status         = MachineStatus.revoked
        machine.wipe_pending   = req.wipe
        machine.revoked_at     = datetime.utcnow()
        machine.config_token   = None
        machine.token_consumed = True
        machine = self.machine_repo.save(machine)
        action = "wipe scheduled on next attestation contact" if req.wipe else "blocked"
        logger.warning("Machine %s REVOKED — action=%s reason=%r", machine_id, action, req.reason)
        return self._machine_detail(machine)

    def lock(self, machine_id: str, req: LockRequest) -> MachineDetail:
        machine = self._get_or_404(machine_id)
        if machine.status == MachineStatus.revoked:
            raise HTTPException(
                409, f"Machine {machine_id} is already revoked — cannot lock a revoked machine"
            )
        machine.status         = MachineStatus.locked
        machine.locked_at      = datetime.utcnow()
        machine.config_token   = None
        machine.token_consumed = True
        machine = self.machine_repo.save(machine)
        logger.warning("Machine %s LOCKED — reason=%r", machine_id, req.reason)
        return self._machine_detail(machine)

    def unlock(self, machine_id: str) -> MachineDetail:
        machine = self._get_or_404(machine_id)
        if machine.status != MachineStatus.locked:
            raise HTTPException(
                409,
                f"Machine {machine_id} is not locked (status={machine.status.value})",
            )
        machine.status    = MachineStatus.attested
        machine.locked_at = None
        machine = self.machine_repo.save(machine)
        logger.info("Machine %s UNLOCKED — restored to attested", machine_id)
        return self._machine_detail(machine)

    def offline_bundle(self, machine_id: str) -> dict:
        machine = self._get_or_404(machine_id)

        config_token = secrets.token_urlsafe(32)
        machine.config_token   = config_token
        machine.token_consumed = False
        machine = self.machine_repo.save(machine)

        settings = get_settings()
        config_url = f"{settings.service_base_url}/api/v1/config/{config_token}"
        iso_url    = get_itl_iso_url(config_url)

        enrollment_cert_pem, enrollment_key_pem = issue_enrollment_cert(
            machine_id = machine.machine_id,
            role       = machine.role.value,
        )

        machineconfig = None
        try:
            machineconfig = generate_machine_config(
                role                = machine.role.value,
                machine_id          = machine.machine_id,
                ek_fingerprint      = machine.ek_fingerprint,
                hostname            = machine.hostname,
                assigned_ip         = machine.assigned_ip,
                enrollment_cert_pem = enrollment_cert_pem,
                enrollment_key_pem  = enrollment_key_pem,
            )
        except Exception:
            pass

        logger.info(
            "Offline bundle generated for machine %s (role=%s)", machine_id, machine.role
        )
        return {
            "machine_id":          machine.machine_id,
            "role":                machine.role.value,
            "status":              machine.status.value,
            "ek_fingerprint":      machine.ek_fingerprint,
            "hostname":            machine.hostname,
            "assigned_ip":         machine.assigned_ip,
            "iso_url":             iso_url,
            "config_url":          config_url,
            "config_token":        config_token,
            "machineconfig":       machineconfig,
            "enrollment_cert_pem": enrollment_cert_pem,
            "enrollment_key_pem":  enrollment_key_pem,
            "install_mode":        "offline",
            "built_at":            datetime.utcnow().isoformat() + "Z",
        }

    def import_machine(self, receipt: dict) -> dict:
        """Import a machine from an offline TPM receipt. Idempotent."""
        ek_fp      = receipt.get("ek_fingerprint", "")
        role_str   = receipt.get("role", "worker-app")
        machine_id = receipt.get("machine_id") or str(uuid.uuid4())

        if not ek_fp:
            raise HTTPException(422, "ek_fingerprint is required in the receipt")

        existing = self.machine_repo.get_by_ek_fingerprint(ek_fp)

        config_token = secrets.token_urlsafe(32)

        if existing:
            logger.info(
                "Import: updating existing machine %s (ek=%s...)", existing.machine_id, ek_fp[:12]
            )
            existing.config_token   = config_token
            existing.token_consumed = False
            existing.hw_uuid        = receipt.get("hw_uuid",    existing.hw_uuid)
            existing.hw_mac         = receipt.get("hw_mac",     existing.hw_mac)
            existing.hw_serial      = receipt.get("hw_serial",  existing.hw_serial)
            existing.hw_product     = receipt.get("hw_product", existing.hw_product)
            machine = self.machine_repo.save(existing)
        else:
            try:
                role = NodeRole(role_str)
            except ValueError:
                role = NodeRole.worker_app

            machine = self.machine_repo.save(MachineRow(
                machine_id     = machine_id,
                ek_fingerprint = ek_fp,
                ek_source      = receipt.get("ek_source", "offline-import"),
                hw_uuid        = receipt.get("hw_uuid", ""),
                hw_mac         = receipt.get("hw_mac", ""),
                hw_serial      = receipt.get("hw_serial", ""),
                hw_product     = receipt.get("hw_product", ""),
                role           = role,
                status         = MachineStatus.registered,
                config_token   = config_token,
            ))
            logger.info(
                "Offline import: new machine %s role=%s ek=%s...",
                machine.machine_id, role, ek_fp[:12],
            )

        return {
            "machine_id":  machine.machine_id,
            "role":        machine.role.value,
            "status":      machine.status.value,
            "config_url":  f"{get_settings().service_base_url}/api/v1/config/{config_token}",
            "message":     "Machine imported from offline receipt — ready for attestation",
        }

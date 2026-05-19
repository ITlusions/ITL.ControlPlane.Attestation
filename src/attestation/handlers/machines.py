"""Machine administration handler — approve, revoke, lock, unlock, bundle, import."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from ..core.config import get_settings
from ..core.eventbus import bus
from ..core.events import NodeEvent, NodeEventPayload
from ..talos.config_generator import generate_machine_config
from ..pki.enrollment_ca import issue_enrollment_cert
from ..talos.iso_factory import get_itl_iso_url
from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..models.operator import AuditLogRow, ApprovalRequestRow
from ..repositories.machine_repo import SqlMachineRepository
from ..repositories.operator_repo import AuditRepository, ApprovalRepository
from ..schemas.requests import ApproveRequest, LockRequest, RevokeRequest
from ..schemas.responses import MachineDetail, PendingApprovalResponse

logger = logging.getLogger(__name__)


class MachineAdminHandler:
    """Handles all admin operations on machine records."""

    def __init__(
        self,
        machine_repo: SqlMachineRepository,
        audit_repo: Optional[AuditRepository] = None,
        approval_repo: Optional[ApprovalRepository] = None,
    ) -> None:
        self.machine_repo  = machine_repo
        self.audit_repo    = audit_repo
        self.approval_repo = approval_repo

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _audit(
        self,
        operator_cn: str,
        action: str,
        machine_id: Optional[str] = None,
        prev_state: Optional[str] = None,
        new_state: Optional[str]  = None,
        detail: Optional[str]     = None,
    ) -> None:
        """Append a record to the audit log (no-op if audit_repo is not wired in)."""
        if self.audit_repo is None:
            return
        entry = AuditLogRow(
            operator_cn = operator_cn,
            action      = action,
            machine_id  = machine_id,
            prev_state  = prev_state,
            new_state   = new_state,
            detail      = detail,
        )
        self.audit_repo.append(entry)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def list_machines(self) -> list[MachineDetail]:
        return [self._machine_detail(m) for m in self.machine_repo.list_all()]

    def approve(
        self,
        machine_id: str,
        req: ApproveRequest,
        operator_cn: str = "SYSTEM",
    ) -> tuple[MachineDetail | PendingApprovalResponse, int]:
        """Approve a pending machine.

        Returns (response_body, http_status_code).

        When the machine's role is listed in ITL_DUAL_CONTROL_ROLES:
          - First approval  → stores a pending vote, returns (PendingApprovalResponse, 202)
          - Second approval from a *different* operator → completes approval, returns (MachineDetail, 200)
          - Same operator submitting twice → treated as first vote still pending, returns 202
          - Expired first vote → cleaned up, new vote stored, returns 202
        """
        machine    = self._get_or_404(machine_id)
        settings   = get_settings()
        prev_state = machine.status.value

        # ----------------------------------------------------------------
        # Dual-control check
        # ----------------------------------------------------------------
        role_str = req.role.value
        dual_control_required = (
            self.approval_repo is not None
            and role_str in settings.dual_control_roles
            and settings.dual_control_quorum >= 2
        )

        if dual_control_required:
            assert self.approval_repo is not None  # narrowing

            pending = self.approval_repo.get_pending_for_machine(machine_id)

            # Find a vote from a *different* operator (quorum partner)
            quorum_partner = next(
                (p for p in pending if p.operator_cn != operator_cn),
                None,
            )

            if quorum_partner is None:
                # No valid partner vote yet — record this operator's vote
                # (idempotent: if this operator already voted, we just return 202 again)
                already_voted = any(p.operator_cn == operator_cn for p in pending)
                new_row: ApprovalRequestRow | None = None
                if not already_voted:
                    window = settings.dual_control_window_seconds
                    new_row = self.approval_repo.create(ApprovalRequestRow(
                        machine_id  = machine_id,
                        operator_cn = operator_cn,
                        role        = role_str,
                        hostname    = req.hostname,
                        assigned_ip = req.assigned_ip,
                        expires_at  = datetime.now(timezone.utc) + timedelta(seconds=window),
                    ))
                    self._audit(
                        operator_cn, "approve_vote",
                        machine_id = machine_id,
                        prev_state = prev_state,
                        detail     = f"first approval vote — awaiting second operator (quorum={settings.dual_control_quorum})",
                    )
                    logger.info(
                        "Machine %s: first approval vote from %s — awaiting second operator",
                        machine_id, operator_cn,
                    )

                # Compute approvals_received and earliest expiry without a second DB call
                approvals_received = len(pending) + (1 if new_row is not None else 0)
                all_votes = list(pending) + ([new_row] if new_row is not None else [])
                window = settings.dual_control_window_seconds
                expires = (
                    min(p.expires_at for p in all_votes)
                    if all_votes
                    else datetime.now(timezone.utc) + timedelta(seconds=window)
                )
                return (
                    PendingApprovalResponse(
                        machine_id          = machine_id,
                        status              = "pending_second_approval",
                        message             = (
                            f"Approval vote recorded for operator '{operator_cn}'. "
                            f"A second operator must also approve before the machine is registered."
                        ),
                        approvals_received  = approvals_received,
                        approvals_required  = settings.dual_control_quorum,
                        expires_at          = expires,
                    ),
                    202,
                )

            # Quorum met — consume the partner vote and proceed
            self.approval_repo.mark_consumed(quorum_partner.id)  # type: ignore[arg-type]
            # Use the role/hostname from the *original* vote (first operator's intent)
            # but allow the second operator to override if they provide values
            if not req.hostname and quorum_partner.hostname:
                req = ApproveRequest(
                    role        = req.role,
                    hostname    = quorum_partner.hostname,
                    assigned_ip = req.assigned_ip or quorum_partner.assigned_ip,
                )
            self._audit(
                operator_cn, "approve_vote",
                machine_id = machine_id,
                prev_state = prev_state,
                detail     = f"second approval vote — quorum reached (partner: {quorum_partner.operator_cn})",
            )
            logger.info(
                "Machine %s: quorum reached (%s + %s) — proceeding with approval",
                machine_id, quorum_partner.operator_cn, operator_cn,
            )

        # ----------------------------------------------------------------
        # Perform the actual approval
        # ----------------------------------------------------------------
        config_token = secrets.token_urlsafe(32)
        machine.role           = req.role
        machine.status         = MachineStatus.registered
        machine.hostname       = req.hostname
        machine.assigned_ip    = req.assigned_ip
        machine.config_token   = config_token
        machine.token_consumed = False
        machine = self.machine_repo.save(machine)

        self._audit(
            operator_cn, "approve",
            machine_id = machine_id,
            prev_state = prev_state,
            new_state  = machine.status.value,
            detail     = f"role={req.role.value} hostname={req.hostname}",
        )
        logger.info(
            "Machine %s approved by %s — role=%s hostname=%s",
            machine_id, operator_cn, req.role, req.hostname,
        )

        settings = get_settings()
        config_url = f"{settings.service_base_url}/api/v1/config/{config_token}"
        iso_url    = get_itl_iso_url(config_url)
        bus.emit_nowait(NodeEventPayload(
            event=NodeEvent.NODE_PROVISIONED,
            ek_fingerprint=machine.ek_fingerprint,
            node={
                "machine_id":  machine.machine_id,
                "hostname":    machine.hostname,
                "role":        machine.role.value,
                "config_url":  config_url,
                "iso_url":     iso_url,
            },
        ))

        return self._machine_detail(machine), 200

    def revoke(
        self,
        machine_id: str,
        req: RevokeRequest,
        operator_cn: str = "SYSTEM",
    ) -> MachineDetail:
        machine    = self._get_or_404(machine_id)
        prev_state = machine.status.value
        machine.status         = MachineStatus.revoked
        machine.wipe_pending   = req.wipe
        machine.revoked_at     = datetime.now(timezone.utc)
        machine.config_token   = None
        machine.token_consumed = True
        machine = self.machine_repo.save(machine)
        action_detail = "wipe scheduled on next attestation contact" if req.wipe else "blocked"
        self._audit(
            operator_cn, "revoke",
            machine_id = machine_id,
            prev_state = prev_state,
            new_state  = machine.status.value,
            detail     = f"{action_detail}; reason={req.reason!r}",
        )
        logger.warning(
            "Machine %s REVOKED by %s — action=%s reason=%r",
            machine_id, operator_cn, action_detail, req.reason,
        )
        bus.emit_nowait(NodeEventPayload(
            event=NodeEvent.NODE_DECOMMISSIONED,
            ek_fingerprint=machine.ek_fingerprint,
            node={
                "machine_id": machine.machine_id,
                "hostname":   machine.hostname,
                "role":       machine.role.value,
            },
            meta={"reason": req.reason},
        ))
        return self._machine_detail(machine)

    def lock(
        self,
        machine_id: str,
        req: LockRequest,
        operator_cn: str = "SYSTEM",
    ) -> MachineDetail:
        machine = self._get_or_404(machine_id)
        if machine.status == MachineStatus.revoked:
            raise HTTPException(
                409, f"Machine {machine_id} is already revoked — cannot lock a revoked machine"
            )
        prev_state             = machine.status.value
        machine.status         = MachineStatus.locked
        machine.locked_at      = datetime.now(timezone.utc)
        machine.config_token   = None
        machine.token_consumed = True
        machine = self.machine_repo.save(machine)
        self._audit(
            operator_cn, "lock",
            machine_id = machine_id,
            prev_state = prev_state,
            new_state  = machine.status.value,
            detail     = f"reason={req.reason!r}",
        )
        logger.warning("Machine %s LOCKED by %s — reason=%r", machine_id, operator_cn, req.reason)
        return self._machine_detail(machine)

    def unlock(self, machine_id: str, operator_cn: str = "SYSTEM") -> MachineDetail:
        machine = self._get_or_404(machine_id)
        if machine.status != MachineStatus.locked:
            raise HTTPException(
                409,
                f"Machine {machine_id} is not locked (status={machine.status.value})",
            )
        prev_state        = machine.status.value
        machine.status    = MachineStatus.attested
        machine.locked_at = None
        machine = self.machine_repo.save(machine)
        self._audit(
            operator_cn, "unlock",
            machine_id = machine_id,
            prev_state = prev_state,
            new_state  = machine.status.value,
        )
        logger.info("Machine %s UNLOCKED by %s — restored to attested", machine_id, operator_cn)
        return self._machine_detail(machine)

    def offline_bundle(self, machine_id: str, operator_cn: str = "SYSTEM") -> dict:
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

        self._audit(
            operator_cn, "offline_bundle",
            machine_id = machine_id,
            detail     = f"role={machine.role.value}",
        )
        logger.info(
            "Offline bundle generated for machine %s (role=%s) by %s",
            machine_id, machine.role, operator_cn,
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
            "built_at":            datetime.now(timezone.utc).isoformat(),
        }

    def import_machine(self, receipt: dict, operator_cn: str = "SYSTEM") -> dict:
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

        self._audit(
            operator_cn, "import",
            machine_id = machine.machine_id,
            detail     = f"ek={ek_fp[:12]}... role={machine.role.value}",
        )
        return {
            "machine_id":  machine.machine_id,
            "role":        machine.role.value,
            "status":      machine.status.value,
            "config_url":  f"{get_settings().service_base_url}/api/v1/config/{config_token}",
            "message":     "Machine imported from offline receipt — ready for attestation",
        }

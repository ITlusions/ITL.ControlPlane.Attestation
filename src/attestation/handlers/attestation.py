"""Attestation handler — TPM EK-based node identity verification."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from ..core.config import get_settings
from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import AttestRequest
from ..schemas.responses import AttestResponse
from ..pki.tpm_verifier import compute_ek_fingerprint, fingerprints_match
from ..pki.nonce_store import NonceStore, get_nonce_store
from ..pki.quote_verifier import QuoteVerifier, QuoteVerificationError

logger = logging.getLogger(__name__)


class AttestationHandler:
    """Handles POST /api/v1/attest — TPM EK identity verification."""

    def __init__(
        self,
        machine_repo: SqlMachineRepository,
        nonce_store:  Optional[NonceStore] = None,
    ) -> None:
        self.machine_repo = machine_repo
        self.nonce_store  = nonce_store or get_nonce_store()
        # RT-11: nonce bytes are stored here after consume() so the quote
        # verifier can use them without a racy second peek() call.
        self._consumed_nonce_bytes: Optional[bytes] = None

    def attest(self, req: AttestRequest) -> AttestResponse:
        """Attest a node's TPM identity after first boot."""
        settings = get_settings()

        # ------------------------------------------------------------------
        # Nonce validation (issue #7)
        # ------------------------------------------------------------------
        if req.nonce_id:
            try:
                # Store consumed bytes immediately — passed to quote verifier below
                self._consumed_nonce_bytes = self.nonce_store.consume(req.nonce_id)
            except TimeoutError:
                raise HTTPException(410, "Attestation nonce has expired — request a new challenge")
            except ValueError:
                raise HTTPException(409, "Attestation nonce has already been used — replay detected")
            except KeyError:
                raise HTTPException(422, "Unknown nonce_id — request a fresh challenge first")
        elif settings.require_nonce:
            raise HTTPException(
                422,
                "ITL_REQUIRE_NONCE is enabled — include nonce_id from GET /api/v1/attest/challenge",
            )


        computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
        if not fingerprints_match(computed_fp, req.ek_fingerprint):
            raise HTTPException(422, "EK fingerprint mismatch")

        machine = self.machine_repo.get_by_ek_fingerprint(computed_fp)

        # ------------------------------------------------------------------
        # PCR quote verification (issue #6, CRIT-03 fix)
        # Enforce require_quote FIRST before checking if quote was supplied.
        # This prevents bypass via "send quote with no registered AK".
        # ------------------------------------------------------------------
        if settings.require_quote and not (req.pcr_quote and req.pcr_signature):
            raise HTTPException(
                422,
                "ITL_REQUIRE_QUOTE is enabled — include pcr_quote and pcr_signature",
            )

        if req.pcr_quote and req.pcr_signature:
            if not machine or not machine.ak_pub:
                raise HTTPException(
                    422,
                    "PCR quote submitted but no AK registered for this machine — "
                    "call POST /api/v1/machines/{id}/ak-activate first",
                )
            # RT-11 fix: nonce bytes must be carried forward from the consume() call
            # above, not re-fetched via peek() which races in multi-process deployments.
            # Pass nonce_bytes_for_quote through the handler's state set in the nonce block.
            try:
                QuoteVerifier().verify(
                    ak_pub_pem=machine.ak_pub,
                    quote_b64=req.pcr_quote,
                    sig_b64=req.pcr_signature,
                    pcr_values={},  # PCR values carried in the quote structure
                    nonce_bytes=self._consumed_nonce_bytes,
                )
            except QuoteVerificationError as exc:
                raise HTTPException(422, f"PCR quote verification failed: {exc}") from exc

        if not machine:
            logger.warning(
                "Attestation from unknown EK %s... — creating pending record", computed_fp[:12]
            )
            machine = self.machine_repo.save(MachineRow(
                machine_id     = str(uuid.uuid4()),
                ek_fingerprint = computed_fp,
                ek_source      = req.ek_source,
                hw_uuid        = req.hw_uuid,
                hw_mac         = req.hw_mac,
                hw_serial      = req.hw_serial,
                hw_product     = req.hw_product,
                role           = NodeRole.worker_app,
                status         = MachineStatus.pending_approval,
            ))
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
        machine.attested_at    = datetime.now(timezone.utc)
        machine.config_token   = config_token
        machine.token_consumed = False
        self.machine_repo.save(machine)
        logger.info("Machine attested: id=%s role=%s", machine.machine_id, machine.role)

        settings = get_settings()
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

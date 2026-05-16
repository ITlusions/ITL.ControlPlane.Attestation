"""Enrollment handler — certificate-based enrollment and cert issuance."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

from ..pki.enrollment_ca import (
    CERT_VALID_DAYS,
    encrypt_with_rsa_pubkey,
    extract_ek_fingerprint_from_cert,
    get_ca_cert_pem,
    issue_enrollment_cert,
    verify_enrollment_cert,
    verify_nonce_signature,
)
from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.responses import AttestResponse, CertResponse
from ..schemas.requests import CertRequest
from ..pki.tpm_verifier import compute_ek_fingerprint, fingerprints_match, verify_ek_pem

logger = logging.getLogger(__name__)


class EnrollmentHandler:
    """Handles certificate-based enrollment and enrollment cert issuance."""

    def __init__(self, machine_repo: SqlMachineRepository) -> None:
        self.machine_repo = machine_repo

    def enroll(self, body: dict) -> AttestResponse:
        """Certificate-based machine enrollment for offline-provisioned nodes."""
        cert_pem            = body.get("cert_pem", "")
        nonce               = body.get("nonce", "")
        nonce_signature_b64 = body.get("nonce_signature", "")

        if not cert_pem or not nonce or not nonce_signature_b64:
            raise HTTPException(422, "cert_pem, nonce, and nonce_signature are required")

        if len(nonce) < 32:
            raise HTTPException(422, "nonce must be at least 32 characters")

        try:
            claims = verify_enrollment_cert(cert_pem)
        except ValueError as exc:
            raise HTTPException(403, f"Enrollment cert rejected: {exc}") from exc

        try:
            verify_nonce_signature(cert_pem, nonce, nonce_signature_b64)
        except ValueError as exc:
            raise HTTPException(403, f"Nonce signature rejected: {exc}") from exc

        machine_id = claims["machine_id"]
        role_str   = claims["role"]

        existing = self.machine_repo.get_by_id(machine_id)

        # Cross-check the EK fingerprint embedded in the cert's URI SAN against
        # the fingerprint stored for the machine (if any).  This prevents a
        # stolen enrollment cert from being used to enroll a different physical
        # machine under the victim's identity.
        cert_ek_fp = extract_ek_fingerprint_from_cert(cert_pem)
        if cert_ek_fp:
            if (
                existing
                and existing.ek_fingerprint
                and not fingerprints_match(cert_ek_fp, existing.ek_fingerprint)
            ):
                raise HTTPException(
                    403,
                    "Enrollment cert EK fingerprint does not match registered machine hardware identity",
                )
        else:
            logger.warning(
                "Enrollment cert for machine %s has no EK SAN — skipping EK fingerprint check (legacy cert)",
                machine_id,
            )

        config_token = secrets.token_urlsafe(32)

        if existing:
            if existing.status == MachineStatus.rejected:
                raise HTTPException(403, f"Machine {machine_id} has been rejected")
            existing.status         = MachineStatus.attested
            existing.attested_at    = datetime.now(timezone.utc)
            existing.config_token   = config_token
            existing.token_consumed = False
            machine = self.machine_repo.save(existing)
            logger.info("Cert enrollment: machine %s updated and attested", machine_id)
        else:
            try:
                role = NodeRole(role_str)
            except ValueError:
                role = NodeRole.worker_app
            machine = self.machine_repo.save(MachineRow(
                machine_id     = machine_id,
                ek_fingerprint = "",  # updated when /attest is called with full EK material
                ek_source      = "enrollment-cert",
                role           = role,
                status         = MachineStatus.attested,
                config_token   = config_token,
                attested_at    = datetime.now(timezone.utc),
            ))
            logger.info(
                "Cert enrollment: new machine %s role=%s registered+attested", machine_id, role
            )

        return AttestResponse(
            machine_id = machine.machine_id,
            status     = "attested",
            hostname   = machine.hostname,
            role       = machine.role.value,
            message    = "Machine enrolled and attested via certificate — config URL ready",
        )

    def request_cert(self, machine_id: str, req: CertRequest) -> CertResponse:
        """Issue an enrollment certificate to the machine itself (EK-authenticated)."""
        machine = self.machine_repo.get_by_id(machine_id)
        if not machine:
            raise HTTPException(404, f"Machine {machine_id} not found")

        if machine.status in (MachineStatus.rejected, MachineStatus.locked, MachineStatus.revoked):
            raise HTTPException(
                403,
                f"Machine {machine_id} status={machine.status.value} — cert issuance denied",
            )

        if req.ek_cert_pem:
            try:
                verify_ek_pem(req.ek_cert_pem, req.ek_source)
            except ValueError as exc:
                raise HTTPException(422, f"Invalid EK material: {exc}") from exc

            computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
            if not fingerprints_match(computed_fp, machine.ek_fingerprint):
                raise HTTPException(
                    403,
                    f"EK fingerprint mismatch: request {req.ek_fingerprint[:12]}... "
                    f"vs registered {machine.ek_fingerprint[:12]}...",
                )
        else:
            if not fingerprints_match(req.ek_fingerprint, machine.ek_fingerprint):
                raise HTTPException(403, "EK fingerprint does not match registered machine")

        cert_pem, key_pem = issue_enrollment_cert(
            machine_id     = machine.machine_id,
            role           = machine.role.value,
            ek_fingerprint = machine.ek_fingerprint,
        )
        ca_pem = get_ca_cert_pem()

        encrypted_key_b64 = ""
        if req.wrapping_key_pem:
            try:
                encrypted_key_b64 = encrypt_with_rsa_pubkey(key_pem.encode(), req.wrapping_key_pem)
                logger.info("Enrollment key transport-encrypted for machine=%s", machine_id)
            except ValueError as exc:
                # RT-06: Hard-fail — never return plaintext private key when wrapping was requested
                raise HTTPException(
                    422,
                    f"Wrapping key encryption failed: {exc}. "
                    "Correct or omit wrapping_key_pem to receive an unencrypted key.",
                ) from exc

        logger.info(
            "Enrollment cert issued via request-cert: machine=%s role=%s ek=%s... encrypted=%s",
            machine_id, machine.role.value, machine.ek_fingerprint[:12], bool(encrypted_key_b64),
        )

        return CertResponse(
            machine_id                   = machine.machine_id,
            role                         = machine.role.value,
            enrollment_cert_pem          = cert_pem,
            enrollment_key_pem           = "" if encrypted_key_b64 else key_pem,
            enrollment_key_encrypted_b64 = encrypted_key_b64,
            enrollment_ca_pem            = ca_pem,
            valid_days                   = CERT_VALID_DAYS,
            message                      = (
                "Enrollment cert issued — save enrollment.crt, enrollment.key, "
                "and enrollment-ca.crt to /itl/ on the EFI partition before rebooting into Talos."
            ),
        )

"""Routes for machine administration and enrollment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..core.deps import (
    get_approval_repo,
    get_audit_repo,
    get_machine_repo,
    resolve_operator,
)
from ..handlers.enrollment import EnrollmentHandler
from ..handlers.machines import MachineAdminHandler
from ..pki.quote_verifier import QuoteVerifier, QuoteVerificationError
from ..repositories.machine_repo import SqlMachineRepository
from ..repositories.operator_repo import AuditRepository, ApprovalRepository
from ..schemas.requests import ApproveRequest, CertRequest, LockRequest, RevokeRequest
from ..schemas.responses import (
    ApprovalDetail,
    AttestResponse,
    CertResponse,
    MachineDetail,
)

router = APIRouter(tags=["machines"])


class EnrollRequest(BaseModel):
    """Pydantic schema for POST /enroll (HIGH-06)."""

    cert_pem:         str
    nonce:            str
    nonce_signature:  str


def _make_handler(
    machine_repo: SqlMachineRepository,
    audit_repo: AuditRepository,
    approval_repo: ApprovalRepository,
) -> MachineAdminHandler:
    return MachineAdminHandler(
        machine_repo  = machine_repo,
        audit_repo    = audit_repo,
        approval_repo = approval_repo,
    )


@router.get("", response_model=list[MachineDetail])
def list_machines(
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """List all registered machines (admin)."""
    return _make_handler(machine_repo, audit_repo, approval_repo).list_machines()


@router.post("/{machine_id}/approve")
def approve_machine(
    machine_id: str,
    req: ApproveRequest,
    response: Response,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Approve a pending machine and assign its role (admin).

    Returns 200 with MachineDetail when the approval is immediate, or 202
    with PendingApprovalResponse when dual-control is required and only one
    operator has approved so far.
    """
    body, status_code = _make_handler(machine_repo, audit_repo, approval_repo).approve(
        machine_id, req, operator_cn
    )
    response.status_code = status_code
    return body


@router.post("/{machine_id}/revoke", response_model=MachineDetail)
def revoke_machine(
    machine_id: str,
    req: RevokeRequest,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Revoke a machine (admin)."""
    return _make_handler(machine_repo, audit_repo, approval_repo).revoke(
        machine_id, req, operator_cn
    )


@router.post("/{machine_id}/lock", response_model=MachineDetail)
def lock_machine(
    machine_id: str,
    req: LockRequest,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Temporarily lock a machine (admin)."""
    return _make_handler(machine_repo, audit_repo, approval_repo).lock(
        machine_id, req, operator_cn
    )


@router.post("/{machine_id}/unlock", response_model=MachineDetail)
def unlock_machine(
    machine_id: str,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Unlock a previously locked machine (admin)."""
    return _make_handler(machine_repo, audit_repo, approval_repo).unlock(
        machine_id, operator_cn
    )


@router.get("/{machine_id}/offline-bundle")
def get_offline_bundle(
    machine_id: str,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Return a bundle payload for building an offline provisioning USB (admin)."""
    return _make_handler(machine_repo, audit_repo, approval_repo).offline_bundle(
        machine_id, operator_cn
    )


@router.post("/import")
def import_machine(
    receipt: dict,
    operator_cn: str = Depends(resolve_operator),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
    audit_repo: AuditRepository = Depends(get_audit_repo),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """Import a machine from an offline TPM receipt (admin). Idempotent."""
    return _make_handler(machine_repo, audit_repo, approval_repo).import_machine(
        receipt, operator_cn
    )


@router.get("/{machine_id}/approvals", response_model=list[ApprovalDetail])
def list_machine_approvals(
    machine_id: str,
    operator_cn: str = Depends(resolve_operator),
    approval_repo: ApprovalRepository = Depends(get_approval_repo),
):
    """List all dual-control approval requests for a machine (including expired/consumed)."""
    rows = approval_repo.list_for_machine(machine_id)
    return [
        ApprovalDetail(
            id          = r.id,
            machine_id  = r.machine_id,
            operator_cn = r.operator_cn,
            role        = r.role,
            hostname    = r.hostname,
            assigned_ip = r.assigned_ip,
            created_at  = r.created_at,
            expires_at  = r.expires_at,
            consumed    = r.consumed,
        )
        for r in rows
    ]


@router.post("/enroll", response_model=AttestResponse)
def enroll_machine(req: EnrollRequest, machine_repo: SqlMachineRepository = Depends(get_machine_repo)):
    """Certificate-based machine enrollment for offline-provisioned nodes."""
    return EnrollmentHandler(machine_repo).enroll(req.model_dump())


@router.post("/{machine_id}/request-cert", response_model=CertResponse)
def request_cert(
    machine_id: str,
    req: CertRequest,
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Issue an enrollment certificate to the machine itself (EK-authenticated)."""
    return EnrollmentHandler(machine_repo).request_cert(machine_id, req)


# ---------------------------------------------------------------------------
# AK activation — issue #6
# ---------------------------------------------------------------------------

class AkActivateRequest(BaseModel):
    """Request body for POST /api/v1/machines/{id}/ak-activate."""

    ek_cert_pem: str          # Must match the machine's stored EK fingerprint (HIGH-03)
    ak_pub:      str          # SubjectPublicKeyInfo PEM of the AK
    quote:       str          # base64-encoded TPM2B_ATTEST (TPMS_ATTEST)
    quote_sig:   str          # base64-encoded signature over sha384/sha256(quote)
    pcr_values:  dict[str, str]  # {"sha256:0": "<hex>", ...}
    nonce_id:    str | None = None  # anti-replay nonce from GET /attest/challenge


class AkActivateResponse(BaseModel):
    machine_id: str
    ak_accepted: bool
    message: str


@router.post("/{machine_id}/ak-activate", response_model=AkActivateResponse)
def ak_activate(
    machine_id: str,
    req: AkActivateRequest,
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Activate the node's Attestation Key (AK) by verifying a PCR quote (issue #6).

    The client generates an AK, performs a TPM2_Quote over PCR banks sha256:{0,4,7},
    signs it with the AK private key, and POSTs the result here.  On success the
    AK public key is stored; subsequent POST /attest calls may include a quote
    signed by this AK.
    """
    from ..pki.nonce_store import get_nonce_store

    nonce_bytes: bytes | None = None
    if req.nonce_id:
        store = get_nonce_store()
        try:
            nonce_bytes = store.consume(req.nonce_id)
        except TimeoutError:
            raise HTTPException(410, "Nonce has expired — request a new challenge")
        except ValueError:
            raise HTTPException(409, "Nonce already consumed — replay detected")
        except KeyError:
            raise HTTPException(422, "Unknown nonce_id — request a challenge first")

    machine = machine_repo.get_by_machine_id(machine_id)
    if machine is None:
        raise HTTPException(404, "Machine not found")

    # HIGH-03: Verify that the caller knows the EK cert matching this machine's
    # stored fingerprint.  This prevents unauthenticated AK hijacking by an
    # attacker who guesses or enumerates a valid machine_id.
    from ..pki.tpm_verifier import compute_ek_fingerprint, fingerprints_match
    try:
        presented_fp = compute_ek_fingerprint(req.ek_cert_pem)
    except (ValueError, Exception) as exc:
        raise HTTPException(422, f"Cannot parse ek_cert_pem: {exc}") from exc
    if not fingerprints_match(presented_fp, machine.ek_fingerprint):
        raise HTTPException(403, "ek_cert_pem does not match this machine's registered EK fingerprint")

    # Also reject AK activation for machines in revoked / rejected / locked states
    from ..models.machine import MachineStatus
    if machine.status in (MachineStatus.revoked, MachineStatus.rejected):
        raise HTTPException(403, f"Cannot activate AK for machine in status '{machine.status.value}'")

    verifier = QuoteVerifier()
    try:
        verifier.verify(
            ak_pub_pem=req.ak_pub,
            quote_b64=req.quote,
            sig_b64=req.quote_sig,
            pcr_values=req.pcr_values,
            nonce_bytes=nonce_bytes,
        )
    except QuoteVerificationError as exc:
        raise HTTPException(422, f"AK quote verification failed: {exc}") from exc

    machine.ak_pub = req.ak_pub
    machine_repo.save(machine)

    return AkActivateResponse(
        machine_id=machine_id,
        ak_accepted=True,
        message="AK registered and PCR quote verified",
    )


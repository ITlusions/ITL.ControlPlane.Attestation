"""Routes for machine administration and enrollment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.deps import get_machine_repo, require_admin
from ..handlers.enrollment import EnrollmentHandler
from ..handlers.machines import MachineAdminHandler
from ..pki.quote_verifier import QuoteVerifier, QuoteVerificationError
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import ApproveRequest, CertRequest, LockRequest, RevokeRequest
from ..schemas.responses import AttestResponse, CertResponse, MachineDetail

router = APIRouter(tags=["machines"])


class EnrollRequest(BaseModel):
    """Pydantic schema for POST /enroll (HIGH-06)."""

    cert_pem:         str
    nonce:            str
    nonce_signature:  str


@router.get("", response_model=list[MachineDetail])
def list_machines(_: None = Depends(require_admin), machine_repo: SqlMachineRepository = Depends(get_machine_repo)):
    """List all registered machines (admin)."""
    return MachineAdminHandler(machine_repo).list_machines()


@router.post("/{machine_id}/approve", response_model=MachineDetail)
def approve_machine(
    machine_id: str,
    req: ApproveRequest,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Approve a pending machine and assign its role (admin)."""
    return MachineAdminHandler(machine_repo).approve(machine_id, req)


@router.post("/{machine_id}/revoke", response_model=MachineDetail)
def revoke_machine(
    machine_id: str,
    req: RevokeRequest,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Revoke a machine (admin)."""
    return MachineAdminHandler(machine_repo).revoke(machine_id, req)


@router.post("/{machine_id}/lock", response_model=MachineDetail)
def lock_machine(
    machine_id: str,
    req: LockRequest,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Temporarily lock a machine (admin)."""
    return MachineAdminHandler(machine_repo).lock(machine_id, req)


@router.post("/{machine_id}/unlock", response_model=MachineDetail)
def unlock_machine(
    machine_id: str,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Unlock a previously locked machine (admin)."""
    return MachineAdminHandler(machine_repo).unlock(machine_id)


@router.get("/{machine_id}/offline-bundle")
def get_offline_bundle(
    machine_id: str,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Return a bundle payload for building an offline provisioning USB (admin)."""
    return MachineAdminHandler(machine_repo).offline_bundle(machine_id)


@router.post("/import")
def import_machine(
    receipt: dict,
    _: None = Depends(require_admin),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
):
    """Import a machine from an offline TPM receipt (admin). Idempotent."""
    return MachineAdminHandler(machine_repo).import_machine(receipt)


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

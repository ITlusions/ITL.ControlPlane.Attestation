"""Routes for TPM attestation."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException

from ..core.deps import get_machine_repo
from ..handlers.attestation import AttestationHandler
from ..pki.nonce_store import get_nonce_store, NonceStore
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import AttestRequest
from ..schemas.responses import AttestResponse

router = APIRouter(tags=["attestation"])


@router.get("/attest/challenge")
def attest_challenge(store: NonceStore = Depends(get_nonce_store)) -> dict:
    """Issue a server-side challenge nonce (issue #7).

    The client must include ``nonce_id`` in the subsequent POST /attest.
    Nonces are single-use and expire after 60 seconds.
    """
    try:
        nonce_id, nonce_bytes, expires_at = store.issue()
    except RuntimeError as exc:
        raise HTTPException(429, str(exc))
    import base64
    return {
        "nonce_id":   nonce_id,
        "nonce":      base64.b64encode(nonce_bytes).decode(),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }


@router.post("/attest", response_model=AttestResponse)
def attest(req: AttestRequest, machine_repo: SqlMachineRepository = Depends(get_machine_repo)):
    """Attest a node's TPM identity after first boot."""
    return AttestationHandler(machine_repo).attest(req)

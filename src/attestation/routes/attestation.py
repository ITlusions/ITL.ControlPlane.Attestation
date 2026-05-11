"""Routes for TPM attestation."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..core.deps import get_db
from ..handlers.attestation import AttestationHandler
from ..core.models import AttestRequest, AttestResponse

router = APIRouter(tags=["attestation"])


@router.post("/attest", response_model=AttestResponse)
def attest(req: AttestRequest, db: Session = Depends(get_db)):
    """Attest a node's TPM identity after first boot."""
    return AttestationHandler(db).attest(req)

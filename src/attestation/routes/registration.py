"""Routes for machine registration (USB agent and self-register)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..core.deps import get_db
from ..handlers.registration import RegistrationHandler
from ..core.models import RegisterRequest, RegisterResponse, SelfRegisterRequest, SelfRegisterResponse

router = APIRouter(tags=["registration"])


@router.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Register a machine by TPM EK fingerprint (USB agent flow)."""
    return RegistrationHandler(db).register(req)


@router.post("/self-register", response_model=SelfRegisterResponse)
def self_register(req: SelfRegisterRequest, db: Session = Depends(get_db)):
    """Extension-initiated registration — no USB agent required."""
    return RegistrationHandler(db).self_register(req)

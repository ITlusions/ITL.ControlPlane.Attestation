"""Routes for machine registration (USB agent and self-register)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.deps import get_machine_repo
from ..handlers.registration import RegistrationHandler
from ..repositories.machine_repo import SqlMachineRepository
from ..schemas.requests import RegisterRequest, SelfRegisterRequest
from ..schemas.responses import RegisterResponse, SelfRegisterResponse

router = APIRouter(tags=["registration"])


@router.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest, machine_repo: SqlMachineRepository = Depends(get_machine_repo)):
    """Register a machine by TPM EK fingerprint (USB agent flow)."""
    return RegistrationHandler(machine_repo).register(req)


@router.post("/self-register", response_model=SelfRegisterResponse)
def self_register(req: SelfRegisterRequest, machine_repo: SqlMachineRepository = Depends(get_machine_repo)):
    """Extension-initiated registration — no USB agent required."""
    return RegistrationHandler(machine_repo).self_register(req)

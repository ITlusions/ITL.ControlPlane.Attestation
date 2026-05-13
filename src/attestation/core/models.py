"""Backward-compat shim — contents moved to models/ and schemas/.

Import from the canonical locations instead:
  from ..models.machine import MachineRow, MachineStatus, NodeRole
  from ..schemas.requests import RegisterRequest, AttestRequest, ...
  from ..schemas.responses import RegisterResponse, MachineDetail, ...
"""
from __future__ import annotations

from ..models.machine import MachineRow, MachineStatus, NodeRole
from ..schemas.requests import (
    ApproveRequest,
    AttestRequest,
    CertRequest,
    LockRequest,
    RegisterRequest,
    RevokeRequest,
    SelfRegisterRequest,
)
from ..schemas.responses import (
    AttestResponse,
    CertResponse,
    MachineDetail,
    RegisterResponse,
    SelfRegisterResponse,
)

# Backward-compat alias: handler code that imports ``Machine`` still works
Machine = MachineRow

__all__ = [
    "Machine",
    "MachineRow",
    "MachineStatus",
    "NodeRole",
    "RegisterRequest",
    "RegisterResponse",
    "SelfRegisterRequest",
    "SelfRegisterResponse",
    "AttestRequest",
    "AttestResponse",
    "ApproveRequest",
    "RevokeRequest",
    "LockRequest",
    "CertRequest",
    "CertResponse",
    "MachineDetail",
]


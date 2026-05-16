"""pulumi-itl-attestation — Pulumi dynamic provider for the ITL Attestation Service."""

from attestation.models.machine import MachineStatus, NodeRole
from attestation.schemas.requests import ApproveRequest, RegisterRequest, RevokeRequest, LockRequest
from sdk import MachineDetail, RegisterResponse

from ._client import AttestationClient, AttestationApiError
from .resources import RegisteredMachine, MachineApproval

__all__ = [
    # Enums
    "NodeRole",
    "MachineStatus",
    # Request / response schemas (re-exported for caller convenience)
    "RegisterRequest",
    "ApproveRequest",
    "RevokeRequest",
    "LockRequest",
    "RegisterResponse",
    "MachineDetail",
    # Provider client
    "AttestationClient",
    "AttestationApiError",
    # Pulumi resources
    "RegisteredMachine",
    "MachineApproval",
]

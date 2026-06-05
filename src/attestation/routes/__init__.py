"""Routes package for the Attestation Service."""

from .attestation import router as attestation_router
from .audit import router as audit_router
from .bootstrap import router as bootstrap_router
from .config import router as config_router
from .machines import router as machines_router
from .registration import router as registration_router

__all__ = [
    "attestation_router",
    "audit_router",
    "bootstrap_router",
    "config_router",
    "machines_router",
    "registration_router",
]

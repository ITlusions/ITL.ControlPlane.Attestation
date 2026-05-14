"""SDK core exceptions."""
from __future__ import annotations


class AttestationSDKError(Exception):
    """Base exception for all SDK errors."""

    pass


class MachineNotFoundError(AttestationSDKError):
    """Machine not found in database."""

    pass


class MachineAlreadyExistsError(AttestationSDKError):
    """Machine already exists (duplicate EK fingerprint or machine_id)."""

    pass


class InvalidMachineStateError(AttestationSDKError):
    """Machine is in an invalid state for the requested operation."""

    pass


class AuditLogIntegrityError(AttestationSDKError):
    """Audit log chain integrity violation detected."""

    pass


class DualControlRequiredError(AttestationSDKError):
    """Operation requires dual-control approval."""

    pass


class UnauthorizedError(AttestationSDKError):
    """Operator lacks required permissions."""

    pass


class TPMVerificationError(AttestationSDKError):
    """TPM verification failed (EK cert invalid, quote invalid, etc.)."""

    pass


class ConfigTokenError(AttestationSDKError):
    """Config token invalid, expired, or already consumed."""

    pass

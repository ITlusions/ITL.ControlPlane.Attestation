"""SDK core infrastructure exports."""
from sdk.core.config import AttestationConfig, config
from sdk.core.database import (
    async_session_maker,
    close_db,
    engine,
    get_session,
    init_db,
)
from sdk.core.exceptions import (
    AttestationSDKError,
    AuditLogIntegrityError,
    ConfigTokenError,
    DualControlRequiredError,
    InvalidMachineStateError,
    MachineAlreadyExistsError,
    MachineNotFoundError,
    TPMVerificationError,
    UnauthorizedError,
)

__all__ = [
    # Config
    "AttestationConfig",
    "config",
    # Database
    "engine",
    "async_session_maker",
    "get_session",
    "init_db",
    "close_db",
    # Exceptions
    "AttestationSDKError",
    "MachineNotFoundError",
    "MachineAlreadyExistsError",
    "InvalidMachineStateError",
    "AuditLogIntegrityError",
    "DualControlRequiredError",
    "UnauthorizedError",
    "TPMVerificationError",
    "ConfigTokenError",
]

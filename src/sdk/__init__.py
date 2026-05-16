"""ITL Control Plane Attestation SDK

This package provides the core data models, repositories, and infrastructure
for the ITL Control Plane Machine Attestation platform.  It is consumed by:

  - Attestation Service (src/attestation/) — FastAPI service for TPM attestation
  - Web Interface (src/web/) — Flask dashboard for operators
  - API Service (future) — Dedicated REST API for external clients

The SDK enforces a clean separation of concerns:
  - Models (sdk.models.*) — SQLModel ORM definitions
  - Repositories (sdk.repositories.*) — Data access layer
  - Core (sdk.core.*) — Database engine, configuration, exceptions

Usage:
    from sdk import MachineRow, NodeRole, MachineStatus, SqlMachineRepository
    from sdk.core import config, get_session

    async with get_session() as session:
        repo = SqlMachineRepository(session)
        machine = repo.get_by_id("a1b2c3d4-...")
        print(machine.status)
"""
from sdk.core import (
    AttestationConfig,
    AttestationSDKError,
    AuditLogIntegrityError,
    ConfigTokenError,
    DualControlRequiredError,
    InvalidMachineStateError,
    MachineAlreadyExistsError,
    MachineNotFoundError,
    TPMVerificationError,
    UnauthorizedError,
    async_session_maker,
    close_db,
    config,
    engine,
    get_session,
    init_db,
)
from sdk.extensions import AttestationExtension
from sdk.models import (
    ApprovalRequestRow,
    AuditLogRow,
    MachineRow,
    MachineStatus,
    NodeRole,
)
from sdk.repositories import (
    GENESIS_HASH,
    ApprovalRequestRepository,
    AuditRepository,
    SqlMachineRepository,
    compute_entry_hash,
)

try:
    from sdk.extensions import CliPlugin
    _cli_exports: list[str] = ["CliPlugin"]
except ImportError:
    _cli_exports = []
from sdk.schemas import MachineDetail, RegisterResponse

__version__ = "0.1.0"

__all__ = [
    "GENESIS_HASH",
    "ApprovalRequestRepository",
    "ApprovalRequestRow",
    # Config
    "AttestationConfig",
    # Extension system
    "AttestationExtension",
    # Exceptions
    "AttestationSDKError",
    "AuditLogIntegrityError",
    "AuditLogRow",
    "AuditRepository",
    "CliPlugin",
    "ConfigTokenError",
    "DualControlRequiredError",
    "InvalidMachineStateError",
    "MachineAlreadyExistsError",
    "MachineDetail",
    "MachineNotFoundError",
    # Models
    "MachineRow",
    "MachineStatus",
    "NodeRole",
    # Schemas
    "RegisterResponse",
    # Repositories
    "SqlMachineRepository",
    "TPMVerificationError",
    "UnauthorizedError",
    # Version
    "__version__",
    "async_session_maker",
    "close_db",
    "compute_entry_hash",
    "config",
    # Database
    "engine",
    "get_session",
    "init_db",
]

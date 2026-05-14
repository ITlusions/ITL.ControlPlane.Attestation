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
from sdk.models import (
    ApprovalRequestRow,
    AuditLogRow,
    MachineRow,
    MachineStatus,
    NodeRole,
)
from sdk.repositories import (
    ApprovalRequestRepository,
    AuditRepository,
    GENESIS_HASH,
    SqlMachineRepository,
    compute_entry_hash,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Config
    "AttestationConfig",
    "config",
    # Database
    "engine",
    "async_session_maker",
    "get_session",
    "init_db",
    "close_db",
    # Models
    "MachineRow",
    "NodeRole",
    "MachineStatus",
    "AuditLogRow",
    "ApprovalRequestRow",
    # Repositories
    "SqlMachineRepository",
    "AuditRepository",
    "ApprovalRequestRepository",
    "GENESIS_HASH",
    "compute_entry_hash",
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

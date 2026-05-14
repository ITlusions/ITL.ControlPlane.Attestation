# Changelog

All notable changes to the ITL Attestation SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-15

### Added
- Initial SDK release with core infrastructure
- `core/config.py` — AttestationConfig with Pydantic BaseSettings
- `core/database.py` — Async SQLAlchemy engine and session factory
- `core/exceptions.py` — Complete exception hierarchy
- `models/machine.py` — MachineRow, NodeRole, MachineStatus ORM models
- `models/operator.py` — AuditLogRow with cryptographic chain, ApprovalRequestRow
- `repositories/machine_repo.py` — SqlMachineRepository with full CRUD
- `repositories/operator_repo.py` — AuditRepository with hash verification, ApprovalRequestRepository
- Comprehensive README with usage examples
- Full type hints and mypy strict mode support
- Environment-based configuration
- Support for SQLite and async database operations

### Features
- **Cryptographic audit chain** — Hash-based integrity verification for audit logs
- **TPM attestation models** — EK fingerprint, AK public key, hardware UUID tracking
- **Dual-control approval workflow** — Multi-operator approval requests
- **Machine lifecycle states** — pending_approval → registered → attested → locked/revoked
- **Node role support** — Control plane, worker infrastructure, worker application tiers
- **Source IP tracking** — All audit log entries include originating IP address

### Dependencies
- SQLModel >=0.0.16
- SQLAlchemy[asyncio] >=2.0.0
- aiosqlite >=0.19.0
- Pydantic >=2.0.0
- Pydantic-settings >=2.0.0

[0.1.0]: https://github.com/ITLusions/ITL.ControlPlane.Attestation/releases/tag/v0.1.0

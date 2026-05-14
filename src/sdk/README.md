# ITL Attestation SDK

**Shared models, repositories and core infrastructure for ITL Control Plane Machine Attestation services**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

## Overview

The ITL Attestation SDK provides the central codebase for the Machine Attestation platform.
All data models, repositories and core infrastructure are defined here and shared by:

- **Attestation Service** — FastAPI service for TPM attestation workflows
- **Web Interface** — Flask dashboard for operators and administrators
- **API Service** (future) — Dedicated REST API for external clients

## Installation

### From PyPI (when published)

```bash
pip install itl-attestation-sdk
```

### From source (development)

```bash
# Clone the repository
git clone https://github.com/ITLusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation/src/sdk

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### As a dependency in your project

Add to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "itl-attestation-sdk>=0.1.0",
]
```

Or with `pip`:

```bash
pip install itl-attestation-sdk
```

## Quick Start

```python
from sdk import (
    MachineRow,
    NodeRole,
    MachineStatus,
    SqlMachineRepository,
    AuditRepository,
    config,
)
from sqlmodel import Session, create_engine

# Initialize database
engine = create_engine(config.db_url)
session = Session(engine)

# Create a machine repository
machine_repo = SqlMachineRepository(session)

# Register a new machine
machine = MachineRow(
    machine_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    ek_fingerprint="SHA384:1a2b3c4d...",
    role=NodeRole.controlplane,
    status=MachineStatus.pending_approval,
    hostname="cp-node-01",
)
machine_repo.save(machine)

# Log the action
audit_repo = AuditRepository(session)
audit_repo.append(
    operator_cn="admin@itlusions.com",
    action="register",
    machine_id=machine.machine_id,
    source_ip="10.0.0.1",
)

# Query machines
attested = machine_repo.list_by_status(MachineStatus.attested)
print(f"Found {len(attested)} attested machines")
```

## Features

- **Cryptographic audit chain** — Hash-based integrity verification for all audit log entries
- **TPM attestation models** — EK fingerprint, AK public key, hardware UUID tracking
- **Dual-control approval workflow** — Multi-operator approval requests with expiry
- **Machine lifecycle states** — `pending_approval` → `registered` → `attested` → `locked`/`revoked`
- **Node role support** — Control plane, worker infrastructure, worker application tiers
- **Source IP tracking** — All audit log entries include originating IP address
- **Type-safe** — Full mypy strict mode support with SQLModel + Pydantic v2
- **Async ready** — Async SQLAlchemy engine and session factory included

```
sdk/
├── core/                   # Core infrastructuur
│   ├── config.py          # AttestationConfig (Pydantic BaseSettings)
│   ├── database.py        # SQLAlchemy engine, async session factory
│   ├── exceptions.py      # SDK excepties
│   └── __init__.py        # Core exports
├── models/                # ORM models (SQLModel)
│   ├── machine.py         # MachineRow, NodeRole, MachineStatus
│   ├── operator.py        # AuditLogRow, ApprovalRequestRow
│   └── __init__.py        # Model exports
├── repositories/          # Data access layer
│   ├── machine_repo.py    # SqlMachineRepository
│   ├── operator_repo.py   # AuditRepository, ApprovalRequestRepository
│   └── __init__.py        # Repository exports
└── __init__.py            # SDK root exports

```

## Gebruik

### Basis import

```python
from sdk import (
    MachineRow,
    NodeRole,
    MachineStatus,
    SqlMachineRepository,
    config,
    get_session,
)

# Configuratie
print(config.db_url)  # sqlite:///d:/repos/.../data/machines.db

# Database sessie
async with get_session() as session:
    repo = SqlMachineRepository(session)
    machine = repo.get_by_id("a1b2c3d4-...")
    print(machine.status)
```

### Models

```python
from sdk.models import MachineRow, MachineStatus, NodeRole

# Nieuwe machine aanmaken
machine = MachineRow(
    machine_id="a1b2c3d4-...",
    ek_fingerprint="SHA384:...",
    role=NodeRole.controlplane,
    status=MachineStatus.pending_approval,
    hostname="cp-node-01",
)
```

### Repositories

```python
from sdk.repositories import SqlMachineRepository, AuditRepository

# Machine operations
repo = SqlMachineRepository(session)
machines = repo.list_all()
machine = repo.get_by_id("...")
repo.save(machine)

# Audit log (cryptographically chained)
audit = AuditRepository(session)
entry = AuditLogRow(
    operator_cn="admin@itlusions.com",
    action="approve",
    machine_id="...",
    detail="Approved for production cluster",
)
audit.append(entry)  # Auto-computes prev_hash and entry_hash
```

## Configuration

All configuration is done via environment variables with the `ATTESTATION_` prefix:

```bash
# Database
ATTESTATION_DB_URL=sqlite:///./data/machines.db
ATTESTATION_DB_ECHO=false

# Service
ATTESTATION_SERVICE_NAME=attestation
ATTESTATION_ENVIRONMENT=production

# Logging
ATTESTATION_LOG_LEVEL=INFO
ATTESTATION_LOG_JSON=true

# Keycloak OIDC
ATTESTATION_KEYCLOAK_URL=https://sts.itlusions.com
ATTESTATION_KEYCLOAK_REALM=itlusions
ATTESTATION_KEYCLOAK_CLIENT_ID=attestation

# Security
ATTESTATION_ADMIN_TOKEN=<break-glass-token>
ATTESTATION_REQUIRE_DUAL_CONTROL=false
```

Or via a `.env` file loaded with `python-dotenv`.

## Development

### Setup

```bash
# Clone and install
git clone https://github.com/ITLusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation/src/sdk
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Type checking
mypy .

# Linting
ruff check .
ruff format .
```

### Building

```bash
# Build wheel
python -m build

# Install locally
pip install dist/itl_attestation_sdk-0.1.0-py3-none-any.whl
```

### Publishing

```bash
# Test PyPI
python -m twine upload --repository testpypi dist/*

# Production PyPI
python -m twine upload dist/*
```

## Project Structure

```
sdk/
├── pyproject.toml         # Package metadata and dependencies
├── README.md              # This file
├── CHANGELOG.md           # Version history
├── LICENSE                # MIT License
├── .gitignore             # Git ignore rules
├── core/                  # Core infrastructure
│   ├── __init__.py       # Core exports
│   ├── config.py         # AttestationConfig (Pydantic BaseSettings)
│   ├── database.py       # SQLAlchemy engine, async session factory
│   └── exceptions.py     # SDK exception hierarchy
├── models/               # ORM models (SQLModel)
│   ├── __init__.py      # Model exports
│   ├── machine.py       # MachineRow, NodeRole, MachineStatus
│   └── operator.py      # AuditLogRow, ApprovalRequestRow
├── repositories/        # Data access layer
│   ├── __init__.py     # Repository exports
│   ├── machine_repo.py # SqlMachineRepository
│   └── operator_repo.py # AuditRepository, ApprovalRequestRepository
└── __init__.py         # SDK root exports
```

## API Reference

### Core Configuration

```python
from sdk.core import config, init_db, close_db

# Access configuration
print(config.db_url)  # sqlite:///d:/repos/.../data/machines.db
print(config.service_name)  # "attestation"

# Initialize database (async)
await init_db()  # CREATE TABLE IF NOT EXISTS

# Cleanup at shutdown
await close_db()  # Close all connections
```

### Models

```python
from sdk.models import (
    MachineRow,
    MachineStatus,
    NodeRole,
    AuditLogRow,
    ApprovalRequestRow,
)

# Create a new machine
machine = MachineRow(
    machine_id="uuid-v4",
    ek_fingerprint="SHA384:...",
    role=NodeRole.controlplane,  # controlplane | worker-infra | worker-app
    status=MachineStatus.pending_approval,
    hostname="cp-node-01",
)

# Machine status enum
MachineStatus.pending_approval  # Awaiting operator approval
MachineStatus.registered        # Approved, config token issued
MachineStatus.attested          # TPM attestation successful
MachineStatus.locked            # Temporarily disabled
MachineStatus.revoked           # Permanently disabled
```

### Repositories

```python
from sdk.repositories import (
    SqlMachineRepository,
    AuditRepository,
    ApprovalRequestRepository,
)

# Machine operations
repo = SqlMachineRepository(session)
machines = repo.list_all()
machine = repo.get_by_id("uuid")
machine = repo.get_by_ek_fingerprint("SHA384:...")
repo.save(machine)
repo.delete(machine.machine_id)

# Audit log (cryptographically chained)
audit = AuditRepository(session)
audit.append(
    operator_cn="admin@itlusions.com",
    action="approve",
    machine_id="uuid",
    detail="Approved for production cluster",
    source_ip="10.0.0.1",
)
entries = audit.list_page(page=1, per_page=50)
is_valid = audit.verify_chain()  # Check hash integrity

# Approval requests (dual-control workflow)
approval_repo = ApprovalRequestRepository(session)
request = approval_repo.create(
    machine_id="uuid",
    requested_by="operator1@itlusions.com",
    reason="Production deployment",
)
active = approval_repo.get_active_for_machine("uuid")
approval_repo.consume(request.id, approved_by="operator2@itlusions.com")
```

### Exceptions

```python
from sdk.core import (
    AttestationSDKError,           # Base exception
    MachineNotFoundError,
    MachineAlreadyExistsError,
    InvalidMachineStateError,
    AuditLogIntegrityError,
    DualControlRequiredError,
    UnauthorizedError,
    TPMVerificationError,
    ConfigTokenError,
)

try:
    machine = repo.get_by_id("invalid")
    if not machine:
        raise MachineNotFoundError(f"Machine not found: invalid")
except MachineNotFoundError as e:
    print(f"Error: {e}")
```

## Migration from Attestation Service

If you're migrating from the old `attestation.models` structure:

### Old imports (deprecated)
```python
from attestation.models.machine import MachineRow, MachineStatus
from attestation.repositories.machine_repo import SqlMachineRepository
```

### New imports (SDK)
```python
from sdk.models import MachineRow, MachineStatus
from sdk.repositories import SqlMachineRepository
```

All functionality remains the same — only the import path changes.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8
- Use type hints (mypy strict mode)
- Write docstrings for public APIs
- Add tests for new features
- Run `ruff check .` and `mypy .` before committing

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality
- **PATCH** version for backwards-compatible bug fixes

Current version: **0.1.0**

```python
from sdk import __version__
print(__version__)  # "0.1.0"
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/ITLusions/ITL.ControlPlane.Attestation/issues)
- **Documentation**: [README](https://github.com/ITLusions/ITL.ControlPlane.Attestation/blob/main/src/sdk/README.md)
- **Contact**: info@itlusions.com

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed version history.

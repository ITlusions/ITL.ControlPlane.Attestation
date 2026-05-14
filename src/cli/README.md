# ITL Attestation CLI

**Command-line interface for ITL Control Plane Machine Attestation platform**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## Overview

The ITL Attestation CLI provides a command-line interface for managing machines in the attestation platform. It communicates with the attestation API service via REST endpoints with OIDC authentication (Keycloak).

## Features

- **Multiple authentication methods**:
  - Interactive browser-based (PKCE flow)
  - Command-line username/password
  - Device code flow (for headless environments)
- **Token caching** — Automatic token storage and refresh
- **Machine management** — List, approve, lock, unlock, revoke machines
- **Audit log access** — View and verify cryptographic audit chain
- **JSON and table output** — Flexible output formatting
- **Environment-based configuration** — Configure via env vars or command options

## Installation

### From PyPI (when published)

```bash
pip install itl-attestation-cli
```

### From source (development)

```bash
# Clone the repository
git clone https://github.com/ITLusions/ITL.ControlPlane.Attestation.git
cd ITL.ControlPlane.Attestation/src/cli

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Verify installation

```bash
attestation --version
```

## Quick Start

### 1. Login

**Interactive browser login (recommended)**:
```bash
attestation auth login
```

**Command-line login**:
```bash
attestation auth login --method password -u admin@itlusions.com
```

**Device code flow** (for headless servers):
```bash
attestation auth login --method device
```

### 2. List machines

```bash
attestation machine list
```

Filter by status or role:
```bash
attestation machine list --status pending_approval
attestation machine list --role controlplane
```

### 3. Approve a machine

```bash
attestation machine approve <machine-id> --reason "Production deployment"
```

### 4. View audit logs

```bash
attestation audit list
attestation audit list --machine-id <machine-id>
```

### 5. Verify audit chain integrity

```bash
attestation audit verify
```

## Configuration

Configuration is done via environment variables:

```bash
# Attestation API
export ATTESTATION_API_URL=http://localhost:9000

# Keycloak OIDC
export KEYCLOAK_URL=https://sts.itlusions.com
export KEYCLOAK_REALM=itlusions
export KEYCLOAK_CLIENT_ID=attestation-cli
```

Or create a `.env` file:

```ini
ATTESTATION_API_URL=http://localhost:9000
KEYCLOAK_URL=https://sts.itlusions.com
KEYCLOAK_REALM=itlusions
KEYCLOAK_CLIENT_ID=attestation-cli
```

## Commands

### Authentication

```bash
# Login with interactive browser
attestation auth login

# Login with username/password
attestation auth login --method password -u admin@itlusions.com

# Login with device code
attestation auth login --method device

# Show current user
attestation auth whoami

# Logout
attestation auth logout

# List cached tokens
attestation auth cache-list

# Clear all cached tokens
attestation auth clear-cache
```

### Machine Management

```bash
# List all machines
attestation machine list

# List with filters
attestation machine list --status attested
attestation machine list --role worker-infra

# Get machine details
attestation machine get <machine-id>

# Approve a pending machine
attestation machine approve <machine-id> --reason "Approved for production"

# Lock a machine (temporary disable)
attestation machine lock <machine-id> --reason "Maintenance"

# Unlock a locked machine
attestation machine unlock <machine-id>

# Revoke a machine (permanent disable)
attestation machine revoke <machine-id> --reason "Decommissioned"
```

### Audit Log

```bash
# List audit log entries
attestation audit list

# Filter by machine
attestation audit list --machine-id <machine-id>

# Pagination
attestation audit list --page 2 --per-page 100

# Verify cryptographic chain integrity
attestation audit verify
```

### Output Formats

All commands support JSON output for scripting:

```bash
# JSON output
attestation machine list --output json

# Table output (default)
attestation machine list --output table
```

## Token Management

Tokens are cached in `~/.itl/attestation-cache/` with filenames based on MD5 hashes of realm + client_id + username.

**Token lifecycle**:
1. Login stores token with expiry timestamp
2. CLI automatically loads token from cache
3. Token is refreshed if expired (refresh token available)
4. Logout removes token from cache

**Security**:
- Cache files are readable only by owner (chmod 0o600)
- Tokens never stored in plaintext config files
- Automatic expiry check before each API call

## Authentication Flows

### 1. Interactive (PKCE)

Best for developer workstations with browser access:

```bash
attestation auth login
```

- Opens browser for Keycloak login
- Uses PKCE (Proof Key for Code Exchange) for security
- No client secret required
- Most secure for public clients

### 2. Password (Resource Owner)

For automation and CI/CD:

```bash
attestation auth login --method password -u admin@itlusions.com -p <password>
```

- Direct username/password exchange
- Requires client configured for direct access grants
- Use with caution (exposes credentials)

### 3. Device Code

For headless servers and remote SSH sessions:

```bash
attestation auth login --method device
```

- CLI displays a URL and code
- User visits URL on another device
- Enters code to authorize CLI
- CLI polls for approval

## Examples

### Approve all pending machines

```bash
#!/bin/bash
for machine_id in $(attestation machine list --status pending_approval --output json | jq -r '.[].machine_id'); do
    attestation machine approve "$machine_id" --reason "Batch approval"
done
```

### Export machine inventory to JSON

```bash
attestation machine list --output json > inventory.json
```

### Check audit log integrity daily

```bash
#!/bin/bash
if attestation audit verify | grep -q "VALID"; then
    echo "✅ Audit log integrity OK"
    exit 0
else
    echo "❌ Audit log integrity FAILED"
    exit 1
fi
```

### Lock all worker-app machines for maintenance

```bash
for machine_id in $(attestation machine list --role worker-app --output json | jq -r '.[].machine_id'); do
    attestation machine lock "$machine_id" --reason "Scheduled maintenance"
done
```

## Development

### Setup

```bash
cd src/cli
pip install -e ".[dev]"
```

### Testing

```bash
pytest
mypy .
ruff check .
ruff format .
```

### Building

```bash
python -m build
twine check dist/*
```

## API Compatibility

The CLI communicates with the attestation API service via REST endpoints:

- `GET /api/v1/machines` — List machines
- `GET /api/v1/machines/{id}` — Get machine details
- `POST /api/v1/machines/{id}/approve` — Approve machine
- `POST /api/v1/machines/{id}/lock` — Lock machine
- `POST /api/v1/machines/{id}/unlock` — Unlock machine
- `POST /api/v1/machines/{id}/revoke` — Revoke machine
- `GET /api/v1/audit` — List audit logs
- `GET /api/v1/audit/verify` — Verify audit chain

**Authentication**: All API calls include `Authorization: Bearer <token>` header with OIDC access token.

## Troubleshooting

### "Not logged in" error

Run `attestation auth login` to authenticate.

### Token expired

The CLI automatically refreshes tokens. If refresh fails, login again:
```bash
attestation auth logout
attestation auth login
```

### Connection refused

Check API URL configuration:
```bash
attestation --api-url http://localhost:9000 machine list
```

### OIDC authentication fails

Verify Keycloak configuration:
```bash
export KEYCLOAK_URL=https://sts.itlusions.com
export KEYCLOAK_REALM=itlusions
export KEYCLOAK_CLIENT_ID=attestation-cli
attestation auth login
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/ITLusions/ITL.ControlPlane.Attestation/issues)
- **Documentation**: [README](https://github.com/ITLusions/ITL.ControlPlane.Attestation/blob/main/src/cli/README.md)
- **Contact**: info@itlusions.com

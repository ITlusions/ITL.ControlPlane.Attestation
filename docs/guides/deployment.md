---
layout: default
title: Deployment
category: Guides
description: Deploy the attestation service from scratch
---

# Deployment — ITL.ControlPlane.Attestation

## Requirements

- Docker 24+ or Python 3.12+
- Persistent volume for `/var/lib/itl-reg` (database, CA key material, role configs)
- `ITL_ADMIN_TOKEN` set to a strong random secret in production
- Role base configs placed at `ITL_CONFIG_CACHE_DIR` before the service can serve MachineConfigs

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `ITL_DB_URL` | `sqlite:////var/lib/itl-reg/db/machines.db` | No | SQLAlchemy database URL |
| `ITL_SERVICE_URL` | `https://attest.itlusions.com` | No | Public base URL of this service (used in config token URLs baked into ISOs) |
| `ITL_FACTORY_URL` | `https://factory.talos.dev` | No | Talos Image Factory base URL |
| `ITL_TALOS_VERSION` | `v1.9.5` | No | Talos version used when building ISO URLs |
| `ITL_INSTALLER_IMAGE` | `ghcr.io/itlusions/itl-talos-installer:latest` | No | Custom Talos installer image embedded in generated MachineConfigs |
| `ITL_ADMIN_TOKEN` | *(empty)* | No (break-glass only) | Shared Bearer token — emergency break-glass path. Prefer Keycloak OIDC for normal operator access. Service returns 503 for admin calls when neither OIDC nor this token is configured. |
| `ITL_ENROLLMENT_CERT_DAYS` | `30` | No | Validity period for issued enrollment certificates |
| `ITL_ENROLLMENT_CA_DIR` | `/var/lib/itl-reg/ca` | No | Directory for Enrollment CA key + cert PEM files |
| `ITL_ENROLLMENT_CA_ALGORITHM` | `ecdsa-p384` | No | CA key algorithm: `ecdsa-p384` (CNSA 2.0 default) or `rsa-4096` |
| `ITL_CONFIG_CACHE_DIR` | `/var/lib/itl-reg/configs` | No | Directory containing role base config YAML files |
| `ITL_TPM_VERIFY_CA` | `false` | No | Enable EK cert chain verification against manufacturer CA bundles |
| `ITL_TPM_VERIFY_CA_STRICT` | `false` | No | When `true`, reject registration if manufacturer CA verification fails |
| `ITL_TPM_CA_BUNDLE_DIR` | `/var/lib/itl-reg/ca-bundles` | No | Directory containing TPM manufacturer CA PEM bundles (Infineon, NTC, STM, etc.) |
| `ITL_REQUIRE_NONCE` | `false` | No | Require anti-replay nonce (`nonce_id`) in every `POST /attest` request |
| `ITL_REQUIRE_QUOTE` | `false` | No | Require a verified PCR quote in every `POST /attest` request |
| `ITL_HIGH_ASSURANCE` | `false` | No | Enable high-assurance mode (enforces TLS 1.3 only) |
| **`ITL_OIDC_ISSUER`** | *(empty)* | **Yes in production** | Keycloak realm URL — e.g. `https://sts.itlusions.com/realms/itl`. Enables OIDC operator authentication when set. |
| **`ITL_OIDC_AUDIENCE`** | `attestation-service` | No | Expected `aud` claim in Keycloak JWTs. Must match the Keycloak client configured for this service. |
| **`ITL_OIDC_OPERATOR_ROLE`** | `attestation-operator` | No | Keycloak realm-role (or client-role) required to access admin endpoints. Tokens without this role are rejected with 403. Set to `""` to skip role enforcement (not recommended). |
| **`ITL_OIDC_ENABLED`** | `true` | No | Set `false` to disable OIDC validation even when `ITL_OIDC_ISSUER` is set. Useful for local dev. |
| **`ITL_DUAL_CONTROL_ROLES`** | *(empty)* | No | Comma-separated list of machine roles requiring 2-of-N operator approval before a machine is registered. E.g. `controlplane` or `controlplane,worker-infra`. |
| **`ITL_DUAL_CONTROL_QUORUM`** | `2` | No | Number of distinct operator approvals required for dual-control roles. |
| **`ITL_DUAL_CONTROL_WINDOW_SECONDS`** | `600` | No | How long (seconds) the first approval vote remains valid. If the second vote does not arrive within this window, the first vote expires and a new window starts. |
| **`ITL_REQUIRE_ENCRYPTED_DELIVERY`** | `false` | No | When `true`, plaintext MachineConfig delivery returns HTTP 406. Clients must send `Accept: application/vnd.itl.config.encrypted+json`. Requires all machines to have an EK cert stored (re-register or re-attest to populate). |

---

## Docker Compose (recommended)

```yaml
services:
  attestation:
    image: ghcr.io/itlusions/itl-controlplane-attestation:latest
    ports:
      - "8080:8080"
    environment:
      ITL_SERVICE_URL: https://attest.itlusions.com
      # Keycloak OIDC — operators authenticate via Keycloak at sts.itlusions.com
      ITL_OIDC_ISSUER: https://sts.itlusions.com/realms/itl
      ITL_OIDC_AUDIENCE: attestation-service
      ITL_OIDC_OPERATOR_ROLE: attestation-operator
      # Dual-control: require 2-of-N approval for controlplane nodes
      ITL_DUAL_CONTROL_ROLES: controlplane
      ITL_DUAL_CONTROL_QUORUM: "2"
      ITL_DUAL_CONTROL_WINDOW_SECONDS: "600"
      # Break-glass token (emergency only — prefer OIDC for normal operator access)
      ITL_ADMIN_TOKEN: ${ITL_ADMIN_TOKEN}
      ITL_TALOS_VERSION: v1.9.5
      ITL_INSTALLER_IMAGE: ghcr.io/itlusions/itl-talos-installer:latest
    volumes:
      - itl-reg-data:/var/lib/itl-reg
    restart: unless-stopped

volumes:
  itl-reg-data:
```

Start:
```sh
ITL_ADMIN_TOKEN=$(openssl rand -hex 32) docker compose up -d
```

---

## Volume Layout

The named volume (or host path) at `/var/lib/itl-reg` contains:

```
/var/lib/itl-reg/
├── ca/
│   ├── enrollment-ca.key    # RSA-4096 private key (mode 0600, auto-generated)
│   └── enrollment-ca.crt    # Self-signed CA cert (valid 10 years)
├── configs/
│   ├── controlplane-final.yaml
│   ├── worker-infra-final.yaml
│   └── worker-app-final.yaml
└── db/
    └── machines.db          # SQLite database
```

The CA key material is auto-generated on first startup. Back it up — losing it invalidates all outstanding enrollment certs.

---

## CLI Installation

The ITL Attestation CLI (`itl-attestation-cli`) is a separate PyPI package for operators to manage machines from the command line.

### Install from PyPI

```sh
pip install itl-attestation-cli
```

### Verify installation

```sh
attestation --version
```

### Configuration

The CLI is configured via environment variables or command-line options:

| Variable | Default | Description |
|---|---|---|
| `ATTESTATION_API_URL` | `http://localhost:9000` | Attestation API base URL |
| `KEYCLOAK_URL` | `https://sts.itlusions.com` | Keycloak base URL |
| `KEYCLOAK_REALM` | `itlusions` | Keycloak realm |
| `KEYCLOAK_CLIENT_ID` | `attestation-cli` | OIDC client ID |

Create a `.env` file or export environment variables:

```sh
export ATTESTATION_API_URL=https://attest.itlusions.com
export KEYCLOAK_URL=https://sts.itlusions.com
export KEYCLOAK_REALM=itlusions
export KEYCLOAK_CLIENT_ID=attestation-cli
```

### Authentication

The CLI supports three authentication methods:

**1. Interactive browser login (recommended):**
```sh
attestation auth login
```
Opens a browser for Keycloak login using PKCE flow. Most secure for public clients.

**2. Command-line username/password:**
```sh
attestation auth login --method password -u admin@itlusions.com
```
Direct username/password exchange. Use with caution.

**3. Device code flow (headless servers):**
```sh
attestation auth login --method device
```
Displays a URL and code to enter on another device. Ideal for SSH sessions.

### Token caching

Tokens are cached in `~/.itl/attestation-cache/` with MD5-hashed filenames. The CLI automatically refreshes expired tokens. Use `attestation auth cache-list` to view cached tokens and `attestation auth clear-cache` to remove them.

### Quick start

```sh
# Login
attestation auth login

# List machines
attestation machine list

# Filter by status
attestation machine list --status pending_approval

# Approve a machine
attestation machine approve <machine-id> --reason "Production deployment"

# View audit logs
attestation audit list

# Verify cryptographic chain integrity
attestation audit verify
```

### Output formats

All commands support JSON output for scripting:

```sh
attestation machine list --output json
attestation audit list --output json | jq '.entries[] | select(.action == "APPROVE")'
```

### CLI vs Web Dashboard vs curl

| Method | Use case |
|---|---|
| **CLI** | Operator workstations, scripting, CI/CD |
| **Web Dashboard** | Visual overview, compliance metrics, bulk operations |
| **curl** | Emergency break-glass, automation without Python |

---

## Role Base Configs

The service cannot serve MachineConfigs until role base configs are present in `ITL_CONFIG_CACHE_DIR`. These files are produced by the `ITL.Talos.HardenedOS` CI pipeline and published as GitHub Release assets.

Download them before starting the service:

```sh
RELEASE_TAG=v1.9.5

gh release download $RELEASE_TAG \
  --repo ITlusions/ITL.Talos.HardenedOS \
  --pattern "*.yaml" \
  --dir /var/lib/itl-reg/configs
```

Or mount them as a ConfigMap in Kubernetes.

---

## Running Locally (Development)

```sh
pip install -e ".[dev]"

# Minimal env for local dev
export ITL_DB_URL="sqlite:///./dev.db"
export ITL_SERVICE_URL="http://localhost:8080"
export ITL_ADMIN_TOKEN="dev-token"       # break-glass; OIDC not required locally
export ITL_OIDC_ENABLED="false"          # disable OIDC for local dev
export ITL_CONFIG_CACHE_DIR="./configs"
export ITL_ENROLLMENT_CA_DIR="./ca"

uvicorn src.attestation.main:app --reload --port 8080
```

---

## Building the Docker Image

```sh
docker build -t itl-controlplane-attestation:local .
```

The image is based on `python:3.12-slim` and installs system packages `gcc libssl-dev curl` for the `cryptography` wheel.

---

## Production Checklist

- [ ] `ITL_OIDC_ISSUER` set to the Keycloak realm URL (`https://sts.itlusions.com/realms/itl`)
- [ ] `ITL_OIDC_OPERATOR_ROLE` matches the Keycloak realm-role assigned to operators
- [ ] `ITL_DUAL_CONTROL_ROLES` set to the roles requiring 2-of-N approval (e.g. `controlplane`)
- [ ] `ITL_ADMIN_TOKEN` set to a cryptographically random value (min 32 bytes hex) — stored in a secrets manager, **not** in version control
- [ ] `ITL_REQUIRE_ENCRYPTED_DELIVERY=true` after all machines have registered / attested (EK certs stored)
- [ ] Volume `/var/lib/itl-reg` mounted on persistent storage (not ephemeral)
- [ ] CA key material backed up off-host
- [ ] Role base configs pre-loaded into `ITL_CONFIG_CACHE_DIR`
- [ ] `ITL_SERVICE_URL` matches the public HTTPS hostname (correct URL is baked into ISOs)
- [ ] TLS termination in place upstream (nginx / Caddy / Kubernetes Ingress)
- [ ] Healthcheck endpoint reachable: `GET /healthz` → `{"status": "ok"}`
- [ ] Audit log forwarded to SIEM (`GET /api/v1/audit` or structured log stream)

---

## CI/CD

Two GitHub Actions workflows:

| File | Trigger | Jobs |
|---|---|---|
| `.github/workflows/ci.yml` | push, PR, manual | `test` (Python 3.12 + 3.13), `build` (docker build) |

The `test` job runs `pytest tests/ -v --tb=short`. The `build` job runs `docker build` to verify the image builds without publishing. Publishing to GHCR is done manually or via a separate release workflow.

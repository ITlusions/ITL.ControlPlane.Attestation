# ITL.ControlPlane.Attestation

![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)
![Development](https://img.shields.io/badge/development-in%20progress-yellow?style=flat-square)

> **Alpha** — This project is under active development. APIs, data models, and behaviour may change without notice.

TPM EK-based hardware identity registration, machine lifecycle management, and enrollment CA for ITL Control Plane nodes.

Machines are registered by TPM Endorsement Key fingerprint before deployment. On first boot the `itl-tpm-register` Talos extension self-attests and receives a signed MachineConfig — no manual bootstrap required.

---

## Flows

### USB Agent flow (physical provisioning)
```
USB agent reads TPM EK
  → POST /api/v1/register
  → service returns iso_url + config_url
  → operator burns ISO, machine boots
  → itl-tpm-register calls POST /api/v1/attest
  → operator approves → action=apply-config
  → extension fetches config_url and applies MachineConfig
```

### Extension self-register flow (generic ISO boot)
```
Machine boots any Talos ISO with talos.config=<service-url>
  → itl-tpm-register calls POST /api/v1/self-register
  → operator approves via POST /machines/{id}/approve
  → extension polls POST /api/v1/attest
  → action=apply-config → extension fetches and applies MachineConfig
```

---

## ISO Delivery

| Env var | Value | Behaviour |
|---|---|---|
| `ITL_ISO_URL` | set | Returns pre-built ITL HardenedOS ISO (all extensions baked in) |
| `ITL_ISO_URL` | empty | Falls back to Talos Image Factory |
| `ITL_FACTORY_URL` | `https://factory.talos.dev` | Official factory (default) |
| `ITL_FACTORY_URL` | `https://factory.itlusions.com` | Self-hosted factory |
| `ITL_FACTORY_EXTENSIONS` | comma-separated names | Extra extensions included in factory schematic |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ITL_SERVICE_URL` | `https://attest.itlusions.com` | Public base URL (used in config token URLs) |
| `ITL_ADMIN_TOKEN` | *(empty)* | Bearer token for admin endpoints — **required in production** |
| `ITL_ISO_URL` | *(empty)* | Pre-built ITL HardenedOS ISO URL. Falls back to Image Factory when unset |
| `ITL_FACTORY_URL` | `https://factory.talos.dev` | Talos Image Factory endpoint |
| `ITL_FACTORY_EXTENSIONS` | *(empty)* | Comma-separated extra extensions for factory schematic (self-hosted factory) |
| `ITL_TALOS_VERSION` | `v1.9.5` | Talos version used in factory ISO URLs |
| `ITL_INSTALLER_IMAGE` | `ghcr.io/itlusions/itl-talos-installer:latest` | Installer image embedded in MachineConfigs |
| `ITL_DB_URL` | `sqlite:////var/lib/itl-reg/db/machines.db` | SQLAlchemy database URL |
| `ITL_ENROLLMENT_CA_DIR` | `/var/lib/itl-reg/ca` | Enrollment CA key + cert directory |
| `ITL_CONFIG_CACHE_DIR` | `/var/lib/itl-reg/configs` | Role base config YAML directory |
| `ITL_ENROLLMENT_CERT_DAYS` | `30` | Validity period for issued enrollment certificates |
| `ITL_ENROLLMENT_CA_ALGORITHM` | `ecdsa-p384` | CA key algorithm: `ecdsa-p384` (default) or `rsa-4096` |
| `ITL_TPM_VERIFY_CA` | `false` | Enable EK cert chain verification against manufacturer CA bundles |
| `ITL_TPM_VERIFY_CA_STRICT` | `false` | Reject registration when manufacturer CA verification fails |
| `ITL_TPM_CA_BUNDLE_DIR` | `/var/lib/itl-reg/ca-bundles` | Directory containing TPM manufacturer CA PEM bundles |
| `ITL_REQUIRE_NONCE` | `false` | Require anti-replay nonce (`nonce_id`) in every `POST /attest` |
| `ITL_REQUIRE_QUOTE` | `false` | Require a verified PCR quote in every `POST /attest` |
| `ITL_HIGH_ASSURANCE` | `false` | Enable high-assurance mode (TLS 1.3 enforcement) |

---

## Quick Start

```sh
# Generate admin token
export ITL_ADMIN_TOKEN=$(openssl rand -hex 32)

# Run
docker compose up -d

# Check
curl https://attest.itlusions.com/healthz
```

Production with pre-built ITL HardenedOS ISO:
```yaml
environment:
  ITL_ADMIN_TOKEN: ${ITL_ADMIN_TOKEN}
  ITL_ISO_URL: https://github.com/ITlusions/ITL.Talos.HardenedOS/releases/download/v1.9.5/itl-talos-v1.9.5.iso
  ITL_SERVICE_URL: https://attest.itlusions.com
```

Self-hosted factory with ITL extensions:
```yaml
environment:
  ITL_FACTORY_URL: https://factory.itlusions.com
  ITL_FACTORY_EXTENSIONS: itlusions/itl-talos-hardened-os-branding,itlusions/itl-talos-tpm-register
```

---

## Volume Layout

```
/var/lib/itl-reg/
├── ca/
│   ├── enrollment-ca.key    # RSA-4096 CA private key (auto-generated, back this up)
│   └── enrollment-ca.crt    # Self-signed CA cert (10-year validity)
├── configs/
│   ├── controlplane-final.yaml
│   ├── worker-infra-final.yaml
│   └── worker-app-final.yaml
└── db/
    └── machines.db
```

---

## API

Interactive docs: `https://attest.itlusions.com/docs`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/healthz` | — | Liveness probe |
| `POST` | `/api/v1/register` | — | Register machine by TPM EK (USB agent) |
| `POST` | `/api/v1/self-register` | — | Extension self-registration on first boot |
| `GET` | `/api/v1/attest/challenge` | — | Issue anti-replay nonce for attestation |
| `POST` | `/api/v1/attest` | — | Attest machine identity; returns action |
| `GET` | `/api/v1/config` | — | Generic config endpoint (MAC-based lookup) |
| `GET` | `/api/v1/config/{token}` | — | One-time config token endpoint |
| `GET` | `/api/v1/machines` | Admin | List all machines |
| `POST` | `/api/v1/machines/{id}/approve` | Admin | Approve pending machine |
| `POST` | `/api/v1/machines/{id}/reject` | Admin | Reject machine |
| `POST` | `/api/v1/machines/{id}/revoke` | Admin | Revoke registered machine |
| `POST` | `/api/v1/machines/{id}/lock` | Admin | Temporarily lock machine |
| `POST` | `/api/v1/machines/{id}/unlock` | Admin | Unlock locked machine |
| `GET` | `/api/v1/machines/{id}/offline-bundle` | Admin | USB provisioning bundle |
| `POST` | `/api/v1/machines/import` | Admin | Import machine from offline TPM receipt |
| `POST` | `/api/v1/machines/enroll` | — | Cert-based self-enrollment |
| `POST` | `/api/v1/machines/{id}/request-cert` | Machine cert | Issue new enrollment cert |
| `POST` | `/api/v1/machines/{id}/ak-activate` | Machine | Activate Attestation Key via PCR quote |

Full reference: [docs/ENDPOINTS.md](docs/ENDPOINTS.md)

---

## Documentation

| File | Content |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data model, machine lifecycle |
| [docs/ENDPOINTS.md](docs/ENDPOINTS.md) | Full API reference with request/response schemas |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose, volume layout, role configs |
| [docs/SECURITY.md](docs/SECURITY.md) | Enrollment CA, TPM EK verification, threat model |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Day-2 operations, approval workflow, troubleshooting |
| [docs/TPM_EXPLAINED.md](docs/TPM_EXPLAINED.md) | TPM concepts: EK, PCRs, AK activation, quotes |

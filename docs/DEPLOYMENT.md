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
| `ITL_ADMIN_TOKEN` | *(empty)* | **Yes in production** | Bearer token for all admin endpoints. Service returns 503 for admin calls when unset. |
| `ITL_ENROLLMENT_CERT_DAYS` | `30` | No | Validity period for issued enrollment certificates |
| `ITL_ENROLLMENT_CA_DIR` | `/var/lib/itl-reg/ca` | No | Directory for Enrollment CA key + cert PEM files |
| `ITL_CONFIG_CACHE_DIR` | `/var/lib/itl-reg/configs` | No | Directory containing role base config YAML files |

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
export ITL_ADMIN_TOKEN="dev-token"
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

- [ ] `ITL_ADMIN_TOKEN` set to a cryptographically random value (min 32 bytes hex)
- [ ] Volume `/var/lib/itl-reg` mounted on persistent storage (not ephemeral)
- [ ] CA key material backed up off-host
- [ ] Role base configs pre-loaded into `ITL_CONFIG_CACHE_DIR`
- [ ] `ITL_SERVICE_URL` matches the public HTTPS hostname (correct URL is baked into ISOs)
- [ ] TLS termination in place upstream (nginx / Caddy / Kubernetes Ingress)
- [ ] Healthcheck endpoint reachable: `GET /healthz` → `{"status": "ok"}`
- [ ] Admin token not stored in version control or image layers

---

## CI/CD

Two GitHub Actions workflows:

| File | Trigger | Jobs |
|---|---|---|
| `.github/workflows/ci.yml` | push, PR, manual | `test` (Python 3.12 + 3.13), `build` (docker build) |

The `test` job runs `pytest tests/ -v --tb=short`. The `build` job runs `docker build` to verify the image builds without publishing. Publishing to GHCR is done manually or via a separate release workflow.

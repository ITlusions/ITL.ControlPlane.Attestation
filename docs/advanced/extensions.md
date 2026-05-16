---
layout: default
title: Extensions
category: Advanced
description: Custom authentication providers and integrations
---

# Extension System

The ITL Attestation Platform supports a modular extension system that allows adding functionality without modifying the core service.

## Architecture

Extensions are Python modules that implement the `AttestationExtension` ABC. They can contribute:

- **REST API routes** (via `get_router()`)
- **Database models** (via `get_models()`)
- **Lifecycle hooks** (`on_startup()`, `on_shutdown()`)

Extensions are discovered automatically at service startup from two sources:

1. **Built-in extensions** — bundled in `src/extensions/builtin/`
2. **External extensions** — installed via pip and registered via entry_points

---

## Built-in Extensions

### Secret Vault

**Name**: `secret_vault`  
**Version**: 2.0.0

TPM-bound secret storage for attested machines + shared secrets for multi-machine access. Combines machine-specific encryption (TPM-bound) with shared secret groups for operational flexibility.

**Features**:
- **Machine secrets**: TPM-bound, encrypted with EK fingerprint
- **Shared secrets**: Multi-machine access with explicit authorization
- AES-256-GCM encryption with HKDF-SHA256 key derivation
- Access tracking and audit logging
- Operator-controlled creation and deletion
- Machine-initiated retrieval (authenticated via EK fingerprint)

---

#### Machine-Specific Secrets

Secrets bound to a single machine via TPM EK fingerprint. Maximum security for machine-specific data like disk encryption keys.

**API Endpoints**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/secrets/machines/{id}/secrets` | Operator | Create secret |
| GET | `/api/v1/secrets/machines/{id}/secrets` | Operator | List secrets |
| GET | `/api/v1/secrets/machines/{id}/secrets/{name}` | Machine (EK) | Get encrypted value |
| DELETE | `/api/v1/secrets/{id}` | Operator | Delete secret |

**CLI Commands**:

```bash
# Create a secret for a machine
attestation secret create <machine-id> --name disk-key --value <secret>

# List all secrets for a machine
attestation secret list <machine-id>

# Get encrypted secret value (machine-initiated)
attestation secret get <machine-id> <secret-name> --ek-fingerprint <fp>

# Delete a secret
attestation secret delete <secret-id>
```

**Database Schema**:

```sql
CREATE TABLE extension_secrets (
    secret_id UUID PRIMARY KEY,
    machine_id UUID REFERENCES machines(machine_id),
    name VARCHAR(128) NOT NULL,
    encrypted_value BYTEA NOT NULL,  -- AES-256-GCM ciphertext
    nonce BYTEA NOT NULL,             -- GCM nonce (96 bits)
    tag BYTEA NOT NULL,               -- GCM tag (128 bits)
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(256) NOT NULL,
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    UNIQUE(machine_id, name)
);
```

**Security Model**:

1. Operator creates secret with plaintext value via authenticated API call
2. Secret is encrypted with key derived from machine's EK fingerprint using HKDF-SHA256
3. Encrypted blob, nonce, and tag are stored in database
4. Machine retrieves secret by proving EK ownership (sends fingerprint in `X-EK-Fingerprint` header)
5. Service verifies EK fingerprint matches the machine record
6. Machine receives encrypted blob that only its TPM can decrypt

---

#### Shared Secrets

Shared secrets accessible by multiple authorized machines. Encrypted with a master key (not TPM-bound). Ideal for cluster join tokens, API keys, and environment-wide certificate bundles.

**API Endpoints**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/shared-secrets` | Operator | Create shared secret |
| GET | `/api/v1/shared-secrets` | Operator | List all shared secrets |
| GET | `/api/v1/shared-secrets/{id}` | Operator | Get shared secret details |
| PUT | `/api/v1/shared-secrets/{id}` | Operator | Update/rotate secret |
| DELETE | `/api/v1/shared-secrets/{id}` | Operator | Delete shared secret |
| POST | `/api/v1/shared-secrets/{id}/access` | Operator | Grant machine access |
| DELETE | `/api/v1/shared-secrets/{id}/access` | Operator | Revoke machine access |
| GET | `/api/v1/shared-secrets/{id}/access` | Operator | List authorized machines |
| GET | `/api/v1/shared-secrets/by-name/{name}/value` | Machine (EK) | Get secret value |

**CLI Commands**:

```bash
# Create shared secret
attestation shared-secret create prod-k8s-join-token --value "K07::server:abc..." --description "Production K8s join token"

# List shared secrets
attestation shared-secret list

# Grant access to machines
attestation shared-secret grant prod-k8s-join-token --machines <uuid1>,<uuid2>,<uuid3>

# Revoke access
attestation shared-secret revoke prod-k8s-join-token --machines <uuid1>

# List authorized machines
attestation shared-secret access prod-k8s-join-token

# Rotate secret value
attestation shared-secret rotate prod-k8s-join-token --value "K07::server:xyz..."

# Delete shared secret
attestation shared-secret delete prod-k8s-join-token

# Machine retrieves value (authenticated with EK fingerprint)
curl -H "X-EK-Fingerprint: sha256:abc..." \
  http://localhost:9000/api/v1/shared-secrets/by-name/prod-k8s-join-token/value
```

**Database Schema**:

```sql
CREATE TABLE extension_shared_secrets (
    shared_secret_id UUID PRIMARY KEY,
    name VARCHAR(128) UNIQUE NOT NULL,
    encrypted_value BYTEA NOT NULL,
    nonce BYTEA NOT NULL,
    tag BYTEA NOT NULL,
    encryption_key_id VARCHAR(64) NOT NULL,  -- "master-key-v1"
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(256) NOT NULL,
    last_rotated_at TIMESTAMP,
    description VARCHAR(512)
);

CREATE TABLE extension_shared_secret_access (
    shared_secret_id UUID REFERENCES extension_shared_secrets ON DELETE CASCADE,
    machine_id UUID REFERENCES machines ON DELETE CASCADE,
    granted_at TIMESTAMP NOT NULL,
    granted_by VARCHAR(256) NOT NULL,
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    PRIMARY KEY (shared_secret_id, machine_id)
);
```

**Security Model**:

1. Operator creates shared secret via authenticated API call
2. Secret is encrypted with a master key (configured via `ITL_SHARED_SECRET_MASTER_KEY` env var or derived from `ITL_SHARED_SECRET_PASSPHRASE`)
3. Operator explicitly grants access to specific machines via access control list
4. Machine retrieves secret by proving EK ownership
5. Service verifies machine is in the authorized list
6. Machine receives decrypted plaintext value (not TPM-bound)

**Master Key Configuration**:

Option 1 — Direct key (hex-encoded):
```bash
export ITL_SHARED_SECRET_MASTER_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

Option 2 — Derive from passphrase (SHA-256):
```bash
export ITL_SHARED_SECRET_PASSPHRASE="your-secure-passphrase-here"
```

Option 3 — Random generated (DEV ONLY, not persistent):
```bash
# No env vars set → random key generated at startup (WARNING: secrets lost on restart!)
```

**Use Cases**:

| Use Case | Recommended Type |
|----------|------------------|
| Disk encryption keys | Machine-specific (TPM-bound) |
| Boot secrets | Machine-specific (TPM-bound) |
| Kubernetes join tokens | Shared secret |
| API keys for service tier | Shared secret |
| Certificate bundles | Shared secret |
| Database credentials | Shared secret |

---

#### Internal Architecture (v2.0.0)

Secret Vault v2.0.0 introduced base classes to eliminate code duplication between machine-specific and shared secrets. All encryption/decryption logic is now centralized and reusable.

**Base Classes**:

```python
# src/extensions/builtin/secret_vault/base_crypto.py
from abc import ABC, abstractmethod
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class BaseCrypto(ABC):
    """
    Base class for AES-256-GCM encryption operations.
    
    Subclasses implement key derivation strategy:
    - MachineSecretCrypto: Derive key from EK fingerprint (HKDF-SHA256)
    - SharedSecretCrypto: Use master key from environment
    """
    
    def __init__(self):
        self._key = self._derive_key()
        self.cipher = AESGCM(self._key)
    
    @abstractmethod
    def _derive_key(self) -> bytes:
        """Derive encryption key (32 bytes for AES-256)."""
        pass
    
    @abstractmethod
    def get_key_id(self) -> str:
        """Return key identifier for metadata tracking."""
        pass
    
    def encrypt(self, plaintext: str) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt plaintext secret value.
        
        Returns:
            Tuple of (ciphertext, nonce, tag)
        """
        nonce = os.urandom(12)  # 96 bits for GCM
        plaintext_bytes = plaintext.encode("utf-8")
        ciphertext_and_tag = self.cipher.encrypt(nonce, plaintext_bytes, None)
        
        # Split ciphertext and tag
        ciphertext = ciphertext_and_tag[:-16]
        tag = ciphertext_and_tag[-16:]
        
        return ciphertext, nonce, tag
    
    def decrypt(self, ciphertext: bytes, nonce: bytes, tag: bytes) -> str:
        """Decrypt encrypted secret value."""
        ciphertext_and_tag = ciphertext + tag
        plaintext_bytes = self.cipher.decrypt(nonce, ciphertext_and_tag, None)
        return plaintext_bytes.decode("utf-8")
```

```python
# src/extensions/builtin/secret_vault/base_models.py
from sqlmodel import Field
from datetime import datetime

class EncryptedSecretMixin:
    """
    Mixin for AES-256-GCM encrypted secret storage.
    
    Provides common fields for all secret types:
    - encrypted_value, nonce, tag (AES-GCM encryption)
    - created_at, created_by (audit trail)
    - last_accessed_at, access_count (access tracking)
    """
    
    encrypted_value: bytes = Field(description="AES-256-GCM encrypted secret value")
    nonce: bytes = Field(description="GCM nonce (96 bits)")
    tag: bytes = Field(description="GCM authentication tag (128 bits)")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(max_length=256)
    last_accessed_at: Optional[datetime] = Field(default=None)
    access_count: int = Field(default=0)
```

**Concrete Implementations**:

```python
# src/extensions/builtin/secret_vault/crypto.py
from .base_crypto import BaseCrypto
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

class MachineSecretCrypto(BaseCrypto):
    """Machine-specific secrets — TPM-bound via EK fingerprint."""
    
    def __init__(self, ek_fingerprint: str):
        self.ek_fingerprint = ek_fingerprint
        super().__init__()
    
    def _derive_key(self) -> bytes:
        """Derive AES-256 key from EK fingerprint using HKDF-SHA256."""
        ikm = bytes.fromhex(self.ek_fingerprint)
        salt = b"ITL.ControlPlane.Attestation.SecretVault.v1"
        
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"machine-secret-encryption"
        )
        return kdf.derive(ikm)
    
    def get_key_id(self) -> str:
        return f"ek-{self.ek_fingerprint[:16]}"
```

```python
# src/extensions/builtin/secret_vault/shared_crypto.py
from .base_crypto import BaseCrypto
import os
import hashlib

class SharedSecretCrypto(BaseCrypto):
    """Shared secrets — master key encryption (not TPM-bound)."""
    
    def __init__(self):
        self._key_source: str = ""
        super().__init__()
    
    def _derive_key(self) -> bytes:
        """Get or generate master encryption key."""
        # Priority: ITL_SHARED_SECRET_MASTER_KEY → ITL_SHARED_SECRET_PASSPHRASE → random
        if "ITL_SHARED_SECRET_MASTER_KEY" in os.environ:
            key = bytes.fromhex(os.environ["ITL_SHARED_SECRET_MASTER_KEY"])
            self._key_source = "env:ITL_SHARED_SECRET_MASTER_KEY"
            return key
        
        if "ITL_SHARED_SECRET_PASSPHRASE" in os.environ:
            passphrase = os.environ["ITL_SHARED_SECRET_PASSPHRASE"]
            key = hashlib.sha256(passphrase.encode("utf-8")).digest()
            self._key_source = "env:ITL_SHARED_SECRET_PASSPHRASE(sha256)"
            return key
        
        # Random key (dev only — not persisted!)
        key = os.urandom(32)
        self._key_source = "random-ephemeral"
        return key
    
    def get_key_id(self) -> str:
        return self._key_source

# Singleton instance
def get_shared_crypto() -> SharedSecretCrypto:
    """Get singleton SharedSecretCrypto instance."""
    global _shared_crypto_instance
    if _shared_crypto_instance is None:
        _shared_crypto_instance = SharedSecretCrypto()
    return _shared_crypto_instance
```

**Models**:

```python
# src/extensions/builtin/secret_vault/models.py
from .base_models import EncryptedSecretMixin

class SecretRow(EncryptedSecretMixin, SQLModel, table=True):
    """Machine-specific TPM-bound secret."""
    __tablename__ = "extension_secrets"
    
    secret_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    machine_id: uuid.UUID = Field(foreign_key="machines.machine_id")
    name: str = Field(max_length=128, index=True)
    
    # Encrypted storage fields inherited from EncryptedSecretMixin:
    # - encrypted_value, nonce, tag
    # - created_at, created_by
    # - last_accessed_at, access_count
```

```python
# src/extensions/builtin/secret_vault/shared_models.py
from .base_models import EncryptedSecretMixin

class SharedSecretRow(EncryptedSecretMixin, SQLModel, table=True):
    """Shared secret accessible by multiple machines."""
    __tablename__ = "extension_shared_secrets"
    
    shared_secret_id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=128, unique=True, index=True)
    
    # Encrypted storage fields inherited from EncryptedSecretMixin:
    # - encrypted_value, nonce, tag
    # - created_at, created_by
    # - last_accessed_at, access_count
    
    encryption_key_id: str = Field(max_length=64)
    last_rotated_at: Optional[datetime] = Field(default=None)
    description: Optional[str] = Field(default=None, max_length=512)
```

**Benefits**:

- **DRY Principle**: Encryption logic defined once in `BaseCrypto`
- **Consistency**: Both secret types use identical encryption fields
- **Mixin Pattern**: `EncryptedSecretMixin` eliminates field duplication
- **Pluggable Key Derivation**: Easy to add new crypto strategies (e.g., HSM-backed keys)
- **Type Safety**: ABC enforcement + SQLModel validation
- **Maintainability**: Changes to encryption on 1 place

---
### Webhooks

**Name**: `webhooks`  
**Version**: 1.0.0

HTTP webhook delivery for attestation events. Operators can register endpoints that receive event notifications with HMAC signatures.

**Features**:
- Subscribe to specific event types (machine.registered, machine.approved, etc.)
- HMAC-SHA256 signatures for webhook verification
- Delivery history and audit log
- Test endpoint for validation
- Automatic retry and failure tracking

**Event Types**:

| Event | Triggered When |
|-------|----------------|
| `machine.registered` | New machine completes registration |
| `machine.approved` | Operator approves a machine |
| `machine.revoked` | Operator revokes a machine certificate |
| `machine.locked` | Machine exceeds failed attestation threshold |
| `secret.created` | New secret is created |
| `secret.accessed` | Machine retrieves a secret |
| `webhook.test` | Manual test event triggered |

**API Endpoints**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/webhooks` | Operator | Create webhook |
| GET | `/api/v1/webhooks` | Operator | List all webhooks |
| GET | `/api/v1/webhooks/{id}` | Operator | Get webhook details |
| PUT | `/api/v1/webhooks/{id}` | Operator | Update webhook |
| DELETE | `/api/v1/webhooks/{id}` | Operator | Delete webhook |
| GET | `/api/v1/webhooks/{id}/deliveries` | Operator | Get delivery history |
| POST | `/api/v1/webhooks/{id}/test` | Operator | Send test event |

**CLI Commands**:

```bash
# Create webhook
attestation webhook add \
  --url https://example.com/hooks/attestation \
  --events machine.approved,machine.revoked \
  --secret my-signing-secret

# List webhooks
attestation webhook list

# Get webhook details
attestation webhook get <webhook-id>

# Update webhook
attestation webhook update <webhook-id> --enabled false

# Delete webhook
attestation webhook delete <webhook-id>

# View delivery history
attestation webhook deliveries <webhook-id> --limit 50

# Test webhook
attestation webhook test <webhook-id>
```

**Webhook Payload Structure**:

```json
{
  "event_type": "machine.approved",
  "timestamp": "2026-05-03T14:32:05.123456Z",
  "machine_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "data": {
    "ek_fingerprint": "sha256:abc123...",
    "hostname": "worker-01.prod.itl.local",
    "approved_by": "CN=admin,OU=IT,O=ITLusions"
  }
}
```

**HMAC Signature Verification** (Python example):

```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify webhook HMAC signature."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    # Extract hex digest from "sha256=..."
    received = signature.replace("sha256=", "")
    
    return hmac.compare_digest(expected, received)

# Usage in webhook handler
@app.post("/hooks/attestation")
async def handle_attestation_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    event = await request.json()
    # Process event...
```

**Database Schema**:

```sql
CREATE TABLE extension_webhooks (
    webhook_id UUID PRIMARY KEY,
    url VARCHAR(512) NOT NULL,
    events TEXT NOT NULL,              -- CSV: "machine.approved,machine.revoked"
    secret VARCHAR(256),               -- HMAC signing secret
    enabled BOOLEAN DEFAULT true,
    created_by VARCHAR(256) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    last_triggered_at TIMESTAMP,
    trigger_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0
);

CREATE TABLE extension_webhook_deliveries (
    delivery_id UUID PRIMARY KEY,
    webhook_id UUID REFERENCES extension_webhooks(webhook_id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL,             -- JSON payload sent
    response_status INTEGER,           -- HTTP status code
    response_body TEXT,                -- Response (truncated to 4KB)
    error TEXT,                        -- Error message if failed
    delivered_at TIMESTAMP NOT NULL,
    duration_ms INTEGER                -- Request duration
);
```

---

### Metrics

**Name**: `metrics`  
**Version**: 1.0.0

Prometheus-compatible metrics exporter for operational monitoring. Exposes counters and gauges at `/metrics` endpoint.

**Features**:
- Prometheus text format export
- Machine registration and attestation counters
- Secret vault operation tracking
- Webhook delivery statistics
- Audit log entry counts
- Machine status gauges

**API Endpoint**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | None | Prometheus metrics export |

**Metrics Exported**:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `attestation_machine_registrations_total` | Counter | `status` | Total registration requests |
| `attestation_machine_attestations_total` | Counter | `action`, `status` | Total attestation requests |
| `attestation_secret_operations_total` | Counter | `operation`, `status` | Secret vault operations |
| `attestation_webhook_deliveries_total` | Counter | `event_type`, `status` | Webhook deliveries |
| `attestation_audit_log_entries_total` | Counter | `action` | Audit log entries |
| `attestation_machines_by_status` | Gauge | `status` | Current machines per status |
| `attestation_active_sessions` | Gauge | — | Active attestation sessions |

**Prometheus Scrape Config**:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'attestation'
    static_configs:
      - targets: ['localhost:9000']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

**Example Queries**:

```promql
# Total machine registrations in last hour
increase(attestation_machine_registrations_total[1h])

# Webhook success rate
rate(attestation_webhook_deliveries_total{status="success"}[5m])
/ rate(attestation_webhook_deliveries_total[5m])

# Machines by status
attestation_machines_by_status

# Secret retrieval rate
rate(attestation_secret_operations_total{operation="get"}[5m])
```

**Grafana Dashboard**:

Key panels to include:
- Machine registration rate (graph)
- Attestation success/failure ratio (pie chart)
- Webhook delivery latency (histogram)
- Current machine status distribution (bar chart)
- Secret access rate (graph)
- Audit log activity (heatmap)

---

### Pulumi State Backend

**Name**: `pulumi_state`  
**Version**: 1.0.0

Turns the Attestation Service into a self-hosted [Pulumi HTTP state backend](https://www.pulumi.com/docs/concepts/state/). Teams run `pulumi login https://attest.itlusions.com` and the service handles stack state, secrets encryption, and server-side deployments — no Pulumi Cloud subscription required.

**Features**:
- Full Pulumi HTTP state protocol implementation
- Per-stack AES-256-GCM secrets encryption (`--secrets-provider https://attest.itlusions.com`)
- Server-side `pulumi up/preview/refresh/destroy` triggered via REST
- Stack history and checkpoint management
- State stored in the Attestation PostgreSQL / SQLite database

**Environment variables**:

| Variable | Default | Description |
|---|---|---|
| `ITL_PULUMI_TOKEN` | *(required)* | Bearer token for CLI authentication |
| `ITL_PULUMI_ORG` | `itlusions` | Org name returned in `/api/user` |
| `ITL_PULUMI_ENABLED` | `true` | Set `false` to disable |

**Quick start**:

```bash
export PULUMI_ACCESS_TOKEN="<ITL_PULUMI_TOKEN>"
pulumi login https://attest.itlusions.com

# Stack with server-side secret encryption
pulumi stack init myorg/myproject/production \
  --secrets-provider https://attest.itlusions.com

pulumi config set --secret db_password "s3cr3t!"
pulumi up
```

**Secrets provider API** (`/encrypt` / `/decrypt`):

| Method | Path | Description |
|---|---|---|
| POST | `/api/stacks/{org}/{project}/{stack}/encrypt` | Encrypt a value (CLI sends base64-encoded plaintext) |
| POST | `/api/stacks/{org}/{project}/{stack}/decrypt` | Decrypt a value |

A random 256-bit AES key is generated for each stack on the first encrypt call and stored in `extension_pulumi_state_stacks.secrets_key`. Ciphertext format: `v1:<base64(12-byte nonce + ciphertext + 16-byte GCM tag)>`.

**Server-side deployments API**:

| Method | Path | Description |
|---|---|---|
| POST | `/api/stacks/{org}/{project}/{stack}/deployments` | Queue a deployment (returns 202) |
| GET | `/api/stacks/{org}/{project}/{stack}/deployments` | List all deployments |
| GET | `/api/stacks/{org}/{project}/{stack}/deployments/{id}` | Get deployment status + logs |
| DELETE | `/api/stacks/{org}/{project}/{stack}/deployments/{id}/cancel` | Cancel a queued/running deployment |

**Trigger a deployment from CI/CD**:

```bash
curl -X POST https://attest.itlusions.com/api/stacks/myorg/myproject/production/deployments \
  -H "Authorization: token $ITL_PULUMI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update",
    "source": {
      "repoURL": "https://github.com/myorg/infra",
      "branch": "main",
      "repoDir": "environments/production"
    }
  }'
```

**Database tables**:

| Table | Description |
|---|---|
| `extension_pulumi_state_stacks` | Stack registry (org/project/stack, checkpoint, secrets key) |
| `extension_pulumi_state_updates` | Update lifecycle with short-lived tokens |
| `extension_pulumi_state_deployments` | Server-side deployment records with logs |

For full details, see [Pulumi Integration](pulumi-provider.md).

---
## Extension Discovery

1. **Built-in extensions** from `src/extensions/builtin/`
2. **External extensions** via `entry_points(group="attestation_extensions")`

To see loaded extensions:

```bash
curl http://localhost:9000/api/v1/extensions
```

Response:

```json
{
  "extensions": [
    {
      "name": "secret_vault",
      "version": "2.0.0",
      "description": "TPM-bound secret storage for attested machines + shared secrets"
    },
    {
      "name": "webhooks",
      "version": "1.0.0",
      "description": "HTTP webhook delivery for attestation events"
    },
    {
      "name": "metrics",
      "version": "1.0.0",
      "description": "Prometheus metrics exporter for operational monitoring"
    },
    {
      "name": "pulumi_state",
      "version": "1.0.0",
      "description": "Pulumi HTTP state backend — store Pulumi stack state in the Attestation DB"
    }
  ],
  "total": 4
}
```

---

## Developing Extensions

### 1. Extension Structure

Create a new package under `src/extensions/builtin/`:

```
src/extensions/builtin/my_extension/
├── __init__.py
├── extension.py      # MyExtension class
├── models.py         # SQLModel classes
├── schemas.py        # Pydantic schemas
├── repository.py     # Data access layer
└── routes.py         # Optional: route logic
```

### 2. Implement Extension Class

```python
# src/extensions/builtin/my_extension/extension.py
from extensions.base import AttestationExtension
from fastapi import APIRouter
from .models import MyRow

class MyExtension(AttestationExtension):
    @property
    def name(self) -> str:
        return "my_extension"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "My custom extension"
    
    def get_router(self) -> APIRouter | None:
        router = APIRouter(prefix="/api/v1/my", tags=["my"])
        
        @router.get("/hello")
        async def hello():
            return {"message": "Hello from my extension"}
        
        return router
    
    def get_models(self) -> list[type]:
        return [MyRow]
    
    def on_startup(self) -> None:
        print(f"[MyExtension] Started (v{self.version})")
```

### 3. Export Extension

```python
# src/extensions/builtin/my_extension/__init__.py
from .extension import MyExtension

__all__ = ["MyExtension"]
```

The extension will be auto-discovered on next service restart.

---

## External Extensions

External extensions can be published to PyPI and installed separately.

### 1. Package Structure

```
itl-attestation-ext-example/
├── pyproject.toml
└── src/
    └── itl_attestation_ext_example/
        ├── __init__.py
        └── extension.py
```

### 2. Register via Entry Points

```toml
# pyproject.toml
[project]
name = "itl-attestation-ext-example"
version = "1.0.0"

[project.entry-points."attestation_extensions"]
example = "itl_attestation_ext_example.extension:ExampleExtension"
```

### 3. Install and Use

```bash
pip install itl-attestation-ext-example
# Restart attestation service — extension auto-loads
```

---

## Extension Guidelines

### Naming Conventions

- **Extension name**: `snake_case`, unique across all extensions
- **Table prefix**: `extension_<name>_*` (e.g., `extension_secrets`)
- **API prefix**: `/api/v1/<name>` (e.g., `/api/v1/secrets`)
- **CLI group**: `attestation <name>` (e.g., `attestation secret`)

### Database Models

All extension models must:
- Use `extension_<name>_` table name prefix
- Include timestamps (`created_at`, `updated_at`)
- Use UUIDs for primary keys
- Follow SQLModel patterns from SDK

### Security

- Extensions run in the same process (no sandbox)
- Extensions have full access to database and SDK
- Extensions must implement their own RBAC checks
- Never trust user input — validate with Pydantic schemas
- Use constant-time comparison for sensitive data

### Dependencies

- Built-in extensions: Can depend on SDK and attestation service dependencies
- External extensions: Must declare all dependencies in `pyproject.toml`

### Error Handling

- Raise `HTTPException` for API errors
- Log errors with `logger.error()` (include extension name)
- Don't crash the service — catch and log exceptions in hooks

---

## Migration Management

Extension models are included in Alembic migrations automatically via `get_models()`.

To generate a migration after adding extension models:

```bash
cd src/attestation
alembic revision --autogenerate -m "Add secret_vault extension"
alembic upgrade head
```

---

## Testing Extensions

### Unit Tests

```python
# tests/extensions/test_secret_vault.py
import pytest
from extensions.builtin.secret_vault.crypto import SecretCrypto

def test_encrypt_decrypt():
    plaintext = "my-secret-value"
    ek_fp = "a" * 64
    
    encrypted, nonce, tag = SecretCrypto.encrypt(plaintext, ek_fp)
    decrypted = SecretCrypto.decrypt(encrypted, nonce, tag, ek_fp)
    
    assert decrypted == plaintext
```

### Integration Tests

```python
# tests/extensions/test_secret_vault_api.py
from fastapi.testclient import TestClient
from attestation.core.app import create_app

def test_create_secret():
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/secrets/machines/test-id/secrets",
        json={"name": "test", "value": "secret123"},
        headers={"Authorization": "Bearer <token>"}
    )
    assert response.status_code == 201
```

---

## Troubleshooting

### Extension not loading

Check logs for discovery errors:

```
[Extension] Failed to load extensions.builtin.my_extension: <error>
```

Common causes:
- Missing `extension.py` file
- Extension class doesn't inherit `AttestationExtension`
- Import errors (missing dependencies)

### Extension routes not registered

Check logs:

```
INFO:     Registered extension routes: secret_vault
```

If missing:
- `get_router()` returns `None`
- Router has no routes
- Extension loaded after `create_app()` called

### Database errors

Extension models must be discoverable:

```python
def get_models(self) -> list[type]:
    return [MyRow]  # Must return actual class, not string
```

---

## Roadmap

Planned future extensions:

- **Audit Export** — Export audit logs to SIEM/S3
- **Compliance Reporting** — Generate compliance reports (NIST, CIS)
- **Backup/Restore** — Automated database backup to object storage
- **Metrics** — Prometheus metrics for monitoring
- **Webhooks** — Event-driven notifications to external systems

---

## Support

- **Issues**: [GitHub Issues](https://github.com/ITLusions/ITL.ControlPlane.Attestation/issues)
- **Documentation**: [docs/](.)
- **Contact**: info@itlusions.com

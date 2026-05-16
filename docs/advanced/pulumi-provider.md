---
layout: default
title: Pulumi Integration
category: Advanced
description: Pulumi HTTP state backend, secrets provider, server-side deployments, and dynamic provider
---

# Pulumi Integration

The Attestation Service offers two complementary Pulumi integrations:

| Integration | Direction | Purpose |
|---|---|---|
| **HTTP State Backend** (`pulumi_state` extension) | Inbound | The Attestation Service *is* the Pulumi backend — stores stack state, encrypts secrets, runs deployments |
| **Dynamic Provider** (`pulumi-itl-attestation`) | Outbound | Pulumi manages machines as resources via the Attestation REST API |

---

## Part 1 — HTTP State Backend

The `pulumi_state` builtin extension turns the Attestation Service into a self-hosted [Pulumi HTTP state backend](https://www.pulumi.com/docs/concepts/state/). Stack state is stored in the same PostgreSQL / SQLite database as the rest of the service — no Pulumi Cloud subscription required.

### Quick start

```bash
# Set the operator token (issued by the service)
export PULUMI_ACCESS_TOKEN="<ITL_PULUMI_TOKEN>"

# Login — this is the only URL teams need
pulumi login https://attest.itlusions.com

# Create a stack — use the service as secrets provider (no passphrase needed)
pulumi stack init myorg/myproject/production \
  --secrets-provider https://attest.itlusions.com

# Normal Pulumi workflow
pulumi up
pulumi refresh
pulumi destroy
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `ITL_PULUMI_TOKEN` | *(required)* | Static bearer token for Pulumi CLI authentication |
| `ITL_PULUMI_ORG` | `itlusions` | Org name returned in `/api/user` |
| `ITL_PULUMI_ENABLED` | `true` | Set `false` to disable the extension entirely |

### Authentication

All state backend endpoints use `Authorization: token <value>`. Two token types are accepted:

- **Operator token** (`ITL_PULUMI_TOKEN`) — used for all user-level calls
- **Update token** — short-lived UUID issued per `pulumi up` run, used internally for checkpoint/events during that run

### Implemented endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/user` | Authenticated user identity |
| GET | `/api/capabilities` | Backend capabilities |
| GET | `/api/user/stacks` | List all stacks |
| HEAD | `/api/stacks/{org}/{project}` | Project existence check |
| POST | `/api/stacks/{org}/{project}` | Create stack |
| GET | `/api/stacks/{org}/{project}/{stack}` | Get stack metadata |
| DELETE | `/api/stacks/{org}/{project}/{stack}` | Delete stack |
| PATCH | `/api/stacks/{org}/{project}/{stack}/tags` | Update stack tags |
| GET | `/api/stacks/{org}/{project}/{stack}/export` | Export checkpoint |
| POST | `/api/stacks/{org}/{project}/{stack}/import` | Import checkpoint |
| GET | `/api/stacks/{org}/{project}/{stack}/updates` | Update history |
| POST | `/api/stacks/{org}/{project}/{stack}/update` | Start update |
| POST | `/api/stacks/{org}/{project}/{stack}/preview` | Start preview |
| POST | `/api/stacks/{org}/{project}/{stack}/refresh` | Start refresh |
| POST | `/api/stacks/{org}/{project}/{stack}/destroy` | Start destroy |
| POST | `/api/stacks/{org}/{project}/{stack}/updates/{id}` | Start update lifecycle |
| PATCH | `/api/stacks/{org}/{project}/{stack}/updates/{id}/checkpoint` | Patch checkpoint |
| POST | `/api/stacks/{org}/{project}/{stack}/updates/{id}/events/batch` | Batch engine events |
| POST | `/api/stacks/{org}/{project}/{stack}/updates/{id}/renew_lease` | Renew update lease |
| POST | `/api/stacks/{org}/{project}/{stack}/updates/{id}/complete` | Complete update |
| POST | `/api/stacks/{org}/{project}/{stack}/encrypt` | Encrypt a secret value |
| POST | `/api/stacks/{org}/{project}/{stack}/decrypt` | Decrypt a secret value |
| POST | `/api/stacks/{org}/{project}/{stack}/deployments` | Queue a server-side deployment |
| GET | `/api/stacks/{org}/{project}/{stack}/deployments` | List deployments |
| GET | `/api/stacks/{org}/{project}/{stack}/deployments/{id}` | Get deployment status |
| DELETE | `/api/stacks/{org}/{project}/{stack}/deployments/{id}/cancel` | Cancel a deployment |

---

### Secrets provider

By default Pulumi encrypts secrets with a passphrase that every team member must know. Using the Attestation Service as a secrets provider replaces this with server-side AES-256-GCM encryption.

```bash
# First stack init — Attestation Service generates a random 256-bit key and stores it
pulumi stack init myorg/myproject/production \
  --secrets-provider https://attest.itlusions.com

# Set an encrypted config value — the CLI calls /encrypt
pulumi config set --secret database_password "s3cr3t!"

# The ciphertext stored in Pulumi.production.yaml looks like:
#   v1:ABcd...==
# It is only readable by calling /decrypt with the correct operator token.
```

**How it works**

1. On the first `/encrypt` call for a stack, a random 32-byte AES-256-GCM key is generated and stored (base64) in `PulumiStackRow.secrets_key`.
2. The CLI sends base64-encoded plaintext; the server returns `v1:<base64(nonce + ciphertext + tag)>`.
3. The ciphertext is stored in the stack's `Pulumi.<stack>.yaml` — it is opaque to anyone without a valid operator token.
4. `/decrypt` reverses the process.

**Benefits over passphrase**

| Approach | Key distribution | Rotation | Audit trail |
|---|---|---|---|
| `--secrets-provider passphrase` | Manual, out-of-band | Re-encrypt all secrets | None |
| `--secrets-provider https://attest…` | Zero — token auth only | Rotate `ITL_PULUMI_TOKEN` | Keycloak / operator logs |

---

### Server-side deployments

The `/deployments` API lets a CI/CD pipeline or operator trigger `pulumi up` on the server — no local Pulumi installation required.

```bash
# Queue an update from a git repository
curl -X POST https://attest.itlusions.com/api/stacks/myorg/myproject/production/deployments \
  -H "Authorization: token $ITL_PULUMI_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update",
    "source": {
      "repoURL": "https://github.com/myorg/infra",
      "branch": "main",
      "repoDir": "environments/production"
    },
    "environmentVariables": {
      "TF_VAR_region": "westeurope"
    }
  }'

# Returns 202 Accepted immediately; poll for status
curl https://attest.itlusions.com/api/stacks/myorg/myproject/production/deployments/<id> \
  -H "Authorization: token $ITL_PULUMI_TOKEN"
```

**Deployment lifecycle**

```
queued  →  running  →  succeeded
                    →  failed
                    →  cancelled
```

The server:
1. Clones the git repository (`git clone --depth 1`) into a temporary directory.
2. Runs `pulumi <operation> --non-interactive --yes` with `PULUMI_BACKEND_URL` set to the service itself.
3. Captures stdout + stderr as the deployment log.
4. Persists final status, exit code, and log in `extension_pulumi_state_deployments`.

**Supported operations**: `update`, `preview`, `refresh`, `destroy`

> **Requirement**: The `pulumi` CLI binary must be available in the container's `PATH`. Add it to the Docker image or install it at runtime.

---

### Database tables

| Table | Description |
|---|---|
| `extension_pulumi_state_stacks` | Stack registry — org / project / stack / tags / checkpoint / secrets key |
| `extension_pulumi_state_updates` | Update lifecycle records with short-lived tokens |
| `extension_pulumi_state_deployments` | Server-side deployment records with logs and status |

---

### Operator walkthrough

This section shows a complete workflow from a fresh environment to a running stack, using the Attestation Service as the state backend, secrets provider, and deployment runner.

#### Prerequisites

| Tool | Minimum version |
|---|---|
| `pulumi` CLI | 3.0.0 |
| `python` | 3.12 |
| Attestation Service | running at `https://attest.itlusions.com` |
| `ITL_PULUMI_TOKEN` | issued by the service operator |

#### Step 1 — Configure credentials

```bash
export PULUMI_ACCESS_TOKEN="eyJ..."   # ITL_PULUMI_TOKEN value

# Verify the token is accepted
curl -s https://attest.itlusions.com/api/user \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" | python3 -m json.tool
# {"name":"operator","githubLogin":"operator","avatarUrl":""}
```

#### Step 2 — Log in to the backend

```bash
pulumi login https://attest.itlusions.com
# Logged into https://attest.itlusions.com as operator
```

> The login URL is the only configuration teams need. No Pulumi Cloud account, no S3 bucket, no environment files.

#### Step 3 — Create a project and stack

```bash
mkdir ~/infra/myproject && cd ~/infra/myproject
pulumi new python --name myproject --description "ITL infra stack" --yes

# Init the stack — use the service as the secrets provider
pulumi stack init itlusions/myproject/production \
  --secrets-provider https://attest.itlusions.com
# Created stack 'production'
# Stack 'production' is using the service's secrets provider
```

The stack is now registered in `extension_pulumi_state_stacks`.

#### Step 4 — Store an encrypted config value

```bash
pulumi config set aws_region eu-west-1
pulumi config set --secret db_password "correct-horse-battery"
```

Internally the CLI calls `POST /api/stacks/itlusions/myproject/production/encrypt`.  
`Pulumi.production.yaml` receives a `v1:…` ciphertext — no passphrase is ever set or distributed.

```yaml
# Pulumi.production.yaml (safe to commit)
config:
  myproject:aws_region: eu-west-1
  myproject:db_password:
    secure: v1:AAEC...kZHI=
```

#### Step 5 — Run pulumi up locally

```bash
pulumi up
```

The CLI communicates with the backend throughout the update lifecycle:

```
POST  /api/stacks/itlusions/myproject/production/update          ← start
PATCH /api/stacks/itlusions/myproject/production/updates/<id>/checkpoint  ← progress
POST  /api/stacks/itlusions/myproject/production/updates/<id>/events/batch
POST  /api/stacks/itlusions/myproject/production/updates/<id>/complete    ← done
```

State is safely stored in the Attestation DB. Any team member with a valid token can run the next `pulumi up` from any machine.

#### Step 6 — Inspect current state

```bash
# Show stack outputs
pulumi stack output

# Export checkpoint JSON (useful for debugging)
curl -s "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/export" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" | python3 -m json.tool | head -40

# List all stacks visible to the operator
curl -s "https://attest.itlusions.com/api/user/stacks" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" | python3 -m json.tool
```

#### Step 7 — Trigger a server-side deployment from CI/CD

When no local `pulumi` installation is available (e.g. in a minimal CI runner), queue a deployment via the REST API:

```bash
DEPLOYMENT=$(curl -s -X POST \
  "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/deployments" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "update",
    "source": {
      "repoURL": "https://github.com/itlusions/infra",
      "branch": "main",
      "repoDir": "environments/production"
    },
    "environmentVariables": {
      "PULUMI_CONFIG_PASSPHRASE": ""
    }
  }')

DEPLOYMENT_ID=$(echo "$DEPLOYMENT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Deployment queued: $DEPLOYMENT_ID"

# Poll until done
while true; do
  STATUS=$(curl -s \
    "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/deployments/$DEPLOYMENT_ID" \
    -H "Authorization: token $PULUMI_ACCESS_TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  echo "Status: $STATUS"
  [[ "$STATUS" == "succeeded" || "$STATUS" == "failed" || "$STATUS" == "cancelled" ]] && break
  sleep 5
done
```

#### Step 8 — Retrieve deployment logs

```bash
curl -s \
  "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/deployments/$DEPLOYMENT_ID" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" | python3 -m json.tool
```

Example response:

```json
{
  "id": "3f2a1b...",
  "status": "succeeded",
  "operation": "update",
  "startedAt": "2026-05-16T09:14:02Z",
  "completedAt": "2026-05-16T09:14:47Z"
}
```

Full stdout + stderr are stored in `extension_pulumi_state_deployments.logs` and accessible via the deployment record.

#### Step 9 — Cancel an in-progress deployment

```bash
curl -s -X DELETE \
  "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/deployments/$DEPLOYMENT_ID/cancel" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN"
# HTTP 204 No Content
```

Cancellation sets the status to `cancelled` if the deployment has not yet entered a terminal state.

#### Step 10 — Tear down the stack

```bash
# Locally
pulumi destroy --yes

# Or server-side
curl -X POST \
  "https://attest.itlusions.com/api/stacks/itlusions/myproject/production/deployments" \
  -H "Authorization: token $PULUMI_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation": "destroy"}'
```

---

## Part 2 — Dynamic Provider (`pulumi-itl-attestation`)

---

## Installation

```bash
pip install pulumi>=3.0.0 pulumi-random>=4.16.0
# Install the provider from the monorepo
pip install -e ./src/pulumi_provider
```

Or from the published package:

```bash
pip install pulumi-itl-attestation
```

---

## Resources

### `RegisteredMachine`

Calls `POST /api/v1/register` on create and `POST /api/v1/machines/{id}/revoke` on destroy.

| Input | Type | Description |
|---|---|---|
| `endpoint` | `str` | Base URL of the Attestation Service |
| `token` | `str` [secret] | Operator bearer token |
| `ek_fingerprint` | `str` | SHA-384 hex fingerprint of the TPM EK |
| `ek_cert_pem` | `str` [secret] | PEM-encoded TPM EK certificate |
| `hw_serial` | `str` | Hardware serial number |
| `hw_product` | `str` | Product name |
| `hw_mac` | `str` | Primary NIC MAC address |
| `desired_role` | `NodeRole \| str` | `controlplane`, `worker-infra`, or `worker-app` |

| Output | Type | Description |
|---|---|---|
| `machine_id` | `str` | UUID assigned by the service |
| `status` | `MachineStatus` | Current machine state |
| `config_url` | `str` | URL to fetch the Talos MachineConfig |
| `config_token` | `str` [secret] | One-time config token (256-bit) |
| `iso_url` | `str` | Signed Talos ISO URL from image factory |

---

### `MachineApproval`

Calls `POST /api/v1/machines/{id}/approve` on create. Automatically depends on the upstream `RegisteredMachine`.

| Input | Type | Description |
|---|---|---|
| `machine_id` | `str` | Output from `RegisteredMachine.machine_id` |
| `role` | `NodeRole \| str` | Role to assign |
| `hostname` | `str` | FQDN to assign to the node |
| `assigned_ip` | `str` | Static IP (optional) |
| `keep_on_delete` | `bool` | If `True`, skip revocation on `pulumi destroy` |

---

## Minimal example

```python
import pulumi
from pulumi_provider import RegisteredMachine, MachineApproval, NodeRole

cfg   = pulumi.Config("attestation")
token = cfg.require_secret("token")

machine = RegisteredMachine(
    "cp-node-01",
    endpoint="http://localhost:8080",
    token=token,
    ek_fingerprint="<sha384-hex>",
    ek_cert_pem=open("ek.pem").read(),
    hw_serial="SN-CP-001",
    desired_role=NodeRole.controlplane,
)

approval = MachineApproval(
    "cp-node-01-approval",
    endpoint="http://localhost:8080",
    token=token,
    machine_id=machine.machine_id,
    role=NodeRole.controlplane,
    hostname="cp-node-01.cluster.local",
    assigned_ip="10.0.1.10",
    opts=pulumi.ResourceOptions(depends_on=[machine]),
)

pulumi.export("machine_id",   machine.machine_id)
pulumi.export("config_url",   machine.config_url)
pulumi.export("config_token", machine.config_token)  # [secret]
```

---

## Secrets

Use `pulumi_random.RandomPassword` to generate per-machine enrollment tokens managed by Pulumi state, then compose them with the service-issued `config_token` into an encrypted bootstrap bundle:

```python
import json
import pulumi_random as random
from pulumi import Output

enrollment_token = random.RandomPassword(
    "cp-enrollment-token",
    length=44,
    special=False,
    opts=pulumi.ResourceOptions(additional_secret_outputs=["result"]),
)

bootstrap_bundle = Output.secret(
    Output.all(
        machine_id=machine.machine_id,
        config_token=machine.config_token,
        config_url=machine.config_url,
        enrollment_token=enrollment_token.result,
    ).apply(lambda v: json.dumps(v, indent=2))
)

pulumi.export("bootstrap_bundle", bootstrap_bundle)  # [secret]
```

The bundle can then be pushed to Azure Key Vault, HashiCorp Vault, a Kubernetes Secret, or embedded into a UEFI variable — all within the same Pulumi stack.

---

## Drift detection

On `pulumi refresh`, the provider calls `GET /api/v1/machines/{id}` and compares the live status with what is stored in state. If the machine was revoked or locked externally, Pulumi marks it as **drifted** and proposes re-creation on the next `pulumi up`.

```bash
pulumi refresh    # reads live state from the API
pulumi up         # reconciles — re-registers revoked machines
```

---

## Full demo

A complete runnable demo with two machines (one controlplane, one worker) is available at [`examples/pulumi-demo/`](https://github.com/ITlusions/ITL.ControlPlane.Attestation/tree/main/examples/pulumi-demo).

```bash
cd examples/pulumi-demo
pulumi stack init dev
pulumi config set attestation:endpoint http://localhost:8080
pulumi config set --secret attestation:token <ITL_ADMIN_TOKEN>
pulumi up
```

---

## Package layout

```
src/pulumi_provider/
  __init__.py     re-exports all public symbols
  _client.py      typed HTTP wrapper (AttestationClient)
  provider.py     Pulumi dynamic.ResourceProvider implementations
  resources.py    RegisteredMachine, MachineApproval
  pyproject.toml  package: pulumi-itl-attestation v0.1.0
```

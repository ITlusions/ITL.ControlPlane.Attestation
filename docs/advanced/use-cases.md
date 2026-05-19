---
layout: default
title: Use Cases
category: Advanced
description: Real-world integration patterns for the attestation service — operational workflows and event-driven integrations
---

# Use Cases

This page covers two categories of use cases:

- **Operational workflows** — day-to-day scenarios using the REST API and CLI, aimed at operators and platform engineers.
- **Event-driven integrations** — patterns that hook into node lifecycle events via the extension API, aimed at developers building automated pipelines.

---

## Operational workflows

### Zero-touch provisioning (ZTP)

The standard path from bare-metal delivery to a running Talos cluster node without any manual SSH or console access.

**Prerequisites**: DHCP and HTTPS reachable from the machine's management network.

**Flow**:

1. Boot the machine from a USB stick loaded with the ITL USB Registration Agent (Alpine Linux).
2. The agent reads the TPM EK certificate from `/sys/kernel/security/tpm0/binary_bios_measurements` and posts it to `POST /api/v1/register`.
3. An operator (or approval automation) calls `POST /api/v1/machines/{id}/approve` — the service generates a Talos Image Factory schematic and a one-time config token.
4. The machine reboots, boots the returned Talos ISO URL, and on first boot calls `POST /api/v1/attest` followed by `GET /api/v1/config/{token}` to retrieve its full Talos machine config.
5. The node joins the cluster; its status transitions to `attested`.

```bash
# Register (runs automatically via USB agent — shown here for reference)
curl -X POST https://attest.itlusions.com/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"ek_cert_pem": "<base64>", "hw_uuid": "...", "hw_serial": "SVC1284AB"}'

# Approve (operator)
attestation machine approve <machine-id> \
  --hostname cp-node-04 \
  --role controlplane \
  --reason "Rack 3 expansion"
```

---

### Hardware replacement

When a node fails and the physical machine must be replaced (different EK, same role and hostname).

**Flow**:

1. Revoke the old machine record: `attestation machine revoke <old-id> --reason "Hardware failure"`
2. Register the replacement machine via USB agent — it gets a new `machine_id` and a new EK fingerprint.
3. Approve with the same hostname and role as the old node.
4. The new node attests and downloads its config; the cluster re-admits it.

The audit log records both the revocation and the new registration, creating a complete chain of custody for compliance purposes.

---

### Dual-control approval

For production environments where a single operator approving a node is not acceptable (SOC 2, NIS2, ISO 27001).

**Flow**:

1. Operator A calls `POST /api/v1/machines/{id}/approve` — the service detects that no prior vote exists and records a `approve_vote` in the audit log. Status remains `pending_approval`.
2. Operator B (different Keycloak identity) calls the same endpoint — the service finds the pending vote from a different operator, records `approve` in the audit log, and advances the machine to `registered`.

Neither operator can self-approve; the second `approve` from the same identity is rejected with `409 Conflict`.

---

### Offline / airgap deployment

For sites with no outbound internet access (classified environments, industrial OT networks).

**Flow**:

1. On a connected machine, generate an offline bundle for the target node:

```bash
attestation machine bundle <machine-id> --output ./bundle-cp-node-04.tar.gz
```

2. Transfer the bundle (USB, CD, secure courier) to the airgap site.
3. Import on the local attestation instance:

```bash
attestation machine import ./bundle-cp-node-04.tar.gz
```

4. The bundle contains the pre-generated Talos ISO URL, signed machine config, and enrollment certificate — the node boots and configures itself without calling out.

---

### Break-glass access

When Keycloak (the OIDC provider) is unavailable but an operator must perform an emergency action.

The attestation service supports a `BREAK_GLASS_TOKEN` environment variable. When set, requests carrying that token in the `X-Break-Glass` header bypass OIDC validation. Every action taken with break-glass credentials is logged with `operator_cn = "BREAK_GLASS"` in the tamper-evident audit chain, making post-incident review straightforward.

```bash
curl -X POST https://attest.itlusions.com/api/v1/machines/<id>/lock \
  -H "X-Break-Glass: $BREAK_GLASS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Emergency isolation — suspected compromise"}'
```

> Never store the break-glass token in source control. Rotate it after every use.

---

### Compliance reporting and audit export

Extract a signed, tamper-evident audit report for a specific machine, suitable for attaching to a change record or incident ticket.

```bash
# Verify the full audit chain (detects any tampering)
attestation audit verify

# Export all events for one machine as a signed PDF
curl -X GET "https://attest.itlusions.com/api/v1/machines/<id>/audit-report" \
  -H "Authorization: Bearer $TOKEN" \
  --output machine-audit-$(date +%Y%m%d).pdf

# Export the raw audit log as JSON for SIEM ingestion
attestation audit list --machine <id> --output json > audit.json
```

The `entry_hash` / `prev_hash` chain ensures that any modification to a historical record is detectable. Use `audit verify` as a scheduled job to alert on tampering.

---

### Enrolling ephemeral CI/CD build agents

Register short-lived build runners (e.g., GitHub Actions self-hosted, GitLab Runner, Tekton) so only attested machines can access signing keys and container registries.

**Flow**:

1. The runner image includes `itl-tpm-register`. On startup it self-registers: `POST /api/v1/self-register`.
2. Auto-approval policy (extension or external webhook) approves runners with `hw_product = "Virtual Machine"` and `role = worker-app` immediately.
3. The runner polls `GET /api/v1/config/{token}` to receive a short-lived client certificate from the enrollment CA.
4. The certificate is used for mTLS to internal package registries and signing services.
5. On shutdown, the runner calls `POST /api/v1/machines/{id}/revoke` to invalidate the certificate immediately.

---

### Certificate-based machine authentication (mTLS)

Nodes can activate an Attestation Key (AK) and receive a client certificate from the enrollment CA, enabling mTLS without distributing long-lived secrets.

```bash
# 1. Generate AK on the node
tpm2_createak ...

# 2. Register AK with the service
curl -X POST https://attest.itlusions.com/api/v1/machines/<id>/ak-activate \
  -H "Content-Type: application/json" \
  -d '{"ak_pub_pem": "<SubjectPublicKeyInfo PEM>"}'

# 3. Request enrollment certificate
curl -X POST https://attest.itlusions.com/api/v1/machines/<id>/enroll \
  -H "Content-Type: application/json" \
  -d '{"csr_pem": "<PKCS#10 CSR>"}'
```

The returned certificate has the machine's EK fingerprint in the SAN, making it trivially verifiable by any relying party that trusts the enrollment CA.

---

## Event-driven integrations

The patterns below use the node event hooks to react to lifecycle transitions. Each section lists the events consumed, the decorator API, and a working code sketch.

---

## SPIFFE / SPIRE — Automatic workload identity

**Scenario**: Every attested node should receive a SPIFFE identity issued by a SPIRE server. When the node is revoked the identity must be removed immediately.

**Events used**: `node.provisioned` (`@on_provisioning`), `node.decommissioned` (`@on_decommissioned`)

```python
import subprocess
from attestation.hooks import on_provisioning, on_decommissioned
from attestation.hooks import ProvisioningContext, DecommissionedContext

SPIRE_SERVER = "spire-server"
TRUST_DOMAIN  = "itlusions.com"


@on_provisioning
async def issue_spiffe_identity(ctx: ProvisioningContext) -> None:
    spiffe_id = f"spiffe://{TRUST_DOMAIN}/nodes/{ctx.ek_fingerprint[:16]}"
    subprocess.run([
        SPIRE_SERVER, "entry", "create",
        "-spiffeID", spiffe_id,
        "-parentID", f"spiffe://{TRUST_DOMAIN}/spire/agent/tpm/{ctx.ek_fingerprint[:16]}",
        "-selector", f"tpm:ek_fingerprint:{ctx.ek_fingerprint}",
    ], check=True)


@on_decommissioned
async def revoke_spiffe_identity(ctx: DecommissionedContext) -> None:
    spiffe_id = f"spiffe://{TRUST_DOMAIN}/nodes/{ctx.ek_fingerprint[:16]}"
    subprocess.run([
        SPIRE_SERVER, "entry", "delete", "-spiffeID", spiffe_id,
    ], check=True)
```

---

## CMDB / Asset inventory sync

**Scenario**: Keep an external CMDB in sync with the hardware inventory. Register the node when it first comes online; mark it inactive on decommission.

**Events used**: `node.online` (`@on_online`), `node.decommissioned` (`@on_decommissioned`)

```python
import httpx
from attestation.hooks import on_online, on_decommissioned
from attestation.hooks import OnlineContext, DecommissionedContext

CMDB_BASE = "https://cmdb.example.com/api"


@on_online
async def register_in_cmdb(ctx: OnlineContext) -> None:
    async with httpx.AsyncClient() as client:
        await client.put(
            f"{CMDB_BASE}/nodes/{ctx.ek_fingerprint}",
            json={
                "hostname": ctx.hostname,
                "role": ctx.role,
                "status": "active",
                "first_seen": ctx.first_seen_at.isoformat(),
                "ek_fingerprint": ctx.ek_fingerprint,
            },
            timeout=5.0,
        )


@on_decommissioned
async def deactivate_in_cmdb(ctx: DecommissionedContext) -> None:
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{CMDB_BASE}/nodes/{ctx.ek_fingerprint}",
            json={"status": "decommissioned", "reason": ctx.reason},
            timeout=5.0,
        )
```

---

## Slack / Teams alert on pending approval

**Scenario**: Notify the ops channel when a node is waiting for operator approval, so the team can act quickly without polling the dashboard.

**Events used**: `node.registered` (`@on_registered`)

```python
import httpx
import os
from attestation.hooks import on_registered
from attestation.hooks import RegisteredContext

WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]


@on_registered
async def notify_ops_channel(ctx: RegisteredContext) -> None:
    hw = ctx.hardware
    text = (
        f":new: *New node pending approval*\n"
        f"EK: `{ctx.ek_fingerprint[:24]}…`\n"
        f"MAC: `{ctx.mac_address}` | TPM: {'yes' if ctx.tpm_available else 'no'}\n"
        f"Product: {hw.get('hw_product', 'unknown')}"
    )
    async with httpx.AsyncClient() as client:
        await client.post(WEBHOOK_URL, json={"text": text}, timeout=5.0)
```

---

## Kubernetes label sync

**Scenario**: Automatically apply `node-role.kubernetes.io/` labels via the Kubernetes API when a node's role changes, keeping cluster labels consistent with the attestation registry.

**Events used**: `node.role_changed` (`@on_role_changed`)

```python
from kubernetes_asyncio import client, config  # pip install kubernetes-asyncio
from attestation.hooks import on_role_changed
from attestation.hooks import RoleChangedContext

ROLE_LABEL_MAP = {
    "controlplane": "control-plane",
    "worker-infra": "worker",
    "worker-app": "worker",
}


@on_role_changed
async def sync_k8s_label(ctx: RoleChangedContext) -> None:
    await config.load_kube_config()
    v1 = client.CoreV1Api()
    new_label = ROLE_LABEL_MAP.get(ctx.new_role)
    if not new_label:
        return
    await v1.patch_node(
        ctx.hostname,
        {"metadata": {"labels": {f"node-role.kubernetes.io/{new_label}": ""}}},
    )
```

---

## Vault dynamic secrets — auto-unseal after attestation

**Scenario**: Retrieve a node-specific Vault token immediately after attestation so the node can unseal its encrypted disks without operator involvement.

**Events used**: `node.online` (`@on_online`)

```python
import httpx
import os
from attestation.hooks import on_online
from attestation.hooks import OnlineContext

VAULT_ADDR   = os.environ["VAULT_ADDR"]
VAULT_TOKEN  = os.environ["VAULT_TOKEN"]


@on_online
async def provision_vault_token(ctx: OnlineContext) -> None:
    async with httpx.AsyncClient() as client:
        # Create a short-lived token scoped to this node's EK fingerprint
        resp = await client.post(
            f"{VAULT_ADDR}/v1/auth/token/create",
            headers={"X-Vault-Token": VAULT_TOKEN},
            json={
                "policies": ["node-disk-unseal"],
                "ttl": "1h",
                "meta": {"ek_fingerprint": ctx.ek_fingerprint, "hostname": ctx.hostname},
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        token = resp.json()["auth"]["client_token"]

    # Store the token in the attestation secret vault so the node can retrieve it
    from attestation.core.eventbus import bus  # noqa: PLC0415
    # (real impl: write via the secret_vault REST API or directly to the repo)
    _ = token  # hand off to your delivery mechanism
```

---

## Writing an extension that bundles multiple use cases

If several hooks belong together, wrap them in an extension class so they are packaged, versioned, and discoverable as a unit:

```python
from sdk import AttestationExtension
from fastapi import APIRouter
# Import the hook functions from a sibling module so they register at import time
from . import hooks as _hooks  # noqa: F401


class NodeLifecycleIntegration(AttestationExtension):
    @property
    def name(self) -> str:
        return "node_lifecycle"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "CMDB sync + Slack alerts + Vault provisioning"

    def get_router(self) -> APIRouter | None:
        return None

    def get_models(self) -> list[type]:
        return []
```

Importing `hooks` as a side effect is enough — the decorators register the handlers with the global bus at import time. No additional wiring is required.

---

## Quick reference

| Use case | Decorator(s) | Key dependency |
|---|---|---|
| SPIFFE identity | `@on_provisioning`, `@on_decommissioned` | `spire-server` CLI |
| CMDB sync | `@on_online`, `@on_decommissioned` | `httpx` |
| Slack / Teams alert | `@on_registered` | `httpx` + webhook URL |
| Kubernetes label sync | `@on_role_changed` | `kubernetes-asyncio` |
| Vault token provisioning | `@on_online` | `httpx` + Vault API |
| Audit all events | `@on_any_event` | — |

For the full event and context API see [extension-development.md](extension-development.md).

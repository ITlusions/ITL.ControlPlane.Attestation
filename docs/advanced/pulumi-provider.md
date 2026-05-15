---
layout: default
title: Pulumi Provider
category: Advanced
description: Infrastructure-as-Code automation for machine registration and approval
---

# Pulumi Provider — `pulumi-itl-attestation`

The `pulumi-itl-attestation` package is a Pulumi [dynamic provider](https://www.pulumi.com/docs/concepts/resources/dynamic-providers/) that manages the full machine lifecycle through the Attestation REST API.  
Machines and their approvals become **Pulumi resources** — diff'd, deployed, and destroyed like any other infrastructure.

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

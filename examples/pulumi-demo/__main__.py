"""ITL Attestation — Pulumi demo program.

Demonstrates registering two bare-metal machines, approving them, and
creating per-machine secrets (random enrollment tokens + bootstrap credential
bundles) managed entirely by Pulumi.

Stack config keys
-----------------
attestation:endpoint   Base URL of the Attestation Service (default: http://localhost:8080)
attestation:token      Operator bearer token  [secret]

Quick start
-----------
# 1. Start the service
docker compose up -d

# 2. Create a stack
pulumi stack init dev

# 3. Set config
pulumi config set attestation:endpoint http://localhost:8080
pulumi config set --secret attestation:token <your-admin-token>

# 4. Deploy
pulumi up

# 5. Inspect secrets
pulumi stack output --show-secrets

# 6. Simulate external drift: revoke cp-node-01 in the UI, then:
pulumi refresh        # detects the machine is gone
pulumi up             # re-registers it; rotates enrollment token

# 7. Tear down
pulumi destroy
"""

from __future__ import annotations

import json

import pulumi
import pulumi_random as random
from pulumi import Output, ResourceOptions

# Import from the provider package — enums are re-exported for convenience.
from pulumi_provider import (
    MachineApproval,
    NodeRole,
    RegisteredMachine,
)

# ── Config ─────────────────────────────────────────────────────────────────────

cfg = pulumi.Config("attestation")
endpoint: str = cfg.get("endpoint") or "http://localhost:8080"
token = cfg.require_secret("token")

# ── Fake EK material (in a real deployment read from TPM provisioning receipts) ─
#
# A real ek_cert_pem is the PEM-encoded TPM Endorsement Key certificate issued
# by the TPM manufacturer (e.g. Infineon, STMicro).  For local dev/testing the
# service accepts any well-formed PEM — the validator only checks fingerprint
# length and hex charset, not the actual cert chain.

_FAKE_EK_PEM = """\
-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEADEMO0000000000000000
0000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000DEMOONLY==
-----END CERTIFICATE-----
"""

# SHA-384 hex fingerprints — must be exactly 96 lowercase hex chars.
_CP_EK_FP  = "a" * 96   # controlplane-01 fake fingerprint
_WRK_EK_FP = "b" * 96   # worker-01 fake fingerprint

# ── Per-machine enrollment secrets ────────────────────────────────────────────
#
# Each machine gets its own random enrollment token (32 bytes → 44-char base64).
# pulumi_random.RandomPassword generates a cryptographically random secret,
# stores it encrypted in Pulumi state, and never changes it on subsequent
# `pulumi up` runs unless you explicitly call `pulumi state delete` or rotate.

cp_enrollment_token = random.RandomPassword(
    "cp-enrollment-token",
    length=44,
    special=False,       # base64-safe alphabet (url_encoded=True handles +/)
    opts=ResourceOptions(additional_secret_outputs=["result"]),
)

worker_enrollment_token = random.RandomPassword(
    "worker-enrollment-token",
    length=44,
    special=False,
    opts=ResourceOptions(additional_secret_outputs=["result"]),
)

# ── Machine: controlplane-01 ───────────────────────────────────────────────────

cp_machine = RegisteredMachine(
    "controlplane-01",
    endpoint=endpoint,
    token=token,
    ek_fingerprint=_CP_EK_FP,
    ek_cert_pem=_FAKE_EK_PEM,
    hw_serial="SN-CP-001",
    hw_product="HPE ProLiant DL380 Gen11",
    hw_mac="aa:bb:cc:dd:ee:01",
    desired_role=NodeRole.controlplane,
)

cp_approval = MachineApproval(
    "controlplane-01-approval",
    endpoint=endpoint,
    token=token,
    machine_id=cp_machine.machine_id,
    role=NodeRole.controlplane,
    hostname="cp-node-01.cluster.local",
    assigned_ip="10.0.1.10",
    opts=ResourceOptions(depends_on=[cp_machine]),
)

# ── Machine: worker-01 ─────────────────────────────────────────────────────────

worker_machine = RegisteredMachine(
    "worker-01",
    endpoint=endpoint,
    token=token,
    ek_fingerprint=_WRK_EK_FP,
    ek_cert_pem=_FAKE_EK_PEM,
    hw_serial="SN-WRK-001",
    hw_product="Dell PowerEdge R750",
    hw_mac="aa:bb:cc:dd:ee:02",
    desired_role=NodeRole.worker_app,
)

worker_approval = MachineApproval(
    "worker-01-approval",
    endpoint=endpoint,
    token=token,
    machine_id=worker_machine.machine_id,
    role=NodeRole.worker_app,
    hostname="worker-01.cluster.local",
    assigned_ip="10.0.1.20",
    # keep_on_delete=True means `pulumi destroy` will NOT revoke the machine.
    # Useful when you want to decommission the Pulumi stack without wiping nodes.
    keep_on_delete=False,
    opts=ResourceOptions(depends_on=[worker_machine]),
)

# ── Bootstrap credential bundles ──────────────────────────────────────────────
#
# Combine the service-issued config_token with our per-machine enrollment token
# into a single JSON object.  Output.all() resolves all Outputs before the
# lambda runs; Output.secret() marks the result as a secret so Pulumi encrypts
# it in state and never prints it in plain text during `pulumi up`.

cp_bootstrap_bundle = Output.secret(
    Output.all(
        machine_id=cp_machine.machine_id,
        config_token=cp_machine.config_token,
        config_url=cp_machine.config_url,
        enrollment_token=cp_enrollment_token.result,
    ).apply(
        lambda v: json.dumps({
            "machine_id":       v["machine_id"],
            "config_url":       v["config_url"],
            "config_token":     v["config_token"],
            "enrollment_token": v["enrollment_token"],
        }, indent=2)
    )
)

worker_bootstrap_bundle = Output.secret(
    Output.all(
        machine_id=worker_machine.machine_id,
        config_token=worker_machine.config_token,
        config_url=worker_machine.config_url,
        enrollment_token=worker_enrollment_token.result,
    ).apply(
        lambda v: json.dumps({
            "machine_id":       v["machine_id"],
            "config_url":       v["config_url"],
            "config_token":     v["config_token"],
            "enrollment_token": v["enrollment_token"],
        }, indent=2)
    )
)

# ── Outputs ────────────────────────────────────────────────────────────────────
# Non-secret outputs — safe to display in CI logs.

pulumi.export("cp_machine_id",            cp_machine.machine_id)
pulumi.export("cp_status",                cp_approval.status)
pulumi.export("cp_config_url",            cp_machine.config_url)

pulumi.export("worker_machine_id",        worker_machine.machine_id)
pulumi.export("worker_status",            worker_approval.status)
pulumi.export("worker_config_url",        worker_machine.config_url)

# Secret outputs — Pulumi encrypts these in state; shown as [secret] in logs.
# Retrieve with: pulumi stack output --show-secrets cp_config_token
pulumi.export("cp_config_token",          cp_machine.config_token)          # [secret]
pulumi.export("cp_enrollment_token",      cp_enrollment_token.result)       # [secret]
pulumi.export("cp_bootstrap_bundle",      cp_bootstrap_bundle)              # [secret]

pulumi.export("worker_config_token",      worker_machine.config_token)      # [secret]
pulumi.export("worker_enrollment_token",  worker_enrollment_token.result)   # [secret]
pulumi.export("worker_bootstrap_bundle",  worker_bootstrap_bundle)          # [secret]

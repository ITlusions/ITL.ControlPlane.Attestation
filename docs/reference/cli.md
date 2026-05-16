---
layout: default
title: CLI Reference
category: Reference
description: Complete command reference for the itl-attestation-cli
---

# CLI Reference — `attestation`

`itl-attestation-cli` is the operator tool for the ITL Attestation Service.  
It wraps the REST API with interactive authentication, table/JSON output, and
TPM-lifecycle workflows.

Install: `pip install itl-attestation-cli`  
Entry point: `attestation`

> Commands marked **[stub]** are defined and discoverable but not yet implemented.

---

## Global Options

These options apply to every command and must be placed **before** the subcommand.

```
attestation [OPTIONS] COMMAND [ARGS]...
```

| Option | Env var | Default | Description |
|---|---|---|---|
| `--api-url TEXT` | `ATTESTATION_API_URL` | `http://localhost:9000` | Attestation API base URL |
| `-o, --output [json\|table]` | — | `table` | Output format |
| `--version` | — | — | Print CLI version and exit |
| `--help` | — | — | Show help and exit |

**Example:**

```sh
attestation --api-url https://attest.itlusions.com --output json machine list
```

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `ATTESTATION_API_URL` | `http://localhost:9000` | API base URL |
| `KEYCLOAK_URL` | `https://sts.itlusions.com` | Keycloak base URL |
| `KEYCLOAK_REALM` | `itlusions` | Keycloak realm |
| `KEYCLOAK_CLIENT_ID` | `attestation-cli` | OIDC client ID |

---

## `auth` — Authentication

```
attestation auth COMMAND
```

### `auth login`

Login to Keycloak and cache the token locally.

```
attestation auth login [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--method [interactive\|password\|device]` | `interactive` | Authentication method |
| `-u, --username TEXT` | — | Username (password method only) |
| `-p, --password TEXT` | — | Password (password method only) |
| `--keycloak-url TEXT` | `$KEYCLOAK_URL` | Keycloak base URL |
| `--realm TEXT` | `$KEYCLOAK_REALM` | Keycloak realm |
| `--client-id TEXT` | `$KEYCLOAK_CLIENT_ID` | OIDC client ID |

**Examples:**

```sh
# Browser-based PKCE (default)
attestation auth login
```
```
Starting interactive browser login...
Opening https://sts.itlusions.com/realms/itlusions/protocol/openid-connect/auth?...
Login successful! Token cached.
   Expires: 2026-05-16 14:30:00 UTC
```

```sh
# Service account / CI
attestation auth login --method password --username svc-ops --password "$SECRET"
```
```
Logging in as svc-ops...
Login successful! Token cached.
   Expires: 2026-05-16 14:30:00 UTC
```

```sh
# Device code flow (headless)
attestation auth login --method device
```
```
Device code: ABCD-EFGH
Open: https://sts.itlusions.com/realms/itlusions/device
Waiting for authorization...
Login successful! Token cached.
   Expires: 2026-05-16 14:30:00 UTC
```

---

### `auth logout`

Remove the cached token.

```
attestation auth logout [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--realm TEXT` | `$KEYCLOAK_REALM` | Keycloak realm |
| `--client-id TEXT` | `$KEYCLOAK_CLIENT_ID` | OIDC client ID |
| `-u, --username TEXT` | — | Limit removal to a specific user's cached token |

**Output:**

```
Logged out successfully. Token removed from cache.
```

---

### `auth whoami`

Decode and display the currently cached token without network calls.

```
attestation auth whoami [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--realm TEXT` | `$KEYCLOAK_REALM` | Keycloak realm |
| `--client-id TEXT` | `$KEYCLOAK_CLIENT_ID` | OIDC client ID |

**Output:**

```
User:    niels.weistra
Email:   niels.weistra@itlusions.com
Realm:   itlusions
Expires: 2026-05-16 14:30:00 UTC
```

---

### `auth cache-list`

List all tokens currently in the local token cache.

```
attestation auth cache-list
```

**Output:**

```
Cached tokens (2):

  Valid
    Realm:   itlusions
    Client:  attestation-cli
    User:    niels.weistra
    Expires: 2026-05-16 14:30:00 UTC

  EXPIRED
    Realm:   itlusions
    Client:  attestation-cli
    User:    svc-ops
    Expires: 2026-05-15 08:00:00 UTC
```

---

### `auth clear-cache`

Delete **all** cached tokens. Prompts for confirmation.

```
attestation auth clear-cache
```

**Output:**

```
Delete all cached tokens? [y/N]: y
Deleted 2 cached token(s).
```

---

## `machine` — Machine Management

```
attestation machine COMMAND
```

Most commands require an active operator token (`auth login`).

### `machine list`

List machines, optionally filtered by status or role.

```
attestation machine list [OPTIONS]
```

| Option | Description |
|---|---|
| `--status TEXT` | Filter by machine status (e.g. `attested`, `pending_approval`, `locked`, `revoked`) |
| `--role TEXT` | Filter by node role (e.g. `controlplane`, `worker`) |

**Example:**

```sh
attestation machine list --status pending_approval
```
```
Machines (2):

  [pending] talos-cp-01 (a3f9c12d...)
     Role:   controlplane
     Status: pending_approval
     IP:     N/A

  [pending] talos-wk-05 (b84d0e77...)
     Role:   worker
     Status: pending_approval
     IP:     N/A
```

```sh
attestation -o json machine list --role controlplane
```
```json
[
  {
    "machine_id": "a3f9c12d-8b2e-4f1a-9c3d-0e5f7a8b9c0d",
    "hostname": "talos-cp-01",
    "role": "controlplane",
    "status": "attested",
    "assigned_ip": "10.0.1.11",
    "registered_at": "2026-05-15T09:12:34Z",
    "attested_at": "2026-05-15T09:14:02Z"
  }
]
```

---

### `machine get`

Show full details for a single machine.

```
attestation machine get MACHINE_ID
```

**Output:**

```
Machine: talos-cp-01
   ID:            a3f9c12d-8b2e-4f1a-9c3d-0e5f7a8b9c0d
   Role:          controlplane
   Status:        attested
   IP:            10.0.1.11
   EK Fingerprint: sha256:4a3b9c1d2e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b
   Registered:    2026-05-15T09:12:34Z
   Attested:      2026-05-15T09:14:02Z
```

---

### `machine approve`

Approve a machine that is in `pending_approval` state.

```
attestation machine approve [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-r, --reason TEXT` | Approval reason (recorded in audit log) |

**Output:**

```
Approved: talos-cp-01 (a3f9c12d...)
```

---

### `machine lock`

Lock a machine, preventing it from attesting.

```
attestation machine lock [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-r, --reason TEXT` | Lock reason |

**Output:**

```
Locked: talos-wk-05 (b84d0e77...)
```

---

### `machine unlock`

Unlock a previously locked machine.

```
attestation machine unlock [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-r, --reason TEXT` | Unlock reason |

**Output:**

```
Unlocked: talos-wk-05 (b84d0e77...)
```

---

### `machine revoke`

Permanently revoke a machine. Prompts for confirmation.

```
attestation machine revoke [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-r, --reason TEXT` | Revocation reason |
| `--yes` | Skip confirmation prompt |

**Output:**

```
Permanently revoke this machine? [y/N]: y
Revoked: talos-wk-05 (b84d0e77...)
```

---

### `machine delete` **[stub]**

Hard-delete the machine record from the database.  
This removes all history. Use `revoke` for recoverable decommission.  
Prompts for confirmation.

```
attestation machine delete MACHINE_ID
```

**Expected output:**

```
Hard-delete this machine record? This cannot be undone. [y/N]: y
Deleted: talos-wk-05 (b84d0e77...)
```

---

### `machine approvals` **[stub]**

Show the dual-control approval history for a machine.

```
attestation machine approvals MACHINE_ID
```

**Expected output:**

```
Approval history for a3f9c12d...:

  2026-05-15T09:13:00Z  APPROVED  by niels.weistra
    Reason: HW verified at rack 3, unit 12

  2026-05-14T16:44:12Z  REJECTED  by svc-ops
    Reason: EK mismatch, re-image required
```

---

### `machine offline-bundle` **[stub]**

Download the offline provisioning bundle for USB-based deployment.

```
attestation machine offline-bundle [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-f, --output-file TEXT` | Write bundle JSON to a file instead of stdout |

**Expected output:**

```sh
attestation machine offline-bundle -f /tmp/talos-cp-01-bundle.json a3f9c12d
```
```
Bundle written to /tmp/talos-cp-01-bundle.json (4.2 KB)
```

---

### `machine import` **[stub]**

Import a machine from an offline TPM receipt file (produced by the USB registration agent).

```
attestation machine import RECEIPT_FILE
```

`RECEIPT_FILE` must be an existing file path.

**Expected output:**

```
Imported: talos-cp-03 (c91e2f44...)
   Status: pending_approval
   Run: attestation machine approve c91e2f44-...
```

---

### `machine request-cert` **[stub]**

Issue an enrollment certificate to a machine using EK-based authentication.

```
attestation machine request-cert MACHINE_ID
```

**Expected output:**

```
Certificate issued for talos-cp-01 (a3f9c12d...)
   Serial:  0x0000000000000042
   Subject: CN=talos-cp-01,OU=nodes,O=ITLusions
   Expires: 2027-05-16T09:14:00Z
   PEM written to stdout — pipe to file or kubeconfig
-----BEGIN CERTIFICATE-----
MIIBpTCCAUugAwIBAgIBQjANBgkqhkiG9w0BAQUFADA...
-----END CERTIFICATE-----
```

---

### `machine ak-activate` **[stub]**

Activate the node's Attestation Key (AK) by verifying a TPM PCR quote.

```
attestation machine ak-activate MACHINE_ID
```

**Expected output:**

```
AK activation for talos-cp-01 (a3f9c12d...):
   PCR quote:  verified
   PCR[0]:     sha256:0000000000000000000000000000000000000000000000000000000000000000
   PCR[7]:     sha256:4a3b9c1d2e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f
   AK status:  active
```

---

### `machine watch` **[stub]**

Poll the machine list and print a refresh whenever state changes.

```
attestation machine watch [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-i, --interval INT` | `5` | Poll interval in seconds |
| `--status TEXT` | — | Filter by status |

**Expected output:**

```
Watching machines (refresh every 5s)  Ctrl-C to stop

[09:14:02]  talos-cp-01   pending_approval  →  attested
[09:14:07]  talos-wk-06   registered        →  pending_approval
```

---

### `machine wipe` **[stub]**

Revoke a machine and set `wipe_pending = True` so that the Talos node resets on its next attestation attempt.  
Prompts for confirmation.

```
attestation machine wipe [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-r, --reason TEXT` | Revocation reason |
| `--yes` | Skip confirmation prompt |

**Expected output:**

```
Revoke with wipe_pending=True? This will trigger a Talos reset on next attest. [y/N]: y
Revoked + wipe scheduled: talos-wk-05 (b84d0e77...)
   The node will reset automatically on its next attestation attempt.
```

---

### `machine stats` **[stub]**

Show machine counts grouped by status and role.

```
attestation machine stats
```

**Expected output:**

```
Machine statistics:

  Status
    attested          12
    pending_approval   2
    locked             1
    revoked            4
    registered         0

  Role
    controlplane       3
    worker            16
```

---

## `audit` — Audit Log

```
attestation audit COMMAND
```

### `audit list`

List audit log entries, with optional pagination and machine filter.

```
attestation audit list [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--machine-id TEXT` | — | Filter by machine ID |
| `--page INT` | `1` | Page number |
| `--per-page INT` | `50` | Items per page |

**Output:**

```
Audit Log (3 of 47):

  [2026-05-16T09:14:02Z] machine.approved
    Operator: niels.weistra
    Machine:  a3f9c12d...
    Detail:   HW verified at rack 3, unit 12

  [2026-05-16T09:10:17Z] machine.registered
    Operator: SYSTEM
    Machine:  a3f9c12d...
    Detail:   EK fingerprint: sha256:4a3b...

  [2026-05-16T08:55:44Z] auth.login
    Operator: niels.weistra
    Detail:   interactive login from 10.0.0.5
```

---

### `audit verify`

Verify the cryptographic chain integrity of the entire audit log.

```
attestation audit verify
```

Returns `VALID` or `INVALID` with a reason.

**Output (pass):**

```
Audit log chain integrity: VALID
```

**Output (fail):**

```
Audit log chain integrity: INVALID
   Error: hash mismatch at entry 38 (id=a7b4c2d1)
```

---

### `audit export` **[stub]**

Export the full audit log to a file.

```
attestation audit export [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-f, --output-file TEXT` | *(required)* | Destination file path |
| `--format [json\|csv]` | `json` | Output file format |

**Example:**

```sh
attestation audit export -f /tmp/audit-2026-05-16.csv --format csv
```

**Expected output:**

```
Exported 47 entries to /tmp/audit-2026-05-16.csv (csv)
```

---

## `secret` — Secret Vault (extension)

```
attestation secret COMMAND
```

Secrets are TPM-encrypted blobs stored per machine.  
Only the machine's own TPM can decrypt the returned blob.

### `secret create`

Create a new secret for a machine.

```
attestation secret create [OPTIONS] MACHINE_ID
```

| Option | Description |
|---|---|
| `-n, --name TEXT` | Secret name *(required)* |
| `-v, --value TEXT` | Secret value in plaintext *(required)* |

**Output:**

```
Secret created:
   ID:      e5f2c91a-0b3d-4a7e-8c1f-2d4e6f8a0b2c
   Machine: a3f9c12d-8b2e-4f1a-9c3d-0e5f7a8b9c0d
   Name:    kube-join-token
   Created: 2026-05-16T09:20:00Z
```

---

### `secret list`

List all secret names for a machine (values are never returned).

```
attestation secret list MACHINE_ID
```

**Output:**

```
Found 3 secret(s):

  kube-join-token
     ID:       e5f2c91a-0b3d-4a7e-8c1f-2d4e6f8a0b2c
     Created:  2026-05-16T09:20:00Z by niels.weistra
     Accessed: 2026-05-16T09:22:14Z (1 times)

  etcd-peer-cert
     ID:       1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d
     Created:  2026-05-15T14:00:00Z by svc-ops
     Accessed: Never

  wireguard-private-key
     ID:       deadbeef-0000-1111-2222-333344445555
     Created:  2026-05-15T14:01:00Z by svc-ops
     Accessed: 2026-05-16T09:14:05Z (3 times)
```

---

### `secret get`

Retrieve an encrypted secret blob for a machine.  
Authentication is via EK fingerprint, **not** the operator token.

```
attestation secret get [OPTIONS] MACHINE_ID SECRET_NAME
```

| Option | Description |
|---|---|
| `--ek-fingerprint TEXT` | Machine EK fingerprint *(required)* |

**Output:**

```
Secret retrieved:
   ID:   e5f2c91a-0b3d-4a7e-8c1f-2d4e6f8a0b2c
   Name: kube-join-token

   Encrypted blob (base64):
   dGhpcyBpcyBhIGZha2UgYmFzZTY0IGVuY3J5cHRlZCBibG9i...

   Nonce: YWJjZGVmZ2hpamtsbW5vcA==
   Tag:   MTIzNDU2Nzg5MGFiY2RlZg==
```

---

### `secret delete`

Permanently delete a secret. Prompts for confirmation.

```
attestation secret delete SECRET_ID
```

**Output:**

```
Are you sure you want to delete this secret? [y/N]: y
Secret e5f2c91a-... deleted
```

---

## `webhook` — Webhook Management (extension)

```
attestation webhook COMMAND
```

All `webhook` commands are **[stub]** — registered and discoverable, not yet implemented.

### `webhook list` **[stub]**

```
attestation webhook list
```

**Expected output:**

```
Webhooks (2):

  [enabled]  f1e2d3c4-...  https://hooks.example.com/attest
             Events: machine.approved, machine.revoked

  [disabled] a0b1c2d3-...  https://ci.example.com/webhook
             Events: machine.registered
```

### `webhook get` **[stub]**

```
attestation webhook get WEBHOOK_ID
```

**Expected output:**

```
Webhook: f1e2d3c4-0a1b-2c3d-4e5f-6a7b8c9d0e1f
   URL:     https://hooks.example.com/attest
   Events:  machine.approved, machine.revoked
   Status:  enabled
   Created: 2026-05-10T12:00:00Z
```

### `webhook create` **[stub]**

```
attestation webhook create [OPTIONS]
```

| Option | Description |
|---|---|
| `-u, --url TEXT` | Target URL to deliver events to *(required)* |
| `-e, --event TEXT` | Event type(s) to subscribe to (repeatable) |
| `-s, --secret TEXT` | HMAC signing secret |

**Expected output:**

```sh
attestation webhook create -u https://hooks.example.com/attest \
  -e machine.approved -e machine.revoked -s "mysecret"
```
```
Webhook created:
   ID:     f1e2d3c4-0a1b-2c3d-4e5f-6a7b8c9d0e1f
   URL:    https://hooks.example.com/attest
   Events: machine.approved, machine.revoked
```

### `webhook update` **[stub]**

```
attestation webhook update [OPTIONS] WEBHOOK_ID
```

| Option | Description |
|---|---|
| `-u, --url TEXT` | New target URL |
| `-e, --event TEXT` | Replace event subscriptions (repeatable) |
| `--enable / --disable` | Enable or disable the webhook |

**Expected output:**

```
Webhook f1e2d3c4-... updated.
```

### `webhook delete` **[stub]**

Prompts for confirmation.

```
attestation webhook delete WEBHOOK_ID
```

**Expected output:**

```
Delete this webhook? [y/N]: y
Webhook f1e2d3c4-... deleted.
```

### `webhook deliveries` **[stub]**

```
attestation webhook deliveries WEBHOOK_ID
```

**Expected output:**

```
Delivery history for f1e2d3c4-... (last 10):

  2026-05-16T09:14:03Z  200 OK       machine.approved  (12ms)
  2026-05-16T08:55:12Z  200 OK       machine.registered (9ms)
  2026-05-15T22:01:44Z  503 ERROR    machine.revoked    retry: 3/3 FAILED
```

### `webhook test` **[stub]**

Send a test ping event to the webhook endpoint.

```
attestation webhook test WEBHOOK_ID
```

**Expected output:**

```
Test event sent to https://hooks.example.com/attest
   Response: 200 OK (11ms)
```

---

## `metrics` — Service Metrics (extension)

```
attestation metrics COMMAND
```

### `metrics show` **[stub]**

Print a Prometheus metrics snapshot from the service.

```
attestation metrics show
```

**Expected output:**

```
# HELP attestation_machines_total Total registered machines by status
# TYPE attestation_machines_total gauge
attestation_machines_total{status="attested"} 12
attestation_machines_total{status="pending_approval"} 2
attestation_machines_total{status="locked"} 1
attestation_machines_total{status="revoked"} 4

# HELP attestation_requests_total Total attestation requests
# TYPE attestation_requests_total counter
attestation_requests_total{result="success"} 287
attestation_requests_total{result="failure"} 14

# HELP attestation_audit_entries_total Total audit log entries
# TYPE attestation_audit_entries_total counter
attestation_audit_entries_total 47
```

---

## Top-Level Utility Commands

### `health` **[stub]**

Check service reachability and report the health status.

```
attestation health
```

**Expected output (healthy):**

```
Service health: OK
   API:      https://attest.itlusions.com  (23ms)
   Database: OK
   CA:       OK
```

**Expected output (degraded):**

```
Service health: DEGRADED
   API:      https://attest.itlusions.com  (23ms)
   Database: OK
   CA:       ERROR  enrollment CA unreachable
```

### `version` **[stub]**

Show the CLI version and the service version returned by the API.

```
attestation version
```

**Expected output:**

```
CLI:     itl-attestation-cli 0.1.0
Service: itl-controlplane-attestation 1.0.0
   Build: 2026-05-16T08:00:00Z  git:a1b2c3d
```

### `config` **[stub]**

Show the active configuration: resolved API URL, Keycloak realm, and client ID.

```
attestation config
```

**Expected output:**

```
Active configuration:
   API URL:    https://attest.itlusions.com  (from ATTESTATION_API_URL)
   Realm:      itlusions                     (from KEYCLOAK_REALM)
   Client ID:  attestation-cli               (from KEYCLOAK_CLIENT_ID)
   Keycloak:   https://sts.itlusions.com     (from KEYCLOAK_URL)
   Token:      cached, expires 2026-05-16 14:30:00 UTC
```

---

## Quick-Reference Cheatsheet

```sh
# Login
attestation auth login
attestation auth whoami

# List machines awaiting approval
attestation machine list --status pending_approval

# Approve and verify
attestation machine approve --reason "HW verified by ops" <id>
attestation machine get <id>

# Lock a suspect node
attestation machine lock --reason "Anomalous PCR values" <id>

# Revoke permanently
attestation machine revoke --reason "Decommissioned" <id>

# Audit
attestation audit list --machine-id <id>
attestation audit verify

# Secrets
attestation secret create --name kube-join-token --value "<token>" <machine_id>
attestation secret list <machine_id>
```

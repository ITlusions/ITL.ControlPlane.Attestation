---
layout: default
title: API Endpoints
category: Reference
description: Complete REST API endpoint documentation
---

# API Endpoints — ITL.ControlPlane.Attestation

Base URL: `https://attest.itlusions.com`  
Interactive docs: `https://attest.itlusions.com/docs`

---

> **For Operators**: Most management operations are easier with the CLI: `pip install itl-attestation-cli`. See [DEPLOYMENT.md](DEPLOYMENT.md#cli-installation) for setup and [OPERATIONS.md](OPERATIONS.md) for workflow examples. This document describes the underlying REST API for integration and troubleshooting.

---

## Authentication

Admin endpoints authenticate operators in the following order of precedence:

### 1. Keycloak OIDC JWT (recommended)

```
Authorization: Bearer <keycloak-access-token>
```

The service validates the JWT against the Keycloak JWKS endpoint configured by `ITL_OIDC_ISSUER`. The token must carry the `ITL_OIDC_OPERATOR_ROLE` claim (default: `attestation-operator`) in either `realm_access.roles` or `resource_access.<client>.roles`. The operator identity recorded in audit log entries is the token's `preferred_username` (fallback: `sub`).

**Obtaining a token from Keycloak (`sts.itlusions.com`):**

```sh
TOKEN=$(curl -s -X POST \
  "https://sts.itlusions.com/realms/itl/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=attestation-service" \
  -d "username=$OPERATOR_USER" \
  -d "password=$OPERATOR_PASS" \
  | jq -r .access_token)
```

### 2. mTLS client certificate (non-OIDC environments)

Nginx (or another TLS-terminating proxy) can forward the verified client cert PEM as a URL-encoded `X-Client-Cert` header. The cert must have been issued by the Enrollment CA with `OU=operator`. The cert `CN` is used as the operator identity.

```
X-Client-Cert: <url-encoded-PEM>
```

### 3. Break-glass shared token (emergency only)

```
Authorization: Bearer <ITL_ADMIN_TOKEN>
```

Falls back to the shared `ITL_ADMIN_TOKEN` when neither OIDC nor mTLS succeeds. All actions performed this way are logged with `operator_cn = SYSTEM`. **This path exists for emergencies — prefer OIDC for normal operations.**

---

Public endpoints (`/register`, `/attest`, `/config`, `/enroll`, `/request-cert`, `/healthz`) do not require authentication.

---

## Health

### `GET /healthz`

Liveness probe. Returns HTTP 200 when the service is up.

**Response**
```json
{ "status": "ok" }
```

---

## Registration

### `POST /api/v1/register`

Register a machine by TPM EK fingerprint. Called from the USB registration agent before the machine is ever booted.

If the machine was previously registered (same EK fingerprint), the existing record is updated with a fresh config token and the same ISO URL is returned for the new boot.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ek_fingerprint` | string (64-char SHA-256 or 96-char SHA-384 hex) | Yes | SHA-256 or SHA-384 fingerprint of the raw EK cert/pub bytes |
| `ek_cert_pem` | string (base64-encoded PEM/DER) | Yes | Raw EK certificate material from the TPM |
| `ek_source` | `"cert"` \| `"pub"` | No (default: `"cert"`) | Whether the EK material is an X.509 cert or a bare public key |
| `hw_uuid` | string | No | SMBIOS system UUID |
| `hw_mac` | string | No | Primary NIC MAC address |
| `hw_serial` | string | No | SMBIOS serial number |
| `hw_product` | string | No | SMBIOS product name |
| `desired_role` | `"controlplane"` \| `"worker-infra"` \| `"worker-app"` | No | Requested role (operator can override at approval) |

**Response 200**

```json
{
  "machine_id":   "550e8400-e29b-41d4-a716-446655440000",
  "role":         "worker-app",
  "status":       "registered",
  "iso_url":      "https://factory.talos.dev/image/<schematic>/v1.9.5/metal-amd64.iso",
  "config_token": "abc123...",
  "config_url":   "https://attest.itlusions.com/api/v1/config/abc123...",
  "message":      "Machine registered — download ISO and boot to continue"
}
```

**Errors**

| Code | Reason |
|---|---|
| 422 | EK fingerprint format invalid, or server-computed fingerprint does not match `ek_fingerprint` |
| 503 | Talos Image Factory unreachable |

---

## Extension Self-Registration

### `POST /api/v1/self-register`

Extension-initiated registration. Called by the `itl-tpm-register` Talos extension on first boot of a **generic** Talos ISO. Does not call the Talos Image Factory — the machine is already booted. No USB agent required.

**Extension flow after calling this endpoint:**

```mermaid
sequenceDiagram
    participant Ext as Extension
    participant API as Attestation API
    participant Op as Operator
    
    Ext->>API: POST /api/v1/self-register
    API-->>Ext: status: pending_approval
    
    loop Every 60s while pending
        Ext->>API: POST /api/v1/attest
        API-->>Ext: action: "none"
    end
    
    Op->>API: Approve machine
    
    Ext->>API: POST /api/v1/attest
    API-->>Ext: action: "apply-config" + config_url
    
    Ext->>Ext: curl config_url \| talosctl apply-config --insecure
    Ext->>Ext: Reboot with full MachineConfig
```

**Request body** — same fields as `RegisterRequest` except `desired_role` is optional and no `iso_url` is returned.

| Field | Type | Required |
|---|---|---|
| `ek_fingerprint` | SHA-256 hex | Yes |
| `ek_cert_pem` | base64-encoded PEM/DER | Yes |
| `ek_source` | `"cert"` \| `"pub"` | No |
| `hw_uuid`, `hw_mac`, `hw_serial`, `hw_product` | string | No |
| `desired_role` | role string | No |

**Response 200**

```json
{
  "machine_id":   "550e8400-...",
  "role":         "worker-app",
  "status":       "pending_approval",
  "config_token": null,
  "config_url":   null,
  "message":      "Machine registered — awaiting operator approval. Poll POST /api/v1/attest every 60 s; when action=apply-config, fetch config_url and run: talosctl apply-config --insecure --file <(curl -sf <config_url>)"
}
```

If the machine is already registered, the existing record is returned so the extension can proceed directly to `POST /api/v1/attest`.

**Errors**

| Code | Reason |
|---|---|
| 422 | Missing EK material or fingerprint mismatch |

---

## Attestation

### `GET /api/v1/attest/challenge`

Issue a server-side anti-replay nonce. The client must include the returned `nonce_id` in the subsequent `POST /api/v1/attest` when `ITL_REQUIRE_NONCE=true`. Nonces are single-use and expire after 60 seconds.

**Response 200**

```json
{
  "nonce_id":   "a3f1b8c2d...",
  "nonce":      "<base64-encoded 32-byte random value>",
  "expires_at": "2026-05-14T11:42:00+00:00"
}
```

**Errors**

| Code | Reason |
|---|---|
| 429 | Nonce store capacity exceeded (too many outstanding challenges) |

---

### `POST /api/v1/attest`

Called by the `itl-tpm-register` Talos extension on first boot. Verifies the EK fingerprint against the registered record and advances the machine to `attested`.

If the machine is unknown, a `pending_approval` record is created automatically.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ek_fingerprint` | string | Yes | SHA-256 hex (64 chars) or SHA-384 hex (96 chars) of EK material |
| `ek_cert_pem` | string | Yes | Raw EK material (base64-encoded) |
| `ek_source` | string | No | `"cert"` or `"pub"` |
| `nonce_id` | string | No | Server-issued nonce ID from `GET /attest/challenge` (required when `ITL_REQUIRE_NONCE=true`) |
| `nonce_signature` | string | No | base64-encoded signature over nonce bytes using AK private key |
| `pcr_quote` | string | No | base64-encoded `TPM2B_ATTEST` (stored, verified when `ITL_REQUIRE_QUOTE=true`) |
| `pcr_signature` | string | No | base64-encoded `TPMT_SIGNATURE` |
| `pcr_nonce` | string | No | Nonce used during quote generation |
| `hw_uuid`, `hw_mac`, `hw_serial`, `hw_product` | string | No | Hardware identity fields |

**Response 200**

```json
{
  "machine_id": "550e8400-...",
  "status":     "attested",
  "hostname":   "k8s-worker-01",
  "role":       "worker-app",
  "message":    "Attestation successful",
  "action":     "none"
}
```

The `action` field instructs the Talos extension what to do:

| `action` | Meaning |
|---|---|
| `"none"` | Normal operation |
| `"wipe"` | Machine revoked with `wipe_pending=true`; extension calls `talosctl reset --graceful=false` |
| `"lock"` | Machine temporarily locked; extension halts enrollment and logs |

**Errors**

| Code | Reason |
|---|---|
| 403 | Machine is in `rejected` state |
| 422 | EK fingerprint mismatch |

---

## Config Delivery

Both config endpoints support **EK-bound AES-256-GCM encrypted delivery**.  Set `Accept: application/vnd.itl.config.encrypted+json` to receive an encrypted envelope instead of plaintext YAML.  See [EK-bound Config Encryption](#ek-bound-config-encryption) below.

### `GET /api/v1/config?mac=<mac>`

Generic ISO config endpoint. Used when a single Talos ISO is deployed without a pre-registered config token. Talos appends `?mac=<hw_mac>` automatically.

Returns the full role-specific MachineConfig YAML for `attested` machines. Returns a safe pending config (no cluster secrets) for all others.

**Query parameters**

| Parameter | Description |
|---|---|
| `mac` | Hardware MAC address (colon-separated, case-insensitive) |

**Request headers (optional)**

| Header | Value | Effect |
|---|---|---|
| `Accept` | `application/vnd.itl.config.encrypted+json` | Return EK-bound encrypted envelope (see below) |

**Response 200** — `application/yaml` (full MachineConfig for attested machines), `text/plain` (pending config), or `application/vnd.itl.config.encrypted+json` (encrypted envelope when requested)

---

### `GET /api/v1/config/{token}`

One-time Talos MachineConfig endpoint. Baked into the custom ISO via the Talos Image Factory kernel argument `talos.config=<this-url>`.

The token is consumed after the first successful fetch but remains re-fetchable (Talos may retry on reboot). Returns a pending config for machines still in `pending_approval`.

**Request headers (optional)**

| Header | Value | Effect |
|---|---|---|
| `Accept` | `application/vnd.itl.config.encrypted+json` | Return EK-bound encrypted envelope (see below) |

**Response 200** — `application/yaml` or `application/vnd.itl.config.encrypted+json`

**Errors**

| Code | Reason |
|---|---|
| 404 | Token not found |
| 406 | `ITL_REQUIRE_ENCRYPTED_DELIVERY=true` and request did not include the encrypted `Accept` header |

---

### EK-bound Config Encryption

When `Accept: application/vnd.itl.config.encrypted+json` is sent, the service wraps a per-delivery AES-256 key with the machine's registered EK public key (RSA-OAEP-SHA256) and encrypts the MachineConfig payload with AES-256-GCM.  Only the TPM that owns the EK private key can unwrap the AES key and decrypt the config.

**Encrypted envelope response**

```json
{
  "format":      "ek-aes256gcm-v1",
  "machine_id":  "550e8400-e29b-41d4-a716-446655440000",
  "wrapped_key": "<base64 RSA-OAEP-SHA256 ciphertext of 32-byte AES key>",
  "iv":          "<base64 96-bit GCM nonce>",
  "ciphertext":  "<base64 AES-256-GCM ciphertext + 128-bit auth tag>"
}
```

**Client-side decryption (`itl-tpm-register` Talos extension)**

```bash
# Unwrap AES key using TPM RSA decrypt (TPM2_RSA_Decrypt, OAEP-SHA256)
tpm2_rsadecrypt -c 0x81010001 -s oaep -I wrapped_key.bin -o aes_key.bin

# Decrypt config payload
openssl enc -d -aes-256-gcm \
    -K $(xxd -p aes_key.bin | tr -d '\n') \
    -iv $(echo "$IV_BASE64" | base64 -d | xxd -p | tr -d '\n') \
    -in ciphertext.bin -out config.yaml
```

**Environment variables**

| Variable | Default | Description |
|---|---|---|
| `ITL_REQUIRE_ENCRYPTED_DELIVERY` | `false` | When `true`, plaintext config delivery returns 406. All clients must send `Accept: application/vnd.itl.config.encrypted+json`. |

**Notes**

- The EK certificate is stored when the machine first registers or attests.  Machines registered before this feature was introduced will not have a stored EK cert; encrypted delivery will fall back to plaintext (or return 406 if enforcement is enabled).
- Only RSA EK keys are supported for key wrapping.  EC EK keys fall back to plaintext.

---

## Machine Lifecycle (Admin)

All endpoints in this section require operator authentication (see [Authentication](#authentication) above).

---

### `GET /api/v1/machines`

List all registered machines.

**Response 200**

```json
[
  {
    "machine_id":     "550e8400-...",
    "ek_fingerprint": "a3f1...",
    "hw_uuid":        "...",
    "hw_mac":         "aa:bb:cc:dd:ee:ff",
    "hw_serial":      "SVTF123A",
    "hw_product":     "PowerEdge R640",
    "role":           "worker-app",
    "status":         "attested",
    "hostname":       "k8s-worker-01",
    "assigned_ip":    "10.0.1.11/24",
    "registered_at":  "2026-05-11T10:00:00",
    "attested_at":    "2026-05-11T10:05:00",
    "locked_at":      null,
    "revoked_at":     null,
    "wipe_pending":   false
  }
]
```

---

### `POST /api/v1/machines/{machine_id}/approve`

Approve a `pending_approval` or `registered` machine. Assigns role, hostname, and IP. Issues a fresh config token.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `role` | `"controlplane"` \| `"worker-infra"` \| `"worker-app"` | Yes | Node role in the cluster |
| `hostname` | string | No | Kubernetes node hostname |
| `assigned_ip` | string (CIDR) | No | Static IP for `machine.network.interfaces[0]` |

**Response 200** — full `MachineDetail` object (immediate approval — role not in `ITL_DUAL_CONTROL_ROLES`)

**Response 202** — `PendingApprovalResponse` (first vote for a dual-control role; a second operator must also approve)

```json
{
  "machine_id":         "550e8400-...",
  "status":             "pending_second_approval",
  "message":            "Approval vote recorded for operator 'alice'. A second operator must also approve before the machine is registered.",
  "approvals_received": 1,
  "approvals_required": 2,
  "expires_at":         "2026-05-14T17:20:00+00:00"
}
```

When a second, **different** operator calls this endpoint within the window (`ITL_DUAL_CONTROL_WINDOW_SECONDS`), the machine moves to `registered` and a `200 MachineDetail` is returned. If the window expires before the second approval, the first vote is discarded and a new window starts on the next call.

---

### `POST /api/v1/machines/{machine_id}/revoke`

Revoke a machine. With `wipe=true`, the next attestation triggers a remote `talosctl reset`.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `wipe` | bool | `false` | When `true`, sets `wipe_pending=true`; next attest returns `action=wipe` |
| `reason` | string | null | Audit note |

**Response 200** — full `MachineDetail` object

---

### `POST /api/v1/machines/{machine_id}/lock`

Temporarily lock a machine. No data is destroyed. Reversible with `/unlock`.

**Request body**

| Field | Type | Description |
|---|---|---|
| `reason` | string | Audit note |

**Response 200** — full `MachineDetail` object

---

### `POST /api/v1/machines/{machine_id}/unlock`

Restore a locked machine to `attested`.

**Response 200** — full `MachineDetail` object

---

### `GET /api/v1/machines/{machine_id}/offline-bundle`

Generate a complete airgap bundle for machines that cannot reach the service during initial deployment.

Returns a JSON payload containing:
- `iso_url` — Talos ISO download URL (from Image Factory)
- `config_token` — one-time config token
- `config_url` — full config endpoint URL
- `machineconfig` — inline MachineConfig YAML with embedded enrollment cert and key

**Response 200**

```json
{
  "machine_id":    "550e8400-...",
  "iso_url":       "https://factory.talos.dev/image/.../metal-amd64.iso",
  "config_token":  "abc123...",
  "config_url":    "https://attest.itlusions.com/api/v1/config/abc123...",
  "machineconfig": "version: v1alpha1\n..."
}
```

---

### `POST /api/v1/machines/import`

Import a machine from a TPM receipt written by the offline USB agent. Registers without booting an ISO.

**Request body** — TPM receipt fields (same as `RegisterRequest` minus the factory ISO call)

---

### `GET /api/v1/machines/{machine_id}/approvals`

List all dual-control approval requests for a machine (including expired and consumed votes). Useful for auditing who voted and when.

**Response 200**

```json
[
  {
    "id":          1,
    "machine_id":  "550e8400-...",
    "operator_cn": "alice",
    "role":        "controlplane",
    "hostname":    "cp-01",
    "assigned_ip": "10.0.0.1/24",
    "created_at":  "2026-05-14T17:00:00+00:00",
    "expires_at":  "2026-05-14T17:10:00+00:00",
    "consumed":    true
  }
]
```

---

## Audit Log (Admin)

### `GET /api/v1/audit`

Paginated, newest-first view of the append-only audit log. Every admin action (approve, revoke, lock, unlock, offline-bundle, import) is recorded here with the operator identity, machine state transition, and optional detail note.

The log is **append-only** — no entry is ever updated or deleted. Every entry includes `prev_hash` and `entry_hash` fields that form a cryptographically chained sequence. Use `GET /api/v1/audit/verify` to validate the full chain.

**Query parameters**

| Parameter | Default | Description |
|---|---|---|
| `page` | `1` | Page number (1-based) |
| `per_page` | `50` | Entries per page (max 200) |

**Response 200**

```json
[
  {
    "id":          42,
    "timestamp":   "2026-05-14T17:05:00+00:00",
    "operator_cn": "niels.weistra",
    "action":      "approve",
    "machine_id":  "550e8400-...",
    "prev_state":  "pending_approval",
    "new_state":   "registered",
    "detail":      "role=controlplane hostname=cp-01",
    "prev_hash":   "a3f1b8c2d...",
    "entry_hash":  "e7d4c9f1a..."
  },
  {
    "id":          41,
    "timestamp":   "2026-05-14T17:04:30+00:00",
    "operator_cn": "alice",
    "action":      "approve_vote",
    "machine_id":  "550e8400-...",
    "prev_state":  "pending_approval",
    "new_state":   null,
    "detail":      "first approval vote — awaiting second operator (quorum=2)",
    "prev_hash":   "0000000000000000000000000000000000000000000000000000000000000000",
    "entry_hash":  "a3f1b8c2d..."
  }
]
```

`operator_cn` is `"SYSTEM"` for any action performed with the break-glass `ITL_ADMIN_TOKEN`.

---

### `GET /api/v1/audit/verify`

Walk the full audit log hash chain and report its integrity. Re-computes every entry's SHA-256 hash and verifies that each `prev_hash` matches the previous entry's `entry_hash`.

The chain root hash (last entry's `entry_hash`) can be published externally (Git commit, transparency log, webhook) to provide out-of-band tamper evidence.

**Response 200 — valid chain**

```json
{
  "valid":            true,
  "entries":          1842,
  "root_hash":        "abc123...",
  "first_invalid_id": null,
  "error":            null
}
```

**Response 200 — broken chain**

```json
{
  "valid":            false,
  "entries":          1842,
  "root_hash":        null,
  "first_invalid_id": 37,
  "error":            "entry_hash mismatch at entry id=37"
}
```

| Field | Description |
|---|---|
| `valid` | `true` iff every entry hash is correct and the chain is unbroken |
| `entries` | Total number of entries inspected |
| `root_hash` | `entry_hash` of the last entry (current chain tip); `null` when `valid=false` or the table is empty |
| `first_invalid_id` | `id` of the first entry with a bad hash; `null` when `valid=true` |
| `error` | Human-readable failure description; `null` when `valid=true` |

## Certificate Enrollment (Public)

### `POST /api/v1/machines/{machine_id}/request-cert`

Machine-authenticated certificate request. The machine re-presents its EK material to prove it is the same physical hardware. No admin token required.

If `wrapping_key_pem` is supplied, the private key is encrypted with that RSA public key using OAEP-SHA256 before being returned (for TPM-resident key unwrap on the client).

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ek_fingerprint` | string | Yes | Must match stored record |
| `ek_cert_pem` | string | Yes | EK material for re-verification |
| `ek_source` | string | No | `"cert"` or `"pub"` |
| `wrapping_key_pem` | string | No | TPM-resident RSA public key for key wrapping |

**Response 200**

```json
{
  "machine_id":                   "550e8400-...",
  "role":                         "worker-app",
  "enrollment_cert_pem":          "-----BEGIN CERTIFICATE-----\n...",
  "enrollment_key_pem":           "-----BEGIN EC PRIVATE KEY-----\n...",
  "enrollment_key_encrypted_b64": "",
  "enrollment_ca_pem":            "-----BEGIN CERTIFICATE-----\n...",
  "valid_days":                   30,
  "message":                      "Enrollment cert issued"
}
```

When `wrapping_key_pem` is supplied, `enrollment_key_pem` is empty and `enrollment_key_encrypted_b64` contains the base64-encoded RSA-OAEP-SHA256 ciphertext of the private key PEM.

---

### `POST /api/v1/machines/enroll`

Certificate-based self-enrollment for offline nodes. Called by the `tpm-attest.sh` script on first Talos boot when an enrollment cert was embedded in the machineconfig.

Two-step challenge-response:
1. Cert chain verified against Enrollment CA
2. Nonce signature verified with cert public key (proves private key possession)

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `cert_pem` | string | Yes | Enrollment cert PEM |
| `nonce` | string | Yes | Random string generated by server (obtained from a prior challenge endpoint, or embedded) |
| `nonce_signature` | string | Yes | Base64 RSA-PKCS1v15-SHA256 signature over the nonce |

**Response 200**

```json
{
  "machine_id": "550e8400-...",
  "status":     "attested",
  "message":    "Self-enrollment successful"
}
```

**Errors**

| Code | Reason |
|---|---|
| 403 | Cert chain verification failed, nonce signature invalid, or machine locked/revoked |
| 404 | `machine_id` from cert CN not found |

---

### `POST /api/v1/machines/{machine_id}/ak-activate`

Activate the node's Attestation Key (AK) by submitting a TPM2_Quote signed by the AK. This binds a hardware-resident AK to the registered machine record. Once registered, the AK can be used in subsequent attestation flows for PCR quote verification.

The caller must also re-present its EK cert to prove it is the same physical hardware (prevents AK hijacking by a party who only knows the `machine_id`).

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ek_cert_pem` | string | Yes | EK material — must match stored EK fingerprint for this machine |
| `ak_pub` | string | Yes | SubjectPublicKeyInfo PEM of the AK (ECDSA P-384 or RSA-3072+) |
| `quote` | string | Yes | base64-encoded `TPM2B_ATTEST` structure |
| `quote_sig` | string | Yes | base64-encoded signature over `sha384(quote)` (ECDSA P-384) or `sha384(quote)` (RSA-PSS) |
| `pcr_values` | object | Yes | PCR readings — `{"sha256:0": "<hex>", "sha256:7": "<hex>", ...}` |
| `nonce_id` | string | No | Anti-replay nonce ID from `GET /attest/challenge`; strongly recommended |

**Response 200**

```json
{
  "machine_id":   "550e8400-...",
  "ak_accepted":  true,
  "message":      "AK registered and PCR quote verified"
}
```

**Errors**

| Code | Reason |
|---|---|
| 403 | `ek_cert_pem` does not match stored EK fingerprint, or machine is revoked/rejected |
| 404 | Machine not found |
| 409 | Nonce already consumed — replay detected |
| 410 | Nonce has expired |
| 422 | AK key type/size not accepted, quote signature invalid, or PCR digest mismatch |

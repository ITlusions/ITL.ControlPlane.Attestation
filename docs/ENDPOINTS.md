---
layout: default
title: API Endpoints
---

# API Endpoints — ITL.ControlPlane.Attestation

Base URL: `https://attest.itlusions.com`  
Interactive docs: `https://attest.itlusions.com/docs`

---

## Authentication

Admin endpoints require a Bearer token:

```
Authorization: Bearer <ITL_ADMIN_TOKEN>
```

Public endpoints (`/register`, `/attest`, `/config`, `/enroll`, `/request-cert`, `/healthz`) do not require this header.

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
| `ek_fingerprint` | string (64-char hex SHA-256) | Yes | SHA-256 of the raw EK cert/pub bytes |
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

```
1. Call POST /api/v1/self-register   → status: pending_approval
2. Poll POST /api/v1/attest (every 60 s)
   → action: "none"  while operator has not yet approved
   → action: "apply-config" + config_url  once operator has approved and machine is attested
3. Fetch config_url and apply:
     talosctl apply-config --insecure --file <(curl -sf <config_url>)
4. Talos reboots with its full cluster MachineConfig.
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

### `POST /api/v1/attest`

Called by the `itl-tpm-register` Talos extension on first boot. Verifies the EK fingerprint against the registered record and advances the machine to `attested`.

If the machine is unknown, a `pending_approval` record is created automatically.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `ek_fingerprint` | string | Yes | SHA-256 hex of EK material |
| `ek_cert_pem` | string | Yes | Raw EK material (base64-encoded) |
| `ek_source` | string | No | `"cert"` or `"pub"` |
| `pcr_quote` | string | No | base64-encoded `TPM2B_ATTEST` (stored, not yet verified — see issue #TBD) |
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

### `GET /api/v1/config?mac=<mac>`

Generic ISO config endpoint. Used when a single Talos ISO is deployed without a pre-registered config token. Talos appends `?mac=<hw_mac>` automatically.

Returns the full role-specific MachineConfig YAML for `attested` machines. Returns a safe pending config (no cluster secrets) for all others.

**Query parameters**

| Parameter | Description |
|---|---|
| `mac` | Hardware MAC address (colon-separated, case-insensitive) |

**Response 200** — `application/yaml` (full MachineConfig for attested machines) or `text/plain` (pending config)

---

### `GET /api/v1/config/{token}`

One-time Talos MachineConfig endpoint. Baked into the custom ISO via the Talos Image Factory kernel argument `talos.config=<this-url>`.

The token is consumed after the first successful fetch but remains re-fetchable (Talos may retry on reboot). Returns a pending config for machines still in `pending_approval`.

**Response 200** — `application/yaml`

**Errors**

| Code | Reason |
|---|---|
| 404 | Token not found |

---

## Machine Lifecycle (Admin)

All endpoints in this section require `Authorization: Bearer <ITL_ADMIN_TOKEN>`.

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

**Response 200** — full `MachineDetail` object

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
  "cert_pem":           "-----BEGIN CERTIFICATE-----\n...",
  "key_pem":            "-----BEGIN RSA PRIVATE KEY-----\n...",
  "key_pem_encrypted":  null,
  "ca_cert_pem":        "-----BEGIN CERTIFICATE-----\n...",
  "valid_days":         30
}
```

When `wrapping_key_pem` is supplied, `key_pem` is `null` and `key_pem_encrypted` contains the base64-encoded OAEP ciphertext.

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
| `nonce_signature_b64` | string | Yes | Base64 RSA-PKCS1v15-SHA256 signature over the nonce |

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

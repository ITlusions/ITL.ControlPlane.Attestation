# Architecture — ITL.ControlPlane.Attestation

## Purpose

The Attestation Service is the hardware trust broker for the ITL Control Plane. It answers a single core question for every node that boots:

> "Is this the physical machine we expect, and is it authorised to join the cluster?"

It does this by anchoring machine identity to the TPM Endorsement Key (EK) — a hardware-bound asymmetric key that cannot be migrated or cloned. Machines register before deployment, boot a signed Talos ISO, and are admitted (or rejected) by an operator before receiving cluster credentials.

---

## System Context

```
┌─────────────────────────────────────────────────────────┐
│  USB Registration Agent (Alpine Linux / ITL Kiosk)      │
│  Reads TPM EK cert → POST /api/v1/register              │
└────────────────────────┬────────────────────────────────┘
                         │  HTTPS
                         ▼
┌─────────────────────────────────────────────────────────┐
│           ITL.ControlPlane.Attestation                  │
│           https://attest.itlusions.com                  │
│                                                         │
│  FastAPI  ──  SQLite DB  ──  Enrollment CA (RSA-4096)   │
│                │                                        │
│                └──  Talos Image Factory (factory.talos.dev) │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   Talos Node      Talos Node     Talos Node
   (boots ISO)   (attest on      (offline USB
                  first boot)     bundle)
```

---

## Source Modules

| File | Role |
|---|---|
| `main.py` | FastAPI app — all HTTP endpoints and request routing |
| `models.py` | SQLModel `Machine` ORM table + all Pydantic request/response schemas |
| `tpm_verifier.py` | EK material structural verification and SHA-256 fingerprint computation |
| `enrollment_ca.py` | Self-signed Enrollment CA lifecycle, cert issuance, chain verification, nonce signature, RSA-OAEP wrapping |
| `config_generator.py` | Merge role base configs (downloaded from GitHub Release) with machine-specific overrides to produce Talos MachineConfig YAML |

---

## Data Model

### Machine record (`machines` table)

| Field | Type | Description |
|---|---|---|
| `machine_id` | UUID v4 | Stable logical identifier assigned at registration |
| `ek_fingerprint` | SHA-256 hex (64 chars) | Primary hardware identity — SHA-256 of raw EK cert/pub bytes |
| `ek_source` | `cert` \| `pub` | Which TPM EK material was presented |
| `hw_uuid`, `hw_mac`, `hw_serial`, `hw_product` | string | SMBIOS hardware identity fields (secondary; EK fp is canonical) |
| `role` | `controlplane` \| `worker-infra` \| `worker-app` | Assigned Talos node role |
| `status` | enum (see below) | Current lifecycle state |
| `hostname`, `assigned_ip` | optional string | Set by operator at approval |
| `config_token` | random URL-safe token | One-time token for Talos config fetch |
| `token_consumed` | bool | True after first successful config fetch |
| `wipe_pending` | bool | When True + status=revoked, next attest triggers talosctl reset |

### Machine status state machine

```
                  ┌──────────────────┐
  (USB agent) ──► │   registered     │ ──► (operator approves) ──► re-registered
                  └────────┬─────────┘
                           │ (Talos boot → POST /attest)
                           ▼
                  ┌──────────────────┐
       ┌────────► │    attested      │ ◄──────────┐
       │          └────────┬─────────┘            │
       │                   │                      │
       │     ┌─────────────┼──────────────┐       │
       │     ▼             ▼              ▼       │
       │  locked        revoked     pending_approval
       │  (unlock) ──►  (wipe?)     (first-boot, unknown MAC)
       │
  (POST /attest, re-boot)
```

When `status=revoked` and `wipe_pending=True`, the next `POST /attest` response includes `"action": "wipe"`. The `itl-tpm-register` Talos extension calls `talosctl reset --graceful=false` on receipt, wiping STATE + EPHEMERAL before rebooting to maintenance mode.

---

## Extension Self-Registration Flow (No USB Agent)

When a machine boots a generic Talos ISO with `talos.config=https://attest.itlusions.com/api/v1/config` baked in, the `itl-tpm-register` extension can self-register without any USB agent pre-step.

```
Talos Node (itl-tpm-register ext)  Attestation Service     Operator
──────────────────────────────     ───────────────────     ────────
Boot generic ISO
Read TPM EK cert from /sys
POST /api/v1/self-register ──────►
  ek_fingerprint, ek_cert_pem,     Verify EK material
  hw_uuid, hw_mac, ...             Create Machine(pending_approval)
◄─────────────────────────────── status: pending_approval
                                                            GET /api/v1/machines
                                                            POST /machines/{id}/approve
                                                            (role, hostname, ip)
Poll POST /api/v1/attest ────────►
(every 60 s until approved)        Check status
                                   If still pending: return pending_approval / action=none
◄─────────────────────────────── action: none  (keep polling)

                                   [operator approves → status=registered]

Poll POST /api/v1/attest ────────►
                                   status=registered → transition to attested
                                   Issue fresh config_token
◄─────────────────────────────── status: attested, action: apply-config
                                  config_url: .../config/<token>

curl config_url | talosctl apply-config --insecure --file -
                                         Talos reboots with full cluster config ✓
```

The `action` field in `AttestResponse`:

| `action` | Meaning |
|---|---|
| `"none"` | Still pending or already attested — no action needed |
| `"apply-config"` | Machine just attested; fetch `config_url` and apply with `talosctl apply-config --insecure` |
| `"wipe"` | Machine revoked with `wipe_pending=true`; extension calls `talosctl reset --graceful=false` |
| `"lock"` | Machine temporarily locked; extension halts and logs |

---

## Registration Flow (USB Agent)

```
USB Agent                          Attestation Service
─────────                          ───────────────────
Read TPM EK cert from /sys         
Compute SHA-256 fingerprint        
POST /api/v1/register ────────────►
  ek_fingerprint, ek_cert_pem,     Verify EK structural integrity
  hw_uuid, hw_mac, ...             Recompute fingerprint, compare
                                   Look up existing record by EK fp
                                   If new: create Machine(registered)
                                   If existing: refresh token
                                   POST schematic → factory.talos.dev
                                   Receive ISO URL
◄──────────────────────────────── Return: iso_url, config_token
Download ISO, burn to USB / boot
```

---

## Attestation Flow (First Talos Boot)

```
Talos Node (itl-tpm-register ext)  Attestation Service
──────────────────────────────     ───────────────────
Read TPM EK cert
POST /api/v1/attest ──────────────►
  ek_fingerprint, ek_cert_pem,     Recompute fingerprint
  hw_uuid, hw_mac, ...             Look up Machine by EK fp
                                   Check status (locked/revoked/pending)
                                   Transition: registered → attested
◄──────────────────────────────── Return: status, action, role
```

---

## Config Delivery

### Token-based (pre-registered machines)

The registration response includes a `config_url`:
```
https://attest.itlusions.com/api/v1/config/<token>
```

This URL is baked into the Talos ISO schematic via the Talos Image Factory kernel argument `talos.config=<url>`. Talos fetches it on first boot. The token is consumed after the first successful fetch (but re-fetchable on reboot).

### MAC-based (generic ISO / unknown machines)

A single generic Talos ISO can be deployed with:
```
talos.config=https://attest.itlusions.com/api/v1/config
```

Talos appends `?mac=<hw_mac>` automatically. The service looks up the MAC, returns the full machineconfig for attested machines, or a safe pending config (no cluster secrets) for all others.

---

## MachineConfig Generation

Role base configs (`controlplane-final.yaml`, `worker-infra-final.yaml`, `worker-app-final.yaml`) are pre-generated by the ITL.Talos.HardenedOS CI pipeline and stored at `ITL_CONFIG_CACHE_DIR` (default: `/var/lib/itl-reg/configs`).

The service merges machine-specific overrides on top:

| Override | Source |
|---|---|
| `machine.network.hostname` | Set by operator at approval |
| `machine.network.interfaces[0].addresses` | `assigned_ip` at approval |
| `machine.nodeLabels["itl.io/machine-id"]` | `machine_id` |
| `machine.nodeLabels["itl.io/tpm-ek"]` | First 16 chars of EK fingerprint |
| `machine.nodeAnnotations["itl.io/tpm-ek-full"]` | Full EK fingerprint |
| `machine.files` | Enrollment cert + key (offline bundles only) |

---

## Enrollment PKI

### CA

A self-signed RSA-4096 CA is auto-generated on first startup and persisted at `ITL_ENROLLMENT_CA_DIR` (default: `/var/lib/itl-reg/ca/`). It is valid for 10 years.

### Enrollment Certificates

Short-lived RSA-2048 certs are issued to machines that request them. The cert encodes:

| Field | Value |
|---|---|
| `CN` | `machine_id` |
| `OU` | `role` |
| `Key Usage` | `digitalSignature`, `keyEncipherment` |
| `EKU` | `clientAuth` |
| `URI SAN` | `urn:itl:ek:<ek_fingerprint>` |

The URI SAN binds the cert to the specific TPM hardware identity.

### Two-step enrollment challenge

```
Node                               Attestation Service
────                               ───────────────────
Present cert + nonce signature ──►
                                   1. Verify cert chain against Enrollment CA
                                   2. Verify nonce signature with cert public key
                                   (proves key possession, not just cert possession)
◄─────────────────────────────── Accept or reject
```

### Key wrapping (optional)

If the machine presents a TPM-resident RSA wrapping key (`wrapping_key_pem`), the service encrypts the enrollment private key with RSA-OAEP-SHA256 before returning it. The private key never travels in plaintext — it is decrypted inside the TPM:

```sh
tpm2_rsadecrypt --key-context wrapping.ctx --input enrollment.key.enc --output enrollment.key
```

---

## Technology Stack

| Component | Technology |
|---|---|
| Web framework | FastAPI 0.115+ |
| ORM + schema | SQLModel 0.0.21+ (SQLAlchemy + Pydantic v2) |
| Database | SQLite (single-file, volume-mounted) |
| Cryptography | `cryptography` 43+ |
| HTTP client | `httpx` 0.28+ (Talos Image Factory calls) |
| Config serialisation | PyYAML 6.0+ |
| Runtime | Python 3.12+, Uvicorn 2 workers |
| Container | python:3.12-slim |

---

## Known Limitations

The following security gaps are tracked as GitHub issues:

| Issue | Gap |
|---|---|
| [#1](https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/1) | EK PEM verified by header-sniff only — needs real X.509 parse |
| [#2](https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/2) | Registration accepted without EK material (self-reported fingerprint) |
| [#3](https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/3) | Manufacturer CA chain verification is stubbed — not implemented |
| [#4](https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/4) | Enrollment does not cross-check EK fingerprint from cert URI SAN |

See [SECURITY.md](SECURITY.md) for full threat model and mitigations.

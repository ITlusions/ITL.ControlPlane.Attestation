---
layout: default
title: Security
---

# Security — ITL.ControlPlane.Attestation

## Threat Model

The Attestation Service sits at the trust boundary between physical hardware and the Kubernetes cluster. An attacker who bypasses it can inject unauthorised nodes, receive cluster join credentials, and intercept workloads routed to the rogue node.

### Assets protected

| Asset | Value |
|---|---|
| Cluster join credentials (embedded in MachineConfig) | Critical — compromise grants full cluster access |
| Enrollment CA private key | Critical — compromise allows forging enrollment certs for any machine |
| Keycloak operator credentials / JWT | High — compromise allows machine lifecycle control; dual-control limits blast radius for critical roles |
| Admin break-glass token (`ITL_ADMIN_TOKEN`) | High — emergency bypass; all actions logged as SYSTEM; rotate promptly after use |
| Machine identity (EK fingerprint) | High — spoofing allows a rogue machine to impersonate a trusted node |
| Config tokens | Medium — one-time use; limited to the config for a single machine |

### Attacker profiles

| Profile | Capability |
|---|---|
| Physical attacker | Has the hardware, can read TPM EK cert from sysfs without TPM auth |
| Network attacker (passive) | Can observe API traffic if TLS is misconfigured |
| Network attacker (active) | Can replay captured API requests |
| Insider / rogue operator | Has stolen/compromised Keycloak credentials; can approve/revoke/wipe machines. Dual-control limits blast radius for critical roles. |
| Supply chain attacker | Can modify USB agent before deployment |

---

## Implemented Controls

### EK fingerprint verification

The server always recomputes the SHA-256 fingerprint of the raw EK bytes sent by the client. It never trusts the client-supplied `ek_fingerprint` value without re-deriving it from the actual material. Comparison uses `hmac.compare_digest` (constant-time) to prevent timing-based fingerprint enumeration.

```python
computed_fp = compute_ek_fingerprint(req.ek_cert_pem)
if not fingerprints_match(computed_fp, req.ek_fingerprint):
    raise HTTPException(422, "EK fingerprint mismatch")
```

### Status gating on config delivery

Only machines in `attested` status receive their full MachineConfig. All others (`pending_approval`, `registered`, `locked`, `revoked`) receive a safe pending config that contains no cluster secrets.

### Config token isolation

Config tokens are cryptographically random (`secrets.token_urlsafe(32)`, 256 bits). Each token is scoped to a single machine. Tokens are generated fresh on every registration and approval, invalidating any previously issued token for that machine.

### Admin token authentication

All machine lifecycle endpoints require operator authentication. The service resolves the calling operator in the following order:

1. **Keycloak OIDC JWT** — Bearer token validated against the JWKS published by `ITL_OIDC_ISSUER`. The JWT must carry the `ITL_OIDC_OPERATOR_ROLE` claim. The operator's `preferred_username` (or `sub`) is recorded in every audit log entry.

2. **mTLS client certificate** (`X-Client-Cert` header, URL-encoded PEM forwarded by nginx) — verified against the Enrollment CA; requires `OU=operator`.

3. **Break-glass shared token** (`ITL_ADMIN_TOKEN` Bearer) — emergency path. Actions are logged as `operator_cn = SYSTEM`. If `ITL_ADMIN_TOKEN` is not set the service returns 503 rather than silently accepting requests.

Comparison against `ITL_ADMIN_TOKEN` uses `hmac.compare_digest` (constant-time) to prevent timing side-channel attacks.

### Per-operator identity and audit trail

Every admin action writes an `AuditLogRow` to the `audit_log` table with `operator_cn`, `action`, `machine_id`, `prev_state`, `new_state`, and an optional `detail` string. The repository layer exposes only an `append()` method — there is no update or delete path, making the log append-only by construction.

The audit log is queryable via `GET /api/v1/audit`.

### Dual-control for critical machine roles

When `ITL_DUAL_CONTROL_ROLES` includes a machine's role, a single operator approval is **not** sufficient to register the machine. The flow requires two distinct operators:

1. Operator A calls `POST /machines/{id}/approve` → `202 pending_second_approval`. A vote row is stored with a configurable expiry window (`ITL_DUAL_CONTROL_WINDOW_SECONDS`, default 10 min).
2. Operator B (different identity) calls the same endpoint → `200 registered`. The vote is consumed.

The same operator cannot be their own quorum partner. This eliminates unilateral approval of high-value nodes by a single compromised operator credential.

### Enrollment PKI — chain verification

The `POST /api/v1/machines/enroll` endpoint verifies:
1. The cert was issued by this service's Enrollment CA (issuer DN + signature)
2. The cert is within its validity period
3. The caller possesses the cert's private key (nonce challenge-response with RSA-PKCS1v15-SHA256)

This means a stolen cert PEM alone is not sufficient — the caller must also have the private key.

### Key wrapping for offline bundles

When a machine requests a cert with a TPM-resident wrapping key, the enrollment private key is encrypted with RSA-OAEP-SHA256 before transit. The cleartext private key never leaves the service's memory unencrypted and is not logged.

### Remote wipe

When a machine is revoked with `wipe=true`, the next attestation response instructs the Talos extension to call `talosctl reset --graceful=false`, wiping STATE and EPHEMERAL partitions. This destroys cluster join credentials on the physical node.

---

## Known Gaps (Open Issues)

The following gaps reduce the security guarantees and are tracked in GitHub:

### Issue #1 — EK PEM header-sniffing

**Status**: Open  
**Risk**: High  
**Link**: https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/1

`verify_ek_pem` checks for magic bytes or PEM markers but never parses the certificate. A crafted payload that contains the right header bytes passes validation regardless of its actual content or Key Usage extension.

**Mitigation until fixed**: Only the registration agent (under operator control) calls this endpoint; an attacker also needs a valid 64-char hex string for the fingerprint field.

---

### Issue #2 — Registration without EK material

**Status**: Open  
**Risk**: Critical  
**Link**: https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/2

If `ek_cert_pem` is absent, the service accepts the client-reported `ek_fingerprint` without any cryptographic verification. Any string that looks like a SHA-256 hex digest can be used to register a machine identity.

**Mitigation until fixed**: The USB registration agent always sends EK material in practice; exploiting this gap requires a custom client.

---

### Issue #3 — No manufacturer CA chain verification

**Status**: Open  
**Risk**: Medium  
**Link**: https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/3

EK certs are not verified against Infineon, NTC, STM or other TPM manufacturer CA bundles. A soft-TPM or emulated TPM with a self-signed EK cert is indistinguishable from a real device.

**Mitigation until fixed**: Physical access control to the data centre is the current compensating control. The hardware identity is still bound to the specific cert material — a different self-signed cert produces a different fingerprint.

---

### Issue #4 — Enrollment EK fingerprint not cross-checked

**Status**: Fixed  
**Risk**: High  
**Link**: https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/4

The `urn:itl:ek:<fingerprint>` URI SAN embedded in enrollment certs is now extracted and compared against the registered `ek_fingerprint` during `/enroll`. A valid enrollment cert issued to machine A can no longer be used by machine B to self-enroll as machine A's identity. Certs issued before this fix (no EK SAN) are still accepted with a warning for backwards compatibility.

---

## Security Controls Summary

| Control | Status |
|---|---|
| Server-recomputes EK fingerprint (no client trust) | Implemented |
| Constant-time fingerprint comparison | Implemented |
| Config gated on attestation status | Implemented |
| One-time config tokens (256-bit entropy) | Implemented |
| Per-operator OIDC authentication via Keycloak | Implemented (`ITL_OIDC_ISSUER`) |
| Keycloak role enforcement (`ITL_OIDC_OPERATOR_ROLE`) | Implemented |
| mTLS client cert authentication (nginx `X-Client-Cert`) | Implemented |
| Break-glass shared token (`ITL_ADMIN_TOKEN`) | Implemented (constant-time comparison) |
| Append-only audit log with operator identity | Implemented (`GET /api/v1/audit`) |
| Dual-control approval for critical roles | Implemented (`ITL_DUAL_CONTROL_ROLES`) |
| Enrollment cert chain verification | Implemented |
| Nonce challenge-response (key possession proof) | Implemented |
| AK activation — PCR quote signature verification | Implemented (opt-in via `POST /machines/{id}/ak-activate`) |
| Server-issued nonce for attestation replay protection | Implemented (enforcement opt-in via `ITL_REQUIRE_NONCE=true`) |
| EK cert parsed with X.509 library + Key Usage check | **Missing — issue #1** |
| Registration requires EK material | **Missing — issue #2** |
| Manufacturer CA chain verification | Opt-in via `ITL_TPM_VERIFY_CA` — not enforced by default (**issue #3**) |
| Enrollment EK fingerprint cross-check | **Missing — issue #4** |
| PCR policy enforcement at attestation | Not yet implemented (AK activation verifies quote structure; policy table not enforced) |
| Certificate revocation list (CRL) | Not implemented |

---

## Recommendations for Production

1. **Configure Keycloak OIDC** (`ITL_OIDC_ISSUER=https://sts.itlusions.com/realms/itl`). Create a realm-level role `attestation-operator` and assign it to operator accounts. Never share a single operator account — each human operator should have a personal Keycloak account so the audit log has meaningful `operator_cn` values.

2. **Enable dual-control** for controlplane nodes (`ITL_DUAL_CONTROL_ROLES=controlplane`). This prevents a single compromised operator credential from unilaterally registering a rogue controlplane node.

3. **Forward the audit log to a SIEM.** The `GET /api/v1/audit` endpoint is paginated and append-only. Periodically export it or configure log shipping from the container's structured log output.

4. **Treat `ITL_ADMIN_TOKEN` as a break-glass credential.** Store it in a secrets manager (HashiCorp Vault, Azure Key Vault, Kubernetes Secret with encryption at rest). Do not commit it to version control. Rotate it after any suspected exposure. All break-glass actions are logged as `operator_cn = SYSTEM`.

5. **Back up the Enrollment CA key** at `/var/lib/itl-reg/ca/enrollment-ca.key` (mode 0600). Losing it invalidates all outstanding enrollment certs. Consider rotating the CA periodically (new CA, re-issue all certs).

6. **Apply fixes for issues #1 and #2 before exposing the registration endpoint to untrusted networks.** Those two gaps together allow completely unauthenticated machine identity injection.

7. **Place TLS termination upstream** (nginx, Caddy, or Kubernetes Ingress with cert-manager). The service speaks plain HTTP on port 8080.

8. **Restrict network access** to `POST /api/v1/register` to your deployment VLAN. Attestation (`POST /api/v1/attest`) and config delivery (`GET /api/v1/config`) must be reachable from nodes on first boot.

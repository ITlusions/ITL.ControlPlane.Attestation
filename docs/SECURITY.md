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
| Admin token | High — grants full machine lifecycle control including remote wipe |
| Machine identity (EK fingerprint) | High — spoofing allows a rogue machine to impersonate a trusted node |
| Config tokens | Medium — one-time use; limited to the config for a single machine |

### Attacker profiles

| Profile | Capability |
|---|---|
| Physical attacker | Has the hardware, can read TPM EK cert from sysfs without TPM auth |
| Network attacker (passive) | Can observe API traffic if TLS is misconfigured |
| Network attacker (active) | Can replay captured API requests |
| Insider / rogue operator | Has admin token; can approve/revoke/wipe machines |
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

All machine lifecycle endpoints require a Bearer token checked against `ITL_ADMIN_TOKEN`. The comparison is a direct string equality check (not constant-time — see open issues). If `ITL_ADMIN_TOKEN` is not set, the service refuses to process admin requests (503) rather than silently accepting them.

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

**Status**: Open  
**Risk**: High  
**Link**: https://github.com/ITlusions/ITL.ControlPlane.Attestation/issues/4

The `urn:itl:ek:<fingerprint>` URI SAN embedded in enrollment certs is never read during enrollment. A valid enrollment cert issued to machine A could be used by machine B to self-enroll as machine A's identity.

**Mitigation until fixed**: Enrollment certs are embedded in machineconfigs delivered over TLS and stored at a restricted path (`/var/lib/itl-tpm/`) on the Talos node. Physical access to a node or a compromised machineconfig delivery is required to steal the cert.

---

## Security Controls Summary

| Control | Status |
|---|---|
| Server-recomputes EK fingerprint (no client trust) | Implemented |
| Constant-time fingerprint comparison | Implemented |
| Config gated on attestation status | Implemented |
| One-time config tokens (256-bit entropy) | Implemented |
| Admin bearer token required for lifecycle ops | Implemented |
| Enrollment cert chain verification | Implemented |
| Nonce challenge-response (key possession proof) | Implemented |
| EK cert parsed with X.509 library + Key Usage check | **Missing — issue #1** |
| Registration requires EK material | **Missing — issue #2** |
| Manufacturer CA chain verification | **Missing — issue #3** |
| Enrollment EK fingerprint cross-check | **Missing — issue #4** |
| TPM PCR quote verification (AIK-based remote attestation) | Not implemented (future scope) |
| Admin token constant-time comparison | Not implemented |
| Certificate revocation list (CRL) | Not implemented |

---

## Recommendations for Production

1. **Set `ITL_ADMIN_TOKEN`** to a minimum 32-byte hex random value. Store it in a secrets manager (HashiCorp Vault, Azure Key Vault, Kubernetes Secret with encryption at rest). Do not commit it to version control.

2. **Back up the Enrollment CA key** at `/var/lib/itl-reg/ca/enrollment-ca.key` (mode 0600). Losing it invalidates all outstanding enrollment certs. Consider rotating the CA periodically (new CA, re-issue all certs).

3. **Apply fixes for issues #1 and #2 before exposing the registration endpoint to untrusted networks.** Those two gaps together allow completely unauthenticated machine identity injection.

4. **Place TLS termination upstream** (nginx, Caddy, or Kubernetes Ingress with cert-manager). The service speaks plain HTTP on port 8080.

5. **Restrict network access** to `POST /api/v1/register` to your deployment VLAN. Attestation (`POST /api/v1/attest`) and config delivery (`GET /api/v1/config`) must be reachable from nodes on first boot.

6. **Audit the admin token usage** — every admin operation is logged with machine ID, role, and status transition. Forward logs to a SIEM.

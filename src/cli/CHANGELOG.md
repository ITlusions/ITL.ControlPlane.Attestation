# Changelog

All notable changes to the ITL Attestation CLI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-12

### Added
- Initial release of ITL Attestation CLI
- OIDC authentication via Keycloak with multiple flows:
  - Interactive browser-based login (PKCE)
  - Command-line username/password login
  - Device code flow for headless environments
- Token caching in `~/.itl/attestation-cache/`
- Automatic token refresh when expired
- Machine management commands:
  - `attestation machine list` — List all machines with filters
  - `attestation machine get` — Get machine details
  - `attestation machine approve` — Approve pending machines
  - `attestation machine lock` — Lock machines (temporary disable)
  - `attestation machine unlock` — Unlock locked machines
  - `attestation machine revoke` — Revoke machines (permanent disable)
- Audit log commands:
  - `attestation audit list` — List audit log entries with pagination
  - `attestation audit verify` — Verify cryptographic chain integrity
- Authentication commands:
  - `attestation auth login` — Login with multiple methods
  - `attestation auth logout` — Logout and remove cached token
  - `attestation auth whoami` — Show current user from token
  - `attestation auth cache-list` — List all cached tokens
  - `attestation auth clear-cache` — Delete all cached tokens
- Dual output formats: JSON and table
- Environment variable configuration support
- REST API client for attestation service
- Comprehensive documentation and examples

[0.1.0]: https://github.com/ITLusions/ITL.ControlPlane.Attestation/releases/tag/cli-v0.1.0

"""OIDC JWT validation against a Keycloak (or any RFC-8414-compliant) issuer.

Usage
-----
The module exposes a single function ``validate_operator_token(token)`` that:

1. Fetches (and caches) the OIDC discovery document from
   ``{ITL_OIDC_ISSUER}/.well-known/openid-configuration``.
2. Fetches (and caches) the JWKS from the ``jwks_uri`` found in that document.
3. Verifies the JWT signature, issuer, audience, and expiry using PyJWT.
4. Checks that the token carries the required operator role (see below).
5. Returns the ``preferred_username`` claim (falling back to ``sub``) as the
   canonical operator identity string.

Configuration
-------------
ITL_OIDC_ISSUER        — full issuer URL, e.g. https://sts.itlusions.com/realms/itl
ITL_OIDC_AUDIENCE      — expected ``aud`` claim (default: "attestation-service")
ITL_OIDC_OPERATOR_ROLE — Keycloak realm-role that grants operator access
                          (default: "attestation-operator").  Set to "" to skip
                          role enforcement (not recommended for production).
ITL_OIDC_ENABLED       — set to "false" to disable OIDC (default: true when issuer is set)

Role check
----------
Keycloak embeds realm roles in the ``realm_access.roles`` claim and client roles
in ``resource_access.<client_id>.roles``.  We check both locations.  Any token
that does *not* carry ``ITL_OIDC_OPERATOR_ROLE`` is rejected with a 403.

Caching
-------
The JWKS is cached in-process for ``_JWKS_CACHE_TTL`` seconds (default 300 s).
A threading.Lock ensures safe concurrent refreshes.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)

_JWKS_CACHE_TTL = 300  # seconds

# Module-level singletons — initialised lazily on first use.
_jwks_client: PyJWKClient | None = None
_discovery:   dict[str, Any]     = {}
_lock = threading.Lock()
_last_init: float = 0.0


def _get_oidc_settings() -> tuple[str, str, str, bool]:
    """Return (issuer, audience, operator_role, enabled) from the application config."""
    from ..core.config import get_settings
    s = get_settings()
    return s.oidc_issuer, s.oidc_audience, s.oidc_operator_role, s.oidc_enabled


def _discover(issuer: str) -> dict[str, Any]:
    """Fetch the OIDC discovery document (RFC 8414)."""
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _ensure_jwks_client(issuer: str) -> PyJWKClient:
    """Return a (cached) PyJWKClient, refreshing if the TTL has elapsed."""
    global _jwks_client, _discovery, _last_init

    now = time.monotonic()
    if _jwks_client is not None and (now - _last_init) < _JWKS_CACHE_TTL:
        return _jwks_client

    with _lock:
        # Double-checked locking
        if _jwks_client is not None and (time.monotonic() - _last_init) < _JWKS_CACHE_TTL:
            return _jwks_client

        logger.info("Refreshing OIDC JWKS from issuer %s", issuer)
        try:
            _discovery = _discover(issuer)
            jwks_uri   = _discovery["jwks_uri"]
        except Exception as exc:
            raise RuntimeError(
                f"Cannot fetch OIDC discovery document from {issuer}: {exc}"
            ) from exc

        _jwks_client = PyJWKClient(jwks_uri, cache_keys=True)
        _last_init   = time.monotonic()
        return _jwks_client


def _extract_roles(payload: dict[str, Any]) -> set[str]:
    """Extract the union of realm-level and resource-level roles from a Keycloak JWT.

    Keycloak includes roles in two places:
      ``realm_access.roles``                    — realm-wide roles
      ``resource_access.<client_id>.roles``     — per-client roles
    We collect all of them so role checks work regardless of how the Keycloak
    client is configured.
    """
    roles: set[str] = set()

    # Realm roles
    realm_access = payload.get("realm_access", {})
    roles.update(realm_access.get("roles", []))

    # Per-client roles
    resource_access = payload.get("resource_access", {})
    for client_data in resource_access.values():
        roles.update(client_data.get("roles", []))

    return roles


def validate_operator_token(token: str) -> str:
    """Validate a Keycloak JWT Bearer token and return the operator identity.

    Returns
    -------
    str
        ``preferred_username`` if present in the token claims, otherwise ``sub``.

    Raises
    ------
    ValueError
        If OIDC is not configured, the token is invalid/expired, the
        issuer/audience does not match, or the token lacks the required
        operator role (``ITL_OIDC_OPERATOR_ROLE``).
    """
    issuer, audience, operator_role, enabled = _get_oidc_settings()

    if not enabled or not issuer:
        raise ValueError("OIDC is not configured (set ITL_OIDC_ISSUER)")

    try:
        client = _ensure_jwks_client(issuer)
        signing_key = client.get_signing_key_from_jwt(token)
    except (PyJWKClientError, RuntimeError) as exc:
        raise ValueError(f"Cannot resolve OIDC signing key: {exc}") from exc

    decode_options: dict[str, Any] = {"verify_exp": True, "verify_iss": True}
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
        "issuer": issuer,
        "options": decode_options,
    }
    if audience:
        decode_kwargs["audience"] = audience
    else:
        decode_options["verify_aud"] = False

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            **decode_kwargs,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("OIDC token has expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise ValueError(f"OIDC token issuer mismatch (expected {issuer!r})") from exc
    except jwt.InvalidAudienceError as exc:
        raise ValueError(f"OIDC token audience mismatch (expected {audience!r})") from exc
    except jwt.PyJWTError as exc:
        raise ValueError(f"OIDC token validation failed: {exc}") from exc

    # Role enforcement — reject tokens without the required operator role
    if operator_role:
        token_roles = _extract_roles(payload)
        if operator_role not in token_roles:
            raise ValueError(
                f"OIDC token does not carry the required role '{operator_role}'. "
                f"Assign this role to the operator in Keycloak."
            )

    identity: str = payload.get("preferred_username") or payload.get("sub") or ""
    if not identity:
        raise ValueError("OIDC token contains neither preferred_username nor sub")

    logger.debug("OIDC token validated — operator=%s roles=%s", identity, _extract_roles(payload))
    return identity


def reset_jwks_cache() -> None:
    """Reset the JWKS cache.  Useful in tests or after a key rotation."""
    global _jwks_client, _discovery, _last_init
    with _lock:
        _jwks_client = None
        _discovery   = {}
        _last_init   = 0.0


"""FastAPI dependencies shared across all routes."""

from __future__ import annotations

import hmac
import logging
from functools import lru_cache
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, create_engine

from .config import get_settings
from ..repositories.machine_repo import SqlMachineRepository
from ..repositories.operator_repo import AuditRepository, ApprovalRepository, OperatorRepository

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_engine():
    return create_engine(
        get_settings().db_url,
        connect_args={"check_same_thread": False},
    )


def get_engine():
    return _get_engine()


def get_db():
    with Session(_get_engine()) as session:
        yield session


def get_machine_repo(db: Session = Depends(get_db)) -> SqlMachineRepository:
    return SqlMachineRepository(db)


def get_operator_repo(db: Session = Depends(get_db)) -> OperatorRepository:
    return OperatorRepository(db)


def get_audit_repo(db: Session = Depends(get_db)) -> AuditRepository:
    return AuditRepository(db)


def get_approval_repo(db: Session = Depends(get_db)) -> ApprovalRepository:
    return ApprovalRepository(db)


def resolve_operator(request: Request) -> str:
    """Resolve and authenticate the calling operator.

    Authentication is attempted in the following order:

    1. **OIDC JWT** — ``Authorization: Bearer <jwt>`` where the token is a
       Keycloak-issued JWT (validated against ``ITL_OIDC_ISSUER``).
       Returns ``preferred_username`` (or ``sub``) from the token claims.

    2. **mTLS client cert** — ``X-Client-Cert`` header containing the
       URL-encoded PEM of a client certificate issued by the Enrollment CA
       with ``OU=operator``.  This is typically injected by an nginx reverse
       proxy that terminates TLS and forwards the verified cert.
       Returns the cert's ``CN`` value.

    3. **Break-glass Bearer token** — ``Authorization: Bearer <ITL_ADMIN_TOKEN>``.
       Returns the sentinel string ``"SYSTEM"``.  All actions performed under
       this identity are logged with ``operator_cn=SYSTEM``.

    Raises HTTP 403 if none of the above succeeds.
    """
    settings = get_settings()
    auth = request.headers.get("Authorization", "")
    bearer_token = auth[7:] if auth.startswith("Bearer ") else ""

    # ------------------------------------------------------------------
    # 1. OIDC JWT (Keycloak at sts.itlusions.com)
    # ------------------------------------------------------------------
    if bearer_token and settings.oidc_enabled and settings.oidc_issuer:
        # Only attempt OIDC when the token is NOT the admin break-glass token.
        # This avoids a round-trip to Keycloak on every break-glass call.
        is_admin_token = (
            bool(settings.admin_token)
            and hmac.compare_digest(bearer_token, settings.admin_token)
        )
        if not is_admin_token:
            from ..pki.oidc import validate_operator_token
            try:
                return validate_operator_token(bearer_token)
            except ValueError as exc:
                logger.debug("OIDC validation failed: %s", exc)
                raise HTTPException(403, f"OIDC token rejected: {exc}") from exc

    # ------------------------------------------------------------------
    # 2. mTLS client cert forwarded by nginx as X-Client-Cert (URL-encoded PEM)
    # ------------------------------------------------------------------
    cert_header = request.headers.get("X-Client-Cert", "")
    if cert_header:
        cert_pem = unquote(cert_header)
        try:
            from ..pki.enrollment_ca import verify_enrollment_cert
            claims = verify_enrollment_cert(cert_pem)
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(403, f"Invalid operator client certificate: {exc}") from exc

        if claims.get("role") != "operator":
            raise HTTPException(
                403,
                "Client certificate OU must be 'operator' — "
                "use POST /api/v1/operators/{id}/issue-cert to obtain one",
            )
        return claims["machine_id"]  # CN holds the operator name

    # ------------------------------------------------------------------
    # 3. Break-glass shared admin token
    # ------------------------------------------------------------------
    if bearer_token and settings.admin_token:
        if hmac.compare_digest(bearer_token, settings.admin_token):
            logger.warning(
                "Break-glass admin token used from %s — action logged as SYSTEM",
                request.client.host if request.client else "unknown",
            )
            return "SYSTEM"

    raise HTTPException(
        403,
        "Operator authentication required. Provide one of: "
        "a Keycloak JWT Bearer token, "
        "an X-Client-Cert mTLS header, "
        "or the ITL_ADMIN_TOKEN Bearer token (break-glass).",
    )


def require_admin(request: Request) -> None:
    """Legacy bearer-token check kept for backward compatibility.

    New code should use ``resolve_operator`` which also supports OIDC and mTLS.
    """
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(503, "Admin token not configured — set ITL_ADMIN_TOKEN")
    auth  = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    # CRIT-04: constant-time comparison prevents timing side-channel leakage
    if not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(403, "Invalid or missing admin token")

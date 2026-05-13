"""FastAPI dependencies shared across all routes."""

from __future__ import annotations

import hmac
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, create_engine

from .config import get_settings
from ..repositories.machine_repo import SqlMachineRepository


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


def require_admin(request: Request) -> None:
    """Simple bearer-token check for admin endpoints."""
    settings = get_settings()
    if not settings.admin_token:
        raise HTTPException(503, "Admin token not configured — set ITL_ADMIN_TOKEN")
    auth  = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    # CRIT-04: constant-time comparison prevents timing side-channel leakage
    if not hmac.compare_digest(token, settings.admin_token):
        raise HTTPException(403, "Invalid or missing admin token")

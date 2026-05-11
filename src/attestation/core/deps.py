"""FastAPI dependencies shared across all routes."""

from __future__ import annotations

from fastapi import HTTPException, Request
from sqlmodel import Session, create_engine

from .config import settings

_engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},
)


def get_engine():
    return _engine


def get_db():
    with Session(_engine) as session:
        yield session


def require_admin(request: Request) -> None:
    """Simple bearer-token check for admin endpoints."""
    if not settings.admin_token:
        raise HTTPException(503, "Admin token not configured — set ITL_ADMIN_TOKEN")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.admin_token:
        raise HTTPException(403, "Invalid or missing admin token")

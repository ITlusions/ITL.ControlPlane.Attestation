"""Routes for MachineConfig delivery."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlmodel import Session

from ..core.deps import get_db
from ..handlers.config_delivery import ConfigDeliveryHandler

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config_by_mac(mac: str, db: Session = Depends(get_db)) -> Response:
    """Generic ISO config endpoint — resolves MachineConfig by MAC address."""
    return ConfigDeliveryHandler(db).get_config_by_mac(mac)


@router.get("/config/{token}")
def get_config(token: str, db: Session = Depends(get_db)) -> Response:
    """One-time Talos MachineConfig endpoint keyed on a single-use token."""
    return ConfigDeliveryHandler(db).get_config_by_token(token)

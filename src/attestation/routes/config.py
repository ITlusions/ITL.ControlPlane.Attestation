"""Routes for MachineConfig delivery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response

from ..core.deps import get_machine_repo
from ..handlers.config_delivery import ConfigDeliveryHandler
from ..repositories.machine_repo import SqlMachineRepository

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config_by_mac(
    request: Request,
    mac: str,
    accept: str = Header(default="", alias="Accept"),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
) -> Response:
    """Generic ISO config endpoint — resolves MachineConfig by MAC address."""
    client_ip = request.client.host if request.client else ""
    return ConfigDeliveryHandler(machine_repo).get_config_by_mac(mac, accept, client_ip)


@router.get("/config/{token}")
def get_config(
    request: Request,
    token: str,
    accept: str = Header(default="", alias="Accept"),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
) -> Response:
    """One-time Talos MachineConfig endpoint keyed on a single-use token."""
    client_ip = request.client.host if request.client else ""
    return ConfigDeliveryHandler(machine_repo).get_config_by_token(token, accept, client_ip)

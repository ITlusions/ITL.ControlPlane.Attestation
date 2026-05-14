"""Routes for MachineConfig delivery."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response

from ..core.deps import get_machine_repo
from ..handlers.config_delivery import ConfigDeliveryHandler
from ..repositories.machine_repo import SqlMachineRepository

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config_by_mac(
    mac: str,
    accept: str = Header(default="", alias="Accept"),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
) -> Response:
    """Generic ISO config endpoint — resolves MachineConfig by MAC address.

    Set ``Accept: application/vnd.itl.config.encrypted+json`` to receive an
    EK-bound AES-256-GCM encrypted envelope instead of plaintext YAML.
    """
    return ConfigDeliveryHandler(machine_repo).get_config_by_mac(mac, accept)


@router.get("/config/{token}")
def get_config(
    token: str,
    accept: str = Header(default="", alias="Accept"),
    machine_repo: SqlMachineRepository = Depends(get_machine_repo),
) -> Response:
    """One-time Talos MachineConfig endpoint keyed on a single-use token.

    Set ``Accept: application/vnd.itl.config.encrypted+json`` to receive an
    EK-bound AES-256-GCM encrypted envelope instead of plaintext YAML.
    """
    return ConfigDeliveryHandler(machine_repo).get_config_by_token(token, accept)

"""Config delivery handler — one-time token and MAC-based MachineConfig endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import Response

from ..core.config import get_settings
from ..talos.config_generator import generate_machine_config, generate_pending_config
from ..models.machine import MachineStatus
from ..repositories.machine_repo import SqlMachineRepository

logger = logging.getLogger(__name__)


class ConfigDeliveryHandler:
    """Handles GET /api/v1/config and GET /api/v1/config/{token}."""

    def __init__(self, machine_repo: SqlMachineRepository) -> None:
        self.machine_repo = machine_repo

    def get_config_by_mac(self, mac: str) -> Response:
        """Resolve MachineConfig by MAC address (generic ISO boot flow).

        Security model: MAC is a routing key only — TPM attestation is the real
        auth gate.  Only attested machines receive the full MachineConfig; all
        others get a safe pending config with no cluster secrets.
        """
        mac_normalised = mac.strip().lower().replace("-", ":")

        machine = self.machine_repo.get_by_mac(mac_normalised)

        if not machine:
            logger.warning(
                "Config request from unknown MAC %s — returning pending config", mac_normalised
            )
            return Response(
                content=generate_pending_config(get_settings().service_base_url),
                media_type="text/plain",
            )

        if machine.status in (
            MachineStatus.pending_approval,
            MachineStatus.registered,
            MachineStatus.locked,
            MachineStatus.revoked,
            MachineStatus.rejected,
        ):
            logger.info(
                "Config request from %s machine %s (MAC %s) — returning pending config",
                machine.status.value, machine.machine_id, mac_normalised,
            )
            return Response(
                content=generate_pending_config(get_settings().service_base_url),
                media_type="text/plain",
            )

        logger.info(
            "Generic ISO config served: machine=%s role=%s MAC=%s",
            machine.machine_id, machine.role.value, mac_normalised,
        )

        try:
            config_yaml = generate_machine_config(
                role           = machine.role.value,
                machine_id     = machine.machine_id,
                ek_fingerprint = machine.ek_fingerprint,
                hostname       = machine.hostname,
                assigned_ip    = machine.assigned_ip,
            )
            return Response(content=config_yaml, media_type="application/yaml")
        except FileNotFoundError as exc:
            logger.error("Base config not found: %s", exc)
            raise HTTPException(
                503, "Base config not available — ensure CI configs are downloaded"
            ) from exc

    def get_config_by_token(self, token: str) -> Response:
        """One-time Talos MachineConfig endpoint keyed on a single-use token."""
        machine = self.machine_repo.get_by_config_token(token)

        if not machine:
            raise HTTPException(404, "Config token not found")

        if machine.token_consumed:
            logger.info(
                "Config re-fetch for machine %s (token already consumed)", machine.machine_id
            )
        else:
            machine.token_consumed = True
            self.machine_repo.save(machine)
            logger.info("Config token consumed for machine %s", machine.machine_id)

        if machine.status == MachineStatus.pending_approval:
            return Response(
                content=generate_pending_config(get_settings().service_base_url),
                media_type="text/plain",
            )

        try:
            config_yaml = generate_machine_config(
                role           = machine.role.value,
                machine_id     = machine.machine_id,
                ek_fingerprint = machine.ek_fingerprint,
                hostname       = machine.hostname,
                assigned_ip    = machine.assigned_ip,
            )
            return Response(content=config_yaml, media_type="application/yaml")
        except FileNotFoundError as exc:
            logger.error("Base config not found: %s", exc)
            raise HTTPException(
                503, "Base config not available — ensure CI configs are downloaded"
            ) from exc

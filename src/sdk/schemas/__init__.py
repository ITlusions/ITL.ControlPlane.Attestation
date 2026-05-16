"""Shared Pydantic response schemas for the ITL Attestation platform.

These schemas form part of the public SDK contract and are consumed by both
the Attestation Service and external integrations such as the Pulumi provider.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves this at runtime
from typing import Optional

from pydantic import BaseModel


class RegisterResponse(BaseModel):
    """Response returned when a machine is registered via POST /api/v1/register."""

    machine_id:   str
    role:         str
    status:       str
    iso_url:      str
    config_token: str
    config_url:   str
    message:      str


class MachineDetail(BaseModel):
    """Full machine record returned by GET /api/v1/machines/{machine_id}."""

    machine_id:     str
    ek_fingerprint: str
    hw_uuid:        str
    hw_mac:         str
    hw_serial:      str
    hw_product:     str
    role:           str
    status:         str
    hostname:       str | None
    assigned_ip:    str | None
    registered_at:  datetime
    attested_at:    datetime | None
    locked_at:      datetime | None
    revoked_at:     datetime | None
    wipe_pending:   bool

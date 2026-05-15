"""Pulumi dynamic ResourceProvider implementations.

Each class maps Pulumi lifecycle operations (create / read / delete) to the
corresponding Attestation REST API calls, using the service's own Pydantic
request/response schemas as the contract.
"""

from __future__ import annotations

from typing import Any

from pulumi import dynamic

from attestation.schemas.requests import ApproveRequest, RegisterRequest, RevokeRequest
from ._client import AttestationClient, AttestationApiError


def _client(props: dict[str, Any]) -> AttestationClient:
    return AttestationClient(endpoint=props["endpoint"], token=props["token"])


# ──────────────────────────────────────────────────────────────────────────── #
# RegisteredMachine provider                                                    #
# ──────────────────────────────────────────────────────────────────────────── #


class _RegisteredMachineProvider(dynamic.ResourceProvider):
    """Lifecycle provider for a machine registered via the USB-agent flow.

    create  → POST /api/v1/register
    read    → GET  /api/v1/machines/{machine_id}
    delete  → POST /api/v1/machines/{machine_id}/revoke
    """

    def create(self, props: dict[str, Any]) -> dynamic.CreateResult:
        client = _client(props)
        resp = client.register(
            ek_fingerprint=props["ek_fingerprint"],
            ek_cert_pem=props["ek_cert_pem"],
            ek_source=props.get("ek_source", "cert"),
            hw_uuid=props.get("hw_uuid", "unknown"),
            hw_mac=props.get("hw_mac", "unknown"),
            hw_serial=props.get("hw_serial", "unknown"),
            hw_product=props.get("hw_product", "unknown"),
            desired_role=props.get("desired_role"),
        )
        machine_id: str = resp["machine_id"]
        return dynamic.CreateResult(
            id_=machine_id,
            outs={
                **props,
                "machine_id": machine_id,
                "role": resp.get("role", ""),
                "status": resp.get("status", ""),
                "iso_url": resp.get("iso_url", ""),
                "config_token": resp.get("config_token", ""),
                "config_url": resp.get("config_url", ""),
                "message": resp.get("message", ""),
            },
        )

    def read(self, id_: str, props: dict[str, Any]) -> dynamic.ReadResult:
        try:
            machine = _client(props).get_machine(id_)
            return dynamic.ReadResult(
                id_=id_,
                outs={
                    **props,
                    "machine_id": machine.machine_id,
                    "role":       machine.role,
                    "status":     machine.status,
                },
            )
        except AttestationApiError as exc:
            if exc.status == 404:
                return dynamic.ReadResult(id_=id_, outs={})
            raise

    def delete(self, id_: str, props: dict[str, Any]) -> None:
        try:
            _client(props).revoke_machine(id_, RevokeRequest(reason="Pulumi resource deleted"))
        except AttestationApiError as exc:
            if exc.status != 404:
                raise


# ──────────────────────────────────────────────────────────────────────────── #
# MachineApproval provider                                                      #
# ──────────────────────────────────────────────────────────────────────────── #


class _MachineApprovalProvider(dynamic.ResourceProvider):
    """Lifecycle provider for approving a pending machine.

    create  → POST /api/v1/machines/{machine_id}/approve
    read    → GET  /api/v1/machines/{machine_id}  (reflects current state)
    delete  → POST /api/v1/machines/{machine_id}/revoke  (or no-op if keep_on_delete=True)
    """

    def create(self, props: dict[str, Any]) -> dynamic.CreateResult:
        client = _client(props)
        req = ApproveRequest(
            role=props["role"],
            hostname=props.get("hostname"),
            assigned_ip=props.get("assigned_ip"),
        )
        resp = client.approve_machine(machine_id=props["machine_id"], req=req)
        return dynamic.CreateResult(
            id_=props["machine_id"],
            outs={
                **props,
                "status":  resp.status,
                "message": "",
            },
        )

    def read(self, id_: str, props: dict[str, Any]) -> dynamic.ReadResult:
        try:
            machine = _client(props).get_machine(id_)
            return dynamic.ReadResult(
                id_=id_,
                outs={**props, "status": machine.status},
            )
        except AttestationApiError as exc:
            if exc.status == 404:
                return dynamic.ReadResult(id_=id_, outs={})
            raise

    def delete(self, id_: str, props: dict[str, Any]) -> None:
        if props.get("keep_on_delete", False):
            return
        try:
            _client(props).revoke_machine(id_, RevokeRequest(reason="Pulumi approval resource deleted"))
        except AttestationApiError as exc:
            if exc.status != 404:
                raise

"""Pulumi resource classes for the ITL Attestation Service.

Usage example
-------------

.. code-block:: python

    import pulumi
    from pulumi_provider import RegisteredMachine, MachineApproval

    config = pulumi.Config()

    machine = RegisteredMachine(
        "worker-01",
        endpoint="https://attestation.itlusions.com",
        token=config.require_secret("attestation_token"),
        ek_fingerprint="<sha384-hex>",
        ek_cert_pem=open("ek.pem").read(),
        hw_serial="SN-123456",
        desired_role="worker-app",
    )

    approval = MachineApproval(
        "worker-01-approval",
        endpoint="https://attestation.itlusions.com",
        token=config.require_secret("attestation_token"),
        machine_id=machine.machine_id,
        role="worker-app",
        hostname="worker-01.cluster.local",
        pulumi.ResourceOptions(depends_on=[machine]),
    )

    pulumi.export("machine_id", machine.machine_id)
    pulumi.export("config_url", machine.config_url)
"""

from __future__ import annotations

from typing import Optional, Union

import pulumi
from pulumi import dynamic, Input, Output, ResourceOptions

from attestation.models.machine import NodeRole, MachineStatus
from .provider import _RegisteredMachineProvider, _MachineApprovalProvider


class RegisteredMachine(dynamic.Resource):
    """Pulumi resource that registers a machine with the Attestation Service.

    On ``pulumi up``  → POST /api/v1/register
    On ``pulumi refresh`` → GET  /api/v1/machines/{id}
    On ``pulumi destroy`` → POST /api/v1/machines/{id}/revoke
    """

    #: Computed outputs
    machine_id:   Output[str]
    role:         Output[NodeRole]
    status:       Output[MachineStatus]
    iso_url:      Output[str]
    config_token: Output[str]
    config_url:   Output[str]
    message:      Output[str]

    def __init__(
        self,
        name: str,
        endpoint: Input[str],
        token: Input[str],
        ek_fingerprint: Input[str],
        ek_cert_pem: Input[str],
        ek_source: Input[str] = "cert",
        hw_uuid: Input[str] = "unknown",
        hw_mac: Input[str] = "unknown",
        hw_serial: Input[str] = "unknown",
        hw_product: Input[str] = "unknown",
        desired_role: Optional[Input[Union[NodeRole, str]]] = None,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        props: dict = {
            "endpoint": endpoint,
            "token": token,
            "ek_fingerprint": ek_fingerprint,
            "ek_cert_pem": ek_cert_pem,
            "ek_source": ek_source,
            "hw_uuid": hw_uuid,
            "hw_mac": hw_mac,
            "hw_serial": hw_serial,
            "hw_product": hw_product,
            "desired_role": desired_role,
            # Output placeholders — populated by the provider on create/read.
            "machine_id": None,
            "role": None,
            "status": None,
            "iso_url": None,
            "config_token": None,
            "config_url": None,
            "message": None,
        }
        # Mark secrets so Pulumi redacts them in state and logs.
        merged_opts = ResourceOptions.merge(
            ResourceOptions(additional_secret_outputs=["token", "ek_cert_pem", "config_token"]),
            opts,
        )
        super().__init__(_RegisteredMachineProvider(), name, props, merged_opts)


class MachineApproval(dynamic.Resource):
    """Pulumi resource that approves a pending machine registration.

    On ``pulumi up``      → POST /api/v1/machines/{machine_id}/approve
    On ``pulumi refresh`` → GET  /api/v1/machines/{machine_id}
    On ``pulumi destroy`` → POST /api/v1/machines/{machine_id}/revoke
                            (skipped when ``keep_on_delete=True``)
    """

    #: Computed outputs
    status:  Output[MachineStatus]
    message: Output[str]

    def __init__(
        self,
        name: str,
        endpoint: Input[str],
        token: Input[str],
        machine_id: Input[str],
        role: Input[Union[NodeRole, str]],
        hostname: Optional[Input[str]] = None,
        assigned_ip: Optional[Input[str]] = None,
        keep_on_delete: bool = False,
        opts: Optional[ResourceOptions] = None,
    ) -> None:
        props: dict = {
            "endpoint": endpoint,
            "token": token,
            "machine_id": machine_id,
            "role": role,
            "hostname": hostname,
            "assigned_ip": assigned_ip,
            "keep_on_delete": keep_on_delete,
            # Output placeholders.
            "status": None,
            "message": None,
        }
        merged_opts = ResourceOptions.merge(
            ResourceOptions(additional_secret_outputs=["token"]),
            opts,
        )
        super().__init__(_MachineApprovalProvider(), name, props, merged_opts)

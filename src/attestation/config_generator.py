"""Machine-specific Talos machineconfig generator.

Reads the role template (a pre-generated machineconfig YAML that the CI
workflow published to the GitHub Release) and applies machine-specific
overrides:
  - hostname
  - network interface static IP (if assigned_ip is set)
  - additional node labels (tpm EK fingerprint, machine_id)

For zero-touch provisioning this generator returns the *full* MachineConfig
that Talos should fetch — the role base config merged with machine overrides.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_ROLE_CONFIG_MAP = {
    "controlplane": "controlplane-final.yaml",
    "worker-infra": "worker-infra-final.yaml",
    "worker-app":   "worker-app-final.yaml",
}

CONFIG_CACHE_DIR = os.environ.get("ITL_CONFIG_CACHE_DIR", "/var/lib/itl-reg/configs")
INSTALLER_IMAGE  = os.environ.get("ITL_INSTALLER_IMAGE",  "ghcr.io/itlusions/itl-talos-installer:latest")


def _load_base_config(role: str) -> dict:
    filename = _ROLE_CONFIG_MAP.get(role)
    if not filename:
        raise ValueError(f"Unknown role: {role}")

    path = os.path.join(CONFIG_CACHE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Base config not found at {path}. "
            "Ensure the Attestation Service has downloaded configs from the GitHub Release."
        )

    with open(path) as f:
        return yaml.safe_load(f)


def generate_machine_config(
    role: str,
    machine_id: str,
    ek_fingerprint: str,
    hostname: Optional[str] = None,
    assigned_ip: Optional[str] = None,
    enrollment_cert_pem: Optional[str] = None,
    enrollment_key_pem: Optional[str] = None,
) -> str:
    """Generate a machine-specific Talos MachineConfig YAML.

    Starts from the role base config and merges:
    - machine.network.hostname
    - machine.network.interfaces[0].addresses (if assigned_ip provided)
    - machine.nodeLabels for itl.io/machine-id and itl.io/tpm-ek
    - machine.nodeAnnotations for itl.io/attested: "true"
    - machine.files for enrollment cert + key (offline bundle only)
    """
    config = _load_base_config(role)

    machine = config.setdefault("machine", {})

    install = machine.setdefault("install", {})
    install.setdefault("image", INSTALLER_IMAGE)

    if hostname:
        network = machine.setdefault("network", {})
        network["hostname"] = hostname
        logger.info("Config: hostname=%s", hostname)

    if assigned_ip:
        network = machine.setdefault("network", {})
        interfaces = network.setdefault("interfaces", [])
        if not interfaces:
            interfaces.append({
                "interface": "eth0",
                "addresses": [assigned_ip],
                "routes": [],
            })
        else:
            interfaces[0].setdefault("addresses", [])
            if assigned_ip not in interfaces[0]["addresses"]:
                interfaces[0]["addresses"].append(assigned_ip)
        logger.info("Config: assigned_ip=%s", assigned_ip)

    node_labels = machine.setdefault("nodeLabels", {})
    node_labels["itl.io/machine-id"] = machine_id
    node_labels["itl.io/tpm-ek"]     = ek_fingerprint[:16]
    node_labels["itl.io/attested"]   = "true"

    node_annotations = machine.setdefault("nodeAnnotations", {})
    node_annotations["itl.io/tpm-ek-full"]  = ek_fingerprint
    node_annotations["itl.io/machine-id"]   = machine_id

    if enrollment_cert_pem or enrollment_key_pem:
        files = machine.setdefault("files", [])
        if enrollment_cert_pem:
            files.append({
                "path":        "/var/lib/itl-tpm/enrollment.crt",
                "permissions": 0o444,
                "op":          "create",
                "content":     enrollment_cert_pem,
            })
            logger.info("Config: embedding enrollment cert for machine %s", machine_id)
        if enrollment_key_pem:
            files.append({
                "path":        "/var/lib/itl-tpm/enrollment.key",
                "permissions": 0o400,
                "op":          "create",
                "content":     enrollment_key_pem,
            })
            logger.info("Config: embedding enrollment key for machine %s", machine_id)

    return yaml.dump(config, default_flow_style=False, allow_unicode=True)


def generate_pending_config(reg_url: str) -> str:
    """Returns a minimal bootstrapping MachineConfig for machines that booted
    without prior registration.  The node joins the cluster in a cordoned state.
    """
    config = {
        "version": "v1alpha1",
        "debug": False,
        "persist": True,
        "machine": {
            "type": "worker",
            "nodeLabels": {
                "itl.io/status":       "pending-approval",
                "itl.io/managed-by":   "talos",
                "itl.io/flavor":       "controlplane-stack",
            },
            "env": {
                "ITL_REG_URL": reg_url,
            },
        },
        "cluster": {
            "id":     "itl-cpstack-cluster",
            "secret": "",  # operator must fill this
        },
    }
    return yaml.dump(config, default_flow_style=False)

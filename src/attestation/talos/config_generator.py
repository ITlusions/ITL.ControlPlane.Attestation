"""Machine-specific Talos machineconfig generator.

Each cluster gets its own subdirectory under ``CONFIG_CACHE_DIR`` which is used
only as a temporary landing zone for ``talosctl gen config`` output.  As soon as
the three plaintext files are written, ``cluster_config_store`` seals them into
``extension_shared_secrets`` (AES-256-GCM) and wipes the plaintext files.

Storage layout (database):

    extension_shared_secrets.name = "talos-cluster-{cluster_id}-controlplane"
    extension_shared_secrets.name = "talos-cluster-{cluster_id}-worker"
    extension_shared_secrets.name = "talos-cluster-{cluster_id}-talosconfig"

Base configs are generated automatically when the first controlplane node of a
cluster fetches its config (zero-touch), or explicitly via
``POST /api/v1/clusters/{cluster_id}/bootstrap``.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Optional

import yaml

from .cluster_config_store import get_store

logger = logging.getLogger(__name__)

_ROLE_CONFIG_MAP = {
    "controlplane": "controlplane.yaml",
    "worker-infra": "worker.yaml",
    "worker-app":   "worker.yaml",
}

CONFIG_CACHE_DIR = os.environ.get("ITL_CONFIG_CACHE_DIR", "/var/lib/itl-reg/configs")
INSTALLER_IMAGE  = os.environ.get("ITL_INSTALLER_IMAGE",  "ghcr.io/itlusions/itl-talos-installer:latest")

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")


def _cluster_dir(cluster_id: str) -> str:
    """Return the config directory for *cluster_id*, validated."""
    if not _SAFE_ID.match(cluster_id):
        raise ValueError(
            f"cluster_id '{cluster_id}' is invalid — use lowercase alphanumeric + hyphens only"
        )
    return os.path.join(CONFIG_CACHE_DIR, cluster_id)


def _load_base_config(role: str, cluster_id: str = "default") -> dict:
    store = get_store()
    content = store.load_for_role(cluster_id, role)  # raises FileNotFoundError if missing
    return yaml.safe_load(content)


def base_configs_exist(cluster_id: str = "default") -> bool:
    """Return True if cluster configs are stored in the database for *cluster_id*."""
    return get_store().exists(cluster_id)


def list_clusters() -> list[str]:
    """Return all cluster IDs that have stored base configs."""
    return get_store().list_cluster_ids()


def generate_base_configs(
    endpoint: str,
    cluster_id: str = "default",
    cluster_name: Optional[str] = None,
) -> None:
    """Generate base Talos MachineConfig files for *cluster_id*.

    Writes ``controlplane.yaml``, ``worker.yaml``, and ``talosconfig`` to
    ``CONFIG_CACHE_DIR/<cluster_id>/``.  Idempotent.

    Args:
        endpoint:     Kubernetes API endpoint (e.g. ``https://10.0.0.1:6443``).
        cluster_id:   Cluster identifier — used as the storage subdirectory.
        cluster_name: Human-readable cluster name passed to talosctl.
                      Defaults to *cluster_id*.

    Raises:
        FileNotFoundError: ``talosctl`` binary not on PATH.
        RuntimeError:      ``talosctl gen config`` exited non-zero.
    """
    if base_configs_exist(cluster_id):
        logger.info("Base configs for cluster '%s' already present — skipping", cluster_id)
        return

    output_dir = _cluster_dir(cluster_id)
    os.makedirs(output_dir, exist_ok=True)

    name = cluster_name or cluster_id
    logger.info("Generating base configs: cluster_id=%s name=%s endpoint=%s", cluster_id, name, endpoint)

    result = subprocess.run(
        [
            "talosctl", "gen", "config",
            name,
            endpoint,
            "--output-dir", output_dir,
            "--force",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"talosctl gen config failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    # Store each file as an encrypted shared secret, then wipe the plaintext.
    store = get_store()
    _SLOTS = [
        ("controlplane.yaml", "controlplane"),
        ("worker.yaml",       "worker"),
        ("talosconfig",       "talosconfig"),
    ]
    for fname, slot in _SLOTS:
        fpath = os.path.join(output_dir, fname)
        if os.path.exists(fpath):
            store.store_from_file(cluster_id, slot, fpath)
            logger.debug("Stored cluster config secret: cluster=%s slot=%s", cluster_id, slot)
        else:
            logger.warning("Expected file not found after talosctl gen config: %s", fpath)

    # Remove temp directory if now empty
    try:
        if os.path.isdir(output_dir) and not os.listdir(output_dir):
            os.rmdir(output_dir)
    except OSError:
        pass

    logger.info("Cluster '%s' configs stored as shared secrets", cluster_id)


def generate_machine_config(
    role: str,
    machine_id: str,
    ek_fingerprint: str,
    cluster_id: str = "default",
    hostname: Optional[str] = None,
    assigned_ip: Optional[str] = None,
    enrollment_cert_pem: Optional[str] = None,
    enrollment_key_pem: Optional[str] = None,
) -> str:
    """Generate a machine-specific Talos MachineConfig YAML."""
    config = _load_base_config(role, cluster_id)

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

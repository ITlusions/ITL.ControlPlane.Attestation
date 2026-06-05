"""Cluster management endpoints — bootstrap, status, talosconfig retrieval."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from ..core.deps import resolve_operator
from ..talos.config_generator import (
    base_configs_exist,
    generate_base_configs,
    list_clusters,
)
from ..talos.cluster_config_store import get_store

router = APIRouter(prefix="/api/v1/clusters", tags=["clusters"])


class BootstrapRequest(BaseModel):
    endpoint: str    # e.g. https://10.0.0.1:6443 or https://vip.itlusions.com:6443
    cluster_name: str | None = None  # human-readable; defaults to cluster_id

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_https(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("endpoint must start with https://")
        return v


@router.get("")
def list_all_clusters(operator: str = Depends(resolve_operator)) -> list[dict]:
    """List all clusters that have generated base configs."""
    return [{"cluster_id": cid, "ready": True} for cid in list_clusters()]


@router.post("/{cluster_id}/bootstrap")
def bootstrap_cluster(
    cluster_id: str,
    body: BootstrapRequest,
    operator: str = Depends(resolve_operator),
) -> dict:
    """Pre-generate base Talos configs for *cluster_id*.

    Optional — configs are also auto-generated when the first controlplane node
    of the cluster fetches its config (zero-touch).  Use this endpoint to set a
    VIP or load-balancer address as the cluster endpoint instead of a node IP.

    Idempotent — returns ``{"generated": false}`` if configs already exist.
    """
    already_exists = base_configs_exist(cluster_id)

    if not already_exists:
        try:
            generate_base_configs(
                endpoint=body.endpoint,
                cluster_id=cluster_id,
                cluster_name=body.cluster_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=f"talosctl not found: {exc}")
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return {
        "cluster_id": cluster_id,
        "endpoint": body.endpoint,
        "generated": not already_exists,
        "ready": True,
    }


@router.get("/{cluster_id}/status")
def cluster_status(
    cluster_id: str,
    operator: str = Depends(resolve_operator),
) -> dict:
    """Check whether base configs have been generated for *cluster_id*."""
    return {
        "cluster_id": cluster_id,
        "ready": base_configs_exist(cluster_id),
    }


@router.get("/{cluster_id}/talosconfig")
def get_talosconfig(
    cluster_id: str,
    operator: str = Depends(resolve_operator),
) -> dict:
    """Download the talosconfig for *cluster_id*.

    The talosconfig grants full admin access to the cluster via talosctl.
    Store it securely — treat it like a root credential.
    """
    if not base_configs_exist(cluster_id):
        raise HTTPException(404, f"Cluster '{cluster_id}' has not been bootstrapped yet.")

    try:
        content = get_store().load(cluster_id, "talosconfig")
    except FileNotFoundError:
        raise HTTPException(404, f"talosconfig not found for cluster '{cluster_id}'.")
    except ValueError as exc:
        raise HTTPException(500, f"Failed to decrypt talosconfig: {exc}")

    return {"cluster_id": cluster_id, "talosconfig": content}


_VALID_SLOTS = {"controlplane", "worker", "talosconfig"}


@router.get("/{cluster_id}/configs/{slot}")
def get_cluster_config(
    cluster_id: str,
    slot: str,
    operator: str = Depends(resolve_operator),
) -> dict:
    """Retrieve a stored cluster config artifact.

    Valid *slot* values:

    - ``controlplane`` — controlplane.yaml (MachineConfig for control-plane nodes)
    - ``worker``       — worker.yaml (MachineConfig for worker nodes)
    - ``talosconfig``  — talosconfig (operator credential for talosctl)

    Returns ``{"cluster_id": ..., "slot": ..., "content": "<yaml string>"}``
    """
    if slot not in _VALID_SLOTS:
        raise HTTPException(400, f"Invalid slot '{slot}'. Must be one of: {', '.join(sorted(_VALID_SLOTS))}")

    if not base_configs_exist(cluster_id):
        raise HTTPException(404, f"Cluster '{cluster_id}' has not been bootstrapped yet.")

    try:
        content = get_store().load(cluster_id, slot)
    except FileNotFoundError:
        raise HTTPException(404, f"Config slot '{slot}' not found for cluster '{cluster_id}'.")
    except ValueError as exc:
        raise HTTPException(500, f"Failed to decrypt config: {exc}")

    return {"cluster_id": cluster_id, "slot": slot, "content": content}

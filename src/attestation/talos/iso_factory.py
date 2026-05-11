"""ISO URL resolution helpers.

Provides a static pre-built ISO URL (``ITL_ISO_URL``) or falls back to
dynamically building one via the Talos Image Factory.
"""

from __future__ import annotations

import logging

import httpx
import yaml
from fastapi import HTTPException

from ..core.config import settings

logger = logging.getLogger(__name__)


def build_factory_iso_url(config_url: str) -> str:
    """POST a schematic to the Talos Image Factory and return an ISO download URL.

    Used as fallback when ``ITL_ISO_URL`` is not configured.  The schematic
    bakes ``talos.config=<config_url>`` into the ISO kernel args so that Talos
    fetches the MachineConfig automatically on first boot.

    Note: ITL custom extensions (itl-branding, itl-security, itl-tpm-register)
    cannot be included via the official factory — only Siderolabs-published
    extensions are supported here.
    """
    base_extensions = ["siderolabs/gvisor", "siderolabs/intel-ucode"]
    all_extensions = base_extensions + [
        e for e in settings.factory_extensions if e not in base_extensions
    ]
    schematic = {
        "customization": {
            "extraKernelArgs": [f"talos.config={config_url}"],
            "systemExtensions": {"officialExtensions": all_extensions},
        }
    }
    logger.info("Factory schematic extensions: %s", all_extensions)
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{settings.factory_url}/schematics",
                content=yaml.dump(schematic, default_flow_style=False),
                headers={"Content-Type": "text/yaml"},
            )
        resp.raise_for_status()
        schematic_id = resp.json()["id"]
    except httpx.HTTPError as exc:
        logger.error("Talos Image Factory unreachable: %s", exc)
        raise HTTPException(503, f"Talos Image Factory unavailable: {exc}") from exc
    except (KeyError, ValueError) as exc:
        logger.error("Unexpected factory response: %s", exc)
        raise HTTPException(502, "Unexpected response from Talos Image Factory") from exc

    iso_url = (
        f"{settings.factory_url}/image/{schematic_id}"
        f"/{settings.talos_version}/metal-amd64.iso"
    )
    logger.info("Factory schematic created: id=%s url=%s", schematic_id, iso_url)
    return iso_url


def get_itl_iso_url(config_url: str) -> str:
    """Return the ISO URL for a new machine registration.

    Priority:
      1. ``ITL_ISO_URL`` — the pre-built ITL HardenedOS ISO (GitHub Release
         asset).  All extensions are already baked in; no factory call needed.
      2. Talos Image Factory — builds a stock Talos ISO with
         ``talos.config=<config_url>`` in the kernel args.  Used when
         ``ITL_ISO_URL`` is not configured (dev / testing environments).
    """
    if settings.iso_url:
        return settings.iso_url
    logger.info("ITL_ISO_URL not set — falling back to Talos Image Factory")
    return build_factory_iso_url(config_url)

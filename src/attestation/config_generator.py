"""Re-export shim — actual implementation lives in talos/config_generator.py."""
from .talos.config_generator import (  # noqa: F401
    CONFIG_CACHE_DIR,
    INSTALLER_IMAGE,
    generate_machine_config,
    generate_pending_config,
)


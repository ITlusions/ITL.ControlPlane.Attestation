"""ITL Attestation CLI

Command-line interface for ITL Control Plane Machine Attestation platform.
Communicates with the attestation API service via REST endpoints with OIDC authentication.
"""

__version__ = "0.1.0"

__all__ = [
    "AttestationClient",
    "CliPlugin",
    "KeycloakClient",
    "OIDCToken",
    "TokenCache",
    "discover_and_register_plugins",
    "get_token",
    "__version__",
]

from .api_client import AttestationClient
from .auth import get_token
from .keycloak_client import KeycloakClient, OIDCToken
from .plugin import CliPlugin
from .plugins import discover_and_register_plugins
from .token_cache import TokenCache

"""ITL Attestation CLI

Command-line interface for ITL Control Plane Machine Attestation platform.
Communicates with the attestation API service via REST endpoints with OIDC authentication.
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AttestationClient",
    "KeycloakClient",
    "OIDCToken",
    "TokenCache",
]

from .api_client import AttestationClient
from .keycloak_client import KeycloakClient, OIDCToken
from .token_cache import TokenCache

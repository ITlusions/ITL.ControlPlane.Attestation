"""Authentication helpers for the attestation CLI.

Available to both built-in commands and third-party CLI plugins.
"""

from __future__ import annotations

import os
import sys

import click

from .token_cache import TokenCache

DEFAULT_REALM = os.getenv("KEYCLOAK_REALM", "itlusions")
DEFAULT_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "attestation-cli")


def get_token() -> str:
    """Return the current cached OIDC access token, or exit with a helpful message.

    Reads KEYCLOAK_REALM and KEYCLOAK_CLIENT_ID from the environment (with sane
    defaults) to locate the correct cache entry.

    Returns:
        Raw access token string.

    Raises:
        SystemExit: When no valid cached token exists.

    Example (inside a plugin command)::

        from cli.auth import get_token
        from cli.api_client import AttestationClient

        @mygroup.command("list")
        @click.pass_context
        def my_list(ctx: click.Context) -> None:
            token = get_token()
            with AttestationClient(ctx.obj["api_url"], token) as client:
                data = client.get("/api/v1/extensions/myext/items")
            click.echo(data)
    """
    realm = os.getenv("KEYCLOAK_REALM", DEFAULT_REALM)
    client_id = os.getenv("KEYCLOAK_CLIENT_ID", DEFAULT_CLIENT_ID)
    cache = TokenCache()
    token = cache.load(realm, client_id)

    if not token:
        click.echo("Not logged in. Run: attestation auth login")
        sys.exit(1)

    return token.access_token

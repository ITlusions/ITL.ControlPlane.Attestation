"""ITL Attestation CLI — Main entry point."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import click

from . import __version__
from .api_client import AttestationClient
from .keycloak_client import KeycloakClient
from .token_cache import TokenCache

# Environment variable defaults
DEFAULT_ATTESTATION_URL = os.getenv("ATTESTATION_API_URL", "http://localhost:9000")
DEFAULT_KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://sts.itlusions.com")
DEFAULT_REALM = os.getenv("KEYCLOAK_REALM", "itlusions")
DEFAULT_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "attestation-cli")


@click.group()
@click.version_option(version=__version__, prog_name="attestation")
@click.option(
    "--api-url",
    envvar="ATTESTATION_API_URL",
    default=DEFAULT_ATTESTATION_URL,
    help="Attestation API base URL",
)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="table",
    help="Output format",
)
@click.pass_context
def cli(ctx: click.Context, api_url: str, output: str) -> None:
    """ITL Attestation CLI — Machine attestation management."""
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["output"] = output


# ===== Authentication Commands =====


@cli.group()
def auth() -> None:
    """Authentication and token management."""
    pass


@auth.command("login")
@click.option(
    "--method",
    type=click.Choice(["interactive", "password", "device"], case_sensitive=False),
    default="interactive",
    help="Authentication method",
)
@click.option("--username", "-u", help="Username (for password method)")
@click.option("--password", "-p", help="Password (for password method)")
@click.option(
    "--keycloak-url",
    envvar="KEYCLOAK_URL",
    default=DEFAULT_KEYCLOAK_URL,
    help="Keycloak base URL",
)
@click.option(
    "--realm",
    envvar="KEYCLOAK_REALM",
    default=DEFAULT_REALM,
    help="Keycloak realm",
)
@click.option(
    "--client-id",
    envvar="KEYCLOAK_CLIENT_ID",
    default=DEFAULT_CLIENT_ID,
    help="OIDC client ID",
)
def auth_login(
    method: str,
    username: str | None,
    password: str | None,
    keycloak_url: str,
    realm: str,
    client_id: str,
) -> None:
    """Login to Keycloak and cache token."""
    kc = KeycloakClient(keycloak_url, realm, client_id)
    cache = TokenCache()

    try:
        if method == "interactive":
            click.echo("🔐 Starting interactive browser login...")
            token = kc.login_interactive()
        elif method == "password":
            if not username:
                username = click.prompt("Username", type=str)
            if not password:
                password = click.prompt("Password", type=str, hide_input=True)
            click.echo(f"🔐 Logging in as {username}...")
            token = kc.login_password(username, password)
        elif method == "device":
            token = kc.login_device_code()
        else:
            raise click.ClickException(f"Unknown method: {method}")

        # Cache token
        cache.save(token, realm, client_id, username)
        click.echo(f"✅ Login successful! Token cached.")
        click.echo(f"   Expires: {token.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    except Exception as e:
        raise click.ClickException(f"Login failed: {e}")


@auth.command("logout")
@click.option(
    "--realm",
    envvar="KEYCLOAK_REALM",
    default=DEFAULT_REALM,
    help="Keycloak realm",
)
@click.option(
    "--client-id",
    envvar="KEYCLOAK_CLIENT_ID",
    default=DEFAULT_CLIENT_ID,
    help="OIDC client ID",
)
@click.option("--username", "-u", help="Username (for user-specific cache)")
def auth_logout(realm: str, client_id: str, username: str | None) -> None:
    """Logout and remove cached token."""
    cache = TokenCache()
    if cache.delete(realm, client_id, username):
        click.echo("✅ Logged out successfully. Token removed from cache.")
    else:
        click.echo("❌ No cached token found.")


@auth.command("whoami")
@click.option(
    "--realm",
    envvar="KEYCLOAK_REALM",
    default=DEFAULT_REALM,
    help="Keycloak realm",
)
@click.option(
    "--client-id",
    envvar="KEYCLOAK_CLIENT_ID",
    default=DEFAULT_CLIENT_ID,
    help="OIDC client ID",
)
def auth_whoami(realm: str, client_id: str) -> None:
    """Show current user from cached token."""
    cache = TokenCache()
    token = cache.load(realm, client_id)

    if not token:
        click.echo("❌ Not logged in. Run: attestation auth login")
        sys.exit(1)

    # Decode JWT (basic, no validation)
    import base64

    try:
        payload = token.access_token.split(".")[1]
        # Add padding if needed
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))
        click.echo(f"👤 User: {decoded.get('preferred_username', 'unknown')}")
        click.echo(f"📧 Email: {decoded.get('email', 'N/A')}")
        click.echo(f"🏢 Realm: {realm}")
        click.echo(f"⏰ Expires: {token.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    except Exception as e:
        click.echo(f"❌ Failed to decode token: {e}")
        sys.exit(1)


@auth.command("cache-list")
def auth_cache_list() -> None:
    """List all cached tokens."""
    cache = TokenCache()
    tokens = cache.list_cached_tokens()

    if not tokens:
        click.echo("No cached tokens found.")
        return

    click.echo(f"📋 Cached tokens ({len(tokens)}):\n")
    for t in tokens:
        status = "❌ EXPIRED" if t["is_expired"] else "✅ Valid"
        username = t["username"] or "N/A"
        click.echo(f"  {status}")
        click.echo(f"    Realm: {t['realm']}")
        click.echo(f"    Client: {t['client_id']}")
        click.echo(f"    User: {username}")
        click.echo(f"    Expires: {t['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        click.echo()


@auth.command("clear-cache")
@click.confirmation_option(prompt="Delete all cached tokens?")
def auth_clear_cache() -> None:
    """Delete all cached tokens."""
    cache = TokenCache()
    count = cache.clear_all()
    click.echo(f"✅ Deleted {count} cached token(s).")


# ===== Machine Commands =====


@cli.group()
def machine() -> None:
    """Machine management."""
    pass


@machine.command("list")
@click.option("--status", help="Filter by status")
@click.option("--role", help="Filter by role")
@click.pass_context
def machine_list(ctx: click.Context, status: str | None, role: str | None) -> None:
    """List machines."""
    api_url = ctx.obj["api_url"]
    output = ctx.obj["output"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machines = client.list_machines(status=status, role=role)

    if output == "json":
        click.echo(json.dumps(machines, indent=2))
    else:
        if not machines:
            click.echo("No machines found.")
            return

        click.echo(f"\n📦 Machines ({len(machines)}):\n")
        for m in machines:
            status_icon = {
                "attested": "✅",
                "registered": "🔷",
                "pending_approval": "⏳",
                "locked": "🔒",
                "revoked": "❌",
            }.get(m.get("status", ""), "❓")

            click.echo(f"  {status_icon} {m['hostname']} ({m['machine_id'][:8]}...)")
            click.echo(f"     Role: {m.get('role', 'N/A')}")
            click.echo(f"     Status: {m.get('status', 'N/A')}")
            click.echo(f"     IP: {m.get('assigned_ip', 'N/A')}")
            click.echo()


@machine.command("get")
@click.argument("machine_id")
@click.pass_context
def machine_get(ctx: click.Context, machine_id: str) -> None:
    """Get machine details."""
    api_url = ctx.obj["api_url"]
    output = ctx.obj["output"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machine = client.get_machine(machine_id)

    if output == "json":
        click.echo(json.dumps(machine, indent=2))
    else:
        click.echo(f"\n📦 Machine: {machine['hostname']}")
        click.echo(f"   ID: {machine['machine_id']}")
        click.echo(f"   Role: {machine.get('role', 'N/A')}")
        click.echo(f"   Status: {machine.get('status', 'N/A')}")
        click.echo(f"   IP: {machine.get('assigned_ip', 'N/A')}")
        click.echo(f"   EK Fingerprint: {machine.get('ek_fingerprint', 'N/A')}")
        click.echo(f"   Registered: {machine.get('registered_at', 'N/A')}")
        click.echo(f"   Attested: {machine.get('attested_at', 'N/A')}")


@machine.command("approve")
@click.argument("machine_id")
@click.option("--reason", "-r", help="Approval reason")
@click.pass_context
def machine_approve(ctx: click.Context, machine_id: str, reason: str | None) -> None:
    """Approve a pending machine."""
    api_url = ctx.obj["api_url"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machine = client.approve_machine(machine_id, reason)

    click.echo(f"✅ Approved: {machine['hostname']} ({machine['machine_id'][:8]}...)")


@machine.command("lock")
@click.argument("machine_id")
@click.option("--reason", "-r", help="Lock reason")
@click.pass_context
def machine_lock(ctx: click.Context, machine_id: str, reason: str | None) -> None:
    """Lock a machine."""
    api_url = ctx.obj["api_url"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machine = client.lock_machine(machine_id, reason)

    click.echo(f"🔒 Locked: {machine['hostname']} ({machine['machine_id'][:8]}...)")


@machine.command("unlock")
@click.argument("machine_id")
@click.option("--reason", "-r", help="Unlock reason")
@click.pass_context
def machine_unlock(ctx: click.Context, machine_id: str, reason: str | None) -> None:
    """Unlock a locked machine."""
    api_url = ctx.obj["api_url"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machine = client.unlock_machine(machine_id, reason)

    click.echo(f"🔓 Unlocked: {machine['hostname']} ({machine['machine_id'][:8]}...)")


@machine.command("revoke")
@click.argument("machine_id")
@click.option("--reason", "-r", help="Revocation reason")
@click.confirmation_option(prompt="Permanently revoke this machine?")
@click.pass_context
def machine_revoke(ctx: click.Context, machine_id: str, reason: str | None) -> None:
    """Revoke a machine (permanent)."""
    api_url = ctx.obj["api_url"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        machine = client.revoke_machine(machine_id, reason)

    click.echo(f"❌ Revoked: {machine['hostname']} ({machine['machine_id'][:8]}...)")


# ===== Audit Commands =====


@cli.group()
def audit() -> None:
    """Audit log operations."""
    pass


@audit.command("list")
@click.option("--machine-id", help="Filter by machine ID")
@click.option("--page", default=1, help="Page number")
@click.option("--per-page", default=50, help="Items per page")
@click.pass_context
def audit_list(
    ctx: click.Context, machine_id: str | None, page: int, per_page: int
) -> None:
    """List audit log entries."""
    api_url = ctx.obj["api_url"]
    output = ctx.obj["output"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        result = client.list_audit_logs(machine_id, page, per_page)

    if output == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        entries = result.get("entries", [])
        total = result.get("total", 0)

        if not entries:
            click.echo("No audit log entries found.")
            return

        click.echo(f"\n📋 Audit Log ({len(entries)} of {total}):\n")
        for entry in entries:
            click.echo(f"  [{entry['timestamp']}] {entry['action']}")
            click.echo(f"    Operator: {entry['operator_cn']}")
            if entry.get("machine_id"):
                click.echo(f"    Machine: {entry['machine_id'][:8]}...")
            if entry.get("detail"):
                click.echo(f"    Detail: {entry['detail']}")
            click.echo()


@audit.command("verify")
@click.pass_context
def audit_verify(ctx: click.Context) -> None:
    """Verify audit log cryptographic chain integrity."""
    api_url = ctx.obj["api_url"]
    token = _get_token()

    with AttestationClient(api_url, token) as client:
        result = client.verify_audit_chain()

    if result.get("valid"):
        click.echo("✅ Audit log chain integrity: VALID")
    else:
        click.echo("❌ Audit log chain integrity: INVALID")
        if result.get("error"):
            click.echo(f"   Error: {result['error']}")


# ===== Secret Management Commands (Extension) =====


@cli.group()
def secret() -> None:
    """Secret vault management (extension)."""
    pass


@secret.command("create")
@click.argument("machine_id")
@click.option("--name", "-n", required=True, help="Secret name")
@click.option("--value", "-v", required=True, help="Secret value (plaintext)")
@click.pass_context
def secret_create(ctx: click.Context, machine_id: str, name: str, value: str) -> None:
    """Create a new secret for a machine."""
    token = _get_token()
    api_url = ctx.obj["api_url"]
    output_format = ctx.obj["output"]

    client = AttestationClient(api_url, token)
    result = client.post(
        f"/api/v1/secrets/machines/{machine_id}/secrets",
        json={"name": name, "value": value}
    )

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"✅ Secret created:")
        click.echo(f"   ID:      {result['secret_id']}")
        click.echo(f"   Machine: {result['machine_id']}")
        click.echo(f"   Name:    {result['name']}")
        click.echo(f"   Created: {result['created_at']}")


@secret.command("list")
@click.argument("machine_id")
@click.pass_context
def secret_list(ctx: click.Context, machine_id: str) -> None:
    """List all secrets for a machine."""
    token = _get_token()
    api_url = ctx.obj["api_url"]
    output_format = ctx.obj["output"]

    client = AttestationClient(api_url, token)
    result = client.get(f"/api/v1/secrets/machines/{machine_id}/secrets")

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        secrets = result.get("secrets", [])
        if not secrets:
            click.echo("No secrets found for this machine.")
            return

        click.echo(f"Found {len(secrets)} secret(s):\n")
        for s in secrets:
            click.echo(f"  📝 {s['name']}")
            click.echo(f"     ID:       {s['secret_id']}")
            click.echo(f"     Created:  {s['created_at']} by {s['created_by']}")
            if s['last_accessed_at']:
                click.echo(f"     Accessed: {s['last_accessed_at']} ({s['access_count']} times)")
            else:
                click.echo(f"     Accessed: Never")
            click.echo()


@secret.command("get")
@click.argument("machine_id")
@click.argument("secret_name")
@click.option(
    "--ek-fingerprint",
    required=True,
    help="Machine EK fingerprint for authentication"
)
@click.pass_context
def secret_get(
    ctx: click.Context,
    machine_id: str,
    secret_name: str,
    ek_fingerprint: str
) -> None:
    """
    Get encrypted secret value.
    
    Returns the encrypted blob that can only be decrypted by the machine's TPM.
    """
    api_url = ctx.obj["api_url"]
    output_format = ctx.obj["output"]

    # Note: This endpoint does NOT require operator auth
    # The machine authenticates via EK fingerprint header
    client = AttestationClient(api_url, None)  # No token needed
    result = client.get(
        f"/api/v1/secrets/machines/{machine_id}/secrets/{secret_name}",
        headers={"X-EK-Fingerprint": ek_fingerprint}
    )

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(f"✅ Secret retrieved:")
        click.echo(f"   ID:   {result['secret_id']}")
        click.echo(f"   Name: {result['name']}")
        click.echo(f"\n   Encrypted blob (base64):")
        click.echo(f"   {result['encrypted_blob'][:64]}...")
        click.echo(f"\n   Nonce: {result['nonce']}")
        click.echo(f"   Tag:   {result['tag']}")


@secret.command("delete")
@click.argument("secret_id")
@click.confirmation_option(prompt="Are you sure you want to delete this secret?")
@click.pass_context
def secret_delete(ctx: click.Context, secret_id: str) -> None:
    """Delete a secret permanently."""
    token = _get_token()
    api_url = ctx.obj["api_url"]

    client = AttestationClient(api_url, token)
    client.delete(f"/api/v1/secrets/{secret_id}")

    click.echo(f"✅ Secret {secret_id} deleted")


# ===== Helper Functions =====


def _get_token() -> str:
    """Get cached token or exit.

    Returns:
        Access token string

    Raises:
        SystemExit: If no valid token found
    """
    realm = os.getenv("KEYCLOAK_REALM", DEFAULT_REALM)
    client_id = os.getenv("KEYCLOAK_CLIENT_ID", DEFAULT_CLIENT_ID)
    cache = TokenCache()
    token = cache.load(realm, client_id)

    if not token:
        click.echo("❌ Not logged in. Run: attestation auth login")
        sys.exit(1)

    return token.access_token


if __name__ == "__main__":
    cli()

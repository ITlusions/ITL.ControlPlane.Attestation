"""Webhooks extension — CLI plugin.

This module shows how a service extension contributes its own CLI commands
alongside its REST API routes. It implements the full ``attestation webhook``
command group and registers it via the ``attestation_cli_plugins`` entry point.

To wire this plugin when shipping ``itl-controlplane-attestation`` as a package,
add to its ``pyproject.toml``::

    [project.entry-points."attestation_cli_plugins"]
    webhooks = "extensions.builtin.webhooks.cli_plugin:WebhooksCliPlugin"
"""

from __future__ import annotations

import json

import click

from cli.api_client import AttestationClient
from cli.auth import get_token
from cli.plugin import CliPlugin


class WebhooksCliPlugin(CliPlugin):
    """CLI plugin for the webhooks built-in extension."""

    @property
    def name(self) -> str:
        return "webhooks"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Webhook management commands contributed by the webhooks extension."

    def register(self, cli: click.Group) -> None:
        """Register the ``webhook`` command group on the root CLI."""

        @cli.group("webhook")
        def webhook() -> None:
            """Webhook management (webhooks extension)."""

        # --- list ---

        @webhook.command("list")
        @click.pass_context
        def webhook_list(ctx: click.Context) -> None:
            """List all registered webhooks."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            with AttestationClient(api_url, token) as client:
                result = client.get("/api/v1/webhooks/")

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                webhooks = result.get("webhooks", [])
                if not webhooks:
                    click.echo("No webhooks registered.")
                    return

                click.echo(f"\nWebhooks ({result.get('total', len(webhooks))}):\n")
                for w in webhooks:
                    status = "enabled" if w.get("enabled") else "disabled"
                    click.echo(f"  {w['webhook_id'][:8]}...  {w['url']}")
                    click.echo(f"     Events:   {', '.join(w.get('events', []))}")
                    click.echo(f"     Status:   {status}")
                    click.echo(
                        f"     Triggers: {w.get('trigger_count', 0)} "
                        f"(failures: {w.get('failure_count', 0)})"
                    )
                    click.echo()

        # --- get ---

        @webhook.command("get")
        @click.argument("webhook_id")
        @click.pass_context
        def webhook_get(ctx: click.Context, webhook_id: str) -> None:
            """Get webhook details."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            with AttestationClient(api_url, token) as client:
                result = client.get(f"/api/v1/webhooks/{webhook_id}")

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"\nWebhook: {result['webhook_id']}")
                click.echo(f"  URL:      {result['url']}")
                click.echo(f"  Events:   {', '.join(result.get('events', []))}")
                click.echo(f"  Enabled:  {result.get('enabled', False)}")
                click.echo(f"  Created:  {result.get('created_at', 'N/A')}")
                click.echo(f"  Triggers: {result.get('trigger_count', 0)}")
                click.echo(f"  Failures: {result.get('failure_count', 0)}")

        # --- create ---

        @webhook.command("create")
        @click.option("--url", "-u", required=True, help="Target URL to deliver events to")
        @click.option(
            "--event",
            "-e",
            multiple=True,
            required=True,
            help="Event type to subscribe to (repeat for multiple)",
        )
        @click.option("--secret", "-s", help="HMAC signing secret")
        @click.pass_context
        def webhook_create(
            ctx: click.Context,
            url: str,
            event: tuple[str, ...],
            secret: str | None,
        ) -> None:
            """Register a new webhook."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            payload: dict = {"url": url, "events": list(event)}
            if secret:
                payload["secret"] = secret

            with AttestationClient(api_url, token) as client:
                result = client.post("/api/v1/webhooks/", json=payload)

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Webhook registered: {result['webhook_id']}")
                click.echo(f"  URL:    {result['url']}")
                click.echo(f"  Events: {', '.join(result.get('events', []))}")

        # --- update ---

        @webhook.command("update")
        @click.argument("webhook_id")
        @click.option("--url", "-u", help="New target URL")
        @click.option("--event", "-e", multiple=True, help="Replace event subscriptions")
        @click.option("--enable/--disable", default=None, help="Enable or disable")
        @click.pass_context
        def webhook_update(
            ctx: click.Context,
            webhook_id: str,
            url: str | None,
            event: tuple[str, ...],
            enable: bool | None,
        ) -> None:
            """Update an existing webhook."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            payload: dict = {}
            if url:
                payload["url"] = url
            if event:
                payload["events"] = list(event)
            if enable is not None:
                payload["enabled"] = enable

            if not payload:
                raise click.UsageError("Provide at least one option to update.")

            with AttestationClient(api_url, token) as client:
                result = client.put(f"/api/v1/webhooks/{webhook_id}", json=payload)

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo(f"Webhook updated: {result['webhook_id']}")

        # --- delete ---

        @webhook.command("delete")
        @click.argument("webhook_id")
        @click.confirmation_option(prompt="Delete this webhook?")
        @click.pass_context
        def webhook_delete(ctx: click.Context, webhook_id: str) -> None:
            """Delete a webhook."""
            api_url = ctx.obj["api_url"]
            token = get_token()

            with AttestationClient(api_url, token) as client:
                client.delete(f"/api/v1/webhooks/{webhook_id}")

            click.echo(f"Webhook {webhook_id} deleted.")

        # --- deliveries ---

        @webhook.command("deliveries")
        @click.argument("webhook_id")
        @click.pass_context
        def webhook_deliveries(ctx: click.Context, webhook_id: str) -> None:
            """List recent delivery attempts for a webhook."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            with AttestationClient(api_url, token) as client:
                result = client.get(f"/api/v1/webhooks/{webhook_id}/deliveries")

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                deliveries = result.get("deliveries", [])
                if not deliveries:
                    click.echo("No deliveries recorded.")
                    return

                click.echo(f"\nDeliveries for {webhook_id[:8]}...:\n")
                for d in deliveries:
                    status = (
                        "OK"
                        if str(d.get("response_status", "")).startswith("2")
                        else "FAIL"
                    )
                    click.echo(
                        f"  [{status}] {d.get('event_type', 'N/A')}  "
                        f"{d.get('delivered_at', 'N/A')}  "
                        f"HTTP {d.get('response_status', '?')}  "
                        f"{d.get('duration_ms', '?')}ms"
                    )

        # --- test ---

        @webhook.command("test")
        @click.argument("webhook_id")
        @click.pass_context
        def webhook_test(ctx: click.Context, webhook_id: str) -> None:
            """Send a test event to a webhook."""
            api_url = ctx.obj["api_url"]
            output = ctx.obj["output"]
            token = get_token()

            with AttestationClient(api_url, token) as client:
                result = client.post(f"/api/v1/webhooks/{webhook_id}/test")

            if output == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                status = result.get("response_status", "?")
                duration = result.get("duration_ms", "?")
                click.echo(f"Test delivery sent: HTTP {status} in {duration}ms")
                if result.get("error"):
                    click.echo(f"  Error: {result['error']}")

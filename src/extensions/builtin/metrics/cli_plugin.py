"""Metrics extension — CLI plugin.

Contributes the ``attestation metrics show`` command by fetching the raw
Prometheus text from the service's ``GET /metrics`` endpoint.

Register via pyproject.toml of itl-controlplane-attestation::

    [project.entry-points."attestation_cli_plugins"]
    metrics = "extensions.builtin.metrics.cli_plugin:MetricsCliPlugin"
"""

from __future__ import annotations

import click

from cli.api_client import AttestationClient
from cli.plugin import CliPlugin


class MetricsCliPlugin(CliPlugin):
    """CLI plugin for the metrics built-in extension."""

    @property
    def name(self) -> str:
        return "metrics"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Service metrics commands contributed by the metrics extension."

    def register(self, cli: click.Group) -> None:
        """Register the ``metrics`` command group on the root CLI."""

        @cli.group("metrics")
        def metrics() -> None:
            """Service metrics (metrics extension)."""

        @metrics.command("show")
        @click.pass_context
        def metrics_show(ctx: click.Context) -> None:
            """Print Prometheus metrics from the service."""
            api_url = ctx.obj["api_url"]
            # The /metrics endpoint is unauthenticated (Prometheus scrape target)
            with AttestationClient(api_url, token=None) as client:
                raw = client.get("/metrics", raw=True)
            click.echo(raw)

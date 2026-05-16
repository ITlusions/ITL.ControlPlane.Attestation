"""CLI plugin discovery and registration.

Scans the ``attestation_cli_plugins`` entry point group and attaches
every found :class:`~cli.plugin.CliPlugin` to the root Click group.
"""

from __future__ import annotations

import importlib.metadata

import click

from .plugin import CliPlugin


def discover_and_register_plugins(cli: click.Group) -> list[str]:
    """Discover installed CLI plugins and register them with the root CLI group.

    Plugins are discovered via the ``attestation_cli_plugins``
    `entry point group <https://packaging.python.org/en/latest/specifications/entry-points/>`_.
    Each entry point must resolve to a :class:`~cli.plugin.CliPlugin` **class**
    (not an instance). It is instantiated here and its
    :meth:`~cli.plugin.CliPlugin.register` method is called with *cli*.

    Failed plugins are skipped with a warning on stderr so that a broken
    third-party plugin never prevents the core CLI from starting.

    Args:
        cli: The root :class:`click.Group` of the ``attestation`` CLI.

    Returns:
        Names of successfully registered plugins, in discovery order.

    Example ``pyproject.toml`` entry (in the third-party package)::

        [project.entry-points."attestation_cli_plugins"]
        my-extension = "mypackage.cli_plugin:MyCliPlugin"
    """
    registered: list[str] = []

    try:
        eps = importlib.metadata.entry_points(group="attestation_cli_plugins")
    except Exception:
        return registered

    for ep in eps:
        try:
            plugin_cls = ep.load()

            if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, CliPlugin)):
                click.echo(
                    f"[attestation] Warning: entry point '{ep.name}' does not point "
                    "to a CliPlugin subclass — skipping.",
                    err=True,
                )
                continue

            plugin: CliPlugin = plugin_cls()
            plugin.register(cli)
            registered.append(plugin.name)

        except Exception as exc:  # noqa: BLE001
            click.echo(
                f"[attestation] Warning: could not load CLI plugin '{ep.name}': {exc}",
                err=True,
            )

    return registered

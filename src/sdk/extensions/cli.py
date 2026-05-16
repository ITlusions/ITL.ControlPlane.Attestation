"""CliPlugin — SDK base class for attestation CLI extension plugins.

Lives in the SDK so that any package that already depends on
``itl-attestation-sdk[cli]`` gets the full plugin contract without also
needing to install ``itl-attestation-cli``.

Requires the ``cli`` extra::

    pip install itl-attestation-sdk[cli]

Quick-start
-----------
1. Implement ``CliPlugin`` in your package::

    # mypackage/cli_plugin.py
    import click
    from sdk.extensions import CliPlugin
    from sdk.extensions import get_token          # if also using the CLI helpers
    from cli.api_client import AttestationClient  # when installed alongside CLI

    class MyCliPlugin(CliPlugin):
        name = "my-extension"
        version = "1.0.0"
        description = "CLI commands for My Extension"

        def register(self, cli: click.Group) -> None:
            @cli.group("myext")
            def myext():
                \"\"\"My extension commands.\"\"\"

            @myext.command("list")
            @click.pass_context
            def myext_list(ctx: click.Context) -> None:
                \"\"\"List my extension resources.\"\"\"
                ...

2. Declare the entry point in your ``pyproject.toml``::

    [project.entry-points."attestation_cli_plugins"]
    my-extension = "mypackage.cli_plugin:MyCliPlugin"

3. Install alongside ``itl-attestation-cli``::

    pip install itl-attestation-sdk[cli] itl-attestation-cli mypackage

The ``attestation`` CLI will include ``attestation myext list`` automatically.

Context contract
----------------
Every command registered via a plugin receives the same ``ctx.obj`` dict
as built-in commands:

``ctx.obj["api_url"]``
    Resolved attestation API base URL (from ``--api-url`` / ``ATTESTATION_API_URL``).

``ctx.obj["output"]``
    Requested output format: ``"json"`` or ``"table"``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import click


class CliPlugin(ABC):
    """Abstract base class for attestation CLI plugins.

    Subclass this, implement :attr:`name`, :attr:`version`, and
    :meth:`register`, then declare it as an ``attestation_cli_plugins``
    entry point so the CLI discovers and loads it at startup.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (kebab-case).

        Used in log messages and error reporting.
        Examples: ``"webhooks"``, ``"my-attestation-extension"``.
        """

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string (e.g. ``"1.0.0"``)."""

    @property
    def description(self) -> str:
        """Short human-readable description shown in warning messages."""
        return ""

    @abstractmethod
    def register(self, cli: click.Group) -> None:
        """Add commands or command groups to the CLI root group.

        Create a new ``@click.group()`` and attach it to *cli*, or use the
        ``@cli.group()`` / ``@cli.command()`` decorators directly.

        Args:
            cli: The root :class:`click.Group` of the ``attestation`` CLI.
        """

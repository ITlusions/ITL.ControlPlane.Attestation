"""CliPlugin — re-exported from the SDK for backward compatibility.

The canonical definition lives in the SDK so extension authors only need
``itl-attestation-sdk[cli]`` rather than ``itl-attestation-cli``:

    from sdk.extensions import CliPlugin

This shim exists so any existing code that imports::

    from cli.plugin import CliPlugin

continues to work without change.
"""

from sdk.extensions import CliPlugin

__all__ = ["CliPlugin"]

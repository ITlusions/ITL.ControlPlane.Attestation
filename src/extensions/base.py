"""
Backward-compatibility shim.

``AttestationExtension`` has moved to the SDK so external extension packages
can declare it as a proper dependency (``itl-attestation-sdk``).

Import from the canonical location::

    from sdk import AttestationExtension
    # or
    from sdk.extensions import AttestationExtension

This module re-exports the class so existing internal code that still uses
``from extensions.base import AttestationExtension`` continues to work.
"""

from sdk.extensions import AttestationExtension

__all__ = ["AttestationExtension"]

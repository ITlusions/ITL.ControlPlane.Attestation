"""
Secret Vault Extension

TPM-bound secret storage for attested machines.
Secrets are encrypted with machine-specific keys derived from the EK.
Only the registered machine can decrypt its secrets.
"""

from .extension import SecretVaultExtension

__all__ = ["SecretVaultExtension"]

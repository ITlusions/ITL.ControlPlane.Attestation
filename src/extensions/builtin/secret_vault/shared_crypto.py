"""
Encryption layer for shared secrets.

Shared secrets use a master key instead of machine-specific derivation.
"""

import os
import hashlib

from .base_crypto import BaseCrypto


class SharedSecretCrypto(BaseCrypto):
    """
    Handles encryption/decryption of shared secrets.
    
    Key source (priority order):
    1. ITL_SHARED_SECRET_MASTER_KEY env var (hex-encoded 32-byte key)
    2. ITL_SHARED_SECRET_PASSPHRASE env var (SHA-256 hashed to 32 bytes)
    3. Random key (development only - secrets lost on restart)
    """
    
    def __init__(self):
        """Initialize shared secret encryption."""
        self._key_source: str = ""  # Set in _derive_key
        super().__init__()
    
    def _derive_key(self) -> bytes:
        """
        Get or generate master encryption key.
        
        Returns:
            32-byte master key
        """
        # Option 1: Direct hex key (production)
        if "ITL_SHARED_SECRET_MASTER_KEY" in os.environ:
            key_hex = os.environ["ITL_SHARED_SECRET_MASTER_KEY"]
            key = bytes.fromhex(key_hex)
            if len(key) != 32:
                raise ValueError("ITL_SHARED_SECRET_MASTER_KEY must be 32 bytes (64 hex chars)")
            self._key_source = "env:ITL_SHARED_SECRET_MASTER_KEY"
            return key
        
        # Option 2: Passphrase hashed to key
        if "ITL_SHARED_SECRET_PASSPHRASE" in os.environ:
            passphrase = os.environ["ITL_SHARED_SECRET_PASSPHRASE"]
            key = hashlib.sha256(passphrase.encode("utf-8")).digest()
            self._key_source = "env:ITL_SHARED_SECRET_PASSPHRASE(sha256)"
            return key
        
        # Option 3: Random key (dev only - not persisted!)
        key = os.urandom(32)
        self._key_source = "random-ephemeral"
        return key
    
    def get_key_id(self) -> str:
        """
        Return key identifier for metadata.
        
        Returns:
            Key source description
        """
        return self._key_source


# Singleton instance
_shared_crypto_instance: SharedSecretCrypto = None


def get_shared_crypto() -> SharedSecretCrypto:
    """
    Get shared crypto singleton instance.
    
    Returns:
        SharedSecretCrypto instance with master key
    """
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = SharedSecretCrypto()
    return _crypto_instance

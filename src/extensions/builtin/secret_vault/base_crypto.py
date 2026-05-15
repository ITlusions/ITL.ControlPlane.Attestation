"""
Base cryptographic operations for secret vault.

Provides AES-256-GCM encryption/decryption with pluggable key derivation.
"""

import os
from abc import ABC, abstractmethod
from typing import Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class BaseCrypto(ABC):
    """
    Base class for AES-256-GCM encryption operations.
    
    Subclasses implement key derivation strategy:
    - MachineSecretCrypto: Derive key from EK fingerprint (HKDF-SHA256)
    - SharedSecretCrypto: Use master key from environment
    """
    
    def __init__(self):
        """Initialize cipher. Key is derived by subclass."""
        self._key = self._derive_key()
        if len(self._key) != 32:
            raise ValueError("Encryption key must be 32 bytes for AES-256")
        self.cipher = AESGCM(self._key)
    
    @abstractmethod
    def _derive_key(self) -> bytes:
        """
        Derive encryption key.
        
        Returns:
            32-byte AES-256 key
        """
        pass
    
    @abstractmethod
    def get_key_id(self) -> str:
        """
        Return key identifier for metadata.
        
        Returns:
            Key ID string (e.g., "ek-derived", "master-key-v1")
        """
        pass
    
    def encrypt(self, plaintext: str) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt plaintext secret value.
        
        Args:
            plaintext: Secret value to encrypt
        
        Returns:
            Tuple of (ciphertext, nonce, tag)
        """
        nonce = os.urandom(12)  # 96 bits for GCM
        plaintext_bytes = plaintext.encode("utf-8")
        
        # AESGCM.encrypt() returns ciphertext + tag concatenated
        ciphertext_and_tag = self.cipher.encrypt(nonce, plaintext_bytes, None)
        
        # Split ciphertext and tag
        ciphertext = ciphertext_and_tag[:-16]  # Everything except last 16 bytes
        tag = ciphertext_and_tag[-16:]  # Last 16 bytes
        
        return ciphertext, nonce, tag
    
    def decrypt(self, ciphertext: bytes, nonce: bytes, tag: bytes) -> str:
        """
        Decrypt encrypted secret value.
        
        Args:
            ciphertext: Encrypted bytes
            nonce: 96-bit nonce used during encryption
            tag: 128-bit authentication tag
        
        Returns:
            Decrypted plaintext string
        
        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails
        """
        # AESGCM.decrypt() expects ciphertext + tag concatenated
        ciphertext_and_tag = ciphertext + tag
        
        plaintext_bytes = self.cipher.decrypt(nonce, ciphertext_and_tag, None)
        return plaintext_bytes.decode("utf-8")

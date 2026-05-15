"""
Encryption layer for machine-specific secrets.

Secrets are encrypted using AES-256-GCM.
The encryption key is derived from the machine's EK fingerprint using HKDF-SHA256.
"""

from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from .base_crypto import BaseCrypto


class MachineSecretCrypto(BaseCrypto):
    """
    Handles encryption/decryption of machine-specific secrets.
    
    Key derivation:
    - Input: Machine's EK fingerprint (SHA-256 of EK public key)
    - Algorithm: HKDF-SHA256 with fixed salt
    - Output: 256-bit AES key unique to this machine
    """
    
    def __init__(self, ek_fingerprint: str):
        """
        Initialize crypto for a specific machine.
        
        Args:
            ek_fingerprint: Machine's EK fingerprint (hex string)
        """
        self.ek_fingerprint = ek_fingerprint
        super().__init__()
    
    def _derive_key(self) -> bytes:
        """
        Derive AES-256 key from EK fingerprint using HKDF-SHA256.
        
        Returns:
            32-byte encryption key
        """
        # Convert hex fingerprint to bytes
        ikm = bytes.fromhex(self.ek_fingerprint)
        
        # Fixed salt for key derivation (not secret, prevents rainbow tables)
        salt = b"ITL.ControlPlane.Attestation.SecretVault.v1"
        
        # Derive 256-bit key using HKDF-SHA256
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"machine-secret-encryption"
        )
        return kdf.derive(ikm)
    
    def get_key_id(self) -> str:
        """
        Return key identifier for metadata.
        
        Returns:
            Key ID derived from EK fingerprint
        """
        return f"ek-{self.ek_fingerprint[:16]}"


"""
Base classes for secret storage models.

Common fields for all encrypted secrets (machine-bound and shared).
"""

from sqlmodel import Field
from datetime import datetime
from typing import Optional


class EncryptedSecretMixin:
    """
    Mixin for AES-256-GCM encrypted secret storage.
    
    Provides common fields for all secret types:
    - encrypted_value, nonce, tag (AES-GCM encryption)
    - created_at, created_by (audit trail)
    - last_accessed_at, access_count (access tracking)
    """
    
    encrypted_value: bytes = Field(
        description="AES-256-GCM encrypted secret value"
    )
    
    nonce: bytes = Field(
        description="GCM nonce (96 bits)"
    )
    
    tag: bytes = Field(
        description="GCM authentication tag (128 bits)"
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp (UTC)"
    )
    
    created_by: str = Field(
        max_length=256,
        description="Operator CN who created the secret"
    )
    
    last_accessed_at: Optional[datetime] = Field(
        default=None,
        description="Last access timestamp (UTC)"
    )
    
    access_count: int = Field(
        default=0,
        description="Number of times secret was retrieved"
    )

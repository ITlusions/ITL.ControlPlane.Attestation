"""
Pydantic schemas for Secret Vault extension API.
"""

from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class SecretCreateRequest(BaseModel):
    """Request to create a new secret."""
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Secret name (e.g., 'disk-encryption-key')",
        examples=["disk-encryption-key", "kubeconfig", "tls-cert"]
    )
    
    value: str = Field(
        ...,
        min_length=1,
        description="Secret value (plaintext, will be encrypted)"
    )


class SecretResponse(BaseModel):
    """Response for secret metadata (no value)."""
    
    secret_id: uuid.UUID
    machine_id: uuid.UUID
    name: str
    created_at: datetime
    created_by: str
    last_accessed_at: datetime | None
    access_count: int
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "machine_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "name": "disk-encryption-key",
                "created_at": "2026-05-15T10:30:00Z",
                "created_by": "operator@itlusions.com",
                "last_accessed_at": None,
                "access_count": 0
            }
        }
    }


class SecretValueResponse(BaseModel):
    """Response containing encrypted secret for machine retrieval."""
    
    secret_id: uuid.UUID
    name: str
    encrypted_blob: str = Field(
        description="Base64-encoded encrypted secret (AES-256-GCM)"
    )
    nonce: str = Field(
        description="Base64-encoded GCM nonce"
    )
    tag: str = Field(
        description="Base64-encoded GCM authentication tag"
    )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "name": "disk-encryption-key",
                "encrypted_blob": "gAAAAA...",
                "nonce": "AQIDBA...",
                "tag": "AQIDBA..."
            }
        }
    }


class SecretListResponse(BaseModel):
    """Response for listing secrets."""
    
    secrets: list[SecretResponse]
    total: int

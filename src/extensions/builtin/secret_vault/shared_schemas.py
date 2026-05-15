"""
Pydantic schemas for shared secrets.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


class SharedSecretCreateRequest(BaseModel):
    """Request to create a shared secret."""
    
    name: str = Field(
        ...,
        max_length=128,
        description="Unique secret name",
        json_schema_extra={"example": "prod-k8s-join-token"}
    )
    
    value: str = Field(
        ...,
        min_length=1,
        description="Secret value (will be encrypted)",
        json_schema_extra={"example": "K07::server:abc123..."}
    )
    
    description: Optional[str] = Field(
        None,
        max_length=512,
        description="Purpose of this secret",
        json_schema_extra={"example": "Kubernetes cluster join token for production"}
    )


class SharedSecretUpdateRequest(BaseModel):
    """Request to update (rotate) a shared secret."""
    
    value: Optional[str] = Field(
        None,
        min_length=1,
        description="New secret value (rotation)"
    )
    
    description: Optional[str] = Field(
        None,
        max_length=512,
        description="Updated description"
    )


class SharedSecretResponse(BaseModel):
    """Shared secret metadata (no secret value)."""
    
    shared_secret_id: uuid.UUID
    name: str
    encryption_key_id: str
    created_at: datetime
    created_by: str
    last_rotated_at: Optional[datetime] = None
    description: Optional[str] = None
    authorized_machine_count: int = Field(
        default=0,
        description="Number of machines with access"
    )
    
    @classmethod
    def from_row(cls, row, authorized_count: int = 0):
        """Convert SharedSecretRow to response."""
        return cls(
            shared_secret_id=row.shared_secret_id,
            name=row.name,
            encryption_key_id=row.encryption_key_id,
            created_at=row.created_at,
            created_by=row.created_by,
            last_rotated_at=row.last_rotated_at,
            description=row.description,
            authorized_machine_count=authorized_count
        )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "shared_secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "name": "prod-k8s-join-token",
                "encryption_key_id": "master-key-v1",
                "created_by": "operator@itlusions.com",
                "authorized_machine_count": 5,
                "description": "Production Kubernetes join token"
            }
        }
    }


class SharedSecretListResponse(BaseModel):
    """List of shared secrets."""
    
    secrets: list[SharedSecretResponse]
    total: int


class SharedSecretValueResponse(BaseModel):
    """Shared secret value (only returned to authorized machines)."""
    
    name: str
    value: str
    accessed_at: datetime
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "prod-k8s-join-token",
                "value": "K07::server:abc123...",
                "accessed_at": "2026-05-15T14:30:00Z"
            }
        }
    }


class SharedSecretAccessGrantRequest(BaseModel):
    """Request to grant machine access to a shared secret."""
    
    machine_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Machine IDs to grant access"
    )


class SharedSecretAccessRevokeRequest(BaseModel):
    """Request to revoke machine access to a shared secret."""
    
    machine_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Machine IDs to revoke access"
    )


class SharedSecretAccessResponse(BaseModel):
    """Access grant record."""
    
    shared_secret_id: uuid.UUID
    machine_id: uuid.UUID
    granted_at: datetime
    granted_by: str
    last_accessed_at: Optional[datetime] = None
    access_count: int = 0
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "shared_secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "machine_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "granted_by": "operator@itlusions.com",
                "access_count": 12
            }
        }
    }


class SharedSecretAccessListResponse(BaseModel):
    """List of machines with access to a shared secret."""
    
    access_grants: list[SharedSecretAccessResponse]
    total: int

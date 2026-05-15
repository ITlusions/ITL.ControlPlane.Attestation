"""
Pydantic schemas for Webhooks extension API.
"""

from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
import uuid


class WebhookCreateRequest(BaseModel):
    """Request to create a new webhook."""
    
    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Target URL for webhook delivery",
        examples=["https://api.example.com/webhooks/attestation"]
    )
    
    events: list[str] = Field(
        ...,
        min_length=1,
        description="List of event types to subscribe to",
        examples=[["machine.registered", "machine.approved", "machine.revoked"]]
    )
    
    secret: str | None = Field(
        default=None,
        description="HMAC-SHA256 secret for signature validation"
    )


class WebhookUpdateRequest(BaseModel):
    """Request to update webhook configuration."""
    
    url: str | None = Field(default=None, max_length=2048)
    events: list[str] | None = Field(default=None, min_length=1)
    secret: str | None = Field(default=None)
    enabled: bool | None = Field(default=None)


class WebhookResponse(BaseModel):
    """Response for webhook metadata."""
    
    webhook_id: uuid.UUID
    url: str
    events: list[str]
    enabled: bool
    created_at: datetime
    created_by: str
    last_triggered_at: datetime | None
    trigger_count: int
    failure_count: int
    
    @classmethod
    def from_row(cls, row):
        """Convert database row to response schema."""
        return cls(
            webhook_id=row.webhook_id,
            url=row.url,
            events=row.events.split(","),
            enabled=row.enabled,
            created_at=row.created_at,
            created_by=row.created_by,
            last_triggered_at=row.last_triggered_at,
            trigger_count=row.trigger_count,
            failure_count=row.failure_count
        )
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "webhook_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "url": "https://api.example.com/webhooks/attestation",
                "events": ["machine.registered", "machine.approved"],
                "enabled": True,
                "created_at": "2026-05-15T10:30:00Z",
                "created_by": "operator@itlusions.com",
                "last_triggered_at": None,
                "trigger_count": 0,
                "failure_count": 0
            }
        }
    }


class WebhookListResponse(BaseModel):
    """Response for listing webhooks."""
    
    webhooks: list[WebhookResponse]
    total: int


class WebhookDeliveryResponse(BaseModel):
    """Response for webhook delivery history."""
    
    delivery_id: uuid.UUID
    webhook_id: uuid.UUID
    event_type: str
    response_status: int | None
    error: str | None
    delivered_at: datetime
    duration_ms: int | None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "delivery_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "webhook_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "event_type": "machine.approved",
                "response_status": 200,
                "error": None,
                "delivered_at": "2026-05-15T10:30:00Z",
                "duration_ms": 125
            }
        }
    }


class WebhookDeliveryListResponse(BaseModel):
    """Response for listing deliveries."""
    
    deliveries: list[WebhookDeliveryResponse]
    total: int


class WebhookEventPayload(BaseModel):
    """Standard webhook event payload structure."""
    
    event_type: str = Field(description="Event type (e.g., 'machine.approved')")
    timestamp: datetime = Field(description="Event timestamp (UTC)")
    machine_id: uuid.UUID | None = Field(default=None, description="Machine ID if applicable")
    data: dict = Field(description="Event-specific data")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "event_type": "machine.approved",
                "timestamp": "2026-05-15T10:30:00Z",
                "machine_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "data": {
                    "ek_fingerprint": "a3f1...",
                    "status": "registered",
                    "approved_by": "operator@itlusions.com"
                }
            }
        }
    }

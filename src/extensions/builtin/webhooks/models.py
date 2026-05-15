"""
Data models for Webhooks extension.

Stores webhook configurations and delivery history.
"""

from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import uuid
import json


class WebhookRow(SQLModel, table=True):
    """
    Webhook configuration for event notifications.
    
    When a subscribed event occurs, the extension sends an HTTP POST
    to the configured URL with event details.
    """
    
    __tablename__ = "extension_webhooks"
    
    webhook_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique webhook identifier"
    )
    
    url: str = Field(
        max_length=2048,
        description="Target URL for webhook delivery"
    )
    
    events: str = Field(
        description="Comma-separated list of subscribed events"
    )
    
    secret: Optional[str] = Field(
        default=None,
        max_length=256,
        description="HMAC-SHA256 secret for signature validation"
    )
    
    enabled: bool = Field(
        default=True,
        description="Whether webhook is active"
    )
    
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp (UTC)"
    )
    
    created_by: str = Field(
        max_length=256,
        description="Operator CN who created the webhook"
    )
    
    last_triggered_at: Optional[datetime] = Field(
        default=None,
        description="Last successful delivery timestamp"
    )
    
    trigger_count: int = Field(
        default=0,
        description="Number of successful deliveries"
    )
    
    failure_count: int = Field(
        default=0,
        description="Number of failed deliveries"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "webhook_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "url": "https://api.example.com/webhooks/attestation",
                "events": "machine.registered,machine.approved,machine.revoked",
                "enabled": True,
                "created_by": "operator@itlusions.com"
            }
        }


class WebhookDeliveryRow(SQLModel, table=True):
    """
    Webhook delivery log for debugging and audit.
    
    Records every delivery attempt with request/response details.
    """
    
    __tablename__ = "extension_webhook_deliveries"
    
    delivery_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique delivery identifier"
    )
    
    webhook_id: uuid.UUID = Field(
        foreign_key="extension_webhooks.webhook_id",
        index=True,
        description="Webhook that was triggered"
    )
    
    event_type: str = Field(
        max_length=128,
        index=True,
        description="Event type (e.g., 'machine.approved')"
    )
    
    payload: str = Field(
        description="JSON payload sent to webhook"
    )
    
    response_status: Optional[int] = Field(
        default=None,
        description="HTTP response status code"
    )
    
    response_body: Optional[str] = Field(
        default=None,
        description="HTTP response body (truncated to 4KB)"
    )
    
    error: Optional[str] = Field(
        default=None,
        description="Error message if delivery failed"
    )
    
    delivered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Delivery attempt timestamp (UTC)"
    )
    
    duration_ms: Optional[int] = Field(
        default=None,
        description="Request duration in milliseconds"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "delivery_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "webhook_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "event_type": "machine.approved",
                "response_status": 200,
                "delivered_at": "2026-05-15T10:30:00Z"
            }
        }

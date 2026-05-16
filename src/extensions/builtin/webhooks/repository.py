"""
Repository for Webhooks extension.

Handles database operations for webhooks and delivery logs.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from datetime import datetime
from typing import Optional
import uuid

from .models import WebhookRow, WebhookDeliveryRow


class WebhookRepository:
    """Repository for webhook operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        url: str,
        events: list[str],
        created_by: str,
        secret: Optional[str] = None
    ) -> WebhookRow:
        """
        Create a new webhook.
        
        Args:
            url: Target URL
            events: List of event types
            created_by: Operator CN
            secret: Optional HMAC secret
        
        Returns:
            Created WebhookRow
        """
        webhook = WebhookRow(
            url=url,
            events=",".join(events),
            secret=secret,
            enabled=True,
            created_by=created_by,
            created_at=datetime.utcnow(),
            trigger_count=0,
            failure_count=0
        )
        
        self.session.add(webhook)
        await self.session.commit()
        await self.session.refresh(webhook)
        
        return webhook
    
    async def get_by_id(self, webhook_id: uuid.UUID) -> Optional[WebhookRow]:
        """Get webhook by ID."""
        result = await self.session.execute(
            select(WebhookRow).where(WebhookRow.webhook_id == webhook_id)
        )
        return result.scalar_one_or_none()
    
    async def list_all(self) -> list[WebhookRow]:
        """List all webhooks."""
        result = await self.session.execute(
            select(WebhookRow).order_by(WebhookRow.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def list_by_event(self, event_type: str) -> list[WebhookRow]:
        """
        List all enabled webhooks subscribed to an event.
        
        Args:
            event_type: Event type to filter by
        
        Returns:
            List of matching webhooks
        """
        result = await self.session.execute(
            select(WebhookRow).where(
                and_(
                    WebhookRow.enabled.is_(True),
                    WebhookRow.events.like(f"%{event_type}%")
                )
            )
        )
        return list(result.scalars().all())
    
    async def update(
        self,
        webhook_id: uuid.UUID,
        url: Optional[str] = None,
        events: Optional[list[str]] = None,
        secret: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> Optional[WebhookRow]:
        """Update webhook configuration."""
        webhook = await self.get_by_id(webhook_id)
        if not webhook:
            return None
        
        if url is not None:
            webhook.url = url
        if events is not None:
            webhook.events = ",".join(events)
        if secret is not None:
            webhook.secret = secret
        if enabled is not None:
            webhook.enabled = enabled
        
        await self.session.commit()
        await self.session.refresh(webhook)
        return webhook
    
    async def delete(self, webhook_id: uuid.UUID) -> bool:
        """Delete a webhook."""
        webhook = await self.get_by_id(webhook_id)
        if not webhook:
            return False
        
        await self.session.delete(webhook)
        await self.session.commit()
        return True
    
    async def record_success(
        self,
        webhook_id: uuid.UUID
    ) -> None:
        """Record successful delivery."""
        webhook = await self.get_by_id(webhook_id)
        if webhook:
            webhook.last_triggered_at = datetime.utcnow()
            webhook.trigger_count += 1
            await self.session.commit()
    
    async def record_failure(
        self,
        webhook_id: uuid.UUID
    ) -> None:
        """Record failed delivery."""
        webhook = await self.get_by_id(webhook_id)
        if webhook:
            webhook.failure_count += 1
            await self.session.commit()


class WebhookDeliveryRepository:
    """Repository for webhook delivery logs."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(
        self,
        webhook_id: uuid.UUID,
        event_type: str,
        payload: str,
        response_status: Optional[int] = None,
        response_body: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> WebhookDeliveryRow:
        """
        Create delivery log entry.
        
        Args:
            webhook_id: Webhook ID
            event_type: Event type
            payload: JSON payload sent
            response_status: HTTP status code
            response_body: Response body (truncated)
            error: Error message if failed
            duration_ms: Request duration
        
        Returns:
            Created WebhookDeliveryRow
        """
        # Truncate response body to 4KB
        if response_body and len(response_body) > 4096:
            response_body = response_body[:4096] + "... (truncated)"
        
        delivery = WebhookDeliveryRow(
            webhook_id=webhook_id,
            event_type=event_type,
            payload=payload,
            response_status=response_status,
            response_body=response_body,
            error=error,
            delivered_at=datetime.utcnow(),
            duration_ms=duration_ms
        )
        
        self.session.add(delivery)
        await self.session.commit()
        await self.session.refresh(delivery)
        
        return delivery
    
    async def list_for_webhook(
        self,
        webhook_id: uuid.UUID,
        limit: int = 100
    ) -> list[WebhookDeliveryRow]:
        """
        List delivery history for a webhook.
        
        Args:
            webhook_id: Webhook ID
            limit: Maximum number of results
        
        Returns:
            List of delivery records (most recent first)
        """
        result = await self.session.execute(
            select(WebhookDeliveryRow)
            .where(WebhookDeliveryRow.webhook_id == webhook_id)
            .order_by(desc(WebhookDeliveryRow.delivered_at))
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def list_recent(
        self,
        limit: int = 100
    ) -> list[WebhookDeliveryRow]:
        """
        List recent deliveries across all webhooks.
        
        Args:
            limit: Maximum number of results
        
        Returns:
            List of delivery records (most recent first)
        """
        result = await self.session.execute(
            select(WebhookDeliveryRow)
            .order_by(desc(WebhookDeliveryRow.delivered_at))
            .limit(limit)
        )
        return list(result.scalars().all())

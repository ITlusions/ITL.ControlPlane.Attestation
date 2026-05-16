"""
Webhook delivery service.

Sends HTTP POST requests to configured webhooks with event payloads.
"""

import hmac
import hashlib
import time
from datetime import datetime
from typing import Optional
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import WebhookRepository, WebhookDeliveryRepository
from .schemas import WebhookEventPayload


class WebhookDeliverer:
    """
    Service for delivering webhook events.
    
    Sends HTTP POST requests to configured webhooks.
    Includes HMAC-SHA256 signature for verification.
    Logs all delivery attempts.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.webhook_repo = WebhookRepository(session)
        self.delivery_repo = WebhookDeliveryRepository(session)
    
    async def trigger_event(
        self,
        event_type: str,
        machine_id: Optional[uuid.UUID] = None,
        data: dict = None
    ) -> int:
        """
        Trigger an event and deliver to all subscribed webhooks.
        
        Args:
            event_type: Event type (e.g., 'machine.approved')
            machine_id: Machine ID if applicable
            data: Event-specific data
        
        Returns:
            Number of webhooks triggered
        """
        # Get all webhooks subscribed to this event
        webhooks = await self.webhook_repo.list_by_event(event_type)
        
        if not webhooks:
            return 0
        
        # Build payload
        payload = WebhookEventPayload(
            event_type=event_type,
            timestamp=datetime.utcnow(),
            machine_id=machine_id,
            data=data or {}
        )
        
        payload_json = payload.model_dump_json()
        
        # Deliver to each webhook
        async with httpx.AsyncClient(timeout=10.0) as client:
            for webhook in webhooks:
                await self._deliver_to_webhook(
                    client=client,
                    webhook_id=webhook.webhook_id,
                    url=webhook.url,
                    secret=webhook.secret,
                    payload_json=payload_json,
                    event_type=event_type
                )
        
        return len(webhooks)
    
    async def _deliver_to_webhook(
        self,
        client: httpx.AsyncClient,
        webhook_id: uuid.UUID,
        url: str,
        secret: Optional[str],
        payload_json: str,
        event_type: str
    ) -> None:
        """
        Deliver event to a single webhook.
        
        Args:
            client: httpx client
            webhook_id: Webhook ID
            url: Target URL
            secret: HMAC secret (optional)
            payload_json: JSON payload
            event_type: Event type
        """
        start_time = time.time()
        
        # Build headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ITL-Attestation-Webhooks/1.0",
            "X-Webhook-Event": event_type
        }
        
        # Add HMAC signature if secret is configured
        if secret:
            signature = hmac.new(
                secret.encode("utf-8"),
                payload_json.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
        
        try:
            # Send POST request
            response = await client.post(
                url,
                content=payload_json,
                headers=headers
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log delivery
            await self.delivery_repo.create(
                webhook_id=webhook_id,
                event_type=event_type,
                payload=payload_json,
                response_status=response.status_code,
                response_body=response.text,
                error=None,
                duration_ms=duration_ms
            )
            
            # Update webhook stats
            if 200 <= response.status_code < 300:
                await self.webhook_repo.record_success(webhook_id)
            else:
                await self.webhook_repo.record_failure(webhook_id)
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Log failed delivery
            await self.delivery_repo.create(
                webhook_id=webhook_id,
                event_type=event_type,
                payload=payload_json,
                response_status=None,
                response_body=None,
                error=str(e),
                duration_ms=duration_ms
            )
            
            # Update failure count
            await self.webhook_repo.record_failure(webhook_id)

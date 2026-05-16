"""
Webhooks extension for attestation service.

Allows operators to register HTTP endpoints that receive attestation events.
"""

from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from sdk import AttestationExtension
from attestation.core.database import get_session
from attestation.core.auth import get_current_user

from .repository import WebhookRepository, WebhookDeliveryRepository
from .deliverer import WebhookDeliverer
from .models import WebhookRow, WebhookDeliveryRow
from .schemas import (
    WebhookCreateRequest,
    WebhookUpdateRequest,
    WebhookResponse,
    WebhookListResponse,
    WebhookDeliveryListResponse,
    WebhookEventPayload
)


class WebhooksExtension(AttestationExtension):
    """
    Webhooks extension.
    
    Allows operators to register HTTP endpoints that receive events
    such as machine registration, approval, revocation, etc.
    
    Features:
    - Configure webhooks with URL and event filters
    - HMAC-SHA256 signatures for verification
    - Delivery history and audit log
    - Test endpoint for validation
    """
    
    @property
    def name(self) -> str:
        return "webhooks"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "HTTP webhook delivery for attestation events"
    
    def get_router(self) -> APIRouter:
        """Return FastAPI router with webhook endpoints."""
        router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])
        
        # Create webhook
        @router.post(
            "/",
            response_model=WebhookResponse,
            status_code=status.HTTP_201_CREATED
        )
        async def create_webhook(
            request: WebhookCreateRequest,
            session: Annotated[AsyncSession, Depends(get_session)],
            user: Annotated[dict, Depends(get_current_user)]
        ):
            """
            Create a new webhook.
            
            The webhook will receive HTTP POST requests when subscribed events occur.
            Optional HMAC secret for signature verification.
            """
            repo = WebhookRepository(session)
            
            webhook = await repo.create(
                url=request.url,
                events=request.events,
                created_by=user["cn"],
                secret=request.secret
            )
            
            return WebhookResponse.from_row(webhook)
        
        # List webhooks
        @router.get("/", response_model=WebhookListResponse)
        async def list_webhooks(
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """List all configured webhooks."""
            repo = WebhookRepository(session)
            webhooks = await repo.list_all()
            
            return WebhookListResponse(
                webhooks=[WebhookResponse.from_row(w) for w in webhooks],
                total=len(webhooks)
            )
        
        # Get webhook by ID
        @router.get("/{webhook_id}", response_model=WebhookResponse)
        async def get_webhook(
            webhook_id: uuid.UUID,
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """Get webhook details."""
            repo = WebhookRepository(session)
            webhook = await repo.get_by_id(webhook_id)
            
            if not webhook:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Webhook {webhook_id} not found"
                )
            
            return WebhookResponse.from_row(webhook)
        
        # Update webhook
        @router.put("/{webhook_id}", response_model=WebhookResponse)
        async def update_webhook(
            webhook_id: uuid.UUID,
            request: WebhookUpdateRequest,
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """Update webhook configuration."""
            repo = WebhookRepository(session)
            
            webhook = await repo.update(
                webhook_id=webhook_id,
                url=request.url,
                events=request.events,
                secret=request.secret,
                enabled=request.enabled
            )
            
            if not webhook:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Webhook {webhook_id} not found"
                )
            
            return WebhookResponse.from_row(webhook)
        
        # Delete webhook
        @router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
        async def delete_webhook(
            webhook_id: uuid.UUID,
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """Delete a webhook."""
            repo = WebhookRepository(session)
            deleted = await repo.delete(webhook_id)
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Webhook {webhook_id} not found"
                )
        
        # Get delivery history
        @router.get("/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
        async def get_delivery_history(
            webhook_id: uuid.UUID,
            limit: int = 100,
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """
            Get delivery history for a webhook.
            
            Returns the most recent delivery attempts (up to limit).
            """
            # Verify webhook exists
            webhook_repo = WebhookRepository(session)
            webhook = await webhook_repo.get_by_id(webhook_id)
            if not webhook:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Webhook {webhook_id} not found"
                )
            
            # Get deliveries
            delivery_repo = WebhookDeliveryRepository(session)
            deliveries = await delivery_repo.list_for_webhook(webhook_id, limit)
            
            return WebhookDeliveryListResponse(
                deliveries=[d.__dict__ for d in deliveries],
                total=len(deliveries)
            )
        
        # Test webhook
        @router.post("/{webhook_id}/test", status_code=status.HTTP_202_ACCEPTED)
        async def test_webhook(
            webhook_id: uuid.UUID,
            session: Annotated[AsyncSession, Depends(get_session)],
            _user: Annotated[dict, Depends(get_current_user)]
        ):
            """
            Send a test event to the webhook.
            
            Useful for validating the endpoint and signature verification.
            """
            # Get webhook
            repo = WebhookRepository(session)
            webhook = await repo.get_by_id(webhook_id)
            
            if not webhook:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Webhook {webhook_id} not found"
                )
            
            # Trigger test event
            deliverer = WebhookDeliverer(session)
            await deliverer.trigger_event(
                event_type="webhook.test",
                machine_id=None,
                data={"message": "Test event from ITL Attestation"}
            )
            
            return {"status": "test event sent"}
        
        return router
    
    def get_models(self) -> list[type]:
        """Return SQLModel table classes for migration generation."""
        return [WebhookRow, WebhookDeliveryRow]

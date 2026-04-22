import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ContactRequest, Tenant
from app.schemas import ContactCreate, ContactResponse
from app.services.email import send_contact_notification
from app.services.webhooks import fire_webhook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["contact"])


@router.post("/contact", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_request(
    data: ContactCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit a contact/human handoff request."""
    result = await db.execute(
        select(Tenant).where(Tenant.slug == data.org_id, Tenant.active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    contact = ContactRequest(
        tenant_id=tenant.id,
        visitor_name=data.visitor_name,
        visitor_email=data.visitor_email,
        message=data.message,
        conversation_id=data.conversation_id,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)

    # Feature 11: Webhook notification
    await fire_webhook(tenant, "contact_request.created", {
        "contact_id": str(contact.id),
        "visitor_name": data.visitor_name,
        "visitor_email": data.visitor_email,
        "message": data.message,
        "conversation_id": str(data.conversation_id) if data.conversation_id else None,
    })

    # Feature 40: Email notification
    if tenant.email_notifications_enabled and tenant.support_email:
        try:
            await send_contact_notification(
                tenant_name=tenant.name,
                support_email=tenant.support_email,
                visitor_name=data.visitor_name,
                visitor_email=data.visitor_email,
                message=data.message,
                conversation_id=str(data.conversation_id) if data.conversation_id else None,
            )
        except Exception:
            logger.exception("Failed to send contact notification email")

    return contact

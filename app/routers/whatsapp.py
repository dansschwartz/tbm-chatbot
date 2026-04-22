"""Feature 39: WhatsApp integration via Twilio webhook."""

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Conversation, Message, Tenant
from app.services.rag import run_rag_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["whatsapp"])


def _get_twilio_credentials(tenant: Tenant) -> tuple[str, str, str]:
    """Get Twilio credentials — tenant-level first, then env fallback."""
    sid = tenant.twilio_account_sid or settings.twilio_account_sid
    token = tenant.twilio_auth_token or settings.twilio_auth_token
    number = tenant.twilio_whatsapp_number or settings.twilio_whatsapp_number
    return sid, token, number


async def _send_whatsapp_reply(to: str, body: str, sid: str, token: str, from_number: str):
    """Send a WhatsApp message via Twilio API."""
    import httpx

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            url,
            auth=(sid, token),
            data={
                "From": f"whatsapp:{from_number}",
                "To": to,
                "Body": body,
            },
        )
        resp.raise_for_status()
        logger.info("WhatsApp reply sent to %s", to)


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive incoming WhatsApp messages from Twilio and respond via RAG pipeline."""
    form = await request.form()
    from_number = form.get("From", "")  # e.g. "whatsapp:+1234567890"
    body = form.get("Body", "").strip()
    to_number = form.get("To", "")  # Our Twilio WhatsApp number

    if not body or not from_number:
        return Response(content="<Response></Response>", media_type="application/xml")

    # Find tenant by WhatsApp number
    clean_to = to_number.replace("whatsapp:", "").strip()
    result = await db.execute(
        select(Tenant).where(
            Tenant.whatsapp_enabled.is_(True),
            Tenant.active.is_(True),
        )
    )
    tenants = result.scalars().all()

    # Match tenant by their configured Twilio number or env default
    tenant = None
    for t in tenants:
        t_number = t.twilio_whatsapp_number or settings.twilio_whatsapp_number
        if t_number and t_number.replace("+", "") == clean_to.replace("+", ""):
            tenant = t
            break

    # If only one WhatsApp-enabled tenant, use it
    if not tenant and len(tenants) == 1:
        tenant = tenants[0]

    if not tenant:
        logger.warning("No WhatsApp-enabled tenant found for number %s", clean_to)
        return Response(content="<Response></Response>", media_type="application/xml")

    # Use phone number as session_id
    session_id = f"wa_{from_number.replace('whatsapp:', '').replace('+', '')}"

    # Get or create conversation
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.session_id == session_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        conversation = Conversation(
            tenant_id=tenant.id,
            session_id=session_id,
            channel="whatsapp",
        )
        db.add(conversation)
        await db.flush()

    # Store user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=body,
        tokens_used=0,
    )
    db.add(user_msg)

    # Run RAG pipeline
    try:
        rag_result = await run_rag_pipeline(db, tenant, body)
        response_text = rag_result["response"]

        # Store assistant message
        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response_text,
            tokens_used=rag_result["tokens_used"],
            is_fallback=rag_result.get("is_fallback", False),
        )
        db.add(assistant_msg)

    except Exception:
        logger.exception("RAG pipeline failed for WhatsApp message")
        response_text = "I'm sorry, I'm having trouble right now. Please try again later."

    # Send reply via Twilio API
    sid, token, wa_number = _get_twilio_credentials(tenant)
    if sid and token and wa_number:
        try:
            await _send_whatsapp_reply(from_number, response_text, sid, token, wa_number)
        except Exception:
            logger.exception("Failed to send WhatsApp reply to %s", from_number)

    # Return empty TwiML (we send via API instead)
    return Response(content="<Response></Response>", media_type="application/xml")

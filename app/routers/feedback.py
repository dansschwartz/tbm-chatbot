import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, Message, MessageFeedback, Tenant
from app.schemas import FeedbackCreate, FeedbackResponse
from app.services.email import send_negative_feedback_alert
from app.services.webhooks import fire_webhook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit thumbs up/down feedback on a bot message."""
    result = await db.execute(select(Message).where(Message.id == data.message_id))
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Look up conversation to get tenant_id
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == message.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Check for existing feedback on this message
    existing = await db.execute(
        select(MessageFeedback).where(MessageFeedback.message_id == data.message_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feedback already submitted for this message")

    feedback = MessageFeedback(
        message_id=data.message_id,
        conversation_id=conversation.id,
        tenant_id=conversation.tenant_id,
        rating=data.rating,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    # Feature 11: Webhook on negative feedback
    if data.rating == "negative":
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == conversation.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant:
            await fire_webhook(tenant, "feedback.negative", {
                "feedback_id": str(feedback.id),
                "message_id": str(data.message_id),
                "conversation_id": str(conversation.id),
                "message_content": message.content[:500],
            })
            # Feature 40: Email alert on negative feedback
            if tenant.email_notifications_enabled and tenant.support_email:
                # Get the user question that preceded this bot message
                user_q_result = await db.execute(
                    select(Message.content).where(
                        Message.conversation_id == conversation.id,
                        Message.role == "user",
                        Message.created_at < message.created_at,
                    ).order_by(Message.created_at.desc()).limit(1)
                )
                user_question = user_q_result.scalar_one_or_none() or "(unknown)"
                try:
                    await send_negative_feedback_alert(
                        tenant_name=tenant.name,
                        support_email=tenant.support_email,
                        user_question=user_question,
                        bot_response=message.content[:500],
                        conversation_id=str(conversation.id),
                    )
                except Exception:
                    logger.exception("Failed to send negative feedback email alert")

    return feedback

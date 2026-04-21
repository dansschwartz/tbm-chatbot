import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Message, MessageFeedback, Conversation
from app.schemas import FeedbackCreate, FeedbackResponse

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
    return feedback

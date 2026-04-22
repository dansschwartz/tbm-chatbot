import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Conversation, CSATRating
from app.schemas import CSATCreate, CSATResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["csat"])


@router.post("/csat", response_model=CSATResponse, status_code=status.HTTP_201_CREATED)
async def submit_csat(
    data: CSATCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit a CSAT rating for a conversation."""
    # Look up conversation
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == data.conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Check for existing CSAT on this conversation
    existing = await db.execute(
        select(CSATRating).where(CSATRating.conversation_id == data.conversation_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CSAT rating already submitted for this conversation")

    rating = CSATRating(
        conversation_id=data.conversation_id,
        tenant_id=conversation.tenant_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(rating)
    await db.flush()
    await db.refresh(rating)
    return rating

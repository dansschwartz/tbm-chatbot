import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_admin_key
from app.models import Conversation, Document, Message, MessageFeedback, ContactRequest, Tenant
from app.schemas import (
    ContactResponse,
    ConversationLog,
    FeedbackResponse,
    MessageLog,
    UnansweredMessage,
    UsageStats,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/usage", response_model=list[UsageStats])
async def get_usage_stats(
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    tenants_result = await db.execute(select(Tenant).order_by(Tenant.name))
    tenants = tenants_result.scalars().all()

    stats = []
    for tenant in tenants:
        conv_count = await db.execute(
            select(func.count(Conversation.id)).where(Conversation.tenant_id == tenant.id)
        )
        msg_count = await db.execute(
            select(func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant.id)
        )
        token_sum = await db.execute(
            select(func.coalesce(func.sum(Message.tokens_used), 0))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.tenant_id == tenant.id)
        )
        doc_count = await db.execute(
            select(func.count(Document.id)).where(Document.tenant_id == tenant.id)
        )

        stats.append(
            UsageStats(
                tenant_id=tenant.id,
                tenant_name=tenant.name,
                total_conversations=conv_count.scalar() or 0,
                total_messages=msg_count.scalar() or 0,
                total_tokens=token_sum.scalar() or 0,
                documents_count=doc_count.scalar() or 0,
            )
        )

    return stats


@router.get("/tenants/{tenant_id}/conversations", response_model=list[ConversationLog])
async def get_conversations(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Conversation.id,
            Conversation.session_id,
            Conversation.started_at,
            Conversation.last_message_at,
            Conversation.visitor_name,
            Conversation.visitor_email,
            Conversation.tags,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.id)
        .order_by(Conversation.last_message_at.desc())
    )

    rows = result.all()
    return [
        ConversationLog(
            id=row.id,
            session_id=row.session_id,
            started_at=row.started_at,
            last_message_at=row.last_message_at,
            message_count=row.message_count,
            visitor_name=row.visitor_name,
            visitor_email=row.visitor_email,
            tags=row.tags,
        )
        for row in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageLog])
async def get_messages(
    conversation_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()


# Feature 2: Admin endpoint to list contact requests
@router.get("/contacts", response_model=list[ContactResponse])
async def get_contacts(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContactRequest)
        .where(ContactRequest.tenant_id == tenant_id)
        .order_by(ContactRequest.created_at.desc())
    )
    return result.scalars().all()


# Feature 7: Admin endpoint to view feedback
@router.get("/feedback", response_model=list[FeedbackResponse])
async def get_feedback(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MessageFeedback)
        .where(MessageFeedback.tenant_id == tenant_id)
        .order_by(MessageFeedback.created_at.desc())
    )
    return result.scalars().all()


# Feature 9: Admin endpoint to view unanswered/fallback messages
@router.get("/unanswered", response_model=list[UnansweredMessage])
async def get_unanswered(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Return fallback bot messages paired with the user question that triggered them."""
    # Get fallback assistant messages for this tenant
    result = await db.execute(
        select(
            Message.id.label("message_id"),
            Message.conversation_id,
            Conversation.session_id,
            Message.content.label("bot_response"),
            Message.created_at,
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.is_fallback.is_(True),
        )
        .order_by(Message.created_at.desc())
        .limit(100)
    )
    rows = result.all()

    unanswered = []
    for row in rows:
        # Find the user message immediately before this bot response
        user_msg_result = await db.execute(
            select(Message.content)
            .where(
                Message.conversation_id == row.conversation_id,
                Message.role == "user",
                Message.created_at < row.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        user_question = user_msg_result.scalar_one_or_none() or "(unknown)"

        unanswered.append(
            UnansweredMessage(
                message_id=row.message_id,
                conversation_id=row.conversation_id,
                session_id=row.session_id,
                user_question=user_question,
                bot_response=row.bot_response,
                created_at=row.created_at,
            )
        )

    return unanswered

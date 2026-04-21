import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_admin_key
from app.models import Conversation, Document, Message, Tenant
from app.schemas import ConversationLog, MessageLog, UsageStats

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

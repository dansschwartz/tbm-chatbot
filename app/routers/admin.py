import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_admin_key
from app.models import (
    Conversation,
    CSATRating,
    Document,
    Message,
    MessageFeedback,
    ContactRequest,
    Tenant,
)
from app.routers.chat import get_daily_count
from app.schemas import (
    AnalyticsSummary,
    ContactResponse,
    ConversationLog,
    ConversationSearchResult,
    CSATResponse,
    FeedbackResponse,
    MessageLog,
    MessagesPerDay,
    TagCount,
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


# Feature 12: CSAT endpoints
@router.get("/csat", response_model=list[CSATResponse])
async def get_csat_ratings(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """List CSAT ratings for a tenant."""
    result = await db.execute(
        select(CSATRating)
        .where(CSATRating.tenant_id == tenant_id)
        .order_by(CSATRating.created_at.desc())
    )
    return result.scalars().all()


# Feature 20: Analytics summary endpoint
@router.get("/analytics", response_model=AnalyticsSummary)
async def get_analytics(
    tenant_id: uuid.UUID,
    days: int = Query(default=30, ge=1, le=365),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Comprehensive analytics summary for a tenant."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total conversations
    total_convs = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.tenant_id == tenant_id,
            Conversation.started_at >= since,
        )
    )).scalar() or 0

    # Total messages
    total_msgs = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id, Message.created_at >= since)
    )).scalar() or 0

    # Avg messages per conversation
    avg_msgs = round(total_msgs / total_convs, 2) if total_convs > 0 else 0.0

    # Total contact requests
    total_contacts = (await db.execute(
        select(func.count(ContactRequest.id)).where(
            ContactRequest.tenant_id == tenant_id,
            ContactRequest.created_at >= since,
        )
    )).scalar() or 0

    # Resolution rate (non-fallback %)
    total_assistant_msgs = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.created_at >= since,
        )
    )).scalar() or 0

    fallback_msgs = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.is_fallback.is_(True),
            Message.created_at >= since,
        )
    )).scalar() or 0

    resolution_rate = round(
        ((total_assistant_msgs - fallback_msgs) / total_assistant_msgs * 100) if total_assistant_msgs > 0 else 0.0,
        1,
    )

    # Avg CSAT score
    avg_csat_result = (await db.execute(
        select(func.avg(CSATRating.rating)).where(
            CSATRating.tenant_id == tenant_id,
            CSATRating.created_at >= since,
        )
    )).scalar()
    avg_csat = round(float(avg_csat_result), 2) if avg_csat_result is not None else None

    # Top tags
    convs_result = await db.execute(
        select(Conversation.tags).where(
            Conversation.tenant_id == tenant_id,
            Conversation.started_at >= since,
            Conversation.tags.isnot(None),
        )
    )
    tag_counter: Counter = Counter()
    for (tags,) in convs_result.all():
        if tags:
            for tag in tags:
                tag_counter[tag] += 1
    top_tags = [TagCount(tag=t, count=c) for t, c in tag_counter.most_common(10)]

    # Messages per day
    msgs_per_day_result = await db.execute(
        select(
            func.date_trunc("day", Message.created_at).label("day"),
            func.count(Message.id).label("cnt"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id, Message.created_at >= since)
        .group_by("day")
        .order_by("day")
    )
    messages_per_day = [
        MessagesPerDay(date=row.day.strftime("%Y-%m-%d"), count=row.cnt)
        for row in msgs_per_day_result.all()
    ]

    # Busiest hours
    hours_result = await db.execute(
        select(
            func.extract("hour", Message.created_at).label("hr"),
            func.count(Message.id).label("cnt"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id, Message.created_at >= since)
        .group_by("hr")
        .order_by(func.count(Message.id).desc())
        .limit(5)
    )
    busiest_hours = [int(row.hr) for row in hours_result.all()]

    # Feature 22: Daily usage count
    daily_usage = get_daily_count(str(tenant_id))

    return AnalyticsSummary(
        total_conversations=total_convs,
        total_messages=total_msgs,
        avg_messages_per_conversation=avg_msgs,
        total_contact_requests=total_contacts,
        resolution_rate=resolution_rate,
        avg_csat_score=avg_csat,
        top_tags=top_tags,
        messages_per_day=messages_per_day,
        busiest_hours=busiest_hours,
        daily_message_usage=daily_usage,
    )


# Feature 21: Conversation search
@router.get("/conversations/search", response_model=list[ConversationSearchResult])
async def search_conversations(
    tenant_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=500),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across message content for a tenant."""
    search_pattern = f"%{q}%"
    result = await db.execute(
        select(
            Message.id.label("message_id"),
            Message.conversation_id,
            Conversation.session_id,
            Conversation.visitor_name,
            Conversation.visitor_email,
            Message.role,
            Message.content,
            Message.created_at,
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.content.ilike(search_pattern),
        )
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    rows = result.all()

    results = []
    for row in rows:
        # Create a snippet around the match
        content = row.content
        lower_content = content.lower()
        lower_q = q.lower()
        idx = lower_content.find(lower_q)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content), idx + len(q) + 50)
            snippet = ("..." if start > 0 else "") + content[start:end] + ("..." if end < len(content) else "")
        else:
            snippet = content[:150] + ("..." if len(content) > 150 else "")

        results.append(
            ConversationSearchResult(
                conversation_id=row.conversation_id,
                session_id=row.session_id,
                visitor_name=row.visitor_name,
                visitor_email=row.visitor_email,
                message_id=row.message_id,
                role=row.role,
                snippet=snippet,
                created_at=row.created_at,
            )
        )

    return results

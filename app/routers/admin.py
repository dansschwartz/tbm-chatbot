import csv
import io
import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import require_admin_key
from app.models import (
    Conversation,
    ConversationNote,
    CSATRating,
    Document,
    DocumentChunk,
    Message,
    MessageFeedback,
    ContactRequest,
    ScheduledMessage,
    Tenant,
)
from app.routers.chat import get_daily_count
from app.schemas import (
    ABTestResult,
    AnalyticsSummary,
    ContactResponse,
    ConversationLog,
    ConversationNoteCreate,
    ConversationNoteResponse,
    ConversationSearchResult,
    CSATResponse,
    FeedbackResponse,
    Insight,
    MessageLog,
    MessagesPerDay,
    ScheduledMessageCreate,
    ScheduledMessageResponse,
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
            Conversation.summary,
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
            summary=row.summary,
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

    # Feature 32: Average response time
    avg_rt_result = (await db.execute(
        select(func.avg(Message.response_time_ms))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.response_time_ms.isnot(None),
            Message.created_at >= since,
        )
    )).scalar()
    avg_response_time = round(float(avg_rt_result), 1) if avg_rt_result is not None else None

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
        avg_response_time_ms=avg_response_time,
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


# ── Feature 29: Scheduled Messages CRUD ──────────────────────────────────────

@router.post("/scheduled-messages", response_model=ScheduledMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_message(
    data: ScheduledMessageCreate,
    tenant_id: uuid.UUID = Query(...),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    sm = ScheduledMessage(
        tenant_id=tenant_id,
        message=data.message,
        target=data.target,
        active=data.active,
        start_date=data.start_date,
        end_date=data.end_date,
    )
    db.add(sm)
    await db.flush()
    await db.refresh(sm)
    return sm


@router.get("/scheduled-messages", response_model=list[ScheduledMessageResponse])
async def list_scheduled_messages(
    tenant_id: uuid.UUID = Query(...),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduledMessage)
        .where(ScheduledMessage.tenant_id == tenant_id)
        .order_by(ScheduledMessage.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/scheduled-messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_message(
    message_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ScheduledMessage).where(ScheduledMessage.id == message_id))
    sm = result.scalar_one_or_none()
    if not sm:
        raise HTTPException(status_code=404, detail="Scheduled message not found")
    await db.delete(sm)


# ── Feature 31: Conversation Notes ───────────────────────────────────────────

@router.post("/conversations/{conversation_id}/notes", response_model=ConversationNoteResponse, status_code=status.HTTP_201_CREATED)
async def add_conversation_note(
    conversation_id: uuid.UUID,
    data: ConversationNoteCreate,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    note = ConversationNote(
        conversation_id=conversation_id,
        tenant_id=conversation.tenant_id,
        author=data.author,
        content=data.content,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    return note


@router.get("/conversations/{conversation_id}/notes", response_model=list[ConversationNoteResponse])
async def list_conversation_notes(
    conversation_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ConversationNote)
        .where(ConversationNote.conversation_id == conversation_id)
        .order_by(ConversationNote.created_at)
    )
    return result.scalars().all()


# ── Feature 41: Conversation Export ─────────────────────────────────────────

@router.get("/export/conversations")
async def export_conversations(
    tenant_id: uuid.UUID = Query(...),
    format: str = Query(default="json", pattern=r"^(json|csv)$"),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Export all conversations for a tenant as JSON or CSV."""
    result = await db.execute(
        select(
            Conversation.id,
            Conversation.session_id,
            Conversation.visitor_name,
            Conversation.visitor_email,
            Conversation.started_at,
            Conversation.tags,
            Conversation.summary,
            Conversation.channel,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.tenant_id == tenant_id)
        .group_by(Conversation.id)
        .order_by(Conversation.started_at.desc())
    )
    rows = result.all()

    # Get CSAT ratings
    csat_result = await db.execute(
        select(CSATRating.conversation_id, CSATRating.rating)
        .where(CSATRating.tenant_id == tenant_id)
    )
    csat_map = {str(r.conversation_id): r.rating for r in csat_result.all()}

    records = []
    for row in rows:
        records.append({
            "conversation_id": str(row.id),
            "visitor_name": row.visitor_name or "",
            "visitor_email": row.visitor_email or "",
            "started_at": row.started_at.isoformat() if row.started_at else "",
            "message_count": row.message_count,
            "tags": ",".join(row.tags) if row.tags else "",
            "summary": row.summary or "",
            "channel": row.channel or "web",
            "csat_rating": csat_map.get(str(row.id), ""),
        })

    if format == "csv":
        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        content = output.getvalue()
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=conversations_{tenant_id}.csv"},
        )

    return records


# ── Feature 44: A/B Test Analytics ──────────────────────────────────────────

@router.get("/ab-test-results", response_model=list[ABTestResult])
async def get_ab_test_results(
    tenant_id: uuid.UUID = Query(...),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Get A/B test results for greeting variants."""
    result = await db.execute(
        select(
            Conversation.greeting_variant_used,
            func.count(Conversation.id).label("conv_count"),
            func.count(Message.id).label("msg_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.greeting_variant_used.isnot(None),
        )
        .group_by(Conversation.greeting_variant_used)
    )
    rows = result.all()
    return [
        ABTestResult(
            variant=row.greeting_variant_used or "default",
            conversation_count=row.conv_count,
            avg_messages=round(row.msg_count / row.conv_count, 2) if row.conv_count > 0 else 0,
        )
        for row in rows
    ]


# ── Feature 45: Smart Insights ──────────────────────────────────────────────

@router.get("/insights", response_model=list[Insight])
async def get_insights(
    tenant_id: uuid.UUID = Query(...),
    days: int = Query(default=30, ge=1, le=365),
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Auto-generate insights based on analytics data."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    insights: list[Insight] = []

    # 1. Unanswered questions analysis
    fallback_count = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.is_fallback.is_(True),
            Message.created_at >= since,
        )
    )).scalar() or 0

    total_bot_msgs = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.created_at >= since,
        )
    )).scalar() or 0

    if total_bot_msgs > 0:
        fallback_pct = round(fallback_count / total_bot_msgs * 100, 1)
        if fallback_pct > 20:
            insights.append(Insight(
                type="content_gap",
                title=f"{fallback_pct}% of questions go unanswered",
                description=f"{fallback_count} out of {total_bot_msgs} bot responses were fallbacks. Review the Unanswered Questions section to identify knowledge base gaps.",
                priority="high",
            ))
        elif fallback_pct > 10:
            insights.append(Insight(
                type="content_gap",
                title=f"{fallback_pct}% fallback rate — room to improve",
                description="Check unanswered questions and add documents covering those topics.",
                priority="medium",
            ))

    # 2. Top unanswered topics
    fallback_msgs = await db.execute(
        select(Message.content)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "user",
            Message.created_at >= since,
        )
        .order_by(Message.created_at.desc())
        .limit(200)
    )
    # Find common question topics from recent messages
    all_user_msgs = [r[0].lower() for r in fallback_msgs.all()]
    topic_counter: Counter = Counter()
    topic_keywords = {
        "hours": ["hours", "open", "close", "schedule"],
        "pricing": ["price", "cost", "fee", "how much", "payment"],
        "location": ["where", "address", "location", "directions", "map"],
        "contact": ["phone", "email", "contact", "reach"],
        "registration": ["register", "sign up", "enroll", "join"],
        "events": ["event", "tournament", "game", "match"],
    }
    for msg in all_user_msgs:
        for topic, keywords in topic_keywords.items():
            if any(kw in msg for kw in keywords):
                topic_counter[topic] += 1

    for topic, count in topic_counter.most_common(3):
        pct = round(count / max(len(all_user_msgs), 1) * 100, 1)
        if pct >= 10:
            insights.append(Insight(
                type="engagement",
                title=f"{pct}% of questions are about {topic}",
                description=f"'{topic}' is a hot topic with {count} questions in {days} days. Ensure your knowledge base covers this well.",
                priority="medium",
            ))

    # 3. CSAT analysis
    avg_csat = (await db.execute(
        select(func.avg(CSATRating.rating)).where(
            CSATRating.tenant_id == tenant_id,
            CSATRating.created_at >= since,
        )
    )).scalar()
    if avg_csat is not None:
        avg_csat = round(float(avg_csat), 2)
        if avg_csat < 3.0:
            insights.append(Insight(
                type="performance",
                title=f"Low CSAT score: {avg_csat}/5",
                description="Customer satisfaction is below average. Review negative feedback and unanswered questions to improve response quality.",
                priority="high",
            ))
        elif avg_csat >= 4.5:
            insights.append(Insight(
                type="performance",
                title=f"Excellent CSAT score: {avg_csat}/5",
                description="Your chatbot is performing well! Keep the knowledge base updated to maintain quality.",
                priority="low",
            ))

    # 4. Negative feedback spike
    neg_feedback = (await db.execute(
        select(func.count(MessageFeedback.id)).where(
            MessageFeedback.tenant_id == tenant_id,
            MessageFeedback.rating == "negative",
            MessageFeedback.created_at >= since,
        )
    )).scalar() or 0
    pos_feedback = (await db.execute(
        select(func.count(MessageFeedback.id)).where(
            MessageFeedback.tenant_id == tenant_id,
            MessageFeedback.rating == "positive",
            MessageFeedback.created_at >= since,
        )
    )).scalar() or 0
    total_feedback = neg_feedback + pos_feedback
    if total_feedback > 5 and neg_feedback > pos_feedback:
        insights.append(Insight(
            type="performance",
            title=f"More thumbs down ({neg_feedback}) than up ({pos_feedback})",
            description="Users are dissatisfied with responses. Review the most recent negative feedback to identify patterns.",
            priority="high",
        ))

    # 5. Document coverage
    doc_count = (await db.execute(
        select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
    )).scalar() or 0
    if doc_count < 5:
        insights.append(Insight(
            type="content_gap",
            title=f"Only {doc_count} documents in knowledge base",
            description="A small knowledge base leads to more unanswered questions. Add more content — FAQs, policies, program details.",
            priority="high" if doc_count < 3 else "medium",
        ))

    # 6. Response time
    avg_rt = (await db.execute(
        select(func.avg(Message.response_time_ms))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.response_time_ms.isnot(None),
            Message.created_at >= since,
        )
    )).scalar()
    if avg_rt is not None and float(avg_rt) > 5000:
        insights.append(Insight(
            type="performance",
            title=f"Slow average response time: {round(float(avg_rt))}ms",
            description="Responses are taking over 5 seconds. This may be due to large documents or high load.",
            priority="medium",
        ))

    return insights

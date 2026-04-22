import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone, date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db, async_session
from app.middleware.auth import get_tenant_by_slug
from app.models import Conversation, Message, ScheduledMessage, Tenant
from app.schemas import ChatRequest, ChatResponse, SourceReference
from app.services.rag import run_rag_pipeline
from app.services.openai_client import chat_completion
from app.services.webhooks import fire_webhook

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

# Simple in-memory rate limiter
_session_timestamps: dict[str, list[float]] = defaultdict(list)
_tenant_timestamps: dict[str, list[float]] = defaultdict(list)

# Feature 22: Daily message counter (resets at midnight UTC)
_daily_counts: dict[str, dict] = {}  # tenant_id -> {"date": "YYYY-MM-DD", "count": int}

# Feature 10: Auto-tagging keyword map
TAG_KEYWORDS = {
    "registration": ["register", "registration", "sign up", "signup", "enroll", "enrollment"],
    "tryouts": ["tryout", "try out", "tryouts", "id session", "evaluation"],
    "financial-aid": ["financial aid", "scholarship", "assistance", "afford", "free", "reduced"],
    "camps": ["camp", "camps", "summer camp", "holiday camp", "spring break"],
    "programs": ["program", "recreational", "travel", "academy", "select", "tots", "pre-travel"],
    "schedules": ["schedule", "calendar", "when", "time", "date"],
    "costs": ["cost", "price", "fee", "tuition", "payment", "how much"],
    "policies": ["policy", "policies", "rule", "rules", "guideline"],
    "contact": ["contact", "email", "phone", "reach", "talk to", "speak with"],
    "futsal": ["futsal", "indoor", "winter league"],
    "safety": ["safety", "concussion", "emergency", "weather", "lightning"],
}


def _check_rate_limit(key: str, store: dict[str, list[float]], limit: int):
    now = time.time()
    window_start = now - 60
    store[key] = [ts for ts in store[key] if ts > window_start]
    if len(store[key]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )
    store[key].append(now)


def _check_daily_quota(tenant: Tenant):
    """Feature 22: Check per-tenant daily message quota."""
    if not tenant.daily_message_limit:
        return
    tenant_key = str(tenant.id)
    today = date.today().isoformat()
    entry = _daily_counts.get(tenant_key)
    if not entry or entry["date"] != today:
        _daily_counts[tenant_key] = {"date": today, "count": 0}
        entry = _daily_counts[tenant_key]
    if entry["count"] >= tenant.daily_message_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily message limit ({tenant.daily_message_limit}) exceeded. Resets at midnight UTC.",
        )


def _increment_daily_count(tenant_id: str):
    today = date.today().isoformat()
    entry = _daily_counts.get(tenant_id)
    if not entry or entry["date"] != today:
        _daily_counts[tenant_id] = {"date": today, "count": 1}
    else:
        entry["count"] += 1


def get_daily_count(tenant_id: str) -> int:
    """Get current daily message count for a tenant."""
    today = date.today().isoformat()
    entry = _daily_counts.get(tenant_id)
    if not entry or entry["date"] != today:
        return 0
    return entry["count"]


def _auto_tag(text: str) -> list[str]:
    """Feature 10: Extract topic tags from message text using keyword matching."""
    lower = text.lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            tags.append(tag)
    return tags


def _check_escalation_triggers(text: str, triggers: list[str] | None) -> bool:
    """Feature 28: Check if user message contains escalation trigger phrases."""
    if not triggers:
        return False
    lower = text.lower()
    return any(t.lower() in lower for t in triggers)


def _check_banned_words(text: str, banned_words: list[str] | None) -> dict | None:
    """Feature 34: Check text against banned words list. Returns flags dict or None."""
    if not banned_words:
        return None
    lower = text.lower()
    found = [w for w in banned_words if w.lower() in lower]
    if found:
        return {"banned_words_detected": found}
    return None


def _filter_banned_response(text: str, banned_words: list[str] | None) -> tuple[str, bool]:
    """Feature 34: Filter bot response for banned words. Returns (text, was_filtered)."""
    if not banned_words:
        return text, False
    lower = text.lower()
    for word in banned_words:
        if word.lower() in lower:
            return "I'm sorry, I can't provide a response to that. Please try rephrasing your question or contact us directly for help.", True
    return text, False


async def _generate_summary(conversation_id, tenant_id):
    """Feature 24: Generate a one-line AI summary of a conversation after 5+ messages."""
    async with async_session() as db:
        try:
            result = await db.execute(
                select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
            )
            messages = result.scalars().all()
            if len(messages) < 5:
                return

            # Check if summary already exists
            conv_result = await db.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = conv_result.scalar_one_or_none()
            if not conversation or conversation.summary:
                return

            transcript = "\n".join(f"{m.role}: {m.content[:200]}" for m in messages[:10])
            result = await chat_completion([
                {"role": "system", "content": "Summarize this conversation in one concise sentence (max 100 words). Focus on the main topic and outcome."},
                {"role": "user", "content": transcript},
            ], max_tokens=100, temperature=0.2)
            conversation.summary = result["content"].strip()[:500]
            await db.commit()
        except Exception:
            logger.warning("Failed to generate conversation summary for %s", conversation_id, exc_info=True)


async def _get_scheduled_messages(db: AsyncSession, tenant_id, is_new: bool) -> list[str]:
    """Feature 29: Get active scheduled messages for a tenant."""
    now = datetime.now(timezone.utc)
    query = select(ScheduledMessage).where(
        ScheduledMessage.tenant_id == tenant_id,
        ScheduledMessage.active.is_(True),
    )
    result = await db.execute(query)
    messages = []
    for sm in result.scalars().all():
        # Check date range
        if sm.start_date and now < sm.start_date.replace(tzinfo=timezone.utc):
            continue
        if sm.end_date and now > sm.end_date.replace(tzinfo=timezone.utc):
            continue
        # Check target
        if sm.target == "all_new" and is_new:
            messages.append(sm.message)
        elif sm.target == "returning" and not is_new:
            messages.append(sm.message)
    return messages


def _is_within_business_hours(business_hours: dict | None) -> bool:
    """Feature 8: Check if current time is within configured business hours."""
    if not business_hours:
        return True

    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        return True

    tz_name = business_hours.get("timezone", "UTC")
    hours = business_hours.get("hours", {})
    if not hours:
        return True

    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        day_abbr = now.strftime("%a").lower()[:3]
        day_hours = hours.get(day_abbr)
        if not day_hours or len(day_hours) < 2:
            return False
        open_time = datetime.strptime(day_hours[0], "%H:%M").time()
        close_time = datetime.strptime(day_hours[1], "%H:%M").time()
        return open_time <= now.time() <= close_time
    except Exception:
        logger.warning("Failed to parse business hours, defaulting to open")
        return True


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    # Resolve tenant
    result = await db.execute(
        select(Tenant).where(Tenant.slug == request.org_id, Tenant.active.is_(True))
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found or inactive")

    # Rate limiting
    _check_rate_limit(request.session_id, _session_timestamps, settings.rate_limit_per_session)
    _check_rate_limit(str(tenant.id), _tenant_timestamps, settings.rate_limit_per_tenant)

    # Feature 22: Daily message quota
    _check_daily_quota(tenant)

    # Get or create conversation
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.session_id == request.session_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
    is_new_conversation = conversation is None
    if not conversation:
        conversation = Conversation(
            tenant_id=tenant.id,
            session_id=request.session_id,
            # Feature 3: Store pre-chat visitor info
            visitor_name=request.visitor_name,
            visitor_email=request.visitor_email,
        )
        db.add(conversation)
        await db.flush()
    elif request.visitor_name and not conversation.visitor_name:
        # Update visitor info if provided later
        conversation.visitor_name = request.visitor_name
        conversation.visitor_email = request.visitor_email

    # Feature 34: Check user message for banned words
    user_content_flags = _check_banned_words(request.message, tenant.banned_words)

    # Store user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
        tokens_used=0,
        content_flags=user_content_flags,
    )
    db.add(user_msg)

    # Feature 32: Start response timer
    response_start = time.time()

    # Feature 28: Check for escalation triggers
    escalation_triggered = _check_escalation_triggers(request.message, tenant.escalation_triggers)

    # Run RAG pipeline
    try:
        rag_result = await run_rag_pipeline(db, tenant, request.message)
    except Exception:
        logger.exception("RAG pipeline failed for tenant %s", tenant.slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response. Please try again.",
        )

    response_text = rag_result["response"]
    is_fallback = rag_result.get("is_fallback", False)
    suggestions = rag_result.get("suggestions", [])

    # Feature 34: Filter bot response for banned words
    response_text, was_filtered = _filter_banned_response(response_text, tenant.banned_words)

    # Feature 28: If escalation triggered, prepend offer to connect with human
    if escalation_triggered:
        escalation_notice = (
            "**It sounds like you'd like to speak with a person.** "
            "I can connect you with our team — just click the contact form below the chat, "
            "or I can continue trying to help.\n\n"
        )
        response_text = escalation_notice + response_text
        # Add escalation tag
        existing_tags = conversation.tags or []
        if "escalation" not in existing_tags:
            conversation.tags = existing_tags + ["escalation"]

    # Feature 8: Prepend away message if outside business hours
    if not _is_within_business_hours(tenant.business_hours) and tenant.away_message:
        response_text = f"**{tenant.away_message}**\n\n{response_text}"

    # Feature 29: Scheduled messages for new conversations
    if is_new_conversation:
        scheduled_msgs = await _get_scheduled_messages(db, tenant.id, is_new_conversation)
        if scheduled_msgs:
            announcement = "\n\n".join(f"📢 {m}" for m in scheduled_msgs)
            response_text = f"{announcement}\n\n---\n\n{response_text}"

    # Feature 32: Calculate response time
    response_time_ms = int((time.time() - response_start) * 1000)

    # Store assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response_text,
        tokens_used=rag_result["tokens_used"],
        is_fallback=is_fallback,
        response_time_ms=response_time_ms,
    )
    db.add(assistant_msg)
    await db.flush()

    # Feature 10: Auto-tag conversation
    new_tags = _auto_tag(request.message)
    if new_tags:
        existing_tags = conversation.tags or []
        merged = list(set(existing_tags + new_tags))
        conversation.tags = merged

    # Feature 22: Increment daily count
    _increment_daily_count(str(tenant.id))

    sources = [SourceReference(**s) for s in rag_result["sources"]]

    # Feature 11: Fire webhooks
    if is_new_conversation:
        await fire_webhook(tenant, "conversation.started", {
            "conversation_id": str(conversation.id),
            "session_id": request.session_id,
            "visitor_name": request.visitor_name,
            "visitor_email": request.visitor_email,
        })
    if is_fallback:
        await fire_webhook(tenant, "fallback.detected", {
            "conversation_id": str(conversation.id),
            "message": request.message,
            "response": response_text,
        })
    # Feature 28: Fire escalation webhook
    if escalation_triggered:
        await fire_webhook(tenant, "escalation.triggered", {
            "conversation_id": str(conversation.id),
            "session_id": request.session_id,
            "trigger_message": request.message,
        })

    # Feature 24: Generate conversation summary after 5+ messages (async, non-blocking)
    msg_count_result = await db.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation.id)
    )
    msg_count = msg_count_result.scalar() or 0
    if msg_count >= 5 and not conversation.summary:
        asyncio.create_task(_generate_summary(conversation.id, tenant.id))

    return ChatResponse(
        response=response_text,
        sources=sources,
        session_id=request.session_id,
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        is_fallback=is_fallback,
        suggestions=suggestions,
    )

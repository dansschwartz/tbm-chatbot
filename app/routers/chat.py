import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_tenant_by_slug
from app.models import Conversation, Message, Tenant
from app.schemas import ChatRequest, ChatResponse, SourceReference
from app.services.rag import run_rag_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

# Simple in-memory rate limiter
_session_timestamps: dict[str, list[float]] = defaultdict(list)
_tenant_timestamps: dict[str, list[float]] = defaultdict(list)

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


def _auto_tag(text: str) -> list[str]:
    """Feature 10: Extract topic tags from message text using keyword matching."""
    lower = text.lower()
    tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            tags.append(tag)
    return tags


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

    # Get or create conversation
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant.id,
            Conversation.session_id == request.session_id,
        )
    )
    conversation = conv_result.scalar_one_or_none()
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

    # Store user message
    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
        tokens_used=0,
    )
    db.add(user_msg)

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

    # Feature 8: Prepend away message if outside business hours
    if not _is_within_business_hours(tenant.business_hours) and tenant.away_message:
        response_text = f"**{tenant.away_message}**\n\n{response_text}"

    # Store assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=response_text,
        tokens_used=rag_result["tokens_used"],
        is_fallback=is_fallback,
    )
    db.add(assistant_msg)
    await db.flush()

    # Feature 10: Auto-tag conversation
    new_tags = _auto_tag(request.message)
    if new_tags:
        existing_tags = conversation.tags or []
        merged = list(set(existing_tags + new_tags))
        conversation.tags = merged

    sources = [SourceReference(**s) for s in rag_result["sources"]]

    return ChatResponse(
        response=response_text,
        sources=sources,
        session_id=request.session_id,
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        is_fallback=is_fallback,
    )

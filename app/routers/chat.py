import logging
import time
from collections import defaultdict

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
        conversation = Conversation(tenant_id=tenant.id, session_id=request.session_id)
        db.add(conversation)
        await db.flush()

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

    # Store assistant message
    assistant_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=rag_result["response"],
        tokens_used=rag_result["tokens_used"],
    )
    db.add(assistant_msg)

    sources = [SourceReference(**s) for s in rag_result["sources"]]

    return ChatResponse(
        response=rag_result["response"],
        sources=sources,
        session_id=request.session_id,
        conversation_id=conversation.id,
    )

"""Feature 23: Knowledge Base Article Viewer — public endpoint for browsing documents."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Document, DocumentChunk, Tenant
from app.schemas import ArticleItem

router = APIRouter(prefix="/api/tenants", tags=["articles"])


@router.get("/{slug}/articles", response_model=list[ArticleItem])
async def list_articles(
    slug: str,
    category: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: browse knowledge base articles for a tenant."""
    # Resolve tenant by slug
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.slug == slug, Tenant.active.is_(True))
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Organization not found")

    query = select(Document).where(
        Document.tenant_id == tenant.id,
        Document.status == "ready",
    )

    if category:
        query = query.where(Document.category == category)

    query = query.order_by(Document.created_at.desc())
    result = await db.execute(query)
    documents = result.scalars().all()

    articles = []
    for doc in documents:
        # Get the first chunk as a snippet
        chunk_result = await db.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .limit(1)
        )
        first_chunk = chunk_result.scalar_one_or_none()
        snippet = (first_chunk[:200] + "...") if first_chunk and len(first_chunk) > 200 else (first_chunk or "")

        # If search filter, check title and snippet
        if search:
            search_lower = search.lower()
            if search_lower not in doc.title.lower() and search_lower not in snippet.lower():
                continue

        articles.append(ArticleItem(
            id=doc.id,
            title=doc.title,
            snippet=snippet,
            source_url=doc.source_url,
            category=doc.category,
        ))

    return articles

import base64
import hashlib
import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.middleware.auth import require_admin_key
from app.models import Document, DocumentChunk, Tenant
from app.schemas import (
    BulkDocumentItem,
    BulkDocumentRequest,
    BulkDocumentResponse,
    DocumentCreate,
    DocumentResponse,
)
from app.schemas import CrawlRequest
from app.services.chunking import chunk_text
from app.services.crawler import crawl_url
from app.services.embeddings import embed_chunks


def _extract_pdf_text(content_b64: str) -> str:
    """Feature 30: Extract text from base64-encoded PDF content."""
    import pdfplumber

    pdf_bytes = base64.b64decode(content_b64)
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tenants/{tenant_id}/documents", tags=["documents"])


async def _process_document(document_id: uuid.UUID, tenant_id: uuid.UUID, content: str):
    async with async_session() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if not document:
                return

            chunks = chunk_text(content)
            if not chunks:
                document.status = "error"
                await db.commit()
                return

            embeddings = await embed_chunks(chunks)

            for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = DocumentChunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    content=chunk_content,
                    embedding=embedding,
                    chunk_metadata={"chunk_index": i, "total_chunks": len(chunks)},
                    chunk_index=i,
                )
                db.add(chunk)

            document.status = "ready"
            document.last_ingested_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Processed document %s: %d chunks", document_id, len(chunks))

        except Exception:
            logger.exception("Failed to process document %s", document_id)
            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                if document:
                    document.status = "error"
                    await db.commit()
            except Exception:
                logger.exception("Failed to update document status")


async def _reingest_document(document_id: uuid.UUID, tenant_id: uuid.UUID, content: str):
    """Feature 18: Re-ingest a document — delete old chunks, re-chunk and re-embed."""
    async with async_session() as db:
        try:
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if not document:
                return

            document.status = "processing"
            await db.commit()

            # Delete old chunks
            await db.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            await db.commit()

            chunks = chunk_text(content)
            if not chunks:
                document.status = "error"
                await db.commit()
                return

            embeddings = await embed_chunks(chunks)

            for i, (chunk_content, embedding) in enumerate(zip(chunks, embeddings)):
                chunk = DocumentChunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    content=chunk_content,
                    embedding=embedding,
                    chunk_metadata={"chunk_index": i, "total_chunks": len(chunks)},
                    chunk_index=i,
                )
                db.add(chunk)

            document.status = "ready"
            document.last_ingested_at = datetime.now(timezone.utc)
            document.content_hash = hashlib.sha256(content.encode()).hexdigest()
            await db.commit()
            logger.info("Re-ingested document %s: %d chunks", document_id, len(chunks))

        except Exception:
            logger.exception("Failed to re-ingest document %s", document_id)
            try:
                result = await db.execute(select(Document).where(Document.id == document_id))
                document = result.scalar_one_or_none()
                if document:
                    document.status = "error"
                    await db.commit()
            except Exception:
                logger.exception("Failed to update document status")


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    tenant_id: uuid.UUID,
    data: DocumentCreate,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    # Verify tenant exists
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    # Feature 30: PDF text extraction
    content = data.content
    if data.content_type == "pdf":
        try:
            content = _extract_pdf_text(data.content)
            if not content.strip():
                raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        except HTTPException:
            raise
        except Exception:
            logger.exception("PDF extraction failed")
            raise HTTPException(status_code=400, detail="Invalid PDF content or extraction failed")

    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Check for duplicate
    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document with identical content already exists")

    document = Document(
        tenant_id=tenant_id,
        title=data.title,
        source_url=data.source_url,
        content_hash=content_hash,
        status="processing",
        content_type=data.content_type,
        category=data.category,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    await _process_document(document.id, tenant_id, content)

    return document


# Feature 17: Bulk document ingestion
@router.post("/bulk", response_model=BulkDocumentResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_documents(
    tenant_id: uuid.UUID,
    data: BulkDocumentRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Bulk ingest multiple documents at once."""
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    succeeded = 0
    failed = 0

    for item in data.documents:
        try:
            content_hash = hashlib.sha256(item.content.encode()).hexdigest()

            # Skip duplicates
            existing = await db.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.content_hash == content_hash,
                )
            )
            if existing.scalar_one_or_none():
                failed += 1
                continue

            document = Document(
                tenant_id=tenant_id,
                title=item.title,
                source_url=item.source_url,
                content_hash=content_hash,
                status="processing",
            )
            db.add(document)
            await db.flush()

            await _process_document(document.id, tenant_id, item.content)
            succeeded += 1

        except Exception:
            logger.exception("Failed to create document '%s'", item.title)
            failed += 1

    return BulkDocumentResponse(total=len(data.documents), succeeded=succeeded, failed=failed)


# Feature 18: Re-ingest document
@router.put("/{document_id}/reingest", response_model=DocumentResponse)
async def reingest_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    data: DocumentCreate,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Re-chunk and re-embed a document with updated content."""
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Update document metadata
    document.title = data.title
    document.source_url = data.source_url
    document.status = "processing"
    await db.flush()
    await db.refresh(document)

    background_tasks.add_task(_reingest_document, document.id, tenant_id, data.content)

    return document


# ── Feature 42: Document Auto-Crawler ───────────────────────────────────────

@router.post("/crawl", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def crawl_document(
    tenant_id: uuid.UUID,
    data: CrawlRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Crawl a URL and auto-create a document from the extracted content."""
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    try:
        crawled = await crawl_url(data.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to crawl URL: {e}")

    title = data.title or crawled["title"]
    content = crawled["content"]
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # Check for duplicate
    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document with identical content already exists")

    document = Document(
        tenant_id=tenant_id,
        title=title,
        source_url=data.url,
        content_hash=content_hash,
        status="processing",
        content_type="text",
        category=data.category,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    await _process_document(document.id, tenant_id, content)

    return document


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    tenant_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.tenant_id == tenant_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    _: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await db.delete(document)

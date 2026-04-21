import hashlib
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.middleware.auth import require_admin_key
from app.models import Document, DocumentChunk, Tenant
from app.schemas import DocumentCreate, DocumentResponse
from app.services.chunking import chunk_text
from app.services.embeddings import embed_chunks

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
                    metadata={"chunk_index": i, "total_chunks": len(chunks)},
                    chunk_index=i,
                )
                db.add(chunk)

            document.status = "ready"
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

    content_hash = hashlib.sha256(data.content.encode()).hexdigest()

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
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    background_tasks.add_task(_process_document, document.id, tenant_id, data.content)

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

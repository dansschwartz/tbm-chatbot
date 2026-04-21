import uuid
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, Document, Tenant
from app.services.embeddings import embed_query
from app.services.openai_client import chat_completion
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are {tenant_name}'s AI assistant.

{custom_system_prompt}

IMPORTANT INSTRUCTIONS:
- ONLY answer questions based on the provided context below.
- If the context does not contain information to answer the question, say "I don't have information about that. Please contact us directly for help with this topic."
- When you use information from the context, be helpful and conversational.
- Do not make up information or draw from knowledge outside the provided context.
- If sources are available, naturally reference them in your response.

CONTEXT:
{context}"""


async def retrieve_relevant_chunks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[dict]:
    top_k = top_k or settings.top_k_chunks

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    query = text("""
        SELECT
            dc.id,
            dc.content,
            dc.chunk_metadata,
            dc.chunk_index,
            d.title AS document_title,
            d.source_url,
            1 - (dc.embedding <=> :embedding::vector) AS similarity
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.tenant_id = :tenant_id
        ORDER BY dc.embedding <=> :embedding::vector
        LIMIT :top_k
    """)

    result = await db.execute(
        query,
        {"tenant_id": str(tenant_id), "embedding": embedding_str, "top_k": top_k},
    )
    rows = result.mappings().all()

    return [
        {
            "content": row["content"],
            "document_title": row["document_title"],
            "source_url": row["source_url"],
            "similarity": float(row["similarity"]),
            "chunk_index": row["chunk_index"],
        }
        for row in rows
    ]


async def run_rag_pipeline(
    db: AsyncSession,
    tenant: Tenant,
    user_message: str,
) -> dict:
    query_embedding = await embed_query(user_message)

    chunks = await retrieve_relevant_chunks(db, tenant.id, query_embedding)

    if chunks:
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            source_label = chunk["document_title"]
            if chunk["source_url"]:
                source_label += f" ({chunk['source_url']})"
            context_parts.append(f"[Source {i}: {source_label}]\n{chunk['content']}")
        context = "\n\n---\n\n".join(context_parts)
    else:
        context = "No relevant context found."

    system_message = SYSTEM_PROMPT_TEMPLATE.format(
        tenant_name=tenant.name,
        custom_system_prompt=tenant.system_prompt,
        context=context,
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]

    result = await chat_completion(messages)

    sources = [
        {
            "document_title": chunk["document_title"],
            "chunk_content": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
            "source_url": chunk["source_url"],
            "relevance_score": chunk["similarity"],
        }
        for chunk in chunks
        if chunk["similarity"] > 0.3
    ]

    return {
        "response": result["content"],
        "tokens_used": result["tokens_used"],
        "sources": sources,
    }

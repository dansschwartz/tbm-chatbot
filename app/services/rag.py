import re
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

{guidance_section}

{contact_section}

IMPORTANT INSTRUCTIONS:
- ONLY answer questions based on the provided context below.
- If the context does not contain information to answer the question, say "I don't have information about that. Please contact us directly for help with this topic."
- When you use information from the context, be helpful and conversational.
- Do not make up information or draw from knowledge outside the provided context.
- If sources are available, naturally reference them in your response.
- If you cannot answer a question or the user asks to speak with someone, tell them they can use the contact form below the chat.{support_email_line}
{language_instruction}
After answering, suggest 2-3 brief follow-up questions the user might want to ask based on the context, formatted exactly as:
SUGGESTIONS: [question 1 | question 2 | question 3]

CONTEXT:
{context}"""


def _parse_suggestions(text: str) -> tuple[str, list[str]]:
    """Extract SUGGESTIONS line from response and return cleaned response + suggestions list."""
    match = re.search(r'SUGGESTIONS:\s*\[([^\]]+)\]\s*$', text, re.MULTILINE)
    if not match:
        return text.strip(), []
    suggestions_str = match.group(1)
    suggestions = [s.strip() for s in suggestions_str.split("|") if s.strip()]
    cleaned = text[:match.start()].strip()
    return cleaned, suggestions

# Similarity threshold below which we consider the response a fallback
FALLBACK_SIMILARITY_THRESHOLD = 0.15  # Lowered — pgvector cosine distance can be subtle


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
            1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.tenant_id = CAST(:tenant_id AS uuid)
        ORDER BY dc.embedding <=> CAST(:embedding AS vector)
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

    # Log similarity scores for debugging
    if chunks:
        logger.info("Top chunk similarities for '%s': %s", user_message[:50],
                     [(c["document_title"], round(c["similarity"], 4)) for c in chunks[:3]])
    else:
        logger.info("No chunks found for query: '%s'", user_message[:50])

    # Feature 9: Detect fallback — no relevant chunks above threshold
    relevant_chunks = [c for c in chunks if c["similarity"] > FALLBACK_SIMILARITY_THRESHOLD]
    is_fallback = len(relevant_chunks) == 0

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

    # Feature 1: Inject guidance rules
    guidance_section = ""
    if tenant.guidance_rules:
        guidance_section = f"ADMIN GUIDANCE RULES (always follow these):\n{tenant.guidance_rules}"

    # Feature 2: Support email line
    support_email_line = ""
    if tenant.support_email:
        support_email_line = f" You can also provide this support email: {tenant.support_email}"

    # Feature 2: Contact section
    contact_section = ""
    if tenant.support_email:
        contact_section = f"If the user needs human assistance, direct them to contact: {tenant.support_email}"

    # Feature 26: Multi-language instruction
    language_instruction = ""
    supported = getattr(tenant, "supported_languages", None) or ["en"]
    if len(supported) > 1 or (supported and supported[0] != "en"):
        language_instruction = (
            "- LANGUAGE: Detect the language of the user's message and respond in that same language. "
            f"Supported languages: {', '.join(supported)}."
        )

    system_message = SYSTEM_PROMPT_TEMPLATE.format(
        tenant_name=tenant.name,
        custom_system_prompt=tenant.system_prompt,
        guidance_section=guidance_section,
        contact_section=contact_section,
        support_email_line=support_email_line,
        language_instruction=language_instruction,
        context=context,
    )

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]

    result = await chat_completion(messages)

    # Feature 13: Parse suggestions from LLM response
    response_text, suggestions = _parse_suggestions(result["content"])

    sources = [
        {
            "document_title": chunk["document_title"],
            "chunk_content": chunk["content"][:200] + "..." if len(chunk["content"]) > 200 else chunk["content"],
            "source_url": chunk["source_url"],
            "relevance_score": chunk["similarity"],
        }
        for chunk in chunks
        if chunk["similarity"] > FALLBACK_SIMILARITY_THRESHOLD
    ]

    return {
        "response": response_text,
        "tokens_used": result["tokens_used"],
        "sources": sources,
        "is_fallback": is_fallback,
        "suggestions": suggestions,
    }

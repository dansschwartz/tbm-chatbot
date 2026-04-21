from app.services.openai_client import create_embedding, create_embeddings_batch


async def embed_query(text: str) -> list[float]:
    return await create_embedding(text)


async def embed_chunks(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embeddings = await create_embeddings_batch(batch)
        all_embeddings.extend(embeddings)
    return all_embeddings

import httpx

from app.config import settings

_client: httpx.AsyncClient | None = None

OPENAI_BASE = "https://api.openai.com/v1"


def _get_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


async def create_embedding(text: str) -> list[float]:
    client = await get_client()
    for attempt in range(3):
        resp = await client.post(
            f"{OPENAI_BASE}/embeddings",
            headers=_get_headers(),
            json={"input": text, "model": settings.embedding_model},
        )
        if resp.status_code == 429:
            wait = min(2 ** attempt * 5, 30)  # 5s, 10s, 30s
            import asyncio
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    resp.raise_for_status()  # Raise the last 429 if all retries failed
    return []


async def create_embeddings_batch(texts: list[str]) -> list[list[float]]:
    client = await get_client()
    resp = await client.post(
        f"{OPENAI_BASE}/embeddings",
        headers=_get_headers(),
        json={"input": texts, "model": settings.embedding_model},
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    data.sort(key=lambda x: x["index"])
    return [item["embedding"] for item in data]


async def chat_completion(
    messages: list[dict[str, str]],
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict:
    client = await get_client()
    for attempt in range(3):
        resp = await client.post(
            f"{OPENAI_BASE}/chat/completions",
            headers=_get_headers(),
            json={
                "model": settings.chat_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if resp.status_code == 429:
            wait = min(2 ** attempt * 5, 30)
            import asyncio
            await asyncio.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()
    result = resp.json()
    return {
        "content": result["choices"][0]["message"]["content"],
        "tokens_used": result["usage"]["total_tokens"],
    }


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None

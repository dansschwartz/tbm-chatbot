import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


async def fire_webhook(tenant, event: str, payload: dict):
    """Fire-and-forget webhook notification. Non-blocking."""
    if not tenant.webhook_url:
        return
    events = tenant.webhook_events or []
    if event not in events:
        return

    async def _send():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                body = {
                    "event": event,
                    "tenant_id": str(tenant.id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": payload,
                }
                resp = await client.post(
                    tenant.webhook_url,
                    json=body,
                    headers={"Content-Type": "application/json", "User-Agent": "TBM-Chatbot-Webhook/1.0"},
                )
                logger.info("Webhook %s -> %s: %d", event, tenant.webhook_url, resp.status_code)
        except Exception:
            logger.warning("Webhook delivery failed for %s to %s", event, tenant.webhook_url, exc_info=True)

    asyncio.create_task(_send())

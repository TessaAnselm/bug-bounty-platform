import os
import httpx
from temporalio import activity


@activity.defn
async def send_discord_alert(message: str) -> None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        activity.logger.info("DISCORD_WEBHOOK_URL not set, skipping alert")
        return

    async with httpx.AsyncClient() as client:
        response = await client.post(
            webhook_url,
            json={"content": message},
            timeout=10,
        )
        response.raise_for_status()

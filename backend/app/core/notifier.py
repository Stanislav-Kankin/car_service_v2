import os
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class BotNotifier:
    """
    Тонкий клиент для REST-API бота.

    ENV:
      BOT_API_URL   - базовый URL сервера бота (например http://127.0.0.1:8086)
      BOT_API_TOKEN - секрет для авторизации (опционально, но рекомендовано)
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or os.getenv("BOT_API_URL", "")).rstrip("/")
        self.token = os.getenv("BOT_API_TOKEN", "")

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    async def send_notification(
        self,
        *,
        recipient_type: str,  # "client" или "service_center"
        telegram_id: int,
        message: str,
        buttons: Optional[List[Dict[str, str]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.base_url:
            logger.info(
                "BotNotifier: BOT_API_URL not set, skipping notification "
                f"(to {recipient_type} {telegram_id})"
            )
            return

        payload: Dict[str, Any] = {
            "recipient_type": recipient_type,
            "telegram_id": telegram_id,
            "message": message,
        }
        if buttons:
            payload["buttons"] = buttons
        if extra:
            payload["extra"] = extra

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.base_url}/api/v1/notify",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
        except Exception as e:
            logger.exception("BotNotifier: failed to send notification to bot API: %r", e)

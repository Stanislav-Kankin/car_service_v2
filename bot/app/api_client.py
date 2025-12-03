from typing import Any, Dict, Optional

import aiohttp

from .config import config


class APIClient:
    def __init__(self) -> None:
        self.base_url = config.BACKEND_URL.rstrip("/")

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=data) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"API error {resp.status}: {text}")
                return await resp.json()

    # ---------- USERS ----------

    async def create_user(self, telegram_id: int) -> Any:
        """
        Создаёт пользователя с указанным telegram_id.
        Остальные поля можно заполнить позже через update_user.
        """
        return await self._request(
            "POST",
            "/api/v1/users/",
            {"telegram_id": telegram_id},
        )

    async def get_user_by_telegram(self, telegram_id: int) -> Any:
        """
        Возвращает пользователя по telegram_id.
        Ожидается, что backend отдаёт JSON с полем id.
        """
        return await self._request(
            "GET",
            f"/api/v1/users/by-telegram/{telegram_id}",
        )

    async def update_user(self, user_id: int, data: Dict[str, Any]) -> Any:
        """
        Частично обновляет пользователя по его id.
        data — словарь с полями (full_name, phone, city, role и т.п.).
        """
        return await self._request(
            "PATCH",
            f"/api/v1/users/{user_id}",
            data,
        )

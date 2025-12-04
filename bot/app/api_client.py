from typing import Any, Dict, Optional
import logging
import aiohttp

from .config import config

logger = logging.getLogger(__name__)


class APIClient:
    """
    Тонкий HTTP-клиент для общения бота с backend-ом CarBot V2.

    Все методы возвращают распарсенный JSON (dict/list) либо текст/None,
    в зависимости от ответа backend-а.
    """

    def __init__(self) -> None:
        # Например: http://127.0.0.1:8040
        self.base_url = config.BACKEND_URL.rstrip("/")

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Базовый метод для всех запросов.

        method   — "GET", "POST", "PATCH", "DELETE"
        endpoint — строка вида "/api/v1/users/..."
        data     — JSON-тело (dict) или None
        params   — query-параметры (?user_id=1 и т.п.)
        """
        url = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=data, params=params) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"API error {resp.status}: {text}")

                if resp.status == 204:
                    return None

                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await resp.json()

                return await resp.text()

    # ------------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------------

    async def create_user(self, data: Dict[str, Any]) -> Any:
        """
        Создание пользователя.

        Ожидает payload:
        {
            "telegram_id": int,
            "full_name": str,
            "phone": str,
            "city": str
        }
        """
        return await self._request(
            "POST",
            "/api/v1/users/",
            data,
        )

    async def get_user_by_telegram(self, telegram_id: int) -> Any:
        """
        Вернёт dict с пользователем или None, если пользователь не найден (404).
        Все остальные ошибки по-прежнему пробрасываем дальше.
        """
        try:
            return await self._request(
                "GET",
                f"/api/v1/users/by-telegram/{telegram_id}",
            )
        except Exception as e:
            msg = str(e)
            if "API error 404" in msg:
                logger.info("User with telegram_id=%s not found in backend", telegram_id)
                return None
            # остальные ошибки — настоящие, их не глушим
            raise

    async def update_user(self, user_id: int, data: Dict[str, Any]) -> Any:
        return await self._request(
            "PATCH",
            f"/api/v1/users/{user_id}",
            data,
        )

    async def get_user(self, user_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/users/{user_id}",
        )

    # ------------------------------------------------------------------
    # CARS (гараж пользователя)
    # ------------------------------------------------------------------

    async def list_cars(self, user_id: Optional[int] = None) -> Any:
        """
        Общий метод: либо все машины, либо по пользователю (если backend так поддерживает).
        В текущем проекте основное использование — list_cars_by_user().
        """
        if user_id is not None:
            endpoint = f"/api/v1/cars/by-user/{user_id}"
            params = None
        else:
            endpoint = "/api/v1/cars/"
            params = None

        return await self._request(
            "GET",
            endpoint,
            params=params,
        )

    async def list_cars_by_user(self, user_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/cars/by-user/{user_id}",
        )

    async def create_car(self, data: Dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            "/api/v1/cars/",
            data,
        )

    async def update_car(self, car_id: int, data: Dict[str, Any]) -> Any:
        return await self._request(
            "PATCH",
            f"/api/v1/cars/{car_id}",
            data,
        )

    async def delete_car(self, car_id: int) -> Any:
        return await self._request(
            "DELETE",
            f"/api/v1/cars/{car_id}",
        )

    async def get_car(self, car_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/cars/{car_id}",
        )

    # ------------------------------------------------------------------
    # REQUESTS (заявки)
    # ------------------------------------------------------------------

    async def create_request(self, data: Dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            "/api/v1/requests/",
            data,
        )

    async def get_request(self, request_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/requests/{request_id}",
        )

    async def list_requests_by_user(self, user_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/requests/by-user/{user_id}",
        )

    async def update_request(self, request_id: int, data: Dict[str, Any]) -> Any:
        return await self._request(
            "PATCH",
            f"/api/v1/requests/{request_id}",
            data,
        )

    # ------------------------------------------------------------------
    # SERVICE CENTERS (СТО)
    # ------------------------------------------------------------------

    async def create_service_center(self, data: Dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            "/api/v1/service-centers/",
            data,
        )

    async def update_service_center(self, sc_id: int, data: Dict[str, Any]) -> Any:
        """
        Частично обновить профиль СТО.
        """
        return await self._request(
            "PATCH",
            f"/api/v1/service-centers/{sc_id}",
            data,
        )

    async def get_service_center(self, sc_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/service-centers/{sc_id}",
        )

    async def list_service_centers(
        self, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        return await self._request(
            "GET",
            "/api/v1/service-centers/",
            params=params,
        )

    async def list_service_centers_by_user(self, user_id: int) -> Any:
        """
        Получить все СТО, привязанные к пользователю.
        Обычно будет одно.
        """
        return await self._request(
            "GET",
            f"/api/v1/service-centers/by-user/{user_id}",
        )

    # ------------------------------------------------------------------
    # OFFERS (отклики СТО на заявки)
    # ------------------------------------------------------------------

    async def create_offer(self, data: Dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            "/api/v1/offers/",
            data,
        )

    async def update_offer(self, offer_id: int, data: Dict[str, Any]) -> Any:
        return await self._request(
            "PATCH",
            f"/api/v1/offers/{offer_id}",
            data,
        )

    async def list_offers_by_request(self, request_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/offers/by-request/{request_id}",
        )

    # ------------------------------------------------------------------
    # BONUS (бонусы)
    # ------------------------------------------------------------------

    async def get_bonus_balance(self, user_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/bonus/{user_id}/balance",
        )

    async def get_bonus_history(self, user_id: int) -> Any:
        return await self._request(
            "GET",
            f"/api/v1/bonus/{user_id}/history",
        )

    async def adjust_bonus(self, user_id: int, data: Dict[str, Any]) -> Any:
        return await self._request(
            "POST",
            f"/api/v1/bonus/{user_id}/adjust",
            data,
        )


# Глобальный экземпляр, чтобы не создавать сессию заново в каждом хендлере
api_client = APIClient()

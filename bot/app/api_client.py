from typing import Any, Dict, Optional

import aiohttp

from .config import config


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

        method  — "GET", "POST", "PATCH", "DELETE"
        endpoint — строка вида "/api/v1/users/..."
        data    — JSON-тело (dict) или None
        params  — query-параметры (?user_id=1 и т.п.)
        """
        url = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, json=data, params=params) as resp:
                # Ошибки >= 400 — пробрасываем наверх
                if resp.status >= 400:
                    text = await resp.text()
                    raise Exception(f"API error {resp.status}: {text}")

                # 204 No Content
                if resp.status == 204:
                    return None

                # Пытаемся вернуть JSON, если он есть
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await resp.json()

                # Фолбэк — просто текст
                return await resp.text()

    # ------------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------------

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

    async def get_user(self, user_id: int) -> Any:
        """
        Получить пользователя по id.
        """
        return await self._request(
            "GET",
            f"/api/v1/users/{user_id}",
        )

    # ------------------------------------------------------------------
    # CARS (гараж пользователя)
    # ------------------------------------------------------------------

    async def list_cars(self, user_id: Optional[int] = None) -> Any:
        """
        Получить список машин.

        Если задан user_id — используем эндпоинт /api/v1/cars/by-user/{user_id},
        иначе — общий список /api/v1/cars/.
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

    async def create_car(self, data: Dict[str, Any]) -> Any:
        """
        Создать машину.
        Ожидается словарь:
        {
            "user_id": int,
            "brand": str,
            "model": str,
            "year": int | None,
            "license_plate": str | None,
            "vin": str | None
        }
        """
        return await self._request(
            "POST",
            "/api/v1/cars/",
            data,
        )

    async def update_car(self, car_id: int, data: Dict[str, Any]) -> Any:
        """
        Обновить данные машины.
        """
        return await self._request(
            "PATCH",
            f"/api/v1/cars/{car_id}",
            data,
        )

    async def delete_car(self, car_id: int) -> Any:
        """
        Удалить машину.
        """
        return await self._request(
            "DELETE",
            f"/api/v1/cars/{car_id}",
        )
    
    async def get_car(self, car_id: int) -> Any:
        """
        Получить машину по её ID.
        """
        return await self._request(
            "GET",
            f"/api/v1/cars/{car_id}",
        )

    # ------------------------------------------------------------------
    # REQUESTS (заявки)
    # ------------------------------------------------------------------

    async def create_request(self, data: Dict[str, Any]) -> Any:
        """
        Создать заявку.
        data — словарь по схеме RequestCreate (user_id, car_id, описание, гео и т.п.).
        """
        return await self._request(
            "POST",
            "/api/v1/requests/",
            data,
        )

    async def get_request(self, request_id: int) -> Any:
        """
        Получить заявку по ID.
        """
        return await self._request(
            "GET",
            f"/api/v1/requests/{request_id}",
        )

    async def list_requests_by_user(self, user_id: int) -> Any:
        """
        Список заявок конкретного пользователя.
        """
        return await self._request(
            "GET",
            f"/api/v1/requests/by-user/{user_id}",
        )

    async def update_request(self, request_id: int, data: Dict[str, Any]) -> Any:
        """
        Обновить заявку (например, статус).
        """
        return await self._request(
            "PATCH",
            f"/api/v1/requests/{request_id}",
            data,
        )

    # ------------------------------------------------------------------
    # SERVICE CENTERS (СТО)
    # ------------------------------------------------------------------

    async def create_service_center(self, data: Dict[str, Any]) -> Any:
        """
        Создать СТО.
        data — словарь по схеме ServiceCenterCreate.
        """
        return await self._request(
            "POST",
            "/api/v1/service-centers/",
            data,
        )

    async def update_service_center(self, sc_id: int, data: Dict[str, Any]) -> Any:
        """
        Обновить профиль СТО.
        """
        return await self._request(
            "PATCH",
            f"/api/v1/service-centers/{sc_id}",
            data,
        )

    async def get_service_center(self, sc_id: int) -> Any:
        """
        Получить СТО по id.
        """
        return await self._request(
            "GET",
            f"/api/v1/service-centers/{sc_id}",
        )

    async def list_service_centers(self, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Список СТО с опциональными фильтрами.
        params может содержать:
        - city
        - specializations
        - radius
        и т.п. (в зависимости от реализованных query-параметров backend-а).
        """
        return await self._request(
            "GET",
            "/api/v1/service-centers/",
            params=params,
        )

    # ------------------------------------------------------------------
    # OFFERS (отклики СТО на заявки)
    # ------------------------------------------------------------------

    async def create_offer(self, data: Dict[str, Any]) -> Any:
        """
        Создать отклик СТО на заявку.
        data — словарь по схеме OfferCreate.
        """
        return await self._request(
            "POST",
            "/api/v1/offers/",
            data,
        )

    async def update_offer(self, offer_id: int, data: Dict[str, Any]) -> Any:
        """
        Обновить отклик (цену, срок, комментарий и т.п.).
        """
        return await self._request(
            "PATCH",
            f"/api/v1/offers/{offer_id}",
            data,
        )

    async def list_offers_by_request(self, request_id: int) -> Any:
        """
        Список откликов по заявке.
        Ожидается эндпоинт вида: /api/v1/offers/by-request/{request_id}
        """
        return await self._request(
            "GET",
            f"/api/v1/offers/by-request/{request_id}",
        )

    # ------------------------------------------------------------------
    # BONUS (бонусы, баланс, история)
    # ------------------------------------------------------------------

    async def get_bonus_balance(self, user_id: int) -> Any:
        """
        Получить текущий баланс бонусов пользователя.
        """
        return await self._request(
            "GET",
            f"/api/v1/bonus/{user_id}/balance",
        )

    async def get_bonus_history(self, user_id: int) -> Any:
        """
        История бонусных транзакций пользователя.
        Ожидается эндпоинт вида: /api/v1/bonus/{user_id}/history
        """
        return await self._request(
            "GET",
            f"/api/v1/bonus/{user_id}/history",
        )

    async def adjust_bonus(self, user_id: int, data: Dict[str, Any]) -> Any:
        """
        Ручное изменение бонусов (для системных операций / админки).
        data — по схеме BonusAdjust (amount, reason, request_id, offer_id и т.п.).
        """
        return await self._request(
            "POST",
            f"/api/v1/bonus/{user_id}/adjust",
            data,
        )

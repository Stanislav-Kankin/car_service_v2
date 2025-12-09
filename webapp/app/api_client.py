from collections.abc import AsyncGenerator

import httpx

from .config import settings


class BackendAPIClient:
    """
    Тонкий клиент для общения с backend'ом CarBot.

    Здесь будут методы:
    - get_current_user
    - list_cars
    - list_requests
    - create_request
    - и т.д.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = base_url or str(settings.BACKEND_API_URL)

    def get_httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=10.0,
        )


async def get_backend_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    FastAPI dependency: даёт готовый httpx.AsyncClient с base_url backend'а.
    """
    client = BackendAPIClient().get_httpx_client()
    try:
        yield client
    finally:
        await client.aclose()

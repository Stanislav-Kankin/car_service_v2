from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import httpx

from webapp.app.config import settings

router = APIRouter(tags=["public"])


def _auth_html() -> HTMLResponse:
    # ВАЖНО: / должен быть 200 OK, без редиректов, иначе цикл.
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>MyGarage — Авторизация…</title>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
        </head>
        <body>
            <script>
              function setUserIdCookie(userId) {
                const parts = [
                  `user_id=${encodeURIComponent(userId)}`,
                  "Path=/",
                  "Max-Age=2592000",
                  "Domain=.dev-cloud-ksa.ru",
                  "SameSite=None",
                  "Secure"
                ];
                document.cookie = parts.join("; ");
              }

              (async function () {
                if (!window.Telegram || !Telegram.WebApp) return;

                const tg = Telegram.WebApp;
                tg.ready();

                const initData = tg.initData || "";
                if (!initData) return;

                const resp = await fetch("/api/v1/auth/telegram-webapp", {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  credentials: "include",
                  body: JSON.stringify({ init_data: initData }),
                });

                if (!resp.ok) return;

                const data = await resp.json();
                if (!data || !data.user_id) return;

                setUserIdCookie(data.user_id);
                window.location.replace("/me/dashboard");
              })();
            </script>
        </body>
        </html>
        """,
    )


def _clear_cookie(resp: HTMLResponse | RedirectResponse) -> None:
    resp.delete_cookie("user_id", path="/")
    resp.delete_cookie("user_id", path="/", domain=".dev-cloud-ksa.ru")
    resp.delete_cookie("userId", path="/")
    resp.delete_cookie("userId", path="/", domain=".dev-cloud-ksa.ru")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    ЕДИНСТВЕННАЯ точка входа Mini App.

    Правило:
    - если НЕТ валидной сессии -> 200 OK auth HTML
    - если session валидна -> redirect /me/dashboard
    """
    user_id = getattr(request.state, "user_id", None)

    # Если cookie нет — отдаём auth-страницу (200)
    if not user_id:
        return _auth_html()

    # Если cookie есть — проверим, что пользователь реально существует в backend
    try:
        async with httpx.AsyncClient(base_url=str(settings.BACKEND_API_URL), timeout=10.0) as client:
            r = await client.get(f"/api/v1/users/{int(user_id)}")
            if r.status_code == 404:
                resp = _auth_html()
                _clear_cookie(resp)
                return resp
            r.raise_for_status()
    except Exception:
        # Если backend недоступен/ошибка — НЕ редиректим, иначе снова цикл
        return _auth_html()

    return RedirectResponse("/me/dashboard", status_code=302)


# Чтобы curl -I не вводил в заблуждение
@router.head("/", response_class=HTMLResponse)
async def index_head(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")


@router.get("/health", response_class=HTMLResponse)
async def health(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")

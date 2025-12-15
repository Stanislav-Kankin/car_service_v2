from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    ЕДИНСТВЕННАЯ точка входа Mini App.

    Если cookie user_id уже есть -> в кабинет.
    Если нет -> отдаём HTML, который делает Telegram auth и ставит cookie.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return RedirectResponse("/me/dashboard", status_code=302)

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


@router.get("/health", response_class=HTMLResponse)
async def health(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")


@router.get("/register")
async def register_redirect(_: Request) -> RedirectResponse:
    return RedirectResponse("/me/register", status_code=302)


@router.post("/register")
async def register_redirect_post(_: Request) -> RedirectResponse:
    return RedirectResponse("/me/register", status_code=302)

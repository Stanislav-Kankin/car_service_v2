from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    ЕДИНСТВЕННАЯ точка входа Mini App.

    Логика:
    - если нет user_id → отрисовываем страницу с JS auth
    - если user_id есть → редирект в /me/dashboard
    """
    user_id = getattr(request.state, "user_id", None)

    if user_id:
        return RedirectResponse("/me/dashboard", status_code=302)

    # Страница ТОЛЬКО для выполнения Telegram auth
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <title>Авторизация…</title>
            <script src="https://telegram.org/js/telegram-web-app.js"></script>
        </head>
        <body>
            <script>
                (function () {
                    if (!window.Telegram || !Telegram.WebApp) {
                        return;
                    }
                    const tg = Telegram.WebApp;
                    tg.ready();

                    if (!tg.initData) {
                        return;
                    }

                    fetch("/api/v1/auth/telegram-webapp", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        credentials: "include",
                        body: JSON.stringify({ init_data: tg.initData }),
                    })
                    .then(resp => resp.json())
                    .then(() => {
                        window.location.replace("/me/dashboard");
                    });
                })();
            </script>
        </body>
        </html>
        """
    )

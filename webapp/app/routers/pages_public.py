from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    # если cookie уже есть — сразу в кабинет
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return RedirectResponse("/me/dashboard", status_code=302)

    # иначе выполняем Telegram auth ОДИН РАЗ
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8"/>
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>Авторизация…</title>
          <script src="https://telegram.org/js/telegram-web-app.js"></script>
        </head>
        <body>
          <script>
            function setUserIdCookie(userId) {
              const isHttps = window.location.protocol === "https:";
              const parts = [
                `user_id=${encodeURIComponent(userId)}`,
                "Path=/",
                "Max-Age=2592000",
                "Domain=.dev-cloud-ksa.ru"
              ];
              if (isHttps) {
                parts.push("SameSite=None");
                parts.push("Secure");
              } else {
                parts.push("SameSite=Lax");
              }
              document.cookie = parts.join("; ");
            }

            (function () {
              if (!window.Telegram || !Telegram.WebApp) return;
              const tg = Telegram.WebApp;
              tg.ready();
              if (!tg.initData) return;

              fetch("/api/v1/auth/telegram-webapp", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "include",
                body: JSON.stringify({init_data: tg.initData})
              })
              .then(r => r.json())
              .then(data => {
                if (!data || !data.user_id) return;
                setUserIdCookie(data.user_id);
                window.location.replace("/me/dashboard");
              })
              .catch(() => {});
            })();
          </script>
        </body>
        </html>
        """
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

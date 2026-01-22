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
            <title>MyGarage — Вход</title>
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center p-4">
            <div class="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-6 space-y-4">
                <h1 class="text-xl font-semibold">Вход по телефону</h1>
                <p class="text-sm text-slate-300">
                    Введите номер телефона — мы пришлём одноразовый код (OTP).
                </p>

                <div class="space-y-2">
                    <label class="text-xs text-slate-400">Телефон</label>
                    <input id="phone" class="w-full rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2"
                           placeholder="+7 999 123-45-67" autocomplete="tel"/>
                </div>

                <button id="btnRequest"
                        class="w-full rounded-xl bg-emerald-500 px-4 py-2 font-semibold text-slate-950 hover:bg-emerald-400 transition">
                    Получить код
                </button>

                <div id="step2" class="hidden space-y-2 pt-2">
                    <label class="text-xs text-slate-400">Код из SMS</label>
                    <input id="code" class="w-full rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2"
                           placeholder="123456" inputmode="numeric" autocomplete="one-time-code"/>
                    <button id="btnVerify"
                            class="w-full rounded-xl bg-sky-500 px-4 py-2 font-semibold text-slate-950 hover:bg-sky-400 transition">
                        Войти
                    </button>
                </div>

                <div id="msg" class="text-sm text-slate-300"></div>
                <div id="dev" class="text-xs text-amber-300"></div>
            </div>

            <script>
              function getSafeNext() {
                try {
                  const params = new URLSearchParams(window.location.search || "");
                  const next = params.get("next") || "";
                  if (next && next.startsWith("/")) return next;
                } catch (e) {}
                return "/me/dashboard";
              }

              function setMsg(text, isError) {
                const el = document.getElementById("msg");
                el.textContent = text || "";
                el.className = "text-sm " + (isError ? "text-rose-300" : "text-slate-300");
              }

              function setDev(text) {
                const el = document.getElementById("dev");
                el.textContent = text || "";
              }

              function showStep2() {
                document.getElementById("step2").classList.remove("hidden");
                document.getElementById("code").focus();
              }

              async function postJson(url, payload) {
                const resp = await fetch(url, {
                  method: "POST",
                  headers: {"Content-Type": "application/json"},
                  credentials: "include",
                  body: JSON.stringify(payload),
                });
                let data = null;
                try { data = await resp.json(); } catch (e) {}
                return { resp, data };
              }

              document.getElementById("btnRequest").addEventListener("click", async () => {
                setMsg("", false);
                setDev("");
                const phone = (document.getElementById("phone").value || "").trim();
                if (!phone) { setMsg("Введите телефон", true); return; }

                const { resp, data } = await postJson("/api/v1/auth/otp/request", { phone });
                if (!resp.ok) {
                  setMsg((data && data.detail) ? data.detail : "Ошибка запроса кода", true);
                  return;
                }
                showStep2();
                setMsg("Код отправлен. Введите его ниже.", false);
                if (data && data.dev_code) {
                  setDev("DEV: код для входа = " + data.dev_code);
                }
              });

              document.getElementById("btnVerify").addEventListener("click", async () => {
                setMsg("", false);
                const phone = (document.getElementById("phone").value || "").trim();
                const code = (document.getElementById("code").value || "").trim();
                if (!phone || !code) { setMsg("Введите телефон и код", true); return; }

                const { resp, data } = await postJson("/api/v1/auth/otp/verify", { phone, code });
                if (!resp.ok) {
                  setMsg((data && data.detail) ? data.detail : "Ошибка проверки кода", true);
                  return;
                }
                const target = getSafeNext();
                window.location.replace(target);
              });
            </script>
        </body>
        </html>
        """,
    )


def _clear_cookie(resp: HTMLResponse | RedirectResponse) -> None:
    # Новая cookie
    resp.delete_cookie("session_id", path="/")
    resp.delete_cookie("session_id", path="/", domain=".dev-cloud-ksa.ru")

    # Legacy cookies (на всякий случай)
    resp.delete_cookie("user_id", path="/")
    resp.delete_cookie("user_id", path="/", domain=".dev-cloud-ksa.ru")
    resp.delete_cookie("userId", path="/")
    resp.delete_cookie("userId", path="/", domain=".dev-cloud-ksa.ru")


def _safe_next_from_request(request: Request) -> str | None:
    nxt = (request.query_params.get("next") or "").strip()
    if nxt and nxt.startswith("/"):
        return nxt
    return None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """
    ЕДИНСТВЕННАЯ точка входа WebApp.

    Правило:
    - если НЕТ валидной сессии -> 200 OK auth HTML
    - если session валидна -> redirect next (если есть) или /me/dashboard
    """
    user_id = getattr(request.state, "user_id", None)
    next_path = _safe_next_from_request(request)

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

    return RedirectResponse(next_path or "/me/dashboard", status_code=302)


@router.head("/", response_class=HTMLResponse)
async def index_head(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")


@router.get("/health", response_class=HTMLResponse)
async def health(_: Request) -> HTMLResponse:
    return HTMLResponse("ok")

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import httpx
import json

from webapp.app.config import settings

router = APIRouter(tags=["public"])


def _auth_html() -> HTMLResponse:
    # ВАЖНО: / должен быть 200 OK, без редиректов, иначе цикл.
    html_str = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MyGarage — Вход</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="manifest" href="/manifest.webmanifest" />
    <meta name="theme-color" content="#0b1220" />
    <link rel="icon" href="/static/icons/icon-192.png" sizes="192x192" />
    <link rel="apple-touch-icon" href="/static/icons/icon-192.png" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
</head>
<body class="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center p-4">
    <div class="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-6 space-y-4">
        <div class="flex items-center justify-between">
            <h1 class="text-xl font-semibold">Вход</h1>
            <span id="modeBadge" class="text-[11px] px-2 py-1 rounded-lg border border-slate-800 text-slate-300"></span>
        </div>

        <div id="tabs" class="flex gap-2">
            <button id="tabEmail" class="flex-1 rounded-xl border border-slate-800 px-3 py-2 text-sm hover:bg-slate-800/30 transition">
                Email
            </button>
            <button id="tabPhone" class="flex-1 rounded-xl border border-slate-800 px-3 py-2 text-sm hover:bg-slate-800/30 transition">
                Телефон (OTP)
            </button>
        </div>

        <!-- EMAIL -->
        <div id="panelEmail" class="space-y-3">
            <p class="text-sm text-slate-300">
                Вход без Telegram и без SMS: email + пароль.
            </p>

            <div class="space-y-2">
                <label class="text-xs text-slate-400">Email</label>
                <input id="email" class="w-full rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2"
                       placeholder="name@example.com" autocomplete="email" inputmode="email"/>
            </div>

            <div class="space-y-2">
                <label class="text-xs text-slate-400">Пароль</label>
                <input id="password" type="password" class="w-full rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2"
                       placeholder="••••••••" autocomplete="current-password"/>
            </div>

            <div class="space-y-2">
                <label class="text-xs text-slate-400">Имя (для регистрации, опционально)</label>
                <input id="full_name" class="w-full rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2"
                       placeholder="Иван" autocomplete="name"/>
            </div>

            <div class="grid grid-cols-2 gap-2">
                <button id="btnEmailLogin"
                        class="w-full rounded-xl bg-sky-500 px-4 py-2 font-semibold text-slate-950 hover:bg-sky-400 transition">
                    Войти
                </button>
                <button id="btnEmailRegister"
                        class="w-full rounded-xl bg-emerald-500 px-4 py-2 font-semibold text-slate-950 hover:bg-emerald-400 transition">
                    Создать аккаунт
                </button>
            </div>
        </div>

        <!-- PHONE OTP (оставлено для совместимости; в AUTH_MODE=app скрывается) -->
        <div id="panelPhone" class="space-y-3">
            <h2 class="text-base font-semibold">Вход по телефону</h2>
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

            <div id="dev" class="text-xs text-amber-300"></div>
        </div>

        <div id="msg" class="text-sm text-slate-300"></div>
    </div>

    <script>
      const AUTH_MODE = "%(AUTH_MODE)s";

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
        if (!el) return;
        el.textContent = text || "";
      }

      function showStep2() {
        document.getElementById("step2").classList.remove("hidden");
        document.getElementById("code").focus();
      }

      function setActiveTab(tab) {
        const btnEmail = document.getElementById("tabEmail");
        const btnPhone = document.getElementById("tabPhone");
        const panelEmail = document.getElementById("panelEmail");
        const panelPhone = document.getElementById("panelPhone");

        const activeCls = "bg-slate-800/40";
        btnEmail.classList.remove(activeCls);
        btnPhone.classList.remove(activeCls);

        if (tab === "phone") {
          btnPhone.classList.add(activeCls);
          panelPhone.classList.remove("hidden");
          panelEmail.classList.add("hidden");
        } else {
          btnEmail.classList.add(activeCls);
          panelEmail.classList.remove("hidden");
          panelPhone.classList.add("hidden");
        }
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

      // ----- init UI
      (function init() {
        const badge = document.getElementById("modeBadge");
        badge.textContent = "AUTH_MODE=" + AUTH_MODE;

        const phoneTab = document.getElementById("tabPhone");
        const phonePanel = document.getElementById("panelPhone");

        // В режиме app скрываем OTP (но код оставляем для совместимости)
        if (AUTH_MODE === "app") {
          phoneTab.disabled = true;
          phoneTab.classList.add("opacity-40", "cursor-not-allowed");
          phonePanel.classList.add("hidden");
          setActiveTab("email");
          return;
        }

        // mixed/telegram: оставляем обе вкладки, по умолчанию email (mixed) / phone (telegram)
        if (AUTH_MODE === "telegram") {
          setActiveTab("phone");
        } else {
          setActiveTab("email");
        }
      })();

      document.getElementById("tabEmail").addEventListener("click", () => setActiveTab("email"));
      document.getElementById("tabPhone").addEventListener("click", () => setActiveTab("phone"));

      // ----- email login/register
      document.getElementById("btnEmailLogin").addEventListener("click", async () => {
        setMsg("", false);
        const email = (document.getElementById("email").value || "").trim();
        const password = (document.getElementById("password").value || "").trim();
        if (!email || !password) { setMsg("Введите email и пароль", true); return; }

        const { resp, data } = await postJson("/api/v1/auth/email/login", { email, password });
        if (!resp.ok) {
          setMsg((data && data.detail) ? data.detail : "Ошибка входа", true);
          return;
        }
        window.location.replace(getSafeNext());
      });

      document.getElementById("btnEmailRegister").addEventListener("click", async () => {
        setMsg("", false);
        const email = (document.getElementById("email").value || "").trim();
        const password = (document.getElementById("password").value || "").trim();
        const full_name = (document.getElementById("full_name").value || "").trim();
        if (!email || !password) { setMsg("Введите email и пароль", true); return; }

        const { resp, data } = await postJson("/api/v1/auth/email/register", { email, password, full_name });
        if (!resp.ok) {
          setMsg((data && data.detail) ? data.detail : "Ошибка регистрации", true);
          return;
        }
        window.location.replace(getSafeNext());
      });

      // ----- phone otp (legacy)
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
        window.location.replace(getSafeNext());
      });
    </script>
<script>
  (function () {
    try {
      if (!("serviceWorker" in navigator)) return;
      if (location.protocol !== "https:" && location.hostname !== "localhost") return;
      navigator.serviceWorker.register("/sw.js").catch(function () {});
    } catch (e) {}
  })();
</script>
</body>
</html>
""" % {"AUTH_MODE": str(getattr(settings, "AUTH_MODE", "mixed") or "mixed").strip().lower()}
    return HTMLResponse(html_str)


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


@router.get('/manifest.webmanifest')
async def manifest() -> Response:
    manifest_dict = {
        'name': 'MyGarage',
        'short_name': 'MyGarage',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#0b1220',
        'theme_color': '#0b1220',
        'icons': [
            {'src': '/static/icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': '/static/icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
        ],
    }
    return Response(content=json.dumps(manifest_dict, ensure_ascii=False), media_type='application/manifest+json')


@router.get('/sw.js')
async def service_worker() -> Response:
    js = """
const CACHE_NAME = 'mygarage-shell-v1';
const PRECACHE_URLS = [
  '/',
  '/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.map((k) => (k === CACHE_NAME ? null : caches.delete(k)))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Только same-origin
  if (url.origin !== self.location.origin) return;

  // API не кешируем
  if (url.pathname.startsWith('/api/')) return;

  // Навигация: network-first, fallback на cached '/'
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(() => caches.match('/'))
    );
    return;
  }

  // Статика/manifest: cache-first
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req).then((resp) => {
      const copy = resp.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
      return resp;
    }))
  );
});
""".strip()
    return Response(content=js, media_type='application/javascript')


from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from webapp.app.services.backend import get_backend_client

router = APIRouter()


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return HTMLResponse(
        """
        <html>
        <head>
            <title>Регистрация</title>
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <script src="https://cdn.tailwindcss.com"></script>
        </head>
        <body class="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center">
            <form method="post" class="bg-slate-900 p-6 rounded-xl w-full max-w-sm space-y-4">
                <h1 class="text-xl font-bold">Регистрация</h1>

                <input
                    name="full_name"
                    placeholder="Имя"
                    required
                    class="w-full p-2 rounded bg-slate-800"
                />

                <input
                    name="phone"
                    placeholder="Телефон"
                    required
                    class="w-full p-2 rounded bg-slate-800"
                />

                <button
                    type="submit"
                    class="w-full bg-blue-600 p-2 rounded"
                >
                    Продолжить
                </button>
            </form>
        </body>
        </html>
        """
    )


@router.post("/register")
async def register_post(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(...),
):
    user_id = request.state.user_id
    if not user_id:
        return RedirectResponse("/me/dashboard", status_code=302)

    client = get_backend_client(request)

    # ✅ Вместо несуществующего /users/complete-registration
    # используем существующий PATCH /users/{user_id}
    await client.patch(
        f"/api/v1/users/{user_id}",
        json={
            "full_name": full_name,
            "phone": phone,
        },
    )

    return RedirectResponse("/me/dashboard", status_code=302)

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from webapp.api_client import get_backend_client

router = APIRouter()

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "public/register.html",
        {"request": request},
    )

@router.post("/register")
async def register_post(
    request: Request,
    full_name: str = Form(...),
    phone: str = Form(...),
):
    client = get_backend_client()

    # временно: без Telegram
    resp = await client.post(
        "/api/v1/users/register",
        json={
            "full_name": full_name,
            "phone": phone,
        },
    )
    resp.raise_for_status()

    user = resp.json()
    response = RedirectResponse("/me/dashboard", status_code=302)
    response.set_cookie("user_id", str(user["id"]), path="/")
    return response

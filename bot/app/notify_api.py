import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


class NotifyPayload(BaseModel):
    recipient_type: str
    telegram_id: int
    message: str
    buttons: Optional[List[Dict[str, str]]] = None
    extra: Optional[Dict[str, Any]] = None


def build_notify_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="CarBot Notify API")

    token = os.getenv("BOT_API_TOKEN", "")
    webapp_public_url = (os.getenv("WEBAPP_PUBLIC_URL", "") or "").rstrip("/")

    def _is_webapp_link(url: str) -> bool:
        """
        Если ссылка ведёт на наш WEBAPP_PUBLIC_URL — открываем как web_app внутри Telegram.
        """
        if not url:
            return False
        if not webapp_public_url:
            return False
        return url.startswith(webapp_public_url + "/") or url == webapp_public_url

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/api/v1/notify")
    async def notify(
        payload: NotifyPayload,
        authorization: str | None = Header(default=None),
    ) -> Dict[str, Any]:
        # Авторизация (если задана)
        if token:
            if not authorization or not authorization.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Unauthorized")
            if authorization.split(" ", 1)[1] != token:
                raise HTTPException(status_code=403, detail="Forbidden")

        kb = None
        if payload.buttons:
            rows = []
            for b in payload.buttons:
                text = (b.get("text") or "").strip()
                url = (b.get("url") or "").strip()
                if not text or not url:
                    continue

                # ✅ если это ссылка на наш WebApp — открываем внутри Telegram
                if _is_webapp_link(url):
                    rows.append([InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))])
                else:
                    rows.append([InlineKeyboardButton(text=text, url=url)])

            if rows:
                kb = InlineKeyboardMarkup(inline_keyboard=rows)

        await bot.send_message(
            chat_id=payload.telegram_id,
            text=payload.message,
            reply_markup=kb,
        )
        return {"ok": True}

    return app

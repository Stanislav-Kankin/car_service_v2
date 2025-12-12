import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class NotifyPayload(BaseModel):
    recipient_type: str
    telegram_id: int
    message: str
    buttons: Optional[List[Dict[str, str]]] = None
    extra: Optional[Dict[str, Any]] = None


def build_notify_app(bot: Bot) -> FastAPI:
    app = FastAPI(title="CarBot Notify API")

    token = os.getenv("BOT_API_TOKEN", "")

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
                text = b.get("text")
                url = b.get("url")
                if text and url:
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

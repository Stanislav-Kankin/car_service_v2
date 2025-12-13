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

    @app.get("/health")
    async def health() -> Dict[str, Any]:
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
            if authorization.removeprefix("Bearer ").strip() != token:
                raise HTTPException(status_code=401, detail="Unauthorized")

        kb = None
        if payload.buttons:
            rows: List[List[InlineKeyboardButton]] = []
            for b in payload.buttons:
                text = b.get("text")
                btn_type = (b.get("type") or "url").lower()
                url = b.get("url")
                if text and url:
                    if btn_type in ("web_app", "webapp", "miniapp"):
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

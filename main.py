import os
import asyncio
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode

# ------------------ CONFIG ------------------

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxx.onrender.com
WEBHOOK_PATH = "/webhook"

logging.basicConfig(level=logging.INFO)

# ------------------ BOT ------------------

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

app = FastAPI()

# ------------------ STATE ------------------

PAIRS = {
    "H": False,
    "SOL": False,
    "ETH": False,
    "RIVER": False,
    "LIGHT": False,
    "BEAT": False,
    "CYS": False,
    "ZPK": False,
    "RAVE": False,
    "DOGE": False,
}

# ------------------ HELPERS ------------------

def only_admin(message: Message) -> bool:
    return message.from_user.id == ADMIN_ID


def pairs_keyboard():
    buttons = []
    for pair, enabled in PAIRS.items():
        status = "🟢" if enabled else "🔴"
        buttons.append(
            InlineKeyboardButton(
                text=f"{status} {pair}",
                callback_data=f"toggle:{pair}"
            )
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        buttons[i:i+2] for i in range(0, len(buttons), 2)
    ])

    return keyboard

# ------------------ HANDLERS ------------------

@router.message(Command("start"))
async def start(message: Message):
    if not only_admin(message):
        return

    await message.answer(
        "👋 <b>Бот запущен</b>\n\n"
        "📊 EMA 7 / EMA 25 / VWAP\n"
        "🔥 Сигналы и автосканер\n\n"
        "Управление парами:",
        reply_markup=pairs_keyboard()
    )


@router.callback_query()
async def toggle_pair(callback):
    if callback.from_user.id != ADMIN_ID:
        return

    data = callback.data
    if not data.startswith("toggle:"):
        return

    pair = data.split(":")[1]
    PAIRS[pair] = not PAIRS[pair]

    await callback.message.edit_reply_markup(
        reply_markup=pairs_keyboard()
    )
    await callback.answer(f"{pair} {'включён' if PAIRS[pair] else 'выключен'}")


@router.message(Command("status"))
async def status(message: Message):
    if not only_admin(message):
        return

    active = [p for p, v in PAIRS.items() if v]
    await message.answer(
        "📡 <b>Статус бота</b>\n\n"
        f"Активные пары: {', '.join(active) if active else 'нет'}\n"
        "Webhook: ✅\n"
        "Бот жив 🫡"
    )

# ------------------ WEBHOOK ------------------

@app.on_event("startup")
async def on_startup():
    webhook_full_url = WEBHOOK_URL + WEBHOOK_PATH
    await bot.set_webhook(webhook_full_url)
    logging.info(f"Webhook set: {webhook_full_url}")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}


# ------------------ RUN ------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
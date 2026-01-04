import os
import asyncio
import logging
from datetime import datetime

import aiohttp
from fastapi import FastAPI, Request

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.enums import ParseMode

# =======================
# НАСТРОЙКИ
# =======================

TOKEN = os.getenv("TOKEN")  # Telegram Bot Token
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # ТВОЙ TG ID
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://xxx.onrender.com/webhook
PORT = int(os.getenv("PORT", 10000))

TIMEFRAME = "15m"

PAIRS = [
    "HUSDT", "SOLUSDT", "ETHUSDT", "RIVERUSDT", "LIGHTUSDT",
    "BEATUSDT", "CYSUSDT", "ZPKUSDT", "RAVEUSDT", "DOGEUSDT"
]

ACTIVE_PAIRS = {p: False for p in PAIRS}

BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines"

logging.basicConfig(level=logging.INFO)

# =======================
# BOT / APP
# =======================

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
app = FastAPI()

# =======================
# BINANCE
# =======================

async def get_klines(symbol: str, interval: str, limit: int = 100):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_KLINES, params=params) as resp:
            return await resp.json()

def ema(values, period):
    k = 2 / (period + 1)
    ema_val = values[0]
    for v in values[1:]:
        ema_val = v * k + ema_val * (1 - k)
    return ema_val

def vwap(klines):
    pv = 0
    vol = 0
    for k in klines:
        price = (float(k[1]) + float(k[4])) / 2
        volume = float(k[5])
        pv += price * volume
        vol += volume
    return pv / vol if vol else 0

# =======================
# КЛАВИАТУРА
# =======================

def main_keyboard():
    rows = []

    for p in PAIRS:
        state = "✅" if ACTIVE_PAIRS[p] else "❌"
        rows.append([
            InlineKeyboardButton(
                text=f"{state} {p.replace('USDT','')}",
                callback_data=f"pair:{p}"
            )
        ])

    rows.append([
        InlineKeyboardButton(text="📊 Статус", callback_data="status")
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

# =======================
# КОМАНДЫ
# =======================

@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "🤖 <b>Сигнальный бот запущен</b>\n\n"
        "EMA7 / EMA25 / VWAP\n"
        "Выбери пары для мониторинга 👇",
        reply_markup=main_keyboard()
    )

# =======================
# КНОПКИ
# =======================

@dp.callback_query(F.data.startswith("pair:"))
async def toggle_pair(callback: CallbackQuery):
    await callback.answer()

    pair = callback.data.split(":")[1]
    ACTIVE_PAIRS[pair] = not ACTIVE_PAIRS[pair]

    await callback.message.edit_reply_markup(reply_markup=main_keyboard())

@dp.callback_query(F.data == "status")
async def status_handler(callback: CallbackQuery):
    await callback.answer()

    active = [p for p, v in ACTIVE_PAIRS.items() if v]

    text = (
        "🟢 <b>Статус бота</b>\n\n"
        f"⏱ Таймфрейм: {TIMEFRAME}\n"
        f"📡 Webhook: активен\n"
        f"📈 Активные пары: {', '.join(active) if active else 'нет'}\n"
        f"🕒 {datetime.utcnow().strftime('%H:%M:%S')} UTC"
    )

    await callback.message.answer(text)

# =======================
# СИГНАЛЫ
# =======================

async def scan_pairs():
    while True:
        for pair, enabled in ACTIVE_PAIRS.items():
            if not enabled:
                continue

            klines = await get_klines(pair, TIMEFRAME)
            closes = [float(k[4]) for k in klines]

            price = closes[-1]
            ema7 = ema(closes[-7:], 7)
            ema25 = ema(closes[-25:], 25)
            vw = vwap(klines)

            if price > ema7 > ema25 and price > vw:
                await bot.send_message(
                    ADMIN_ID,
                    f"📈 <b>{pair}</b> ({TIMEFRAME})\n"
                    f"🔵 ЛОНГ\n\n"
                    f"Цена: {price:.4f}\n"
                    f"EMA7: {ema7:.4f}\n"
                    f"EMA25: {ema25:.4f}\n"
                    f"VWAP: {vw:.4f}\n\n"
                    f"https://www.binance.com/ru/futures/{pair}"
                )

        await asyncio.sleep(60)

# =======================
# WEBHOOK
# =======================

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    await dp.feed_update(bot, data)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    asyncio.create_task(scan_pairs())
    logging.info(f"Webhook set: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

# =======================
# RUN
# =======================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
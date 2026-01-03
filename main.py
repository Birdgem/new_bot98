import asyncio
import aiohttp
import math
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")

BINANCE_URL = "https://api.binance.com/api/v3/klines"

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m"
}

user_state = {}

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ---------- UTILITIES ----------

def ema(values, period):
    k = 2 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def vwap(highs, lows, closes, volumes):
    tpv = 0
    vol_sum = 0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        typical_price = (h + l + c) / 3
        tpv += typical_price * v
        vol_sum += v
    return tpv / vol_sum if vol_sum != 0 else 0


async def fetch_klines(symbol, interval, limit=50):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_URL, params=params) as resp:
            return await resp.json()


# ---------- KEYBOARDS ----------

def pairs_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"pair_{p}")]
            for p in PAIRS
        ]
    )


def timeframe_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=tf, callback_data=f"tf_{tf}")]
            for tf in TIMEFRAMES
        ]
    )


# ---------- HANDLERS ----------

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Я анализирую рынок по:\n"
        "• EMA 7\n"
        "• EMA 25\n"
        "• VWAP\n\n"
        "Нажми /analyze",
    )


@dp.message(Command("analyze"))
async def analyze(message: Message):
    await message.answer(
        "📊 Выбери торговую пару:",
        reply_markup=pairs_keyboard()
    )


@dp.callback_query(F.data.startswith("pair_"))
async def choose_pair(callback):
    pair = callback.data.split("_")[1]
    user_state[callback.from_user.id] = {"pair": pair}

    await callback.message.edit_text(
        f"⏱ Пара выбрана: {pair}\n\nВыбери таймфрейм:",
        reply_markup=timeframe_keyboard()
    )


@dp.callback_query(F.data.startswith("tf_"))
async def choose_tf(callback):
    tf = callback.data.split("_")[1]
    state = user_state.get(callback.from_user.id)

    if not state:
        await callback.answer("Начни с /analyze")
        return

    pair = state["pair"]

    klines = await fetch_klines(pair, TIMEFRAMES[tf])

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    price = closes[-1]
    ema7 = ema(closes[-7:], 7)
    ema25 = ema(closes[-25:], 25)
    vwap_val = vwap(highs, lows, closes, volumes)

    if ema7 > ema25 and price > vwap_val:
        trend = "📈 ЛОНГ"
        reason = "Цена выше VWAP"
    elif ema7 < ema25 and price < vwap_val:
        trend = "📉 ШОРТ"
        reason = "Цена ниже VWAP"
    else:
        trend = "⏸ НЕТ СДЕЛКИ"
        reason = "Флэт / неопределённость"

    text = (
        f"📊 Анализ {pair}\n"
        f"⏱ Таймфрейм: {tf}\n\n"
        f"💰 Цена: {price:.4f}\n"
        f"EMA 7: {ema7:.4f}\n"
        f"EMA 25: {ema25:.4f}\n"
        f"VWAP: {vwap_val:.4f}\n\n"
        f"🚦 Тренд: {trend}\n"
        f"📌 {reason}"
    )

    await callback.message.edit_text(text)


# ---------- START ----------

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

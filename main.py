import asyncio
import time
import aiohttp
from typing import Dict, List

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ParseMode

# ===================== НАСТРОЙКИ =====================

BOT_TOKENS = [
    "TOKEN_1",
    # "TOKEN_2",  # просто добавляешь сюда
]

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = "5m"

COOLDOWN_SECONDS = 30  # откат между анализами

BINANCE_API = "https://api.binance.com/api/v3/klines"

last_run: Dict[int, float] = {}

# ===================== КЛАВИАТУРЫ =====================

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Анализ", callback_data="analyze")],
        [InlineKeyboardButton(text="📈 Статус бота", callback_data="status")]
    ])

def symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s, callback_data=f"symbol:{s}")]
        for s in SYMBOLS
    ])

# ===================== УТИЛИТЫ =====================

async def fetch_klines(symbol: str, limit: int = 100):
    params = {
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": limit
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_API, params=params) as resp:
            return await resp.json()

def ema(values: List[float], period: int):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period
    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

def vwap(closes: List[float], volumes: List[float]):
    total_vol = sum(volumes)
    if total_vol == 0:
        return None
    return sum(c * v for c, v in zip(closes, volumes)) / total_vol

# ===================== АНАЛИЗ =====================

async def analyze_symbol(symbol: str):
    klines = await fetch_klines(symbol)

    if not isinstance(klines, list) or len(klines) < 30:
        return None

    closes = []
    volumes = []

    for k in klines:
        try:
            closes.append(float(k[4]))
            volumes.append(float(k[5]))
        except (IndexError, ValueError):
            continue

    if len(closes) < 30:
        return None

    price = closes[-1]
    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)
    vw = vwap(closes, volumes)

    if not all([ema7, ema25, vw]):
        return None

    avg_volume = sum(volumes[-20:]) / 20
    last_volume = volumes[-1]
    volume_ok = last_volume > avg_volume

    trend = "🟢 Бычий" if ema7 > ema25 else "🔴 Медвежий"

    if price > ema7 > ema25 and price > vw and volume_ok:
        signal = "📈 ЛОНГ"
    elif price < ema7 < ema25 and price < vw and volume_ok:
        signal = "📉 ШОРТ"
    else:
        signal = "⏸ ФЛЭТ"

    link = f"https://www.binance.com/ru/futures/{symbol}"

    text = (
        f"📊 <b>{symbol}</b>\n"
        f"⏱ Таймфрейм: {TIMEFRAME}\n\n"
        f"💰 Цена: {price:.4f}\n"
        f"EMA 7: {ema7:.4f}\n"
        f"EMA 25: {ema25:.4f}\n"
        f"VWAP: {vw:.4f}\n\n"
        f"📦 Объём: {'✔️' if volume_ok else '❌'}\n"
        f"🐂 Тренд: {trend}\n\n"
        f"🚦 Сигнал: <b>{signal}</b>\n\n"
        f"🔗 <a href='{link}'>Открыть пару</a>"
    )

    return text

# ===================== ХЕНДЛЕРЫ =====================

async def start_cmd(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Я сигнальный бот:\n"
        "EMA 7 / EMA 25 / VWAP + объём\n\n"
        "Выбери действие 👇",
        reply_markup=main_keyboard()
    )

async def status_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "✅ Бот работает\n"
        f"📊 Пар: {len(SYMBOLS)}\n"
        f"⏱ Таймфрейм: {TIMEFRAME}\n"
        f"⏳ Откат: {COOLDOWN_SECONDS} сек"
    )

async def analyze_cb(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Выбери торговую пару:",
        reply_markup=symbols_keyboard()
    )

async def symbol_cb(callback: CallbackQuery):
    user_id = callback.from_user.id
    now = time.time()

    if user_id in last_run and now - last_run[user_id] < COOLDOWN_SECONDS:
        await callback.answer("⏳ Подожди перед следующим запросом", show_alert=True)
        return

    last_run[user_id] = now

    symbol = callback.data.split(":")[1]
    await callback.answer("⏳ Анализирую...")

    result = await analyze_symbol(symbol)

    if not result:
        await callback.message.answer("⚠️ Недостаточно данных для анализа")
        return

    await callback.message.answer(result, parse_mode=ParseMode.HTML)

# ===================== ЗАПУСК =====================

async def run_bot(token: str):
    bot = Bot(token=token)
    dp = Dispatcher()

    dp.message.register(start_cmd, Command("start"))
    dp.callback_query.register(analyze_cb, F.data == "analyze")
    dp.callback_query.register(status_cb, F.data == "status")
    dp.callback_query.register(symbol_cb, F.data.startswith("symbol:"))

    await dp.start_polling(bot)

async def main():
    await asyncio.gather(*(run_bot(t) for t in BOT_TOKENS))

if __name__ == "__main__":
    asyncio.run(main())
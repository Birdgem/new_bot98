import asyncio
import aiohttp
import time
import os
from typing import List, Dict

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")        # токен бота
ADMIN_ID = int(os.getenv("ADMIN_ID"))     # твой telegram user_id

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

TIMEFRAME = "5m"
SCAN_INTERVAL = 300        # скан рынка (сек)
ALIVE_INTERVAL = 3600      # бот жив (сек)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

# защита от спама одинаковых сигналов
last_signal: Dict[str, str] = {}

start_time = time.time()

# ================== УТИЛИТЫ ==================

async def fetch_klines(symbol: str, limit: int = 100):
    params = {
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": limit
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_KLINES, params=params) as r:
            return await r.json()


def ema(values: List[float], period: int):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def vwap(prices: List[float], volumes: List[float]):
    total = sum(volumes)
    if total == 0:
        return None
    return sum(p * v for p, v in zip(prices, volumes)) / total


# ================== АНАЛИЗ ==================

async def analyze(symbol: str):
    klines = await fetch_klines(symbol)

    if not isinstance(klines, list) or len(klines) < 30:
        return None

    closes, highs, lows, volumes = [], [], [], []

    for k in klines:
        try:
            closes.append(float(k[4]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
            volumes.append(float(k[5]))
        except Exception:
            return None

    price = closes[-1]

    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)
    vw = vwap(closes, volumes)

    if not all([ema7, ema25, vw]):
        return None

    avg_volume = sum(volumes[-20:]) / 20
    vol_ratio = volumes[-1] / avg_volume if avg_volume else 0

    # тренд
    bullish = ema7 > ema25
    bearish = ema7 < ema25

    # сигналы
    signal = None

    if bullish and price > vw:
        signal = "📈 ЛОНГ"
        if vol_ratio > 1.5:
            signal = "🔥 ЛОНГ"

    elif bearish and price < vw:
        signal = "📉 ШОРТ"
        if vol_ratio > 1.5:
            signal = "🔥 ШОРТ"

    # пробой
    high_break = price > max(highs[-20:])
    low_break = price < min(lows[-20:])

    if high_break and vol_ratio > 1.5:
        signal = "🚀 ПРОБОЙ ВВЕРХ"

    if low_break and vol_ratio > 1.5:
        signal = "💥 ПРОБОЙ ВНИЗ"

    if not signal:
        return None

    return {
        "symbol": symbol,
        "signal": signal,
        "price": price,
        "ema7": ema7,
        "ema25": ema25,
        "vwap": vw,
        "volume": vol_ratio,
    }


# ================== БОТ ==================

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🟢 Сигнальный бот запущен")


async def scanner():
    while True:
        for symbol in SYMBOLS:
            result = await analyze(symbol)
            if not result:
                continue

            key = f"{symbol}"
            if last_signal.get(key) == result["signal"]:
                continue

            last_signal[key] = result["signal"]

            text = (
                f"📊 {symbol}\n"
                f"🚦 {result['signal']}\n\n"
                f"Цена: {result['price']:.4f}\n"
                f"EMA7: {result['ema7']:.4f}\n"
                f"EMA25: {result['ema25']:.4f}\n"
                f"VWAP: {result['vwap']:.4f}\n"
                f"Объём x{result['volume']:.2f}\n\n"
                f"https://www.binance.com/futures/{symbol}"
            )

            await bot.send_message(ADMIN_ID, text)

        await asyncio.sleep(SCAN_INTERVAL)


async def alive_ping():
    while True:
        uptime = int((time.time() - start_time) / 60)
        await bot.send_message(
            ADMIN_ID,
            f"🟢 Бот жив\n⏱ Аптайм: {uptime} мин"
        )
        await asyncio.sleep(ALIVE_INTERVAL)


async def main():
    asyncio.create_task(scanner())
    asyncio.create_task(alive_ping())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
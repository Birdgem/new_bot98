import asyncio
import aiohttp
import time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ =================

TOKEN = "PASTE_YOUR_TOKEN_HERE"
ADMIN_ID = 123456789

TIMEFRAME = "5m"
SCAN_INTERVAL = 300  # 5 минут

BINANCE_URL = "https://api.binance.com/api/v3/klines"

# ================= ПАРЫ =================

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

last_signal = {}

# ================= BOT =================

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= КЛАВИАТУРА =================

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

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(*buttons)
    return kb

# ================= BINANCE =================

async def fetch_klines(symbol: str, interval: str, limit: int = 100):
    params = {
        "symbol": symbol + "USDT",
        "interval": interval,
        "limit": limit
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_URL, params=params) as resp:
            return await resp.json()

def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for price in values[1:]:
        e = price * k + e * (1 - k)
    return e

def vwap(closes, volumes):
    total = sum(volumes)
    if total == 0:
        return None
    return sum(c * v for c, v in zip(closes, volumes)) / total

# ================= АНАЛИЗ =================

async def analyze_pair(pair: str):
    klines = await fetch_klines(pair, TIMEFRAME)
    if not isinstance(klines, list) or len(klines) < 30:
        return None

    closes = [float(k[4]) for k in klines]
    volumes = [float(k[5]) for k in klines]

    price = closes[-1]
    ema7 = ema(closes[-7:], 7)
    ema25 = ema(closes[-25:], 25)
    vw = vwap(closes, volumes)

    if not vw:
        return None

    if price > ema7 > ema25 and price > vw:
        signal = "📈 ЛОНГ"
    elif price < ema7 < ema25 and price < vw:
        signal = "📉 ШОРТ"
    else:
        return None

    text = (
        f"📊 {pair}USDT ({TIMEFRAME})\n"
        f"{signal}\n\n"
        f"Цена: {price:.4f}\n"
        f"EMA7: {ema7:.4f}\n"
        f"EMA25: {ema25:.4f}\n"
        f"VWAP: {vw:.4f}\n\n"
        f"https://www.binance.com/ru/futures/{pair}USDT"
    )
    return text

# ================= HANDLERS =================

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "⚙️ Управление торговыми парами\n\n"
        "🟢 — включена\n"
        "🔴 — выключена",
        reply_markup=pairs_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("toggle:"))
async def toggle_pair(callback: types.CallbackQuery):
    pair = callback.data.split(":")[1]
    PAIRS[pair] = not PAIRS[pair]

    await callback.answer(
        f"{pair} {'включена' if PAIRS[pair] else 'выключена'}"
    )
    await callback.message.edit_reply_markup(reply_markup=pairs_keyboard())

# ================= SCANNER =================

async def scanner():
    while True:
        for pair, enabled in PAIRS.items():
            if not enabled:
                continue

            try:
                result = await analyze_pair(pair)
                if not result:
                    continue

                if last_signal.get(pair) == result:
                    continue

                last_signal[pair] = result
                await bot.send_message(ADMIN_ID, result)

            except Exception as e:
                print(f"{pair} error:", e)

        await asyncio.sleep(SCAN_INTERVAL)

# ================= MAIN =================

async def main():
    asyncio.create_task(scanner())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
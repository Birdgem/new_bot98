import os
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

BINANCE_URL = "https://api.binance.com/api/v3/klines"

PAIRS = [
    "HUSDT", "SOLUSDT", "ETHUSDT", "RIVERUSDT", "LIGHTUSDT",
    "BEATUSDT", "CYSUSDT", "ZPKUSDT", "RAVEUSDT", "DOGEUSDT"
]

ENABLED_PAIRS = {p: False for p in PAIRS}
TIMEFRAMES = ["1m", "5m", "15m"]
CURRENT_TF = "5m"

LAST_SIGNAL = {}

# ====== UTILS ======
def ema(data, period):
    k = 2 / (period + 1)
    e = data[0]
    for p in data[1:]:
        e = p * k + e * (1 - k)
    return e

def vwap(closes, volumes):
    return sum(c * v for c, v in zip(closes, volumes)) / sum(volumes)

# ====== BINANCE ======
async def get_klines(symbol, interval, limit=100):
    async with aiohttp.ClientSession() as s:
        async with s.get(BINANCE_URL, params={
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }) as r:
            return await r.json()

# ====== ANALYSIS ======
async def analyze(pair):
    kl = await get_klines(pair, CURRENT_TF)
    closes = [float(k[4]) for k in kl]
    volumes = [float(k[5]) for k in kl]

    price = closes[-1]
    ema7 = ema(closes[-7:], 7)
    ema25 = ema(closes[-25:], 25)
    vw = vwap(closes, volumes)
    vol_now = volumes[-1]
    vol_avg = sum(volumes[-20:]) / 20

    strength = ""
    if vol_now > vol_avg * 1.8:
        strength = "🔥🔥"
    elif vol_now > vol_avg * 1.3:
        strength = "🔥"

    if price > ema7 > ema25 and price > vw:
        direction = f"📈 ЛОНГ {strength}"
    elif price < ema7 < ema25 and price < vw:
        direction = f"📉 ШОРТ {strength}"
    else:
        return None

    if LAST_SIGNAL.get(pair) == direction:
        return None

    LAST_SIGNAL[pair] = direction

    return (
        f"📊 {pair} ({CURRENT_TF})\n"
        f"💰 Цена: {price:.4f}\n"
        f"EMA7: {ema7:.4f}\n"
        f"EMA25: {ema25:.4f}\n"
        f"VWAP: {vw:.4f}\n"
        f"📦 Объём: {'высокий' if strength else 'обычный'}\n\n"
        f"{direction}\n"
        f"🔗 https://www.binance.com/ru/futures/{pair}"
    )

# ====== KEYBOARDS ======
def main_keyboard():
    rows = []
    for p, on in ENABLED_PAIRS.items():
        rows.append([
            InlineKeyboardButton(
                text=("🟢 " if on else "🔴 ") + p.replace("USDT",""),
                callback_data=f"pair:{p}"
            )
        ])
    rows.append([
        InlineKeyboardButton(text=f"⏱ TF: {CURRENT_TF}", callback_data="tf")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ====== COMMANDS ======
@dp.message(Command("start"))
async def start(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer("⚙️ Управление ботом", reply_markup=main_keyboard())

@dp.callback_query()
async def callbacks(c: types.CallbackQuery):
    global CURRENT_TF

    if c.from_user.id != ADMIN_ID:
        return

    if c.data.startswith("pair:"):
        p = c.data.split(":")[1]
        ENABLED_PAIRS[p] = not ENABLED_PAIRS[p]

    elif c.data == "tf":
        i = TIMEFRAMES.index(CURRENT_TF)
        CURRENT_TF = TIMEFRAMES[(i + 1) % len(TIMEFRAMES)]

    await c.message.edit_reply_markup(reply_markup=main_keyboard())
    await c.answer()

# ====== SCANNER ======
async def scanner():
    while True:
        for p, on in ENABLED_PAIRS.items():
            if not on:
                continue
            try:
                res = await analyze(p)
                if res:
                    await bot.send_message(ADMIN_ID, res)
            except Exception as e:
                print(p, e)
        await asyncio.sleep(60)

# ====== HEARTBEAT ======
async def heartbeat():
    while True:
        await bot.send_message(ADMIN_ID, "✅ Бот жив и работает")
        await asyncio.sleep(3600)

# ====== MAIN ======
async def main():
    asyncio.create_task(scanner())
    asyncio.create_task(heartbeat())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
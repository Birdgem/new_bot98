import os
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import math

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
LAST_SCAN_TS = 0
START_TS = time.time()

SCAN_INTERVAL = 60
HEARTBEAT_INTERVAL = 3600

# ========= INDICATORS =========
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    e = sum(data[:period]) / period
    for p in data[period:]:
        e = p * k + e * (1 - k)
    return e

def rsi(data, period=14):
    if len(data) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = data[-i] - data[-i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period if losses else 0.0001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(data):
    ema12 = ema(data, 12)
    ema26 = ema(data, 26)
    if not ema12 or not ema26:
        return None, None
    macd_line = ema12 - ema26
    signal = ema([macd_line] * 9, 9)
    return macd_line, signal

def vwap(closes, volumes):
    total = sum(volumes)
    if total == 0:
        return None
    return sum(c * v for c, v in zip(closes, volumes)) / total

def is_flat(closes):
    if len(closes) < 20:
        return True
    high = max(closes[-20:])
    low = min(closes[-20:])
    return (high - low) / closes[-1] < 0.01

# ========= BINANCE =========
async def get_klines(symbol, interval, limit=120):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            BINANCE_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit}
        ) as r:
            data = await r.json()
            return data if isinstance(data, list) else []

# ========= ANALYSIS =========
async def analyze(pair):
    kl = await get_klines(pair, CURRENT_TF)
    if len(kl) < 50:
        return None

    closes, volumes = [], []
    for k in kl:
        closes.append(float(k[4]))
        volumes.append(float(k[5]))

    price = closes[-1]

    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)
    vw = vwap(closes, volumes)

    if not all([ema7, ema25, vw]):
        return None

    vol_avg = sum(volumes[-20:]) / 20
    vol_now = volumes[-1]

    signal = None
    strength = ""

    if price > ema7 > ema25 and price > vw:
        signal = "📈 ЛОНГ"
    elif price < ema7 < ema25 and price < price < vw:
        signal = "📉 ШОРТ"

    if signal:
        spread = abs(ema7 - ema25) / price
        if vol_now > vol_avg * 1.8 and spread > 0.002:
            strength = "🔥🔥"
        elif vol_now > vol_avg * 1.3:
            strength = "🔥"

    # ---- CONTEXT (НЕ ФИЛЬТР) ----
    rsi_val = rsi(closes)
    macd_line, macd_signal = macd(closes)
    flat = is_flat(closes)

    macd_text = "подтверждает" if macd_line and macd_signal and macd_line > macd_signal else "не подтверждает"

    return {
        "pair": pair,
        "price": price,
        "ema7": ema7,
        "ema25": ema25,
        "vwap": vw,
        "signal": signal,
        "strength": strength,
        "rsi": rsi_val,
        "macd": macd_text,
        "flat": "да" if flat else "нет"
    }

# ========= KEYBOARD =========
def main_keyboard():
    rows = []
    for p, on in ENABLED_PAIRS.items():
        rows.append([
            InlineKeyboardButton(
                text=("🟢 " if on else "🔴 ") + p.replace("USDT", ""),
                callback_data=f"pair:{p}"
            )
        ])

    rows.append([
        InlineKeyboardButton(text=f"⏱ {CURRENT_TF}", callback_data="tf"),
        InlineKeyboardButton(text="📊 Статус", callback_data="status")
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ========= HANDLERS =========
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

    elif c.data == "status":
        uptime = int((time.time() - START_TS) / 60)
        enabled = [p for p, v in ENABLED_PAIRS.items() if v]
        await c.message.answer(
            f"📊 Статус бота\n\n"
            f"🕒 Аптайм: {uptime} мин\n"
            f"⏱ TF: {CURRENT_TF}\n"
            f"📈 Активные пары: {', '.join(enabled) if enabled else 'нет'}"
        )

    await c.message.edit_reply_markup(reply_markup=main_keyboard())
    await c.answer()

# ========= SCANNER =========
async def scanner():
    global LAST_SCAN_TS
    while True:
        LAST_SCAN_TS = time.time()
        for p, on in ENABLED_PAIRS.items():
            if not on:
                continue

            try:
                r = await analyze(p)
                if not r or not r["signal"]:
                    continue

                key = f"{p}:{r['signal']}:{r['strength']}"
                if LAST_SIGNAL.get(p) == key:
                    continue

                LAST_SIGNAL[p] = key

                text = (
                    f"📊 {p} ({CURRENT_TF})\n"
                    f"{r['signal']} {r['strength']}\n\n"
                    f"📌 Контекст:\n"
                    f"• RSI: {r['rsi']:.1f}\n"
                    f"• MACD: {r['macd']}\n"
                    f"• Флэт: {r['flat']}\n\n"
                    f"Цена: {r['price']:.4f}\n"
                    f"EMA7: {r['ema7']:.4f}\n"
                    f"EMA25: {r['ema25']:.4f}\n"
                    f"VWAP: {r['vwap']:.4f}"
                )

                await bot.send_message(ADMIN_ID, text)

            except Exception as e:
                print(p, e)

        await asyncio.sleep(SCAN_INTERVAL)

# ========= HEARTBEAT =========
async def heartbeat():
    while True:
        await bot.send_message(ADMIN_ID, "✅ Бот жив и работает")
        await asyncio.sleep(HEARTBEAT_INTERVAL)

# ========= MAIN =========
async def main():
    asyncio.create_task(scanner())
    asyncio.create_task(heartbeat())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

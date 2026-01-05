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
GRID_ENABLED = {p: False for p in PAIRS}

TIMEFRAMES = ["1m", "5m", "15m"]
CURRENT_TF = "15m"

STRICT_MODE = False

LAST_SIGNAL = {}
START_TS = time.time()

SCAN_INTERVAL = 60
HEARTBEAT_INTERVAL = 3600

# ===== GRID STATE (DRY-RUN) =====
GRID_STATE = {}

VIRTUAL_BALANCE = 1000.0
GRID_LEVELS = 10

# ========= UTILS =========
def ema(data, period):
    if len(data) < period:
        return None
    k = 2 / (period + 1)
    e = sum(data[:period]) / period
    for p in data[period:]:
        e = p * k + e * (1 - k)
    return e

def vwap(closes, volumes):
    total_vol = sum(volumes)
    if total_vol == 0:
        return None
    return sum(c * v for c, v in zip(closes, volumes)) / total_vol

# ========= BINANCE =========
async def get_klines(symbol, interval, limit=120):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            BINANCE_URL,
            params={"symbol": symbol, "interval": interval, "limit": limit}
        ) as r:
            data = await r.json()
            return data if isinstance(data, list) else []

# ========= BTC CONTEXT =========
async def btc_context():
    kl = await get_klines("BTCUSDT", CURRENT_TF)
    if len(kl) < 30:
        return "неопределён"

    closes = [float(k[4]) for k in kl]
    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)

    if closes[-1] > ema7 > ema25:
        return "бычий"
    elif closes[-1] < ema7 < ema25:
        return "медвежий"
    return "флэт"

# ========= GRID =========
def build_grid(pair, highs, lows):
    high = max(highs[-50:])
    low = min(lows[-50:])
    step = (high - low) / GRID_LEVELS

    levels = [low + step * i for i in range(1, GRID_LEVELS)]
    GRID_STATE[pair] = {
        "levels": levels,
        "position": [],
        "pnl": 0.0,
        "trades": 0
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
        InlineKeyboardButton(
            text=("🧱 Сетка: ON" if GRID_ENABLED[p] else "🧱 Сетка: OFF"),
            callback_data=f"grid:{p}"
        )
        for p in PAIRS if ENABLED_PAIRS[p]
    ])

    rows.append([
        InlineKeyboardButton(
            text=("🔴 Строгий" if STRICT_MODE else "🟢 Свободный"),
            callback_data="strict"
        ),
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
    global STRICT_MODE

    if c.from_user.id != ADMIN_ID:
        return

    if c.data.startswith("pair:"):
        p = c.data.split(":")[1]
        ENABLED_PAIRS[p] = not ENABLED_PAIRS[p]

    elif c.data.startswith("grid:"):
        p = c.data.split(":")[1]
        GRID_ENABLED[p] = not GRID_ENABLED[p]
        GRID_STATE.pop(p, None)

    elif c.data == "strict":
        STRICT_MODE = not STRICT_MODE

    elif c.data == "status":
        await c.message.answer(
            "📊 Статус бота\n\n"
            f"🕒 Аптайм: {int((time.time() - START_TS)/60)} мин\n"
            f"🧠 Режим: {'СТРОГИЙ' if STRICT_MODE else 'СВОБОДНЫЙ'}\n"
            f"🧱 Активные сетки: {', '.join([p for p,v in GRID_ENABLED.items() if v]) or 'нет'}"
        )

    await c.message.edit_reply_markup(reply_markup=main_keyboard())
    await c.answer()

# ========= SCANNER =========
async def scanner():
    while True:
        btc_ctx = await btc_context()

        for p in PAIRS:
            if not ENABLED_PAIRS[p] or not GRID_ENABLED[p]:
                continue

            kl = await get_klines(p, CURRENT_TF)
            closes = [float(k[4]) for k in kl]
            highs = [float(k[2]) for k in kl]
            lows = [float(k[3]) for k in kl]
            price = closes[-1]

            if p not in GRID_STATE:
                build_grid(p, highs, lows)
                await bot.send_message(
                    ADMIN_ID,
                    f"🧱 СЕТКА (DRY-RUN) — {p}\n"
                    f"Диапазон: {min(lows[-50:]):.4f} – {max(highs[-50:]):.4f}\n"
                    f"Уровней: {GRID_LEVELS}"
                )

            grid = GRID_STATE[p]

            for lvl in grid["levels"]:
                if price <= lvl and lvl not in grid["position"]:
                    grid["position"].append(lvl)
                    grid["trades"] += 1

                if price > lvl and lvl in grid["position"]:
                    profit = (price - lvl) / lvl * 100
                    grid["pnl"] += profit
                    grid["position"].remove(lvl)
                    grid["trades"] += 1

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

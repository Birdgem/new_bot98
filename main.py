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

# ===== GRID UI STATE (ШАГ 1) =====
GRID_ENABLED = {p: False for p in PAIRS}
GRID_MODE = "FREE"  # FREE / STRICT

# ===== GRID FUTURE PARAMS (НЕ ИСПОЛЬЗУЮТСЯ ПОКА) =====
GRID_DRY_RUN_DEPOSIT = 100.0   # $
GRID_DRY_RUN_LEVERAGE = 10     # x10

TIMEFRAMES = ["1m", "5m", "15m"]
CURRENT_TF = "15m"

LAST_SIGNAL = {}
START_TS = time.time()

SCAN_INTERVAL = 60
HEARTBEAT_INTERVAL = 3600

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

# ========= KEYBOARD =========
def main_keyboard():
    rows = []

    # пары
    for p, on in ENABLED_PAIRS.items():
        rows.append([
            InlineKeyboardButton(
                text=("🟢 " if on else "🔴 ") + p.replace("USDT", ""),
                callback_data=f"pair:{p}"
            )
        ])

    # сетка (только для включённых пар)
    active_grid_pairs = [p for p in PAIRS if ENABLED_PAIRS[p]]
    if active_grid_pairs:
        rows.append([
            InlineKeyboardButton(
                text="🧱 Сетка: ON" if any(GRID_ENABLED[p] for p in active_grid_pairs) else "🧱 Сетка: OFF",
                callback_data="grid_toggle"
            )
        ])

    # режим + статус
    rows.append([
        InlineKeyboardButton(
            text=f"🧠 Режим: {'СТРОГИЙ' if GRID_MODE == 'STRICT' else 'СВОБОДНЫЙ'}",
            callback_data="grid_mode"
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
    global GRID_MODE

    if c.from_user.id != ADMIN_ID:
        await c.answer()
        return

    if c.data.startswith("pair:"):
        p = c.data.split(":")[1]
        ENABLED_PAIRS[p] = not ENABLED_PAIRS[p]
        if not ENABLED_PAIRS[p]:
            GRID_ENABLED[p] = False  # авто-выкл сетки

    elif c.data == "grid_toggle":
        for p in PAIRS:
            if ENABLED_PAIRS[p]:
                GRID_ENABLED[p] = not GRID_ENABLED[p]

    elif c.data == "grid_mode":
        GRID_MODE = "STRICT" if GRID_MODE == "FREE" else "FREE"

    elif c.data == "status":
        enabled_pairs = [p for p, v in ENABLED_PAIRS.items() if v]
        grid_pairs = [p for p, v in GRID_ENABLED.items() if v]

        await c.message.answer(
            "📊 Статус бота\n\n"
            f"🕒 Аптайм: {int((time.time() - START_TS)/60)} мин\n"
            f"⏱ TF: {CURRENT_TF}\n"
            f"🧠 Режим: {'СТРОГИЙ' if GRID_MODE=='STRICT' else 'СВОБОДНЫЙ'}\n"
            f"📈 Активные пары: {', '.join(enabled_pairs) if enabled_pairs else 'нет'}\n"
            f"🧱 Сетка: {', '.join(grid_pairs) if grid_pairs else 'выкл'}\n\n"
            f"(DRY-RUN: депо {GRID_DRY_RUN_DEPOSIT}$, плечо x{GRID_DRY_RUN_LEVERAGE})"
        )

    await c.message.edit_reply_markup(reply_markup=main_keyboard())
    await c.answer()

# ========= SCANNER (ПОКА ПУСТОЙ ДЛЯ СЕТКИ) =========
async def scanner():
    while True:
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

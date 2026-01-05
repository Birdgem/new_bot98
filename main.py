import os
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

PAIRS = [
    "HUSDT", "SOLUSDT", "ETHUSDT", "RIVERUSDT", "LIGHTUSDT",
    "BEATUSDT", "CYSUSDT", "ZPKUSDT", "RAVEUSDT", "DOGEUSDT"
]

ENABLED_PAIRS = {p: False for p in PAIRS}
GRID_ENABLED = {p: False for p in PAIRS}

TIMEFRAMES = ["1m", "5m", "15m"]
CURRENT_TF = "15m"

GRID_MODE = "FREE"  # FREE / STRICT

GRID_DRY_RUN_DEPOSIT = 100.0
GRID_DRY_RUN_LEVERAGE = 10

START_TS = time.time()

SCAN_INTERVAL = 60
HEARTBEAT_INTERVAL = 3600

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
            text="🧱 Сетка: ON" if any(GRID_ENABLED[p] for p in PAIRS) else "🧱 Сетка: OFF",
            callback_data="grid_toggle"
        )
    ])

    rows.append([
        InlineKeyboardButton(text=f"⏱ {CURRENT_TF}", callback_data="tf"),
        InlineKeyboardButton(
            text=f"🧠 Режим: {'СТРОГИЙ' if GRID_MODE=='STRICT' else 'СВОБОДНЫЙ'}",
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
    global CURRENT_TF, GRID_MODE

    if c.from_user.id != ADMIN_ID:
        await c.answer()
        return

    # ---- STATE CHANGES ----
    if c.data.startswith("pair:"):
        p = c.data.split(":")[1]
        ENABLED_PAIRS[p] = not ENABLED_PAIRS[p]
        if not ENABLED_PAIRS[p]:
            GRID_ENABLED[p] = False

    elif c.data == "grid_toggle":
        for p in PAIRS:
            if ENABLED_PAIRS[p]:
                GRID_ENABLED[p] = not GRID_ENABLED[p]

    elif c.data == "grid_mode":
        GRID_MODE = "STRICT" if GRID_MODE == "FREE" else "FREE"

    elif c.data == "tf":
        i = TIMEFRAMES.index(CURRENT_TF)
        CURRENT_TF = TIMEFRAMES[(i + 1) % len(TIMEFRAMES)]

    elif c.data == "status":
        enabled = [p for p, v in ENABLED_PAIRS.items() if v]
        grid = [p for p, v in GRID_ENABLED.items() if v]

        await c.message.answer(
            "📊 Статус бота\n\n"
            f"🕒 Аптайм: {int((time.time()-START_TS)/60)} мин\n"
            f"⏱ TF: {CURRENT_TF}\n"
            f"🧠 Режим: {'СТРОГИЙ' if GRID_MODE=='STRICT' else 'СВОБОДНЫЙ'}\n"
            f"📈 Активные пары: {', '.join(enabled) if enabled else 'нет'}\n"
            f"🧱 Сетка: {', '.join(grid) if grid else 'выкл'}\n\n"
            f"(DRY-RUN: депо {GRID_DRY_RUN_DEPOSIT}$, плечо x{GRID_DRY_RUN_LEVERAGE})"
        )

    # ---- SAFE UI UPDATE ----
    try:
        await c.message.edit_reply_markup(reply_markup=main_keyboard())
    except TelegramBadRequest:
        pass  # сообщение нельзя обновить — игнорируем

    await c.answer()

# ========= BACKGROUND =========
async def scanner():
    while True:
        await asyncio.sleep(SCAN_INTERVAL)

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

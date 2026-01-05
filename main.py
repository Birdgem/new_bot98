import os
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========= CONFIG =========
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

BINANCE_URL = "https://api.binance.com/api/v3/klines"

PAIRS = [
    "HUSDT", "SOLUSDT", "ETHUSDT", "RIVERUSDT", "LIGHTUSDT",
    "BEATUSDT", "CYSUSDT", "ZPKUSDT", "RAVEUSDT", "DOGEUSDT"
]

TIMEFRAMES = ["1m", "5m", "15m"]
CURRENT_TF = "15m"

SCAN_INTERVAL = 60
HEARTBEAT_INTERVAL = 3600
START_TS = time.time()

# ========= SIGNAL STATE =========
ENABLED_PAIRS = {p: False for p in PAIRS}
LAST_SIGNAL = {}
LAST_BREAKOUT = {}
LAST_SCAN_TS = 0

# ========= GRID CONFIG (DRY-RUN v3) =========
GRID_ENABLED = {p: False for p in PAIRS}
GRID_STATE = {}

GRID_DEPOSIT = 100.0
GRID_LEVERAGE = 10
GRID_CAPITAL = GRID_DEPOSIT * GRID_LEVERAGE

GRID_STEP_PCT = 0.005   # 0.5%
GRID_LEVELS = 6

GRID_STATS = {
    "trades": 0,
    "pnl": 0.0
}

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

# ========= ANALYSIS =========
async def analyze(pair):
    kl = await get_klines(pair, CURRENT_TF)
    if len(kl) < 30:
        return None, None

    closes, volumes, highs, lows = [], [], [], []
    for k in kl:
        closes.append(float(k[4]))
        volumes.append(float(k[5]))
        highs.append(float(k[2]))
        lows.append(float(k[3]))

    price = closes[-1]
    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)
    vw = vwap(closes, volumes)

    if not all([ema7, ema25, vw]):
        return None, None

    vol_avg = sum(volumes[-20:]) / 20
    vol_now = volumes[-1]

    signal = None
    strength = None

    if price > ema7 > ema25 and price > vw:
        signal = "📈 ЛОНГ"
    elif price < ema7 < ema25 and price < vw:
        signal = "📉 ШОРТ"

    if signal:
        spread = abs(ema7 - ema25) / price
        if vol_now > vol_avg * 1.8 and spread > 0.002:
            strength = "🔥🔥"
        elif vol_now > vol_avg * 1.3:
            strength = "🔥"

    breakout = None
    if price > max(highs[-20:]) and vol_now > vol_avg * 1.5:
        breakout = "🚀 ПРОБОЙ ВВЕРХ"
    elif price < min(lows[-20:]) and vol_now > vol_avg * 1.5:
        breakout = "💥 ПРОБОЙ ВНИЗ"

    return {
        "pair": pair,
        "price": price,
        "ema7": ema7,
        "ema25": ema25,
        "vwap": vw,
        "signal": signal,
        "strength": strength,
    }, breakout

# ========= GRID LOGIC =========
def init_grid(pair, price):
    step = price * GRID_STEP_PCT
    levels = []

    for i in range(1, GRID_LEVELS + 1):
        buy = price - step * i
        sell = buy + step
        levels.append({
            "buy": buy,
            "sell": sell,
            "active": False
        })

    GRID_STATE[pair] = levels

def grid_tick(pair, price):
    if pair not in GRID_STATE:
        init_grid(pair, price)

    for lvl in GRID_STATE[pair]:
        if not lvl["active"] and price <= lvl["buy"]:
            lvl["active"] = True

        elif lvl["active"] and price >= lvl["sell"]:
            pnl = (lvl["sell"] - lvl["buy"]) * (GRID_CAPITAL / price / GRID_LEVELS)
            GRID_STATS["pnl"] += pnl
            GRID_STATS["trades"] += 1
            lvl["active"] = False

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
        InlineKeyboardButton(text="🧱 Сетка: ON" if any(GRID_ENABLED.values()) else "🧱 Сетка: OFF", callback_data="grid"),
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

    elif c.data == "grid":
        for p in PAIRS:
            GRID_ENABLED[p] = not GRID_ENABLED[p]
            if GRID_ENABLED[p]:
                GRID_STATE.pop(p, None)

    elif c.data == "status":
        uptime = int((time.time() - START_TS) / 60)
        active_pairs = [p for p, v in ENABLED_PAIRS.items() if v]
        active_grids = [p for p, v in GRID_ENABLED.items() if v]

        await c.message.answer(
            "📊 Статус бота\n\n"
            f"🕒 Аптайм: {uptime} мин\n"
            f"⏱ TF: {CURRENT_TF}\n"
            f"📈 Активные пары: {', '.join(active_pairs) if active_pairs else 'нет'}\n"
            f"🧱 Сетка: {', '.join(active_grids) if active_grids else 'выкл'}\n"
            f"📦 Сделок: {GRID_STATS['trades']}\n"
            f"💰 PnL: {GRID_STATS['pnl']:.2f}$\n\n"
            f"(DRY-RUN: депо 100$, плечо x10)"
        )

    await c.message.edit_reply_markup(reply_markup=main_keyboard())
    await c.answer()

# ========= SCANNER =========
async def scanner():
    global LAST_SCAN_TS

    while True:
        LAST_SCAN_TS = time.time()

        for p in PAIRS:
            try:
                kl = await get_klines(p, CURRENT_TF)
                if not kl:
                    continue

                price = float(kl[-1][4])

                if GRID_ENABLED[p]:
                    grid_tick(p, price)

                if not ENABLED_PAIRS[p]:
                    continue

                result, breakout = await analyze(p)
                if not result:
                    continue

                sig_key = f"{p}:{result['signal']}:{result['strength']}"
                if result["signal"] and LAST_SIGNAL.get(p) != sig_key:
                    LAST_SIGNAL[p] = sig_key

                    await bot.send_message(
                        ADMIN_ID,
                        f"📊 {p} ({CURRENT_TF})\n"
                        f"{result['signal']} {result['strength'] or ''}\n\n"
                        f"Цена: {result['price']:.4f}\n"
                        f"EMA7: {result['ema7']:.4f}\n"
                        f"EMA25: {result['ema25']:.4f}\n"
                        f"VWAP: {result['vwap']:.4f}"
                    )

                if breakout and LAST_BREAKOUT.get(p) != breakout:
                    LAST_BREAKOUT[p] = breakout
                    await bot.send_message(ADMIN_ID, f"{p} — {breakout}")

            except Exception as e:
                print("ERR", p, e)

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

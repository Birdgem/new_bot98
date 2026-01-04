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
LAST_BREAKOUT = {}
LAST_SCAN_TS = None
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

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(closes):
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if not ema12 or not ema26:
        return None, None
    macd_line = ema12 - ema26
    signal_line = macd_line  # упрощённо для realtime
    return macd_line, signal_line

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
        try:
            closes.append(float(k[4]))
            volumes.append(float(k[5]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
        except Exception:
            return None, None

    price = closes[-1]
    ema7 = ema(closes, 7)
    ema25 = ema(closes, 25)
    vw = vwap(closes, volumes)
    rsi_val = rsi(closes)
    macd_line, macd_signal = macd(closes)

    if not all([ema7, ema25, vw, rsi_val]):
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

    return (
        {
            "pair": pair,
            "price": price,
            "ema7": ema7,
            "ema25": ema25,
            "vwap": vw,
            "signal": signal,
            "strength": strength,
            "rsi": rsi_val,
            "macd_ok": macd_line >= macd_signal
        },
        breakout
    )

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
        await c.answer()
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
        last_scan = (
            f"{int(time.time() - LAST_SCAN_TS)} сек назад"
            if LAST_SCAN_TS else "ещё не было"
        )

        await c.message.answer(
            "📊 Статус бота\n\n"
            f"🕒 Аптайм: {uptime} мин\n"
            f"⏱ Таймфрейм: {CURRENT_TF}\n"
            f"📈 Активные пары: {', '.join(enabled) if enabled else 'нет'}\n"
            f"🔄 Последний скан: {last_scan}"
        )

    await c.answer()
    await c.message.edit_reply_markup(reply_markup=main_keyboard())

# ========= SCANNER =========
async def scanner():
    global LAST_SCAN_TS
    while True:
        LAST_SCAN_TS = time.time()
        for p, on in ENABLED_PAIRS.items():
            if not on:
                continue

            try:
                result, breakout = await analyze(p)
                if not result:
                    continue

                sig_key = f"{p}:{result['signal']}:{result['strength']}"
                if result["signal"] and LAST_SIGNAL.get(p) != sig_key:
                    LAST_SIGNAL[p] = sig_key

                    text = (
                        f"📊 {p} ({CURRENT_TF})\n"
                        f"{result['signal']} {result['strength'] or ''}\n\n"
                        f"Цена: {result['price']:.4f}\n"
                        f"EMA7: {result['ema7']:.4f}\n"
                        f"EMA25: {result['ema25']:.4f}\n"
                        f"VWAP: {result['vwap']:.4f}\n\n"
                        f"RSI(14): {result['rsi']:.1f} {'✅' if 40 <= result['rsi'] <= 60 else '⚠️'}\n"
                        f"MACD: {'подтверждает ✅' if result['macd_ok'] else 'не подтверждает ❌'}\n\n"
                        f"https://www.binance.com/ru/futures/{p}"
                    )

                    await bot.send_message(ADMIN_ID, text)

                if breakout and LAST_BREAKOUT.get(p) != breakout:
                    LAST_BREAKOUT[p] = breakout
                    await bot.send_message(
                        ADMIN_ID,
                        f"📊 {p} ({CURRENT_TF})\n{breakout}\n\n"
                        f"https://www.binance.com/ru/futures/{p}"
                    )

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

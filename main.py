import asyncio
import os
from typing import List

import ccxt
import pandas as pd

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ======================
# НАСТРОЙКИ
# ======================

BOT_TOKEN = os.getenv("BOT_TOKEN")  # обязательно задать в Render
DEFAULT_SYMBOL = "BTC/USDT"

TIMEFRAMES = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
}

PAIRS = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
]

# ======================
# BINANCE (SPOT)
# ======================

exchange = ccxt.binance({
    "enableRateLimit": True,
})

# ======================
# ИНДИКАТОРЫ
# ======================

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum()

# ======================
# ЗАГРУЗКА ДАННЫХ
# ======================

def load_ohlcv(symbol: str, timeframe: str, limit: int = 150) -> pd.DataFrame:
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    return df

# ======================
# АНАЛИЗ
# ======================

def analyze_market(symbol: str, timeframe: str) -> str:
    df = load_ohlcv(symbol, timeframe)

    df["ema7"] = ema(df["close"], 7)
    df["ema25"] = ema(df["close"], 25)
    df["vwap"] = vwap(df)

    last = df.iloc[-1]

    price = last["close"]
    ema7 = last["ema7"]
    ema25 = last["ema25"]
    vwap_val = last["vwap"]

    trend = "❓"
    if ema7 > ema25:
        trend = "📈 Лонг"
    elif ema7 < ema25:
        trend = "📉 Шорт"

    vwap_state = "выше VWAP" if price > vwap_val else "ниже VWAP"

    text = (
        f"📊 *Анализ {symbol}*\n"
        f"⏱ Таймфрейм: `{timeframe}`\n\n"
        f"💰 Цена: `{price:.4f}`\n"
        f"EMA 7: `{ema7:.4f}`\n"
        f"EMA 25: `{ema25:.4f}`\n"
        f"VWAP: `{vwap_val:.4f}`\n\n"
        f"📌 Тренд: *{trend}*\n"
        f"📍 Цена {vwap_state}\n"
    )

    return text

# ======================
# КЛАВИАТУРЫ
# ======================

def pairs_keyboard():
    kb = InlineKeyboardBuilder()
    for pair in PAIRS:
        kb.button(text=pair, callback_data=f"pair:{pair}")
    kb.adjust(2)
    return kb.as_markup()

def timeframe_keyboard(symbol: str):
    kb = InlineKeyboardBuilder()
    for tf in TIMEFRAMES:
        kb.button(
            text=tf,
            callback_data=f"tf:{symbol}:{tf}"
        )
    kb.adjust(4)
    return kb.as_markup()

# ======================
# HANDLERS
# ======================

async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Я анализирую рынок по EMA 7 / EMA 25 / VWAP.\n\n"
        "Нажми /analyze",
    )

async def cmd_analyze(message: Message):
    await message.answer(
        "Выбери торговую пару:",
        reply_markup=pairs_keyboard()
    )

async def pair_chosen(callback: CallbackQuery):
    symbol = callback.data.split(":")[1]
    await callback.message.edit_text(
        f"Пара: *{symbol}*\n\nВыбери таймфрейм:",
        reply_markup=timeframe_keyboard(symbol),
        parse_mode="Markdown"
    )
    await callback.answer()

async def timeframe_chosen(callback: CallbackQuery):
    _, symbol, timeframe = callback.data.split(":")
    text = analyze_market(symbol, timeframe)
    await callback.message.edit_text(
        text,
        parse_mode="Markdown"
    )
    await callback.answer()

# ======================
# MAIN
# ======================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_analyze, Command("analyze"))

    dp.callback_query.register(pair_chosen, F.data.startswith("pair:"))
    dp.callback_query.register(timeframe_chosen, F.data.startswith("tf:"))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

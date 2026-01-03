import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

# ======================
# CONFIG
# ======================

TOKEN = os.getenv("BOT_TOKEN")  # обязательно добавить в Render → Environment
FIXED_RISK = 100  # $100 фикс

logging.basicConfig(level=logging.INFO)

# ======================
# STATE
# ======================

user_state = {}  # user_id -> dict


def get_state(user_id: int):
    if user_id not in user_state:
        user_state[user_id] = {
            "symbol": "BTCUSDT",
            "side": "LONG",
        }
    return user_state[user_id]


# ======================
# KEYBOARDS
# ======================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Лонг", callback_data="side_LONG"),
                InlineKeyboardButton(text="📉 Шорт", callback_data="side_SHORT"),
            ],
            [
                InlineKeyboardButton(text="📊 График", callback_data="chart"),
            ],
            [
                InlineKeyboardButton(text="BTCUSDT", callback_data="pair_BTCUSDT"),
                InlineKeyboardButton(text="ETHUSDT", callback_data="pair_ETHUSDT"),
            ],
            [
                InlineKeyboardButton(text="SOLUSDT", callback_data="pair_SOLUSDT"),
            ],
        ]
    )


# ======================
# BOT INIT
# ======================

bot = Bot(token=TOKEN)
dp = Dispatcher()


# ======================
# HANDLERS
# ======================

@dp.message(Command("start"))
async def start(message: Message):
    state = get_state(message.from_user.id)

    text = (
        "🤖 *Трейдинг-бот запущен*\n\n"
        f"📌 Пара: `{state['symbol']}`\n"
        f"📌 Режим: `{state['side']}`\n"
        f"💰 Риск: `${FIXED_RISK}` (фикс)\n\n"
        "Выбери действие:"
    )

    await message.answer(
        text,
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )


@dp.callback_query(F.data.startswith("side_"))
async def change_side(call: CallbackQuery):
    side = call.data.split("_")[1]
    state = get_state(call.from_user.id)
    state["side"] = side

    await call.answer(f"Режим: {side}")
    await start(call.message)


@dp.callback_query(F.data.startswith("pair_"))
async def change_pair(call: CallbackQuery):
    pair = call.data.split("_")[1]
    state = get_state(call.from_user.id)
    state["symbol"] = pair

    await call.answer(f"Пара: {pair}")
    await start(call.message)


@dp.callback_query(F.data == "chart")
async def chart(call: CallbackQuery):
    state = get_state(call.from_user.id)
    symbol = state["symbol"]

    url = f"https://www.binance.com/en/futures/{symbol}"

    await call.answer()
    await call.message.answer(
        f"📊 График {symbol}\n{url}"
    )


@dp.message()
async def risk_calculator(message: Message):
    """
    Ожидаем ввод:
    entry stop
    например:
    42500 42100
    """
    try:
        entry, stop = map(float, message.text.replace(",", ".").split())
        diff = abs(entry - stop)

        if diff == 0:
            raise ValueError

        position_size = FIXED_RISK / diff

        await message.answer(
            "📐 *Риск-калькулятор*\n\n"
            f"Вход: `{entry}`\n"
            f"Стоп: `{stop}`\n"
            f"Риск: `${FIXED_RISK}`\n\n"
            f"📦 *Размер позиции:* `{position_size:.4f}`",
            parse_mode="Markdown"
        )

    except Exception:
        await message.answer(
            "❌ Неверный формат\n\n"
            "Введи так:\n"
            "`42500 42100`",
            parse_mode="Markdown"
        )


# ======================
# STARTUP
# ======================

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN not set")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

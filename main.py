import os
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

TOKEN = os.environ["BOT_TOKEN"]

bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("✅ Бот запущен на Render + Python 3.13")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

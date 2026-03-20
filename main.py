"""
Qarz Tizimi — Asosiy bot fayli
"""

from create_db import create_all_tables
create_all_tables()

import asyncio
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from handlers.admin import admin_router
from handlers.shop import shop_router
from handlers.user import user_router
from scheduler import setup_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Routerlarni ulash
    dp.include_router(admin_router)   # Admin (filtrlangan)
    dp.include_router(shop_router)    # Maskanchi
    dp.include_router(user_router)    # Oddiy foydalanuvchi

    # Schedulerni ishga tushirish
    setup_scheduler(bot)

    logging.info("Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())

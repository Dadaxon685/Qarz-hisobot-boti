"""
Qarz Tizimi — Asosiy bot fayli
Bot + FastAPI backend birgalikda ishga tushadi
"""
from create_db import create_all_tables
create_all_tables()

import asyncio
import logging
import os
import threading
import uvicorn
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

def run_api():
    """FastAPI ni alohida threadda ishga tushirish"""
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="warning")

async def main():
    # FastAPI ni background da ishga tushirish
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()
    logging.info(f"FastAPI ishga tushdi!")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(admin_router)
    dp.include_router(shop_router)
    dp.include_router(user_router)

    setup_scheduler(bot)

    logging.info("Bot ishga tushdi!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())

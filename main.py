import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# O'zingizning routerlaringizni import qiling
from handlers.admin import admin_router
from handlers.shop import shop_router
from handlers.user import user_router

# Bot sozlamalari
API_TOKEN = '8340168068:AAE126I8LCTcEcGfrAh9pqJ2c7cB4Ih7fJs'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- 1. AVTOMATIK ESLATMA FUNKSIYASI ---
async def send_daily_reminders():
    logging.info("Eslatmalar yuborish boshlandi...")
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Faqat customer_id (Telegram ID) si bor va statusi 'unpaid' bo'lganlarni olamiz
    cursor.execute("""
        SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.status = 'unpaid' AND d.customer_id IS NOT NULL
    """)
    records = cursor.fetchall()
    conn.close()

    for cid, name, amount, date, shop_name in records:
        try:
            text = (
                f"🔔 <b>QARZNI QAYTARISH HAQIDA ESLATMA</b>\n"
                f"────────────────────\n"
                f"Hurmatli <b>{name}</b>, sizning <b>{shop_name}</b> do'konidan "
                f"<b>{amount:,} so'm</b> miqdorida qarzingiz bor.\n\n"
                f"📅 To'lov muddati: <b>{date}</b>\n"
                f"────────────────────\n"
                f"<i>Iltimos, to'lovni o'z vaqtida amalga oshiring. 🙏</i>"
            )
            await bot.send_message(cid, text, parse_mode="HTML")
            await asyncio.sleep(0.05) # Telegram limitiga tushmaslik uchun (flood limit)
        except Exception as e:
            logging.error(f"Mijoz {cid} ga xabar yuborib bo'lmadi: {e}")

# --- 2. ASOSIY ISHGA TUSHIRISH (MAIN) ---
async def main():
    logging.basicConfig(level=logging.INFO)

    # Routerlarni ulash (TARTIB MUHIM!)
    dp.include_router(admin_router)
    dp.include_router(shop_router)
    dp.include_router(user_router)

    # SCHEDULER sozlash
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    
    # Har kuni ertalab soat 09:00 da ishga tushadi
    scheduler.add_job(send_daily_reminders, "cron", hour="9,12,16,20,22", minute=0)
    
    # Agar test qilmoqchi bo'lsangiz (har 1 minutda):
    # scheduler.add_job(send_daily_reminders, "interval", minutes=1)
    
    scheduler.start()

    print("Bot va Avtomatik eslatuvchi ishga tushdi...")

    await dp.start_polling(bot)
    await bot.send_message

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")

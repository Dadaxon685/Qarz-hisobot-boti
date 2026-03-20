import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Routerlarni import qilish
from handlers.admin import admin_router
from handlers.shop import shop_router
from handlers.user import user_router

# Bazani ulovchi va yaratuvchi funksiyalarni import qilish
from models import init_db
from handlers.connections import get_connection

# Bot sozlamalari
# Railway Variables bo'limiga BOT_TOKEN kalitini qo'shishni unutmang
API_TOKEN = os.getenv('BOT_TOKEN', '8340168068:AAE126I8LCTcEcGfrAh9pqJ2c7cB4Ih7fJs')
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- 1. AVTOMATIK ESLATMA FUNKSIYASI (PostgreSQL versiyasi) ---
async def send_daily_reminders():
    logging.info("Eslatmalar yuborish jarayoni boshlandi...")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # PostgreSQL so'rovi
        cursor.execute("""
            SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name 
            FROM debts d 
            JOIN shops s ON d.shop_id = s.id 
            WHERE d.status = 'unpaid' AND d.customer_id IS NOT NULL
        """)
        records = cursor.fetchall()
        
        for cid, name, amount, date, shop_name in records:
            try:
                text = (
                    f"🔔 <b>QARZNI QAYTARISH HAQIDA ESLATMA</b>\n"
                    f"────────────────────\n"
                    f"Hurmatli <b>{name}</b>, sizning <b>{shop_name}</b> Maskanidan "
                    f"<b>{amount:,.0f} so'm</b> miqdorida qarzingiz bor.\n\n"
                    f"📅 To'lov muddati: <b>{date}</b>\n"
                    f"────────────────────\n"
                    f"<i>Iltimos, to'lovni o'z vaqtida amalga oshiring. 🙏</i>"
                )
                await bot.send_message(cid, text, parse_mode="HTML")
                await asyncio.sleep(0.05) # Flood limitga tushmaslik uchun
            except Exception as e:
                logging.error(f"Xabar yuborishda xatolik (ID: {cid}): {e}")
                
    except Exception as db_err:
        logging.error(f"Eslatma yuborishda baza xatosi: {db_err}")
    finally:
        if conn:
            conn.close()

# --- 2. ASOSIY ISHGA TUSHIRISH (MAIN) ---
async def main():
    # Loglarni darajasini sozlash
    logging.basicConfig(level=logging.INFO)

    # A) BAZANI INICIALIZATSIYA QILISH
    print("Bazani tekshirish boshlandi...")
    try:
        init_db()  # models.py dagi jadvallarni yaratish funksiyasi
        print("PostgreSQL bazasi va jadvallar tayyor!")
    except Exception as e:
        print(f"DIQQAT! Baza yaratishda xatolik: {e}")
        # Baza ulanmasa botni ishlatish xavfli, shuning uchun to'xtatamiz
        return

    # B) ROUTERLARNI ULASH
    dp.include_router(admin_router)
    dp.include_router(shop_router)
    dp.include_router(user_router)

    # C) SCHEDULER (VAZIFALARNI REJALASHTIRUVCHI)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    # Har kuni belgilangan soatlarda eslatma yuboradi
    scheduler.add_job(send_daily_reminders, "cron", hour="9,12,16,20,22", minute=0)
    scheduler.start()

    print("Bot va Avtomatik eslatuvchi muvaffaqiyatli ishga tushdi!")

    # D) POLLINGNI BOSHLASH
    # Oldingi sessiyalarni tozalash (Conflict xatosini kamaytirish uchun)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot qo'lda to'xtatildi")

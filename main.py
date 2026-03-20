import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Routerlarni import qilish
from handlers.admin import admin_router
from handlers.shop import shop_router
from handlers.user import user_router

# Bazani ulovchi va yaratuvchi funksiyalarni import qilish
from models import init_db
from handlers.connections import get_connection

# Bot sozlamalari
# Tokenni Railway Variables-dan oladi, agar u yerda bo'lmasa pastdagini ishlatadi
API_TOKEN = os.getenv('BOT_TOKEN', '8340168068:AAGT-xeh4xm5bWx5rupMRN6KL-2JKrq6zEk')

# DefaultBotProperties orqali HTML parse mode-ni global sozlaymiz
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- 1. AVTOMATIK ESLATMA FUNKSIYASI ---
async def send_daily_reminders():
    logging.info("Eslatmalar yuborish jarayoni boshlandi...")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # PostgreSQL so'rovi - Maskan nomini olish uchun JOIN ishlatilgan
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
                await bot.send_message(cid, text)
                await asyncio.sleep(0.05) # Telegram flood limitdan qochish
            except Exception as e:
                logging.error(f"Xabar yuborishda xatolik (ID: {cid}): {e}")
                
    except Exception as db_err:
        logging.error(f"Eslatma yuborishda baza xatosi: {db_err}")
    finally:
        if conn:
            conn.close()

# --- 2. ASOSIY ISHGA TUSHIRISH (MAIN) ---
async def main():
    # Loglarni sozlash
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # A) BAZANI INICIALIZATSIYA QILISH
    logging.info("Bazani tekshirish boshlandi...")
    try:
        # models.py ichidagi init_db funksiyasi
        init_db()  
        logging.info("✅ PostgreSQL bazasi va jadvallar tayyor!")
    except Exception as e:
        logging.error(f"❌ DIQQAT! Baza yaratishda xatolik: {e}")
        # Baza bo'lmasa bot ishlamaydi, shuning uchun qaytamiz
        return

    # B) ROUTERLARNI ULASH
    dp.include_router(admin_router)
    dp.include_router(shop_router)
    dp.include_router(user_router)

    # C) SCHEDULER (VAZIFALARNI REJALASHTIRUVCHI)
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    # Har kuni belgilangan vaqtlarda eslatma yuborish
    scheduler.add_job(send_daily_reminders, "cron", hour="9,12,16,20,22", minute=0)
    scheduler.start()

    logging.info("🚀 Bot va Avtomatik eslatuvchi muvaffaqiyatli ishga tushdi!")

    # D) POLLINGNI BOSHLASH
    # Konflikt xatolarini oldini olish uchun webhookni tozalaymiz
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot qo'lda to'xtatildi")

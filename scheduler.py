"""
Kundalik avtomatik eslatmalar.
O'rnatish: pip install apscheduler
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from handlers.connections import get_connection

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

async def send_daily_reminders(bot: Bot):
    """Har kuni 09:00 — bugun/ertaga muddati tugaydigan qarzlar"""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    today_str = today.strftime("%d.%m.%Y")
    tomorrow_str = tomorrow.strftime("%d.%m.%Y")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.customer_id, d.amount, d.due_date, s.name
            FROM debts d JOIN shops s ON s.id = d.shop_id
            WHERE d.status = 'unpaid' AND d.customer_id IS NOT NULL
            AND (d.due_date = %s OR d.due_date = %s)
        """, (today_str, tomorrow_str))
        sent = 0
        for cid, amount, due_date, shop_name in cursor.fetchall():
            urgency = "🔴 <b>BUGUN</b>" if due_date == today_str else "🟡 <b>ERTAGA</b>"
            try:
                await bot.send_message(cid,
                    f"⏰ <b>QARZ ESLATMASI</b>\n\n{urgency} to'lov muddati!\n\n"
                    f"🏪 {shop_name}\n💰 {float(amount):,.0f} so'm\n📅 {due_date}\n\nIltimos, o'z vaqtida to'lang! 🙏",
                    parse_mode="HTML")
                sent += 1
            except: pass
        logging.info(f"Eslatmalar: {sent} ta yuborildi")
    finally:
        if conn: conn.close()

async def send_overdue_to_owners(bot: Bot):
    """Har kuni 18:00 — do'kon egalariga kechikkan qarzlar hisoboti"""
    today = datetime.now().date()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.customer_id, d.amount, d.due_date, s.name, s.owner_id
            FROM debts d JOIN shops s ON s.id = d.shop_id
            WHERE d.status = 'unpaid'
        """)
        overdue = {}
        for cid, amount, due_date, shop_name, owner_id in cursor.fetchall():
            try:
                db_date = datetime.strptime(due_date, "%d.%m.%Y").date()
                if db_date < today:
                    days = (today - db_date).days
                    if cid:
                        try:
                            await bot.send_message(cid,
                                f"🚨 <b>KECHIKKAN QARZ</b>\n\n🏪 {shop_name}\n"
                                f"💰 {float(amount):,.0f} so'm\n📅 {due_date}\n⚠️ {days} kun kechikdi",
                                parse_mode="HTML")
                        except: pass
                    if owner_id not in overdue:
                        overdue[owner_id] = {'count':0, 'total':0, 'shop':shop_name}
                    overdue[owner_id]['count'] += 1
                    overdue[owner_id]['total'] += float(amount)
            except: continue

        for owner_id, info in overdue.items():
            try:
                await bot.send_message(owner_id,
                    f"📊 <b>Kechikkan qarzlar</b>\n🏪 {info['shop']}\n"
                    f"👥 {info['count']} ta • 💰 {info['total']:,.0f} so'm",
                    parse_mode="HTML")
            except: pass
    finally:
        if conn: conn.close()

def setup_scheduler(bot: Bot):
    scheduler.add_job(send_daily_reminders, 'cron', hour=9, minute=0, args=[bot])
    scheduler.add_job(send_overdue_to_owners, 'cron', hour=18, minute=0, args=[bot])
    scheduler.start()
    logging.info("Scheduler ishga tushdi!")
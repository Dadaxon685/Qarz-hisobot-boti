"""
Kundalik eslatmalar — kuniga 3 marta: 08:00, 13:00, 19:00
"""
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from handlers.connections import get_connection

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")


async def send_reminders(bot: Bot, time_label: str):
    today = datetime.now().date()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # customer_id bor (telefon raqami saqlangan) va to'lanmagan qarzlar
        cursor.execute("""
            SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name
            FROM debts d
            JOIN shops s ON s.id = d.shop_id
            WHERE d.status = 'unpaid' AND d.customer_id IS NOT NULL
        """)
        rows = cursor.fetchall()

        # Mijoz bo'yicha guruhlash
        customers = {}
        for cid, name, amount, due_date, shop_name in rows:
            if cid not in customers:
                customers[cid] = {'name': name, 'debts': []}
            customers[cid]['debts'].append({
                'amount': float(amount),
                'due_date': due_date,
                'shop': shop_name
            })

        sent = 0
        for cid, info in customers.items():
            try:
                total = sum(d['amount'] for d in info['debts'])
                overdue_count = 0
                lines = ""

                for d in info['debts']:
                    is_late = False
                    try:
                        p = d['due_date'].split('.')
                        if len(p) == 3:
                            dd = datetime(int(p[2]), int(p[1]), int(p[0])).date()
                            is_late = dd < today
                            if is_late: overdue_count += 1
                    except: pass
                    tag = " 🔴 <b>KECHIKDI!</b>" if is_late else ""
                    lines += f"🏪 {d['shop']}\n💰 {d['amount']:,.0f} so'm | 📅 {d['due_date']}{tag}\n\n"

                if overdue_count:
                    header = f"🚨 <b>DIQQAT! {overdue_count} ta qarzingiz kechikdi!</b>"
                else:
                    header = "⏰ <b>Qarz eslatmasi</b>"

                text = (
                    f"{header}\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"{lines}"
                    f"💵 <b>Jami: {total:,.0f} so'm</b>\n\n"
                    f"Iltimos, o'z vaqtida to'lang! 🙏"
                )
                await bot.send_message(chat_id=cid, text=text, parse_mode="HTML")
                sent += 1
            except Exception as e:
                logging.warning(f"Eslatma yuborilmadi {cid}: {e}")

        logging.info(f"[{time_label}] Eslatmalar: {sent} ta")
    except Exception as e:
        logging.error(f"Scheduler xatosi: {e}")
    finally:
        if conn: conn.close()


def setup_scheduler(bot: Bot):
    scheduler.add_job(send_reminders, 'cron', hour=8,  minute=0,  args=[bot, "08:00"])
    scheduler.add_job(send_reminders, 'cron', hour=13, minute=0,  args=[bot, "13:00"])
    scheduler.add_job(send_reminders, 'cron', hour=19, minute=0,  args=[bot, "19:00"])
    scheduler.start()
    logging.info("Scheduler: 08:00, 13:00, 19:00")

"""
Eslatmalar tizimi:
- 09:00 — bugun muddati tugaydigan qarzlar
- 14:00 — ertaga muddati tugaydigan qarzlar  
- 19:00 — kechikkan qarzlar (do'kon egalariga ham hisobot)
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from handlers.connections import get_connection

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")


async def remind_today(bot: Bot):
    """09:00 — bugun muddati tugaydigan qarzlar"""
    today = datetime.now().strftime("%d.%m.%Y")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name, s.owner_id
            FROM debts d JOIN shops s ON s.id=d.shop_id
            WHERE d.status='unpaid' AND d.customer_id IS NOT NULL AND d.due_date=%s
        """, (today,))
        rows = cursor.fetchall()

        sent = 0
        notified_owners = {}
        for cid, cname, amount, due_date, shop_name, owner_id in rows:
            try:
                await bot.send_message(
                    chat_id=cid,
                    text=(
                        f"🔔 <b>BUGUN to'lov muddati!</b>\n\n"
                        f"🏪 <b>{shop_name}</b>\n"
                        f"💰 <b>{float(amount):,.0f} so'm</b>\n"
                        f"📅 Muddat: <b>{due_date}</b>\n\n"
                        f"Iltimos, bugun to'lang! 🙏"
                    ), parse_mode="HTML"
                )
                sent += 1
                if owner_id not in notified_owners:
                    notified_owners[owner_id] = []
                notified_owners[owner_id].append(f"• {cname}: {float(amount):,.0f} so'm")
            except: pass

        # Do'kon egalariga xabar
        for owner_id, items in notified_owners.items():
            try:
                await bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"📊 <b>Bugun to'lov muddati tugaydigan qarzlar:</b>\n\n"
                        + "\n".join(items)
                    ), parse_mode="HTML"
                )
            except: pass

        logging.info(f"[09:00] Bugungi eslatmalar: {sent} ta")
    except Exception as e:
        logging.error(f"remind_today xatosi: {e}")
    finally:
        if conn: conn.close()


async def remind_tomorrow(bot: Bot):
    """14:00 — ertaga muddati tugaydigan qarzlar"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name
            FROM debts d JOIN shops s ON s.id=d.shop_id
            WHERE d.status='unpaid' AND d.customer_id IS NOT NULL AND d.due_date=%s
        """, (tomorrow,))
        rows = cursor.fetchall()

        sent = 0
        for cid, cname, amount, due_date, shop_name in rows:
            try:
                await bot.send_message(
                    chat_id=cid,
                    text=(
                        f"⚠️ <b>ERTAGA to'lov muddati!</b>\n\n"
                        f"🏪 <b>{shop_name}</b>\n"
                        f"💰 <b>{float(amount):,.0f} so'm</b>\n"
                        f"📅 Muddat: <b>{due_date}</b>\n\n"
                        f"Ertaga to'lashni unutmang! ⏰"
                    ), parse_mode="HTML"
                )
                sent += 1
            except: pass

        logging.info(f"[14:00] Ertangi eslatmalar: {sent} ta")
    except Exception as e:
        logging.error(f"remind_tomorrow xatosi: {e}")
    finally:
        if conn: conn.close()


async def remind_overdue(bot: Bot):
    """19:00 — kechikkan qarzlar"""
    today = datetime.now().date()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name, s.owner_id
            FROM debts d JOIN shops s ON s.id=d.shop_id
            WHERE d.status='unpaid' AND d.due_date IS NOT NULL
        """)
        rows = cursor.fetchall()

        overdue_by_owner = {}
        customer_debts = {}

        for cid, cname, amount, due_date, shop_name, owner_id in rows:
            try:
                parts = due_date.split('.')
                if len(parts) != 3: continue
                dd = datetime(int(parts[2]), int(parts[1]), int(parts[0])).date()
                if dd >= today: continue
                days_late = (today - dd).days

                # Mijozga eslatma
                if cid:
                    if cid not in customer_debts:
                        customer_debts[cid] = []
                    customer_debts[cid].append({
                        'shop': shop_name, 'amount': float(amount),
                        'due_date': due_date, 'days': days_late
                    })

                # Egaga hisobot
                if owner_id not in overdue_by_owner:
                    overdue_by_owner[owner_id] = []
                overdue_by_owner[owner_id].append({
                    'name': cname, 'amount': float(amount), 'days': days_late
                })
            except: continue

        # Mijozlarga xabar
        sent = 0
        for cid, debts in customer_debts.items():
            try:
                total = sum(d['amount'] for d in debts)
                lines = ""
                for d in debts:
                    lines += f"🏪 {d['shop']}\n💰 {d['amount']:,.0f} so'm\n⏰ {d['days']} kun kechikdi\n\n"
                await bot.send_message(
                    chat_id=cid,
                    text=(
                        f"🚨 <b>KECHIKKAN QARZLAR!</b>\n\n"
                        f"{lines}"
                        f"💵 <b>Jami: {total:,.0f} so'm</b>\n\n"
                        f"Iltimos, imkon qadar tezroq to'lang!"
                    ), parse_mode="HTML"
                )
                sent += 1
            except: pass

        # Do'kon egalariga hisobot
        for owner_id, items in overdue_by_owner.items():
            try:
                total = sum(i['amount'] for i in items)
                lines = "\n".join([f"• {i['name']}: {i['amount']:,.0f} so'm ({i['days']} kun)" for i in items[:10]])
                await bot.send_message(
                    chat_id=owner_id,
                    text=(
                        f"📊 <b>Kechikkan qarzlar hisoboti:</b>\n\n"
                        f"{lines}\n\n"
                        f"💵 <b>Jami kechikkan: {total:,.0f} so'm</b>"
                    ), parse_mode="HTML"
                )
            except: pass

        logging.info(f"[19:00] Kechikkan eslatmalar: {sent} ta")
    except Exception as e:
        logging.error(f"remind_overdue xatosi: {e}")
    finally:
        if conn: conn.close()


def setup_scheduler(bot: Bot):
    scheduler.add_job(remind_today,    'cron', hour=9,  minute=0,  args=[bot])
    scheduler.add_job(remind_tomorrow, 'cron', hour=14, minute=0,  args=[bot])
    scheduler.add_job(remind_overdue,  'cron', hour=19, minute=0,  args=[bot])
    scheduler.start()
    logging.info("✅ Scheduler: 09:00, 14:00, 19:00")

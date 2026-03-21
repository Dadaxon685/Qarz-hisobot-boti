"""
Qarz Tizimi — Bot main threadda, FastAPI background threadda
"""
from create_db import create_all_tables
create_all_tables()

import asyncio
import logging
import os
import threading
import uvicorn
import random
import jwt
import hashlib

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from handlers.admin import admin_router
from handlers.shop import shop_router
from handlers.user import user_router
from scheduler import setup_scheduler
from handlers.connections import get_connection

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5148276461"))

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="Qarz Tizimi API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

security = HTTPBearer()
otp_store = {}

class OtpRequest(BaseModel):
    phone: str

class OtpVerify(BaseModel):
    phone: str
    code: str

class AdminLogin(BaseModel):
    telegram_id: int
    secret: str

class ShopCreate(BaseModel):
    name: str
    owner_id: int
    phone: str
    address: str

class DebtCreate(BaseModel):
    customer_phone: str
    customer_name: str
    amount: float
    due_date: str

class PaymentCreate(BaseModel):
    debt_id: int
    amount: float

def create_token(data):
    return jwt.encode(data, SECRET_KEY, algorithm="HS256")

def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        raise HTTPException(status_code=401, detail="Token yaroqsiz")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return decode_token(credentials.credentials)

def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Faqat admin uchun")
    return user

def require_shop(user=Depends(get_current_user)):
    if user.get("role") not in ("shop", "admin"):
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    return user

@app.get("/")
def root():
    return {"status": "Qarz Tizimi API ishlayapti!"}

@app.post("/auth/send-otp")
async def send_otp(req: OtpRequest):
    phone = req.phone.strip()
    if not phone.startswith('+'): phone = '+' + phone
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, owner_id FROM shops WHERE phone = %s", (phone,))
        shop = cursor.fetchone()
        if not shop:
            raise HTTPException(status_code=404, detail="Bu raqamda maskan topilmadi")
        shop_id, shop_name, owner_id = shop
    finally:
        conn.close()

    code = str(random.randint(100000, 999999))
    otp_store[phone] = {"code": code, "shop_id": shop_id, "shop_name": shop_name, "owner_id": owner_id}

    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=owner_id,
            text=f"🔐 <b>Kirish kodi</b>\n\nWeb panelga kirish:\n\n<code>{code}</code>\n\n⚠️ Kodni hech kimga bermang!",
            parse_mode="HTML"
        )
        await bot.session.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Xabar yuborishda xato: {e}")

    return {"message": "Kod yuborildi", "shop_name": shop_name}

@app.post("/auth/verify-otp")
def verify_otp(req: OtpVerify):
    phone = req.phone.strip()
    if not phone.startswith('+'): phone = '+' + phone
    data = otp_store.get(phone)
    if not data:
        raise HTTPException(status_code=400, detail="Avval kod so'rang")
    if data["code"] != req.code:
        raise HTTPException(status_code=400, detail="Kod noto'g'ri")
    del otp_store[phone]
    token = create_token({"role": "shop", "shop_id": data["shop_id"], "shop_name": data["shop_name"], "owner_id": data["owner_id"]})
    return {"token": token, "role": "shop", "shop_name": data["shop_name"]}

@app.post("/auth/telegram-login")
def telegram_login(data: dict):
    """Telegram Widget dan kelgan ma'lumotlar bilan kirish"""
    telegram_id = data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Telegram ID topilmadi")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (telegram_id,))
        shop = cursor.fetchone()
        if not shop:
            raise HTTPException(status_code=404, detail="Bu Telegram akkauntga bog'liq maskan topilmadi")
        shop_id, shop_name = shop
        token = create_token({"role": "shop", "shop_id": shop_id, "shop_name": shop_name, "owner_id": telegram_id})
        return {"token": token, "role": "shop", "shop_name": shop_name}
    finally:
        conn.close()

@app.post("/auth/admin-login")
def admin_login(req: AdminLogin):
    if req.telegram_id != SUPER_ADMIN_ID:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")
    expected = hashlib.sha256(f"{req.telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]
    if req.secret != expected:
        raise HTTPException(status_code=401, detail="Noto'g'ri kod")
    token = create_token({"telegram_id": req.telegram_id, "role": "admin"})
    return {"token": token, "role": "admin"}

@app.get("/admin/stats")
def admin_stats(user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM shops")
        shops = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debts WHERE status='unpaid'")
        d = cursor.fetchone()
        cursor.execute("SELECT COUNT(DISTINCT customer_phone) FROM debts")
        customers = cursor.fetchone()[0]
        return {"shops": shops, "debts_count": d[0], "total_debt": float(d[1]), "customers": customers}
    finally:
        conn.close()

@app.get("/admin/shops")
def admin_get_shops(user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.owner_id, s.phone, s.address,
                   COUNT(d.id), COALESCE(SUM(d.amount),0)
            FROM shops s LEFT JOIN debts d ON d.shop_id=s.id AND d.status='unpaid'
            GROUP BY s.id ORDER BY s.id DESC
        """)
        cols = ["id","name","owner_id","phone","address","debt_count","total_debt"]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]
    finally:
        conn.close()

@app.post("/admin/shops")
def admin_create_shop(data: ShopCreate, user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO shops (name,owner_id,phone,address) VALUES (%s,%s,%s,%s) RETURNING id",
                       (data.name, data.owner_id, data.phone, data.address))
        shop_id = cursor.fetchone()[0]
        conn.commit()
        return {"id": shop_id, "message": "Maskan qo'shildi"}
    finally:
        conn.close()

@app.delete("/admin/shops/{shop_id}")
def admin_delete_shop(shop_id: int, user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shops WHERE id=%s", (shop_id,))
        conn.commit()
        return {"message": "O'chirildi"}
    finally:
        conn.close()

class BroadcastRequest(BaseModel):
    text: str
    target: str = "all"  # all, shops, debtors

class SendMessageRequest(BaseModel):
    owner_id: int
    text: str

@app.post("/admin/broadcast")
async def admin_broadcast(data: BroadcastRequest, user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        user_ids = set()

        if data.target in ("all", "shops"):
            cursor.execute("SELECT owner_id FROM shops")
            for row in cursor.fetchall():
                user_ids.add(row[0])

        if data.target in ("all", "debtors"):
            cursor.execute("SELECT DISTINCT customer_id FROM debts WHERE customer_id IS NOT NULL AND status='unpaid'")
            for row in cursor.fetchall():
                user_ids.add(row[0])

        sent = 0
        bot = Bot(token=BOT_TOKEN)
        for uid in user_ids:
            try:
                await bot.send_message(chat_id=uid, text=f"📣 <b>XABAR</b>\n\n{data.text}", parse_mode="HTML")
                sent += 1
                import asyncio
                await asyncio.sleep(0.05)
            except: continue
        await bot.session.close()
        return {"sent": sent, "total": len(user_ids)}
    finally:
        conn.close()

@app.post("/admin/send-message")
async def admin_send_message(data: SendMessageRequest, user=Depends(require_admin)):
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=data.owner_id,
            text=f"📩 <b>Admin xabari:</b>\n\n{data.text}",
            parse_mode="HTML"
        )
        await bot.session.close()
        return {"message": "Yuborildi"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/debts")
def admin_all_debts(user=Depends(require_admin)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.id, d.customer_name, d.customer_phone, d.amount,
                   d.due_date, d.status, d.debt_date, s.name
            FROM debts d JOIN shops s ON s.id=d.shop_id
            ORDER BY d.debt_date DESC LIMIT 100
        """)
        cols = ["id","customer_name","customer_phone","amount","due_date","status","debt_date","shop_name"]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]
    finally:
        conn.close()

@app.get("/shop/stats")
def shop_stats(user=Depends(require_shop)):
    from datetime import datetime
    conn = get_connection()
    try:
        cursor = conn.cursor()
        shop_id = user["shop_id"]
        today = datetime.now().strftime("%d.%m.%Y")

        cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debts WHERE shop_id=%s AND status='unpaid'", (shop_id,))
        d = cursor.fetchone()

        # Muddati o'tgan — bugungi sanadan OLDIN yozilgan
        cursor.execute("SELECT id, due_date FROM debts WHERE shop_id=%s AND status='unpaid' AND due_date IS NOT NULL", (shop_id,))
        all_debts = cursor.fetchall()

        overdue_count = 0
        today_date = datetime.now().date()
        for _, due_date in all_debts:
            try:
                p = due_date.split('.')
                if len(p) == 3:
                    dd = datetime(int(p[2]), int(p[1]), int(p[0])).date()
                    if dd < today_date:
                        overdue_count += 1
            except: pass

        return {"debt_count": d[0], "total_debt": float(d[1]), "overdue_count": overdue_count}
    finally:
        conn.close()

@app.get("/shop/overdue")
def shop_overdue_debts(user=Depends(require_shop)):
    """Muddati o'tgan qarzlar — bugungi sanadan oldingi"""
    from datetime import datetime
    conn = get_connection()
    try:
        cursor = conn.cursor()
        shop_id = user["shop_id"]
        today_date = datetime.now().date()

        cursor.execute("""
            SELECT id, customer_name, customer_phone, amount, due_date, debt_date
            FROM debts WHERE shop_id=%s AND status='unpaid' AND due_date IS NOT NULL
        """, (shop_id,))
        rows = cursor.fetchall()

        overdue = []
        for row in rows:
            try:
                p = row[4].split('.')
                if len(p) == 3:
                    dd = datetime(int(p[2]), int(p[1]), int(p[0])).date()
                    if dd < today_date:
                        days_late = (today_date - dd).days
                        overdue.append({
                            "id": row[0],
                            "customer_name": row[1],
                            "customer_phone": row[2],
                            "amount": float(row[3]),
                            "due_date": row[4],
                            "debt_date": str(row[5]),
                            "days_late": days_late
                        })
            except: pass

        # Eng ko'p kechikkan birinchi
        overdue.sort(key=lambda x: x['days_late'], reverse=True)
        return overdue
    finally:
        conn.close()

@app.get("/shop/debts")
def shop_get_debts(user=Depends(require_shop)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id,customer_name,customer_phone,amount,due_date,status,debt_date FROM debts WHERE shop_id=%s ORDER BY debt_date DESC", (user["shop_id"],))
        cols = ["id","customer_name","customer_phone","amount","due_date","status","debt_date"]
        return [dict(zip(cols, r)) for r in cursor.fetchall()]
    finally:
        conn.close()

async def notify_customer(customer_id, text):
    if not customer_id: return
    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id=customer_id, text=text, parse_mode="HTML")
        await bot.session.close()
    except Exception as e:
        logging.warning(f"Xabar yuborilmadi {customer_id}: {e}")

@app.post("/shop/debts")
async def shop_create_debt(data: DebtCreate, user=Depends(require_shop)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        shop_id = user["shop_id"]
        shop_name = user["shop_name"]

        cursor.execute("SELECT customer_id FROM debts WHERE customer_phone=%s AND customer_id IS NOT NULL LIMIT 1", (data.customer_phone,))
        cid_row = cursor.fetchone()
        customer_id = cid_row[0] if cid_row else None

        cursor.execute("SELECT id,amount FROM debts WHERE shop_id=%s AND customer_phone=%s AND status='unpaid'", (shop_id, data.customer_phone))
        existing = cursor.fetchone()
        if existing:
            new_amount = float(existing[1]) + data.amount
            cursor.execute("UPDATE debts SET amount=%s, due_date=%s, debt_date=CURRENT_DATE WHERE id=%s", (new_amount, data.due_date, existing[0]))
            conn.commit()
            await notify_customer(customer_id,
                f"⚠️ <b>Qarzingiz yangilandi!</b>\n\n"
                f"🏪 <b>Maskan:</b> {shop_name}\n"
                f"💰 <b>Umumiy qarz:</b> {new_amount:,.0f} so'm\n"
                f"📅 <b>Muddat:</b> {data.due_date}\n\n"
                f"Iltimos, o'z vaqtida to'lang! 🙏"
            )
            return {"message": "Qarz yangilandi", "total": new_amount}

        cursor.execute("INSERT INTO debts (shop_id,customer_phone,customer_name,amount,due_date,status,debt_date) VALUES (%s,%s,%s,%s,%s,'unpaid',CURRENT_DATE) RETURNING id",
                       (shop_id, data.customer_phone, data.customer_name, data.amount, data.due_date))
        debt_id = cursor.fetchone()[0]
        conn.commit()
        await notify_customer(customer_id,
            f"💳 <b>Sizga yangi qarz yozildi!</b>\n\n"
            f"🏪 <b>Maskan:</b> {shop_name}\n"
            f"👤 <b>Ism:</b> {data.customer_name}\n"
            f"💰 <b>Summa:</b> {data.amount:,.0f} so'm\n"
            f"📅 <b>To'lov muddati:</b> {data.due_date}\n\n"
            f"⚠️ Muddatida to'lang!\n"
            f"📱 Qarzlaringizni ko'rish: /start"
        )
        return {"message": "Qarz saqlandi", "id": debt_id}
    finally:
        conn.close()

@app.post("/shop/payment")
async def shop_payment(data: PaymentCreate, user=Depends(require_shop)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, customer_id, customer_name FROM debts WHERE id=%s AND shop_id=%s", (data.debt_id, user["shop_id"]))
        res = cursor.fetchone()
        if not res:
            raise HTTPException(status_code=404, detail="Qarz topilmadi")
        current = float(res[0])
        customer_id = res[1]
        customer_name = res[2]
        if data.amount >= current:
            cursor.execute("DELETE FROM debts WHERE id=%s", (data.debt_id,))
            msg = "Qarz to'liq yopildi"
            await notify_customer(customer_id,
                f"✅ <b>Qarzingiz yopildi!</b>\n\n"
                f"🏪 <b>Maskan:</b> {user['shop_name']}\n"
                f"👤 <b>Ism:</b> {customer_name}\n"
                f"💰 <b>To'liq to'langan:</b> {current:,.0f} so'm\n\n"
                f"Rahmat! Endi qarzingiz yo'q 🎉"
            )
        else:
            new_amount = current - data.amount
            cursor.execute("UPDATE debts SET amount=%s WHERE id=%s", (new_amount, data.debt_id))
            msg = f"Qoldi: {new_amount:,.0f} so'm"
            await notify_customer(customer_id,
                f"💰 <b>To'lov qabul qilindi!</b>\n\n"
                f"🏪 <b>Maskan:</b> {user['shop_name']}\n"
                f"✅ <b>To'langan:</b> {data.amount:,.0f} so'm\n"
                f"📊 <b>Qolgan qarz:</b> {new_amount:,.0f} so'm\n\n"
                f"Rahmat! Qolgan qarzni ham o'z vaqtida to'lang 🙏"
            )
        conn.commit()
        return {"message": msg}
    finally:
        conn.close()

@app.delete("/shop/debts/{debt_id}")
def shop_delete_debt(debt_id: int, user=Depends(require_shop)):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM debts WHERE id=%s AND shop_id=%s", (debt_id, user["shop_id"]))
        conn.commit()
        return {"message": "O'chirildi"}
    finally:
        conn.close()


# ============================================================
# STARTUP: Bot ni FastAPI startup eventida ishga tushirish
# ============================================================

@app.on_event("startup")
async def startup_event():
    """FastAPI ishga tushganda botni ham ishga tushirish"""
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin_router)
    dp.include_router(shop_router)
    dp.include_router(user_router)
    setup_scheduler(bot)
    logging.info("Bot polling boshlandi!")
    # Background task sifatida ishga tushirish
    asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

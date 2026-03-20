"""
Qarz Tizimi - FastAPI Backend
O'rnatish: pip install fastapi uvicorn pg8000 python-jose passlib
Ishga tushirish: uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import pg8000
import os
import jwt
import hashlib

app = FastAPI(title="Qarz Tizimi API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5148276461"))

security = HTTPBearer()

# ============================================================
# DB ULANISH
# ============================================================

def get_db():
    conn = pg8000.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "qarz-tizimi"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    try:
        yield conn
    finally:
        conn.close()

# ============================================================
# JWT HELPERS
# ============================================================

def create_token(data: dict) -> str:
    return jwt.encode(data, SECRET_KEY, algorithm="HS256")

def decode_token(token: str) -> dict:
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

# ============================================================
# SCHEMAS
# ============================================================

class LoginRequest(BaseModel):
    telegram_id: int
    secret: str          # botdan yuborilgan maxfiy kod

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

class BroadcastRequest(BaseModel):
    text: str

# ============================================================
# AUTH
# ============================================================

@app.post("/auth/login")
def login(req: LoginRequest, db=Depends(get_db)):
    cursor = db.cursor()

    # Super admin tekshirish
    if req.telegram_id == SUPER_ADMIN_ID:
        expected = hashlib.sha256(f"{req.telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]
        if req.secret != expected:
            raise HTTPException(status_code=401, detail="Noto'g'ri parol")
        token = create_token({"telegram_id": req.telegram_id, "role": "admin"})
        return {"token": token, "role": "admin"}

    # Maskanchi tekshirish
    cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (req.telegram_id,))
    shop = cursor.fetchone()
    if not shop:
        raise HTTPException(status_code=404, detail="Maskan topilmadi")

    expected = hashlib.sha256(f"{req.telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]
    if req.secret != expected:
        raise HTTPException(status_code=401, detail="Noto'g'ri parol")

    token = create_token({"telegram_id": req.telegram_id, "role": "shop", "shop_id": shop[0], "shop_name": shop[1]})
    return {"token": token, "role": "shop", "shop_name": shop[1]}

@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user

# ============================================================
# ADMIN — MASKANLAR
# ============================================================

@app.get("/admin/shops")
def admin_get_shops(user=Depends(require_admin), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.id, s.name, s.owner_id, s.phone, s.address, s.created_at,
               COUNT(d.id) as debt_count,
               COALESCE(SUM(d.amount), 0) as total_debt
        FROM shops s
        LEFT JOIN debts d ON d.shop_id = s.id AND d.status = 'unpaid'
        GROUP BY s.id ORDER BY s.created_at DESC
    """)
    rows = cursor.fetchall()
    cols = ["id","name","owner_id","phone","address","created_at","debt_count","total_debt"]
    return [dict(zip(cols, r)) for r in rows]

@app.post("/admin/shops")
def admin_create_shop(data: ShopCreate, user=Depends(require_admin), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO shops (name, owner_id, phone, address) VALUES (%s, %s, %s, %s) RETURNING id",
        (data.name, data.owner_id, data.phone, data.address)
    )
    shop_id = cursor.fetchone()[0]
    db.commit()
    return {"id": shop_id, "message": "Maskan qo'shildi"}

@app.delete("/admin/shops/{shop_id}")
def admin_delete_shop(shop_id: int, user=Depends(require_admin), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM shops WHERE id = %s", (shop_id,))
    db.commit()
    return {"message": "O'chirildi"}

@app.get("/admin/stats")
def admin_stats(user=Depends(require_admin), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM shops")
    shops = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debts WHERE status='unpaid'")
    d = cursor.fetchone()
    cursor.execute("SELECT COUNT(DISTINCT customer_phone) FROM debts")
    customers = cursor.fetchone()[0]
    return {
        "shops": shops,
        "debts_count": d[0],
        "total_debt": float(d[1]),
        "customers": customers
    }

@app.get("/admin/debts")
def admin_all_debts(user=Depends(require_admin), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        SELECT d.id, d.customer_name, d.customer_phone, d.amount,
               d.due_date, d.status, d.debt_date, s.name as shop_name
        FROM debts d JOIN shops s ON s.id = d.shop_id
        ORDER BY d.debt_date DESC LIMIT 100
    """)
    cols = ["id","customer_name","customer_phone","amount","due_date","status","debt_date","shop_name"]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

# ============================================================
# SHOP — QARZLAR
# ============================================================

@app.get("/shop/debts")
def shop_get_debts(user=Depends(require_shop), db=Depends(get_db)):
    cursor = db.cursor()
    shop_id = user["shop_id"]
    cursor.execute("""
        SELECT id, customer_name, customer_phone, amount, due_date, status, debt_date
        FROM debts WHERE shop_id = %s ORDER BY debt_date DESC
    """, (shop_id,))
    cols = ["id","customer_name","customer_phone","amount","due_date","status","debt_date"]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]

@app.post("/shop/debts")
def shop_create_debt(data: DebtCreate, user=Depends(require_shop), db=Depends(get_db)):
    cursor = db.cursor()
    shop_id = user["shop_id"]

    cursor.execute("""
        SELECT id, amount FROM debts
        WHERE shop_id = %s AND customer_phone = %s AND status = 'unpaid'
    """, (shop_id, data.customer_phone))
    existing = cursor.fetchone()

    if existing:
        new_amount = existing[1] + data.amount
        cursor.execute("""
            UPDATE debts SET amount = %s, due_date = %s, debt_date = CURRENT_DATE
            WHERE id = %s
        """, (new_amount, data.due_date, existing[0]))
        db.commit()
        return {"message": "Qarz yangilandi", "total": new_amount}

    cursor.execute("""
        INSERT INTO debts (shop_id, customer_phone, customer_name, amount, due_date, status, debt_date)
        VALUES (%s, %s, %s, %s, %s, 'unpaid', CURRENT_DATE) RETURNING id
    """, (shop_id, data.customer_phone, data.customer_name, data.amount, data.due_date))
    debt_id = cursor.fetchone()[0]
    db.commit()
    return {"message": "Qarz saqlandi", "id": debt_id}

@app.post("/shop/payment")
def shop_payment(data: PaymentCreate, user=Depends(require_shop), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT amount FROM debts WHERE id = %s", (data.debt_id,))
    res = cursor.fetchone()
    if not res:
        raise HTTPException(status_code=404, detail="Qarz topilmadi")

    current = float(res[0])
    if data.amount >= current:
        cursor.execute("DELETE FROM debts WHERE id = %s", (data.debt_id,))
        msg = "Qarz to'liq yopildi"
    else:
        cursor.execute("UPDATE debts SET amount = %s WHERE id = %s", (current - data.amount, data.debt_id))
        msg = f"Qoldi: {current - data.amount:,.0f} so'm"

    db.commit()
    return {"message": msg}

@app.get("/shop/stats")
def shop_stats(user=Depends(require_shop), db=Depends(get_db)):
    cursor = db.cursor()
    shop_id = user["shop_id"]
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debts
        WHERE shop_id = %s AND status = 'unpaid'
    """, (shop_id,))
    d = cursor.fetchone()
    cursor.execute("""
        SELECT COUNT(*) FROM debts WHERE shop_id = %s
        AND status = 'unpaid'
        AND TO_DATE(due_date, 'DD.MM.YYYY') < CURRENT_DATE
    """, (shop_id,))
    overdue = cursor.fetchone()[0]
    return {
        "debt_count": d[0],
        "total_debt": float(d[1]),
        "overdue_count": overdue
    }

@app.delete("/shop/debts/{debt_id}")
def shop_delete_debt(debt_id: int, user=Depends(require_shop), db=Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM debts WHERE id = %s AND shop_id = %s", (debt_id, user["shop_id"]))
    db.commit()
    return {"message": "O'chirildi"}
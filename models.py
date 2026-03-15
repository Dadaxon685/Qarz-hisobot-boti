
import sqlite3


def init_db():
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Maskanlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        owner_id BIGINT UNIQUE,
        phone TEXT,
        address TEXT
    )''')
    
    # Qarzlar jadvali (Hamma ustunlar borligiga ishonch hosil qiling)
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER,
        customer_id BIGINT,        -- Telegramga xabar yuborish uchun shart
        customer_name TEXT,
        customer_phone TEXT,       -- Telefon raqam
        amount REAL,
        debt_date TEXT,
        due_date TEXT,
        status TEXT DEFAULT 'unpaid',
        FOREIGN KEY (shop_id) REFERENCES shops (id)
    )''')
    
    conn.commit()
    conn.close()
    print("Database yangilandi!")
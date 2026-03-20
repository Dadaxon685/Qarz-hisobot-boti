# models.py
from handlers.connections import get_connection

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Maskanlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
        id SERIAL PRIMARY KEY,
        name TEXT,
        owner_id BIGINT UNIQUE,
        phone TEXT,
        address TEXT
    )''')
    
    # 2. Qarzlar jadvali
    cursor.execute('''CREATE TABLE IF NOT EXISTS debts (
        id SERIAL PRIMARY KEY,
        shop_id INTEGER,
        customer_id BIGINT,
        customer_name TEXT,
        customer_phone TEXT,
        amount REAL,
        debt_date TEXT,
        due_date TEXT,
        status TEXT DEFAULT 'unpaid',
        CONSTRAINT fk_shop
            FOREIGN KEY (shop_id) 
            REFERENCES shops (id)
            ON DELETE CASCADE
    )''')
    
    conn.commit()
    cursor.close()
    conn.close()
    print("PostgreSQL jadvallari tayyor!")

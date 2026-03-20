
import os
import psycopg2

def get_connection():
    # Railway o'zgaruvchilarni avtomatik o'qiydi
    db_url = os.getenv('DATABASE_URL')
    return psycopg2.connect(db_url, sslmode='require')
    
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Do'konlar (shops) jadvali
    # PostgreSQL-da INTEGER PRIMARY KEY AUTOINCREMENT o'rniga SERIAL PRIMARY KEY ishlatiladi
    cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
        id SERIAL PRIMARY KEY,
        name TEXT,
        owner_id BIGINT UNIQUE,
        phone TEXT,
        address TEXT
    )''')
    
    # Qarzlar (debts) jadvali
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
    print("PostgreSQL bazasi muvaffaqiyatli tayyorlandi!")

if __name__ == "__main__":
    init_db()

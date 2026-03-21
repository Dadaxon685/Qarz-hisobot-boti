"""
PostgreSQL jadvallarini yaratish skripti.
"""
import os
import logging
from handlers.connections import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TABLES = [
    # 1. Maskanlar
    """
    CREATE TABLE IF NOT EXISTS shops (
        id         SERIAL PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        owner_id   BIGINT UNIQUE NOT NULL,
        phone      VARCHAR(20),
        address    TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # 2. Xodimlar — DO'KON XODIMLARI
    """
    CREATE TABLE IF NOT EXISTS employees (
        id          SERIAL PRIMARY KEY,
        shop_id     INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
        telegram_id BIGINT NOT NULL,
        full_name   VARCHAR(255),
        role        VARCHAR(20) DEFAULT 'staff',
        added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(shop_id, telegram_id)
    )
    """,
    # 3. Foydalanuvchilar
    """
    CREATE TABLE IF NOT EXISTS users (
        id          SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        full_name   VARCHAR(255),
        phone       VARCHAR(20),
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # 4. Qarzlar
    """
    CREATE TABLE IF NOT EXISTS debts (
        id             SERIAL PRIMARY KEY,
        shop_id        INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
        customer_id    BIGINT,
        customer_phone VARCHAR(20) NOT NULL,
        customer_name  VARCHAR(255) NOT NULL,
        amount         NUMERIC(15, 2) NOT NULL,
        due_date       VARCHAR(20),
        status         VARCHAR(10) DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'paid')),
        debt_date      DATE DEFAULT CURRENT_DATE,
        added_by       BIGINT,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_shops_owner_id       ON shops(owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_employees_shop_id    ON employees(shop_id)",
    "CREATE INDEX IF NOT EXISTS idx_employees_tg_id      ON employees(telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_debts_shop_id        ON debts(shop_id)",
    "CREATE INDEX IF NOT EXISTS idx_debts_customer_phone ON debts(customer_phone)",
    "CREATE INDEX IF NOT EXISTS idx_debts_customer_id    ON debts(customer_id)",
    "CREATE INDEX IF NOT EXISTS idx_users_phone          ON users(phone)",
]


def create_all_tables():
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        logging.info("Jadvallar yaratilmoqda...")
        for sql in TABLES:
            cursor.execute(sql)
            logging.info("✅ Jadval yaratildi (yoki allaqachon mavjud)")

        logging.info("Indexlar yaratilmoqda...")
        for sql in INDEXES:
            cursor.execute(sql)
            logging.info(f"✅ Index: {sql.split('idx_')[1].split(' ')[0]}")

        conn.commit()

        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name
        """)
        tables = cursor.fetchall()

        print("\n" + "="*40)
        print("✅ DATABASE MUVAFFAQIYATLI SOZLANDI!")
        print("="*40)
        for t in tables:
            print(f"   • {t[0]}")
        print("="*40 + "\n")

    except Exception as e:
        logging.error(f"❌ Xatolik yuz berdi: {e}")
        raise
    finally:
        if conn: conn.close()


if __name__ == "__main__":
    create_all_tables()

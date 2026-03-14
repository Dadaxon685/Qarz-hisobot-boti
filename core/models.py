import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # 1. Do'konlar jadvali
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id BIGINT UNIQUE,
            phone TEXT,
            address TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 2. Mijozlar jadvali
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER,
            full_name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
        )''')

        # 3. Qarzlar jadvali
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            amount DECIMAL(15, 2),
            description TEXT,
            deadline TIMESTAMP,
            is_paid BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
        )''')
        self.conn.commit()

    # --- SUPER ADMIN FUNKSIYALARI ---

    def add_shop(self, name, owner_id, phone, address):
        try:
            self.cursor.execute("INSERT INTO shops (name, owner_id, phone, address) VALUES (?, ?, ?, ?)",
                               (name, owner_id, phone, address))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_all_shops(self):
        self.cursor.execute("SELECT * FROM shops")
        return self.cursor.fetchall()

    def get_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM shops")
        shops_count = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT SUM(amount) FROM debts WHERE is_paid = 0")
        total_debt = self.cursor.fetchone()[0] or 0
        return shops_count, total_debt

    # --- DO'KONCHI FUNKSIYALARI ---

    def get_shop_by_owner(self, owner_id):
        self.cursor.execute("SELECT * FROM shops WHERE owner_id = ?", (owner_id,))
        return self.cursor.fetchone()

    def add_customer(self, shop_id, name, phone, address="Noma'lum"):
        self.cursor.execute("INSERT INTO customers (shop_id, full_name, phone, address) VALUES (?, ?, ?, ?)",
                           (shop_id, name, phone, address))
        self.conn.commit()
        return self.cursor.lastrowid

    def add_debt(self, customer_id, amount, description, days):
        deadline = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
        self.cursor.execute("INSERT INTO debts (customer_id, amount, description, deadline) VALUES (?, ?, ?, ?)",
                           (customer_id, amount, description, deadline))
        self.conn.commit()
        return deadline

    def get_shop_debts(self, shop_id):
        # Do'kondagi barcha qarzdorlarni va ularning umumiy qarzini olish
        query = """
        SELECT c.full_name, c.phone, SUM(d.amount), d.deadline 
        FROM customers c
        JOIN debts d ON c.id = d.customer_id
        WHERE c.shop_id = ? AND d.is_paid = 0
        GROUP BY c.id
        """
        self.cursor.execute(query, (shop_id,))
        return self.cursor.fetchall()

    # --- AVTOMATIK ESLATMA UCHUN ---

    def get_overdue_debts(self):
        # Muddati o'tgan qarzlarni topish
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        query = """
        SELECT c.full_name, c.phone, d.amount, s.name, s.address
        FROM debts d
        JOIN customers c ON d.customer_id = c.id
        JOIN shops s ON c.shop_id = s.id
        WHERE d.deadline < ? AND d.is_paid = 0
        """
        self.cursor.execute(query, (now,))
        return self.cursor.fetchall()

    def close(self):
        self.conn.close()
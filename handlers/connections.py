import os
import psycopg2

def get_connection():
    # Railway o'zgaruvchilardan DATABASE_URL ni oladi
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        # Agar Railway-da hali DATABASE_URL qo'shilmagan bo'lsa, xato beradi
        raise ValueError("Xatolik: DATABASE_URL o'zgaruvchisi topilmadi! Railway Variables bo'limini tekshiring.")
        
    return psycopg2.connect(db_url, sslmode='require')

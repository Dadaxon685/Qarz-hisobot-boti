import os
import psycopg2
from psycopg2.extras import DictCursor

def get_connection():
    """
    Railway'dagi PostgreSQL bazasiga ulanish hosil qiladi.
    DATABASE_URL o'zgaruvchisi Railway Variables bo'limida bo'lishi shart.
    """
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("Xatolik: DATABASE_URL topilmadi! Railway Variables-ni tekshiring.")
        
    # sslmode='require' tashqi server bilan xavfsiz bog'lanish uchun shart
    return psycopg2.connect(db_url, sslmode='require')

# Ma'lumotlarni lug'at (dict) ko'rinishida olish uchun yordamchi funksiya (ixtiyoriy)
def get_dict_cursor(conn):
    return conn.cursor(cursor_factory=DictCursor)

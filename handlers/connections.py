import os
import psycopg2

def get_connection():
    # Railway-dagi URL: postgresql://user:pass@host:port/dbname
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("DATABASE_URL topilmadi!")

    try:
        # URL "postgresql://" bilan boshlansa, uni psycopg2 tushunadigan 
        # formatga o'tkazishning eng xavfsiz yo'li - to'g'ridan-to'g'ri URLni uzatish
        # lekin ba'zi versiyalarda xato bermasligi uchun quyidagicha ulanamiz:
        return psycopg2.connect(db_url)
    except Exception as e:
        # Agar yuqoridagi ishlamasa, muqobil variant (aynan Railway uchun):
        print(f"Ulanishda xato: {e}")
        raise e

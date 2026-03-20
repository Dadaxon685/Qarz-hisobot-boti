import os
import psycopg2
from urllib.parse import urlparse

def get_connection():
    # Railway Variables bo'limidagi DATABASE_URL ni oladi
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("DATABASE_URL topilmadi! Railway-da Variables-ni tekshiring.")

    # URLni tahlil qilamiz
    result = urlparse(db_url)
    
    # Eng ishonchli ulanish usuli (parametrlar orqali)
    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode='require' # Railway tashqi ulanish uchun bu shart
    )

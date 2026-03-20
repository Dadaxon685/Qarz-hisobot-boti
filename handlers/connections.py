import os
import psycopg2
from urllib.parse import urlparse

def get_connection():
    # Railway-dagi DATABASE_URL o'zgaruvchisini olamiz
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("DATABASE_URL topilmadi!")

    # URLni tahlil qilamiz
    result = urlparse(db_url)
    
    # Har bir parametrni alohida uzatamiz
    return psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode='require'  # Tashqi ulanish uchun bu shart!
    )

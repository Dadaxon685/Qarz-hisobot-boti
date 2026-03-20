import os
import psycopg2
from urllib.parse import urlparse

def get_connection():
    # Railway o'zgaruvchisidan URLni olamiz
    db_url = os.getenv('DATABASE_URL')
    
    if not db_url:
        raise ValueError("DATABASE_URL topilmadi! Railway Variables-ni tekshiring.")

    # URLni tahlil qilamiz (postgresql://user:pass@host:port/dbname)
    result = urlparse(db_url)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port

    # Bo'laklangan ma'lumotlar orqali ulanamiz (eng ishonchli usul)
    return psycopg2.connect(
        database=database,
        user=username,
        password=password,
        host=hostname,
        port=port,
        sslmode='prefer' # Railway ichki tarmog'i uchun 'prefer' yoki 'require'
    )

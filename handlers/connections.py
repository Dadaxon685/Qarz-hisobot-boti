import os
import pg8000
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        from urllib.parse import urlparse
        r = urlparse(database_url)
        return pg8000.connect(
            host=r.hostname,
            port=r.port or 5432,
            database=r.path[1:],
            user=r.username,
            password=r.password,
        )

    return pg8000.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        database=os.getenv("DB_NAME", "qarz-tizimi"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
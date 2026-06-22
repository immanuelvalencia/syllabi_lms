import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("DATABASE_URL")
if url:
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE;")
            cur.execute("CREATE SCHEMA public;")
            cur.execute("GRANT ALL ON SCHEMA public TO postgres;")
            cur.execute("GRANT ALL ON SCHEMA public TO public;")
        conn.commit()
    print("Schema dropped and recreated.")
else:
    print("No DATABASE_URL found.")

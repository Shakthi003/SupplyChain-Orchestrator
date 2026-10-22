from dotenv import load_dotenv
import os
load_dotenv()

from sqlalchemy import create_engine, text

user = os.getenv('POSTGRES_USER')
password = os.getenv('POSTGRES_PASSWORD')
host = os.getenv('POSTGRES_HOST')
port = os.getenv('POSTGRES_PORT')
db = os.getenv('POSTGRES_DB')

url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_database(), version()"))
        db_name, ver = result.fetchone()
        print(f"Connected to DB : {db_name}")
        print(f"PostgreSQL ver  : {ver[:50]}")
        print("PostgreSQL via Python: OK")
except Exception as e:
    print(f"ERROR: {e}")

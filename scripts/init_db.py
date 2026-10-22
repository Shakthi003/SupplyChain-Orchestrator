"""
scripts/init_db.py — Create All Database Tables

What this does:
  Reads all the SQLAlchemy model classes from core/models.py
  and runs CREATE TABLE SQL for each one in PostgreSQL.

Why a separate script?
  We only run this ONCE (or when we want to reset the database).
  It's not part of the main application -- it's a setup tool.

How to run:
  uv run python scripts/init_db.py
"""

import sys
import os

# Add the project root to Python's path so we can import from core/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from core.config import DATABASE_URL
from core.models import Base


def init_db():
    print("=" * 55)
    print("  SupplyChain Orchestrator -- Database Initializer")
    print("=" * 55)

    print(f"\nConnecting to: {DATABASE_URL.split('@')[1]}")
    engine = create_engine(DATABASE_URL, echo=False)

    # Test the connection first
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.scalar()
            print(f"[OK] Connected to database: '{db_name}'")
    except Exception as e:
        print(f"[ERROR] Could not connect to PostgreSQL: {e}")
        print("   Make sure PostgreSQL is running and your .env is correct.")
        sys.exit(1)

    # Base.metadata.create_all() looks at ALL classes that inherit from Base
    # and runs CREATE TABLE IF NOT EXISTS for each one.
    # Safe to run multiple times -- won't delete existing data.
    print("\nCreating tables...")
    Base.metadata.create_all(engine)

    # Verify by listing all tables that now exist in the database
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print(f"\n[OK] {len(tables)} tables created successfully:\n")
    for table in sorted(tables):
        columns = inspector.get_columns(table)
        print(f"   {table:<35} ({len(columns)} columns)")

    print("\nDatabase is ready! You can now run the data generator.")
    print("   Next: uv run python scripts/generate_data.py")
    print("=" * 55)


if __name__ == "__main__":
    init_db()

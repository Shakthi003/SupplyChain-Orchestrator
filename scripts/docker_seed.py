"""
scripts/docker_seed.py -- first-start setup for the Docker stack. Safe to run on every start.

  1. create tables                      (idempotent)
  2. generate synthetic data + EVT-002  ONLY if the database has no suppliers yet
                                        (so a restart never wipes the audit log)
  3. build the document index           ONLY if chroma_db is empty
  4. (re)load the Neo4j graph           optional: failure is reported, not fatal
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from core.config import DATABASE_URL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args: str, optional: bool = False) -> bool:
    print(f"\n>>> {' '.join(args)}", flush=True)
    code = subprocess.run([sys.executable, *args], cwd=ROOT).returncode
    if code and not optional:
        sys.exit(code)
    return code == 0


def has_data() -> bool:
    with create_engine(DATABASE_URL).connect() as conn:
        return conn.execute(text("SELECT count(*) FROM suppliers")).scalar() > 0


def main() -> None:
    run("scripts/init_db.py")

    if has_data():
        print("\nDatabase already has data -- skipping data generation.")
    else:
        run("scripts/generate_data.py")
        run("scripts/add_scenario_2.py")

    chroma = os.path.join(ROOT, "chroma_db")
    if os.path.isdir(chroma) and os.listdir(chroma):
        print("\nDocument index already built -- skipping.")
    else:
        run("-m", "retrieval.embedder")

    if not run("scripts/load_graph.py", optional=True):
        print("\n[WARN] Neo4j graph not loaded. The app still works; the 'Impact chain' tab will say so.")


if __name__ == "__main__":
    main()

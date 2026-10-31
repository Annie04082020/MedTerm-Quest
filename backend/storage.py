from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from backend import config  # Load backend/.env before resolving database settings.

ROOT = Path(__file__).resolve().parent.parent

def db_path():
    return Path(os.environ.get('MEDTERM_DB_PATH', str(ROOT / 'data' / 'medterm.sqlite3')))

@contextmanager
def database():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


"""Backend-only .env settings. Explicit process environment takes precedence."""
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent

def load_backend_env(path=None):
    return load_dotenv(path or BACKEND_DIR / '.env', override=False, encoding='utf-8-sig')

load_backend_env()

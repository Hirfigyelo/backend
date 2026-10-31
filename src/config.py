from os import getenv
from pathlib import Path

DEBUG:bool = int(getenv("DEBUG_MODE", "0")) == 1

PROXIED = int(getenv("PROXIED", "0")) == 1

DATA_DIR = Path("/data/") if not DEBUG else Path(__file__).parent.parent / "data"
LOGS_DIR = DATA_DIR / "logs"

HOST: str = getenv("HOST", "127.0.0.1") if DEBUG else "0.0.0.0"
PORT: int = int(getenv("PORT", "8000")) if DEBUG else 8000

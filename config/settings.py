import os
from pathlib import Path
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/Santarem")
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DATA_DIR = Path.home() / ".businessvision"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "8"))
CONVITE_EXPIRACAO_HORAS = int(os.getenv("CONVITE_EXPIRACAO_HORAS", "72"))
RUN_DB_BOOTSTRAP = os.getenv("RUN_DB_BOOTSTRAP", "false").lower() == "true"

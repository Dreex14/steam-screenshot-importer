"""Rutas de datos de la aplicación, registro (logs) y copias de seguridad."""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "SteamScreenshotImporter"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
LOG_DIR = DATA_DIR / "logs"
BACKUP_DIR = DATA_DIR / "backups"
STAGING_DIR = DATA_DIR / "staging"
LEDGER_FILE = DATA_DIR / "imported.json"
JOURNAL_FILE = DATA_DIR / "journal.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
MAX_BACKUPS = 30

log = logging.getLogger("steamshot")


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if log.handlers:
        return
    log.setLevel(logging.DEBUG)
    fh = RotatingFileHandler(LOG_DIR / "steamshot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".steamshot-tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def backup_file(path: Path, tag: str) -> Path | None:
    """Copia ``path`` a la carpeta de copias de seguridad y devuelve la ruta de la copia."""
    if not path.exists():
        return None
    dest_dir = BACKUP_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}_{tag}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    shutil.copy2(path, dest)
    _prune_backups()
    return dest


def _prune_backups() -> None:
    dirs = sorted((d for d in BACKUP_DIR.iterdir() if d.is_dir()), key=lambda d: d.name)
    for d in dirs[:-MAX_BACKUPS]:
        shutil.rmtree(d, ignore_errors=True)


class Ledger:
    """Registro local de imágenes ya importadas (hash SHA-256 → archivo en Steam)."""

    def __init__(self):
        self.data: dict = read_json(LEDGER_FILE, {})

    def _key(self, account_id: int, appid: int) -> str:
        return f"{account_id}/{appid}"

    def find(self, account_id: int, appid: int, sha: str) -> str | None:
        return self.data.get(self._key(account_id, appid), {}).get(sha)

    def add(self, account_id: int, appid: int, sha: str, steam_file: str) -> None:
        self.data.setdefault(self._key(account_id, appid), {})[sha] = steam_file

    def remove(self, account_id: int, appid: int, sha: str) -> None:
        self.data.get(self._key(account_id, appid), {}).pop(sha, None)

    def save(self) -> None:
        write_json_atomic(LEDGER_FILE, self.data)

"""Detección de la instalación de Steam, cuentas, juegos y estado del cliente."""
from __future__ import annotations

import os
import subprocess
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

from . import vdf

STEAMID64_BASE = 76561197960265728
_CREATE_NO_WINDOW = 0x08000000


@dataclass
class SteamUser:
    account_id: int
    steamid64: int
    persona: str
    account_name: str

    @property
    def label(self) -> str:
        name = self.persona or self.account_name or "?"
        extra = f" ({self.account_name})" if self.account_name and self.account_name != name else ""
        return f"{name}{extra} · {self.account_id}"


def _reg(key: str, value: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, value)[0]
    except OSError:
        return None


def find_steam_path() -> Path | None:
    candidates = [_reg(r"Software\Valve\Steam", "SteamPath")]
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                candidates.append(winreg.QueryValueEx(k, "InstallPath")[0])
        except OSError:
            pass
    candidates.append(r"C:\Program Files (x86)\Steam")
    for c in candidates:
        if c and (Path(c) / "steam.exe").exists():
            return Path(os.path.normpath(c))
    return None


def active_account_id() -> int:
    """AccountID de la sesión abierta en el cliente (0 si no hay ninguna)."""
    v = _reg(r"Software\Valve\Steam\ActiveProcess", "ActiveUser")
    return int(v or 0)


def _running_images() -> set[str]:
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             creationflags=_CREATE_NO_WINDOW, timeout=15).stdout
    except Exception:
        return set()
    return {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line}


def is_steam_running() -> bool:
    imgs = _running_images()
    return "steam.exe" in imgs or "steamwebhelper.exe" in imgs


def shutdown_steam(steam_path: Path, timeout: float = 90, log=print) -> bool:
    """Cierre limpio mediante la opción oficial ``steam.exe -shutdown``."""
    if not is_steam_running():
        return True
    log("Cerrando Steam de forma ordenada (steam.exe -shutdown)…")
    subprocess.Popen([str(steam_path / "steam.exe"), "-shutdown"], creationflags=_CREATE_NO_WINDOW)
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(1.5)
        if not is_steam_running():
            time.sleep(2)  # margen para que termine de escribir sus archivos
            return True
    return False


def start_steam(steam_path: Path, extra_args: list[str] | None = None) -> None:
    subprocess.Popen([str(steam_path / "steam.exe"), *(extra_args or [])],
                     creationflags=0x00000008 | _CREATE_NO_WINDOW, close_fds=True)  # DETACHED_PROCESS


def open_url(url: str) -> None:
    os.startfile(url)  # noqa: S606 - abre steam:// con el cliente oficial


def list_users(steam_path: Path) -> list[SteamUser]:
    users: dict[int, SteamUser] = {}
    login = steam_path / "config" / "loginusers.vdf"
    if login.exists():
        try:
            data = vdf.load(login).get("users", {})
        except vdf.VDFError:
            data = {}
        for sid, info in data.items():
            if sid.isdigit():
                acc = int(sid) - STEAMID64_BASE
                users[acc] = SteamUser(acc, int(sid), info.get("PersonaName", ""), info.get("AccountName", ""))
    userdata = steam_path / "userdata"
    result = []
    if userdata.exists():
        for d in userdata.iterdir():
            if d.is_dir() and d.name.isdigit() and int(d.name) > 0:
                acc = int(d.name)
                result.append(users.get(acc) or SteamUser(acc, acc + STEAMID64_BASE, "", ""))
    active = active_account_id()
    result.sort(key=lambda u: (u.account_id != active, (u.persona or u.account_name).lower()))
    return result


def screenshots_root(steam_path: Path, account_id: int) -> Path:
    return steam_path / "userdata" / str(account_id) / "760"

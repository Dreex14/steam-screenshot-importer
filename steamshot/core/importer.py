"""Importación de imágenes a la biblioteca de capturas de Steam.

Método: el mismo que usan SteaScree/SnapSteam desde hace años, sin tocar el
cliente ni la red. Con Steam **cerrado** se copian las imágenes (JPEG) y sus
miniaturas a ``userdata/<cuenta>/760/remote/<appid>/screenshots`` y se registran
en ``screenshots.vdf``. Al abrir Steam, las capturas aparecen en el gestor oficial.

Seguridad:
* nunca se modifican ni borran los originales;
* nunca se sobrescribe un archivo existente de Steam;
* copia de seguridad de ``screenshots.vdf`` antes de cada cambio;
* escritura atómica + diario (journal) para deshacer una importación interrumpida.
"""
from __future__ import annotations

import shutil
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import images, steam, vdf
from ..i18n import tr
from .common import (JOURNAL_FILE, STAGING_DIR, Ledger, backup_file, log, read_json,
                     write_json_atomic, write_text_atomic)


class ImportError_(RuntimeError):
    pass


@dataclass
class ItemResult:
    source: Path
    status: str            # "imported" | "duplicate" | "error"
    steam_file: str = ""   # p. ej. "20261113120000_1.jpg"
    message: str = ""


@dataclass
class ImportReport:
    appid: int
    account_id: int
    items: list[ItemResult] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)

    @property
    def imported_files(self) -> list[str]:
        return [i.steam_file for i in self.items if i.status == "imported"]


def vdf_path(steam_path: Path, account_id: int) -> Path:
    return steam.screenshots_root(steam_path, account_id) / "screenshots.vdf"


def shots_dir(steam_path: Path, account_id: int, appid: int) -> Path:
    return steam.screenshots_root(steam_path, account_id) / "remote" / str(appid) / "screenshots"


def _load_vdf(path: Path) -> dict:
    if not path.exists():
        return {"screenshots": {}}
    data = vdf.load(path)
    if "screenshots" not in data or not isinstance(data["screenshots"], dict):
        raise ImportError_(tr("err_vdf_format", path=path))
    return data


def _unique_name(taken, used: set[str]) -> str:
    stamp = taken.strftime("%Y%m%d%H%M%S")
    n = 1
    while f"{stamp}_{n}.jpg".lower() in used:
        n += 1
    name = f"{stamp}_{n}.jpg"
    used.add(name.lower())
    return name


# --------------------------------------------------------------------------- recuperación
def pending_recovery() -> dict | None:
    j = read_json(JOURNAL_FILE, None)
    return j if j and not j.get("committed") else None


def recover(log_fn: Callable[[str], None] = print) -> bool:
    """Deshace una importación que quedó a medias (cierre inesperado, corte de luz...)."""
    j = read_json(JOURNAL_FILE, None)
    if not j:
        return False
    if not j.get("committed"):
        if steam.is_steam_running():
            raise ImportError_(tr("err_close_to_recover"))
        for f in j.get("created", []):
            try:
                Path(f).unlink()
                log_fn(tr("removed_file", name=Path(f).name))
            except FileNotFoundError:
                pass
        if j.get("backup") and Path(j["backup"]).exists() and j.get("vdf_touched"):
            shutil.copy2(j["backup"], j["vdf"])
            log_fn(tr("vdf_restored"))
    JOURNAL_FILE.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------- importación
def label_gameid(label: str) -> int:
    """ID estable de 64 bits para una etiqueta propia (juego que no es de Steam).

    Mismo formato que usa Steam para los accesos directos «no de Steam»:
    ``(appid32 << 32) | 0x02000000`` con el bit alto de appid32 activo.
    """
    appid32 = (zlib.crc32(("steamshot:" + label.strip().casefold()).encode("utf-8")) | 0x80000000) & 0xFFFFFFFF
    return (appid32 << 32) | 0x02000000


def is_shortcut_id(gameid: int) -> bool:
    return gameid >= 2**32


def import_images(steam_path: Path, account_id: int, appid: int, sources: list[Path],
                  label: str | None = None,
                  skip_duplicates: bool = True,
                  progress: Callable[[int, int, str], None] = lambda *a: None,
                  log_fn: Callable[[str], None] = print,
                  cancelled: Callable[[], bool] = lambda: False) -> ImportReport:
    report = ImportReport(appid, account_id)
    if not 0 < appid < 2**64:
        raise ImportError_(tr("err_bad_id"))
    if is_shortcut_id(appid) and not (label or "").strip():
        raise ImportError_(tr("err_need_name"))
    if steam.is_steam_running():
        raise ImportError_(tr("err_steam_open"))
    if pending_recovery():
        raise ImportError_(tr("err_pending"))
    if not (steam_path / "userdata" / str(account_id)).exists():
        raise ImportError_(tr("err_no_account", acc=account_id))

    vpath = vdf_path(steam_path, account_id)
    data = _load_vdf(vpath)  # valida antes de tocar nada
    shots = data["screenshots"]
    app_key = str(appid)
    entries = shots.get(app_key)
    if not isinstance(entries, dict):
        entries = {}

    dest_dir = shots_dir(steam_path, account_id, appid)
    thumb_dir = dest_dir / "thumbnails"
    used = {p.name.lower() for p in dest_dir.glob("*")} if dest_dir.exists() else set()
    used |= {Path(e.get("filename", "")).name.lower() for e in entries.values() if isinstance(e, dict)}
    next_idx = max((int(k) for k in entries if k.isdigit()), default=-1) + 1

    ledger = Ledger()
    seen: dict[str, Path] = {}
    created: list[str] = []
    backup = backup_file(vpath, f"cuenta{account_id}_app{appid}")
    journal = {"vdf": str(vpath), "backup": str(backup) if backup else "", "created": created,
               "vdf_touched": False, "committed": False, "started": time.time()}
    write_json_atomic(JOURNAL_FILE, journal)
    if backup:
        log_fn(tr("backup", path=backup))

    staging = STAGING_DIR / f"{int(time.time() * 1000)}"
    total = len(sources)
    try:
        for i, src in enumerate(sources, 1):
            if cancelled():
                log_fn(tr("cancelled"))
                break
            progress(i - 1, total, src.name)
            try:
                digest = images.sha256(src)
                if digest in seen:
                    report.items.append(ItemResult(src, "duplicate", message=tr("same_as", name=seen[digest].name)))
                    continue
                seen[digest] = src
                prev = ledger.find(account_id, appid, digest)
                if skip_duplicates and prev and (dest_dir / prev).exists():
                    report.items.append(ItemResult(src, "duplicate", prev, tr("already_imported")))
                    continue
                tmp_img, tmp_th = staging / f"{i}.jpg", staging / f"{i}_t.jpg"
                prep = images.prepare(src, tmp_img, tmp_th)
                name = _unique_name(prep.taken, used)
                dest_dir.mkdir(parents=True, exist_ok=True)
                thumb_dir.mkdir(parents=True, exist_ok=True)
                final, final_th = dest_dir / name, thumb_dir / name
                if final.exists() or final_th.exists():  # nunca sobrescribir
                    raise ImportError_(tr("err_exists", name=name))
                created += [str(final), str(final_th)]
                write_json_atomic(JOURNAL_FILE, journal)
                shutil.move(str(tmp_img), final)
                shutil.move(str(tmp_th), final_th)
                entries[str(next_idx)] = {
                    "type": "1",
                    "filename": f"{appid}/screenshots/{name}",
                    "thumbnail": f"{appid}/screenshots/thumbnails/{name}",
                    "vrfilename": "",
                    "imported": "0",
                    "width": str(prep.width),
                    "height": str(prep.height),
                    "gameid": str(appid),
                    "creation": str(int(prep.taken.timestamp())),
                    "caption": "",
                    "Permissions": "",
                    "hscreenshot": "",
                }
                next_idx += 1
                ledger.add(account_id, appid, digest, name)
                notes = []
                if prep.resized:
                    notes.append(tr("resized", w=prep.width, h=prep.height))
                notes.append(tr("converted") if prep.reencoded else tr("copied"))
                report.items.append(ItemResult(src, "imported", name, ", ".join(notes)))
            except Exception as e:  # noqa: BLE001 - un archivo malo no detiene el lote
                log.exception("Error con %s", src)
                from PIL import UnidentifiedImageError
                msg = tr("not_image") if isinstance(e, UnidentifiedImageError) else str(e)
                report.items.append(ItemResult(src, "error", message=msg))

        if report.count("imported"):
            shots[app_key] = entries
            if is_shortcut_id(appid):
                names = shots.get("shortcutnames")
                if not isinstance(names, dict):
                    names = {}
                names[app_key] = label.strip()
                shots["shortcutnames"] = names
            if "shortcutnames" in shots:  # mantener 'shortcutnames' al final, como Steam
                shots["shortcutnames"] = shots.pop("shortcutnames")
            text = vdf.dumps(data)
            vdf.loads(text)  # verificación de integridad antes de escribir
            if steam.is_steam_running():
                raise ImportError_(tr("err_steam_started"))
            journal["vdf_touched"] = True
            write_json_atomic(JOURNAL_FILE, journal)
            vpath.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(vpath, text)
            check = _load_vdf(vpath)["screenshots"].get(app_key, {})
            if len(check) != len(entries):
                raise ImportError_(tr("err_verify"))
        journal["committed"] = True
        write_json_atomic(JOURNAL_FILE, journal)
        ledger.save()
        JOURNAL_FILE.unlink(missing_ok=True)
        progress(total, total, "")
        return report
    except BaseException:
        log_fn(tr("undoing"))
        recover(log_fn)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------- verificación
def known_labels(steam_path: Path, account_id: int) -> dict[int, str]:
    """Etiquetas (juegos que no son de Steam) que ya tienen capturas en esta cuenta."""
    try:
        names = _load_vdf(vdf_path(steam_path, account_id))["screenshots"].get("shortcutnames") or {}
    except (OSError, vdf.VDFError, ImportError_):
        return {}
    return {int(k): v for k, v in names.items() if k.isdigit() and isinstance(v, str)}


def publication_status(steam_path: Path, account_id: int, appid: int, files: list[str]) -> dict[str, str]:
    """Devuelve {archivo: publishedfileid} leyendo lo que Steam guardó en screenshots.vdf.

    Un ``publishedfileid`` distinto de 0 es la prueba de que Steam subió la captura.
    Steam guarda este archivo al cerrarse (y a veces antes), así que puede tardar.
    """
    data = _load_vdf(vdf_path(steam_path, account_id))
    wanted = {f.lower() for f in files}
    out: dict[str, str] = {}
    for e in (data["screenshots"].get(str(appid)) or {}).values():
        if isinstance(e, dict):
            name = Path(e.get("filename", "")).name
            if name.lower() in wanted:
                pid = e.get("publishedfileid", "")
                out[name] = pid if pid not in ("", "0") else ""
    return out

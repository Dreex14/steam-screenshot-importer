"""Detección, conversión y miniaturas de imágenes. Nunca modifica los originales."""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps, features

Image.MAX_IMAGE_PIXELS = 400_000_000  # permitir fotos grandes (se reducen después)

# Límites que aplica la nube de Steam (los mismos que usa SteaScree).
STEAM_MAX_SIDE = 16000
STEAM_MAX_PIXELS = 26_210_175
THUMB_WIDTH = 200  # k_ScreenshotThumbWidth (Steamworks)
JPEG_QUALITY = 95

_WANTED = [".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".tga"]
if features.check("avif"):
    _WANTED.append(".avif")
SUPPORTED_EXTS = tuple(e for e in _WANTED if e in Image.registered_extensions())


@dataclass
class Prepared:
    path: Path          # JPEG listo para Steam
    thumb: Path         # miniatura de 200 px de ancho
    width: int
    height: int
    reencoded: bool
    resized: bool
    taken: datetime


def scan_folder(folder: Path, recursive: bool = False) -> list[Path]:
    it = folder.rglob("*") if recursive else folder.iterdir()
    files = [p for p in it if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
    return sorted(files, key=lambda p: str(p).lower())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fit_steam_limits(w: int, h: int) -> tuple[int, int]:
    scale = min(1.0, STEAM_MAX_SIDE / w, STEAM_MAX_SIDE / h, (STEAM_MAX_PIXELS / (w * h)) ** 0.5)
    if scale >= 1.0:
        return w, h
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    while nw * nh > STEAM_MAX_PIXELS:
        nw, nh = nw - 1, max(1, int((nw - 1) * h / w))
    return nw, nh


def _taken_time(img: Image.Image, src: Path) -> datetime:
    try:
        exif = img.getexif()
        raw = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)  # DateTimeOriginal / DateTime
        if raw:
            return datetime.strptime(str(raw).strip("\x00")[:19], "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return datetime.fromtimestamp(src.stat().st_mtime)


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def prepare(src: Path, dest: Path, thumb: Path, quality: int = JPEG_QUALITY) -> Prepared:
    """Genera en ``dest`` un JPEG apto para Steam y su miniatura en ``thumb``.

    Si el original ya es un JPEG compatible (RGB baseline, sin EXIF y dentro de los
    límites) se copia byte a byte para no perder calidad; si no, se recodifica a
    JPEG calidad 95 sin submuestreo de color.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im.seek(0)
        taken = _taken_time(im, src)
        orientation = im.getexif().get(0x0112, 1) if "exif" in im.info else 1
        w0, h0 = im.size
        if orientation in (5, 6, 7, 8):
            w0, h0 = h0, w0
        w, h = fit_steam_limits(w0, h0)
        resized = (w, h) != (w0, h0)
        # Sin EXIF: además de evitar rotaciones, no se publican GPS ni datos de cámara.
        raw_ok = (im.format == "JPEG" and im.mode == "RGB" and "exif" not in im.info
                  and not resized and not im.info.get("progressive"))
        icc = im.info.get("icc_profile")
        if raw_ok:
            shutil.copyfile(src, dest)
            img = _to_rgb(im)
        else:
            img = _to_rgb(ImageOps.exif_transpose(im))
            if resized:
                img = img.resize((w, h), Image.LANCZOS)
            img.save(dest, "JPEG", quality=quality, subsampling=0, optimize=True, icc_profile=icc)
        th = max(1, THUMB_WIDTH * h // w)  # igual que Steam: 2560x1440 -> 200x112
        img.resize((THUMB_WIDTH, th), Image.LANCZOS).save(thumb, "JPEG", quality=90)
    return Prepared(dest, thumb, w, h, not raw_ok, resized, taken)

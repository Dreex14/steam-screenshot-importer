"""Paso de publicación.

No existe ninguna API oficial para publicar capturas en el perfil (Steamworks solo
permite añadirlas a la biblioteca local y la Web API no tiene ese método). Para no
arriesgar la cuenta, la subida la hace siempre el cliente oficial de Steam:
la aplicación abre el gestor de capturas directamente en el juego elegido
(``steam://open/screenshots/<appid>``, el mismo enlace que usa el propio cliente)
y el usuario solo tiene que seleccionar las capturas nuevas y pulsar «Subir».

Después se comprueba de verdad la publicación leyendo ``publishedfileid`` en
``screenshots.vdf``, que es donde Steam anota el identificador de la captura subida.
"""
from __future__ import annotations

from pathlib import Path

from . import importer, steam

PROFILE_URL = "https://steamcommunity.com/profiles/{sid}/screenshots/?sort=newestfirst&browsefilter=myfiles&view=grid"


def open_screenshot_manager(appid: int) -> None:
    """Abre (o arranca) Steam en el gestor de capturas del juego indicado."""
    steam.open_url(f"steam://open/screenshots/{int(appid)}")


def open_profile_screenshots(steamid64: int) -> None:
    steam.open_url(PROFILE_URL.format(sid=steamid64))


def check(steam_path: Path, account_id: int, appid: int, files: list[str]) -> tuple[list[str], list[str]]:
    """Devuelve (publicadas, pendientes) según lo guardado por Steam."""
    status = importer.publication_status(steam_path, account_id, appid, files)
    published = [f for f in files if status.get(f)]
    pending = [f for f in files if not status.get(f)]
    return published, pending

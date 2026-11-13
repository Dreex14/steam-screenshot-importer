"""Traducciones (español / inglés).

El idioma se elige al arrancar según la distribución de teclado activa: si es
española (cualquier variante, incluida la latinoamericana) se usa español; en
cualquier otro caso, inglés.
"""
from __future__ import annotations

import ctypes
import sys

LANG = "en"

_T: dict[str, tuple[str, str]] = {
    # --- cabecera y galería
    "account": ("Cuenta:", "Account:"),
    "refresh_tip": ("Volver a detectar Steam y las cuentas", "Detect Steam and accounts again"),
    "pick_folder": ("📁  Elegir carpeta…", "📁  Choose folder…"),
    "no_folder": ("Ninguna carpeta seleccionada", "No folder selected"),
    "subfolders": ("Incluir subcarpetas", "Include subfolders"),
    "select_all": ("Seleccionar todo", "Select all"),
    "select_none": ("Ninguna", "None"),
    "n_selected": ("{n} de {total} seleccionadas", "{n} of {total} selected"),
    "folder_dialog": ("Carpeta con imágenes", "Folder with images"),
    "steam_open": ("Steam abierto", "Steam running"),
    "steam_closed": ("Steam cerrado", "Steam closed"),
    "steam_missing": ("⚠ Steam no encontrado", "⚠ Steam not found"),
    "steam_missing_log": ("No se encontró la instalación de Steam.", "Steam installation not found."),
    "active_session": ("  ● sesión activa", "  ● signed in"),
    # --- juego
    "game_title": ("<b>Juego</b> — nombre con el que aparecerá en tu perfil:",
                   "<b>Game</b> — name shown on your profile:"),
    "game_placeholder": ("p. ej. The Legend of Zelda: Tears of the Kingdom",
                         "e.g. The Legend of Zelda: Tears of the Kingdom"),
    "game_hint": ("Para capturas de Switch, PS5, otras consolas o emuladores. Steam las publica como "
                  "«juego que no es de Steam» con este nombre. Usa siempre el mismo nombre para "
                  "agrupar las capturas de un juego; los ya usados salen en el desplegable.",
                  "For screenshots from Switch, PS5, other consoles or emulators. Steam publishes them as "
                  "a “non-Steam game” with this name. Always use the same name to keep a game's "
                  "screenshots together; names you have used appear in the drop-down list."),
    # --- acción y progreso
    "go": ("Importar y publicar", "Import and publish"),
    "go_n": ("Importar y publicar {n} imágenes", "Import and publish {n} images"),
    "go_1": ("Importar y publicar 1 imagen", "Import and publish 1 image"),
    "importing": ("Importando…", "Importing…"),
    "ready": ("Listo", "Ready"),
    "log_title": ("Registro:", "Log:"),
    "n_found": ("{n} imágenes compatibles en {folder}", "{n} supported images in {folder}"),
    "read_folder_error": ("No se pudo leer la carpeta: {e}", "Could not read the folder: {e}"),
    "close_title": ("Hay que cerrar Steam", "Steam needs to close"),
    "close_body": ("Para añadir las capturas sin riesgo de corromper la biblioteca, Steam debe estar cerrado.\n\n"
                   "La aplicación lo cerrará de forma ordenada y lo volverá a abrir en el gestor de capturas.",
                   "Steam must be closed to add the screenshots without risking your library.\n\n"
                   "The app will close it cleanly and reopen it in the screenshot manager."),
    "other_account": ("\n\n⚠ La sesión abierta ahora en Steam es de otra cuenta. Para publicar tendrás que "
                      "iniciar sesión con la cuenta elegida.",
                      "\n\n⚠ Steam is currently signed in with a different account. To publish, sign in "
                      "with the selected account."),
    "importing_log": ("Importando {n} imágenes en «{game}» (cuenta {acc})…",
                      "Importing {n} images into “{game}” (account {acc})…"),
    "closing_steam": ("Cerrando Steam de forma ordenada…", "Closing Steam cleanly…"),
    "steam_closed_log": ("Steam cerrado.", "Steam closed."),
    "steam_timeout": ("Steam no se cerró a tiempo. Ciérralo manualmente y reintenta.",
                      "Steam did not close in time. Close it manually and try again."),
    "error": ("Error", "Error"),
    "error_log": ("Error: {msg}", "Error: {msg}"),
    "import_failed": ("No se pudo importar", "Import failed"),
    "item_ok": ("✔ {src} → {dst} ({msg})", "✔ {src} → {dst} ({msg})"),
    "item_dup": ("• {src}: omitida, duplicada ({msg})", "• {src}: skipped, duplicate ({msg})"),
    "item_err": ("✖ {src}: {msg}", "✖ {src}: {msg}"),
    "summary": ("Importadas {ok} · duplicadas {dup} · errores {err}",
                "Imported {ok} · duplicates {dup} · errors {err}"),
    "opening_manager": ("Steam se está abriendo en el gestor de capturas de este juego.",
                        "Steam is opening in this game's screenshot manager."),
    # --- publicación
    "pub_title": ("<b>Súbelas desde Steam</b>", "<b>Upload them from Steam</b>"),
    "hide": ("Ocultar", "Hide"),
    "hide_tip": ("Ocultar este aviso", "Hide this notice"),
    "open_manager": ("Abrir gestor de capturas", "Open screenshot manager"),
    "open_profile": ("Ver en mi perfil", "View on my profile"),
    "pub_pending": ("Las capturas ya están en Steam. En el gestor de capturas de «{game}» selecciona las "
                    "{n} nuevas (Ctrl+clic o Mayús+clic), elige la visibilidad y pulsa <b>Subir</b>."
                    "<br><br>Subidas a tu perfil: <b>{done} de {total}</b> "
                    "<span style='color:#8b949e'>(se comprueba automáticamente)</span>",
                    "The screenshots are now in Steam. In the screenshot manager for “{game}”, select the "
                    "{n} new ones (Ctrl+click or Shift+click), choose the visibility and press <b>Upload</b>."
                    "<br><br>Uploaded to your profile: <b>{done} of {total}</b> "
                    "<span style='color:#8b949e'>(checked automatically)</span>"),
    "pub_done": ("<b style='color:#3fb950'>✔ Las {total} capturas están publicadas en Steam</b> (comprobado).",
                 "<b style='color:#3fb950'>✔ All {total} screenshots are published on Steam</b> (verified)."),
    "pub_progress": ("Steam confirma {done} de {total} capturas publicadas.",
                     "Steam confirms {done} of {total} screenshots published."),
    # --- recuperación
    "recover_title": ("Importación interrumpida", "Interrupted import"),
    "recover_body": ("La última importación no terminó correctamente.\n"
                     "¿Deshacer sus cambios y restaurar screenshots.vdf desde la copia de seguridad?",
                     "The last import did not finish correctly.\n"
                     "Undo its changes and restore screenshots.vdf from the backup?"),
    "recover_ok": ("Recuperación completada.", "Recovery completed."),
    "recover_fail": ("No se pudo recuperar: {e}", "Could not recover: {e}"),
    # --- núcleo (importer)
    "err_bad_id": ("ID de juego no válido.", "Invalid game ID."),
    "err_need_name": ("Las capturas de juegos que no son de Steam necesitan un nombre.",
                      "Screenshots of non-Steam games need a name."),
    "err_steam_open": ("Steam está abierto. Debe cerrarse para modificar la biblioteca de capturas de forma segura.",
                       "Steam is running. It must be closed to safely change the screenshot library."),
    "err_pending": ("Hay una importación anterior interrumpida. Recupérala antes de continuar.",
                    "A previous import was interrupted. Recover it before continuing."),
    "err_no_account": ("No existe la carpeta de la cuenta {acc}.", "The folder for account {acc} does not exist."),
    "err_vdf_format": ("Formato inesperado en {path}; no se modifica.", "Unexpected format in {path}; not modified."),
    "err_exists": ("{name} ya existe", "{name} already exists"),
    "err_steam_started": ("Steam se abrió durante la importación; se deshacen los cambios.",
                          "Steam started during the import; changes are being undone."),
    "err_verify": ("La verificación de screenshots.vdf no coincide.", "screenshots.vdf verification failed."),
    "err_close_to_recover": ("Cierra Steam antes de recuperar la importación interrumpida.",
                             "Close Steam before recovering the interrupted import."),
    "backup": ("Copia de seguridad: {path}", "Backup: {path}"),
    "cancelled": ("Cancelado por el usuario.", "Cancelled by the user."),
    "same_as": ("Igual que {name}", "Same as {name}"),
    "already_imported": ("Ya importada antes", "Already imported"),
    "resized": ("reducida a {w}x{h}", "resized to {w}x{h}"),
    "converted": ("convertida a JPEG", "converted to JPEG"),
    "copied": ("copiada sin recomprimir", "copied without recompression"),
    "undoing": ("Error: deshaciendo los cambios de esta importación…", "Error: undoing this import's changes…"),
    "removed_file": ("Eliminado archivo de la importación interrumpida: {name}",
                     "Removed file from the interrupted import: {name}"),
    "vdf_unclosed": ("screenshots.vdf dañado: texto sin cerrar.", "Damaged screenshots.vdf: unclosed string."),
    "vdf_brace_key": ("screenshots.vdf dañado: bloque sin nombre.", "Damaged screenshots.vdf: block without a name."),
    "vdf_brace_open": ("screenshots.vdf dañado: llave de cierre sobrante.", "Damaged screenshots.vdf: extra closing brace."),
    "vdf_incomplete": ("screenshots.vdf dañado: estructura incompleta.", "Damaged screenshots.vdf: incomplete structure."),
    "not_image": ("no es una imagen válida o está dañada", "not a valid image or the file is damaged"),
    "vdf_restored": ("screenshots.vdf restaurado desde la copia de seguridad.", "screenshots.vdf restored from backup."),
}


def detect_language() -> str:
    """'es' si la distribución de teclado activa es española; si no, 'en'."""
    if sys.platform == "win32":
        try:
            hkl = ctypes.windll.user32.GetKeyboardLayout(0)
            return "es" if (hkl & 0x3FF) == 0x0A else "en"  # LANG_SPANISH
        except Exception:
            pass
    import locale
    loc = (locale.getlocale()[0] or "").lower()
    return "es" if loc.startswith(("es", "spanish")) else "en"


def set_language(lang: str) -> None:
    global LANG
    LANG = "es" if lang == "es" else "en"


def tr(key: str, **kw) -> str:
    es, en = _T[key]
    text = es if LANG == "es" else en
    return text.format(**kw) if kw else text

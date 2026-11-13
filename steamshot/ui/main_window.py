"""Ventana principal (PySide6)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThread, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from ..core import images, importer, publish, steam
from ..core.common import SETTINGS_FILE, log, read_json, write_json_atomic
from .. import i18n
from ..i18n import tr

THUMB = 150


# --------------------------------------------------------------------------- miniaturas en segundo plano
class _ThumbSignals(QObject):
    done = Signal(str, QPixmap)


class _ThumbTask(QRunnable):
    def __init__(self, path: str, signals: _ThumbSignals, generation: int, owner):
        super().__init__()
        self.path, self.signals, self.generation, self.owner = path, signals, generation, owner

    def run(self):
        if self.generation != self.owner.generation:
            return
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            size.scale(THUMB * 2, THUMB * 2, Qt.KeepAspectRatio)
            reader.setScaledSize(size)
        img = reader.read()
        if img.isNull():  # formatos que Qt no lee (p. ej. TGA, AVIF): usar Pillow
            try:
                from PIL import Image
                from PIL.ImageQt import ImageQt
                with Image.open(self.path) as im:
                    im.thumbnail((THUMB * 2, THUMB * 2))
                    img = ImageQt(im.convert("RGBA")).copy()
            except Exception:
                return
        if self.generation == self.owner.generation:
            self.signals.done.emit(self.path, QPixmap.fromImage(img))


# --------------------------------------------------------------------------- trabajo pesado en un hilo
class ImportWorker(QThread):
    progress = Signal(int, int, str)
    message = Signal(str, str)        # texto, nivel
    finished_ok = Signal(object)      # ImportReport
    failed = Signal(str)

    def __init__(self, steam_path: Path, account_id: int, gameid: int, label: str | None,
                 files: list[Path], close_steam: bool):
        super().__init__()
        self.args = (steam_path, account_id, gameid, label, files, close_steam)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        steam_path, account_id, gameid, label, files, close_steam = self.args
        try:
            if close_steam and steam.is_steam_running():
                self.message.emit(tr("closing_steam"), "info")
                if not steam.shutdown_steam(steam_path, log=lambda m: None):
                    raise importer.ImportError_(tr("steam_timeout"))
                self.message.emit(tr("steam_closed_log"), "info")
            report = importer.import_images(
                steam_path, account_id, gameid, files, label=label,
                progress=lambda i, n, name: self.progress.emit(i, n, name),
                log_fn=lambda m: self.message.emit(m, "info"),
                cancelled=lambda: self._cancel)
            self.finished_ok.emit(report)
        except Exception as e:  # noqa: BLE001
            log.exception("Importación fallida")
            self.failed.emit(str(e))


# --------------------------------------------------------------------------- ventana
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Steam Screenshot Importer")
        self.resize(1200, 760)
        self.settings = read_json(SETTINGS_FILE, {})
        self.steam_path = steam.find_steam_path()
        self.generation = 0
        self.pool = QThreadPool.globalInstance()
        self.thumb_signals = _ThumbSignals()
        self.thumb_signals.done.connect(self._on_thumb)
        self.items: dict[str, QListWidgetItem] = {}
        self.worker: ImportWorker | None = None
        self.labels: dict[int, str] = {}
        self.watch: dict | None = None
        self.watch_timer = QTimer(self, interval=3000, timeout=self._poll_publication)

        self._build()
        self._load_steam()
        QTimer.singleShot(0, self._check_recovery)
        last = self.settings.get("folder")
        if last and Path(last).is_dir():
            self._load_folder(Path(last))

    # ------------------------------------------------------------------ construcción
    def _build(self):
        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # cabecera: Steam + cuenta
        head = QHBoxLayout()
        title = QLabel("Steam Screenshot Importer")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        self.steam_status = QLabel()
        self.steam_status.setObjectName("muted")
        self.steam_status.setMinimumWidth(110)
        head.addWidget(self.steam_status)
        head.addWidget(QLabel(tr("account")))
        self.user_combo = QComboBox(minimumWidth=260)
        self.user_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.user_combo.setMinimumContentsLength(28)
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        head.addWidget(self.user_combo)
        refresh = QPushButton("⟳")
        refresh.setToolTip(tr("refresh_tip"))
        refresh.setFixedWidth(36)
        refresh.clicked.connect(self._load_steam)
        head.addWidget(refresh)
        lay.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split, 1)

        # ---- izquierda: carpeta + galería
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        pick = QPushButton(tr("pick_folder"))
        pick.clicked.connect(self._pick_folder)
        row.addWidget(pick)
        self.folder_label = QLabel(tr("no_folder"))
        self.folder_label.setObjectName("muted")
        self.folder_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.folder_label, 1)
        self.recursive = QCheckBox(tr("subfolders"))
        self.recursive.setChecked(bool(self.settings.get("recursive")))
        self.recursive.toggled.connect(lambda: self._reload_folder())
        row.addWidget(self.recursive)
        ll.addLayout(row)

        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.IconMode)
        self.gallery.setIconSize(QSize(THUMB, THUMB))
        self.gallery.setGridSize(QSize(THUMB + 24, THUMB + 40))
        self.gallery.setResizeMode(QListWidget.Adjust)
        self.gallery.setMovement(QListWidget.Static)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.gallery.setWordWrap(True)
        self.gallery.itemSelectionChanged.connect(self._update_button)
        ll.addWidget(self.gallery, 1)

        sel = QHBoxLayout()
        b_all = QPushButton(tr("select_all"))
        b_all.clicked.connect(self.gallery.selectAll)
        b_none = QPushButton(tr("select_none"))
        b_none.clicked.connect(self.gallery.clearSelection)
        sel.addWidget(b_all)
        sel.addWidget(b_none)
        sel.addStretch()
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        sel.addWidget(self.count_label)
        ll.addLayout(sel)
        split.addWidget(left)

        # ---- derecha: destino, acción, progreso, registro
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)

        box = QFrame(objectName="panel")
        l1 = QVBoxLayout(box)
        l1.addWidget(QLabel(tr("game_title")))
        self.label_combo = QComboBox(editable=True)
        self.label_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.label_combo.lineEdit().setPlaceholderText(tr("game_placeholder"))
        self.label_combo.lineEdit().setMaxLength(120)
        self.label_combo.currentTextChanged.connect(self._update_button)
        l1.addWidget(self.label_combo)
        hint = QLabel(tr("game_hint"))
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        hint.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        l1.addWidget(hint)
        l1.addStretch()
        rl.addWidget(box, 1)

        self.go = QPushButton(tr("go"))
        self.go.setObjectName("primary")
        self.go.setMinimumHeight(46)
        self.go.clicked.connect(self._start)
        rl.addWidget(self.go)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.setFormat(tr("ready"))
        self.progress.setValue(0)
        rl.addWidget(self.progress)

        self.pub_frame = QFrame(objectName="card")
        pf = QVBoxLayout(self.pub_frame)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("pub_title")))
        top.addStretch()
        b_close = QPushButton(tr("hide"), toolTip=tr("hide_tip"))
        b_close.clicked.connect(self._close_publication)
        top.addWidget(b_close)
        pf.addLayout(top)
        self.pub_label = QLabel()
        self.pub_label.setWordWrap(True)
        pf.addWidget(self.pub_label)
        pr = QHBoxLayout()
        self.b_manager = QPushButton(tr("open_manager"))
        self.b_manager.clicked.connect(lambda: self.watch and publish.open_screenshot_manager(self.watch["gameid"]))
        self.b_profile = QPushButton(tr("open_profile"))
        self.b_profile.clicked.connect(self._open_profile)
        pr.addWidget(self.b_manager)
        pr.addWidget(self.b_profile)
        pf.addLayout(pr)
        self.pub_frame.hide()
        rl.addWidget(self.pub_frame)

        rl.addWidget(QLabel(tr("log_title")))
        self.log_view = QPlainTextEdit(readOnly=True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        rl.addWidget(self.log_view, 1)
        split.addWidget(right)
        split.setSizes([760, 440])

        self.setCentralWidget(root)
        self._update_button()

    # ------------------------------------------------------------------ registro
    def _log(self, text: str, level: str = "info"):
        colors = {"info": "#c9d1d9", "ok": "#3fb950", "warn": "#d29922", "error": "#f85149"}
        esc = text.replace("&", "&amp;").replace("<", "&lt;")
        self.log_view.appendHtml(f'<span style="color:{colors.get(level, "#c9d1d9")}">{esc}</span>')
        getattr(log, {"ok": "info", "warn": "warning"}.get(level, level), log.info)(text)

    # ------------------------------------------------------------------ Steam / cuentas / juegos
    def _load_steam(self):
        self.steam_path = steam.find_steam_path()
        self.user_combo.blockSignals(True)
        self.user_combo.clear()
        if not self.steam_path:
            self.steam_status.setText(tr("steam_missing"))
            self._log(tr("steam_missing_log"), "error")
            self.user_combo.blockSignals(False)
            return
        running = steam.is_steam_running()
        active = steam.active_account_id() if running else 0
        self.steam_status.setText(tr("steam_open") if running else tr("steam_closed"))
        self.steam_status.setToolTip(str(self.steam_path))
        users = steam.list_users(self.steam_path)
        wanted = self.settings.get("account_id") or active
        for u in users:
            mark = tr("active_session") if u.account_id == active else ""
            self.user_combo.addItem(u.label + mark, u)
            if u.account_id == wanted:
                self.user_combo.setCurrentIndex(self.user_combo.count() - 1)
        self.user_combo.blockSignals(False)
        self._on_user_changed()

    def _user(self) -> steam.SteamUser | None:
        return self.user_combo.currentData()

    def _on_user_changed(self):
        u = self._user()
        if not (u and self.steam_path):
            return
        self.labels = importer.known_labels(self.steam_path, u.account_id)
        current = self.label_combo.currentText()
        self.label_combo.blockSignals(True)
        self.label_combo.clear()
        names = sorted(set(self.labels.values()) | set(self.settings.get("labels", [])), key=str.casefold)
        self.label_combo.addItems(names)
        self.label_combo.setEditText(current or self.settings.get("last_label", ""))
        self.label_combo.blockSignals(False)
        self._update_button()

    # ------------------------------------------------------------------ galería
    def _pick_folder(self):
        start = self.settings.get("folder") or str(Path.home() / "Pictures")
        d = QFileDialog.getExistingDirectory(self, tr("folder_dialog"), start)
        if d:
            self._load_folder(Path(d))

    def _reload_folder(self):
        if self.settings.get("folder"):
            self._load_folder(Path(self.settings["folder"]))

    def _load_folder(self, folder: Path):
        self.settings["folder"] = str(folder)
        self.settings["recursive"] = self.recursive.isChecked()
        self._save_settings()
        self.generation += 1
        self.gallery.clear()
        self.items.clear()
        self.folder_label.setText(str(folder))
        try:
            files = images.scan_folder(folder, self.recursive.isChecked())
        except OSError as e:
            self._log(tr("read_folder_error", e=e), "error")
            return
        placeholder = QPixmap(THUMB, THUMB)
        placeholder.fill(QColor("#21262d"))
        icon = QIcon(placeholder)
        for f in files:
            it = QListWidgetItem(icon, f.name)
            it.setData(Qt.UserRole, str(f))
            it.setToolTip(str(f))
            self.gallery.addItem(it)
            self.items[str(f)] = it
            self.pool.start(_ThumbTask(str(f), self.thumb_signals, self.generation, self))
        self.gallery.selectAll()
        self._log(tr("n_found", n=len(files), folder=folder))
        self._update_button()

    def _on_thumb(self, path: str, pix: QPixmap):
        it = self.items.get(path)
        if it:  # centrar en un lienzo cuadrado para que todas las celdas sean iguales
            canvas = QPixmap(THUMB * 2, THUMB * 2)
            canvas.fill(Qt.transparent)
            scaled = pix.scaled(canvas.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p = QPainter(canvas)
            p.drawPixmap((canvas.width() - scaled.width()) // 2, (canvas.height() - scaled.height()) // 2, scaled)
            p.end()
            it.setIcon(QIcon(canvas))

    def _selected_files(self) -> list[Path]:
        rows = sorted(self.gallery.row(i) for i in self.gallery.selectedItems())
        return [Path(self.gallery.item(r).data(Qt.UserRole)) for r in rows]

    # ------------------------------------------------------------------ destino
    def _target(self) -> tuple[int, str] | None:
        """(id del juego, nombre) o None si falta el nombre."""
        name = " ".join(self.label_combo.currentText().split())
        if not name:
            return None
        for gid, existing in self.labels.items():
            if existing.casefold() == name.casefold():
                return gid, existing
        return importer.label_gameid(name), name

    def _update_button(self):
        n = len(self.gallery.selectedItems())
        total = self.gallery.count()
        self.count_label.setText(tr("n_selected", n=n, total=total))
        busy = self.worker is not None
        ok = n > 0 and self._target() is not None and self._user() is not None and not busy
        self.go.setEnabled(ok)
        self.go.setText(tr("importing") if busy else (tr("go_1") if n == 1 else tr("go_n", n=n) if n else tr("go")))

    # ------------------------------------------------------------------ proceso
    def _start(self):
        target, user, files = self._target(), self._user(), self._selected_files()
        if not (target and user and files and self.steam_path):
            return
        gameid, label = target
        shown = label
        running = steam.is_steam_running()
        if running:
            active = steam.active_account_id()
            extra = ""
            if active and active != user.account_id:
                extra = tr("other_account")
            r = QMessageBox.question(
                self, tr("close_title"), tr("close_body") + extra,
                QMessageBox.Ok | QMessageBox.Cancel)
            if r != QMessageBox.Ok:
                return
        labels = set(self.settings.get("labels", [])) | {label}
        self.settings["labels"] = sorted(labels, key=str.casefold)[:200]
        self.settings["last_label"] = label
        self.settings["account_id"] = user.account_id
        self._save_settings()

        self._log(tr("importing_log", n=len(files), game=shown, acc=user.account_id))
        self.pub_frame.hide()
        self.watch_timer.stop()
        self.worker = ImportWorker(self.steam_path, user.account_id, gameid, label, files, running)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self._log)
        self.worker.finished_ok.connect(lambda rep: self._on_done(rep, shown, user))
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_end)
        self._update_button()
        self.worker.start()

    def _on_progress(self, i: int, n: int, name: str):
        self.progress.setMaximum(max(n, 1))
        self.progress.setValue(i)
        self.progress.setFormat(f"{i}/{n}  {name}" if name else f"{i}/{n}")

    def _on_worker_end(self):
        self.worker = None
        self._update_button()

    def _on_failed(self, msg: str):
        self.progress.setFormat(tr("error"))
        self._log(tr("error_log", msg=msg), "error")
        QMessageBox.critical(self, tr("import_failed"), msg)

    def _on_done(self, rep: importer.ImportReport, shown: str, user: steam.SteamUser):
        for it in rep.items:
            if it.status == "imported":
                self._log(tr("item_ok", src=it.source.name, dst=it.steam_file, msg=it.message), "ok")
            elif it.status == "duplicate":
                self._log(tr("item_dup", src=it.source.name, msg=it.message), "warn")
            else:
                self._log(tr("item_err", src=it.source.name, msg=it.message), "error")
        n_ok, n_dup, n_err = rep.count("imported"), rep.count("duplicate"), rep.count("error")
        summary = tr("summary", ok=n_ok, dup=n_dup, err=n_err)
        self._log(summary, "ok" if not n_err else "warn")
        self.progress.setFormat(summary)
        if not n_ok:
            return
        self.watch = {"gameid": rep.appid, "account": rep.account_id, "files": rep.imported_files,
                      "shown": shown, "steamid64": user.steamid64}
        publish.open_screenshot_manager(rep.appid)
        self._log(tr("opening_manager"))
        self._show_publication([], rep.imported_files)
        self.watch_timer.start()

    # ------------------------------------------------------------------ verificación de la publicación
    def _show_publication(self, published: list[str], pending: list[str]):
        w = self.watch
        total = len(published) + len(pending)
        if pending:
            txt = tr("pub_pending", game=w["shown"], n=len(pending), done=len(published), total=total)
        else:
            txt = tr("pub_done", total=total)
        self.pub_label.setText(txt)
        self.pub_frame.show()

    def _poll_publication(self):
        w = self.watch
        if not (w and self.steam_path):
            self.watch_timer.stop()
            return
        try:
            published, pending = publish.check(self.steam_path, w["account"], w["gameid"], w["files"])
        except Exception as e:  # noqa: BLE001
            log.debug("poll: %s", e)
            return
        if len(published) != w.get("last", -1):
            if w.get("last", -1) >= 0 and published:
                self._log(tr("pub_progress", done=len(published), total=len(w["files"])), "ok")
            w["last"] = len(published)
            self._show_publication(published, pending)
        if not pending:
            self.watch_timer.stop()

    def _close_publication(self):
        self.watch_timer.stop()
        self.watch = None
        self.pub_frame.hide()

    def _open_profile(self):
        if self.watch:
            publish.open_profile_screenshots(self.watch["steamid64"])

    # ------------------------------------------------------------------ varios
    def _check_recovery(self):
        j = importer.pending_recovery()
        if not j:
            return
        r = QMessageBox.question(self, tr("recover_title"), tr("recover_body"))
        if r == QMessageBox.Yes:
            try:
                importer.recover(lambda m: self._log(m, "warn"))
                self._log(tr("recover_ok"), "ok")
            except Exception as e:  # noqa: BLE001
                self._log(tr("recover_fail", e=e), "error")

    def _save_settings(self):
        try:
            write_json_atomic(SETTINGS_FILE, self.settings)
        except OSError:
            pass

    def closeEvent(self, e):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(30000)
        self.generation += 1
        self.pool.clear()
        super().closeEvent(e)


STYLE = """
* { font-family: 'Segoe UI'; font-size: 10pt; }
QMainWindow, QWidget { background: #0d1117; color: #c9d1d9; }
QLabel#title { font-size: 15pt; font-weight: 600; color: #f0f6fc; }
QLabel#muted { color: #8b949e; }
QPushButton { background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #30363d; }
QPushButton:disabled { color: #6e7681; }
QPushButton#primary { background: #1f6feb; border: none; color: white; font-size: 11pt; font-weight: 600; }
QPushButton#primary:hover { background: #388bfd; }
QPushButton#primary:disabled { background: #1c2d4a; color: #6e7681; }
QLineEdit, QComboBox, QPlainTextEdit, QListWidget { background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; padding: 4px; selection-background-color: #1f6feb; }
QListWidget::item:selected { background: #1f6feb55; border: 1px solid #388bfd; border-radius: 6px; }
QTabWidget::pane { border: 1px solid #30363d; border-radius: 6px; top: -1px; }
QTabBar::tab { background: #161b22; padding: 7px 14px; border: 1px solid #30363d; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
QTabBar::tab:selected { background: #0d1117; color: #f0f6fc; }
QProgressBar { background: #161b22; border: 1px solid #30363d; border-radius: 6px; text-align: center; height: 22px; }
QProgressBar::chunk { background: #238636; border-radius: 5px; }
QFrame#card { background: #161b22; border: 1px solid #1f6feb; border-radius: 8px; }
QFrame#panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; }
QFrame#panel QLabel { background: transparent; }
QFrame#card QLabel, QFrame#card QPushButton { background: transparent; }
QFrame#card QPushButton { border: 1px solid #30363d; }
QCheckBox { spacing: 6px; }
QSplitter::handle { background: #0d1117; }
"""


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    from PySide6.QtCore import QLibraryInfo, QTranslator
    qt_tr = QTranslator(app)  # botones estándar de Qt (Aceptar/Cancelar…) en el idioma elegido
    if i18n.LANG == "es" and qt_tr.load("qtbase_es", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_tr)
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    icon = base / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.show()
    return app.exec()

@echo off
rem Genera dist\SteamScreenshotImporter.exe (no hace falta Python para ejecutarlo)
python -m pip install -r requirements.txt pyinstaller || exit /b 1
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name SteamScreenshotImporter --icon assets\icon.ico ^
  --add-data "assets\icon.png;assets" ^
  --exclude-module PyQt6 --exclude-module PyQt5 --exclude-module tkinter ^
  --exclude-module numpy --exclude-module pandas --exclude-module customtkinter ^
  run.py

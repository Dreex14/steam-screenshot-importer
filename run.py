"""Punto de entrada (también para PyInstaller)."""
import sys

from steamshot.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

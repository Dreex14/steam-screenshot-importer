import sys

from steamshot.core.common import setup_logging


def main() -> int:
    setup_logging()
    from steamshot import i18n
    i18n.set_language(i18n.detect_language())
    from steamshot.ui.main_window import run
    return run()


if __name__ == "__main__":
    sys.exit(main())

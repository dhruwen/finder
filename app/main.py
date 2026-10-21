"""Application entry point."""
from __future__ import annotations

import os
import sys


def self_test() -> int:
    """`Finder --self-test`: used by the release build (CI) to prove the
    *packaged* app actually starts — every module, Qt plugin, bundled asset
    and the local AI model resolve inside the frozen bundle — then exits.
    Exit code 0 = OK. Never touches the user's files."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtGui import QImage
    from PyQt6.QtWidgets import QApplication

    from app.core import ner
    from app.ui.main_window import MainWindow
    from app.ui.resources import resource_path
    from app.ui.style import CHECK_ICON, STYLESHEET

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    problems = []
    if QImage(CHECK_ICON).isNull():
        problems.append(f"check-mark image not loadable: {CHECK_ICON}")
    if not resource_path("docs", "USER_GUIDE.md").exists():
        problems.append("USER_GUIDE.md missing")
    if not ner.is_available() or ner.suggest_name("Ramesh Kumar ITR 2024") is None:
        problems.append("local AI name model not working")
    MainWindow().close()

    for p in problems:
        print("SELF-TEST FAIL:", p)
    print("SELF-TEST", "FAILED" if problems else "OK")
    return 1 if problems else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    from PyQt6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow
    from app.ui.style import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName("Finder")
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

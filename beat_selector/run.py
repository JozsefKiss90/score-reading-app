from __future__ import annotations

import sys
from typing import List, Optional

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication, QFileDialog

from .view import ScoreViewBeats


def _pick_file_if_needed(path: Optional[str]) -> Optional[str]:
    if path:
        return path
    dlg = QFileDialog()
    dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
    dlg.setNameFilter("Scores (*.mxl *.xml *.musicxml)")
    if dlg.exec():
        files = dlg.selectedFiles()
        if files:
            return files[0]
    return None


def main(argv: List[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    app = QApplication(argv)
    app.aboutToQuit.connect(lambda: print("[ScoreViewBeats] aboutToQuit()", flush=True))
    mxl_path = _pick_file_if_needed(argv[1] if len(argv) > 1 else None)
    if not mxl_path:
        print("No score selected, exiting.")
        return 0

    w = ScoreViewBeats(mxl_path)
    w.resize(900, 700)
    w.show()

    rc = app.exec()
    print(f"[ScoreViewBeats] app.exec() returned {rc}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

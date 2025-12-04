# run_selection_lab.py — demo launcher for the static BeatSelector window
import os
import sys

from PyQt6.QtWidgets import QApplication

from ui.beat_selector import BeatSelector
from app_context import AppContext

# Config defaults imported from existing config.py (if available)

DEFAULT_MXL = "Gymnopdie_No._1__Satie.mxl"
DEFAULT_XML = "Gymnopdie/score.xml"


def main() -> None:
    app = QApplication(sys.argv)

    # Reuse the same resource resolution logic as the main app
    ctx = AppContext()

    mxl_file = ctx.resources_path(DEFAULT_MXL)
    xml_path = ctx.resources_path(DEFAULT_XML)

    if not os.path.exists(mxl_file):
        print("MXL not found:", mxl_file)
        ctx.shutdown()
        sys.exit(1)

    w = BeatSelector(mxl_file, xml_path)
    w.resize(1200, 900)
    w.show()

    # Print selections as they change
    def on_sel(keys: list[str]) -> None:
        print("Selected beats:", keys)

    w.selectionChanged.connect(on_sel)

    ret = app.exec()
    ctx.shutdown()
    sys.exit(ret)


if __name__ == "__main__":
    main()

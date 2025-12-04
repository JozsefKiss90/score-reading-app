import os
import sys

from PyQt6.QtWidgets import QApplication

from config import DEFAULT_SF2, DEFAULT_MXL, DEFAULT_XML
from ui.practice_window import PracticeWindow
from app_context import AppContext


def main() -> None:
    app = QApplication(sys.argv)

    # Application-wide context: resources + shared MIDI service
    ctx = AppContext(soundfont_name=DEFAULT_SF2)

    mxl_file = ctx.resources_path(DEFAULT_MXL)
    xml_path = ctx.resources_path(DEFAULT_XML)

    if not os.path.exists(mxl_file):
        print("MXL file not found:", mxl_file)
        ctx.shutdown()
        sys.exit(1)

    # Practice window now receives the shared context
    window = PracticeWindow(ctx, mxl_file, xml_path, score_path=mxl_file)
    window.resize(1400, 900)
    window.show()

    ret = app.exec()
    ctx.shutdown()
    sys.exit(ret)


if __name__ == "__main__":
    main()


# run_selection_lab.py — demo launcher for the static BeatSelector window
import os, sys
from PyQt6.QtWidgets import QApplication
from ui.beat_selector import BeatSelector

# Match app.py helper
def resources_path(name: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "resources", name)
    if os.path.exists(cand):
        return cand
    return os.path.join(os.getcwd(), "resources", name)

# Config defaults imported from existing config.py (if available)
try:
    from config import DEFAULT_MXL, DEFAULT_XML
except Exception:
    DEFAULT_MXL = "Gymnopdie_No._1__Satie.mxl"
    DEFAULT_XML = "Gymnopdie/score.xml"

def main():
    app = QApplication(sys.argv)
    mxl_file = resources_path(DEFAULT_MXL)
    xml_path = resources_path(DEFAULT_XML)

    if not os.path.exists(mxl_file):
        print("MXL not found:", mxl_file)
        sys.exit(1)

    w = BeatSelector(mxl_file, xml_path)
    w.resize(1200, 900); w.show()

    # Print selections as they change
    def on_sel(keys):
        print("Selected beats:", keys)
    w.selectionChanged.connect(on_sel)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

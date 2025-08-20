
import os, sys
from PyQt6.QtWidgets import QApplication
from config import NUM_KEYS, KEY_WIDTH, VIEW_HEIGHT, DEFAULT_SF2, DEFAULT_MXL, DEFAULT_XML
from ui.pianoroll import PianoRoll
from ui.practice_window import PracticeWindow

def resources_path(name: str) -> str:
    # Resolve relative to installed package layout or local tree
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.join(here, "resources", name)
    if os.path.exists(cand):
        return cand
    # Fallback to CWD/resources
    return os.path.join(os.getcwd(), "resources", name)

def main():
    app = QApplication(sys.argv)

    mxl_file = resources_path(DEFAULT_MXL)
    xml_path = resources_path(DEFAULT_XML)
    sf2_path = resources_path(DEFAULT_SF2)

    if not os.path.exists(mxl_file):
        print("MXL file not found:", mxl_file)
        sys.exit(1)

    
    window = PracticeWindow(mxl_file, xml_path, soundfont=sf2_path, score_path=mxl_file)
    window.resize(1400, 900)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from audio.midi_service import MidiService
from .cof_view import CofView   # <-- fixed import

def main():
    app = QApplication(sys.argv)

    midi = MidiService()  # create once for THIS COF app
    html = Path(__file__).resolve().parent / "minimap_es_test_chord.html"

    cof = CofView(str(html), midi_service=midi)
    cof.resize(1100, 750)
    cof.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

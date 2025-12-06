import sys, json
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox

# Your refactored viewer (now with beat selection)
from beat_ui import ScoreView  # same file you just updated

def main():
    app = QApplication(sys.argv)

    # --- choose a score (or hard-code a path) ---
    score_path = str(Path("resources/Gymnopdie/score.xml").resolve())

    # --- build UI ---
    win = QWidget()
    win.setWindowTitle("Beat Selector — score_view")
    layout = QVBoxLayout(win)

    view = ScoreView(score_path)     # <— shows the score & draws beat boxes automatically
    view.set_highlight_theme("sky")  # optional: 'amber'|'sky'|'mint'|'violet'
    layout.addWidget(view, 1)

    # Buttons: read/save selection
    btn_get  = QPushButton("Get selection")
    btn_load = QPushButton("Load selection from JSON…")
    btn_save = QPushButton("Save selection to JSON…")
    btn_clear= QPushButton("Clear selection")

    layout.addWidget(btn_get)
    layout.addWidget(btn_load)
    layout.addWidget(btn_save)
    layout.addWidget(btn_clear)
    
    def on_get():
        def show_selection(pairs):
            # pairs is a Python list of [absIdx, beatIdx]
            QMessageBox.information(win, "Selection", json.dumps(pairs, indent=2))
        view.get_selection(show_selection)

    def on_save():
        def after_get(pairs):
            fn, _ = QFileDialog.getSaveFileName(win, "Save selection", "selection.json", "JSON (*.json)")
            if not fn: return
            Path(fn).write_text(json.dumps({"pairs": pairs}, indent=2), encoding="utf-8")
        view.get_selection(after_get)

    def on_load():
        fn, _ = QFileDialog.getOpenFileName(win, "Load selection", "", "JSON (*.json)")
        if not fn: return
        data = json.loads(Path(fn).read_text(encoding="utf-8"))
        pairs = [(int(a), int(b)) for a,b in data.get("pairs", [])]
        view.set_selection(pairs)

    def on_clear():
        view.clear_selection()

    btn_get.clicked.connect(on_get)
    btn_save.clicked.connect(on_save)
    btn_load.clicked.connect(on_load)
    btn_clear.clicked.connect(on_clear)

    win.resize(1200, 800)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

import sys, time, mido
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QTimer

class Test(QWidget):
    def __init__(self):
        super().__init__()
        print("Ports:", mido.get_input_names())
        self.inport = mido.open_input("SE61 0")
        print("Opened:", self.inport)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(5)

    def poll(self):
        for msg in self.inport.iter_pending():
            print("MIDI:", msg)

app = QApplication(sys.argv)
w = Test()
w.show()
sys.exit(app.exec())

import sys
import os
import ctypes

# Ensure the root project folder is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from app.gui.main_window import MainWindow

def main():
    # Set Windows AppUserModelID so Taskbar displays custom icon instead of generic Python/EXE icon
    if os.name == 'nt':
        try:
            myappid = 'vipstudios.vipgifstudio.editor.1.0.1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("VIP GIF Studio")
    app.setOrganizationName("VIP Studios")

    # Set App Icon
    icon_path = os.path.join(current_dir, "assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()


"""
Modern Dark Theme QSS (CSS) stylesheet inspired by professional video editing suites.
"""

DARK_STYLESHEET = """
/* Global App Defaults */
QWidget {
    background-color: #181825;
    color: #CDD6F4;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 13px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: #11111B;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #45475A;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #585B70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #11111B;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #45475A;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #585B70;
}

/* Header Cards & Panels */
QGroupBox {
    background-color: #1E1E2E;
    border: 1px solid #313244;
    border-radius: 10px;
    margin-top: 15px;
    padding: 15px;
    font-weight: bold;
    color: #89B4FA;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 15px;
    padding: 0 8px;
    background-color: #1E1E2E;
    color: #89B4FA;
}

/* Buttons */
QPushButton {
    background-color: #313244;
    color: #F5E0DC;
    border: 1px solid #45475A;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #45475A;
    border-color: #89B4FA;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #585B70;
}
QPushButton:disabled {
    background-color: #1E1E2E;
    color: #585B70;
    border-color: #313244;
}

/* Accent Buttons (Converter / Open File) */
QPushButton#primaryButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89B4FA, stop:1 #B4BEFE);
    color: #11111B;
    border: none;
    font-size: 14px;
    font-weight: bold;
    border-radius: 10px;
    padding: 12px 24px;
}
QPushButton#primaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B4BEFE, stop:1 #CBA6F7);
    color: #11111B;
}
QPushButton#primaryButton:disabled {
    background: #313244;
    color: #585B70;
}

QPushButton#fileButton {
    background-color: #313244;
    border: 1px dashed #89B4FA;
    color: #89B4FA;
    border-radius: 10px;
    font-size: 13px;
    padding: 10px;
}
QPushButton#fileButton:hover {
    background-color: #45475A;
    border: 1px solid #B4BEFE;
    color: #FFFFFF;
}

/* Inputs & Combos */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #11111B;
    color: #CDD6F4;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #89B4FA;
    selection-color: #11111B;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #89B4FA;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1E1E2E;
    border: 1px solid #45475A;
    selection-background-color: #89B4FA;
    selection-color: #11111B;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #313244;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #89B4FA;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #F5C2E7;
    border: 2px solid #89B4FA;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: #FFFFFF;
    border-color: #F5C2E7;
}

/* Progress Bar */
QProgressBar {
    background-color: #11111B;
    border: 1px solid #313244;
    border-radius: 8px;
    text-align: center;
    color: #CDD6F4;
    font-weight: bold;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89B4FA, stop:1 #F5C2E7);
    border-radius: 7px;
}

/* Time Code Label */
QLabel#timeLabel {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 14px;
    color: #F5C2E7;
    font-weight: bold;
    background-color: #11111B;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 4px 8px;
}
"""

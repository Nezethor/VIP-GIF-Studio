from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont

class DualRangeSlider(QWidget):
    """
    Custom dual-handle horizontal slider for selecting video trim start and end times.
    """
    # Signal emitted when start or end values change: (start_val, end_val)
    rangeChanged = pyqtSignal(float, float)
    # Signal emitted while dragging handles: (current_handle_val)
    handleMoved = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(44)
        self.setMouseTracking(True)

        self._min_val = 0.0
        self._max_val = 100.0
        self._start_val = 0.0
        self._end_val = 100.0
        self._current_pos = 0.0

        self._active_handle = None  # 'start', 'end', or 'pos'
        self._handle_radius = 9.0
        self._bar_height = 8.0

    def setRange(self, min_val: float, max_val: float):
        self._min_val = max(0.0, min_val)
        self._max_val = max(self._min_val + 0.1, max_val)
        self._start_val = max(self._min_val, self._start_val)
        self._end_val = min(self._max_val, self._end_val)
        if self._start_val >= self._end_val:
            self._start_val = self._min_val
            self._end_val = self._max_val
        self.update()

    def setValues(self, start_val: float, end_val: float):
        self._start_val = max(self._min_val, min(start_val, self._max_val))
        self._end_val = max(self._start_val + 0.1, min(end_val, self._max_val))
        self.update()
        self.rangeChanged.emit(self._start_val, self._end_val)

    def setCurrentPos(self, pos_val: float):
        self._current_pos = max(self._min_val, min(pos_val, self._max_val))
        self.update()

    def getValues(self):
        return self._start_val, self._end_val

    def _val_to_x(self, val: float) -> float:
        margin = self._handle_radius + 4
        width = self.width() - 2 * margin
        if self._max_val <= self._min_val:
            return margin
        ratio = (val - self._min_val) / (self._max_val - self._min_val)
        return margin + ratio * width

    def _x_to_val(self, x: float) -> float:
        margin = self._handle_radius + 4
        width = self.width() - 2 * margin
        if width <= 0:
            return self._min_val
        ratio = (x - margin) / width
        ratio = max(0.0, min(1.0, ratio))
        return self._min_val + ratio * (self._max_val - self._min_val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = self._handle_radius + 4
        cy = self.height() / 2.0
        bar_rect = QRectF(margin, cy - self._bar_height / 2.0, self.width() - 2 * margin, self._bar_height)

        # 1. Background Groove
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#313244")))
        painter.drawRoundedRect(bar_rect, 4, 4)

        # 2. Selected Range Bar
        x_start = self._val_to_x(self._start_val)
        x_end = self._val_to_x(self._end_val)
        range_rect = QRectF(x_start, cy - self._bar_height / 2.0, max(2.0, x_end - x_start), self._bar_height)
        painter.setBrush(QBrush(QColor("#89B4FA")))
        painter.drawRoundedRect(range_rect, 4, 4)

        # 3. Current Playhead Line (if within range)
        x_pos = self._val_to_x(self._current_pos)
        painter.setPen(QPen(QColor("#F5C2E7"), 2, Qt.PenStyle.SolidLine))
        painter.drawLine(int(x_pos), int(cy - 12), int(x_pos), int(cy + 12))

        # 4. Start Handle (Green / Cyan tint)
        self._draw_handle(painter, x_start, cy, QColor("#A6E3A1"), "A")

        # 5. End Handle (Red / Pink tint)
        self._draw_handle(painter, x_end, cy, QColor("#F38BA8"), "B")

    def _draw_handle(self, painter: QPainter, x: float, cy: float, color: QColor, label: str):
        r = self._handle_radius
        handle_rect = QRectF(x - r, cy - r, 2 * r, 2 * r)

        # Outer ring
        painter.setPen(QPen(QColor("#11111B"), 2))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(handle_rect)

        # Text label inside handle
        painter.setPen(QPen(QColor("#11111B")))
        font = QFont('Segoe UI', 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(handle_rect, Qt.AlignmentFlag.AlignCenter, label)

    def mousePressEvent(self, event):
        x = event.position().x()
        x_start = self._val_to_x(self._start_val)
        x_end = self._val_to_x(self._end_val)

        d_start = abs(x - x_start)
        d_end = abs(x - x_end)

        if d_start <= 14 and d_start <= d_end:
            self._active_handle = 'start'
        elif d_end <= 14:
            self._active_handle = 'end'
        else:
            # Clicked on track: move playhead position
            val = self._x_to_val(x)
            self.handleMoved.emit(val)
            self._active_handle = 'pos'

    def mouseMoveEvent(self, event):
        x = event.position().x()
        val = self._x_to_val(x)

        if self._active_handle == 'start':
            self._start_val = min(val, self._end_val - 0.1)
            self.update()
            self.rangeChanged.emit(self._start_val, self._end_val)
            self.handleMoved.emit(self._start_val)
        elif self._active_handle == 'end':
            self._end_val = max(val, self._start_val + 0.1)
            self.update()
            self.rangeChanged.emit(self._start_val, self._end_val)
            self.handleMoved.emit(self._end_val)
        elif self._active_handle == 'pos':
            self.handleMoved.emit(val)

    def mouseReleaseEvent(self, event):
        self._active_handle = None

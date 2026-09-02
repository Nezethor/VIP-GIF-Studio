from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QGroupBox, QMenu, QInputDialog, QColorDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QMouseEvent

from app.core.timeline import SpeedInterval, TimelineTextClip


class TimelineCanvas(QWidget):
    """
    Photoshop / Premiere style visual multi-track timeline canvas.
    Displays:
    - Time ruler with playhead needle.
    - Track 1: Speed Interval Blocks (Color-coded by speed factor).
    - Track 2: Simple Text Overlay Clips.
    """
    playhead_moved = pyqtSignal(float)
    interval_selected = pyqtSignal(object)
    text_clip_selected = pyqtSignal(object)
    timeline_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(150)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)

        self.duration = 10.0
        self.current_sec = 0.0
        self.intervals = [SpeedInterval(0.0, 10.0, 1.0)]
        self.text_clips = []

        self.selected_interval = self.intervals[0]
        self.selected_text_clip = None

        self._is_dragging_playhead = False
        self._is_dragging_clip_edge = False
        self._dragged_clip = None
        self._drag_edge_side = None

    def set_duration(self, duration: float):
        if duration <= 0:
            return
        self.duration = duration
        if not self.intervals or abs(sum(i.duration for i in self.intervals) - duration) > 0.5:
            self.intervals = [SpeedInterval(0.0, self.duration, 1.0)]
            self.selected_interval = self.intervals[0]
        self.update()

    def set_current_sec(self, sec: float):
        self.current_sec = max(0.0, min(self.duration, sec))
        self.update()

    def split_interval_at_current_sec(self):
        """Splits the interval containing current_sec into two separate blocks."""
        for idx, item in enumerate(self.intervals):
            if item.start_sec < self.current_sec < item.end_sec - 0.2:
                # Create two sub-intervals
                left = SpeedInterval(item.start_sec, self.current_sec, item.speed, item.reverse)
                right = SpeedInterval(self.current_sec, item.end_sec, item.speed, item.reverse)
                self.intervals[idx] = left
                self.intervals.insert(idx + 1, right)
                self.selected_interval = right
                self.timeline_changed.emit()
                self.update()
                return

    def _sec_to_x(self, sec: float) -> float:
        margin_left = 10
        usable_w = max(10, self.width() - 20)
        return margin_left + (sec / max(0.1, self.duration)) * usable_w

    def _x_to_sec(self, x: float) -> float:
        margin_left = 10
        usable_w = max(10, self.width() - 20)
        rel_x = max(0, min(usable_w, x - margin_left))
        return (rel_x / float(usable_w)) * self.duration

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, QColor("#181825"))

        # Track layouts
        ruler_h = 30
        track1_y = 35
        track1_h = 45
        track2_y = 90
        track2_h = 45

        # Track background lanes
        painter.fillRect(10, track1_y, w - 20, track1_h, QColor("#1E1E2E"))
        painter.fillRect(10, track2_y, w - 20, track2_h, QColor("#1E1E2E"))

        # Track labels
        font_sm = QFont("Segoe UI", 8)
        painter.setFont(font_sm)
        painter.setPen(QColor("#A6ADC8"))
        painter.drawText(15, track1_y + 16, "PISTA VELOCIDAD")
        painter.drawText(15, track2_y + 16, "PISTA TEXTO")

        # --- 1. DRAW RULER ---
        painter.setPen(QPen(QColor("#45475A"), 1))
        painter.drawLine(10, ruler_h, w - 10, ruler_h)

        step_sec = max(0.5, self.duration / 10.0)
        curr_t = 0.0
        while curr_t <= self.duration + 0.01:
            x = self._sec_to_x(curr_t)
            painter.setPen(QPen(QColor("#585B70"), 1))
            painter.drawLine(int(x), ruler_h - 8, int(x), ruler_h)

            # Time text
            painter.setPen(QColor("#CDD6F4"))
            painter.drawText(int(x) - 15, ruler_h - 12, 30, 12, Qt.AlignmentFlag.AlignCenter, f"{curr_t:.1f}s")
            curr_t += step_sec

        # --- 2. DRAW SPEED INTERVAL CLIPS (TRACK 1) ---
        for item in self.intervals:
            x1 = self._sec_to_x(item.start_sec)
            x2 = self._sec_to_x(item.end_sec)
            block_w = max(2, x2 - x1)

            # Color coding based on speed
            if item.reverse:
                bg_color = QColor("#F38BA8") # Red / Pink for Reverse
            elif item.speed < 0.9:
                bg_color = QColor("#FAB387") # Orange for Slow-mo
            elif item.speed > 1.1:
                bg_color = QColor("#CBA6F7") # Purple for Fast
            else:
                bg_color = QColor("#89B4FA") # Blue for Normal

            if item == self.selected_interval:
                pen = QPen(QColor("#FFFFFF"), 2)
            else:
                pen = QPen(QColor("#11111B"), 1)

            painter.setPen(pen)
            painter.setBrush(QBrush(bg_color))
            rect = QRect(int(x1), track1_y + 2, int(block_w), track1_h - 4)
            painter.drawRoundedRect(rect, 4, 4)

            # Text inside block
            painter.setPen(QColor("#11111B"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            rev_tag = " 🔄" if item.reverse else ""
            txt_str = f"{item.speed:.2f}x{rev_tag}"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt_str)

        # --- 3. DRAW TEXT CLIPS (TRACK 2) ---
        for t_clip in self.text_clips:
            x1 = self._sec_to_x(t_clip.start_sec)
            x2 = self._sec_to_x(t_clip.end_sec)
            block_w = max(2, x2 - x1)

            bg_color = QColor("#A6E3A1") # Green for Text
            if t_clip == self.selected_text_clip:
                pen = QPen(QColor("#FFFFFF"), 2)
            else:
                pen = QPen(QColor("#11111B"), 1)

            painter.setPen(pen)
            painter.setBrush(QBrush(bg_color))
            rect = QRect(int(x1), track2_y + 2, int(block_w), track2_h - 4)
            painter.drawRoundedRect(rect, 4, 4)

            painter.setPen(QColor("#11111B"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"💬 {t_clip.text[:12]}")

        # --- 4. DRAW PLAYHEAD NEEDLE ---
        px = self._sec_to_x(self.current_sec)
        painter.setPen(QPen(QColor("#F5E0DC"), 2))
        painter.drawLine(int(px), 0, int(px), h)

        # Playhead handle cap
        painter.setBrush(QBrush(QColor("#F5E0DC")))
        points = [
            QPoint(int(px) - 6, 0),
            QPoint(int(px) + 6, 0),
            QPoint(int(px) + 6, 10),
            QPoint(int(px), 16),
            QPoint(int(px) - 6, 10)
        ]
        painter.drawPolygon(points)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            x, y = pos.x(), pos.y()

            # Playhead interaction
            ruler_rect = QRect(0, 0, self.width(), 35)
            if ruler_rect.contains(int(x), int(y)):
                self._is_dragging_playhead = True
                new_sec = self._x_to_sec(x)
                self.set_current_sec(new_sec)
                self.playhead_moved.emit(new_sec)
                return

            # Track 1: Speed Interval Click Selection
            track1_rect = QRect(0, 35, self.width(), 50)
            if track1_rect.contains(int(x), int(y)):
                sec = self._x_to_sec(x)
                for item in self.intervals:
                    if item.start_sec <= sec <= item.end_sec:
                        self.selected_interval = item
                        self.selected_text_clip = None
                        self.interval_selected.emit(item)
                        self.update()
                        break

            # Track 2: Text Clip Click Selection
            track2_rect = QRect(0, 90, self.width(), 50)
            if track2_rect.contains(int(x), int(y)):
                sec = self._x_to_sec(x)
                for t_clip in self.text_clips:
                    if t_clip.start_sec <= sec <= t_clip.end_sec:
                        self.selected_text_clip = t_clip
                        self.selected_interval = None
                        self.text_clip_selected.emit(t_clip)
                        self.update()
                        break

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging_playhead:
            new_sec = self._x_to_sec(event.position().x())
            self.set_current_sec(new_sec)
            self.playhead_moved.emit(new_sec)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_playhead = False


class TimelineWidget(QWidget):
    """
    Complete Timeline Editor panel with Toolbar, Canvas, and Inspector Controls.
    """
    playhead_moved = pyqtSignal(float)
    timeline_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

        # 1. Timeline Toolbar
        toolbar = QHBoxLayout()
        lbl_title = QLabel("🎬 Línea de Tiempo Profesional (Edición Multipista)", self)
        lbl_title.setStyleSheet("font-weight: bold; color: #89B4FA; font-size: 13px;")
        toolbar.addWidget(lbl_title)

        toolbar.addStretch()

        self.btn_split = QPushButton("✂ Dividir Clip en Aguja", self)
        self.btn_split.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        self.btn_split.clicked.connect(self._on_split_clicked)
        toolbar.addWidget(self.btn_split)

        self.btn_add_text = QPushButton("💬 + Texto en Aguja", self)
        self.btn_add_text.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_add_text.clicked.connect(self._on_add_text_clicked)
        toolbar.addWidget(self.btn_add_text)

        layout.addLayout(toolbar)

        # 2. Timeline Canvas
        self.canvas = TimelineCanvas(self)
        self.canvas.playhead_moved.connect(self.playhead_moved.emit)
        self.canvas.interval_selected.connect(self._on_interval_selected)
        self.canvas.text_clip_selected.connect(self._on_text_clip_selected)
        self.canvas.timeline_changed.connect(self.timeline_updated.emit)
        layout.addWidget(self.canvas)

        # 3. Block Inspector & Speed Controls
        self.inspector_group = QGroupBox("Inspector del Clip Seleccionado", self)
        insp_layout = QHBoxLayout(self.inspector_group)
        insp_layout.setContentsMargins(10, 6, 10, 6)

        self.lbl_insp_info = QLabel("Selecciona un bloque de la línea de tiempo", self.inspector_group)
        self.lbl_insp_info.setStyleSheet("color: #BAC2DE;")
        insp_layout.addWidget(self.lbl_insp_info)

        self.lbl_speed_tag = QLabel("Velocidad:", self.inspector_group)
        insp_layout.addWidget(self.lbl_speed_tag)

        self.spn_block_speed = QDoubleSpinBox(self.inspector_group)
        self.spn_block_speed.setRange(-10.0, 10.0)
        self.spn_block_speed.setValue(1.0)
        self.spn_block_speed.setSingleStep(0.25)
        self.spn_block_speed.setSuffix(" x")
        self.spn_block_speed.valueChanged.connect(self._on_speed_spin_changed)
        insp_layout.addWidget(self.spn_block_speed)

        # Quick speed preset buttons for block
        for spd_val, spd_lbl in [(-2.0, "-2x"), (0.25, "0.25x"), (0.5, "0.5x"), (1.0, "1x"), (2.0, "2x"), (4.0, "4x")]:
            btn = QPushButton(spd_lbl, self.inspector_group)
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda _, v=spd_val: self.spn_block_speed.setValue(v))
            insp_layout.addWidget(btn)

        layout.addWidget(self.inspector_group)

    def set_duration(self, duration: float):
        self.canvas.set_duration(duration)

    def set_current_sec(self, sec: float):
        self.canvas.set_current_sec(sec)

    def _on_split_clicked(self):
        self.canvas.split_interval_at_current_sec()

    def _on_add_text_clicked(self):
        text, ok = QInputDialog.getText(self, "Agregar Texto en Línea de Tiempo", "Ingresa el texto a mostrar:")
        if ok and text:
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 3.0)
            t_clip = TimelineTextClip(text=text, start_sec=start, end_sec=end)
            self.canvas.text_clips.append(t_clip)
            self.canvas.selected_text_clip = t_clip
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_interval_selected(self, interval: SpeedInterval):
        if interval:
            rev_sign = -1.0 if interval.reverse else 1.0
            self.spn_block_speed.blockSignals(True)
            self.spn_block_speed.setValue(interval.speed * rev_sign)
            self.spn_block_speed.blockSignals(False)
            self.lbl_insp_info.setText(f"Intervalo [{interval.start_sec:.2f}s - {interval.end_sec:.2f}s]")

    def _on_text_clip_selected(self, t_clip: TimelineTextClip):
        if t_clip:
            self.lbl_insp_info.setText(f"Texto: \"{t_clip.text}\" [{t_clip.start_sec:.2f}s - {t_clip.end_sec:.2f}s]")

    def _on_speed_spin_changed(self, val: float):
        if self.canvas.selected_interval:
            if val < 0:
                self.canvas.selected_interval.speed = abs(val)
                self.canvas.selected_interval.reverse = True
            else:
                self.canvas.selected_interval.speed = max(0.1, val)
                self.canvas.selected_interval.reverse = False

            self.canvas.selected_interval.label = f"{val:.2f}x"
            self.canvas.update()
            self.timeline_updated.emit()

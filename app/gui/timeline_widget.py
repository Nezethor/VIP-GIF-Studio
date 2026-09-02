import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QGroupBox,
    QFileDialog, QColorDialog, QScrollBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QMouseEvent, QWheelEvent

from app.core.timeline import SpeedInterval, TimelineTextClip, TimelineImageClip


class TimelineCanvas(QWidget):
    """
    Photoshop / Premiere style visual multi-track timeline canvas with:
    - Multi-track layout (Speed, Text Track 1, Text Track 2, Image Track).
    - Mouse wheel zooming (Ctrl+Wheel or Wheel to zoom in/out).
    - Draggable clips and draggable edge handles for precision timing.
    - Interactive playhead scrubbing.
    """
    playhead_moved = pyqtSignal(float)
    interval_selected = pyqtSignal(object)
    text_clip_selected = pyqtSignal(object)
    image_clip_selected = pyqtSignal(object)
    timeline_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(220)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)

        self.duration = 10.0
        self.current_sec = 0.0
        self.zoom_level = 1.0  # 1.0x to 20.0x zoom
        self.scroll_offset_sec = 0.0

        self.intervals = [SpeedInterval(0.0, 10.0, 1.0)]
        self.text_clips = []
        self.image_clips = []

        self.selected_interval = self.intervals[0]
        self.selected_text_clip = None
        self.selected_image_clip = None

        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._is_dragging_edge = False
        self._dragged_item = None
        self._drag_edge = None  # 'left' or 'right'
        self._drag_start_x = 0
        self._drag_orig_start = 0.0
        self._drag_orig_end = 0.0

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
                left = SpeedInterval(item.start_sec, self.current_sec, item.speed, item.reverse)
                right = SpeedInterval(self.current_sec, item.end_sec, item.speed, item.reverse)
                self.intervals[idx] = left
                self.intervals.insert(idx + 1, right)
                self.selected_interval = right
                self.timeline_changed.emit()
                self.update()
                return

    def _sec_to_x(self, sec: float) -> float:
        margin_left = 120
        usable_w = max(10, (self.width() - 130) * self.zoom_level)
        rel_sec = sec - self.scroll_offset_sec
        return margin_left + (rel_sec / max(0.1, self.duration)) * usable_w

    def _x_to_sec(self, x: float) -> float:
        margin_left = 120
        usable_w = max(10, (self.width() - 130) * self.zoom_level)
        rel_x = max(0, min(usable_w, x - margin_left))
        return self.scroll_offset_sec + (rel_x / float(usable_w)) * self.duration

    def wheelEvent(self, event: QWheelEvent):
        """Mouse wheel zooming in and out of timeline."""
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_level = min(20.0, self.zoom_level * 1.2)
        else:
            self.zoom_level = max(1.0, self.zoom_level / 1.2)
        self.update()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        painter.fillRect(0, 0, w, h, QColor("#181825"))

        ruler_h = 28
        track_h = 40
        track_y = [32, 77, 122, 167]
        track_names = ["PISTA VELOCIDAD", "PISTA TEXTO 1", "PISTA TEXTO 2", "PISTA IMAGENES"]

        # Track background lanes
        for idx, ty in enumerate(track_y):
            painter.fillRect(115, ty, w - 120, track_h, QColor("#1E1E2E"))

            # Track header label
            painter.setPen(QColor("#A6ADC8"))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(5, ty + 24, track_names[idx])

        # --- 1. RULER ---
        painter.setPen(QPen(QColor("#45475A"), 1))
        painter.drawLine(115, ruler_h, w - 5, ruler_h)

        step_sec = max(0.2, (self.duration / 10.0) / self.zoom_level)
        curr_t = 0.0
        while curr_t <= self.duration + 0.01:
            x = self._sec_to_x(curr_t)
            if 115 <= x <= w:
                painter.setPen(QPen(QColor("#585B70"), 1))
                painter.drawLine(int(x), ruler_h - 6, int(x), ruler_h)

                painter.setPen(QColor("#CDD6F4"))
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(int(x) - 15, ruler_h - 14, 30, 12, Qt.AlignmentFlag.AlignCenter, f"{curr_t:.1f}s")
            curr_t += step_sec

        # --- 2. TRACK 0: SPEED INTERVALS ---
        for item in self.intervals:
            x1 = max(115, self._sec_to_x(item.start_sec))
            x2 = min(w, self._sec_to_x(item.end_sec))
            if x2 > 115 and x1 < w:
                block_w = max(4, x2 - x1)

                if item.reverse:
                    bg_color = QColor("#F38BA8")
                elif item.speed < 0.9:
                    bg_color = QColor("#FAB387")
                elif item.speed > 1.1:
                    bg_color = QColor("#CBA6F7")
                else:
                    bg_color = QColor("#89B4FA")

                pen = QPen(QColor("#FFFFFF"), 2) if item == self.selected_interval else QPen(QColor("#11111B"), 1)
                painter.setPen(pen)
                painter.setBrush(QBrush(bg_color))
                rect = QRect(int(x1), track_y[0] + 2, int(block_w), track_h - 4)
                painter.drawRoundedRect(rect, 4, 4)

                painter.setPen(QColor("#11111B"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                rev_tag = " 🔄" if item.reverse else ""
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{item.speed:.2f}x{rev_tag}")

        # --- 3. TRACK 1 & 2: TEXT CLIPS ---
        for t_clip in self.text_clips:
            t_idx = 1 if getattr(t_clip, 'track_index', 0) == 0 else 2
            ty = track_y[t_idx]

            x1 = max(115, self._sec_to_x(t_clip.start_sec))
            x2 = min(w, self._sec_to_x(t_clip.end_sec))
            if x2 > 115 and x1 < w:
                block_w = max(4, x2 - x1)
                bg_color = QColor("#A6E3A1")

                pen = QPen(QColor("#FFFFFF"), 2) if t_clip == self.selected_text_clip else QPen(QColor("#11111B"), 1)
                painter.setPen(pen)
                painter.setBrush(QBrush(bg_color))
                rect = QRect(int(x1), ty + 2, int(block_w), track_h - 4)
                painter.drawRoundedRect(rect, 4, 4)

                painter.setPen(QColor("#11111B"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"💬 {t_clip.text[:10]}")

        # --- 4. TRACK 3: IMAGE CLIPS ---
        for img_clip in self.image_clips:
            ty = track_y[3]
            x1 = max(115, self._sec_to_x(img_clip.start_sec))
            x2 = min(w, self._sec_to_x(img_clip.end_sec))
            if x2 > 115 and x1 < w:
                block_w = max(4, x2 - x1)
                bg_color = QColor("#89DCEB")

                pen = QPen(QColor("#FFFFFF"), 2) if img_clip == self.selected_image_clip else QPen(QColor("#11111B"), 1)
                painter.setPen(pen)
                painter.setBrush(QBrush(bg_color))
                rect = QRect(int(x1), ty + 2, int(block_w), track_h - 4)
                painter.drawRoundedRect(rect, 4, 4)

                painter.setPen(QColor("#11111B"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                base_name = os.path.basename(img_clip.image_path)[:10] if img_clip.image_path else "Imagen"
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"🖼 {base_name}")

        # --- 5. PLAYHEAD NEEDLE ---
        px = self._sec_to_x(self.current_sec)
        if 115 <= px <= w:
            painter.setPen(QPen(QColor("#F5E0DC"), 2))
            painter.drawLine(int(px), 0, int(px), h)

            painter.setBrush(QBrush(QColor("#F5E0DC")))
            points = [
                QPoint(int(px) - 5, 0),
                QPoint(int(px) + 5, 0),
                QPoint(int(px) + 5, 8),
                QPoint(int(px), 14),
                QPoint(int(px) - 5, 8)
            ]
            painter.drawPolygon(points)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = event.position().x(), event.position().y()
            self._drag_start_x = x

            # Ruler playhead scrubbing
            if y <= 30 and x >= 115:
                self._is_dragging_playhead = True
                new_sec = self._x_to_sec(x)
                self.set_current_sec(new_sec)
                self.playhead_moved.emit(new_sec)
                return

            # Check Speed Interval Selection (Track 0)
            if 32 <= y <= 72:
                sec = self._x_to_sec(x)
                for item in self.intervals:
                    if item.start_sec <= sec <= item.end_sec:
                        self.selected_interval = item
                        self.selected_text_clip = None
                        self.selected_image_clip = None
                        self._dragged_item = item
                        self._is_dragging_block = True
                        self._drag_orig_start = item.start_sec
                        self._drag_orig_end = item.end_sec
                        self.interval_selected.emit(item)
                        self.update()
                        break

            # Check Text Clip Selection (Track 1 & 2)
            elif 77 <= y <= 162:
                sec = self._x_to_sec(x)
                for t_clip in self.text_clips:
                    if t_clip.start_sec <= sec <= t_clip.end_sec:
                        self.selected_text_clip = t_clip
                        self.selected_interval = None
                        self.selected_image_clip = None
                        self._dragged_item = t_clip
                        self._is_dragging_block = True
                        self._drag_orig_start = t_clip.start_sec
                        self._drag_orig_end = t_clip.end_sec
                        self.text_clip_selected.emit(t_clip)
                        self.update()
                        break

            # Check Image Clip Selection (Track 3)
            elif 167 <= y <= 207:
                sec = self._x_to_sec(x)
                for img_clip in self.image_clips:
                    if img_clip.start_sec <= sec <= img_clip.end_sec:
                        self.selected_image_clip = img_clip
                        self.selected_interval = None
                        self.selected_text_clip = None
                        self._dragged_item = img_clip
                        self._is_dragging_block = True
                        self._drag_orig_start = img_clip.start_sec
                        self._drag_orig_end = img_clip.end_sec
                        self.image_clip_selected.emit(img_clip)
                        self.update()
                        break

    def mouseMoveEvent(self, event: QMouseEvent):
        x = event.position().x()
        if self._is_dragging_playhead:
            new_sec = self._x_to_sec(x)
            self.set_current_sec(new_sec)
            self.playhead_moved.emit(new_sec)

        elif self._is_dragging_block and self._dragged_item:
            dx_pixels = x - self._drag_start_x
            sec_per_pixel = (self.duration / max(10, (self.width() - 130) * self.zoom_level))
            d_sec = dx_pixels * sec_per_pixel

            dur = self._drag_orig_end - self._drag_orig_start
            new_start = max(0.0, min(self.duration - dur, self._drag_orig_start + d_sec))
            new_end = new_start + dur

            self._dragged_item.start_sec = round(new_start, 2)
            self._dragged_item.end_sec = round(new_end, 2)
            self.update()
            self.timeline_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._dragged_item = None


class TimelineWidget(QWidget):
    """
    Complete Multi-Track Timeline Editor with Zoom, Clip Dragging, and Full Inspector.
    """
    playhead_moved = pyqtSignal(float)
    timeline_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Timeline Toolbar
        toolbar = QHBoxLayout()
        lbl_title = QLabel("🎬 Línea de Tiempo Multipista Profesional (Zoom & Arrastre)", self)
        lbl_title.setStyleSheet("font-weight: bold; color: #89B4FA; font-size: 13px;")
        toolbar.addWidget(lbl_title)

        toolbar.addStretch()

        self.btn_split = QPushButton("✂ Dividir Clip", self)
        self.btn_split.setStyleSheet("background-color: #F38BA8; color: #11111B; font-weight: bold;")
        self.btn_split.clicked.connect(self._on_split_clicked)
        toolbar.addWidget(self.btn_split)

        self.btn_add_text = QPushButton("💬 + Texto", self)
        self.btn_add_text.setStyleSheet("background-color: #A6E3A1; color: #11111B; font-weight: bold;")
        self.btn_add_text.clicked.connect(self._on_add_text_clicked)
        toolbar.addWidget(self.btn_add_text)

        self.btn_add_image = QPushButton("🖼 + Marca de Agua / Imagen", self)
        self.btn_add_image.setStyleSheet("background-color: #89DCEB; color: #11111B; font-weight: bold;")
        self.btn_add_image.clicked.connect(self._on_add_image_clicked)
        toolbar.addWidget(self.btn_add_image)

        layout.addLayout(toolbar)

        # 2. Timeline Canvas
        self.canvas = TimelineCanvas(self)
        self.canvas.playhead_moved.connect(self.playhead_moved.emit)
        self.canvas.interval_selected.connect(self._on_interval_selected)
        self.canvas.text_clip_selected.connect(self._on_text_clip_selected)
        self.canvas.image_clip_selected.connect(self._on_image_clip_selected)
        self.canvas.timeline_changed.connect(self.timeline_updated.emit)
        layout.addWidget(self.canvas)

        # 3. Comprehensive Inspector & Property Editor
        self.inspector_group = QGroupBox("Inspector de Propiedades y Edición del Elemento Seleccionado", self)
        self.insp_layout = QHBoxLayout(self.inspector_group)
        self.insp_layout.setContentsMargins(8, 4, 8, 4)
        self.insp_layout.setSpacing(8)

        self.lbl_insp_info = QLabel("Selecciona un elemento en la línea de tiempo para editar", self.inspector_group)
        self.lbl_insp_info.setStyleSheet("color: #BAC2DE;")
        self.insp_layout.addWidget(self.lbl_insp_info)

        # Speed Inspector Controls
        self.spn_block_speed = QDoubleSpinBox(self.inspector_group)
        self.spn_block_speed.setRange(-10.0, 10.0)
        self.spn_block_speed.setValue(1.0)
        self.spn_block_speed.setSingleStep(0.25)
        self.spn_block_speed.setSuffix(" x")
        self.spn_block_speed.valueChanged.connect(self._on_speed_spin_changed)
        self.insp_layout.addWidget(self.spn_block_speed)

        # Text Editing Controls
        self.txt_clip_content = QLineEdit(self.inspector_group)
        self.txt_clip_content.setPlaceholderText("Texto del subtítulo...")
        self.txt_clip_content.textChanged.connect(self._on_text_content_changed)
        self.txt_clip_content.setVisible(False)
        self.insp_layout.addWidget(self.txt_clip_content)

        self.spn_font_size = QSpinBox(self.inspector_group)
        self.spn_font_size.setRange(10, 200)
        self.spn_font_size.setValue(40)
        self.spn_font_size.setSuffix(" pt")
        self.spn_font_size.valueChanged.connect(self._on_font_size_changed)
        self.spn_font_size.setVisible(False)
        self.insp_layout.addWidget(self.spn_font_size)

        self.spn_start_sec = QDoubleSpinBox(self.inspector_group)
        self.spn_start_sec.setRange(0, 7200)
        self.spn_start_sec.setSingleStep(0.1)
        self.spn_start_sec.setSuffix(" s")
        self.spn_start_sec.valueChanged.connect(self._on_timing_changed)
        self.spn_start_sec.setVisible(False)
        self.insp_layout.addWidget(self.spn_start_sec)

        self.spn_end_sec = QDoubleSpinBox(self.inspector_group)
        self.spn_end_sec.setRange(0.1, 7200)
        self.spn_end_sec.setSingleStep(0.1)
        self.spn_end_sec.setSuffix(" s")
        self.spn_end_sec.valueChanged.connect(self._on_timing_changed)
        self.spn_end_sec.setVisible(False)
        self.insp_layout.addWidget(self.spn_end_sec)

        layout.addWidget(self.inspector_group)

    def set_duration(self, duration: float):
        self.canvas.set_duration(duration)

    def set_current_sec(self, sec: float):
        self.canvas.set_current_sec(sec)

    def _on_split_clicked(self):
        self.canvas.split_interval_at_current_sec()

    def _on_add_text_clicked(self):
        start = self.canvas.current_sec
        end = min(self.canvas.duration, start + 3.0)
        t_clip = TimelineTextClip(text="Nuevo Texto", start_sec=start, end_sec=end, track_index=0)
        self.canvas.text_clips.append(t_clip)
        self.canvas.selected_text_clip = t_clip
        self.canvas.update()
        self.timeline_updated.emit()
        self._on_text_clip_selected(t_clip)

    def _on_add_image_clicked(self):
        file_path, _ = QFileDialog.getSaveFileName if False else QFileDialog.getOpenFileName(
            self, "Seleccionar Imagen / Marca de Agua", "", "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if file_path:
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 5.0)
            img_clip = TimelineImageClip(image_path=file_path, start_sec=start, end_sec=end)
            self.canvas.image_clips.append(img_clip)
            self.canvas.selected_image_clip = img_clip
            self.canvas.update()
            self.timeline_updated.emit()
            self._on_image_clip_selected(img_clip)

    def _on_interval_selected(self, interval: SpeedInterval):
        self.txt_clip_content.setVisible(False)
        self.spn_font_size.setVisible(False)
        self.spn_start_sec.setVisible(False)
        self.spn_end_sec.setVisible(False)
        self.spn_block_speed.setVisible(True)

        if interval:
            rev_sign = -1.0 if interval.reverse else 1.0
            self.spn_block_speed.blockSignals(True)
            self.spn_block_speed.setValue(interval.speed * rev_sign)
            self.spn_block_speed.blockSignals(False)
            self.lbl_insp_info.setText(f"Intervalo de Velocidad [{interval.start_sec:.2f}s - {interval.end_sec:.2f}s]")

    def _on_text_clip_selected(self, t_clip: TimelineTextClip):
        self.spn_block_speed.setVisible(False)
        self.txt_clip_content.setVisible(True)
        self.spn_font_size.setVisible(True)
        self.spn_start_sec.setVisible(True)
        self.spn_end_sec.setVisible(True)

        if t_clip:
            self.txt_clip_content.blockSignals(True)
            self.txt_clip_content.setText(t_clip.text)
            self.txt_clip_content.blockSignals(False)

            self.spn_font_size.blockSignals(True)
            self.spn_font_size.setValue(t_clip.font_size)
            self.spn_font_size.blockSignals(False)

            self.spn_start_sec.blockSignals(True)
            self.spn_start_sec.setValue(t_clip.start_sec)
            self.spn_start_sec.blockSignals(False)

            self.spn_end_sec.blockSignals(True)
            self.spn_end_sec.setValue(t_clip.end_sec)
            self.spn_end_sec.blockSignals(False)

            self.lbl_insp_info.setText(f"Subtítulo en Línea de Tiempo:")

    def _on_image_clip_selected(self, img_clip: TimelineImageClip):
        self.spn_block_speed.setVisible(False)
        self.txt_clip_content.setVisible(False)
        self.spn_font_size.setVisible(False)
        self.spn_start_sec.setVisible(True)
        self.spn_end_sec.setVisible(True)

        if img_clip:
            self.spn_start_sec.blockSignals(True)
            self.spn_start_sec.setValue(img_clip.start_sec)
            self.spn_start_sec.blockSignals(False)

            self.spn_end_sec.blockSignals(True)
            self.spn_end_sec.setValue(img_clip.end_sec)
            self.spn_end_sec.blockSignals(False)

            self.lbl_insp_info.setText(f"Imagen: {os.path.basename(img_clip.image_path)}")

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

    def _on_text_content_changed(self, text: str):
        if self.canvas.selected_text_clip:
            self.canvas.selected_text_clip.text = text
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_font_size_changed(self, size: int):
        if self.canvas.selected_text_clip:
            self.canvas.selected_text_clip.font_size = size
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_timing_changed(self):
        if self.canvas.selected_text_clip:
            self.canvas.selected_text_clip.start_sec = self.spn_start_sec.value()
            self.canvas.selected_text_clip.end_sec = max(self.spn_start_sec.value() + 0.1, self.spn_end_sec.value())
            self.canvas.update()
            self.timeline_updated.emit()
        elif self.canvas.selected_image_clip:
            self.canvas.selected_image_clip.start_sec = self.spn_start_sec.value()
            self.canvas.selected_image_clip.end_sec = max(self.spn_start_sec.value() + 0.1, self.spn_end_sec.value())
            self.canvas.update()
            self.timeline_updated.emit()

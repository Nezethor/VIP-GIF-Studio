import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QGroupBox,
    QFileDialog, QColorDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QMouseEvent, QWheelEvent, QKeyEvent

from app.core.timeline import SpeedInterval, TimelineTextClip, TimelineImageClip, TimelineVideoClip


class TimelineCanvas(QWidget):
    """
    Photoshop / Premiere style visual multi-track timeline canvas with:
    - Left/Right Edge Trimming Drag Handles.
    - Drag & Move Clips across timeline.
    - Delete Key support (Supr / Delete).
    - Multi-track support: Speed, Text 1, Text 2, Images, Secondary Video overlays.
    """
    playhead_moved = pyqtSignal(float)
    interval_selected = pyqtSignal(object)
    text_clip_selected = pyqtSignal(object)
    image_clip_selected = pyqtSignal(object)
    video_clip_selected = pyqtSignal(object)
    timeline_changed = pyqtSignal()
    item_deleted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(270)
        self.setMinimumWidth(400)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.duration = 10.0
        self.current_sec = 0.0
        self.zoom_level = 1.0
        self.scroll_offset_sec = 0.0

        self.intervals = [SpeedInterval(0.0, 10.0, 1.0)]
        self.text_clips = []
        self.image_clips = []
        self.video_clips = []

        self.extra_text_tracks = 0
        self.extra_image_tracks = 0
        self.extra_video_tracks = 0

        self.selected_interval = self.intervals[0]
        self.selected_text_clip = None
        self.selected_image_clip = None
        self.selected_video_clip = None

        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._is_dragging_left_handle = False
        self._is_dragging_right_handle = False

        self._dragged_item = None
        self._drag_start_x = 0
        self._drag_orig_start = 0.0
        self._drag_orig_end = 0.0
        self._update_height()

    def _get_track_layout(self):
        tracks = [
            ("PISTA RECORTES", "recortes", 0),
            ("PISTA VELOCIDAD", "velocidad", 0),
            ("PISTA TEXTO 1", "text", 0),
            ("PISTA TEXTO 2", "text", 1),
        ]
        for i in range(self.extra_text_tracks):
            tracks.append((f"PISTA TEXTO {3 + i}", "text", 2 + i))

        tracks.append(("PISTA IMAGENES 1", "image", 0))
        for i in range(self.extra_image_tracks):
            tracks.append((f"PISTA IMAGENES {2 + i}", "image", 1 + i))

        tracks.append(("PISTA VIDEO PIP 1", "video", 0))
        for i in range(self.extra_video_tracks):
            tracks.append((f"PISTA VIDEO PIP {2 + i}", "video", 1 + i))

        return tracks

    def _update_height(self):
        tracks = self._get_track_layout()
        h = 35 + len(tracks) * 45
        self.setFixedHeight(h)

    def add_new_track(self, track_type: str):
        if track_type == 'text':
            self.extra_text_tracks += 1
        elif track_type == 'image':
            self.extra_image_tracks += 1
        elif track_type == 'video':
            self.extra_video_tracks += 1
        self._update_height()
        self.update()

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

    def delete_selected_item(self):
        """Deletes currently selected text, image, or video clip."""
        if self.selected_text_clip and self.selected_text_clip in self.text_clips:
            self.text_clips.remove(self.selected_text_clip)
            self.selected_text_clip = None
            self.timeline_changed.emit()
            self.item_deleted.emit()
            self.update()
        elif self.selected_image_clip and self.selected_image_clip in self.image_clips:
            self.image_clips.remove(self.selected_image_clip)
            self.selected_image_clip = None
            self.timeline_changed.emit()
            self.item_deleted.emit()
            self.update()
        elif self.selected_video_clip and self.selected_video_clip in self.video_clips:
            self.video_clips.remove(self.selected_video_clip)
            self.selected_video_clip = None
            self.timeline_changed.emit()
            self.item_deleted.emit()
            self.update()
        elif self.selected_interval and len(self.intervals) > 1:
            self.intervals.remove(self.selected_interval)
            self.selected_interval = self.intervals[0]
            self.timeline_changed.emit()
            self.item_deleted.emit()
            self.update()

    def keyPressEvent(self, event: QKeyEvent):
        """Delete key (Supr / Backspace) deletes selected clip."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected_item()
            event.accept()
        else:
            super().keyPressEvent(event)

    def split_interval_at_current_sec(self):
        """Splits the speed interval or secondary video clip at current_sec."""
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

        for idx, v_clip in enumerate(self.video_clips):
            if v_clip.start_sec < self.current_sec < v_clip.end_sec - 0.2:
                left = TimelineVideoClip(v_clip.video_path, v_clip.start_sec, self.current_sec, v_clip.x_ratio, v_clip.y_ratio, v_clip.width_ratio, v_clip.height_ratio, v_clip.speed, v_clip.reverse)
                right = TimelineVideoClip(v_clip.video_path, self.current_sec, v_clip.end_sec, v_clip.x_ratio, v_clip.y_ratio, v_clip.width_ratio, v_clip.height_ratio, v_clip.speed, v_clip.reverse)
                self.video_clips[idx] = left
                self.video_clips.insert(idx + 1, right)
                self.selected_video_clip = right
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
        track_h = 38
        tracks = self._get_track_layout()

        for idx, (t_name, t_type, t_subidx) in enumerate(tracks):
            ty = 32 + idx * 43
            painter.fillRect(115, ty, w - 120, track_h, QColor("#1E1E2E"))
            painter.setPen(QColor("#A6ADC8"))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(5, ty + 24, t_name)

        # 1. RULER
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

        def draw_clip_block(x1, x2, ty, bg_color, is_selected, title, item=None):
            if x2 > 115 and x1 < w:
                block_w = max(6, x2 - x1)
                pen = QPen(QColor("#FFFFFF"), 2) if is_selected else QPen(QColor("#11111B"), 1)
                painter.setPen(pen)
                painter.setBrush(QBrush(bg_color))
                rect = QRect(int(x1), ty + 2, int(block_w), track_h - 4)
                painter.drawRoundedRect(rect, 4, 4)

                y_center = ty + (track_h // 2)
                painter.setPen(QPen(QColor(17, 17, 27, 100), 1.5, Qt.PenStyle.DashLine))
                painter.drawLine(int(x1) + 4, y_center, int(x1 + block_w) - 4, y_center)

                if item and getattr(item, 'enable_keyframes', False):
                    nodes = getattr(item, 'keyframe_nodes', [])
                    for node in nodes:
                        nsec = node.get('sec', 0.0)
                        if item.start_sec - 0.05 <= nsec <= item.end_sec + 0.05:
                            nx = self._sec_to_x(nsec)
                            if 115 <= nx <= w:
                                painter.setPen(QPen(QColor("#11111B"), 1))
                                painter.setBrush(QBrush(QColor("#F5C2E7") if is_selected else QColor("#89B4FA")))
                                d_size = 5
                                diamond = [
                                    QPoint(int(nx), y_center - d_size),
                                    QPoint(int(nx) + d_size, y_center),
                                    QPoint(int(nx), y_center + d_size),
                                    QPoint(int(nx) - d_size, y_center)
                                ]
                                painter.drawPolygon(diamond)

                if is_selected:
                    painter.setBrush(QBrush(QColor("#FFFFFF")))
                    painter.drawRect(int(x1), ty + 4, 4, track_h - 8)
                    painter.drawRect(int(x1 + block_w - 4), ty + 4, 4, track_h - 8)

                painter.setPen(QColor("#11111B"))
                painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, title)

        for idx, (t_name, t_type, t_subidx) in enumerate(tracks):
            ty = 32 + idx * 43
            if t_type == "recortes":
                for c_idx, item in enumerate(self.intervals):
                    x1 = max(115, self._sec_to_x(item.start_sec))
                    x2 = min(w, self._sec_to_x(item.end_sec))
                    draw_clip_block(x1, x2, ty, QColor("#F38BA8"), item == self.selected_interval, f"✂ Clip {c_idx+1} [{item.start_sec:.1f}s - {item.end_sec:.1f}s]")
            elif t_type == "velocidad":
                for item in self.intervals:
                    x1 = max(115, self._sec_to_x(item.start_sec))
                    x2 = min(w, self._sec_to_x(item.end_sec))
                    col = QColor("#FAB387") if item.speed < 0.9 else (QColor("#CBA6F7") if item.speed > 1.1 else QColor("#89B4FA"))
                    rev_tag = " 🔄" if item.reverse else ""
                    draw_clip_block(x1, x2, ty, col, item == self.selected_interval, f"⚡ {item.speed:.2f}x{rev_tag}")
            elif t_type == "text":
                for t_clip in self.text_clips:
                    if getattr(t_clip, 'track_index', 0) == t_subidx:
                        x1 = max(115, self._sec_to_x(t_clip.start_sec))
                        x2 = min(w, self._sec_to_x(t_clip.end_sec))
                        draw_clip_block(x1, x2, ty, QColor("#A6E3A1"), t_clip == self.selected_text_clip, f"💬 {t_clip.text[:10]}", t_clip)
            elif t_type == "image":
                for img_clip in self.image_clips:
                    if getattr(img_clip, 'track_index', 0) == t_subidx:
                        x1 = max(115, self._sec_to_x(img_clip.start_sec))
                        x2 = min(w, self._sec_to_x(img_clip.end_sec))
                        bname = os.path.basename(img_clip.image_path)[:10] if img_clip.image_path else "Imagen"
                        draw_clip_block(x1, x2, ty, QColor("#89DCEB"), img_clip == self.selected_image_clip, f"🖼 {bname}", img_clip)
            elif t_type == "video":
                for v_clip in self.video_clips:
                    if getattr(v_clip, 'track_index', 0) == t_subidx:
                        x1 = max(115, self._sec_to_x(v_clip.start_sec))
                        x2 = min(w, self._sec_to_x(v_clip.end_sec))
                        bname = os.path.basename(v_clip.video_path)[:10] if v_clip.video_path else "Video PIP"
                        draw_clip_block(x1, x2, ty, QColor("#F9E2AF"), v_clip == self.selected_video_clip, f"📹 {bname}", v_clip)

        px = self._sec_to_x(self.current_sec)
        if 115 <= px <= w:
            painter.setPen(QPen(QColor("#F5E0DC"), 2))
            painter.drawLine(int(px), 0, int(px), h)
            painter.setBrush(QBrush(QColor("#F5E0DC")))
            points = [QPoint(int(px) - 5, 0), QPoint(int(px) + 5, 0), QPoint(int(px) + 5, 8), QPoint(int(px), 14), QPoint(int(px) - 5, 8)]
            painter.drawPolygon(points)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            x, y = event.position().x(), event.position().y()
            self._drag_start_x = x

            if y <= 30 and x >= 115:
                self._is_dragging_playhead = True
                new_sec = self._x_to_sec(x)
                self.set_current_sec(new_sec)
                self.playhead_moved.emit(new_sec)
                return

            def check_handle_or_body(item):
                x1 = self._sec_to_x(item.start_sec)
                x2 = self._sec_to_x(item.end_sec)
                if abs(x - x1) <= 8:
                    self._is_dragging_left_handle = True
                    self._dragged_item = item
                    self._drag_orig_start = item.start_sec
                    self._drag_orig_end = item.end_sec
                    return True
                elif abs(x - x2) <= 8:
                    self._is_dragging_right_handle = True
                    self._dragged_item = item
                    self._drag_orig_start = item.start_sec
                    self._drag_orig_end = item.end_sec
                    return True
                elif x1 <= x <= x2:
                    self._is_dragging_block = True
                    self._dragged_item = item
                    self._drag_orig_start = item.start_sec
                    self._drag_orig_end = item.end_sec
                    return True
                return False

            tracks = self._get_track_layout()
            track_idx = int((y - 32) // 43)
            if 0 <= track_idx < len(tracks):
                t_name, t_type, t_subidx = tracks[track_idx]
                if t_type in ("recortes", "velocidad"):
                    for item in self.intervals:
                        if check_handle_or_body(item):
                            self.selected_interval = item
                            self.selected_text_clip = None
                            self.selected_image_clip = None
                            self.selected_video_clip = None
                            self.interval_selected.emit(item)
                            self.update()
                            return
                elif t_type == "text":
                    for t_clip in self.text_clips:
                        if getattr(t_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(t_clip):
                                self.selected_text_clip = t_clip
                                self.selected_interval = None
                                self.selected_image_clip = None
                                self.selected_video_clip = None
                                self.text_clip_selected.emit(t_clip)
                                self.update()
                                return
                elif t_type == "image":
                    for img_clip in self.image_clips:
                        if getattr(img_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(img_clip):
                                self.selected_image_clip = img_clip
                                self.selected_interval = None
                                self.selected_text_clip = None
                                self.selected_video_clip = None
                                self.image_clip_selected.emit(img_clip)
                                self.update()
                                return
                elif t_type == "video":
                    for v_clip in self.video_clips:
                        if getattr(v_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(v_clip):
                                self.selected_video_clip = v_clip
                                self.selected_interval = None
                                self.selected_text_clip = None
                                self.selected_image_clip = None
                                self.video_clip_selected.emit(v_clip)
                                self.update()
                                return

    def mouseMoveEvent(self, event: QMouseEvent):
        x = event.position().x()
        if self._is_dragging_playhead:
            new_sec = self._x_to_sec(x)
            self.set_current_sec(new_sec)
            self.playhead_moved.emit(new_sec)

        elif self._dragged_item:
            dx_pixels = x - self._drag_start_x
            sec_per_pixel = (self.duration / max(10, (self.width() - 130) * self.zoom_level))
            d_sec = dx_pixels * sec_per_pixel

            if self._is_dragging_left_handle:
                new_start = max(0.0, min(self._drag_orig_end - 0.1, self._drag_orig_start + d_sec))
                self._dragged_item.start_sec = round(new_start, 2)
            elif self._is_dragging_right_handle:
                new_end = max(self._drag_orig_start + 0.1, min(self.duration, self._drag_orig_end + d_sec))
                self._dragged_item.end_sec = round(new_end, 2)
            elif self._is_dragging_block:
                dur = self._drag_orig_end - self._drag_orig_start
                new_start = max(0.0, min(self.duration - dur, self._drag_orig_start + d_sec))
                self._dragged_item.start_sec = round(new_start, 2)
                self._dragged_item.end_sec = round(new_start + dur, 2)

            self.update()
            self.timeline_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._is_dragging_left_handle = False
        self._is_dragging_right_handle = False
        self._dragged_item = None


class TimelineWidget(QWidget):
    """
    Multi-Track Timeline Editor with Edge Trimming Handles, Delete Key & Full Inspector.
    """
    playhead_moved = pyqtSignal(float)
    timeline_updated = pyqtSignal()
    clip_selected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        lbl_title = QLabel("🎬 Línea de Tiempo Multipista (Bordes Arrastrables & Tecla Supr)", self)
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

        self.btn_add_image = QPushButton("🖼 + Imagen / Marca", self)
        self.btn_add_image.setStyleSheet("background-color: #89DCEB; color: #11111B; font-weight: bold;")
        self.btn_add_image.clicked.connect(self._on_add_image_clicked)
        toolbar.addWidget(self.btn_add_image)

        self.btn_add_video = QPushButton("📹 + Video PIP", self)
        self.btn_add_video.setStyleSheet("background-color: #F9E2AF; color: #11111B; font-weight: bold;")
        self.btn_add_video.clicked.connect(self._on_add_video_clicked)
        toolbar.addWidget(self.btn_add_video)

        self.btn_add_track = QPushButton("➕ Agregar Nueva Pista", self)
        self.btn_add_track.setStyleSheet("background-color: #CBA6F7; color: #11111B; font-weight: bold;")
        self.btn_add_track.clicked.connect(self._on_add_track_menu)
        toolbar.addWidget(self.btn_add_track)

        self.btn_delete = QPushButton("🗑 Eliminar Seleccionado (Supr)", self)
        self.btn_delete.setStyleSheet("background-color: #45475A; color: #F38BA8; font-weight: bold;")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self.btn_delete)

        layout.addLayout(toolbar)

        # Canvas
        self.canvas = TimelineCanvas(self)
        self.canvas.playhead_moved.connect(self.playhead_moved.emit)
        self.canvas.interval_selected.connect(self._on_interval_selected)
        self.canvas.text_clip_selected.connect(self._on_text_clip_selected)
        self.canvas.image_clip_selected.connect(self._on_image_clip_selected)
        self.canvas.video_clip_selected.connect(self._on_video_clip_selected)
        self.canvas.timeline_changed.connect(self.timeline_updated.emit)
        layout.addWidget(self.canvas)

        # Inspector
        self.inspector_group = QGroupBox("Inspector de Propiedades del Clip", self)
        self.insp_layout = QHBoxLayout(self.inspector_group)
        self.insp_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_insp_info = QLabel("Selecciona un elemento para editar sus propiedades", self.inspector_group)
        self.lbl_insp_info.setStyleSheet("color: #BAC2DE;")
        self.insp_layout.addWidget(self.lbl_insp_info)

        self.spn_block_speed = QDoubleSpinBox(self.inspector_group)
        self.spn_block_speed.setRange(-10.0, 10.0)
        self.spn_block_speed.setValue(1.0)
        self.spn_block_speed.setSingleStep(0.25)
        self.spn_block_speed.setSuffix(" x")
        self.spn_block_speed.valueChanged.connect(self._on_speed_spin_changed)
        self.insp_layout.addWidget(self.spn_block_speed)

        self.txt_clip_content = QLineEdit(self.inspector_group)
        self.txt_clip_content.setPlaceholderText("Texto...")
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

        # Photoshop-style Keyframe Animation Buttons
        self.btn_kf_start = QPushButton("📍 Fijar Clave Inicio", self.inspector_group)
        self.btn_kf_start.setToolTip("Fija la posición y tamaño actuales como punto de inicio de animación (Keyframe Start)")
        self.btn_kf_start.clicked.connect(self._on_set_kf_start)
        self.btn_kf_start.setVisible(False)
        self.insp_layout.addWidget(self.btn_kf_start)

        self.btn_kf_end = QPushButton("🏁 Fijar Clave Fin", self.inspector_group)
        self.btn_kf_end.setToolTip("Fija la posición y tamaño actuales como punto final de animación (Keyframe End)")
        self.btn_kf_end.clicked.connect(self._on_set_kf_end)
        self.btn_kf_end.setVisible(False)
        self.insp_layout.addWidget(self.btn_kf_end)

        self.btn_add_kf_node = QPushButton("◆ Añadir Nodo Clave", self.inspector_group)
        self.btn_add_kf_node.setToolTip("Añade un nodo fotograma clave rombo ◆ en el tiempo actual para animaciones avanzadas de múltiples puntos")
        self.btn_add_kf_node.setStyleSheet("background-color: #F5C2E7; color: #11111B; font-weight: bold;")
        self.btn_add_kf_node.clicked.connect(self._on_add_kf_node)
        self.btn_add_kf_node.setVisible(False)
        self.insp_layout.addWidget(self.btn_add_kf_node)

        layout.addWidget(self.inspector_group)

    def _on_add_kf_node(self):
        sel = self.canvas.selected_text_clip or self.canvas.selected_image_clip or self.canvas.selected_video_clip
        if sel:
            sec = self.canvas.current_sec
            sel.add_keyframe_node(sec)
            self.lbl_insp_info.setText(f"◆ Nodo Clave Alojado a los {sec:.2f}s")
            self.canvas.update()
            self.timeline_updated.emit()

    def set_duration(self, duration: float):
        self.canvas.set_duration(duration)

    def set_current_sec(self, sec: float):
        self.canvas.set_current_sec(sec)

    def _on_split_clicked(self):
        self.canvas.split_interval_at_current_sec()

    def _on_delete_clicked(self):
        self.canvas.delete_selected_item()

    def _on_add_text_clicked(self):
        start = self.canvas.current_sec
        end = min(self.canvas.duration, start + 3.0)
        t_clip = TimelineTextClip(text="Nuevo Texto", start_sec=start, end_sec=end)
        self.canvas.text_clips.append(t_clip)
        self.canvas.selected_text_clip = t_clip
        self.canvas.update()
        self.timeline_updated.emit()
        self._on_text_clip_selected(t_clip)

    def _on_add_image_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
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

    def _on_add_video_clicked(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Video Secundario (PIP)", "", "Videos (*.mp4 *.avi *.mov *.webm *.mkv)"
        )
        if file_path:
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 5.0)
            v_clip = TimelineVideoClip(video_path=file_path, start_sec=start, end_sec=end)
            self.canvas.video_clips.append(v_clip)
            self.canvas.selected_video_clip = v_clip
            self.canvas.update()
            self.timeline_updated.emit()
            self._on_video_clip_selected(v_clip)

    def _on_add_track_menu(self):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; font-weight: bold; }
            QMenu::item:selected { background-color: #89B4FA; color: #11111B; }
        """)
        
        act_text = menu.addAction("💬 + Nueva Pista de Texto Independiente")
        act_img = menu.addAction("🖼 + Nueva Pista de Imagen / Marca Independiente")
        act_vid = menu.addAction("📹 + Nueva Pista de Vídeo PIP Independiente")
        
        chosen = menu.exec(self.btn_add_track.mapToGlobal(QPoint(0, self.btn_add_track.height())))
        if chosen == act_text:
            self.canvas.add_new_track('text')
            new_idx = 1 + self.canvas.extra_text_tracks
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 3.0)
            t_clip = TimelineTextClip(text=f"Texto Pista {new_idx+1}", start_sec=start, end_sec=end, track_index=new_idx)
            self.canvas.text_clips.append(t_clip)
            self.canvas.selected_text_clip = t_clip
            self.canvas.update()
            self.timeline_updated.emit()
            self._on_text_clip_selected(t_clip)
        elif chosen == act_img:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar Imagen para Nueva Pista", "", "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)"
            )
            if file_path:
                self.canvas.add_new_track('image')
                new_idx = self.canvas.extra_image_tracks
                start = self.canvas.current_sec
                end = min(self.canvas.duration, start + 5.0)
                img_clip = TimelineImageClip(image_path=file_path, start_sec=start, end_sec=end, track_index=new_idx)
                self.canvas.image_clips.append(img_clip)
                self.canvas.selected_image_clip = img_clip
                self.canvas.update()
                self.timeline_updated.emit()
                self._on_image_clip_selected(img_clip)
        elif chosen == act_vid:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Seleccionar Video PIP para Nueva Pista", "", "Videos (*.mp4 *.avi *.mov *.webm *.mkv)"
            )
            if file_path:
                self.canvas.add_new_track('video')
                new_idx = self.canvas.extra_video_tracks
                start = self.canvas.current_sec
                end = min(self.canvas.duration, start + 5.0)
                v_clip = TimelineVideoClip(video_path=file_path, start_sec=start, end_sec=end, track_index=new_idx)
                self.canvas.video_clips.append(v_clip)
                self.canvas.selected_video_clip = v_clip
                self.canvas.update()
                self.timeline_updated.emit()
                self._on_video_clip_selected(v_clip)

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

    def _on_set_kf_start(self):
        sel = self.canvas.selected_text_clip or self.canvas.selected_image_clip or self.canvas.selected_video_clip
        if sel:
            sel.enable_keyframes = True
            sel.start_x_ratio = getattr(sel, 'x_ratio', 0.5)
            sel.start_y_ratio = getattr(sel, 'y_ratio', 0.5)
            sel.start_width_ratio = getattr(sel, 'width_ratio', 0.3)
            sel.start_height_ratio = getattr(sel, 'height_ratio', 0.3)
            sel.start_font_size = getattr(sel, 'font_size', 40)

            if not hasattr(sel, 'keyframe_nodes') or sel.keyframe_nodes is None:
                sel.keyframe_nodes = []
            
            sel.keyframe_nodes = [n for n in sel.keyframe_nodes if abs(n.get('sec', -1) - sel.start_sec) > 0.05]
            sel.keyframe_nodes.append({'sec': sel.start_sec, 'x': sel.start_x_ratio, 'y': sel.start_y_ratio})
            sel.keyframe_nodes.sort(key=lambda n: n.get('sec', 0.0))

            self.lbl_insp_info.setText("📍 Clave de Inicio Guardada (Keyframe Start)")
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_set_kf_end(self):
        sel = self.canvas.selected_text_clip or self.canvas.selected_image_clip or self.canvas.selected_video_clip
        if sel:
            sel.enable_keyframes = True
            sel.end_x_ratio = getattr(sel, 'x_ratio', 0.5)
            sel.end_y_ratio = getattr(sel, 'y_ratio', 0.5)
            sel.end_width_ratio = getattr(sel, 'width_ratio', 0.3)
            sel.end_height_ratio = getattr(sel, 'height_ratio', 0.3)
            sel.end_font_size = getattr(sel, 'font_size', 40)

            if not hasattr(sel, 'keyframe_nodes') or sel.keyframe_nodes is None:
                sel.keyframe_nodes = []

            sel.keyframe_nodes = [n for n in sel.keyframe_nodes if abs(n.get('sec', -1) - sel.end_sec) > 0.05]
            sel.keyframe_nodes.append({'sec': sel.end_sec, 'x': sel.end_x_ratio, 'y': sel.end_y_ratio})
            sel.keyframe_nodes.sort(key=lambda n: n.get('sec', 0.0))

            self.lbl_insp_info.setText("🏁 Clave de Fin Guardada (Keyframe End)")
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_text_clip_selected(self, t_clip: TimelineTextClip):
        self.canvas.selected_text_clip = t_clip
        self.canvas.selected_image_clip = None
        self.canvas.selected_video_clip = None
        self.clip_selected.emit(t_clip)
        self.spn_block_speed.setVisible(False)
        self.txt_clip_content.setVisible(True)
        self.spn_font_size.setVisible(True)
        self.spn_start_sec.setVisible(True)
        self.spn_end_sec.setVisible(True)
        self.btn_kf_start.setVisible(True)
        self.btn_kf_end.setVisible(True)
        self.btn_add_kf_node.setVisible(True)

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

            self.lbl_insp_info.setText("Subtítulo en Línea de Tiempo:")

    def _on_image_clip_selected(self, img_clip: TimelineImageClip):
        self.canvas.selected_image_clip = img_clip
        self.canvas.selected_text_clip = None
        self.canvas.selected_video_clip = None
        self.clip_selected.emit(img_clip)
        self.spn_block_speed.setVisible(False)
        self.txt_clip_content.setVisible(False)
        self.spn_font_size.setVisible(False)
        self.spn_start_sec.setVisible(True)
        self.spn_end_sec.setVisible(True)
        self.btn_kf_start.setVisible(True)
        self.btn_kf_end.setVisible(True)
        self.btn_add_kf_node.setVisible(True)

        if img_clip:
            self.spn_start_sec.blockSignals(True)
            self.spn_start_sec.setValue(img_clip.start_sec)
            self.spn_start_sec.blockSignals(False)

            self.spn_end_sec.blockSignals(True)
            self.spn_end_sec.setValue(img_clip.end_sec)
            self.spn_end_sec.blockSignals(False)

            self.lbl_insp_info.setText(f"Imagen: {os.path.basename(img_clip.image_path)}")

    def _on_video_clip_selected(self, v_clip: TimelineVideoClip):
        self.canvas.selected_video_clip = v_clip
        self.canvas.selected_text_clip = None
        self.canvas.selected_image_clip = None
        self.clip_selected.emit(v_clip)
        self.txt_clip_content.setVisible(False)
        self.spn_font_size.setVisible(False)
        self.spn_start_sec.setVisible(True)
        self.spn_end_sec.setVisible(True)
        self.spn_block_speed.setVisible(True)
        self.btn_kf_start.setVisible(True)
        self.btn_kf_end.setVisible(True)
        self.btn_add_kf_node.setVisible(True)

        if v_clip:
            rev_sign = -1.0 if v_clip.reverse else 1.0
            self.spn_block_speed.blockSignals(True)
            self.spn_block_speed.setValue(v_clip.speed * rev_sign)
            self.spn_block_speed.blockSignals(False)

            self.spn_start_sec.blockSignals(True)
            self.spn_start_sec.setValue(v_clip.start_sec)
            self.spn_start_sec.blockSignals(False)

            self.spn_end_sec.blockSignals(True)
            self.spn_end_sec.setValue(v_clip.end_sec)
            self.spn_end_sec.blockSignals(False)

            self.lbl_insp_info.setText(f"Video PIP: {os.path.basename(v_clip.video_path)}")

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
        elif self.canvas.selected_video_clip:
            if val < 0:
                self.canvas.selected_video_clip.speed = abs(val)
                self.canvas.selected_video_clip.reverse = True
            else:
                self.canvas.selected_video_clip.speed = max(0.1, val)
                self.canvas.selected_video_clip.reverse = False
            self.canvas.update()
            self.timeline_updated.emit()

    def _on_text_content_changed(self, text: str):
        if self.canvas.selected_text_clip:
            self.canvas.selected_text_clip.text = text
            self.canvas.update()
            if not hasattr(self, '_text_timer'):
                from PyQt6.QtCore import QTimer
                self._text_timer = QTimer(self)
                self._text_timer.setSingleShot(True)
                self._text_timer.timeout.connect(self.timeline_updated.emit)
            self._text_timer.start(150)

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
        elif self.canvas.selected_video_clip:
            self.canvas.selected_video_clip.start_sec = self.spn_start_sec.value()
            self.canvas.selected_video_clip.end_sec = max(self.spn_start_sec.value() + 0.1, self.spn_end_sec.value())
            self.canvas.update()
            self.timeline_updated.emit()


from PyQt6.QtWidgets import QDialog, QFormLayout, QDialogButtonBox

class ClipInspectorDialog(QDialog):
    """Diálogo emergente para editar los atributos de cualquier elemento seleccionado con doble clic (Texto, Imagen, Vídeo PIP)."""
    def __init__(self, clip, parent=None):
        super().__init__(parent)
        self.clip = clip
        self.setWindowTitle(f"Editar Atributos - {self._get_title()}")
        self.setFixedWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #1E1E2E; color: #CDD6F4; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: #BAC2DE; font-size: 13px; font-weight: bold; }
            QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 6px; }
            QPushButton { background-color: #89B4FA; color: #11111B; font-weight: bold; border-radius: 4px; padding: 8px 14px; }
            QPushButton:hover { background-color: #B4BEFE; }
        """)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        # Tiempos de inicio y fin
        self.spn_start = QDoubleSpinBox(self)
        self.spn_start.setRange(0.0, 3600.0)
        self.spn_start.setValue(clip.start_sec)
        self.spn_start.setSuffix(" s")

        self.spn_end = QDoubleSpinBox(self)
        self.spn_end.setRange(0.1, 3600.0)
        self.spn_end.setValue(clip.end_sec)
        self.spn_end.setSuffix(" s")

        form.addRow("Tiempo Inicio:", self.spn_start)
        form.addRow("Tiempo Fin:", self.spn_end)

        if isinstance(clip, TimelineTextClip):
            self.txt_content = QLineEdit(clip.text, self)
            self.spn_font_size = QSpinBox(self)
            self.spn_font_size.setRange(10, 250)
            self.spn_font_size.setValue(clip.font_size)

            self.color_fill = getattr(clip, 'color', '#FFFFFF')
            self.color_border = getattr(clip, 'border_color', '#000000')

            self.btn_fill = QPushButton(f"Relleno: {self.color_fill}", self)
            self.btn_fill.clicked.connect(self._pick_fill_color)

            self.btn_border = QPushButton(f"Borde: {self.color_border}", self)
            self.btn_border.clicked.connect(self._pick_border_color)

            form.addRow("Texto:", self.txt_content)
            form.addRow("Tamaño Letra (pt):", self.spn_font_size)
            form.addRow("Color Relleno:", self.btn_fill)
            form.addRow("Color Borde:", self.btn_border)

        elif isinstance(clip, (TimelineImageClip, TimelineVideoClip)):
            self.spn_width_pct = QSpinBox(self)
            self.spn_width_pct.setRange(5, 100)
            self.spn_width_pct.setValue(int(clip.width_ratio * 100))
            self.spn_width_pct.setSuffix(" %")

            self.spn_height_pct = QSpinBox(self)
            self.spn_height_pct.setRange(5, 100)
            self.spn_height_pct.setValue(int(clip.height_ratio * 100))
            self.spn_height_pct.setSuffix(" %")

            form.addRow("Ancho (% Pantalla):", self.spn_width_pct)
            form.addRow("Alto (% Pantalla):", self.spn_height_pct)

            if isinstance(clip, TimelineVideoClip):
                self.spn_speed = QDoubleSpinBox(self)
                self.spn_speed.setRange(0.1, 10.0)
                self.spn_speed.setValue(clip.speed)
                form.addRow("Velocidad de Vídeo:", self.spn_speed)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _get_title(self):
        if isinstance(self.clip, TimelineTextClip): return "Texto / Subtítulo"
        elif isinstance(self.clip, TimelineImageClip): return f"Imagen ({os.path.basename(self.clip.image_path)})"
        elif isinstance(self.clip, TimelineVideoClip): return f"Vídeo PIP ({os.path.basename(self.clip.video_path)})"
        return "Elemento"

    def _pick_fill_color(self):
        col = QColorDialog.getColor(QColor(self.color_fill), self, "Seleccionar Color de Relleno")
        if col.isValid():
            self.color_fill = col.name()
            self.btn_fill.setText(f"Relleno: {self.color_fill}")

    def _pick_border_color(self):
        col = QColorDialog.getColor(QColor(self.color_border), self, "Seleccionar Color de Borde")
        if col.isValid():
            self.color_border = col.name()
            self.btn_border.setText(f"Borde: {self.color_border}")

    def _save(self):
        self.clip.start_sec = self.spn_start.value()
        self.clip.end_sec = max(self.clip.start_sec + 0.1, self.spn_end.value())

        if isinstance(self.clip, TimelineTextClip):
            self.clip.text = self.txt_content.text()
            self.clip.font_size = self.spn_font_size.value()
            self.clip.color = self.color_fill
            self.clip.border_color = self.color_border
        elif isinstance(self.clip, (TimelineImageClip, TimelineVideoClip)):
            self.clip.width_ratio = self.spn_width_pct.value() / 100.0
            self.clip.height_ratio = self.spn_height_pct.value() / 100.0
            if isinstance(self.clip, TimelineVideoClip):
                self.clip.speed = self.spn_speed.value()

        self.accept()

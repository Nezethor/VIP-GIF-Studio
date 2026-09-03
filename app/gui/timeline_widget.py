import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDoubleSpinBox, QSpinBox, QLineEdit, QComboBox, QGroupBox,
    QFileDialog, QColorDialog, QMessageBox, QScrollArea, QFrame,
    QTabWidget, QSlider, QCheckBox, QMenu, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QMouseEvent, QWheelEvent, QKeyEvent, QPixmap, QImage

from app.core.timeline import (
    SpeedInterval, TimelineTextClip, TimelineImageClip, TimelineVideoClip,
    TimelineShapeClip, TimelineAudioClip, TransitionClip, AdjustmentLayer, LayerGroup
)
from app.core.photoshop_fx import PhotoshopFX


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
        self.shape_clips = []           # NEW: vector shapes
        self.audio_clips = []           # NEW: independent audio tracks
        self.transition_clips = []      # NEW: transitions between clips
        self.adjustment_layers = []     # NEW: global adjustment layers
        self.layer_groups = []          # NEW: layer groups / smart objects

        self.extra_text_tracks = 0
        self.extra_image_tracks = 0
        self.extra_video_tracks = 0
        self.extra_audio_tracks = 0

        self.selected_interval = self.intervals[0]
        self.selected_text_clip = None
        self.selected_image_clip = None
        self.selected_video_clip = None
        self.selected_shape_clip = None
        self.selected_audio_clip = None
        self.selected_adjustment = None
        self.selected_transition = None

        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._is_dragging_left_handle = False
        self._is_dragging_right_handle = False
        self._is_slip_mode = False

        self._dragged_item = None
        self._drag_start_x = 0
        self._drag_orig_start = 0.0
        self._drag_orig_end = 0.0
        self._active_snap_x = None
        self._snap_threshold_pixels = 12

        # Waveform pixmap cache: audio_clip.id -> QPixmap
        self._waveform_cache = {}

        self._update_height()

    def _get_track_layout(self):
        tracks = [
            ("✂ RECORTES", "recortes", 0),
            ("⚡ VELOCIDAD", "velocidad", 0),
            ("💬 TEXTO 1", "text", 0),
            ("💬 TEXTO 2", "text", 1),
        ]
        for i in range(self.extra_text_tracks):
            tracks.append((f"💬 TEXTO {3 + i}", "text", 2 + i))

        tracks.append(("🖼 IMAGENES 1", "image", 0))
        for i in range(self.extra_image_tracks):
            tracks.append((f"🖼 IMAGENES {2 + i}", "image", 1 + i))

        tracks.append(("📹 VIDEO PIP 1", "video", 0))
        for i in range(self.extra_video_tracks):
            tracks.append((f"📹 VIDEO PIP {2 + i}", "video", 1 + i))

        # NEW: Shape tracks
        if self.shape_clips:
            shape_indices = sorted(set(getattr(c, 'track_index', 0) for c in self.shape_clips))
            for si in shape_indices:
                tracks.append((f"🔷 FORMAS {si + 1}", "shape", si))

        # NEW: Adjustment Layer tracks
        if self.adjustment_layers:
            adj_indices = sorted(set(getattr(c, 'track_index', 0) for c in self.adjustment_layers))
            for ai in adj_indices:
                tracks.append((f"🎛 AJUSTE {ai + 1}", "adjustment", ai))

        # NEW: Transition tracks
        if self.transition_clips:
            tracks.append(("🎞 TRANSICIONES", "transition", 0))

        # NEW: Audio tracks
        tracks.append(("🎵 AUDIO 1", "audio", 0))
        for i in range(self.extra_audio_tracks):
            tracks.append((f"🎵 AUDIO {2 + i}", "audio", 1 + i))

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
        elif track_type == 'audio':
            self.extra_audio_tracks += 1
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
        """Deletes currently selected text, image, video, shape, audio, adjustment, or transition clip."""
        def _del(lst, sel_attr):
            item = getattr(self, sel_attr, None)
            if item and item in lst:
                lst.remove(item)
                setattr(self, sel_attr, None)
                self.timeline_changed.emit()
                self.item_deleted.emit()
                self.update()
                return True
            return False

        if _del(self.text_clips, 'selected_text_clip'): return
        if _del(self.image_clips, 'selected_image_clip'): return
        if _del(self.video_clips, 'selected_video_clip'): return
        if _del(self.shape_clips, 'selected_shape_clip'): return
        if _del(self.audio_clips, 'selected_audio_clip'): return
        if _del(self.adjustment_layers, 'selected_adjustment'): return
        if _del(self.transition_clips, 'selected_transition'): return
        if self.selected_interval and len(self.intervals) > 1:
            self.intervals.remove(self.selected_interval)
            self.selected_interval = self.intervals[0]
            self.timeline_changed.emit()
            self.item_deleted.emit()
            self.update()

    def keyPressEvent(self, event: QKeyEvent):
        """Delete key (Supr / Backspace) deletes clip, Ctrl+D duplicates clip."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected_item()
            event.accept()
        elif event.key() == Qt.Key.Key_D and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.duplicate_selected_item()
            event.accept()
        else:
            super().keyPressEvent(event)

    def duplicate_selected_item(self):
        """Duplicates the currently selected clip or interval (Ctrl+D)."""
        if self.selected_text_clip:
            orig = self.selected_text_clip
            dur = orig.duration
            new_start = min(self.duration - 0.5, orig.end_sec)
            new_end = min(self.duration, new_start + dur)
            clone = TimelineTextClip(
                text=orig.text + " (Copia)",
                start_sec=new_start,
                end_sec=new_end,
                x_ratio=min(1.0, orig.x_ratio + 0.05),
                y_ratio=min(1.0, orig.y_ratio + 0.05),
                font_size=orig.font_size,
                color=orig.color,
                border_color=orig.border_color,
                track_index=getattr(orig, 'track_index', 0),
                layer_z=getattr(orig, 'layer_z', 10)
            )
            for attr in ('opacity', 'fade_in_sec', 'fade_out_sec', 'blend_mode', 'filter_type', 'brightness', 'contrast', 'saturation', 'blur_radius', 'drop_shadow', 'rotation', 'easing_curve'):
                if hasattr(orig, attr):
                    setattr(clone, attr, getattr(orig, attr))
            self.text_clips.append(clone)
            self.selected_text_clip = clone
            self.timeline_changed.emit()
            self.text_clip_selected.emit(clone)
            self.update()
            return clone

        elif self.selected_image_clip:
            orig = self.selected_image_clip
            dur = orig.duration
            new_start = min(self.duration - 0.5, orig.end_sec)
            new_end = min(self.duration, new_start + dur)
            clone = TimelineImageClip(
                image_path=orig.image_path,
                start_sec=new_start,
                end_sec=new_end,
                x_ratio=min(1.0, orig.x_ratio + 0.05),
                y_ratio=min(1.0, orig.y_ratio + 0.05),
                width_ratio=orig.width_ratio,
                height_ratio=orig.height_ratio,
                track_index=getattr(orig, 'track_index', 0),
                layer_z=getattr(orig, 'layer_z', 5)
            )
            for attr in ('opacity', 'fade_in_sec', 'fade_out_sec', 'blend_mode', 'filter_type', 'brightness', 'contrast', 'saturation', 'blur_radius', 'drop_shadow', 'rotation', 'border_radius', 'border_width', 'border_color', 'easing_curve'):
                if hasattr(orig, attr):
                    setattr(clone, attr, getattr(orig, attr))
            self.image_clips.append(clone)
            self.selected_image_clip = clone
            self.timeline_changed.emit()
            self.image_clip_selected.emit(clone)
            self.update()
            return clone

        elif self.selected_video_clip:
            orig = self.selected_video_clip
            dur = orig.duration
            new_start = min(self.duration - 0.5, orig.end_sec)
            new_end = min(self.duration, new_start + dur)
            clone = TimelineVideoClip(
                video_path=orig.video_path,
                start_sec=new_start,
                end_sec=new_end,
                x_ratio=min(1.0, orig.x_ratio + 0.05),
                y_ratio=min(1.0, orig.y_ratio + 0.05),
                width_ratio=orig.width_ratio,
                height_ratio=orig.height_ratio,
                speed=orig.speed,
                reverse=orig.reverse,
                track_index=getattr(orig, 'track_index', 0),
                layer_z=getattr(orig, 'layer_z', 2)
            )
            for attr in ('opacity', 'fade_in_sec', 'fade_out_sec', 'blend_mode', 'filter_type', 'brightness', 'contrast', 'saturation', 'blur_radius', 'drop_shadow', 'rotation', 'border_radius', 'border_width', 'border_color', 'easing_curve'):
                if hasattr(orig, attr):
                    setattr(clone, attr, getattr(orig, attr))
            self.video_clips.append(clone)
            self.selected_video_clip = clone
            self.timeline_changed.emit()
            self.video_clip_selected.emit(clone)
            self.update()
            return clone


    def split_interval_at_current_sec(self):
        """Splits the speed interval, video clip, image clip, or shape clip at current_sec."""
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

        for idx, shp in enumerate(self.shape_clips):
            if shp.start_sec < self.current_sec < shp.end_sec - 0.2:
                left = TimelineShapeClip(shp.shape_type, shp.start_sec, self.current_sec,
                                         shp.x_ratio, shp.y_ratio, shp.width_ratio, shp.height_ratio,
                                         shp.fill_color, shp.stroke_color, shp.stroke_width,
                                         shp.track_index, shp.layer_z)
                right = TimelineShapeClip(shp.shape_type, self.current_sec, shp.end_sec,
                                          shp.x_ratio, shp.y_ratio, shp.width_ratio, shp.height_ratio,
                                          shp.fill_color, shp.stroke_color, shp.stroke_width,
                                          shp.track_index, shp.layer_z)
                self.shape_clips[idx] = left
                self.shape_clips.insert(idx + 1, right)
                self.selected_shape_clip = right
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

            # --- NEW CLIP TYPES ---
            elif t_type == "shape":
                for shp in self.shape_clips:
                    if getattr(shp, 'track_index', 0) == t_subidx:
                        x1 = max(115, self._sec_to_x(shp.start_sec))
                        x2 = min(w, self._sec_to_x(shp.end_sec))
                        # Use fill color as block color
                        try:
                            shp_col = QColor(getattr(shp, 'fill_color', '#CBA6F7'))
                        except Exception:
                            shp_col = QColor("#CBA6F7")
                        draw_clip_block(x1, x2, ty, shp_col, shp == self.selected_shape_clip,
                                        f"🔷 {getattr(shp, 'shape_type', 'Shape')[:8]}", shp)

            elif t_type == "adjustment":
                for adj in self.adjustment_layers:
                    if getattr(adj, 'track_index', 0) == t_subidx:
                        x1 = max(115, self._sec_to_x(adj.start_sec))
                        x2 = min(w, self._sec_to_x(adj.end_sec))
                        draw_clip_block(x1, x2, ty, QColor("#94E2D5"), adj == self.selected_adjustment,
                                        f"🎛 {getattr(adj, 'adjustment_type', 'Ajuste')[:12]}")

            elif t_type == "transition":
                for trans in self.transition_clips:
                    tx1 = max(115, self._sec_to_x(trans.start_sec))
                    tx2 = min(w, self._sec_to_x(trans.end_sec))
                    draw_clip_block(tx1, tx2, ty, QColor("#F2CDCD"), trans == self.selected_transition,
                                    f"🎞 {getattr(trans, 'transition_type', 'Trans')[:8]}")

            elif t_type == "audio":
                for ac in self.audio_clips:
                    if getattr(ac, 'track_index', 0) == t_subidx:
                        ax1 = max(115, self._sec_to_x(ac.start_sec))
                        ax2 = min(w, self._sec_to_x(ac.end_sec))
                        muted = getattr(ac, 'muted', False)
                        a_col = QColor("#45475A") if muted else QColor("#B4BEFE")
                        bname = os.path.basename(getattr(ac, 'audio_path', 'Audio'))[:12]
                        # Draw block base
                        if ax2 > 115 and ax1 < w:
                            block_w = max(6, ax2 - ax1)
                            is_sel = ac == self.selected_audio_clip
                            pen = QPen(QColor("#FFFFFF"), 2) if is_sel else QPen(QColor("#11111B"), 1)
                            painter.setPen(pen)
                            painter.setBrush(QBrush(a_col))
                            rect = QRect(int(ax1), ty + 2, int(block_w), 34)
                            painter.drawRoundedRect(rect, 4, 4)

                            # Draw waveform if cached
                            cache_key = ac.id
                            if cache_key in self._waveform_cache:
                                wf_pix = self._waveform_cache[cache_key]
                                painter.drawPixmap(int(ax1) + 2, ty + 3,
                                                   min(int(block_w) - 4, wf_pix.width()), 30, wf_pix)
                            else:
                                # Request async waveform render
                                self._request_waveform(ac)

                            painter.setPen(QColor("#11111B"))
                            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                            mute_tag = " 🔇" if muted else ""
                            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"🎵 {bname}{mute_tag}")

        px = self._sec_to_x(self.current_sec)
        if 115 <= px <= w:
            painter.setPen(QPen(QColor("#F5E0DC"), 2))
            painter.drawLine(int(px), 0, int(px), h)
            painter.setBrush(QBrush(QColor("#F5E0DC")))
            points = [QPoint(int(px) - 5, 0), QPoint(int(px) + 5, 0), QPoint(int(px) + 5, 8), QPoint(int(px), 14), QPoint(int(px) - 5, 8)]
            painter.drawPolygon(points)

        # Draw Photoshop Magnetic Snap Guide Line & Badge (Línea de Imán inteligente)
        if getattr(self, '_active_snap_x', None) is not None:
            snap_x = int(self._active_snap_x)
            if 115 <= snap_x <= w:
                painter.setPen(QPen(QColor("#F9E2AF"), 2, Qt.PenStyle.DashLine))
                painter.drawLine(snap_x, 0, snap_x, h)
                badge_rect = QRect(snap_x - 22, 2, 44, 16)
                painter.setPen(QColor("#11111B"))
                painter.setBrush(QBrush(QColor("#F9E2AF")))
                painter.drawRoundedRect(badge_rect, 4, 4)
                painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "🧲 IMÁN")

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

                def _deselect_all():
                    self.selected_interval = None
                    self.selected_text_clip = None
                    self.selected_image_clip = None
                    self.selected_video_clip = None
                    self.selected_shape_clip = None
                    self.selected_audio_clip = None
                    self.selected_adjustment = None
                    self.selected_transition = None

                if t_type in ("recortes", "velocidad"):
                    for item in self.intervals:
                        if check_handle_or_body(item):
                            _deselect_all()
                            self.selected_interval = item
                            self.interval_selected.emit(item)
                            self.update()
                            return
                elif t_type == "text":
                    for t_clip in self.text_clips:
                        if getattr(t_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(t_clip):
                                _deselect_all()
                                self.selected_text_clip = t_clip
                                self.text_clip_selected.emit(t_clip)
                                self.update()
                                return
                elif t_type == "image":
                    for img_clip in self.image_clips:
                        if getattr(img_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(img_clip):
                                _deselect_all()
                                self.selected_image_clip = img_clip
                                self.image_clip_selected.emit(img_clip)
                                self.update()
                                return
                elif t_type == "video":
                    for v_clip in self.video_clips:
                        if getattr(v_clip, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(v_clip):
                                _deselect_all()
                                self.selected_video_clip = v_clip
                                self.video_clip_selected.emit(v_clip)
                                self.update()
                                return
                elif t_type == "shape":
                    for shp in self.shape_clips:
                        if getattr(shp, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(shp):
                                _deselect_all()
                                self.selected_shape_clip = shp
                                self.timeline_changed.emit()
                                self.update()
                                return
                elif t_type == "audio":
                    for ac in self.audio_clips:
                        if getattr(ac, 'track_index', 0) == t_subidx:
                            x1 = self._sec_to_x(ac.start_sec)
                            x2 = self._sec_to_x(ac.end_sec)
                            if x1 <= x <= x2:
                                _deselect_all()
                                self.selected_audio_clip = ac
                                self.timeline_changed.emit()
                                self.update()
                                return
                elif t_type == "adjustment":
                    for adj in self.adjustment_layers:
                        if getattr(adj, 'track_index', 0) == t_subidx:
                            if check_handle_or_body(adj):
                                _deselect_all()
                                self.selected_adjustment = adj
                                self.timeline_changed.emit()
                                self.update()
                                return
                elif t_type == "transition":
                    for trans in self.transition_clips:
                        x1 = self._sec_to_x(trans.start_sec)
                        x2 = self._sec_to_x(trans.end_sec)
                        if x1 <= x <= x2:
                            _deselect_all()
                            self.selected_transition = trans
                            self.timeline_changed.emit()
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
            threshold_sec = self._snap_threshold_pixels * sec_per_pixel

            # Collect magnetic snap candidates across timeline
            snap_candidates = [0.0, self.duration, self.current_sec]
            for it in self.intervals:
                if it != self._dragged_item:
                    snap_candidates.extend([it.start_sec, it.end_sec])
            for tc in self.text_clips:
                if tc != self._dragged_item:
                    snap_candidates.extend([tc.start_sec, tc.end_sec])
            for ic in self.image_clips:
                if ic != self._dragged_item:
                    snap_candidates.extend([ic.start_sec, ic.end_sec])
            for vc in self.video_clips:
                if vc != self._dragged_item:
                    snap_candidates.extend([vc.start_sec, vc.end_sec])
            for sc in self.shape_clips:
                if sc != self._dragged_item:
                    snap_candidates.extend([sc.start_sec, sc.end_sec])
            for ac in self.audio_clips:
                if ac != self._dragged_item:
                    snap_candidates.extend([ac.start_sec, ac.end_sec])

            def check_snap(target_val):
                best_dist = threshold_sec
                best_cand = None
                for cand in snap_candidates:
                    dist = abs(target_val - cand)
                    if dist < best_dist:
                        best_dist = dist
                        best_cand = cand
                return best_cand

            snapped_pos = None

            if self._is_dragging_left_handle:
                raw_start = max(0.0, min(self._drag_orig_end - 0.1, self._drag_orig_start + d_sec))
                cand = check_snap(raw_start)
                if cand is not None and cand < self._drag_orig_end - 0.05:
                    new_start = cand
                    snapped_pos = cand
                else:
                    new_start = raw_start
                self._dragged_item.start_sec = round(new_start, 2)

            elif self._is_dragging_right_handle:
                raw_end = max(self._drag_orig_start + 0.1, min(self.duration, self._drag_orig_end + d_sec))
                cand = check_snap(raw_end)
                if cand is not None and cand > self._drag_orig_start + 0.05:
                    new_end = cand
                    snapped_pos = cand
                else:
                    new_end = raw_end
                self._dragged_item.end_sec = round(new_end, 2)

            elif self._is_dragging_block:
                dur = self._drag_orig_end - self._drag_orig_start
                raw_start = max(0.0, min(self.duration - dur, self._drag_orig_start + d_sec))
                raw_end = raw_start + dur

                cand_start = check_snap(raw_start)
                cand_end = check_snap(raw_end)

                if cand_start is not None:
                    new_start = max(0.0, min(self.duration - dur, cand_start))
                    snapped_pos = new_start
                elif cand_end is not None:
                    new_start = max(0.0, min(self.duration - dur, cand_end - dur))
                    snapped_pos = cand_end
                else:
                    new_start = raw_start

                self._dragged_item.start_sec = round(new_start, 2)
                self._dragged_item.end_sec = round(new_start + dur, 2)

            if snapped_pos is not None:
                self._active_snap_x = self._sec_to_x(snapped_pos)
            else:
                self._active_snap_x = None

            self.update()
            self.timeline_changed.emit()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._is_dragging_playhead = False
        self._is_dragging_block = False
        self._is_dragging_left_handle = False
        self._is_dragging_right_handle = False
        self._dragged_item = None
        self._active_snap_x = None
        self.update()

    def _request_waveform(self, audio_clip):
        """Requests an async waveform render for the given audio clip, storing result in cache."""
        cache_key = audio_clip.id
        if cache_key in self._waveform_cache:
            return
        # Mark as pending to avoid multiple requests
        self._waveform_cache[cache_key] = None
        try:
            from app.core.audio_engine import WaveformRenderer
            renderer = WaveformRenderer(width=200, height=30, wave_color="#89B4FA", bg_color="#181825")
            def _on_done(img):
                try:
                    from PIL.ImageQt import ImageQt
                    qt_img = ImageQt(img.convert("RGBA"))
                    pix = QPixmap.fromImage(QImage(qt_img))
                    self._waveform_cache[cache_key] = pix
                    self.update()
                except Exception:
                    pass
            renderer.render_async(
                audio_clip.audio_path,
                start_sec=getattr(audio_clip, 'source_trim_start', 0.0),
                duration=audio_clip.duration,
                callback=_on_done)
        except Exception:
            pass


class TimelineWidget(QWidget):
    """
    Multi-Track Timeline Editor with Edge Trimming Handles, Delete Key & Full Inspector.
    Supports: Clip Trim, Split, Slip, Speed, Keyframes, Transitions, Groups, Audio, Shapes, Adjustment Layers.
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
        lbl_title = QLabel("🎬 Línea de Tiempo Multipista — VIP GIF Studio v3.0", self)
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

        self.btn_add_image = QPushButton("🖼 + Imagen", self)
        self.btn_add_image.setStyleSheet("background-color: #89DCEB; color: #11111B; font-weight: bold;")
        self.btn_add_image.clicked.connect(self._on_add_image_clicked)
        toolbar.addWidget(self.btn_add_image)

        self.btn_add_video = QPushButton("📹 + Video PIP", self)
        self.btn_add_video.setStyleSheet("background-color: #F9E2AF; color: #11111B; font-weight: bold;")
        self.btn_add_video.clicked.connect(self._on_add_video_clicked)
        toolbar.addWidget(self.btn_add_video)

        # NEW: Shape button
        self.btn_add_shape = QPushButton("🔷 + Forma", self)
        self.btn_add_shape.setStyleSheet("background-color: #CBA6F7; color: #11111B; font-weight: bold;")
        self.btn_add_shape.clicked.connect(self._on_add_shape_clicked)
        toolbar.addWidget(self.btn_add_shape)

        # NEW: Audio Track button
        self.btn_add_audio = QPushButton("🎵 + Audio", self)
        self.btn_add_audio.setStyleSheet("background-color: #B4BEFE; color: #11111B; font-weight: bold;")
        self.btn_add_audio.clicked.connect(self._on_add_audio_clicked)
        toolbar.addWidget(self.btn_add_audio)

        # NEW: Transition button
        self.btn_add_transition = QPushButton("🎞 Transición", self)
        self.btn_add_transition.setStyleSheet("background-color: #F2CDCD; color: #11111B; font-weight: bold;")
        self.btn_add_transition.clicked.connect(self._on_add_transition_clicked)
        toolbar.addWidget(self.btn_add_transition)

        # NEW: Adjustment Layer button
        self.btn_add_adj = QPushButton("🎛 Ajuste", self)
        self.btn_add_adj.setStyleSheet("background-color: #94E2D5; color: #11111B; font-weight: bold;")
        self.btn_add_adj.clicked.connect(self._on_add_adjustment_clicked)
        toolbar.addWidget(self.btn_add_adj)

        self.btn_add_track = QPushButton("➕ Nueva Pista", self)
        self.btn_add_track.setStyleSheet("background-color: #CBA6F7; color: #11111B; font-weight: bold;")
        self.btn_add_track.clicked.connect(self._on_add_track_menu)
        toolbar.addWidget(self.btn_add_track)

        self.btn_duplicate = QPushButton("📄 Duplicar (Ctrl+D)", self)
        self.btn_duplicate.setStyleSheet("background-color: #89DCEB; color: #11111B; font-weight: bold;")
        self.btn_duplicate.clicked.connect(self._on_duplicate_clicked)
        toolbar.addWidget(self.btn_duplicate)

        self.btn_delete = QPushButton("🗑 Eliminar (Supr)", self)
        self.btn_delete.setStyleSheet("background-color: #45475A; color: #F38BA8; font-weight: bold;")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        toolbar.addWidget(self.btn_delete)

        layout.addLayout(toolbar)

        # Canvas inside styled ScrollArea (Permite infinitas pistas con scroll vertical fluido)
        self.canvas = TimelineCanvas(self)
        self.canvas.playhead_moved.connect(self.playhead_moved.emit)
        self.canvas.interval_selected.connect(self._on_interval_selected)
        self.canvas.text_clip_selected.connect(self._on_text_clip_selected)
        self.canvas.image_clip_selected.connect(self._on_image_clip_selected)
        self.canvas.video_clip_selected.connect(self._on_video_clip_selected)
        self.canvas.timeline_changed.connect(self.timeline_updated.emit)

        self.canvas_scroll = QScrollArea(self)
        self.canvas_scroll.setWidget(self.canvas)
        self.canvas_scroll.setWidgetResizable(True)
        self.canvas_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.canvas_scroll.setStyleSheet("""
            QScrollArea { background-color: #181825; border: 1px solid #313244; border-radius: 6px; }
            QScrollBar:vertical {
                border: none; background: #181825; width: 10px; margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #45475A; min-height: 25px; border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #89B4FA;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                border: none; background: #181825; height: 10px; margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #45475A; min-width: 25px; border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #89B4FA;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        layout.addWidget(self.canvas_scroll)

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

    def _on_add_shape_clicked(self):
        """Opens shape type menu and adds a new TimelineShapeClip to the timeline."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; font-weight: bold; } QMenu::item:selected { background-color: #CBA6F7; color: #11111B; }")
        for shape_name in TimelineShapeClip.SHAPES:
            menu.addAction(f"🔷 {shape_name}")
        chosen = menu.exec(self.btn_add_shape.mapToGlobal(QPoint(0, self.btn_add_shape.height())))
        if chosen:
            shape_type = chosen.text().replace("🔷 ", "")
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 3.0)
            shp = TimelineShapeClip(shape_type=shape_type, start_sec=start, end_sec=end, track_index=0)
            self.canvas.shape_clips.append(shp)
            self.canvas.selected_shape_clip = shp
            self.canvas._update_height()
            self.canvas.update()
            self.timeline_updated.emit()
            self.lbl_insp_info.setText(f"🔷 Forma '{shape_type}' añadida [{start:.1f}s - {end:.1f}s]")

    def _on_add_audio_clicked(self):
        """Opens file dialog to select audio and adds TimelineAudioClip to the timeline."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Archivo de Audio", "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.opus)")
        if file_path:
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 10.0)
            track_idx = self.canvas.extra_audio_tracks
            ac = TimelineAudioClip(audio_path=file_path, start_sec=start, end_sec=end, track_index=track_idx)
            self.canvas.audio_clips.append(ac)
            self.canvas.selected_audio_clip = ac
            self.canvas._update_height()
            self.canvas.update()
            self.timeline_updated.emit()
            import os
            self.lbl_insp_info.setText(f"🎵 Audio '{os.path.basename(file_path)}' añadido [{start:.1f}s - {end:.1f}s]")

    def _on_add_transition_clicked(self):
        """Opens transition type menu and adds a TransitionClip at the current playhead."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; font-weight: bold; } QMenu::item:selected { background-color: #F2CDCD; color: #11111B; }")
        for t_name in TransitionClip.TYPES:
            menu.addAction(f"🎞 {t_name}")
        chosen = menu.exec(self.btn_add_transition.mapToGlobal(QPoint(0, self.btn_add_transition.height())))
        if chosen:
            t_type = chosen.text().replace("🎞 ", "")
            at_sec = self.canvas.current_sec
            trans = TransitionClip(transition_type=t_type, at_sec=at_sec, duration=0.5)
            self.canvas.transition_clips.append(trans)
            self.canvas.selected_transition = trans
            self.canvas._update_height()
            self.canvas.update()
            self.timeline_updated.emit()
            self.lbl_insp_info.setText(f"🎞 Transición '{t_type}' en {at_sec:.2f}s (0.5s duración)")

    def _on_add_adjustment_clicked(self):
        """Opens adjustment type menu and adds an AdjustmentLayer to the timeline."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; font-weight: bold; } QMenu::item:selected { background-color: #94E2D5; color: #11111B; }")
        for a_name in AdjustmentLayer.ADJUSTMENT_TYPES:
            menu.addAction(f"🎛 {a_name}")
        chosen = menu.exec(self.btn_add_adj.mapToGlobal(QPoint(0, self.btn_add_adj.height())))
        if chosen:
            a_type = chosen.text().replace("🎛 ", "")
            start = self.canvas.current_sec
            end = min(self.canvas.duration, start + 5.0)
            adj = AdjustmentLayer(adjustment_type=a_type, start_sec=start, end_sec=end, track_index=0)
            self.canvas.adjustment_layers.append(adj)
            self.canvas.selected_adjustment = adj
            self.canvas._update_height()
            self.canvas.update()
            self.timeline_updated.emit()
            self.lbl_insp_info.setText(f"🎛 Capa de Ajuste '{a_type}' [{start:.1f}s - {end:.1f}s]")

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

    def _on_duplicate_clicked(self):
        self.canvas.duplicate_selected_item()

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
            
            node_start = {
                'sec': sel.start_sec,
                'x_ratio': sel.start_x_ratio,
                'y_ratio': sel.start_y_ratio,
                'width_ratio': sel.start_width_ratio,
                'height_ratio': sel.start_height_ratio,
                'font_size': sel.start_font_size
            }
            sel.keyframe_nodes = [n for n in sel.keyframe_nodes if abs(n.get('sec', -1) - sel.start_sec) > 0.05]
            sel.keyframe_nodes.append(node_start)
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

            node_end = {
                'sec': sel.end_sec,
                'x_ratio': sel.end_x_ratio,
                'y_ratio': sel.end_y_ratio,
                'width_ratio': sel.end_width_ratio,
                'height_ratio': sel.end_height_ratio,
                'font_size': sel.end_font_size
            }
            sel.keyframe_nodes = [n for n in sel.keyframe_nodes if abs(n.get('sec', -1) - sel.end_sec) > 0.05]
            sel.keyframe_nodes.append(node_end)
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
    """Diálogo avanzado estilo Photoshop con pestañas de Transformación y Efectos Visuales FX."""
    def __init__(self, clip, parent=None):
        super().__init__(parent)
        self.clip = clip
        self.setWindowTitle(f"Inspector de Clip - {self._get_title()}")
        self.setFixedWidth(480)
        self.setStyleSheet("""
            QDialog { background-color: #1E1E2E; color: #CDD6F4; font-family: 'Segoe UI', sans-serif; }
            QLabel { color: #BAC2DE; font-size: 12px; font-weight: bold; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background-color: #313244; color: #CDD6F4; border: 1px solid #45475A; border-radius: 4px; padding: 5px; }
            QTabWidget::pane { border: 1px solid #45475A; background-color: #181825; border-radius: 6px; padding: 10px; }
            QTabBar::tab { background-color: #313244; color: #BAC2DE; padding: 8px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #181825; color: #89B4FA; border: 1px solid #45475A; border-bottom: none; }
            QPushButton { background-color: #89B4FA; color: #11111B; font-weight: bold; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #B4BEFE; }
            QCheckBox { color: #CDD6F4; font-weight: bold; spacing: 8px; }
            QSlider::groove:horizontal { height: 6px; background: #313244; border-radius: 3px; }
            QSlider::handle:horizontal { background: #89B4FA; width: 14px; margin: -4px 0; border-radius: 7px; }
        """)

        main_layout = QVBoxLayout(self)

        tabs = QTabWidget(self)

        # TAB 1: 📐 Transformación & Tiempo
        tab_trans = QWidget()
        form_trans = QFormLayout(tab_trans)
        form_trans.setSpacing(10)

        self.spn_start = QDoubleSpinBox(tab_trans)
        self.spn_start.setRange(0.0, 7200.0)
        self.spn_start.setValue(clip.start_sec)
        self.spn_start.setSuffix(" s")

        self.spn_end = QDoubleSpinBox(tab_trans)
        self.spn_end.setRange(0.1, 7200.0)
        self.spn_end.setValue(clip.end_sec)
        self.spn_end.setSuffix(" s")

        form_trans.addRow("Tiempo Inicio:", self.spn_start)
        form_trans.addRow("Tiempo Fin:", self.spn_end)

        if isinstance(clip, TimelineTextClip):
            self.txt_content = QLineEdit(clip.text, tab_trans)
            self.spn_font_size = QSpinBox(tab_trans)
            self.spn_font_size.setRange(10, 250)
            self.spn_font_size.setValue(clip.font_size)

            self.color_fill = getattr(clip, 'color', '#FFFFFF')
            self.color_border = getattr(clip, 'border_color', '#000000')

            self.btn_fill = QPushButton(f"Relleno: {self.color_fill}", tab_trans)
            self.btn_fill.clicked.connect(self._pick_fill_color)

            self.btn_border = QPushButton(f"Borde: {self.color_border}", tab_trans)
            self.btn_border.clicked.connect(self._pick_border_color)

            form_trans.addRow("Texto:", self.txt_content)
            form_trans.addRow("Tamaño Letra (pt):", self.spn_font_size)
            form_trans.addRow("Color Relleno:", self.btn_fill)
            form_trans.addRow("Color Borde:", self.btn_border)

        elif isinstance(clip, (TimelineImageClip, TimelineVideoClip)):
            self.spn_width_pct = QSpinBox(tab_trans)
            self.spn_width_pct.setRange(5, 100)
            self.spn_width_pct.setValue(int(clip.width_ratio * 100))
            self.spn_width_pct.setSuffix(" %")

            self.spn_height_pct = QSpinBox(tab_trans)
            self.spn_height_pct.setRange(5, 100)
            self.spn_height_pct.setValue(int(clip.height_ratio * 100))
            self.spn_height_pct.setSuffix(" %")

            form_trans.addRow("Ancho (% Pantalla):", self.spn_width_pct)
            form_trans.addRow("Alto (% Pantalla):", self.spn_height_pct)

            if isinstance(clip, TimelineVideoClip):
                self.spn_speed = QDoubleSpinBox(tab_trans)
                self.spn_speed.setRange(0.1, 10.0)
                self.spn_speed.setValue(clip.speed)
                form_trans.addRow("Velocidad de Vídeo:", self.spn_speed)

        self.spn_rotation = QDoubleSpinBox(tab_trans)
        self.spn_rotation.setRange(-360.0, 360.0)
        self.spn_rotation.setSingleStep(5.0)
        self.spn_rotation.setSuffix("°")
        self.spn_rotation.setValue(getattr(clip, 'rotation', 0.0))
        form_trans.addRow("Rotación Angular:", self.spn_rotation)

        self.combo_easing = QComboBox(tab_trans)
        self.combo_easing.addItems(["Linear", "Suave Entrada (Ease In)", "Suave Salida (Ease Out)", "Suave Ambos (Ease In-Out)", "Rebote (Bounce)"])
        cur_easing = getattr(clip, 'easing_curve', 'Linear')
        e_idx = self.combo_easing.findText(cur_easing, Qt.MatchFlag.MatchContains)
        if e_idx >= 0: self.combo_easing.setCurrentIndex(e_idx)
        form_trans.addRow("Curva de Animación:", self.combo_easing)

        tabs.addTab(tab_trans, "📐 Transformación & Tiempo")

        # TAB 2: 🎨 Photoshop FX & Estilos
        tab_fx = QWidget()
        form_fx = QFormLayout(tab_fx)
        form_fx.setSpacing(10)

        # Blend Mode
        self.combo_blend = QComboBox(tab_fx)
        self.combo_blend.addItems(PhotoshopFX.BLEND_MODES)
        cur_blend = getattr(clip, 'blend_mode', 'Normal')
        idx = self.combo_blend.findText(cur_blend, Qt.MatchFlag.MatchContains)
        if idx >= 0: self.combo_blend.setCurrentIndex(idx)
        form_fx.addRow("Modo de Fusión (Blend):", self.combo_blend)

        # Opacity Slider + SpinBox
        op_hlayout = QHBoxLayout()
        self.slider_opacity = QSlider(Qt.Orientation.Horizontal, tab_fx)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(int(getattr(clip, 'opacity', 1.0) * 100))
        self.spn_opacity = QSpinBox(tab_fx)
        self.spn_opacity.setRange(0, 100)
        self.spn_opacity.setValue(self.slider_opacity.value())
        self.spn_opacity.setSuffix(" %")
        self.slider_opacity.valueChanged.connect(self.spn_opacity.setValue)
        self.spn_opacity.valueChanged.connect(self.slider_opacity.setValue)
        op_hlayout.addWidget(self.slider_opacity)
        op_hlayout.addWidget(self.spn_opacity)
        form_fx.addRow("Opacidad General:", op_hlayout)

        # Fade In & Fade Out
        self.spn_fade_in = QDoubleSpinBox(tab_fx)
        self.spn_fade_in.setRange(0.0, 5.0)
        self.spn_fade_in.setSingleStep(0.2)
        self.spn_fade_in.setSuffix(" s")
        self.spn_fade_in.setValue(getattr(clip, 'fade_in_sec', 0.0))

        self.spn_fade_out = QDoubleSpinBox(tab_fx)
        self.spn_fade_out.setRange(0.0, 5.0)
        self.spn_fade_out.setSingleStep(0.2)
        self.spn_fade_out.setSuffix(" s")
        self.spn_fade_out.setValue(getattr(clip, 'fade_out_sec', 0.0))

        fade_hlayout = QHBoxLayout()
        fade_hlayout.addWidget(QLabel("Entrada:", tab_fx))
        fade_hlayout.addWidget(self.spn_fade_in)
        fade_hlayout.addWidget(QLabel("Salida:", tab_fx))
        fade_hlayout.addWidget(self.spn_fade_out)
        form_fx.addRow("Desvanecimiento Suave:", fade_hlayout)

        # Filters / LUTs
        self.combo_filter = QComboBox(tab_fx)
        self.combo_filter.addItems(PhotoshopFX.FILTERS)
        cur_filter = getattr(clip, 'filter_type', 'Normal')
        f_idx = self.combo_filter.findText(cur_filter, Qt.MatchFlag.MatchContains)
        if f_idx >= 0: self.combo_filter.setCurrentIndex(f_idx)
        form_fx.addRow("Filtro de Capa / Tono:", self.combo_filter)

        # Brightness & Contrast
        self.spn_brightness = QDoubleSpinBox(tab_fx)
        self.spn_brightness.setRange(0.2, 2.5)
        self.spn_brightness.setSingleStep(0.1)
        self.spn_brightness.setValue(getattr(clip, 'brightness', 1.0))

        self.spn_contrast = QDoubleSpinBox(tab_fx)
        self.spn_contrast.setRange(0.2, 2.5)
        self.spn_contrast.setSingleStep(0.1)
        self.spn_contrast.setValue(getattr(clip, 'contrast', 1.0))

        bc_hlayout = QHBoxLayout()
        bc_hlayout.addWidget(QLabel("Brillo:", tab_fx))
        bc_hlayout.addWidget(self.spn_brightness)
        bc_hlayout.addWidget(QLabel("Contraste:", tab_fx))
        bc_hlayout.addWidget(self.spn_contrast)
        form_fx.addRow("Ajuste Tonal:", bc_hlayout)

        # Saturation & Blur
        self.spn_saturation = QDoubleSpinBox(tab_fx)
        self.spn_saturation.setRange(0.0, 3.0)
        self.spn_saturation.setSingleStep(0.1)
        self.spn_saturation.setValue(getattr(clip, 'saturation', 1.0))

        self.spn_blur = QDoubleSpinBox(tab_fx)
        self.spn_blur.setRange(0.0, 15.0)
        self.spn_blur.setSingleStep(0.5)
        self.spn_blur.setSuffix(" px")
        self.spn_blur.setValue(getattr(clip, 'blur_radius', 0.0))

        sat_hlayout = QHBoxLayout()
        sat_hlayout.addWidget(QLabel("Saturación:", tab_fx))
        sat_hlayout.addWidget(self.spn_saturation)
        sat_hlayout.addWidget(QLabel("Desenfoque:", tab_fx))
        sat_hlayout.addWidget(self.spn_blur)
        form_fx.addRow("Color y Enfoque:", sat_hlayout)

        # Rounded Corners & Border for Images and PIP Video
        if isinstance(clip, (TimelineImageClip, TimelineVideoClip)):
            self.spn_radius = QSpinBox(tab_fx)
            self.spn_radius.setRange(0, 80)
            self.spn_radius.setValue(getattr(clip, 'border_radius', 0))
            self.spn_radius.setSuffix(" px")

            self.spn_border_w = QSpinBox(tab_fx)
            self.spn_border_w.setRange(0, 30)
            self.spn_border_w.setValue(getattr(clip, 'border_width', 0))
            self.spn_border_w.setSuffix(" px")

            self.frame_border_col = getattr(clip, 'border_color', '#FFFFFF')
            self.btn_frame_border = QPushButton(f"Color: {self.frame_border_col}", tab_fx)
            self.btn_frame_border.clicked.connect(self._pick_frame_border_color)

            corner_hlayout = QHBoxLayout()
            corner_hlayout.addWidget(QLabel("Radio:", tab_fx))
            corner_hlayout.addWidget(self.spn_radius)
            corner_hlayout.addWidget(QLabel("Borde:", tab_fx))
            corner_hlayout.addWidget(self.spn_border_w)
            corner_hlayout.addWidget(self.btn_frame_border)
            form_fx.addRow("Marco y Esquinas:", corner_hlayout)

        # Drop Shadow
        self.chk_shadow = QCheckBox("Activar Sombra Paralela (Drop Shadow)", tab_fx)
        self.chk_shadow.setChecked(getattr(clip, 'drop_shadow', isinstance(clip, TimelineTextClip)))
        form_fx.addRow("Estilo de Capa:", self.chk_shadow)

        tabs.addTab(tab_fx, "🎨 Photoshop FX & Estilos")

        main_layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

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

    def _pick_frame_border_color(self):
        col = QColorDialog.getColor(QColor(getattr(self, 'frame_border_col', '#FFFFFF')), self, "Seleccionar Color de Marco")
        if col.isValid():
            self.frame_border_col = col.name()
            self.btn_frame_border.setText(f"Color: {self.frame_border_col}")

    def _save(self):
        self.clip.start_sec = self.spn_start.value()
        self.clip.end_sec = max(self.clip.start_sec + 0.1, self.spn_end.value())
        self.clip.rotation = self.spn_rotation.value()
        self.clip.easing_curve = self.combo_easing.currentText()

        # Save Tab 1 (Transformation)
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
            if hasattr(self, 'spn_radius'):
                self.clip.border_radius = self.spn_radius.value()
                self.clip.border_width = self.spn_border_w.value()
                self.clip.border_color = getattr(self, 'frame_border_col', '#FFFFFF')

        # Save Tab 2 (Photoshop FX)
        self.clip.blend_mode = self.combo_blend.currentText()
        self.clip.opacity = self.spn_opacity.value() / 100.0
        self.clip.fade_in_sec = self.spn_fade_in.value()
        self.clip.fade_out_sec = self.spn_fade_out.value()
        self.clip.filter_type = self.combo_filter.currentText()
        self.clip.brightness = self.spn_brightness.value()
        self.clip.contrast = self.spn_contrast.value()
        self.clip.saturation = self.spn_saturation.value()
        self.clip.blur_radius = self.spn_blur.value()
        self.clip.drop_shadow = self.chk_shadow.isChecked()

        self.accept()

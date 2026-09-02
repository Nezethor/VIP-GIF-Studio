from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QDoubleSpinBox
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PIL import Image, ImageDraw, ImageFont
import cv2
import os
import numpy as np

from app.core.video_info import VideoInfo
from app.gui.range_slider import DualRangeSlider

class VideoPreviewWidget(QWidget):
    """
    Video Preview and Timeline Trimmer control widget with subtitle rendering.
    """
    positionChanged = pyqtSignal(float)
    trimChanged = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_info = None
        self.cap = None
        self.current_sec = 0.0
        self.is_playing = False
        self.start_sec = 0.0
        self.end_sec = 0.0
        self.subtitles = []

        self._init_ui()

        # Playback timer (~30 fps preview refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._next_frame)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Video Display Frame Container
        self.display_frame = QFrame(self)
        self.display_frame.setStyleSheet("""
            QFrame {
                background-color: #0F0F17;
                border: 2px solid #313244;
                border-radius: 12px;
            }
        """)
        display_layout = QVBoxLayout(self.display_frame)
        display_layout.setContentsMargins(5, 5, 5, 5)

        self.video_label = QLabel("Arrastra o selecciona un video para comenzar", self.display_frame)
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("""
            QLabel {
                color: #585B70;
                font-size: 15px;
                font-weight: 500;
            }
        """)
        self.video_label.setMinimumSize(480, 270)
        display_layout.addWidget(self.video_label)
        layout.addWidget(self.display_frame, stretch=1)

        # Timeline Trimmer Slider
        self.range_slider = DualRangeSlider(self)
        self.range_slider.rangeChanged.connect(self._on_trim_changed)
        self.range_slider.handleMoved.connect(self.seek_to)
        layout.addWidget(self.range_slider)

        # Precise Time SpinBoxes (Inicio / Fin exactos)
        time_inputs_layout = QHBoxLayout()
        time_inputs_layout.setSpacing(10)

        lbl_start_input = QLabel("✂ Recorte Inicio (seg):", self)
        self.spn_start_time = QDoubleSpinBox(self)
        self.spn_start_time.setDecimals(2)
        self.spn_start_time.setSingleStep(0.10)
        self.spn_start_time.setRange(0.00, 9999.00)
        self.spn_start_time.setFixedWidth(110)
        self.spn_start_time.valueChanged.connect(self._on_spin_start_changed)

        lbl_end_input = QLabel("✂ Recorte Fin (seg):", self)
        self.spn_end_time = QDoubleSpinBox(self)
        self.spn_end_time.setDecimals(2)
        self.spn_end_time.setSingleStep(0.10)
        self.spn_end_time.setRange(0.00, 9999.00)
        self.spn_end_time.setFixedWidth(110)
        self.spn_end_time.valueChanged.connect(self._on_spin_end_changed)

        time_inputs_layout.addWidget(lbl_start_input)
        time_inputs_layout.addWidget(self.spn_start_time)
        time_inputs_layout.addSpacing(20)
        time_inputs_layout.addWidget(lbl_end_input)
        time_inputs_layout.addWidget(self.spn_end_time)
        time_inputs_layout.addStretch()

        layout.addLayout(time_inputs_layout)

        # Control Bar (Play, Timecode, Loop indicators)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        self.btn_play = QPushButton("▶ Reproducir", self)
        self.btn_play.setFixedWidth(120)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)

        self.btn_set_start = QPushButton("⚑ Inicio (A)", self)
        self.btn_set_start.setEnabled(False)
        self.btn_set_start.clicked.connect(self._set_current_as_start)
        controls_layout.addWidget(self.btn_set_start)

        self.btn_set_end = QPushButton("⚑ Fin (B)", self)
        self.btn_set_end.setEnabled(False)
        self.btn_set_end.clicked.connect(self._set_current_as_end)
        controls_layout.addWidget(self.btn_set_end)

        controls_layout.addStretch()

        self.lbl_timecode = QLabel("00:00.00 / 00:00.00", self)
        self.lbl_timecode.setObjectName("timeLabel")
        controls_layout.addWidget(self.lbl_timecode)

        layout.addLayout(controls_layout)

    def load_video(self, file_path: str):
        self.stop()
        if self.cap:
            self.cap.release()

        self.video_info = VideoInfo(file_path)
        if not self.video_info.is_valid:
            self.video_label.setText("⚠ No se pudo cargar el formato de video seleccionado.")
            self.btn_play.setEnabled(False)
            self.btn_set_start.setEnabled(False)
            self.btn_set_end.setEnabled(False)
            return False

        self.cap = cv2.VideoCapture(file_path)
        self.start_sec = 0.0
        self.end_sec = self.video_info.duration
        self.current_sec = 0.0

        self.range_slider.setRange(0.0, self.video_info.duration)
        self.range_slider.setValues(0.0, self.video_info.duration)

        self.spn_start_time.blockSignals(True)
        self.spn_end_time.blockSignals(True)
        self.spn_start_time.setRange(0.0, self.video_info.duration)
        self.spn_end_time.setRange(0.0, self.video_info.duration)
        self.spn_start_time.setValue(0.0)
        self.spn_end_time.setValue(self.video_info.duration)
        self.spn_start_time.blockSignals(False)
        self.spn_end_time.blockSignals(False)

        self.btn_play.setEnabled(True)
        self.btn_set_start.setEnabled(True)
        self.btn_set_end.setEnabled(True)

        self.seek_to(0.0)
        return True

    def set_subtitles(self, subtitles: list):
        self.subtitles = subtitles
        if self.video_info and self.cap:
            self.seek_to(self.current_sec)

    def seek_to(self, sec: float):
        if not self.video_info or not self.cap:
            return

        sec = max(0.0, min(sec, self.video_info.duration))
        self.current_sec = sec

        frame_num = int(sec * self.video_info.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.cap.read()
        if ret:
            self._render_frame(frame)

        self.range_slider.setCurrentPos(sec)
        self._update_timecode_label()
        self.positionChanged.emit(sec)

    def toggle_play(self):
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.video_info or not self.cap:
            return
        if self.current_sec >= self.end_sec:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)
        self.is_playing = True
        self.btn_play.setText("⏸ Pausa")
        self.timer.start()

    def pause(self):
        self.is_playing = False
        self.btn_play.setText("▶ Reproducir")
        self.timer.stop()

    def stop(self):
        self.pause()
        self.current_sec = self.start_sec
        self.range_slider.setCurrentPos(self.current_sec)

    def _update_preview(self):
        self.seek_to(self.current_sec)

    def _next_frame(self):
        if not self.is_playing or not self.video_info or not self.cap:
            return

        intervals = getattr(self, 'speed_intervals', [])
        if intervals:
            in_any = any(inv.start_sec <= self.current_sec <= inv.end_sec for inv in intervals)
            if not in_any:
                next_invs = [inv for inv in intervals if inv.start_sec > self.current_sec]
                if next_invs:
                    next_start = min(inv.start_sec for inv in next_invs)
                    self.seek_to(next_start)
                    return
                else:
                    first_start = min(inv.start_sec for inv in intervals)
                    self.seek_to(first_start)
                    return

        self.current_sec += 0.033
        if self.current_sec >= self.end_sec:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)
            return

        ret, frame = self.cap.read()
        if ret:
            self._render_frame(frame)
            self.range_slider.setCurrentPos(self.current_sec)
            self._update_timecode_label()
            self.positionChanged.emit(self.current_sec)
        else:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)

    def _get_font(self, size: int):
        try:
            return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", int(size))
        except Exception:
            return ImageFont.load_default()

    def _render_frame(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        # Draw active Picture-in-Picture (PIP) video overlays onto frame
        active_vids = [v for v in getattr(self, 'video_clips', []) if v.is_visible_at(self.current_sec)]
        if active_vids:
            for v_clip in active_vids:
                if not hasattr(self, '_pip_caps'): self._pip_caps = {}
                if v_clip.video_path not in self._pip_caps: self._pip_caps[v_clip.video_path] = cv2.VideoCapture(v_clip.video_path)
                if v_clip.video_path in self._pip_caps:
                    try:
                        pip_cap = self._pip_caps[v_clip.video_path]
                        rel_t = self.current_sec - v_clip.start_sec
                        fps = pip_cap.get(cv2.CAP_PROP_FPS) or 30.0
                        total_frames = int(pip_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
                        v_dur_sec = float(total_frames) / fps if fps > 0 else 1.0

                        # Infinite loop wrapping when PIP video is stretched
                        loop_t = rel_t % v_dur_sec if v_dur_sec > 0 else 0.0
                        target_frame = int(loop_t * fps) % max(1, total_frames)
                        pip_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        ret, pip_frame = pip_cap.read()
                        if not ret:
                            pip_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, pip_frame = pip_cap.read()

                        if ret:
                            pip_rgb = cv2.cvtColor(pip_frame, cv2.COLOR_BGR2RGB)
                            cur_x, cur_y, cur_w, cur_h, _ = v_clip.get_transform_at(self.current_sec) if hasattr(v_clip, 'get_transform_at') else (v_clip.x_ratio, v_clip.y_ratio, v_clip.width_ratio, v_clip.height_ratio, 40)
                            target_w = max(30, int(w * cur_w))
                            target_h = max(30, int(h * cur_h))
                            pip_resized = cv2.resize(pip_rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                            pos_x = int((w - target_w) * cur_x)
                            pos_y = int((h - target_h) * cur_y)

                            px1, py1 = max(0, pos_x), max(0, pos_y)
                            px2, py2 = min(w, pos_x + target_w), min(h, pos_y + target_h)

                            frame_rgb[py1:py2, px1:px2] = pip_resized[0:(py2-py1), 0:(px2-px1)]
                    except Exception:
                        pass

        # Draw active image overlays onto frame using PIL
        active_imgs = [img for img in getattr(self, 'image_clips', []) if img.is_visible_at(self.current_sec)]
        if active_imgs:
            pil_img = Image.fromarray(frame_rgb)
            for img_clip in active_imgs:
                if os.path.exists(img_clip.image_path):
                    try:
                        overlay_img = Image.open(img_clip.image_path).convert("RGBA")
                        cur_x, cur_y, cur_w, cur_h, _ = img_clip.get_transform_at(self.current_sec) if hasattr(img_clip, 'get_transform_at') else (img_clip.x_ratio, img_clip.y_ratio, img_clip.width_ratio, img_clip.height_ratio, 40)
                        target_w = max(20, int(w * cur_w))
                        target_h = max(20, int(h * cur_h))
                        overlay_img = overlay_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                        pos_x = int((w - target_w) * cur_x)
                        pos_y = int((h - target_h) * cur_y)

                        pil_img.paste(overlay_img, (pos_x, pos_y), overlay_img)
                    except Exception:
                        pass
            frame_rgb = np.array(pil_img.convert("RGB"))

        # Draw active subtitles onto frame using PIL
        active_subs = [s for s in self.subtitles if s.is_visible_at(self.current_sec)]
        pil_img = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_img)

        for sub in active_subs:
            cur_x, cur_y, _, _, cur_fs = sub.get_transform_at(self.current_sec) if hasattr(sub, 'get_transform_at') else (sub.x_ratio, sub.y_ratio, 0.3, 0.3, sub.font_size)
            ref_h = 720.0
            scaled_size = max(10, int(cur_fs * max(0.2, h / ref_h)))
            font = self._get_font(scaled_size)

            bbox = draw.textbbox((0, 0), sub.text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            x = int((w - text_w) * cur_x)
            y = int((h - text_h) * cur_y)

            # Draw outline
            ox, oy = max(1, int(scaled_size / 14)), max(1, int(scaled_size / 14))
            draw.text((x-ox, y), sub.text, font=font, fill=sub.border_color)
            draw.text((x+ox, y), sub.text, font=font, fill=sub.border_color)
            draw.text((x, y-oy), sub.text, font=font, fill=sub.border_color)
            draw.text((x, y+oy), sub.text, font=font, fill=sub.border_color)

            # Draw text fill
            draw.text((x, y), sub.text, font=font, fill=sub.color)

        # Draw smooth bounding box with corner handles around selected item
        sel = getattr(self, 'selected_item', None) or getattr(self, '_dragged_item', None)
        if sel and hasattr(sel, 'is_visible_at') and sel.is_visible_at(self.current_sec):
            cur_x, cur_y, cur_w, cur_h, cur_fs = sel.get_transform_at(self.current_sec) if hasattr(sel, 'get_transform_at') else (sel.x_ratio, sel.y_ratio, getattr(sel, 'width_ratio', 0.3), getattr(sel, 'height_ratio', 0.3), getattr(sel, 'font_size', 40))

            if hasattr(sel, 'width_ratio'):
                bw = max(30, int(w * cur_w))
                bh = max(30, int(h * cur_h))
                bx = int((w - bw) * cur_x)
                by = int((h - bh) * cur_y)
            else:
                # Text element auto-fitting box using EXACT rendered font size & metrics
                scaled_size = max(10, int(cur_fs * max(0.2, h / 720.0)))
                font = self._get_font(scaled_size)
                t_box = draw.textbbox((0, 0), sel.text or "Texto", font=font)
                text_w = t_box[2] - t_box[0]
                text_h = t_box[3] - t_box[1]

                bw = max(40, text_w + 30)
                bh = max(24, text_h + 20)
                bx = int((w - text_w) * cur_x) - 15
                by = int((h - text_h) * cur_y) - 10

            # Smooth cyan rectangle with keyframe indicator glow
            box_color = "#F5C2E7" if getattr(sel, 'enable_keyframes', False) else "#89B4FA"
            draw.rectangle([bx, by, bx + bw, by + bh], outline=box_color, width=2)

            # Corner handle dots
            r = 6
            draw.ellipse([bx - r, by - r, bx + r, by + r], fill="#F5E0DC", outline=box_color)
            draw.ellipse([bx + bw - r, by - r, bx + bw + r, by + r], fill="#F5E0DC", outline=box_color)
            draw.ellipse([bx - r, by + bh - r, bx + r, by + bh + r], fill="#F5E0DC", outline=box_color)
            draw.ellipse([bx + bw - r, by + bh - r, bx + bw + r, by + bh + r], fill="#F5E0DC", outline=box_color)

        frame_rgb = np.array(pil_img)

        q_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        # Scale keeping aspect ratio
        lbl_size = self.video_label.size()
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.video_label.setPixmap(scaled_pixmap)

    def _get_rendered_video_rect(self):
        lbl_w = max(1, self.video_label.width())
        lbl_h = max(1, self.video_label.height())
        if not self.video_info or self.video_info.width <= 0 or self.video_info.height <= 0:
            return 0, 0, lbl_w, lbl_h

        vw, vh = self.video_info.width, self.video_info.height
        scale = min(lbl_w / float(vw), lbl_h / float(vh))
        render_w = max(1, int(vw * scale))
        render_h = max(1, int(vh * scale))
        offset_x = int((lbl_w - render_w) / 2.0)
        offset_y = int((lbl_h - render_h) / 2.0)
        return offset_x, offset_y, render_w, render_h

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton or not self.video_info:
            return

        lbl_pos = self.video_label.mapFrom(self, event.position().toPoint())
        rx, ry, rw, rh = self._get_rendered_video_rect()

        # Local click coordinates mapped strictly inside rendered video frame
        local_x = lbl_pos.x() - rx
        local_y = lbl_pos.y() - ry

        # Strict selection priority: ONLY drag/resize currently selected item from timeline
        sel = getattr(self, 'selected_item', None)
        
        if not sel or not (hasattr(sel, 'is_visible_at') and sel.is_visible_at(self.current_sec)):
            active_subs = [s for s in self.subtitles if s.is_visible_at(self.current_sec)]
            active_imgs = [img for img in getattr(self, 'image_clips', []) if img.is_visible_at(self.current_sec)]
            active_vids = [v for v in getattr(self, 'video_clips', []) if v.is_visible_at(self.current_sec)]
            if active_imgs: sel = active_imgs[-1]
            elif active_vids: sel = active_vids[-1]
            elif active_subs: sel = active_subs[-1]

        if sel and hasattr(sel, 'is_visible_at') and sel.is_visible_at(self.current_sec):
            self._dragged_item = sel
            self._resize_corner = None

            cur_x, cur_y, cur_w, cur_h, cur_fs = sel.get_transform_at(self.current_sec) if hasattr(sel, 'get_transform_at') else (sel.x_ratio, sel.y_ratio, getattr(sel, 'width_ratio', 0.3), getattr(sel, 'height_ratio', 0.3), getattr(sel, 'font_size', 40))

            if hasattr(sel, 'width_ratio'):
                bw = max(30, int(rw * cur_w))
                bh = max(30, int(rh * cur_h))
                bx = int((rw - bw) * cur_x)
                by = int((rh - bh) * cur_y)
            else:
                scaled_size = max(10, int(cur_fs * max(0.2, rh / 720.0)))
                font = self._get_font(scaled_size)
                t_box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), sel.text or "Texto", font=font)
                text_w = t_box[2] - t_box[0]
                text_h = t_box[3] - t_box[1]
                bw = max(40, text_w + 30)
                bh = max(24, text_h + 20)
                bx = int((rw - text_w) * cur_x) - 15
                by = int((rh - text_h) * cur_y) - 10

            r = 25 # Hit target radius for corner handles
            is_inside_corner = (abs(local_x - bx) <= r and abs(local_y - by) <= r) or \
                               (abs(local_x - (bx + bw)) <= r and abs(local_y - by) <= r) or \
                               (abs(local_x - bx) <= r and abs(local_y - (by + bh)) <= r) or \
                               (abs(local_x - (bx + bw)) <= r and abs(local_y - (by + bh)) <= r)
            is_inside_body = (bx <= local_x <= bx + bw) and (by <= local_y <= by + bh)

            if not (is_inside_corner or is_inside_body):
                self._dragged_item = None
                self._resize_corner = None
                return

            self._dragged_item = sel
            self._resize_corner = None

            # Save initial bounding rect coordinates for anchor-based corner resizing
            self._init_bx = bx
            self._init_by = by
            self._init_bw = bw
            self._init_bh = bh

            if abs(local_x - bx) <= r and abs(local_y - by) <= r:
                self._resize_corner = "TL"
            elif abs(local_x - (bx + bw)) <= r and abs(local_y - by) <= r:
                self._resize_corner = "TR"
            elif abs(local_x - bx) <= r and abs(local_y - (by + bh)) <= r:
                self._resize_corner = "BL"
            elif abs(local_x - (bx + bw)) <= r and abs(local_y - (by + bh)) <= r:
                self._resize_corner = "BR"
            else:
                self._drag_offset_x = local_x - bx
                self._drag_offset_y = local_y - by

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        sel = getattr(self, 'selected_item', None) or getattr(self, '_dragged_item', None)
        if sel:
            from app.gui.timeline_widget import ClipInspectorDialog
            dlg = ClipInspectorDialog(sel, self)
            if dlg.exec():
                self.update_needed.emit()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = getattr(self, '_dragged_item', None)
        if item:
            lbl_pos = self.video_label.mapFrom(self, event.position().toPoint())
            rx, ry, rw, rh = self._get_rendered_video_rect()
            local_x = lbl_pos.x() - rx
            local_y = lbl_pos.y() - ry

            corner = getattr(self, '_resize_corner', None)
            if corner:
                init_x1 = getattr(self, '_init_bx', 0)
                init_y1 = getattr(self, '_init_by', 0)
                init_x2 = init_x1 + getattr(self, '_init_bw', 100)
                init_y2 = init_y1 + getattr(self, '_init_bh', 100)

                if corner == "BR":
                    x1 = init_x1
                    y1 = init_y1
                    x2 = max(x1 + 30, local_x)
                    y2 = max(y1 + 30, local_y)
                elif corner == "BL":
                    x1 = min(init_x2 - 30, local_x)
                    y1 = init_y1
                    x2 = init_x2
                    y2 = max(y1 + 30, local_y)
                elif corner == "TR":
                    x1 = init_x1
                    y1 = min(init_y2 - 30, local_y)
                    x2 = max(x1 + 30, local_x)
                    y2 = init_y2
                elif corner == "TL":
                    x1 = min(init_x2 - 30, local_x)
                    y1 = min(init_y2 - 30, local_y)
                    x2 = init_x2
                    y2 = init_y2

                new_w = max(30, x2 - x1)
                new_h = max(30, y2 - y1)

                denom_w = float(rw - new_w) if rw != new_w else 1.0
                denom_h = float(rh - new_h) if rh != new_h else 1.0

                calc_x_ratio = max(0.0, min(1.0, round(x1 / denom_w, 3)))
                calc_y_ratio = max(0.0, min(1.0, round(y1 / denom_h, 3)))

                if hasattr(item, 'width_ratio'):
                    item.width_ratio = round(max(0.05, min(1.0, new_w / float(rw))), 3)
                    item.height_ratio = round(max(0.05, min(1.0, new_h / float(rh))), 3)
                    item.x_ratio = calc_x_ratio
                    item.y_ratio = calc_y_ratio
                elif hasattr(item, 'font_size'):
                    item.font_size = max(10, min(200, int(new_h * 0.8)))
                    item.x_ratio = calc_x_ratio
                    item.y_ratio = calc_y_ratio
            else:
                off_x = getattr(self, '_drag_offset_x', 0)
                off_y = getattr(self, '_drag_offset_y', 0)

                if hasattr(item, 'width_ratio'):
                    new_bx = local_x - off_x
                    new_by = local_y - off_y

                    cur_w = getattr(item, 'width_ratio', 0.3)
                    cur_h = getattr(item, 'height_ratio', 0.3)
                    bw = max(30, int(rw * cur_w))
                    bh = max(30, int(rh * cur_h))

                    denom_w = float(rw - bw) if rw != bw else 1.0
                    denom_h = float(rh - bh) if rh != bh else 1.0

                    item.x_ratio = max(0.0, min(1.0, round(new_bx / denom_w, 3)))
                    item.y_ratio = max(0.0, min(1.0, round(new_by / denom_h, 3)))
                else:
                    # Precise Text Dragging - Zero Offset!
                    cur_fs = getattr(item, 'font_size', 40)
                    scaled_size = max(10, int(cur_fs * max(0.2, rh / 720.0)))
                    font = self._get_font(scaled_size)
                    t_box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), item.text or "Texto", font=font)
                    text_w = t_box[2] - t_box[0]
                    text_h = t_box[3] - t_box[1]

                    new_tx = local_x - off_x + 15
                    new_ty = local_y - off_y + 10

                    denom_w = float(rw - text_w) if rw != text_w else 1.0
                    denom_h = float(rh - text_h) if rh != text_h else 1.0

                    item.x_ratio = max(0.0, min(1.0, round(new_tx / denom_w, 3)))
                    item.y_ratio = max(0.0, min(1.0, round(new_ty / denom_h, 3)))

            if getattr(item, 'enable_keyframes', False):
                mid_sec = (item.start_sec + item.end_sec) / 2.0
                if self.current_sec <= mid_sec:
                    item.start_x_ratio = item.x_ratio
                    item.start_y_ratio = item.y_ratio
                    if hasattr(item, 'width_ratio'):
                        item.start_width_ratio = item.width_ratio
                        item.start_height_ratio = item.height_ratio
                    if hasattr(item, 'font_size'):
                        item.start_font_size = item.font_size
                else:
                    item.end_x_ratio = item.x_ratio
                    item.end_y_ratio = item.y_ratio
                    if hasattr(item, 'width_ratio'):
                        item.end_width_ratio = item.width_ratio
                        item.end_height_ratio = item.height_ratio
                    if hasattr(item, 'font_size'):
                        item.end_font_size = item.font_size

            if not getattr(self, '_is_rendering', False):
                self._is_rendering = True
                try:
                    self.seek_to(self.current_sec)
                finally:
                    self._is_rendering = False

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._dragged_item = None
        self._resize_corner = None

    def _update_sub_position_from_mouse(self, mouse_x: int, mouse_y: int):
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.video_info and self.cap and not getattr(self, '_is_rendering', False):
            self._is_rendering = True
            try:
                self.seek_to(self.current_sec)
            finally:
                self._is_rendering = False

    def _on_trim_changed(self, start_sec, end_sec):
        self.start_sec = start_sec
        self.end_sec = end_sec
        
        self.spn_start_time.blockSignals(True)
        self.spn_end_time.blockSignals(True)
        self.spn_start_time.setValue(start_sec)
        self.spn_end_time.setValue(end_sec)
        self.spn_start_time.blockSignals(False)
        self.spn_end_time.blockSignals(False)

        self._update_timecode_label()
        self.trimChanged.emit(start_sec, end_sec)

    def _on_spin_start_changed(self, val):
        if val < self.end_sec - 0.1:
            self.start_sec = val
            self.range_slider.setValues(self.start_sec, self.end_sec)
            self.seek_to(val)

    def _on_spin_end_changed(self, val):
        if val > self.start_sec + 0.1:
            self.end_sec = val
            self.range_slider.setValues(self.start_sec, self.end_sec)
            self.seek_to(val)

    def _set_current_as_start(self):
        if self.current_sec < self.end_sec - 0.1:
            self.range_slider.setValues(self.current_sec, self.end_sec)

    def _set_current_as_end(self):
        if self.current_sec > self.start_sec + 0.1:
            self.range_slider.setValues(self.start_sec, self.current_sec)

    def _update_timecode_label(self):
        start_str = VideoInfo.format_time(self.start_sec)
        end_str = VideoInfo.format_time(self.end_sec)
        dur_str = VideoInfo.format_time(self.end_sec - self.start_sec)
        self.lbl_timecode.setText(f"Trim: {start_str} - {end_str}  ({dur_str})")

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QDoubleSpinBox
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PIL import Image, ImageDraw, ImageFont
import cv2
import os

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

    def _next_frame(self):
        if not self.is_playing or not self.video_info or not self.cap:
            return

        self.current_sec += 0.033
        if self.current_sec >= self.end_sec:
            # Loop playback inside trim selection
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

    def _render_frame(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape

        # Draw active subtitles onto frame using PIL
        active_subs = [s for s in self.subtitles if s.is_visible_at(self.current_sec)]
        if active_subs:
            pil_img = Image.fromarray(frame_rgb)
            draw = ImageDraw.Draw(pil_img)
            
            for sub in active_subs:
                try:
                    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", sub.font_size)
                except Exception:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), sub.text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]

                x = int((w - text_w) * sub.x_ratio)
                y = int((h - text_h) * sub.y_ratio)

                # Draw outline
                ox, oy = 2, 2
                draw.text((x-ox, y), sub.text, font=font, fill=sub.border_color)
                draw.text((x+ox, y), sub.text, font=font, fill=sub.border_color)
                draw.text((x, y-oy), sub.text, font=font, fill=sub.border_color)
                draw.text((x, y+oy), sub.text, font=font, fill=sub.border_color)

                # Draw text fill
                draw.text((x, y), sub.text, font=font, fill=sub.color)

            frame_rgb = cv2.cvtColor(cv2.cvtColor(Image.Image.toqimage(pil_img).toImage().bits(), cv2.COLOR_RGBA2RGB), cv2.COLOR_RGB2BGR)
            q_img = QImage(pil_img.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
        else:
            q_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)

        # Scale keeping aspect ratio
        lbl_size = self.video_label.size()
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.video_label.setPixmap(scaled_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.video_info and self.cap:
            self.seek_to(self.current_sec)

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

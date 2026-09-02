import cv2
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from app.core.video_info import VideoInfo
from app.gui.range_slider import DualRangeSlider

class VideoPreviewWidget(QWidget):
    """
    Video Preview and Timeline Trimmer control widget.
    Renders video frames using OpenCV for universal format support (MP4, FLV, AVI, MKV, WebM, MOV).
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

        self.btn_play.setEnabled(True)
        self.btn_set_start.setEnabled(True)
        self.btn_set_end.setEnabled(True)

        self.seek_to(0.0)
        return True

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
        bytes_per_line = ch * w
        q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

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
        self._update_timecode_label()
        self.trimChanged.emit(start_sec, end_sec)

    def _set_current_as_start(self):
        if self.current_sec < self.end_sec - 0.1:
            self.range_slider.setValues(self.current_sec, self.end_sec)

    def _set_current_as_end(self):
        if self.current_sec > self.start_sec + 0.1:
            self.range_slider.setValues(self.start_sec, self.current_sec)

    def _update_timecode_label(self):
        curr_str = VideoInfo.format_time(self.current_sec)
        start_str = VideoInfo.format_time(self.start_sec)
        end_str = VideoInfo.format_time(self.end_sec)
        dur_str = VideoInfo.format_time(self.end_sec - self.start_sec)
        self.lbl_timecode.setText(f"Trim: {start_str} - {end_str}  ({dur_str})")

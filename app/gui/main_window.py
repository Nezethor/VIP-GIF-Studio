import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QFileDialog, QComboBox, QProgressBar,
    QMessageBox, QFrame, QSplitter, QCheckBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QDesktopServices, QIcon, QPixmap

from app.gui.styles import DARK_STYLESHEET
from app.gui.video_player import VideoPreviewWidget
from app.gui.subtitle_dialog import SubtitleManagerDialog
from app.core.converter import GifConverterWorker
from app.core.video_info import VideoInfo

class MainWindow(QMainWindow):
    """
    Main Window for VIP GIF Studio application.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIP GIF Studio - Convertidor de Video y GIF")
        self.resize(1150, 780)
        self.setMinimumSize(850, 600)
        self.setAcceptDrops(True)

        # Set Window Icon
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.current_video_path = ""
        self.subtitles = []
        self.worker = None

        self.setStyleSheet(DARK_STYLESHEET)
        self._init_ui(icon_path)

    def _init_ui(self, icon_path=""):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Title Bar with Movie Clapperboard Logo
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        if icon_path and os.path.exists(icon_path):
            logo_label = QLabel(self)
            pix = QPixmap(icon_path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
            header_layout.addWidget(logo_label)

        title_label = QLabel("VIP GIF Studio", self)
        title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #89B4FA;")
        subtitle_label = QLabel("Convertidor Profesional de Video y GIF", self)
        subtitle_label.setStyleSheet("font-size: 13px; color: #A6ADC8; margin-left: 6px;")

        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        header_layout.addStretch()

        self.btn_select_file = QPushButton("📁 Abrir Video o GIF (MP4, FLV, GIF...)", self)
        self.btn_select_file.setObjectName("fileButton")
        self.btn_select_file.clicked.connect(self._select_video_file)
        header_layout.addWidget(self.btn_select_file)

        main_layout.addLayout(header_layout)

        # Splitter Layout (Left: Video Player & Trim, Right: Conversion Settings)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)

        # --- LEFT PANEL: Video Player ---
        left_container = QWidget(self)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.video_player = VideoPreviewWidget(left_container)
        left_layout.addWidget(self.video_player)

        splitter.addWidget(left_container)

        # --- RIGHT PANEL: GIF Settings & Subtitles ---
        right_container = QWidget(self)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Info Box
        info_group = QGroupBox("Metadatos del Archivo", right_container)
        info_layout = QVBoxLayout(info_group)
        self.lbl_info = QLabel("Ningún archivo cargado", info_group)
        self.lbl_info.setStyleSheet("color: #BAC2DE; font-size: 12px;")
        info_layout.addWidget(self.lbl_info)
        right_layout.addWidget(info_group)

        # Subtitles Manager Box
        sub_group = QGroupBox("Subtítulos y Superposición de Texto", right_container)
        sub_layout = QVBoxLayout(sub_group)

        self.btn_manage_subtitles = QPushButton("💬 Gestor de Subtítulos y Texto", sub_group)
        self.btn_manage_subtitles.clicked.connect(self._open_subtitle_manager)
        sub_layout.addWidget(self.btn_manage_subtitles)

        self.lbl_sub_count = QLabel("Subtítulos agregados: 0", sub_group)
        self.lbl_sub_count.setStyleSheet("color: #F5C2E7; font-size: 12px;")
        sub_layout.addWidget(self.lbl_sub_count)

        right_layout.addWidget(sub_group)

        # Settings Box
        settings_group = QGroupBox("Ajustes de Calidad y Efectos", right_container)
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(10)

        # Resolution / Scale
        lbl_scale = QLabel("Resolución / Ancho:", settings_group)
        self.combo_scale = QComboBox(settings_group)
        self.combo_scale.addItems([
            "480p - Ancho 480px (Recomendado)",
            "720p - Ancho 720px (HD)",
            "1080p - Ancho 1080px (Full HD)",
            "360p - Ancho 360px (Ligero)",
            "Original (Sin escalar)"
        ])
        settings_layout.addWidget(lbl_scale)
        settings_layout.addWidget(self.combo_scale)

        # FPS Selection
        lbl_fps = QLabel("Fotogramas por Segundo (FPS):", settings_group)
        self.combo_fps = QComboBox(settings_group)
        self.combo_fps.addItems([
            "15 FPS (Recomendado - Tamaño Óptimo)",
            "24 FPS (Fluidez Cine)",
            "30 FPS (Máxima Fluidez)",
            "10 FPS (Archivo Pequeño)"
        ])
        settings_layout.addWidget(lbl_fps)
        settings_layout.addWidget(self.combo_fps)

        # Speed Control (0.1x to 10.0x)
        lbl_speed = QLabel("Velocidad de Reproducción (0.1x - 10.0x):", settings_group)
        speed_h_layout = QHBoxLayout()

        self.spn_speed = QDoubleSpinBox(settings_group)
        self.spn_speed.setRange(0.10, 10.00)
        self.spn_speed.setValue(1.00)
        self.spn_speed.setSingleStep(0.25)
        self.spn_speed.setSuffix(" x")
        speed_h_layout.addWidget(self.spn_speed)

        btn_speed_05 = QPushButton("0.5x", settings_group)
        btn_speed_05.setFixedWidth(45)
        btn_speed_05.clicked.connect(lambda: self.spn_speed.setValue(0.5))

        btn_speed_1 = QPushButton("1.0x", settings_group)
        btn_speed_1.setFixedWidth(45)
        btn_speed_1.clicked.connect(lambda: self.spn_speed.setValue(1.0))

        btn_speed_2 = QPushButton("2.0x", settings_group)
        btn_speed_2.setFixedWidth(45)
        btn_speed_2.clicked.connect(lambda: self.spn_speed.setValue(2.0))

        btn_speed_5 = QPushButton("5.0x", settings_group)
        btn_speed_5.setFixedWidth(45)
        btn_speed_5.clicked.connect(lambda: self.spn_speed.setValue(5.0))

        speed_h_layout.addWidget(btn_speed_05)
        speed_h_layout.addWidget(btn_speed_1)
        speed_h_layout.addWidget(btn_speed_2)
        speed_h_layout.addWidget(btn_speed_5)

        settings_layout.addWidget(lbl_speed)
        settings_layout.addLayout(speed_h_layout)

        # Reverse Playback Checkbox
        self.chk_reverse = QCheckBox("🔄 Reproducir a la Inversa (Reverse)", settings_group)
        self.chk_reverse.setStyleSheet("font-weight: bold; color: #89B4FA;")
        settings_layout.addWidget(self.chk_reverse)

        # Dither Algorithm
        lbl_dither = QLabel("Algoritmo de Color (Paleta HD):", settings_group)
        self.combo_dither = QComboBox(settings_group)
        self.combo_dither.addItems([
            "Sierra2-4a (Máxima Calidad sin bandas - Recomendado)",
            "Floyd-Steinberg (Difusión Clásica)",
            "Bayer Scale 5 (Estilo Retro Dither)",
            "Ninguno (Colores Planos / Archivo Pequeño)"
        ])
        settings_layout.addWidget(lbl_dither)
        settings_layout.addWidget(self.combo_dither)

        right_layout.addWidget(settings_group)

        # Primary Convert Action
        right_layout.addStretch()

        self.btn_convert = QPushButton("⚡ GENERAR GIF DE MÁXIMA CALIDAD", right_container)
        self.btn_convert.setObjectName("primaryButton")
        self.btn_convert.setEnabled(False)
        self.btn_convert.clicked.connect(self._start_conversion)
        right_layout.addWidget(self.btn_convert)

        # Progress Section
        self.progress_bar = QProgressBar(right_container)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("", right_container)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #F5C2E7; font-weight: 500;")
        right_layout.addWidget(self.lbl_status)

        self.btn_open_folder = QPushButton("📂 Abrir Carpeta de Destino", right_container)
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        right_layout.addWidget(self.btn_open_folder)

        splitter.addWidget(right_container)
        splitter.setSizes([720, 410])

        main_layout.addWidget(splitter)

        self.last_output_path = ""

    def _select_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar Video o GIF",
            "",
            "Archivos Multimedia (*.mp4 *.flv *.avi *.mov *.mkv *.webm *.wmv *.m4v *.3gp *.gif);;Todos los archivos (*.*)"
        )
        if file_path:
            self._load_video_file(file_path)

    def _open_subtitle_manager(self):
        if not self.video_player.video_info or not self.video_player.video_info.is_valid:
            QMessageBox.warning(self, "Aviso", "Primero debes cargar un archivo de video o GIF.")
            return

        dur = self.video_player.video_info.duration
        curr = self.video_player.current_sec
        dlg = SubtitleManagerDialog(self.subtitles, video_duration=dur, current_sec=curr, parent=self)
        dlg.subtitles_changed.connect(self._on_subtitles_updated)
        if dlg.exec():
            self._on_subtitles_updated(dlg.subtitles)

    def _on_subtitles_updated(self, new_subtitles):
        self.subtitles = new_subtitles
        self.video_player.set_subtitles(self.subtitles)
        self.lbl_sub_count.setText(f"Subtítulos agregados: {len(self.subtitles)}")

    def _load_video_file(self, file_path: str):
        if not os.path.exists(file_path):
            return

        success = self.video_player.load_video(file_path)
        if success:
            self.current_video_path = file_path
            info = self.video_player.video_info
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            
            self.lbl_info.setText(
                f"<b>Archivo:</b> {info.filename}<br>"
                f"<b>Resolución:</b> {info.width}x{info.height} px<br>"
                f"<b>FPS Original:</b> {info.fps:.2f} fps<br>"
                f"<b>Duración Total:</b> {VideoInfo.format_time(info.duration)}<br>"
                f"<b>Tamaño:</b> {size_mb:.2f} MB"
            )

            self.btn_convert.setEnabled(True)
            self.lbl_status.setText("Video cargado listos para recortar y convertir.")
            self.progress_bar.setVisible(False)
            self.btn_open_folder.setVisible(False)

    def _get_selected_scale(self) -> int:
        idx = self.combo_scale.currentIndex()
        if idx == 0: return 480
        elif idx == 1: return 720
        elif idx == 2: return 1080
        elif idx == 3: return 360
        else: return 0  # Original

    def _get_selected_fps(self) -> int:
        idx = self.combo_fps.currentIndex()
        if idx == 0: return 15
        elif idx == 1: return 24
        elif idx == 2: return 30
        else: return 10

    def _get_selected_dither(self) -> str:
        idx = self.combo_dither.currentIndex()
        if idx == 0: return "sierra2_4a"
        elif idx == 1: return "floyd_steinberg"
        elif idx == 2: return "bayer:bayer_scale=5"
        else: return "none"

    def _get_selected_speed(self) -> float:
        idx = self.combo_speed.currentIndex()
        if idx == 0: return 1.0
        elif idx == 1: return 1.25
        elif idx == 2: return 1.5
        elif idx == 3: return 2.0
        else: return 0.5

    def _start_conversion(self):
        if not self.current_video_path:
            return

        base_name = os.path.splitext(os.path.basename(self.current_video_path))[0]
        default_output = os.path.join(os.path.dirname(self.current_video_path), f"{base_name}_clip.gif")

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar GIF como...",
            default_output,
            "Imagen GIF (*.gif)"
        )

        if not output_path:
            return

        self.last_output_path = output_path

        start_sec = self.video_player.start_sec
        end_sec = self.video_player.end_sec
        fps = self._get_selected_fps()
        scale_width = self._get_selected_scale()
        dither = self._get_selected_dither()
        speed = self.spn_speed.value()
        reverse = self.chk_reverse.isChecked()

        self.btn_convert.setEnabled(False)
        self.btn_select_file.setEnabled(False)
        self.btn_manage_subtitles.setEnabled(False)
        self.video_player.pause()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_open_folder.setVisible(False)
        self.lbl_status.setText("Generando GIF de alta calidad... Por favor espera.")

        self.worker = GifConverterWorker(
            input_path=self.current_video_path,
            output_path=output_path,
            start_sec=start_sec,
            end_sec=end_sec,
            target_fps=fps,
            scale_width=scale_width,
            dither=dither,
            speed=speed,
            reverse=reverse,
            subtitles=self.subtitles
        )
        self.worker.progress_changed.connect(self._on_progress)
        self.worker.conversion_finished.connect(self._on_finished)
        self.worker.conversion_failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, percent: int, msg: str):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def _on_finished(self, output_path: str):
        self.btn_convert.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        self.btn_manage_subtitles.setEnabled(True)
        self.progress_bar.setValue(100)
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        self.lbl_status.setText(f"🎉 ¡GIF generado exitosamente! ({size_mb:.2f} MB)")
        self.btn_open_folder.setVisible(True)

        QMessageBox.information(
            self,
            "VIP GIF Studio",
            f"¡El archivo GIF fue creado con máxima calidad!\n\nRuta: {output_path}\nTamaño: {size_mb:.2f} MB"
        )

    def _on_failed(self, error_msg: str):
        self.btn_convert.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        self.btn_manage_subtitles.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.lbl_status.setText("❌ Error al convertir el video.")
        QMessageBox.critical(self, "Error de Conversión", error_msg)

    def _open_output_folder(self):
        if self.last_output_path and os.path.exists(self.last_output_path):
            folder = os.path.dirname(self.last_output_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            ext = os.path.splitext(file_path)[1].lower()
            if ext in ['.mp4', '.flv', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.m4v', '.3gp', '.gif']:
                self._load_video_file(file_path)
                break

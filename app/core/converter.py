import sys
import os
import subprocess
import re
import imageio_ffmpeg
from PyQt6.QtCore import QThread, pyqtSignal

def get_ffmpeg_path():
    """Obtiene la ruta del ejecutable FFmpeg, soportando binarios congelados en PyInstaller."""
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        # Buscar en las posibles rutas del paquete compilado
        try:
            exe_name = os.path.basename(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            exe_name = "ffmpeg.exe"

        possible_paths = [
            os.path.join(base_dir, "imageio_ffmpeg", "binaries", exe_name),
            os.path.join(base_dir, "binaries", exe_name),
            os.path.join(base_dir, exe_name),
            os.path.join(base_dir, "ffmpeg.exe")
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p

    return imageio_ffmpeg.get_ffmpeg_exe()


class GifConverterWorker(QThread):
    """
    Background QThread to convert video to high-quality GIF using 2-pass FFmpeg palette filter.
    Supports speed adjustment (0.1x - 10.0x), reverse playback, and custom text overlays.
    """
    progress_changed = pyqtSignal(int, str)  # (percent: int, log_message: str)
    conversion_finished = pyqtSignal(str)   # (output_path: str)
    conversion_failed = pyqtSignal(str)     # (error_msg: str)

    def __init__(self, 
                 input_path: str, 
                 output_path: str, 
                 start_sec: float, 
                 end_sec: float, 
                 target_fps: int = 15, 
                 scale_width: int = 480, 
                 dither: str = "sierra2_4a", 
                 speed: float = 1.0,
                 reverse: bool = False,
                 subtitles: list = None,
                 parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.target_fps = target_fps
        self.scale_width = scale_width
        self.dither = dither
        self.speed = max(0.1, min(10.0, speed))
        self.reverse = reverse
        self.subtitles = subtitles or []
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _build_drawtext_filters(self):
        """Construct FFmpeg drawtext filter string for all subtitles."""
        drawtext_filters = []
        font_path = r"C\:/Windows/Fonts/arial.ttf"

        for sub in self.subtitles:
            if not sub.text or not sub.text.strip():
                continue

            # Escape special FFmpeg filter characters: \, ', :, %
            escaped_text = sub.text.replace('\\', '\\\\').replace("'", "’").replace(':', '\\:').replace('%', '\\%')
            
            # Convert hex colors (#RRGGBB) to FFmpeg format
            font_color = sub.color.replace('#', '0x') if sub.color.startswith('#') else 'white'
            border_color = sub.border_color.replace('#', '0x') if sub.border_color.startswith('#') else 'black'

            # Relative position calculation
            # x_ratio = 0.5 -> (w-tw)/2 ; y_ratio = 0.8 -> (h-th)*0.8
            x_expr = f"(w-tw)*{sub.x_ratio:.3f}"
            y_expr = f"(h-th)*{sub.y_ratio:.3f}"

            filter_str = (
                f"drawtext=fontfile='{font_path}':text='{escaped_text}':"
                f"x={x_expr}:y={y_expr}:fontsize={sub.font_size}:"
                f"fontcolor={font_color}:borderw=2:bordercolor={border_color}:"
                f"enable='between(t,{sub.start_sec:.3f},{sub.end_sec:.3f})'"
            )
            drawtext_filters.append(filter_str)

        return drawtext_filters

    def run(self):
        try:
            ffmpeg_exe = get_ffmpeg_path()
            if not os.path.exists(self.input_path):
                self.conversion_failed.emit(f"Archivo de entrada no encontrado: {self.input_path}")
                return

            duration = self.end_sec - self.start_sec
            if duration <= 0:
                self.conversion_failed.emit("La duración seleccionada es inválida.")
                return

            self.progress_changed.emit(5, "Iniciando análisis de video y generación de paleta de alta definición...")

            # Temporary palette PNG file path
            palette_file = self.output_path + ".palette.png"

            # Filter definitions
            pts_mult = 1.0 / self.speed if self.speed > 0 else 1.0
            scale_str = f"scale={self.scale_width}:-1:flags=lanczos" if self.scale_width > 0 else "scale=iw:ih:flags=lanczos"
            
            # Base video filters: fps, setpts, scale
            filters_list = [f"fps={self.target_fps}", f"setpts={pts_mult:.4f}*PTS", scale_str]

            # Add reverse filter if enabled
            if self.reverse:
                filters_list.append("reverse")

            # Add drawtext filters for subtitles
            drawtext_filters = self._build_drawtext_filters()
            filters_list.extend(drawtext_filters)

            base_vf = ",".join(filters_list)

            # Pass 1: Generate palette
            palette_filter = f"[0:v]{base_vf},palettegen=stats_mode=full:max_colors=256"

            cmd_pass1 = [
                ffmpeg_exe, "-y",
                "-ss", f"{self.start_sec:.3f}",
                "-to", f"{self.end_sec:.3f}",
                "-i", self.input_path,
                "-vf", palette_filter,
                palette_file
            ]

            self._run_cmd(cmd_pass1, progress_offset=5, progress_range=35)

            if self._is_cancelled:
                self._clean_palette(palette_file)
                self.conversion_failed.emit("Conversión cancelada por el usuario.")
                return

            self.progress_changed.emit(40, "Paleta generada. Aplicando mapeo de color, subtítulos y dithering avanzado...")

            # Pass 2: Apply palette
            dither_option = f"dither={self.dither}:diff_mode=rectangle" if self.dither != "none" else "dither=none"
            apply_filter = f"[0:v]{base_vf}[x];[x][1:v]paletteuse={dither_option}"

            cmd_pass2 = [
                ffmpeg_exe, "-y",
                "-ss", f"{self.start_sec:.3f}",
                "-to", f"{self.end_sec:.3f}",
                "-i", self.input_path,
                "-i", palette_file,
                "-filter_complex", apply_filter,
                self.output_path
            ]

            self._run_cmd(cmd_pass2, progress_offset=40, progress_range=55)

            self._clean_palette(palette_file)

            if self._is_cancelled:
                self.conversion_failed.emit("Conversión cancelada por el usuario.")
                return

            if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                self.progress_changed.emit(100, "¡GIF creado exitosamente con máxima calidad!")
                self.conversion_finished.emit(self.output_path)
            else:
                self.conversion_failed.emit("No se pudo generar el archivo GIF de salida.")

        except Exception as e:
            self.conversion_failed.emit(f"Error durante la conversión: {str(e)}")

    def _clean_palette(self, palette_path):
        if os.path.exists(palette_path):
            try:
                os.remove(palette_path)
            except Exception:
                pass

    def _run_cmd(self, cmd_list, progress_offset: int, progress_range: int):
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            startupinfo=startupinfo,
            encoding='utf-8',
            errors='replace'
        )

        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        total_duration = max(0.1, self.end_sec - self.start_sec)

        while True:
            if self._is_cancelled:
                process.kill()
                break

            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break

            if line:
                match = time_pattern.search(line)
                if match:
                    hours, mins, secs = float(match.group(1)), float(match.group(2)), float(match.group(3))
                    elapsed = hours * 3600 + mins * 60 + secs
                    fraction = min(1.0, elapsed / total_duration)
                    current_percent = int(progress_offset + (fraction * progress_range))
                    self.progress_changed.emit(current_percent, f"Procesando fotogramas... ({current_percent}%)")

        process.wait()

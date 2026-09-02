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


class MediaConverterWorker(QThread):
    """
    Background QThread to convert video/GIF to high-quality GIF or Video (MP4, WebM, AVI, MOV).
    Renders ALL timeline elements (Text, Images, PIP Videos, Keyframes, Speed Cuts) frame-by-frame
    with 100% 1:1 preview matching and perfect audio sync.
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
                 timeline_intervals: list = None,
                 timeline_texts: list = None,
                 image_clips: list = None,
                 video_clips: list = None,
                 gpu_engine: str = "auto",
                 parent=None):
        super().__init__(parent)
        self.input_path = input_path
        self.output_path = output_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.target_fps = target_fps
        self.scale_width = scale_width
        self.dither = dither
        self.speed = abs(speed) if speed != 0 else 1.0
        self.reverse = reverse
        self.subtitles = subtitles if subtitles else []
        self.timeline_intervals = timeline_intervals if timeline_intervals else []
        self.timeline_texts = timeline_texts if timeline_texts else []
        self.image_clips = image_clips if image_clips else []
        self.video_clips = video_clips if video_clips else []
        self.gpu_engine = gpu_engine
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def composite_frame_at(self, frame_bgr, current_sec: float):
        """
        Render all active timeline elements (Text, Subtitles, Watermark Images, PIP Videos)
        onto frame_bgr at timestamp current_sec with keyframe interpolation and 1:1 preview matching.
        """
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        from app.core.photoshop_fx import PhotoshopFX

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = frame_rgb.shape

        # 1. PIP Video Overlay Clips with Photoshop FX
        for v_clip in getattr(self, 'video_clips', []):
            if v_clip.is_visible_at(current_sec) and os.path.exists(v_clip.video_path):
                try:
                    pip_cap = getattr(v_clip, '_cap', None)
                    if pip_cap is None or not pip_cap.isOpened():
                        pip_cap = cv2.VideoCapture(v_clip.video_path)
                        v_clip._cap = pip_cap

                    fps = pip_cap.get(cv2.CAP_PROP_FPS) or 30.0
                    total_frames = int(pip_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
                    v_dur_sec = float(total_frames) / fps if fps > 0 else 1.0

                    rel_t = current_sec - v_clip.start_sec
                    loop_t = rel_t % v_dur_sec if v_dur_sec > 0 else 0.0
                    target_frame = int(loop_t * fps) % max(1, total_frames)
                    pip_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                    ret, pip_frame = pip_cap.read()
                    if ret:
                        pip_rgb = cv2.cvtColor(pip_frame, cv2.COLOR_BGR2RGB)
                        cur_x, cur_y, cur_w, cur_h, _ = v_clip.get_transform_at(current_sec) if hasattr(v_clip, 'get_transform_at') else (v_clip.x_ratio, v_clip.y_ratio, v_clip.width_ratio, v_clip.height_ratio, 40)
                        target_w = max(30, int(w * cur_w))
                        target_h = max(30, int(h * cur_h))
                        pip_resized = cv2.resize(pip_rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                        # Apply Photoshop FX
                        pip_pil = Image.fromarray(pip_resized).convert("RGBA")
                        pip_fx = PhotoshopFX.apply_adjustments(
                            pip_pil,
                            filter_type=getattr(v_clip, 'filter_type', 'Normal'),
                            brightness=getattr(v_clip, 'brightness', 1.0),
                            contrast=getattr(v_clip, 'contrast', 1.0),
                            saturation=getattr(v_clip, 'saturation', 1.0),
                            blur_radius=getattr(v_clip, 'blur_radius', 0.0)
                        )
                        v_op = PhotoshopFX.compute_opacity_with_fade(
                            current_sec, v_clip.start_sec, v_clip.end_sec,
                            base_opacity=getattr(v_clip, 'opacity', 1.0),
                            fade_in_sec=getattr(v_clip, 'fade_in_sec', 0.0),
                            fade_out_sec=getattr(v_clip, 'fade_out_sec', 0.0)
                        )
                        pos_x = int((w - target_w) * cur_x)
                        pos_y = int((h - target_h) * cur_y)

                        bg_temp = Image.fromarray(frame_rgb).convert("RGBA")
                        if getattr(v_clip, 'drop_shadow', False):
                            s_box = Image.new("RGBA", (target_w, target_h), (0, 0, 0, int(140 * v_op)))
                            s_box = s_box.filter(ImageFilter.GaussianBlur(4))
                            bg_temp.paste(s_box, (pos_x + 6, pos_y + 6), s_box)

                        bg_temp = PhotoshopFX.apply_blend_composite(
                            bg_temp, pip_fx, (pos_x, pos_y),
                            blend_mode=getattr(v_clip, 'blend_mode', 'Normal'),
                            opacity=v_op
                        )
                        frame_rgb = np.array(bg_temp.convert("RGB"))
                except Exception:
                    pass

        # 2. Image / Watermark Overlay Clips with Photoshop FX
        active_imgs = [img for img in getattr(self, 'image_clips', []) if img.is_visible_at(current_sec)]
        if active_imgs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            for img_clip in active_imgs:
                if os.path.exists(img_clip.image_path):
                    try:
                        overlay_img = Image.open(img_clip.image_path).convert("RGBA")
                        cur_x, cur_y, cur_w, cur_h, _ = img_clip.get_transform_at(current_sec) if hasattr(img_clip, 'get_transform_at') else (img_clip.x_ratio, img_clip.y_ratio, img_clip.width_ratio, img_clip.height_ratio, 40)
                        target_w = max(20, int(w * cur_w))
                        target_h = max(20, int(h * cur_h))
                        overlay_img = overlay_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                        pos_x = int((w - target_w) * cur_x)
                        pos_y = int((h - target_h) * cur_y)

                        img_fx = PhotoshopFX.apply_adjustments(
                            overlay_img,
                            filter_type=getattr(img_clip, 'filter_type', 'Normal'),
                            brightness=getattr(img_clip, 'brightness', 1.0),
                            contrast=getattr(img_clip, 'contrast', 1.0),
                            saturation=getattr(img_clip, 'saturation', 1.0),
                            blur_radius=getattr(img_clip, 'blur_radius', 0.0)
                        )
                        img_op = PhotoshopFX.compute_opacity_with_fade(
                            current_sec, img_clip.start_sec, img_clip.end_sec,
                            base_opacity=getattr(img_clip, 'opacity', 1.0),
                            fade_in_sec=getattr(img_clip, 'fade_in_sec', 0.0),
                            fade_out_sec=getattr(img_clip, 'fade_out_sec', 0.0)
                        )

                        if getattr(img_clip, 'drop_shadow', False):
                            s_box = Image.new("RGBA", (target_w, target_h), (0, 0, 0, int(150 * img_op)))
                            s_box = s_box.filter(ImageFilter.GaussianBlur(5))
                            pil_img.paste(s_box, (pos_x + 6, pos_y + 6), s_box)

                        pil_img = PhotoshopFX.apply_blend_composite(
                            pil_img, img_fx, (pos_x, pos_y),
                            blend_mode=getattr(img_clip, 'blend_mode', 'Normal'),
                            opacity=img_op
                        )
                    except Exception:
                        pass
            frame_rgb = np.array(pil_img.convert("RGB"))

        # 3. Text & Subtitle Overlay Clips with Photoshop FX
        all_texts = list(getattr(self, 'subtitles', [])) + list(getattr(self, 'timeline_texts', []))
        active_subs = [s for s in all_texts if s.is_visible_at(current_sec)]
        if active_subs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            draw = ImageDraw.Draw(pil_img)

            for sub in active_subs:
                cur_x, cur_y, _, _, cur_fs = sub.get_transform_at(current_sec) if hasattr(sub, 'get_transform_at') else (sub.x_ratio, sub.y_ratio, 0.3, 0.3, sub.font_size)
                ref_h = 720.0
                scaled_size = max(10, int(cur_fs * max(0.2, h / ref_h)))
                
                try:
                    font = ImageFont.truetype("arial.ttf", scaled_size)
                except Exception:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), sub.text, font=font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]

                x = int((w - text_w) * cur_x)
                y = int((h - text_h) * cur_y)

                t_op = PhotoshopFX.compute_opacity_with_fade(
                    current_sec, sub.start_sec, sub.end_sec,
                    base_opacity=getattr(sub, 'opacity', 1.0),
                    fade_in_sec=getattr(sub, 'fade_in_sec', 0.0),
                    fade_out_sec=getattr(sub, 'fade_out_sec', 0.0)
                )

                # Soft Drop Shadow
                if getattr(sub, 'drop_shadow', True) and t_op > 0.05:
                    draw.text((x + 4, y + 4), sub.text, font=font, fill=(0, 0, 0, int(160 * t_op)))

                ox, oy = max(1, int(scaled_size / 14)), max(1, int(scaled_size / 14))
                draw.text((x-ox, y), sub.text, font=font, fill=sub.border_color)
                draw.text((x+ox, y), sub.text, font=font, fill=sub.border_color)
                draw.text((x, y-oy), sub.text, font=font, fill=sub.border_color)
                draw.text((x, y+oy), sub.text, font=font, fill=sub.border_color)

                draw.text((x, y), sub.text, font=font, fill=sub.color)

            frame_rgb = np.array(pil_img.convert("RGB"))

        return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    def run(self):
        import cv2
        import numpy as np

        try:
            ffmpeg_exe = get_ffmpeg_path()
            if not os.path.exists(self.input_path):
                self.conversion_failed.emit(f"Archivo de entrada no encontrado: {self.input_path}")
                return

            cap = cv2.VideoCapture(self.input_path)
            if not cap.isOpened():
                self.conversion_failed.emit("No se pudo abrir el archivo de video de entrada.")
                return

            orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
            orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
            orig_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            if self.scale_width > 0:
                out_w = self.scale_width
                out_h = int(orig_h * (out_w / float(orig_w)))
                out_h = out_h + (out_h % 2) # ensure even height for H.264
            else:
                out_w = orig_w
                out_h = orig_h

            ext = os.path.splitext(self.output_path)[1].lower()
            is_video_export = ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v']

            self.progress_changed.emit(5, "Iniciando motor de composición fotograma a fotograma...")

            # Determine speed intervals
            if self.timeline_intervals and len(self.timeline_intervals) > 0:
                intervals = self.timeline_intervals
            else:
                from app.core.timeline import SpeedInterval
                intervals = [SpeedInterval(self.start_sec, self.end_sec, self.speed, self.reverse)]

            # Temporary raw video file for video exports
            tmp_video = self.output_path + ".tmp.mp4" if is_video_export else self.output_path

            # Helper for GPU/CPU Encoder selection
            enc_flags = self._get_encoder_flags(ffmpeg_exe, is_video_export)

            # FFmpeg Command with Raw Video Stdin Pipe
            if is_video_export:
                cmd_ffmpeg = [
                    ffmpeg_exe, "-y",
                    "-f", "rawvideo",
                    "-vcodec", "rawvideo",
                    "-s", f"{out_w}x{out_h}",
                    "-pix_fmt", "bgr24",
                    "-r", str(self.target_fps),
                    "-i", "-"
                ] + enc_flags + [
                    "-pix_fmt", "yuv420p",
                    tmp_video
                ]
            else:
                # Direct GIF export using palettegen/paletteuse via ffmpeg
                cmd_ffmpeg = [
                    ffmpeg_exe, "-y",
                    "-f", "rawvideo",
                    "-vcodec", "rawvideo",
                    "-s", f"{out_w}x{out_h}",
                    "-pix_fmt", "bgr24",
                    "-r", str(self.target_fps),
                    "-i", "-",
                    "-filter_complex", "split[s0][s1];[s0]palettegen=stats_mode=full[p];[s1][p]paletteuse=dither=sierra2_4a",
                    self.output_path
                ]

            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

            process = subprocess.Popen(
                cmd_ffmpeg,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )

            # Total duration calculation across active remaining intervals
            total_active_sec = sum(inv.duration / max(0.1, inv.speed) for inv in intervals)
            processed_sec = 0.0

            # Render frames for each remaining active interval
            for inv in intervals:
                if self._is_cancelled:
                    break

                inv_dur = inv.duration
                inv_speed = max(0.1, inv.speed)
                step_sec = (1.0 / self.target_fps) * inv_speed

                if inv.reverse:
                    t_cur = inv.end_sec
                    while t_cur >= inv.start_sec and not self._is_cancelled:
                        target_frame_idx = max(0, int(t_cur * orig_fps))
                        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            if (orig_w, orig_h) != (out_w, out_h):
                                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                            
                            comp_frame = self.composite_frame_at(frame, t_cur)
                            process.stdin.write(comp_frame.tobytes())

                        t_cur -= step_sec
                        processed_sec += (1.0 / self.target_fps)
                        percent = min(90, int(5 + (processed_sec / max(0.1, total_active_sec)) * 80))
                        self.progress_changed.emit(percent, f"Renderizando elementos en pantalla... ({percent}%)")
                else:
                    t_cur = inv.start_sec
                    start_frame_idx = max(0, int(inv.start_sec * orig_fps))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)
                    current_frame_idx = start_frame_idx

                    last_valid_frame = None

                    while t_cur <= inv.end_sec and not self._is_cancelled:
                        target_frame_idx = max(0, int(t_cur * orig_fps))
                        
                        # Fast-forward sequential reads until current_frame_idx reaches target_frame_idx
                        ret = True
                        while current_frame_idx <= target_frame_idx:
                            ret, frame = cap.read()
                            if not ret or frame is None:
                                break
                            last_valid_frame = frame
                            current_frame_idx += 1

                        frame_to_use = last_valid_frame if (last_valid_frame is not None) else frame

                        if frame_to_use is not None:
                            if (orig_w, orig_h) != (out_w, out_h):
                                frame_to_use = cv2.resize(frame_to_use, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                            
                            comp_frame = self.composite_frame_at(frame_to_use, t_cur)
                            process.stdin.write(comp_frame.tobytes())

                        t_cur += step_sec
                        processed_sec += (1.0 / self.target_fps)
                        percent = min(90, int(5 + (processed_sec / max(0.1, total_active_sec)) * 80))
                        self.progress_changed.emit(percent, f"Renderizando elementos en pantalla... ({percent}%)")

            process.stdin.close()
            process.wait()
            cap.release()

            # Close VideoCaptures of PIP clips
            for v_clip in getattr(self, 'video_clips', []):
                pip_cap = getattr(v_clip, '_cap', None)
                if pip_cap:
                    pip_cap.release()

            if self._is_cancelled:
                self.conversion_failed.emit("Conversión cancelada por el usuario.")
                return

            if is_video_export:
                # Merge Audio for active intervals into final MP4
                self.progress_changed.emit(92, "Sincronizando pistas de audio...")
                try:
                    audio_filters = []
                    concat_a = []
                    for idx, inv in enumerate(intervals):
                        a_lbl = f"a{idx}"
                        af_parts = [f"atrim=start={inv.start_sec:.3f}:end={inv.end_sec:.3f}", "asetpts=PTS-STARTPTS"]
                        if inv.reverse:
                            af_parts.append("areverse")
                        spd = inv.speed
                        while spd > 2.0:
                            af_parts.append("atempo=2.0")
                            spd /= 2.0
                        while spd < 0.5:
                            af_parts.append("atempo=0.5")
                            spd /= 0.5
                        if abs(spd - 1.0) > 0.001:
                            af_parts.append(f"atempo={spd:.4f}")
                        audio_filters.append(f"[1:a]{','.join(af_parts)}[{a_lbl}]")
                        concat_a.append(f"[{a_lbl}]")

                    audio_filters.append(f"{''.join(concat_a)}concat=n={len(intervals)}:v=0:a=1[outa]")
                    full_af = ";".join(audio_filters)

                    cmd_merge = [
                        ffmpeg_exe, "-y",
                        "-i", tmp_video,
                        "-i", self.input_path,
                        "-filter_complex", full_af,
                        "-map", "0:v",
                        "-map", "[outa]",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        self.output_path
                    ]

                    proc_m = subprocess.Popen(cmd_merge, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
                    ret_m = proc_m.wait()

                    if ret_m == 0 and os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                        if os.path.exists(tmp_video):
                            os.remove(tmp_video)
                    else:
                        raise RuntimeError("Audio muxing skipped/failed")
                except Exception:
                    # If audio merge fails or source has no audio, fallback to composited video track
                    if os.path.exists(self.output_path):
                        try: os.remove(self.output_path)
                        except Exception: pass
                    if os.path.exists(tmp_video):
                        os.rename(tmp_video, self.output_path)

            if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                self.progress_changed.emit(100, "¡Vídeo renderizado con éxito con todos sus elementos!")
                self.conversion_finished.emit(self.output_path)
            else:
                self.conversion_failed.emit("No se pudo generar el archivo final.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.conversion_failed.emit(f"Error durante el procesamiento: {str(e)}")

    def _get_encoder_flags(self, ffmpeg_exe, is_video: bool) -> list:
        if not is_video:
            return []
        
        selected = getattr(self, 'gpu_engine', 'auto')

        # 1. NVIDIA NVENC
        if selected in ['nvenc', 'auto']:
            flags = ['-c:v', 'h264_nvenc', '-preset', 'p4']
            if self._test_encoder(ffmpeg_exe, flags):
                print("[GPU] Hardware Encoder Acoplado: NVIDIA NVENC (h264_nvenc)")
                return flags

        # 2. AMD Radeon AMF GPU
        if selected in ['amf', 'auto']:
            flags = ['-c:v', 'h264_amf', '-usage', 'transcoding', '-quality', 'speed']
            if self._test_encoder(ffmpeg_exe, flags):
                print("[GPU] Hardware Encoder Acoplado: AMD Radeon AMF (h264_amf)")
                return flags

        # 3. Intel QuickSync QSV
        if selected in ['qsv', 'auto']:
            flags = ['-c:v', 'h264_qsv', '-preset', 'veryfast']
            if self._test_encoder(ffmpeg_exe, flags):
                print("[GPU] Hardware Encoder Acoplado: Intel QuickSync (h264_qsv)")
                return flags

        # 4. Windows Media Foundation Hardware GPU (DirectX HW Acceleration)
        if selected in ['mf', 'auto']:
            flags = ['-c:v', 'h264_mf']
            if self._test_encoder(ffmpeg_exe, flags):
                print("[GPU] Hardware Encoder Acoplado: Windows Media Foundation GPU (h264_mf)")
                return flags

        # 5. CPU High-Performance Multi-Core Fallback
        print("[CPU] Multi-Threading Acoplado: libx264 Ultrafast (-threads 0)")
        return ['-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'fastdecode', '-crf', '20', '-threads', '0']

    def _test_encoder(self, ffmpeg_exe, encoder_flags: list) -> bool:
        try:
            cmd = [ffmpeg_exe, '-y', '-f', 'lavfi', '-i', 'nullsrc=s=1280x720:d=0.1'] + encoder_flags + ['-f', 'null', '-']
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, timeout=4)
            return res.returncode == 0
        except Exception:
            return False

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


# Alias for backwards compatibility
GifConverterWorker = MediaConverterWorker

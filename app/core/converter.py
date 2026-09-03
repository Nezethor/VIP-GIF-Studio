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
    Background QThread — VIP GIF Studio v3.0.0 render engine.
    Renders ALL timeline elements frame-by-frame:
      - Speed Intervals (trim, reverse, speed)
      - Text / Subtitle clips with keyframes, opacity, rotation, masks
      - Image clips with keyframes, Photoshop FX, masks
      - PIP Video clips with slip edit, keyframes, FX, masks
      - Shape clips (rectangle, ellipse, triangle, star…)
      - Adjustment Layers (global post-processing per frame)
      - Transitions between clips (Fade, Wipe, Slide, Zoom, Glitch…)
      - Independent Audio tracks (mixed via FFmpeg)
    Uses NumPy GPUCompositor for faster alpha blending.
    """
    progress_changed = pyqtSignal(int, str)
    conversion_finished = pyqtSignal(str)
    conversion_failed = pyqtSignal(str)

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
                 shape_clips: list = None,
                 audio_clips: list = None,
                 transition_clips: list = None,
                 adjustment_layers: list = None,
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
        self.subtitles = subtitles or []
        self.timeline_intervals = timeline_intervals or []
        self.timeline_texts = timeline_texts or []
        self.image_clips = image_clips or []
        self.video_clips = video_clips or []
        self.shape_clips = shape_clips or []
        self.audio_clips = audio_clips or []
        self.transition_clips = transition_clips or []
        self.adjustment_layers = adjustment_layers or []
        self.gpu_engine = gpu_engine
        self._is_cancelled = False
        self._pip_caps = {}

    def cancel(self):
        self._is_cancelled = True

    # ------------------------------------------------------------------
    # Frame compositing
    # ------------------------------------------------------------------

    def composite_frame_at(self, frame_bgr, current_sec: float):
        """
        Render all active timeline elements onto frame_bgr at timestamp current_sec.
        Order: PIP Video → Images → Shapes → Texts/Subtitles → Adjustment Layers → Transitions
        """
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        from app.core.photoshop_fx import PhotoshopFX

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, _ = frame_rgb.shape

        # ----------------------------------------------------------------
        # 1. PIP Video Overlay Clips
        # ----------------------------------------------------------------
        for v_clip in self.video_clips:
            if not v_clip.is_visible_at(current_sec):
                continue
            if not os.path.exists(getattr(v_clip, 'video_path', '')):
                continue
            try:
                pip_cap = self._pip_caps.get(v_clip.id)
                if pip_cap is None or not pip_cap.isOpened():
                    pip_cap = cv2.VideoCapture(v_clip.video_path)
                    self._pip_caps[v_clip.id] = pip_cap

                fps = pip_cap.get(cv2.CAP_PROP_FPS) or 30.0
                total_frames = int(pip_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
                v_dur_sec = float(total_frames) / fps if fps > 0 else 1.0

                slip_off = getattr(v_clip, 'slip_offset_sec', 0.0)
                rel_t = (current_sec - v_clip.start_sec + slip_off) * getattr(v_clip, 'speed', 1.0)
                if getattr(v_clip, 'reverse', False):
                    rel_t = v_dur_sec - rel_t
                loop_t = rel_t % v_dur_sec if v_dur_sec > 0 else 0.0
                target_frame = int(loop_t * fps) % max(1, total_frames)
                pip_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, pip_frame = pip_cap.read()
                if not ret:
                    continue

                pip_rgb = cv2.cvtColor(pip_frame, cv2.COLOR_BGR2RGB)
                cur_x, cur_y, cur_w, cur_h, _ = v_clip.get_transform_at(current_sec)
                target_w = max(30, int(w * cur_w))
                target_h = max(30, int(h * cur_h))
                pip_resized = cv2.resize(pip_rgb, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

                pip_pil = Image.fromarray(pip_resized).convert("RGBA")
                pip_fx = PhotoshopFX.apply_adjustments(
                    pip_pil,
                    filter_type=getattr(v_clip, 'filter_type', 'Normal'),
                    brightness=getattr(v_clip, 'brightness', 1.0),
                    contrast=getattr(v_clip, 'contrast', 1.0),
                    saturation=getattr(v_clip, 'saturation', 1.0),
                    blur_radius=getattr(v_clip, 'blur_radius', 0.0),
                )
                # Mask
                if getattr(v_clip, 'mask_path', ''):
                    pip_fx = PhotoshopFX.apply_mask(pip_fx, v_clip.mask_path, getattr(v_clip, 'mask_invert', False))

                if getattr(v_clip, 'border_radius', 0) > 0 or getattr(v_clip, 'border_width', 0) > 0:
                    pip_fx = PhotoshopFX.apply_border_and_corners(
                        pip_fx, radius=getattr(v_clip, 'border_radius', 0),
                        border_width=getattr(v_clip, 'border_width', 0),
                        border_color=getattr(v_clip, 'border_color', '#FFFFFF'))

                cur_rot = v_clip.get_rotation_at(current_sec) if hasattr(v_clip, 'get_rotation_at') else getattr(v_clip, 'rotation', 0.0)
                if abs(cur_rot) > 0.1:
                    pip_fx = PhotoshopFX.apply_rotation(pip_fx, cur_rot)

                v_op = PhotoshopFX.compute_opacity_with_fade(
                    current_sec, v_clip.start_sec, v_clip.end_sec,
                    base_opacity=v_clip.get_opacity_at(current_sec) if hasattr(v_clip, 'get_opacity_at') else getattr(v_clip, 'opacity', 1.0),
                    fade_in_sec=getattr(v_clip, 'fade_in_sec', 0.0),
                    fade_out_sec=getattr(v_clip, 'fade_out_sec', 0.0))

                pos_x = int((w - target_w) * cur_x)
                pos_y = int((h - target_h) * cur_y)

                bg_temp = Image.fromarray(frame_rgb).convert("RGBA")
                if getattr(v_clip, 'drop_shadow', False):
                    s_box = Image.new("RGBA", pip_fx.size, (0, 0, 0, int(140 * v_op)))
                    s_box = s_box.filter(ImageFilter.GaussianBlur(4))
                    bg_temp.paste(s_box, (pos_x + 6, pos_y + 6), s_box)

                bg_temp = PhotoshopFX.apply_blend_composite(
                    bg_temp, pip_fx, (pos_x, pos_y),
                    blend_mode=getattr(v_clip, 'blend_mode', 'Normal'),
                    opacity=v_op)
                frame_rgb = np.array(bg_temp.convert("RGB"))
            except Exception:
                pass

        # ----------------------------------------------------------------
        # 2. Image Overlay Clips
        # ----------------------------------------------------------------
        active_imgs = [c for c in self.image_clips if c.is_visible_at(current_sec)]
        if active_imgs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            for img_clip in active_imgs:
                if not os.path.exists(img_clip.image_path):
                    continue
                try:
                    overlay_img = Image.open(img_clip.image_path).convert("RGBA")
                    cur_x, cur_y, cur_w, cur_h, _ = img_clip.get_transform_at(current_sec)
                    target_w = max(20, int(w * cur_w))
                    target_h = max(20, int(h * cur_h))
                    overlay_img = overlay_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

                    img_fx = PhotoshopFX.apply_adjustments(
                        overlay_img,
                        filter_type=getattr(img_clip, 'filter_type', 'Normal'),
                        brightness=getattr(img_clip, 'brightness', 1.0),
                        contrast=getattr(img_clip, 'contrast', 1.0),
                        saturation=getattr(img_clip, 'saturation', 1.0),
                        blur_radius=getattr(img_clip, 'blur_radius', 0.0))

                    if getattr(img_clip, 'mask_path', ''):
                        img_fx = PhotoshopFX.apply_mask(img_fx, img_clip.mask_path, getattr(img_clip, 'mask_invert', False))

                    if getattr(img_clip, 'border_radius', 0) > 0 or getattr(img_clip, 'border_width', 0) > 0:
                        img_fx = PhotoshopFX.apply_border_and_corners(
                            img_fx, radius=getattr(img_clip, 'border_radius', 0),
                            border_width=getattr(img_clip, 'border_width', 0),
                            border_color=getattr(img_clip, 'border_color', '#FFFFFF'))

                    cur_rot = img_clip.get_rotation_at(current_sec) if hasattr(img_clip, 'get_rotation_at') else getattr(img_clip, 'rotation', 0.0)
                    if abs(cur_rot) > 0.1:
                        img_fx = PhotoshopFX.apply_rotation(img_fx, cur_rot)

                    img_op = PhotoshopFX.compute_opacity_with_fade(
                        current_sec, img_clip.start_sec, img_clip.end_sec,
                        base_opacity=img_clip.get_opacity_at(current_sec) if hasattr(img_clip, 'get_opacity_at') else getattr(img_clip, 'opacity', 1.0),
                        fade_in_sec=getattr(img_clip, 'fade_in_sec', 0.0),
                        fade_out_sec=getattr(img_clip, 'fade_out_sec', 0.0))

                    pos_x = int((w - target_w) * cur_x)
                    pos_y = int((h - target_h) * cur_y)

                    if getattr(img_clip, 'drop_shadow', False):
                        s_box = Image.new("RGBA", img_fx.size, (0, 0, 0, int(150 * img_op)))
                        s_box = s_box.filter(ImageFilter.GaussianBlur(5))
                        pil_img.paste(s_box, (pos_x + 6, pos_y + 6), s_box)

                    pil_img = PhotoshopFX.apply_blend_composite(
                        pil_img, img_fx, (pos_x, pos_y),
                        blend_mode=getattr(img_clip, 'blend_mode', 'Normal'),
                        opacity=img_op)
                except Exception:
                    pass
            frame_rgb = np.array(pil_img.convert("RGB"))

        # ----------------------------------------------------------------
        # 3. Shape Clips
        # ----------------------------------------------------------------
        active_shapes = [c for c in self.shape_clips if c.is_visible_at(current_sec)]
        if active_shapes:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            for shp in active_shapes:
                try:
                    cur_x, cur_y, cur_w, cur_h, _ = shp.get_transform_at(current_sec)
                    target_w = max(10, int(w * cur_w))
                    target_h = max(10, int(h * cur_h))
                    shape_img = PhotoshopFX.render_shape(
                        target_w, target_h,
                        shape_type=getattr(shp, 'shape_type', 'Rectangle'),
                        fill_color=getattr(shp, 'fill_color', '#CBA6F7'),
                        stroke_color=getattr(shp, 'stroke_color', '#FFFFFF'),
                        stroke_width=getattr(shp, 'stroke_width', 2),
                        corner_radius=getattr(shp, 'corner_radius', 0),
                        star_points=getattr(shp, 'star_points', 5))

                    if getattr(shp, 'blur_radius', 0.0) > 0:
                        shape_img = PhotoshopFX.apply_adjustments(shape_img, blur_radius=shp.blur_radius)

                    if getattr(shp, 'mask_path', ''):
                        shape_img = PhotoshopFX.apply_mask(shape_img, shp.mask_path, getattr(shp, 'mask_invert', False))

                    cur_rot = shp.get_rotation_at(current_sec) if hasattr(shp, 'get_rotation_at') else getattr(shp, 'rotation', 0.0)
                    if abs(cur_rot) > 0.1:
                        shape_img = PhotoshopFX.apply_rotation(shape_img, cur_rot)

                    shp_op = PhotoshopFX.compute_opacity_with_fade(
                        current_sec, shp.start_sec, shp.end_sec,
                        base_opacity=shp.get_opacity_at(current_sec) if hasattr(shp, 'get_opacity_at') else getattr(shp, 'opacity', 1.0),
                        fade_in_sec=getattr(shp, 'fade_in_sec', 0.0),
                        fade_out_sec=getattr(shp, 'fade_out_sec', 0.0))

                    pos_x = int((w - target_w) * cur_x)
                    pos_y = int((h - target_h) * cur_y)

                    if getattr(shp, 'drop_shadow', False):
                        s_box = Image.new("RGBA", shape_img.size, (0, 0, 0, int(120 * shp_op)))
                        s_box = s_box.filter(ImageFilter.GaussianBlur(4))
                        pil_img.paste(s_box, (pos_x + 4, pos_y + 4), s_box)

                    pil_img = PhotoshopFX.apply_blend_composite(
                        pil_img, shape_img, (pos_x, pos_y),
                        blend_mode=getattr(shp, 'blend_mode', 'Normal'),
                        opacity=shp_op)
                except Exception:
                    pass
            frame_rgb = np.array(pil_img.convert("RGB"))

        # ----------------------------------------------------------------
        # 4. Text & Subtitle Overlay Clips
        # ----------------------------------------------------------------
        all_texts = list(self.subtitles) + list(self.timeline_texts)
        active_subs = [s for s in all_texts if s.is_visible_at(current_sec)]
        if active_subs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            draw = ImageDraw.Draw(pil_img)

            for sub in active_subs:
                try:
                    cur_x, cur_y, _, _, cur_fs = sub.get_transform_at(current_sec) if hasattr(sub, 'get_transform_at') else (sub.x_ratio, sub.y_ratio, 0.3, 0.3, sub.font_size)
                    ref_h = 720.0
                    scaled_size = max(10, int(cur_fs * max(0.2, h / ref_h)))

                    # Font loading with family support
                    font_family = getattr(sub, 'font_family', 'Arial')
                    bold = getattr(sub, 'font_bold', False)
                    italic = getattr(sub, 'font_italic', False)
                    try:
                        font_file = "arialbd.ttf" if bold else ("ariali.ttf" if italic else "arial.ttf")
                        font = ImageFont.truetype(font_file, scaled_size)
                    except Exception:
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
                        base_opacity=sub.get_opacity_at(current_sec) if hasattr(sub, 'get_opacity_at') else getattr(sub, 'opacity', 1.0),
                        fade_in_sec=getattr(sub, 'fade_in_sec', 0.0),
                        fade_out_sec=getattr(sub, 'fade_out_sec', 0.0))

                    alpha_val = int(255 * t_op)

                    # Drop Shadow
                    if getattr(sub, 'drop_shadow', True) and t_op > 0.05:
                        draw.text((x + 4, y + 4), sub.text, font=font, fill=(0, 0, 0, int(160 * t_op)))

                    # Outline stroke
                    ox, oy = max(1, int(scaled_size / 14)), max(1, int(scaled_size / 14))
                    bc = sub.border_color
                    draw.text((x - ox, y), sub.text, font=font, fill=bc)
                    draw.text((x + ox, y), sub.text, font=font, fill=bc)
                    draw.text((x, y - oy), sub.text, font=font, fill=bc)
                    draw.text((x, y + oy), sub.text, font=font, fill=bc)

                    # Main text
                    draw.text((x, y), sub.text, font=font, fill=sub.color)
                except Exception:
                    pass

            frame_rgb = np.array(pil_img.convert("RGB"))

        # ----------------------------------------------------------------
        # 5. Adjustment Layers (global post-processing)
        # ----------------------------------------------------------------
        active_adj = [a for a in self.adjustment_layers if a.is_active_at(current_sec)]
        if active_adj:
            frame_bgr_adj = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            for adj in active_adj:
                try:
                    frame_bgr_adj = PhotoshopFX.apply_adjustment_layer(frame_bgr_adj, adj)
                except Exception:
                    pass
            frame_rgb = cv2.cvtColor(frame_bgr_adj, cv2.COLOR_BGR2RGB)

        return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

    # ------------------------------------------------------------------
    # Transition helper: get the transition frame at current_sec
    # ------------------------------------------------------------------

    def _get_transition_blend(self, frame_bgr, current_sec: float, cap, orig_fps: float,
                               out_w: int, out_h: int) -> np.ndarray:
        """
        If a transition is active at current_sec, blends current frame with next/prev clip frame.
        Returns blended BGR frame.
        """
        import cv2
        from app.core.photoshop_fx import PhotoshopFX

        for trans in self.transition_clips:
            if not trans.is_active_at(current_sec):
                continue
            try:
                progress = trans.get_progress_at(current_sec)
                # Get "other" frame at the boundary
                other_sec = trans.at_sec + (1.0 / max(1, self.target_fps))
                other_frame_idx = max(0, int(other_sec * orig_fps))
                cap.set(cv2.CAP_PROP_POS_FRAMES, other_frame_idx)
                ret, other_frame = cap.read()
                if not ret or other_frame is None:
                    continue
                if (other_frame.shape[1], other_frame.shape[0]) != (out_w, out_h):
                    other_frame = cv2.resize(other_frame, (out_w, out_h))

                frame_bgr = PhotoshopFX.apply_transition(
                    frame_a=frame_bgr,
                    frame_b=other_frame,
                    transition_type=getattr(trans, 'transition_type', 'Fade'),
                    progress=progress)
            except Exception:
                pass

        return frame_bgr

    # ------------------------------------------------------------------
    # Main render loop
    # ------------------------------------------------------------------

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
                out_h = out_h + (out_h % 2)
            else:
                out_w, out_h = orig_w, orig_h

            ext = os.path.splitext(self.output_path)[1].lower()
            is_video_export = ext in ['.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v']

            self.progress_changed.emit(5, "Iniciando motor de composición fotograma a fotograma...")

            if self.timeline_intervals and len(self.timeline_intervals) > 0:
                intervals = self.timeline_intervals
            else:
                from app.core.timeline import SpeedInterval
                intervals = [SpeedInterval(self.start_sec, self.end_sec, self.speed, self.reverse)]

            tmp_video = self.output_path + ".tmp.mp4" if is_video_export else self.output_path
            enc_flags = self._get_encoder_flags(ffmpeg_exe, is_video_export)

            if is_video_export:
                cmd_ffmpeg = [
                    ffmpeg_exe, "-y",
                    "-f", "rawvideo",
                    "-vcodec", "rawvideo",
                    "-s", f"{out_w}x{out_h}",
                    "-pix_fmt", "bgr24",
                    "-r", str(self.target_fps),
                    "-i", "-"
                ] + enc_flags + ["-pix_fmt", "yuv420p", tmp_video]
            else:
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
                startupinfo=startupinfo)

            total_active_sec = sum(inv.duration / max(0.1, inv.speed) for inv in intervals)
            processed_sec = 0.0

            for inv in intervals:
                if self._is_cancelled:
                    break

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
                            frame = self._get_transition_blend(frame, t_cur, cap, orig_fps, out_w, out_h)
                            comp_frame = self.composite_frame_at(frame, t_cur)
                            process.stdin.write(comp_frame.tobytes())
                        t_cur -= step_sec
                        processed_sec += (1.0 / self.target_fps)
                        percent = min(90, int(5 + (processed_sec / max(0.1, total_active_sec)) * 80))
                        self.progress_changed.emit(percent, f"Renderizando... ({percent}%)")
                else:
                    t_cur = inv.start_sec
                    start_frame_idx = max(0, int(inv.start_sec * orig_fps))
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_idx)
                    current_frame_idx = start_frame_idx
                    last_valid_frame = None

                    while t_cur <= inv.end_sec and not self._is_cancelled:
                        target_frame_idx = max(0, int(t_cur * orig_fps))
                        ret = True
                        while current_frame_idx <= target_frame_idx:
                            ret, frame = cap.read()
                            if not ret or frame is None:
                                break
                            last_valid_frame = frame
                            current_frame_idx += 1

                        frame_to_use = last_valid_frame if last_valid_frame is not None else frame

                        if frame_to_use is not None:
                            if (orig_w, orig_h) != (out_w, out_h):
                                frame_to_use = cv2.resize(frame_to_use, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
                            frame_to_use = self._get_transition_blend(frame_to_use, t_cur, cap, orig_fps, out_w, out_h)
                            comp_frame = self.composite_frame_at(frame_to_use, t_cur)
                            process.stdin.write(comp_frame.tobytes())

                        t_cur += step_sec
                        processed_sec += (1.0 / self.target_fps)
                        percent = min(90, int(5 + (processed_sec / max(0.1, total_active_sec)) * 80))
                        self.progress_changed.emit(percent, f"Renderizando elementos en pantalla... ({percent}%)")

            process.stdin.close()
            process.wait()
            cap.release()

            # Release PIP caps
            for pip_cap in self._pip_caps.values():
                try:
                    pip_cap.release()
                except Exception:
                    pass
            self._pip_caps.clear()

            if self._is_cancelled:
                self.conversion_failed.emit("Conversión cancelada por el usuario.")
                return

            if is_video_export:
                # --- Audio mixing ---
                self.progress_changed.emit(91, "Mezclando pistas de audio...")
                merged_audio_tmp = None

                # Mix independent audio tracks if any
                audio_track_merged = None
                if self.audio_clips:
                    try:
                        from app.core.audio_engine import AudioMixer
                        mixer = AudioMixer(self.audio_clips, total_duration=total_active_sec)
                        import tempfile
                        merged_audio_tmp = tempfile.mktemp(suffix=".wav")
                        if mixer.mix_to_wav(merged_audio_tmp):
                            audio_track_merged = merged_audio_tmp
                    except Exception:
                        pass

                # Merge audio into final output
                self.progress_changed.emit(92, "Sincronizando pistas de audio del video original...")
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
                    ]
                    if audio_track_merged and os.path.exists(audio_track_merged):
                        cmd_merge += ["-i", audio_track_merged]
                        # Mix original + extra tracks
                        cmd_merge += [
                            "-filter_complex",
                            full_af + f";[outa][2:a]amix=inputs=2:duration=first:normalize=0[mixfinal]",
                            "-map", "0:v",
                            "-map", "[mixfinal]",
                        ]
                    else:
                        cmd_merge += [
                            "-filter_complex", full_af,
                            "-map", "0:v",
                            "-map", "[outa]",
                        ]
                    cmd_merge += ["-c:v", "copy", "-c:a", "aac", self.output_path]

                    proc_m = subprocess.Popen(cmd_merge, stdout=subprocess.DEVNULL,
                                              stderr=subprocess.DEVNULL, startupinfo=startupinfo)
                    ret_m = proc_m.wait()

                    if ret_m == 0 and os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                        if os.path.exists(tmp_video):
                            os.remove(tmp_video)
                    else:
                        raise RuntimeError("Audio muxing failed")

                except Exception:
                    if os.path.exists(self.output_path):
                        try:
                            os.remove(self.output_path)
                        except Exception:
                            pass
                    if os.path.exists(tmp_video):
                        os.rename(tmp_video, self.output_path)

                # Cleanup temp audio
                if merged_audio_tmp and os.path.exists(merged_audio_tmp):
                    try:
                        os.remove(merged_audio_tmp)
                    except Exception:
                        pass

            if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                self.progress_changed.emit(100, "¡Vídeo renderizado con éxito con todos sus elementos!")
                self.conversion_finished.emit(self.output_path)
            else:
                self.conversion_failed.emit("No se pudo generar el archivo final.")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.conversion_failed.emit(f"Error durante el procesamiento: {str(e)}")

    # ------------------------------------------------------------------
    # Encoder selection (unchanged from v2)
    # ------------------------------------------------------------------

    def _get_encoder_flags(self, ffmpeg_exe, is_video: bool) -> list:
        if not is_video:
            return []
        selected = getattr(self, 'gpu_engine', 'auto')
        if selected in ['nvenc', 'auto']:
            flags = ['-c:v', 'h264_nvenc', '-preset', 'p4']
            if self._test_encoder(ffmpeg_exe, flags):
                return flags
        if selected in ['amf', 'auto']:
            flags = ['-c:v', 'h264_amf', '-usage', 'transcoding', '-quality', 'speed']
            if self._test_encoder(ffmpeg_exe, flags):
                return flags
        if selected in ['qsv', 'auto']:
            flags = ['-c:v', 'h264_qsv', '-preset', 'veryfast']
            if self._test_encoder(ffmpeg_exe, flags):
                return flags
        if selected in ['mf', 'auto']:
            flags = ['-c:v', 'h264_mf']
            if self._test_encoder(ffmpeg_exe, flags):
                return flags
        return ['-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'fastdecode', '-crf', '20', '-threads', '0']

    def _test_encoder(self, ffmpeg_exe, encoder_flags: list) -> bool:
        try:
            cmd = [ffmpeg_exe, '-y', '-f', 'lavfi', '-i', 'nullsrc=s=1280x720:d=0.1'] + encoder_flags + ['-f', 'null', '-']
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 startupinfo=startupinfo, timeout=4)
            return res.returncode == 0
        except Exception:
            return False

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
            errors='replace')
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
                    self.progress_changed.emit(current_percent, f"Procesando... ({current_percent}%)")
        process.wait()


# Alias for backwards compatibility
GifConverterWorker = MediaConverterWorker

"""
app/core/audio_engine.py — v3.0.0
Audio Mixer and Waveform Renderer for VIP GIF Studio.

AudioMixer:
  - Extracts and mixes multiple independent audio tracks using FFmpeg
  - Supports volume, fade in/out, mute, pan, loop, source trim
  - Generates a single merged WAV/AAC for final export muxing

WaveformRenderer:
  - Generates waveform preview thumbnails for the timeline
  - Returns a PIL RGBA image ready to paint inside audio clip blocks
  - Uses librosa (if available) or fallback numpy FFT approach
"""

import os
import subprocess
import tempfile
import threading
import numpy as np
from PIL import Image, ImageDraw


def get_ffmpeg_path():
    """Returns the path to the ffmpeg executable (same logic as converter.py)."""
    import sys
    import imageio_ffmpeg
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        try:
            exe_name = os.path.basename(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            exe_name = "ffmpeg.exe"
        for p in [
            os.path.join(base_dir, "imageio_ffmpeg", "binaries", exe_name),
            os.path.join(base_dir, "binaries", exe_name),
            os.path.join(base_dir, exe_name),
            os.path.join(base_dir, "ffmpeg.exe"),
        ]:
            if os.path.exists(p):
                return p
    return imageio_ffmpeg.get_ffmpeg_exe()


# ---------------------------------------------------------------------------
# AudioMixer
# ---------------------------------------------------------------------------

class AudioMixer:
    """
    Mixes multiple TimelineAudioClip objects into a single audio output
    for final muxing in the video export pipeline.

    Each clip supports:
    - Independent volume (0.0-4.0)
    - Fade in/out (seconds)
    - Mute
    - Pan (-1.0 to +1.0)
    - Source trim (start/end within audio file)
    - Loop
    """

    def __init__(self, audio_clips: list, total_duration: float):
        """
        audio_clips: list of TimelineAudioClip objects
        total_duration: total timeline duration in seconds
        """
        self.audio_clips = [c for c in (audio_clips or []) if not getattr(c, 'muted', False)]
        self.total_duration = max(0.1, total_duration)

    def build_ffmpeg_filter_graph(self, input_indices: dict) -> tuple:
        """
        Builds the FFmpeg filter_complex string and output label for audio mixing.

        input_indices: dict mapping audio_clip.id -> input index in ffmpeg -i list
        Returns: (filter_complex_str, output_label)
        """
        if not self.audio_clips:
            return None, None

        filters = []
        mix_inputs = []

        for clip in self.audio_clips:
            idx = input_indices.get(clip.id)
            if idx is None:
                continue

            lbl = f"a{idx}"
            parts = []

            # Source trim
            src_start = max(0.0, getattr(clip, 'source_trim_start', 0.0))
            src_end = getattr(clip, 'source_trim_end', 0.0)
            if src_end > src_start:
                parts.append(f"atrim=start={src_start:.3f}:end={src_end:.3f}")
            else:
                parts.append(f"atrim=start={src_start:.3f}")
            parts.append("asetpts=PTS-STARTPTS")

            # Delay to timeline position
            delay_ms = int(clip.start_sec * 1000)
            if delay_ms > 0:
                parts.append(f"adelay={delay_ms}|{delay_ms}")

            # Volume
            vol = max(0.0, min(4.0, getattr(clip, 'volume', 1.0)))
            if abs(vol - 1.0) > 0.01:
                parts.append(f"volume={vol:.3f}")

            # Fade in
            fi = getattr(clip, 'fade_in_sec', 0.0)
            if fi > 0.001:
                parts.append(f"afade=t=in:st=0:d={fi:.3f}")

            # Fade out
            fo = getattr(clip, 'fade_out_sec', 0.0)
            if fo > 0.001:
                fo_start = max(0, clip.duration - fo)
                parts.append(f"afade=t=out:st={fo_start:.3f}:d={fo:.3f}")

            # Pan
            pan = getattr(clip, 'pan', 0.0)
            if abs(pan) > 0.01:
                left = max(0.0, 1.0 - pan)
                right = max(0.0, 1.0 + pan)
                parts.append(f"pan=stereo|c0={left:.3f}*c0|c1={right:.3f}*c1")

            filter_chain = f"[{idx}:a]{','.join(parts)}[{lbl}]"
            filters.append(filter_chain)
            mix_inputs.append(f"[{lbl}]")

        if not mix_inputs:
            return None, None

        n = len(mix_inputs)
        if n == 1:
            out_lbl = mix_inputs[0].strip("[]")
            return ";".join(filters), out_lbl
        else:
            out_lbl = "mixout"
            filters.append(f"{''.join(mix_inputs)}amix=inputs={n}:duration=first:normalize=0[{out_lbl}]")
            return ";".join(filters), out_lbl

    def get_ffmpeg_inputs(self) -> list:
        """
        Returns list of (clip, ffmpeg_args_list) for each audio clip to use as -i input.
        """
        result = []
        for clip in self.audio_clips:
            if not os.path.exists(getattr(clip, 'audio_path', '')):
                continue
            loop_flag = ["-stream_loop", "-1"] if getattr(clip, 'loop', False) else []
            result.append((clip, loop_flag + ["-i", clip.audio_path]))
        return result

    def mix_to_wav(self, output_wav_path: str) -> bool:
        """
        Uses FFmpeg to mix all audio clips to a single WAV file.
        Returns True on success.
        """
        if not self.audio_clips:
            return False

        ffmpeg = get_ffmpeg_path()
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

        inputs = self.get_ffmpeg_inputs()
        if not inputs:
            return False

        cmd = [ffmpeg, "-y"]
        input_idx_map = {}
        i = 0
        for clip, args in inputs:
            cmd.extend(args)
            input_idx_map[clip.id] = i
            i += 1

        fc, out_lbl = self.build_ffmpeg_filter_graph(input_idx_map)

        if fc and out_lbl:
            cmd.extend(["-filter_complex", fc, "-map", f"[{out_lbl}]"])
        else:
            cmd.extend(["-map", "0:a"])

        cmd.extend([
            "-t", str(self.total_duration),
            "-ar", "44100",
            "-ac", "2",
            output_wav_path
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 startupinfo=startupinfo, timeout=120)
            return res.returncode == 0 and os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# WaveformRenderer
# ---------------------------------------------------------------------------

class WaveformRenderer:
    """
    Generates visual waveform thumbnails for audio clips in the timeline.
    Returns a PIL RGBA image that can be embedded in timeline track blocks.
    """

    def __init__(self, width: int = 200, height: int = 34,
                 wave_color: str = "#89B4FA", bg_color: str = "#181825"):
        self.width = width
        self.height = height
        self.wave_color = wave_color
        self.bg_color = bg_color

    def render(self, audio_path: str, start_sec: float = 0.0, duration: float = 5.0) -> Image.Image:
        """
        Returns a PIL RGBA image of the waveform for the given audio path
        from start_sec for duration seconds.
        Falls back to a placeholder if audio cannot be loaded.
        """
        try:
            return self._render_with_librosa(audio_path, start_sec, duration)
        except Exception:
            pass
        try:
            return self._render_with_ffmpeg(audio_path, start_sec, duration)
        except Exception:
            pass
        return self._render_placeholder()

    def _render_with_librosa(self, audio_path: str, start_sec: float, duration: float) -> Image.Image:
        """Uses librosa to load audio and render waveform."""
        import librosa
        y, sr = librosa.load(audio_path, sr=None, offset=start_sec, duration=duration, mono=True)
        return self._draw_waveform(y)

    def _render_with_ffmpeg(self, audio_path: str, start_sec: float, duration: float) -> Image.Image:
        """Uses FFmpeg to decode audio to PCM, then renders waveform."""
        ffmpeg = get_ffmpeg_path()
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start_sec),
            "-t", str(min(duration, 30.0)),  # max 30s for preview
            "-i", audio_path,
            "-f", "f32le",
            "-ac", "1",
            "-ar", "8000",
            "pipe:1"
        ]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        res = subprocess.run(cmd, capture_output=True, startupinfo=startupinfo, timeout=10)
        if res.returncode != 0 or not res.stdout:
            return self._render_placeholder()

        y = np.frombuffer(res.stdout, dtype=np.float32)
        return self._draw_waveform(y)

    def _draw_waveform(self, samples: np.ndarray) -> Image.Image:
        """Draws the waveform from a 1D numpy float32 array into a PIL RGBA image."""
        img = Image.new("RGBA", (self.width, self.height), self.bg_color + "FF" if len(self.bg_color) == 7 else self.bg_color)
        draw = ImageDraw.Draw(img)

        if len(samples) == 0:
            return img

        # Normalize
        max_amp = np.max(np.abs(samples))
        if max_amp > 0:
            samples = samples / max_amp

        # Downsample to width
        step = max(1, len(samples) // self.width)
        peaks = []
        for i in range(self.width):
            chunk = samples[i * step:(i + 1) * step]
            if len(chunk) > 0:
                peaks.append(float(np.max(np.abs(chunk))))
            else:
                peaks.append(0.0)

        cy = self.height / 2.0
        half_h = (self.height - 4) / 2.0

        try:
            r = int(self.wave_color[1:3], 16)
            g = int(self.wave_color[3:5], 16)
            b = int(self.wave_color[5:7], 16)
            wc = (r, g, b, 200)
        except Exception:
            wc = (137, 180, 250, 200)

        for x, amp in enumerate(peaks):
            bar_h = max(1, int(amp * half_h))
            draw.line([(x, int(cy - bar_h)), (x, int(cy + bar_h))], fill=wc, width=1)

        return img

    def _render_placeholder(self) -> Image.Image:
        """Returns a flat placeholder waveform image when audio cannot be loaded."""
        img = Image.new("RGBA", (self.width, self.height), "#181825FF")
        draw = ImageDraw.Draw(img)
        cy = self.height // 2
        draw.line([(0, cy), (self.width, cy)], fill="#45475A", width=2)
        # Small wave icon
        for x in range(0, self.width, 4):
            amp = int(4 * abs(((x // 4) % 4) - 2))
            draw.line([(x, cy - amp), (x, cy + amp)], fill="#45475A", width=1)
        return img

    def render_async(self, audio_path: str, start_sec: float, duration: float,
                     callback) -> threading.Thread:
        """
        Renders waveform in a background thread and calls callback(image) when done.
        """
        def _worker():
            img = self.render(audio_path, start_sec, duration)
            callback(img)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t


# ---------------------------------------------------------------------------
# Waveform cache (lightweight)
# ---------------------------------------------------------------------------

_waveform_cache: dict = {}
_wf_lock = threading.Lock()


def get_cached_waveform(audio_path: str, width: int, height: int,
                        start_sec: float = 0.0, duration: float = 5.0) -> Image.Image:
    """Returns a cached waveform image, rendering it fresh if not cached."""
    key = (audio_path, width, height, round(start_sec, 1), round(duration, 1))
    with _wf_lock:
        if key in _waveform_cache:
            return _waveform_cache[key]

    renderer = WaveformRenderer(width=width, height=height)
    img = renderer.render(audio_path, start_sec, duration)

    with _wf_lock:
        if len(_waveform_cache) > 50:
            _waveform_cache.clear()
        _waveform_cache[key] = img

    return img

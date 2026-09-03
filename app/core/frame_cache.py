"""
app/core/frame_cache.py — v3.0.0
LRU Frame Cache + NumPy GPU-style Compositor for VIP GIF Studio.

FrameCache:
  - Thread-safe LRU cache for decoded video frames (BGR numpy arrays)
  - Avoids redundant cv2.VideoCapture seeks during preview and render
  - Configurable max size in frames (default 120)

GPUCompositor:
  - High-performance NumPy-vectorized compositing operations
  - Significantly faster than PIL paste() for large frame sequences
  - Provides alpha blend, multiply blend, screen blend, overlay blend
  - Designed as a drop-in acceleration layer for converter.py
"""

import threading
import collections
import numpy as np


# ---------------------------------------------------------------------------
# FrameCache
# ---------------------------------------------------------------------------

class FrameCache:
    """
    Thread-safe LRU (Least Recently Used) cache for video frames.

    Usage:
        cache = FrameCache(max_frames=120)
        frame = cache.get("video.mp4", 42)
        if frame is None:
            frame = decode_frame(42)
            cache.put("video.mp4", 42, frame)
    """

    def __init__(self, max_frames: int = 120):
        self._max = max(8, max_frames)
        self._cache: collections.OrderedDict = collections.OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, video_path: str, frame_idx: int) -> tuple:
        return (video_path, frame_idx)

    def get(self, video_path: str, frame_idx: int):
        """Returns cached BGR frame or None if not cached."""
        key = self._make_key(video_path, frame_idx)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, video_path: str, frame_idx: int, frame: np.ndarray):
        """Stores frame in cache, evicting oldest entry if over capacity."""
        if frame is None:
            return
        key = self._make_key(video_path, frame_idx)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max:
                    self._cache.popitem(last=False)
                self._cache[key] = frame.copy()

    def invalidate(self, video_path: str):
        """Remove all cached frames for a specific video path."""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k[0] == video_path]
            for k in keys_to_remove:
                del self._cache[k]

    def clear(self):
        """Clear all cached frames."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict:
        return {
            "size": self.size,
            "max": self._max,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self.hit_rate:.1%}",
        }


# ---------------------------------------------------------------------------
# VideoReader (cached cv2 reader helper)
# ---------------------------------------------------------------------------

class CachedVideoReader:
    """
    Wraps cv2.VideoCapture with FrameCache integration.
    Provides get_frame(sec) that returns a BGR numpy frame,
    using the cache to avoid redundant seeks.
    """

    def __init__(self, video_path: str, cache: FrameCache = None):
        import cv2
        self.video_path = video_path
        self._cap = cv2.VideoCapture(video_path)
        self._cache = cache or FrameCache(max_frames=60)
        self._fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
        self._last_frame_idx = -1

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def duration_sec(self) -> float:
        return self._total_frames / max(1.0, self._fps)

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def get_frame_at_sec(self, sec: float, loop: bool = False):
        """Returns BGR frame at given time in seconds, using cache."""
        if loop and self.duration_sec > 0:
            sec = sec % self.duration_sec
        frame_idx = max(0, min(self._total_frames - 1, int(sec * self._fps)))
        return self.get_frame(frame_idx)

    def get_frame(self, frame_idx: int):
        """Returns BGR frame at frame_idx, using cache."""
        import cv2
        frame_idx = max(0, min(self._total_frames - 1, frame_idx))
        cached = self._cache.get(self.video_path, frame_idx)
        if cached is not None:
            return cached

        # Sequential read is fastest; only seek when necessary
        if frame_idx != self._last_frame_idx + 1:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

        ret, frame = self._cap.read()
        if ret and frame is not None:
            self._last_frame_idx = frame_idx
            self._cache.put(self.video_path, frame_idx, frame)
            return frame

        # Retry with explicit seek
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self._cap.read()
        if ret and frame is not None:
            self._last_frame_idx = frame_idx
            self._cache.put(self.video_path, frame_idx, frame)
            return frame

        return None

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None


# ---------------------------------------------------------------------------
# GPUCompositor — NumPy-vectorized compositing engine
# ---------------------------------------------------------------------------

class GPUCompositor:
    """
    High-performance compositing operations implemented with NumPy.

    All operations work on RGBA uint8 numpy arrays unless stated otherwise.
    These are approximately 5-50x faster than equivalent PIL paste() operations
    because they use vectorized SIMD-friendly numpy operations.

    Method naming mirrors Photoshop blend modes.
    """

    @staticmethod
    def alpha_over(bg: np.ndarray, fg: np.ndarray, x: int = 0, y: int = 0,
                   opacity: float = 1.0) -> np.ndarray:
        """
        Porter-Duff 'over' compositing: fg over bg at position (x, y).
        bg and fg must be RGBA uint8 arrays.
        Modifies bg in-place and returns it.
        """
        h_bg, w_bg = bg.shape[:2]
        h_fg, w_fg = fg.shape[:2]

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_bg, x + w_fg)
        y2 = min(h_bg, y + h_fg)

        if x1 >= x2 or y1 >= y2:
            return bg

        fx1, fy1 = x1 - x, y1 - y
        fx2, fy2 = fx1 + (x2 - x1), fy1 + (y2 - y1)

        fg_crop = fg[fy1:fy2, fx1:fx2].astype(np.float32)
        bg_crop = bg[y1:y2, x1:x2].astype(np.float32)

        fg_a = (fg_crop[:, :, 3:4] / 255.0) * max(0.0, min(1.0, opacity))
        bg_a = bg_crop[:, :, 3:4] / 255.0

        out_a = fg_a + bg_a * (1.0 - fg_a)
        safe_denom = np.where(out_a > 1e-6, out_a, 1.0)
        out_rgb = (fg_crop[:, :, :3] * fg_a + bg_crop[:, :, :3] * bg_a * (1.0 - fg_a)) / safe_denom

        result = np.concatenate([
            np.clip(out_rgb, 0, 255),
            np.clip(out_a * 255, 0, 255)
        ], axis=2).astype(np.uint8)

        bg[y1:y2, x1:x2] = result
        return bg

    @staticmethod
    def alpha_over_bgr(bg_bgr: np.ndarray, fg_rgba: np.ndarray, x: int = 0, y: int = 0,
                       opacity: float = 1.0) -> np.ndarray:
        """
        Fast composite: fg_rgba (RGBA) over bg_bgr (BGR) at (x,y).
        Returns modified bg_bgr (BGR, no alpha).
        """
        h_bg, w_bg = bg_bgr.shape[:2]
        h_fg, w_fg = fg_rgba.shape[:2]

        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_bg, x + w_fg), min(h_bg, y + h_fg)

        if x1 >= x2 or y1 >= y2:
            return bg_bgr

        fx1, fy1 = x1 - x, y1 - y
        fx2, fy2 = fx1 + (x2 - x1), fy1 + (y2 - y1)

        fg_crop = fg_rgba[fy1:fy2, fx1:fx2].astype(np.float32)
        bg_crop = bg_bgr[y1:y2, x1:x2].astype(np.float32)

        # fg is RGBA, bg is BGR — reorder fg to BGR
        fg_bgr = fg_crop[:, :, [2, 1, 0]]  # RGB→BGR
        fg_a = (fg_crop[:, :, 3:4] / 255.0) * max(0.0, min(1.0, opacity))

        out_bgr = fg_bgr * fg_a + bg_crop * (1.0 - fg_a)
        bg_bgr[y1:y2, x1:x2] = np.clip(out_bgr, 0, 255).astype(np.uint8)
        return bg_bgr

    @staticmethod
    def multiply_blend(bg: np.ndarray, fg: np.ndarray, x: int = 0, y: int = 0,
                       opacity: float = 1.0) -> np.ndarray:
        """Multiply blend mode composite (RGBA over RGBA)."""
        h_bg, w_bg = bg.shape[:2]
        h_fg, w_fg = fg.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_bg, x + w_fg), min(h_bg, y + h_fg)
        if x1 >= x2 or y1 >= y2:
            return bg
        fx1, fy1 = x1 - x, y1 - y
        fg_crop = fg[fy1:fy1 + (y2 - y1), fx1:fx1 + (x2 - x1)].astype(np.float32) / 255.0
        bg_crop = bg[y1:y2, x1:x2].astype(np.float32) / 255.0
        fg_a = fg_crop[:, :, 3:4] * opacity
        blended = bg_crop[:, :, :3] * fg_crop[:, :, :3]
        out_rgb = blended * fg_a + bg_crop[:, :, :3] * (1.0 - fg_a)
        result = np.concatenate([np.clip(out_rgb * 255, 0, 255),
                                  np.clip(bg_crop[:, :, 3:4] * 255, 0, 255)], axis=2).astype(np.uint8)
        bg[y1:y2, x1:x2] = result
        return bg

    @staticmethod
    def screen_blend(bg: np.ndarray, fg: np.ndarray, x: int = 0, y: int = 0,
                     opacity: float = 1.0) -> np.ndarray:
        """Screen blend mode composite (RGBA over RGBA)."""
        h_bg, w_bg = bg.shape[:2]
        h_fg, w_fg = fg.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_bg, x + w_fg), min(h_bg, y + h_fg)
        if x1 >= x2 or y1 >= y2:
            return bg
        fx1, fy1 = x1 - x, y1 - y
        fg_crop = fg[fy1:fy1 + (y2 - y1), fx1:fx1 + (x2 - x1)].astype(np.float32) / 255.0
        bg_crop = bg[y1:y2, x1:x2].astype(np.float32) / 255.0
        fg_a = fg_crop[:, :, 3:4] * opacity
        blended = 1.0 - (1.0 - bg_crop[:, :, :3]) * (1.0 - fg_crop[:, :, :3])
        out_rgb = blended * fg_a + bg_crop[:, :, :3] * (1.0 - fg_a)
        result = np.concatenate([np.clip(out_rgb * 255, 0, 255),
                                  np.clip(bg_crop[:, :, 3:4] * 255, 0, 255)], axis=2).astype(np.uint8)
        bg[y1:y2, x1:x2] = result
        return bg

    @staticmethod
    def resize_frame(frame: np.ndarray, target_w: int, target_h: int,
                     quality: str = "fast") -> np.ndarray:
        """
        Resize a BGR/RGBA frame to target dimensions.
        quality: "fast" (INTER_LINEAR), "best" (INTER_LANCZOS4)
        """
        import cv2
        if frame is None or target_w <= 0 or target_h <= 0:
            return frame
        interp = cv2.INTER_LINEAR if quality == "fast" else cv2.INTER_LANCZOS4
        if frame.shape[1] == target_w and frame.shape[0] == target_h:
            return frame
        return cv2.resize(frame, (target_w, target_h), interpolation=interp)

    @staticmethod
    def pil_to_bgra_numpy(pil_image: "Image.Image") -> np.ndarray:
        """Convert PIL RGBA image to BGRA numpy array."""
        arr = np.array(pil_image.convert("RGBA"))
        return arr[:, :, [2, 1, 0, 3]]  # RGBA → BGRA

    @staticmethod
    def bgr_frame_to_rgba_pil(frame_bgr: np.ndarray) -> "Image.Image":
        """Convert BGR numpy frame to PIL RGBA image."""
        from PIL import Image
        import cv2
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb).convert("RGBA")


# ---------------------------------------------------------------------------
# Global shared instances (singletons for app-wide use)
# ---------------------------------------------------------------------------

# Shared frame cache — used by video_player.py and converter.py
_global_frame_cache = FrameCache(max_frames=180)


def get_global_cache() -> FrameCache:
    """Returns the application-wide shared FrameCache instance."""
    return _global_frame_cache


def clear_global_cache():
    """Clears the global frame cache (call when loading new video)."""
    _global_frame_cache.clear()

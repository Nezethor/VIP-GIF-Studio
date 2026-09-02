import cv2
import os
from PIL import Image, ImageSequence

class VideoInfo:
    """Helper class to extract metadata and frames from video and GIF files."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.is_valid = False
        self.is_gif = file_path.lower().endswith('.gif')
        self.width = 0
        self.height = 0
        self.fps = 30.0
        self.total_frames = 0
        self.duration = 0.0  # seconds

        self._read_metadata()

    def _read_metadata(self):
        if not self.file_path or not os.path.isfile(self.file_path):
            return

        if self.is_gif:
            try:
                with Image.open(self.file_path) as im:
                    self.width, self.height = im.size
                    self.total_frames = getattr(im, 'n_frames', 1)
                    # Average frame duration in ms
                    durations = []
                    for frame in ImageSequence.Iterator(im):
                        durations.append(frame.info.get('duration', 100))
                    avg_dur_ms = sum(durations) / len(durations) if durations else 100
                    if avg_dur_ms <= 0: avg_dur_ms = 100
                    self.fps = 1000.0 / avg_dur_ms
                    self.duration = (avg_dur_ms * self.total_frames) / 1000.0
                    self.is_valid = True
                    return
            except Exception:
                pass

        cap = cv2.VideoCapture(self.file_path)
        if not cap.isOpened():
            return

        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if self.fps > 0 and self.total_frames > 0:
            self.duration = self.total_frames / self.fps
        else:
            self.duration = 0.0

        if self.width > 0 and self.height > 0 and self.duration > 0:
            self.is_valid = True

        cap.release()

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds into MM:SS.ms"""
        if seconds < 0:
            seconds = 0
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 100)
        return f"{mins:02d}:{secs:02d}.{millis:02d}"

    def get_frame_at_sec(self, sec: float):
        """Retrieve OpenCV BGR image frame at specific time offset in seconds."""
        if not self.is_valid:
            return None

        cap = cv2.VideoCapture(self.file_path)
        if not cap.isOpened():
            return None

        frame_number = int(sec * self.fps)
        frame_number = max(0, min(frame_number, self.total_frames - 1))
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        cap.release()

        if ret:
            return frame
        return None

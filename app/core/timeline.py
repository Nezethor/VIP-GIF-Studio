import uuid

class SpeedInterval:
    """Represents a video segment with a specific speed factor and reverse flag."""
    def __init__(self, start_sec: float, end_sec: float, speed: float = 1.0, reverse: bool = False, label: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.speed = speed
        self.reverse = reverse
        self.label = label or f"{speed:.2f}x"

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)


class TimelineTextClip:
    """Represents an editable text clip placed on a specific timeline track."""
    def __init__(self, text: str = "Texto Rápidos", start_sec: float = 0.0, end_sec: float = 3.0,
                 x_ratio: float = 0.5, y_ratio: float = 0.85, font_size: int = 40,
                 color: str = "#FFFFFF", border_color: str = "#000000", track_index: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.text = text
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.font_size = font_size
        self.color = color
        self.border_color = border_color
        self.track_index = track_index

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def get_scaled_font_size(self, current_height: int) -> int:
        ref_h = 720.0
        scale = max(0.2, current_height / ref_h)
        return max(10, int(self.font_size * scale))


class TimelineImageClip:
    """Represents an overlay image/watermark clip placed on the timeline."""
    def __init__(self, image_path: str, start_sec: float = 0.0, end_sec: float = 5.0,
                 x_ratio: float = 0.85, y_ratio: float = 0.1, scale_factor: float = 0.2, track_index: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.image_path = image_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.scale_factor = scale_factor
        self.track_index = track_index

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

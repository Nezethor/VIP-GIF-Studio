class SubtitleItem:
    """Model representing a subtitle / text overlay with position, timing, and font size."""

    def __init__(self, text: str = "Texto de Subtítulo", start_sec: float = 0.0, end_sec: float = 5.0,
                 x_ratio: float = 0.5, y_ratio: float = 0.8, font_size: int = 36,
                 color: str = "#FFFFFF", border_color: str = "#000000"):
        self.text = text
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.font_size = font_size  # Reference font size at 720p height
        self.color = color
        self.border_color = border_color

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def get_scaled_font_size(self, current_height: int) -> int:
        """Scales font size proportionally relative to reference 720p height."""
        ref_h = 720.0
        scale = max(0.2, current_height / ref_h)
        return max(10, int(self.font_size * scale))


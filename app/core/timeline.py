import uuid
import math


def apply_easing_curve(t: float, curve: str = "Linear") -> float:
    """Calculates easing transition factor t (0.0 to 1.0) according to curve."""
    t = max(0.0, min(1.0, t))
    if not curve or "Linear" in curve or "Lineal" in curve:
        return t
    elif "Ease In-Out" in curve or "Suave Ambos" in curve:
        return (1.0 - math.cos(math.pi * t)) / 2.0
    elif "Ease In" in curve or "Suave Entrada" in curve:
        return t * t
    elif "Ease Out" in curve or "Suave Salida" in curve:
        return t * (2.0 - t)
    elif "Bounce" in curve or "Rebote" in curve:
        if t < (1 / 2.75):
            return 7.5625 * t * t
        elif t < (2 / 2.75):
            t -= (1.5 / 2.75)
            return 7.5625 * t * t + 0.75
        elif t < (2.5 / 2.75):
            t -= (2.25 / 2.75)
            return 7.5625 * t * t + 0.9375
        else:
            t -= (2.625 / 2.75)
            return 7.5625 * t * t + 0.984375
    return t


class SpeedInterval:
    """Represents a main video segment with a specific speed factor and reverse flag."""
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
    """Represents an editable text clip placed on a timeline track."""
    def __init__(self, text: str = "Texto Rápido", start_sec: float = 0.0, end_sec: float = 3.0,
                 x_ratio: float = 0.5, y_ratio: float = 0.85, font_size: int = 40,
                 color: str = "#FFFFFF", border_color: str = "#000000", track_index: int = 0, layer_z: int = 10):
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
        self.layer_z = layer_z

        # Keyframe Animation Attributes & Multi-node list
        self.enable_keyframes = False
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_font_size = font_size
        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_font_size = font_size

        self.keyframe_nodes = []

        # Photoshop Effects & Layer Styles
        self.opacity = 1.0
        self.fade_in_sec = 0.0
        self.fade_out_sec = 0.0
        self.blend_mode = "Normal"
        self.filter_type = "Normal"
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.blur_radius = 0.0
        self.drop_shadow = True
        self.rotation = 0.0
        self.easing_curve = "Linear"

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def add_keyframe_node(self, sec: float, x_ratio: float = None, y_ratio: float = None, width_ratio: float = None, height_ratio: float = None, font_size: int = None):
        self.enable_keyframes = True
        sec = max(self.start_sec, min(self.end_sec, sec))
        cur_x, cur_y, cur_w, cur_h, cur_fs = self.get_transform_at(sec)
        
        node = {
            'sec': sec,
            'x_ratio': cur_x if x_ratio is None else x_ratio,
            'y_ratio': cur_y if y_ratio is None else y_ratio,
            'width_ratio': cur_w if width_ratio is None else width_ratio,
            'height_ratio': cur_h if height_ratio is None else height_ratio,
            'font_size': cur_fs if font_size is None else font_size
        }
        
        if not hasattr(self, 'keyframe_nodes') or not self.keyframe_nodes:
            self.keyframe_nodes = [
                {'sec': self.start_sec, 'x_ratio': self.start_x_ratio, 'y_ratio': self.start_y_ratio, 'width_ratio': 0.3, 'height_ratio': 0.3, 'font_size': self.start_font_size},
                {'sec': self.end_sec, 'x_ratio': self.end_x_ratio, 'y_ratio': self.end_y_ratio, 'width_ratio': 0.3, 'height_ratio': 0.3, 'font_size': self.end_font_size}
            ]
        
        self.keyframe_nodes = [n for n in self.keyframe_nodes if abs(n['sec'] - sec) > 0.05]
        self.keyframe_nodes.append(node)
        self.keyframe_nodes.sort(key=lambda n: n['sec'])

    def get_transform_at(self, current_sec: float):
        if not getattr(self, 'enable_keyframes', False):
            return self.x_ratio, self.y_ratio, 0.3, 0.3, self.font_size
        
        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes:
            return self.x_ratio, self.y_ratio, 0.3, 0.3, self.font_size

        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))
        if len(sorted_nodes) == 1:
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                0.3, 0.3,
                n0.get('font_size', self.font_size)
            )

        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                0.3, 0.3,
                n0.get('font_size', self.font_size)
            )
        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            n_last = sorted_nodes[-1]
            return (
                n_last.get('x_ratio', n_last.get('x', self.x_ratio)),
                n_last.get('y_ratio', n_last.get('y', self.y_ratio)),
                0.3, 0.3,
                n_last.get('font_size', self.font_size)
            )
        
        for i in range(len(sorted_nodes) - 1):
            n1 = sorted_nodes[i]
            n2 = sorted_nodes[i+1]
            s1 = n1.get('sec', self.start_sec)
            s2 = n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                dur = max(0.001, s2 - s1)
                t = (current_sec - s1) / dur
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))
                x1 = n1.get('x_ratio', n1.get('x', self.x_ratio))
                x2 = n2.get('x_ratio', n2.get('x', self.x_ratio))
                y1 = n1.get('y_ratio', n1.get('y', self.y_ratio))
                y2 = n2.get('y_ratio', n2.get('y', self.y_ratio))
                fs1 = n1.get('font_size', self.font_size)
                fs2 = n2.get('font_size', self.font_size)
                cx = x1 + (x2 - x1) * t
                cy = y1 + (y2 - y1) * t
                cfs = int(fs1 + (fs2 - fs1) * t)
                return cx, cy, 0.3, 0.3, cfs

        return self.x_ratio, self.y_ratio, 0.3, 0.3, self.font_size

    def get_scaled_font_size(self, current_height: int) -> int:
        ref_h = 720.0
        scale = max(0.2, current_height / ref_h)
        return max(10, int(self.font_size * scale))


class TimelineImageClip:
    """Represents an overlay image / watermark clip on the timeline."""
    def __init__(self, image_path: str, start_sec: float = 0.0, end_sec: float = 5.0,
                 x_ratio: float = 0.85, y_ratio: float = 0.1, width_ratio: float = 0.25, height_ratio: float = 0.25,
                 track_index: int = 0, layer_z: int = 5):
        self.id = str(uuid.uuid4())[:8]
        self.image_path = image_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.width_ratio = max(0.05, min(1.0, width_ratio))
        self.height_ratio = max(0.05, min(1.0, height_ratio))
        self.track_index = track_index
        self.layer_z = layer_z

        # Keyframe Animation Attributes & Multi-node list
        self.enable_keyframes = False
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_width_ratio = self.width_ratio
        self.start_height_ratio = self.height_ratio

        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_width_ratio = self.width_ratio
        self.end_height_ratio = self.height_ratio

        self.keyframe_nodes = []

        # Photoshop Effects & Layer Styles
        self.opacity = 1.0
        self.fade_in_sec = 0.0
        self.fade_out_sec = 0.0
        self.blend_mode = "Normal"
        self.filter_type = "Normal"
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.blur_radius = 0.0
        self.drop_shadow = False
        self.rotation = 0.0
        self.border_radius = 0
        self.border_width = 0
        self.border_color = "#FFFFFF"
        self.easing_curve = "Linear"

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def add_keyframe_node(self, sec: float, x_ratio: float = None, y_ratio: float = None, width_ratio: float = None, height_ratio: float = None, font_size: int = None):
        self.enable_keyframes = True
        sec = max(self.start_sec, min(self.end_sec, sec))
        cur_x, cur_y, cur_w, cur_h, cur_fs = self.get_transform_at(sec)
        
        node = {
            'sec': sec,
            'x_ratio': cur_x if x_ratio is None else x_ratio,
            'y_ratio': cur_y if y_ratio is None else y_ratio,
            'width_ratio': cur_w if width_ratio is None else width_ratio,
            'height_ratio': cur_h if height_ratio is None else height_ratio,
            'font_size': cur_fs if font_size is None else font_size
        }
        
        if not hasattr(self, 'keyframe_nodes') or not self.keyframe_nodes:
            self.keyframe_nodes = [
                {'sec': self.start_sec, 'x_ratio': self.start_x_ratio, 'y_ratio': self.start_y_ratio, 'width_ratio': self.start_width_ratio, 'height_ratio': self.start_height_ratio, 'font_size': 40},
                {'sec': self.end_sec, 'x_ratio': self.end_x_ratio, 'y_ratio': self.end_y_ratio, 'width_ratio': self.end_width_ratio, 'height_ratio': self.end_height_ratio, 'font_size': 40}
            ]
        
        self.keyframe_nodes = [n for n in self.keyframe_nodes if abs(n['sec'] - sec) > 0.05]
        self.keyframe_nodes.append(node)
        self.keyframe_nodes.sort(key=lambda n: n['sec'])

    def get_transform_at(self, current_sec: float):
        if not getattr(self, 'enable_keyframes', False):
            return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40
        
        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes:
            return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40

        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))
        if len(sorted_nodes) == 1:
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                n0.get('width_ratio', self.width_ratio),
                n0.get('height_ratio', self.height_ratio),
                40
            )

        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                n0.get('width_ratio', self.width_ratio),
                n0.get('height_ratio', self.height_ratio),
                40
            )
        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            n_last = sorted_nodes[-1]
            return (
                n_last.get('x_ratio', n_last.get('x', self.x_ratio)),
                n_last.get('y_ratio', n_last.get('y', self.y_ratio)),
                n_last.get('width_ratio', self.width_ratio),
                n_last.get('height_ratio', self.height_ratio),
                40
            )

        for i in range(len(sorted_nodes) - 1):
            n1 = sorted_nodes[i]
            n2 = sorted_nodes[i+1]
            s1 = n1.get('sec', self.start_sec)
            s2 = n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                dur = max(0.001, s2 - s1)
                t = (current_sec - s1) / dur
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))
                x1 = n1.get('x_ratio', n1.get('x', self.x_ratio))
                x2 = n2.get('x_ratio', n2.get('x', self.x_ratio))
                y1 = n1.get('y_ratio', n1.get('y', self.y_ratio))
                y2 = n2.get('y_ratio', n2.get('y', self.y_ratio))
                w1 = n1.get('width_ratio', self.width_ratio)
                w2 = n2.get('width_ratio', self.width_ratio)
                h1 = n1.get('height_ratio', self.height_ratio)
                h2 = n2.get('height_ratio', self.height_ratio)
                cx = x1 + (x2 - x1) * t
                cy = y1 + (y2 - y1) * t
                cw = w1 + (w2 - w1) * t
                ch = h1 + (h2 - h1) * t
                return cx, cy, cw, ch, 40

        return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40


class TimelineVideoClip:
    """Represents a picture-in-picture secondary video overlay clip on the timeline."""
    def __init__(self, video_path: str, start_sec: float = 0.0, end_sec: float = 5.0,
                 x_ratio: float = 0.05, y_ratio: float = 0.05, width_ratio: float = 0.35, height_ratio: float = 0.35,
                 speed: float = 1.0, reverse: bool = False, track_index: int = 0, layer_z: int = 2):
        self.id = str(uuid.uuid4())[:8]
        self.video_path = video_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.width_ratio = max(0.05, min(1.0, width_ratio))
        self.height_ratio = max(0.05, min(1.0, height_ratio))
        self.speed = speed
        self.reverse = reverse
        self.track_index = track_index
        self.layer_z = layer_z

        # Keyframe Animation Attributes & Multi-node list
        self.enable_keyframes = False
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_width_ratio = self.width_ratio
        self.start_height_ratio = self.height_ratio

        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_width_ratio = self.width_ratio
        self.end_height_ratio = self.height_ratio

        self.keyframe_nodes = []

        # Photoshop Effects & Layer Styles
        self.opacity = 1.0
        self.fade_in_sec = 0.0
        self.fade_out_sec = 0.0
        self.blend_mode = "Normal"
        self.filter_type = "Normal"
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.blur_radius = 0.0
        self.drop_shadow = False
        self.rotation = 0.0
        self.border_radius = 0
        self.border_width = 0
        self.border_color = "#FFFFFF"
        self.easing_curve = "Linear"

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def add_keyframe_node(self, sec: float, x_ratio: float = None, y_ratio: float = None, width_ratio: float = None, height_ratio: float = None, font_size: int = None):
        self.enable_keyframes = True
        sec = max(self.start_sec, min(self.end_sec, sec))
        cur_x, cur_y, cur_w, cur_h, cur_fs = self.get_transform_at(sec)
        
        node = {
            'sec': sec,
            'x_ratio': cur_x if x_ratio is None else x_ratio,
            'y_ratio': cur_y if y_ratio is None else y_ratio,
            'width_ratio': cur_w if width_ratio is None else width_ratio,
            'height_ratio': cur_h if height_ratio is None else height_ratio,
            'font_size': cur_fs if font_size is None else font_size
        }
        
        if not hasattr(self, 'keyframe_nodes') or not self.keyframe_nodes:
            self.keyframe_nodes = [
                {'sec': self.start_sec, 'x_ratio': self.start_x_ratio, 'y_ratio': self.start_y_ratio, 'width_ratio': self.start_width_ratio, 'height_ratio': self.start_height_ratio, 'font_size': 40},
                {'sec': self.end_sec, 'x_ratio': self.end_x_ratio, 'y_ratio': self.end_y_ratio, 'width_ratio': self.end_width_ratio, 'height_ratio': self.end_height_ratio, 'font_size': 40}
            ]
        
        self.keyframe_nodes = [n for n in self.keyframe_nodes if abs(n['sec'] - sec) > 0.05]
        self.keyframe_nodes.append(node)
        self.keyframe_nodes.sort(key=lambda n: n['sec'])

    def get_transform_at(self, current_sec: float):
        if not getattr(self, 'enable_keyframes', False):
            return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40
        
        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes:
            return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40

        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))
        if len(sorted_nodes) == 1:
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                n0.get('width_ratio', self.width_ratio),
                n0.get('height_ratio', self.height_ratio),
                40
            )

        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            n0 = sorted_nodes[0]
            return (
                n0.get('x_ratio', n0.get('x', self.x_ratio)),
                n0.get('y_ratio', n0.get('y', self.y_ratio)),
                n0.get('width_ratio', self.width_ratio),
                n0.get('height_ratio', self.height_ratio),
                40
            )
        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            n_last = sorted_nodes[-1]
            return (
                n_last.get('x_ratio', n_last.get('x', self.x_ratio)),
                n_last.get('y_ratio', n_last.get('y', self.y_ratio)),
                n_last.get('width_ratio', self.width_ratio),
                n_last.get('height_ratio', self.height_ratio),
                40
            )

        for i in range(len(sorted_nodes) - 1):
            n1 = sorted_nodes[i]
            n2 = sorted_nodes[i+1]
            s1 = n1.get('sec', self.start_sec)
            s2 = n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                dur = max(0.001, s2 - s1)
                t = (current_sec - s1) / dur
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))
                x1 = n1.get('x_ratio', n1.get('x', self.x_ratio))
                x2 = n2.get('x_ratio', n2.get('x', self.x_ratio))
                y1 = n1.get('y_ratio', n1.get('y', self.y_ratio))
                y2 = n2.get('y_ratio', n2.get('y', self.y_ratio))
                w1 = n1.get('width_ratio', self.width_ratio)
                w2 = n2.get('width_ratio', self.width_ratio)
                h1 = n1.get('height_ratio', self.height_ratio)
                h2 = n2.get('height_ratio', self.height_ratio)
                cx = x1 + (x2 - x1) * t
                cy = y1 + (y2 - y1) * t
                cw = w1 + (w2 - w1) * t
                ch = h1 + (h2 - h1) * t
                return cx, cy, cw, ch, 40

        return self.x_ratio, self.y_ratio, self.width_ratio, self.height_ratio, 40

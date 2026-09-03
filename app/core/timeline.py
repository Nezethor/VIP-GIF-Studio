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
    elif "Elastic" in curve or "Elástico" in curve:
        if t == 0 or t == 1:
            return t
        p = 0.3
        s = p / 4
        t -= 1
        return -(math.pow(2, 10 * t) * math.sin((t - s) * (2 * math.pi) / p))
    elif "Cubic" in curve or "Cúbico" in curve:
        return t * t * t
    return t


# ---------------------------------------------------------------------------
# Shared mixin for full keyframe interpolation (transform + opacity + rotation)
# ---------------------------------------------------------------------------

class _KeyframeMixin:
    """Mixin that provides add_keyframe_node / get_transform_at for all clip types."""

    def _init_kf_attrs(self):
        self.enable_keyframes = False
        self.keyframe_nodes = []
        self.easing_curve = "Linear"

    def add_keyframe_node(self, sec: float, x_ratio: float = None, y_ratio: float = None,
                          width_ratio: float = None, height_ratio: float = None,
                          font_size: int = None, opacity: float = None,
                          rotation: float = None, scale_x: float = None, scale_y: float = None):
        self.enable_keyframes = True
        sec = max(self.start_sec, min(self.end_sec, sec))
        cur_x, cur_y, cur_w, cur_h, cur_fs = self.get_transform_at(sec)

        node = {
            'sec': sec,
            'x_ratio': cur_x if x_ratio is None else x_ratio,
            'y_ratio': cur_y if y_ratio is None else y_ratio,
            'width_ratio': cur_w if width_ratio is None else width_ratio,
            'height_ratio': cur_h if height_ratio is None else height_ratio,
            'font_size': cur_fs if font_size is None else font_size,
            'opacity': getattr(self, 'opacity', 1.0) if opacity is None else opacity,
            'rotation': getattr(self, 'rotation', 0.0) if rotation is None else rotation,
            'scale_x': getattr(self, 'scale_x', 1.0) if scale_x is None else scale_x,
            'scale_y': getattr(self, 'scale_y', 1.0) if scale_y is None else scale_y,
        }

        if not self.keyframe_nodes:
            self.keyframe_nodes = [
                {
                    'sec': self.start_sec,
                    'x_ratio': getattr(self, 'start_x_ratio', getattr(self, 'x_ratio', 0.5)),
                    'y_ratio': getattr(self, 'start_y_ratio', getattr(self, 'y_ratio', 0.5)),
                    'width_ratio': getattr(self, 'start_width_ratio', getattr(self, 'width_ratio', 0.3)),
                    'height_ratio': getattr(self, 'start_height_ratio', getattr(self, 'height_ratio', 0.3)),
                    'font_size': getattr(self, 'start_font_size', getattr(self, 'font_size', 40)),
                    'opacity': getattr(self, 'opacity', 1.0),
                    'rotation': getattr(self, 'rotation', 0.0),
                    'scale_x': getattr(self, 'scale_x', 1.0),
                    'scale_y': getattr(self, 'scale_y', 1.0),
                },
                {
                    'sec': self.end_sec,
                    'x_ratio': getattr(self, 'end_x_ratio', getattr(self, 'x_ratio', 0.5)),
                    'y_ratio': getattr(self, 'end_y_ratio', getattr(self, 'y_ratio', 0.5)),
                    'width_ratio': getattr(self, 'end_width_ratio', getattr(self, 'width_ratio', 0.3)),
                    'height_ratio': getattr(self, 'end_height_ratio', getattr(self, 'height_ratio', 0.3)),
                    'font_size': getattr(self, 'end_font_size', getattr(self, 'font_size', 40)),
                    'opacity': getattr(self, 'opacity', 1.0),
                    'rotation': getattr(self, 'rotation', 0.0),
                    'scale_x': getattr(self, 'scale_x', 1.0),
                    'scale_y': getattr(self, 'scale_y', 1.0),
                },
            ]

        self.keyframe_nodes = [n for n in self.keyframe_nodes if abs(n.get('sec', 0) - sec) > 0.05]
        self.keyframe_nodes.append(node)
        self.keyframe_nodes.sort(key=lambda n: n.get('sec', 0.0))

    def get_transform_at(self, current_sec: float):
        if not getattr(self, 'enable_keyframes', False):
            return (
                getattr(self, 'x_ratio', 0.5),
                getattr(self, 'y_ratio', 0.5),
                getattr(self, 'width_ratio', 0.3),
                getattr(self, 'height_ratio', 0.3),
                getattr(self, 'font_size', 40),
            )

        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes:
            return (
                getattr(self, 'x_ratio', 0.5),
                getattr(self, 'y_ratio', 0.5),
                getattr(self, 'width_ratio', 0.3),
                getattr(self, 'height_ratio', 0.3),
                getattr(self, 'font_size', 40),
            )

        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))

        def _n_val(n, key, fallback_attr, fallback=0.0):
            return n.get(key, n.get(fallback_attr, getattr(self, fallback_attr, fallback)))

        if len(sorted_nodes) == 1:
            n0 = sorted_nodes[0]
            return (
                _n_val(n0, 'x_ratio', 'x_ratio', 0.5),
                _n_val(n0, 'y_ratio', 'y_ratio', 0.5),
                n0.get('width_ratio', getattr(self, 'width_ratio', 0.3)),
                n0.get('height_ratio', getattr(self, 'height_ratio', 0.3)),
                n0.get('font_size', getattr(self, 'font_size', 40)),
            )

        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            n0 = sorted_nodes[0]
            return (
                _n_val(n0, 'x_ratio', 'x_ratio', 0.5),
                _n_val(n0, 'y_ratio', 'y_ratio', 0.5),
                n0.get('width_ratio', getattr(self, 'width_ratio', 0.3)),
                n0.get('height_ratio', getattr(self, 'height_ratio', 0.3)),
                n0.get('font_size', getattr(self, 'font_size', 40)),
            )

        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            n_last = sorted_nodes[-1]
            return (
                _n_val(n_last, 'x_ratio', 'x_ratio', 0.5),
                _n_val(n_last, 'y_ratio', 'y_ratio', 0.5),
                n_last.get('width_ratio', getattr(self, 'width_ratio', 0.3)),
                n_last.get('height_ratio', getattr(self, 'height_ratio', 0.3)),
                n_last.get('font_size', getattr(self, 'font_size', 40)),
            )

        for i in range(len(sorted_nodes) - 1):
            n1 = sorted_nodes[i]
            n2 = sorted_nodes[i + 1]
            s1 = n1.get('sec', self.start_sec)
            s2 = n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                dur = max(0.001, s2 - s1)
                t = (current_sec - s1) / dur
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))

                def lerp(a, b): return a + (b - a) * t

                cx = lerp(_n_val(n1, 'x_ratio', 'x_ratio', 0.5), _n_val(n2, 'x_ratio', 'x_ratio', 0.5))
                cy = lerp(_n_val(n1, 'y_ratio', 'y_ratio', 0.5), _n_val(n2, 'y_ratio', 'y_ratio', 0.5))
                cw = lerp(n1.get('width_ratio', getattr(self, 'width_ratio', 0.3)),
                          n2.get('width_ratio', getattr(self, 'width_ratio', 0.3)))
                ch = lerp(n1.get('height_ratio', getattr(self, 'height_ratio', 0.3)),
                          n2.get('height_ratio', getattr(self, 'height_ratio', 0.3)))
                cfs = int(lerp(n1.get('font_size', getattr(self, 'font_size', 40)),
                               n2.get('font_size', getattr(self, 'font_size', 40))))
                return cx, cy, cw, ch, cfs

        return (
            getattr(self, 'x_ratio', 0.5),
            getattr(self, 'y_ratio', 0.5),
            getattr(self, 'width_ratio', 0.3),
            getattr(self, 'height_ratio', 0.3),
            getattr(self, 'font_size', 40),
        )

    def get_opacity_at(self, current_sec: float) -> float:
        """Interpolates opacity from keyframe nodes if available."""
        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes or not getattr(self, 'enable_keyframes', False):
            return getattr(self, 'opacity', 1.0)
        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))
        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            return sorted_nodes[0].get('opacity', getattr(self, 'opacity', 1.0))
        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            return sorted_nodes[-1].get('opacity', getattr(self, 'opacity', 1.0))
        for i in range(len(sorted_nodes) - 1):
            n1, n2 = sorted_nodes[i], sorted_nodes[i + 1]
            s1, s2 = n1.get('sec', self.start_sec), n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                t = (current_sec - s1) / max(0.001, s2 - s1)
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))
                o1 = n1.get('opacity', getattr(self, 'opacity', 1.0))
                o2 = n2.get('opacity', getattr(self, 'opacity', 1.0))
                return o1 + (o2 - o1) * t
        return getattr(self, 'opacity', 1.0)

    def get_rotation_at(self, current_sec: float) -> float:
        """Interpolates rotation from keyframe nodes if available."""
        nodes = getattr(self, 'keyframe_nodes', None)
        if not nodes or not getattr(self, 'enable_keyframes', False):
            return getattr(self, 'rotation', 0.0)
        sorted_nodes = sorted(nodes, key=lambda n: n.get('sec', 0.0))
        if current_sec <= sorted_nodes[0].get('sec', self.start_sec):
            return sorted_nodes[0].get('rotation', getattr(self, 'rotation', 0.0))
        if current_sec >= sorted_nodes[-1].get('sec', self.end_sec):
            return sorted_nodes[-1].get('rotation', getattr(self, 'rotation', 0.0))
        for i in range(len(sorted_nodes) - 1):
            n1, n2 = sorted_nodes[i], sorted_nodes[i + 1]
            s1, s2 = n1.get('sec', self.start_sec), n2.get('sec', self.end_sec)
            if s1 <= current_sec <= s2:
                t = (current_sec - s1) / max(0.001, s2 - s1)
                t = apply_easing_curve(t, getattr(self, 'easing_curve', 'Linear'))
                r1 = n1.get('rotation', getattr(self, 'rotation', 0.0))
                r2 = n2.get('rotation', getattr(self, 'rotation', 0.0))
                return r1 + (r2 - r1) * t
        return getattr(self, 'rotation', 0.0)


# ---------------------------------------------------------------------------
# SpeedInterval
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# TimelineTextClip
# ---------------------------------------------------------------------------

class TimelineTextClip(_KeyframeMixin):
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

        # Keyframe start/end references
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_font_size = font_size
        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_font_size = font_size

        self._init_kf_attrs()

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
        self.scale_x = 1.0
        self.scale_y = 1.0

        # Mask support
        self.mask_path = ""
        self.mask_invert = False

        # Group support
        self.group_id = ""

        # Font style
        self.font_bold = False
        self.font_italic = False
        self.font_family = "Arial"
        self.text_align = "center"

        # Transition
        self.transition_in = "None"
        self.transition_out = "None"
        self.transition_duration = 0.5

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def get_scaled_font_size(self, current_height: int) -> int:
        ref_h = 720.0
        scale = max(0.2, current_height / ref_h)
        return max(10, int(self.font_size * scale))


# ---------------------------------------------------------------------------
# TimelineImageClip
# ---------------------------------------------------------------------------

class TimelineImageClip(_KeyframeMixin):
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

        # Keyframe start/end references
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_width_ratio = self.width_ratio
        self.start_height_ratio = self.height_ratio
        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_width_ratio = self.width_ratio
        self.end_height_ratio = self.height_ratio

        self._init_kf_attrs()

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
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.border_radius = 0
        self.border_width = 0
        self.border_color = "#FFFFFF"

        # Mask support
        self.mask_path = ""
        self.mask_invert = False

        # Group support
        self.group_id = ""

        # Slip edit
        self.slip_offset_sec = 0.0

        # Transition
        self.transition_in = "None"
        self.transition_out = "None"
        self.transition_duration = 0.5

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec


# ---------------------------------------------------------------------------
# TimelineVideoClip
# ---------------------------------------------------------------------------

class TimelineVideoClip(_KeyframeMixin):
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

        # Keyframe start/end references
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_width_ratio = self.width_ratio
        self.start_height_ratio = self.height_ratio
        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_width_ratio = self.width_ratio
        self.end_height_ratio = self.height_ratio

        self._init_kf_attrs()

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
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.border_radius = 0
        self.border_width = 0
        self.border_color = "#FFFFFF"

        # Mask support
        self.mask_path = ""
        self.mask_invert = False

        # Group support
        self.group_id = ""

        # Slip edit: offset into the source video
        self.slip_offset_sec = 0.0

        # Transition
        self.transition_in = "None"
        self.transition_out = "None"
        self.transition_duration = 0.5

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec


# ---------------------------------------------------------------------------
# TimelineShapeClip  (NEW)
# ---------------------------------------------------------------------------

class TimelineShapeClip(_KeyframeMixin):
    """
    Represents a vector shape (rectangle, ellipse, triangle, star, line, polygon)
    rendered directly on the timeline — no external file needed.
    """
    SHAPES = ["Rectangle", "Ellipse", "Triangle", "Star", "Line", "Rounded Rectangle", "Arrow", "Hexagon"]

    def __init__(self, shape_type: str = "Rectangle", start_sec: float = 0.0, end_sec: float = 3.0,
                 x_ratio: float = 0.3, y_ratio: float = 0.3, width_ratio: float = 0.4, height_ratio: float = 0.3,
                 fill_color: str = "#CBA6F7", stroke_color: str = "#FFFFFF", stroke_width: int = 2,
                 track_index: int = 0, layer_z: int = 8):
        self.id = str(uuid.uuid4())[:8]
        self.shape_type = shape_type
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.x_ratio = max(0.0, min(1.0, x_ratio))
        self.y_ratio = max(0.0, min(1.0, y_ratio))
        self.width_ratio = max(0.02, min(1.0, width_ratio))
        self.height_ratio = max(0.02, min(1.0, height_ratio))
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width
        self.track_index = track_index
        self.layer_z = layer_z

        # Keyframe start/end references
        self.start_x_ratio = self.x_ratio
        self.start_y_ratio = self.y_ratio
        self.start_width_ratio = self.width_ratio
        self.start_height_ratio = self.height_ratio
        self.end_x_ratio = self.x_ratio
        self.end_y_ratio = self.y_ratio
        self.end_width_ratio = self.width_ratio
        self.end_height_ratio = self.height_ratio

        self._init_kf_attrs()

        # Effects
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
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.corner_radius = 0       # for Rounded Rectangle
        self.star_points = 5         # number of points for Star shape

        # Mask / group
        self.mask_path = ""
        self.mask_invert = False
        self.group_id = ""

        # Transition
        self.transition_in = "None"
        self.transition_out = "None"
        self.transition_duration = 0.5

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_visible_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec


# ---------------------------------------------------------------------------
# TimelineAudioClip  (NEW)
# ---------------------------------------------------------------------------

class TimelineAudioClip:
    """
    Represents an independent audio track clip (music, SFX, voiceover).
    Supports volume, fade in/out, mute, trim in/out, and pan.
    """
    def __init__(self, audio_path: str, start_sec: float = 0.0, end_sec: float = 5.0,
                 volume: float = 1.0, track_index: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.audio_path = audio_path
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.volume = max(0.0, min(4.0, volume))   # 0.0 = mute, 1.0 = original, up to 4.0 = boost
        self.track_index = track_index

        # Trim within the source file
        self.source_trim_start = 0.0   # seconds into the audio file to start reading
        self.source_trim_end = 0.0     # 0.0 = use full file

        # Fade
        self.fade_in_sec = 0.0
        self.fade_out_sec = 0.0

        # Pan: -1.0 = full left, 0.0 = center, +1.0 = full right
        self.pan = 0.0

        # Mute
        self.muted = False

        # Pitch shift (semitones, -12 to +12)
        self.pitch_shift = 0.0

        # Loop the audio clip
        self.loop = False

        # Group
        self.group_id = ""

        # Waveform cache (generated on demand)
        self._waveform_cache = None

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_active_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec


# ---------------------------------------------------------------------------
# TransitionClip  (NEW)
# ---------------------------------------------------------------------------

class TransitionClip:
    """
    Represents a transition effect between two adjacent clips.
    Positioned at the boundary between clip A (ending) and clip B (starting).
    """
    TYPES = [
        "Fade",          # dissolve / cross-fade
        "Wipe Left",     # horizontal wipe from right to left
        "Wipe Right",    # horizontal wipe from left to right
        "Wipe Up",       # vertical wipe upward
        "Wipe Down",     # vertical wipe downward
        "Slide Left",    # slide new clip in from right
        "Slide Right",   # slide new clip in from left
        "Zoom In",       # new clip zooms in
        "Zoom Out",      # old clip zooms out revealing new
        "Dissolve",      # additive dissolve
        "Flash",         # white flash between clips
        "Spin",          # rotate spin
        "Push",          # push old clip out while new comes in
        "Iris",          # circular iris wipe
        "Glitch",        # digital glitch transition
    ]

    def __init__(self, transition_type: str = "Fade", at_sec: float = 1.0,
                 duration: float = 0.5, track_index: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.transition_type = transition_type
        self.at_sec = max(0.0, at_sec)        # center point of transition on timeline
        self.duration = max(0.1, duration)    # total duration of transition (e.g. 0.5s)
        self.track_index = track_index
        self.easing = "Ease In-Out"

    @property
    def start_sec(self) -> float:
        return max(0.0, self.at_sec - self.duration / 2.0)

    @property
    def end_sec(self) -> float:
        return self.at_sec + self.duration / 2.0

    def is_active_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec

    def get_progress_at(self, current_sec: float) -> float:
        """Returns 0.0 (start of transition) to 1.0 (end) at given time."""
        if self.duration <= 0:
            return 1.0
        t = (current_sec - self.start_sec) / self.duration
        return max(0.0, min(1.0, t))


# ---------------------------------------------------------------------------
# AdjustmentLayer  (NEW)
# ---------------------------------------------------------------------------

class AdjustmentLayer:
    """
    A non-destructive adjustment layer applied globally to all layers beneath it.
    No image — purely parameter-based (brightness, contrast, saturation, etc.).
    Similar to Photoshop Adjustment Layers.
    """
    ADJUSTMENT_TYPES = [
        "Brightness/Contrast",
        "Hue/Saturation",
        "Color Balance",
        "Curves (Simulated)",
        "Levels",
        "Exposure",
        "Vibrance",
        "Black & White",
        "Photo Filter",
        "Channel Mixer",
        "Gradient Map",
        "Posterize",
        "Threshold",
        "Vignette",
    ]

    def __init__(self, adjustment_type: str = "Brightness/Contrast",
                 start_sec: float = 0.0, end_sec: float = 5.0, track_index: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.adjustment_type = adjustment_type
        self.start_sec = max(0.0, start_sec)
        self.end_sec = max(self.start_sec + 0.1, end_sec)
        self.track_index = track_index
        self.layer_z = 100   # always on top of all other layers

        # Adjustment parameters (sensible defaults = no effect)
        self.opacity = 1.0
        self.brightness = 1.0
        self.contrast = 1.0
        self.saturation = 1.0
        self.hue_shift = 0.0          # degrees -180 to +180
        self.exposure = 0.0           # stops, -3.0 to +3.0
        self.vibrance = 0.0           # -1.0 to +1.0
        self.blur_radius = 0.0
        self.sharpen = 0.0            # 0.0 to 5.0
        self.vignette_strength = 0.0  # 0.0 = no vignette, 1.0 = full
        self.vignette_radius = 0.75   # 0.0 to 1.0
        self.color_temp = 0.0         # -1.0 (cool) to +1.0 (warm)
        self.tint = 0.0               # -1.0 (magenta) to +1.0 (green)
        self.posterize_levels = 0     # 0 = off, 2-8 = number of levels
        self.threshold_value = 0      # 0 = off, 1-254 = threshold

        # Filter preset
        self.filter_type = "Normal"

        # Blend mode (how the adjustment blends with layers below)
        self.blend_mode = "Normal"

        # Group
        self.group_id = ""

    @property
    def duration(self) -> float:
        return max(0.1, self.end_sec - self.start_sec)

    def is_active_at(self, current_sec: float) -> bool:
        return self.start_sec <= current_sec <= self.end_sec


# ---------------------------------------------------------------------------
# LayerGroup  (NEW)
# ---------------------------------------------------------------------------

class LayerGroup:
    """
    A named group of clip IDs that can be collapsed/expanded in the timeline,
    transformed together, and exported as a Smart Object (cached PNG sequence).
    """
    def __init__(self, name: str = "Grupo", clip_ids: list = None):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.clip_ids = clip_ids or []  # list of clip.id strings
        self.collapsed = False

        # Group-level transform (applied on top of individual clip transforms)
        self.group_x_offset = 0.0
        self.group_y_offset = 0.0
        self.group_scale = 1.0
        self.group_rotation = 0.0
        self.group_opacity = 1.0

        # Smart Object caching
        self.is_smart_object = False
        self.smart_object_cache_path = ""   # path to cached PNG/frame sequence

    def add_clip(self, clip_id: str):
        if clip_id not in self.clip_ids:
            self.clip_ids.append(clip_id)

    def remove_clip(self, clip_id: str):
        if clip_id in self.clip_ids:
            self.clip_ids.remove(clip_id)

import uuid

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
        if not nodes or len(nodes) < 2:
            t = max(0.0, min(1.0, (current_sec - self.start_sec) / max(0.1, self.end_sec - self.start_sec)))
            cur_x = self.start_x_ratio + (self.end_x_ratio - self.start_x_ratio) * t
            cur_y = self.start_y_ratio + (self.end_y_ratio - self.start_y_ratio) * t
            cur_fs = int(self.start_font_size + (self.end_font_size - self.start_font_size) * t)
            return cur_x, cur_y, 0.3, 0.3, cur_fs
        
        if current_sec <= nodes[0]['sec']:
            n0 = nodes[0]
            return n0['x_ratio'], n0['y_ratio'], n0['width_ratio'], n0['height_ratio'], n0['font_size']
        if current_sec >= nodes[-1]['sec']:
            n_last = nodes[-1]
            return n_last['x_ratio'], n_last['y_ratio'], n_last['width_ratio'], n_last['height_ratio'], n_last['font_size']
        
        for i in range(len(nodes) - 1):
            n1 = nodes[i]
            n2 = nodes[i+1]
            if n1['sec'] <= current_sec <= n2['sec']:
                t = (current_sec - n1['sec']) / max(0.001, (n2['sec'] - n1['sec']))
                cx = n1['x_ratio'] + (n2['x_ratio'] - n1['x_ratio']) * t
                cy = n1['y_ratio'] + (n2['y_ratio'] - n1['y_ratio']) * t
                cw = n1['width_ratio'] + (n2['width_ratio'] - n1['width_ratio']) * t
                ch = n1['height_ratio'] + (n2['height_ratio'] - n1['height_ratio']) * t
                cfs = int(n1['font_size'] + (n2['font_size'] - n1['font_size']) * t)
                return cx, cy, cw, ch, cfs

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
        if not nodes or len(nodes) < 2:
            t = max(0.0, min(1.0, (current_sec - self.start_sec) / max(0.1, self.end_sec - self.start_sec)))
            cur_x = self.start_x_ratio + (self.end_x_ratio - self.start_x_ratio) * t
            cur_y = self.start_y_ratio + (self.end_y_ratio - self.start_y_ratio) * t
            cur_w = self.start_width_ratio + (self.end_width_ratio - self.start_width_ratio) * t
            cur_h = self.start_height_ratio + (self.end_height_ratio - self.start_height_ratio) * t
            return cur_x, cur_y, cur_w, cur_h, 40
        
        if current_sec <= nodes[0]['sec']:
            n0 = nodes[0]
            return n0['x_ratio'], n0['y_ratio'], n0['width_ratio'], n0['height_ratio'], n0['font_size']
        if current_sec >= nodes[-1]['sec']:
            n_last = nodes[-1]
            return n_last['x_ratio'], n_last['y_ratio'], n_last['width_ratio'], n_last['height_ratio'], n_last['font_size']
        
        for i in range(len(nodes) - 1):
            n1 = nodes[i]
            n2 = nodes[i+1]
            if n1['sec'] <= current_sec <= n2['sec']:
                t = (current_sec - n1['sec']) / max(0.001, (n2['sec'] - n1['sec']))
                cx = n1['x_ratio'] + (n2['x_ratio'] - n1['x_ratio']) * t
                cy = n1['y_ratio'] + (n2['y_ratio'] - n1['y_ratio']) * t
                cw = n1['width_ratio'] + (n2['width_ratio'] - n1['width_ratio']) * t
                ch = n1['height_ratio'] + (n2['height_ratio'] - n1['height_ratio']) * t
                cfs = int(n1['font_size'] + (n2['font_size'] - n1['font_size']) * t)
                return cx, cy, cw, ch, cfs


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
        if not nodes or len(nodes) < 2:
            t = max(0.0, min(1.0, (current_sec - self.start_sec) / max(0.1, self.end_sec - self.start_sec)))
            cur_x = self.start_x_ratio + (self.end_x_ratio - self.start_x_ratio) * t
            cur_y = self.start_y_ratio + (self.end_y_ratio - self.start_y_ratio) * t
            cur_w = self.start_width_ratio + (self.end_width_ratio - self.start_width_ratio) * t
            cur_h = self.start_height_ratio + (self.end_height_ratio - self.start_height_ratio) * t
            return cur_x, cur_y, cur_w, cur_h, 40
        
        if current_sec <= nodes[0]['sec']:
            n0 = nodes[0]
            return n0['x_ratio'], n0['y_ratio'], n0['width_ratio'], n0['height_ratio'], n0['font_size']
        if current_sec >= nodes[-1]['sec']:
            n_last = nodes[-1]
            return n_last['x_ratio'], n_last['y_ratio'], n_last['width_ratio'], n_last['height_ratio'], n_last['font_size']
        
        for i in range(len(nodes) - 1):
            n1 = nodes[i]
            n2 = nodes[i+1]
            if n1['sec'] <= current_sec <= n2['sec']:
                t = (current_sec - n1['sec']) / max(0.001, (n2['sec'] - n1['sec']))
                cx = n1['x_ratio'] + (n2['x_ratio'] - n1['x_ratio']) * t
                cy = n1['y_ratio'] + (n2['y_ratio'] - n1['y_ratio']) * t
                cw = n1['width_ratio'] + (n2['width_ratio'] - n1['width_ratio']) * t
                ch = n1['height_ratio'] + (n2['height_ratio'] - n1['height_ratio']) * t
                cfs = int(n1['font_size'] + (n2['font_size'] - n1['font_size']) * t)
                return cx, cy, cw, ch, cfs

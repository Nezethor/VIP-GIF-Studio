import os
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QDoubleSpinBox, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint, QPointF
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont,
    QCursor, QMouseEvent, QKeyEvent, QContextMenuEvent, QPolygonF
)

from app.core.photoshop_fx import PhotoshopFX
from app.core.frame_cache import get_global_cache, GPUCompositor
from app.core.video_info import VideoInfo
from app.gui.range_slider import DualRangeSlider
from app.core.timeline import (
    TimelineTextClip, TimelineImageClip, TimelineVideoClip,
    TimelineShapeClip, TimelineAudioClip, TransitionClip, AdjustmentLayer
)


class InteractiveVideoLabel(QLabel):
    """
    Surface interactiva avanzada para el reproductor de video.
    Permite:
      - Clic directo sobre cualquier elemento en pantalla (Texto, Imagen, Video PIP, Forma) para seleccionarlo.
      - Mover arrastrando el cuerpo del elemento (X/Y).
      - Redimensionar usando 4 manejadores de esquinas (TL, TR, BL, BR) o 4 laterales (T, B, L, R).
      - Rotar en tiempo real con el manejador superior de rotación (rot knob).
      - Menú contextual con clic derecho (Inspector FX, Duplicar, Eliminar, Keyframes, Traer al frente, etc.).
      - Atajos de teclado (Supr/Backspace para borrar, flechas para ajuste fino, Ctrl+D para duplicar, R para reset de rotación).
      - Dibujo vectorial nítido con QPainter de la caja delimitadora, manejadores y badge HUD informativo.
    """

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.player = player
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("color: #585B70; font-size: 15px; font-weight: 500;")
        self.setMinimumSize(480, 270)

    # ------------------------------------------------------------------
    # Coordenadas y Rectángulos de transformación
    # ------------------------------------------------------------------

    def _get_rendered_rect(self):
        """Retorna (rx, ry, rw, rh) del video escalado dentro del QLabel."""
        lbl_w = max(1, self.width())
        lbl_h = max(1, self.height())
        vinfo = self.player.video_info
        if not vinfo or vinfo.width <= 0 or vinfo.height <= 0:
            return 0, 0, lbl_w, lbl_h

        vw, vh = vinfo.width, vinfo.height
        scale = min(lbl_w / float(vw), lbl_h / float(vh))
        rw = max(1, int(vw * scale))
        rh = max(1, int(vh * scale))
        rx = int((lbl_w - rw) / 2.0)
        ry = int((lbl_h - rh) / 2.0)
        return rx, ry, rw, rh

    def _get_item_screen_box(self, item):
        """
        Retorna (bx, by, bw, bh) del item en coordenadas locales de la zona renderizada (0..rw, 0..rh).
        """
        rx, ry, rw, rh = self._get_rendered_rect()
        sec = self.player.current_sec

        cur_x, cur_y, cur_w, cur_h, cur_fs = item.get_transform_at(sec) if hasattr(item, 'get_transform_at') else (
            item.x_ratio, item.y_ratio, getattr(item, 'width_ratio', 0.3), getattr(item, 'height_ratio', 0.3), getattr(item, 'font_size', 40)
        )

        if isinstance(item, (TimelineImageClip, TimelineVideoClip, TimelineShapeClip)) or hasattr(item, 'width_ratio'):
            bw = max(24, int(rw * cur_w))
            bh = max(24, int(rh * cur_h))
            bx = int((rw - bw) * cur_x)
            by = int((rh - bh) * cur_y)
        else:
            # Text / Subtitle
            scaled_size = max(10, int(cur_fs * max(0.2, rh / 720.0)))
            font = self.player._get_font(scaled_size)
            dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
            t_box = dummy_draw.textbbox((0, 0), getattr(item, 'text', 'Texto') or "Texto", font=font)
            text_w = max(20, t_box[2] - t_box[0])
            text_h = max(14, t_box[3] - t_box[1])
            bw = text_w + 20
            bh = text_h + 14
            bx = int((rw - text_w) * cur_x) - 10
            by = int((rh - text_h) * cur_y) - 7

        return bx, by, bw, bh

    # ------------------------------------------------------------------
    # Hit Testing
    # ------------------------------------------------------------------

    def _hit_test(self, local_x: int, local_y: int):
        """
        Detecta qué item y qué manejador está bajo el cursor (local_x, local_y relativo a rw/rh).
        Retorna (item, handle_type) donde handle_type es:
          'ROT', 'TL', 'TR', 'BL', 'BR', 'T', 'B', 'L', 'R', 'BODY', o (None, None).
        """
        sec = self.player.current_sec
        sel = self.player.selected_item

        # 1. Comprobar primero los manejadores del item seleccionado actualmente
        if sel and hasattr(sel, 'is_visible_at') and sel.is_visible_at(sec):
            bx, by, bw, bh = self._get_item_screen_box(sel)
            cx = bx + bw / 2.0
            cy = by + bh / 2.0
            rot_x = cx
            rot_y = by - 26
            hr = 10

            # Manejador de rotación (perilla circular superior)
            if math.hypot(local_x - rot_x, local_y - rot_y) <= hr + 4:
                return sel, 'ROT'

            # 4 Esquinas
            if abs(local_x - bx) <= hr and abs(local_y - by) <= hr: return sel, 'TL'
            if abs(local_x - (bx + bw)) <= hr and abs(local_y - by) <= hr: return sel, 'TR'
            if abs(local_x - bx) <= hr and abs(local_y - (by + bh)) <= hr: return sel, 'BL'
            if abs(local_x - (bx + bw)) <= hr and abs(local_y - (by + bh)) <= hr: return sel, 'BR'

            # 4 Bordes laterales
            if abs(local_y - by) <= 7 and (bx < local_x < bx + bw): return sel, 'T'
            if abs(local_y - (by + bh)) <= 7 and (bx < local_x < bx + bw): return sel, 'B'
            if abs(local_x - bx) <= 7 and (by < local_y < by + bh): return sel, 'L'
            if abs(local_x - (bx + bw)) <= 7 and (by < local_y < by + bh): return sel, 'R'

            # Cuerpo del elemento seleccionado
            if bx <= local_x <= bx + bw and by <= local_y <= by + bh:
                return sel, 'BODY'

        # 2. Comprobar si se hace clic sobre cualquier otro elemento visible (orden Z invertido: Textos -> Formas -> Imágenes -> PIP)
        all_candidates = []
        all_candidates.extend([s for s in getattr(self.player, 'subtitles', []) if s.is_visible_at(sec)])
        all_candidates.extend([s for s in getattr(self.player, 'shape_clips', []) if s.is_visible_at(sec)])
        all_candidates.extend([img for img in getattr(self.player, 'image_clips', []) if img.is_visible_at(sec)])
        all_candidates.extend([v for v in getattr(self.player, 'video_clips', []) if v.is_visible_at(sec)])

        for item in reversed(all_candidates):
            bx, by, bw, bh = self._get_item_screen_box(item)
            if bx <= local_x <= bx + bw and by <= local_y <= by + bh:
                return item, 'BODY'

        return None, None

    # ------------------------------------------------------------------
    # Eventos de Ratón
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton or not self.player.video_info:
            super().mousePressEvent(event)
            return

        rx, ry, rw, rh = self._get_rendered_rect()
        local_x = event.position().x() - rx
        local_y = event.position().y() - ry

        item, handle = self._hit_test(local_x, local_y)

        if item is not None:
            self.player.selected_item = item
            self.player._dragged_item = item
            self.player._active_handle = handle
            self.player._drag_start_x = local_x
            self.player._drag_start_y = local_y

            bx, by, bw, bh = self._get_item_screen_box(item)
            self.player._init_bx = bx
            self.player._init_by = by
            self.player._init_bw = bw
            self.player._init_bh = bh
            self.player._init_rotation = getattr(item, 'rotation', 0.0)
            self.player._init_x_ratio = item.x_ratio
            self.player._init_y_ratio = item.y_ratio
            self.player._drag_offset_x = local_x - bx
            self.player._drag_offset_y = local_y - by

            self.player.item_selected.emit(item)
            self.update()
        else:
            # Clic en el fondo deselecciona
            self.player.selected_item = None
            self.player._dragged_item = None
            self.player._active_handle = None
            self.player.item_selected.emit(None)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        rx, ry, rw, rh = self._get_rendered_rect()
        local_x = event.position().x() - rx
        local_y = event.position().y() - ry

        item = getattr(self.player, '_dragged_item', None)
        handle = getattr(self.player, '_active_handle', None)

        if item is not None and handle is not None:
            # Arrastre activo
            bx = self.player._init_bx
            by = self.player._init_by
            bw = self.player._init_bw
            bh = self.player._init_bh
            cx = bx + bw / 2.0
            cy = by + bh / 2.0

            if handle == 'ROT':
                # Rotación continua
                angle = math.degrees(math.atan2(local_y - cy, local_x - cx)) + 90.0
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    angle = round(angle / 15.0) * 15.0  # Snap a múltiplos de 15°
                while angle > 180.0: angle -= 360.0
                while angle < -180.0: angle += 360.0
                item.rotation = round(angle, 1)

            elif handle == 'BODY':
                # Mover elemento
                off_x = getattr(self.player, '_drag_offset_x', 0)
                off_y = getattr(self.player, '_drag_offset_y', 0)
                new_bx = local_x - off_x
                new_by = local_y - off_y

                denom_w = float(rw - bw) if rw != bw else 1.0
                denom_h = float(rh - bh) if rh != bh else 1.0
                item.x_ratio = max(0.0, min(1.0, round(new_bx / denom_w, 3)))
                item.y_ratio = max(0.0, min(1.0, round(new_by / denom_h, 3)))

            else:
                # Redimensionado con esquinas o bordes
                new_bx, new_by, new_bw, new_bh = bx, by, bw, bh

                if 'R' in handle:
                    new_bw = max(24, local_x - bx)
                if 'L' in handle:
                    new_bx = min(bx + bw - 24, local_x)
                    new_bw = max(24, (bx + bw) - new_bx)
                if 'B' in handle:
                    new_bh = max(24, local_y - by)
                if 'T' in handle:
                    new_by = min(by + bh - 24, local_y)
                    new_bh = max(24, (by + bh) - new_by)

                denom_w = float(rw - new_bw) if rw != new_bw else 1.0
                denom_h = float(rh - new_bh) if rh != new_bh else 1.0

                if hasattr(item, 'width_ratio'):
                    item.width_ratio = round(max(0.04, min(1.0, new_bw / float(rw))), 3)
                    item.height_ratio = round(max(0.04, min(1.0, new_bh / float(rh))), 3)
                    item.x_ratio = max(0.0, min(1.0, round(new_bx / denom_w, 3)))
                    item.y_ratio = max(0.0, min(1.0, round(new_by / denom_h, 3)))
                elif hasattr(item, 'font_size'):
                    vinfo_h = getattr(self.player.video_info, 'height', 720) or 720
                    item.font_size = max(10, min(250, int(new_bh * 0.75 * (vinfo_h / float(rh)))))
                    item.x_ratio = max(0.0, min(1.0, round(new_bx / denom_w, 3)))
                    item.y_ratio = max(0.0, min(1.0, round(new_by / denom_h, 3)))

            # Sincronizar fotogramas clave si están activos
            if getattr(item, 'enable_keyframes', False):
                nodes = getattr(item, 'keyframe_nodes', None)
                if nodes:
                    nearest_idx = min(range(len(nodes)), key=lambda i: abs(nodes[i].get('sec', 0) - self.player.current_sec))
                    n = nodes[nearest_idx]
                    n['x_ratio'] = item.x_ratio
                    n['y_ratio'] = item.y_ratio
                    if hasattr(item, 'width_ratio'):
                        n['width_ratio'] = item.width_ratio
                        n['height_ratio'] = item.height_ratio
                    if hasattr(item, 'font_size'):
                        n['font_size'] = item.font_size
                    n['rotation'] = getattr(item, 'rotation', 0.0)

            self.player.item_modified.emit(item)
            self.player._is_drag_active = True
            # Re-renderizar fotograma en vivo
            self.player.seek_to(self.player.current_sec)
            self.update()

        else:
            # Hover: actualizar cursor según la posición
            h_item, h_handle = self._hit_test(local_x, local_y)
            if h_handle == 'ROT':
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            elif h_handle in ('TL', 'BR'):
                self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            elif h_handle in ('TR', 'BL'):
                self.setCursor(QCursor(Qt.CursorShape.SizeBDiagCursor))
            elif h_handle in ('T', 'B'):
                self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
            elif h_handle in ('L', 'R'):
                self.setCursor(QCursor(Qt.CursorShape.SizeHorCursor))
            elif h_handle == 'BODY':
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            elif h_item is not None:
                self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            else:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.player._dragged_item:
            self.player.item_modified.emit(self.player._dragged_item)
        self.player._dragged_item = None
        self.player._active_handle = None
        self.player._is_drag_active = False
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        rx, ry, rw, rh = self._get_rendered_rect()
        local_x = event.position().x() - rx
        local_y = event.position().y() - ry
        item, _ = self._hit_test(local_x, local_y)
        if item is not None:
            self.player.selected_item = item
            self.player.item_selected.emit(item)
            self.player._open_clip_inspector(item)
        else:
            super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # Menú Contextual (Clic Derecho)
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QContextMenuEvent):
        rx, ry, rw, rh = self._get_rendered_rect()
        local_x = event.pos().x() - rx
        local_y = event.pos().y() - ry

        item, _ = self._hit_test(local_x, local_y)
        if item is not None:
            self.player.selected_item = item
            self.player.item_selected.emit(item)
            self.update()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E1E2E; color: #CDD6F4;
                border: 1px solid #45475A; font-weight: bold;
                border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #89B4FA; color: #11111B; }
            QMenu::separator { height: 1px; background-color: #313244; margin: 4px 8px; }
        """)

        sel = self.player.selected_item
        if sel is not None:
            act_insp = menu.addAction("⚙ Inspector de Propiedades & FX...")
            act_kf = menu.addAction("📍 Crear Fotograma Clave (Keyframe) Aquí")
            act_reset = menu.addAction("🔄 Restablecer Transformación (Centrar & 0°)")
            menu.addSeparator()
            act_dup = menu.addAction("📄 Duplicar Clip")
            act_del = menu.addAction("🗑 Eliminar Clip")
            menu.addSeparator()
        else:
            act_insp = act_kf = act_reset = act_dup = act_del = None

        act_add_text = menu.addAction("💬 + Agregar Texto")
        act_add_img = menu.addAction("🖼 + Agregar Imagen")
        act_add_shp = menu.addAction("🔷 + Agregar Forma")
        act_add_vid = menu.addAction("📹 + Agregar Video PIP")

        chosen = menu.exec(event.globalPos())
        if not chosen:
            return

        if chosen == act_insp:
            self.player._open_clip_inspector(sel)
        elif chosen == act_kf:
            self.player.add_keyframe_at_current_sec()
        elif chosen == act_reset:
            self.player.reset_transform_selected_item()
        elif chosen == act_dup:
            self.player.duplicate_selected_item()
        elif chosen == act_del:
            self.player.delete_selected_item()
        elif chosen == act_add_text:
            if hasattr(self.player, 'main_win') and self.player.main_win:
                self.player.main_win.timeline._on_add_text_clicked()
        elif chosen == act_add_img:
            if hasattr(self.player, 'main_win') and self.player.main_win:
                self.player.main_win.timeline._on_add_image_clicked()
        elif chosen == act_add_shp:
            if hasattr(self.player, 'main_win') and self.player.main_win:
                self.player.main_win.timeline._on_add_shape_clicked()
        elif chosen == act_add_vid:
            if hasattr(self.player, 'main_win') and self.player.main_win:
                self.player.main_win.timeline._on_add_video_clicked()

    # ------------------------------------------------------------------
    # Atajos de Teclado
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        sel = self.player.selected_item
        if not sel:
            super().keyPressEvent(event)
            return

        step = 0.02 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.005
        k = event.key()

        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.player.delete_selected_item()
        elif k == Qt.Key.Key_Left:
            sel.x_ratio = max(0.0, round(sel.x_ratio - step, 3))
            self.player.item_modified.emit(sel)
            self.player.seek_to(self.player.current_sec)
        elif k == Qt.Key.Key_Right:
            sel.x_ratio = min(1.0, round(sel.x_ratio + step, 3))
            self.player.item_modified.emit(sel)
            self.player.seek_to(self.player.current_sec)
        elif k == Qt.Key.Key_Up:
            sel.y_ratio = max(0.0, round(sel.y_ratio - step, 3))
            self.player.item_modified.emit(sel)
            self.player.seek_to(self.player.current_sec)
        elif k == Qt.Key.Key_Down:
            sel.y_ratio = min(1.0, round(sel.y_ratio + step, 3))
            self.player.item_modified.emit(sel)
            self.player.seek_to(self.player.current_sec)
        elif k == Qt.Key.Key_R:
            sel.rotation = 0.0
            self.player.item_modified.emit(sel)
            self.player.seek_to(self.player.current_sec)
        elif k == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.player.duplicate_selected_item()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Dibujo de Manejadores Vectoriales (QPainter)
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        super().paintEvent(event)
        sel = self.player.selected_item
        if not sel or not self.player.video_info or not hasattr(sel, 'is_visible_at') or not sel.is_visible_at(self.player.current_sec):
            return

        rx, ry, rw, rh = self._get_rendered_rect()
        bx, by, bw, bh = self._get_item_screen_box(sel)

        # Coordenadas absolutas en el QLabel
        abs_x = rx + bx
        abs_y = ry + by
        cx = abs_x + bw / 2.0
        cy = abs_y + bh / 2.0
        rot_y = abs_y - 26

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Color del marco (accent): Mauve si keyframes activos, Cyan/Blue normal
        has_kf = getattr(sel, 'enable_keyframes', False)
        accent_color = QColor("#F5C2E7") if has_kf else QColor("#CBA6F7")
        handle_fill = QColor("#FFFFFF")
        handle_border = QColor("#11111B")

        # 1. Marco delimitador (dashed)
        pen_box = QPen(accent_color, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen_box)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(abs_x, abs_y, bw, bh)

        # 2. Línea y perilla de Rotación (Stem & Knob)
        painter.setPen(QPen(accent_color, 2, Qt.PenStyle.SolidLine))
        painter.drawLine(int(cx), abs_y, int(cx), int(rot_y))

        # Perilla de rotación
        painter.setPen(QPen(handle_border, 1.5))
        painter.setBrush(QBrush(accent_color))
        painter.drawEllipse(QPointF(cx, rot_y), 7.0, 7.0)

        # 3. Manecillas de Esquinas (TL, TR, BL, BR)
        hs = 8
        hs_half = hs // 2
        painter.setPen(QPen(accent_color, 1.5))
        painter.setBrush(QBrush(handle_fill))

        corners = [
            (abs_x - hs_half, abs_y - hs_half),
            (abs_x + bw - hs_half, abs_y - hs_half),
            (abs_x - hs_half, abs_y + bh - hs_half),
            (abs_x + bw - hs_half, abs_y + bh - hs_half)
        ]
        for x, y in corners:
            painter.drawRect(x, y, hs, hs)

        # 4. Manecillas Laterales (T, B, L, R)
        es = 6
        es_half = es // 2
        edges = [
            (int(cx) - es_half, abs_y - es_half),
            (int(cx) - es_half, abs_y + bh - es_half),
            (abs_x - es_half, int(cy) - es_half),
            (abs_x + bw - es_half, int(cy) - es_half)
        ]
        for x, y in edges:
            painter.drawRect(x, y, es, es)

        # 5. Cruz central (Anchor)
        painter.setPen(QPen(accent_color, 1.5))
        painter.drawLine(int(cx) - 5, int(cy), int(cx) + 5, int(cy))
        painter.drawLine(int(cx), int(cy) - 5, int(cx), int(cy) + 5)

        # 6. HUD informativo flotante si se está transformando
        if getattr(self.player, '_is_drag_active', False):
            badge_text = f"X: {int(sel.x_ratio*100)}% | Y: {int(sel.y_ratio*100)}% | Rot: {getattr(sel, 'rotation', 0):.0f}°"
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(badge_text) + 16
            th = 22
            badge_x = int(cx - tw / 2)
            badge_y = abs_y + bh + 10
            if badge_y + th > ry + rh:
                badge_y = abs_y - th - 34

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(24, 24, 37, 230)))
            painter.drawRoundedRect(badge_x, badge_y, tw, th, 4, 4)

            painter.setPen(QColor("#CDD6F4"))
            painter.drawText(QRect(badge_x, badge_y, tw, th), Qt.AlignmentFlag.AlignCenter, badge_text)

        painter.end()


class VideoPreviewWidget(QWidget):
    """
    Control interactivo completo de Previsualización y Recorte de Video.
    Permite ver, reproducir, recortar y EDITAR DIRECTAMENTE desde la pantalla
    todas las capas (Videos PIP, Imágenes, Formas, Textos, Transiciones y Capas de Ajuste).
    """
    positionChanged = pyqtSignal(float)
    trimChanged = pyqtSignal(float, float)
    item_selected = pyqtSignal(object)
    item_modified = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_win = None
        self.video_info = None
        self.cap = None
        self.current_sec = 0.0
        self.is_playing = False
        self.start_sec = 0.0
        self.end_sec = 0.0
        self.subtitles = []
        self.image_clips = []
        self.video_clips = []
        self.shape_clips = []
        self.audio_clips = []
        self.transition_clips = []
        self.adjustment_layers = []
        self.speed_intervals = []

        self.selected_item = None
        self._dragged_item = None
        self._active_handle = None
        self._is_drag_active = False
        self._pip_caps = {}
        self._pip_last_pos = {}

        self._init_ui()

        # Playback timer (~30 fps preview refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._next_frame)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Video Display Frame Container
        self.display_frame = QFrame(self)
        self.display_frame.setStyleSheet("""
            QFrame {
                background-color: #0F0F17;
                border: 2px solid #313244;
                border-radius: 12px;
            }
        """)
        display_layout = QVBoxLayout(self.display_frame)
        display_layout.setContentsMargins(4, 4, 4, 4)

        # Surface de Previsualización Interactiva
        self.video_label = InteractiveVideoLabel(self, self.display_frame)
        display_layout.addWidget(self.video_label)
        layout.addWidget(self.display_frame, stretch=1)

        # Timeline Trimmer Slider
        self.range_slider = DualRangeSlider(self)
        self.range_slider.rangeChanged.connect(self._on_trim_changed)
        self.range_slider.handleMoved.connect(self.seek_to)
        layout.addWidget(self.range_slider)

        # Precise Time SpinBoxes (Inicio / Fin exactos)
        time_inputs_layout = QHBoxLayout()
        time_inputs_layout.setSpacing(10)

        lbl_start_input = QLabel("✂ Recorte Inicio (seg):", self)
        self.spn_start_time = QDoubleSpinBox(self)
        self.spn_start_time.setDecimals(2)
        self.spn_start_time.setSingleStep(0.10)
        self.spn_start_time.setRange(0.00, 9999.00)
        self.spn_start_time.setFixedWidth(110)
        self.spn_start_time.valueChanged.connect(self._on_spin_start_changed)

        lbl_end_input = QLabel("✂ Recorte Fin (seg):", self)
        self.spn_end_time = QDoubleSpinBox(self)
        self.spn_end_time.setDecimals(2)
        self.spn_end_time.setSingleStep(0.10)
        self.spn_end_time.setRange(0.00, 9999.00)
        self.spn_end_time.setFixedWidth(110)
        self.spn_end_time.valueChanged.connect(self._on_spin_end_changed)

        time_inputs_layout.addWidget(lbl_start_input)
        time_inputs_layout.addWidget(self.spn_start_time)
        time_inputs_layout.addSpacing(20)
        time_inputs_layout.addWidget(lbl_end_input)
        time_inputs_layout.addWidget(self.spn_end_time)
        time_inputs_layout.addStretch()

        layout.addLayout(time_inputs_layout)

        # Control Bar (Play, Timecode, Loop indicators)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        self.btn_play = QPushButton("▶ Reproducir", self)
        self.btn_play.setFixedWidth(120)
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.btn_play)

        self.btn_set_start = QPushButton("⚑ Inicio (A)", self)
        self.btn_set_start.setEnabled(False)
        self.btn_set_start.clicked.connect(self._set_current_as_start)
        controls_layout.addWidget(self.btn_set_start)

        self.btn_set_end = QPushButton("⚑ Fin (B)", self)
        self.btn_set_end.setEnabled(False)
        self.btn_set_end.clicked.connect(self._set_current_as_end)
        controls_layout.addWidget(self.btn_set_end)

        controls_layout.addStretch()

        self.lbl_timecode = QLabel("00:00.00 / 00:00.00", self)
        self.lbl_timecode.setObjectName("timeLabel")
        controls_layout.addWidget(self.lbl_timecode)

        layout.addLayout(controls_layout)

    def load_video(self, file_path: str):
        self.stop()
        if self.cap:
            self.cap.release()

        self.video_info = VideoInfo(file_path)
        if not self.video_info.is_valid:
            self.video_label.setText("⚠ No se pudo cargar el formato de video seleccionado.")
            self.btn_play.setEnabled(False)
            self.btn_set_start.setEnabled(False)
            self.btn_set_end.setEnabled(False)
            return False

        self.cap = cv2.VideoCapture(file_path)
        self.start_sec = 0.0
        self.end_sec = self.video_info.duration
        self.current_sec = 0.0

        self.range_slider.setRange(0.0, self.video_info.duration)
        self.range_slider.setValues(0.0, self.video_info.duration)

        self.spn_start_time.blockSignals(True)
        self.spn_end_time.blockSignals(True)
        self.spn_start_time.setRange(0.0, self.video_info.duration)
        self.spn_end_time.setRange(0.0, self.video_info.duration)
        self.spn_start_time.setValue(0.0)
        self.spn_end_time.setValue(self.video_info.duration)
        self.spn_start_time.blockSignals(False)
        self.spn_end_time.blockSignals(False)

        self.btn_play.setEnabled(True)
        self.btn_set_start.setEnabled(True)
        self.btn_set_end.setEnabled(True)

        self.seek_to(0.0)
        return True

    def set_subtitles(self, subtitles: list):
        self.subtitles = subtitles
        if self.video_info and self.cap:
            self.seek_to(self.current_sec)

    def seek_to(self, sec: float):
        if not self.video_info or not self.cap:
            return

        sec = max(0.0, min(sec, self.video_info.duration))
        self.current_sec = sec

        frame_num = int(sec * self.video_info.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.cap.read()
        if ret and frame is not None:
            self._render_frame(frame)

        self.range_slider.setCurrentPos(sec)
        self._update_timecode_label()
        self.positionChanged.emit(sec)

    def toggle_play(self):
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def play(self):
        if not self.video_info or not self.cap:
            return
        if self.current_sec >= self.end_sec:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)
        self.is_playing = True
        self.btn_play.setText("⏸ Pausa")
        self.timer.start()

    def pause(self):
        self.is_playing = False
        self.btn_play.setText("▶ Reproducir")
        self.timer.stop()

    def stop(self):
        self.pause()
        self.current_sec = self.start_sec
        self.range_slider.setCurrentPos(self.current_sec)

    def _next_frame(self):
        if not self.is_playing or not self.video_info or not self.cap:
            return

        intervals = getattr(self, 'speed_intervals', [])
        if intervals:
            in_any = any(inv.start_sec <= self.current_sec <= inv.end_sec for inv in intervals)
            if not in_any:
                next_invs = [inv for inv in intervals if inv.start_sec > self.current_sec]
                if next_invs:
                    self.seek_to(min(inv.start_sec for inv in next_invs))
                    return
                else:
                    self.seek_to(min(inv.start_sec for inv in intervals))
                    return

        frame_dt = 1.0 / max(1.0, self.video_info.fps)
        self.current_sec += frame_dt
        if self.current_sec >= self.end_sec:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)
            return

        ret, frame = self.cap.read()
        if ret and frame is not None:
            self._render_frame(frame)
            self.range_slider.setCurrentPos(self.current_sec)
            self._update_timecode_label()
            self.positionChanged.emit(self.current_sec)
        else:
            self.current_sec = self.start_sec
            self.seek_to(self.start_sec)

    def _get_font(self, size: int):
        if not hasattr(self, '_font_cache'): self._font_cache = {}
        if size not in self._font_cache:
            try:
                self._font_cache[size] = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", int(size))
            except Exception:
                self._font_cache[size] = ImageFont.load_default()
        return self._font_cache[size]

    def _get_cached_image(self, path: str):
        if not hasattr(self, '_img_cache'): self._img_cache = {}
        if path not in self._img_cache:
            if os.path.exists(path):
                self._img_cache[path] = Image.open(path).convert("RGBA")
            else:
                return None
        return self._img_cache[path]

    def _get_resized_overlay(self, path: str, target_w: int, target_h: int):
        if not hasattr(self, '_resize_cache'): self._resize_cache = {}
        key = (path, target_w, target_h)
        if key not in self._resize_cache:
            base_img = self._get_cached_image(path)
            if base_img is None: return None
            if len(self._resize_cache) > 60: self._resize_cache.clear()
            self._resize_cache[key] = base_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
        return self._resize_cache[key]

    # ------------------------------------------------------------------
    # Pipeline de Renderizado Fotograma a Fotograma en Previsualización
    # ------------------------------------------------------------------

    def _render_frame(self, frame_bgr):
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape

        # 1. Transiciones Activas en Previsualización
        for trans in getattr(self, 'transition_clips', []):
            if trans.is_active_at(self.current_sec):
                try:
                    progress = trans.get_progress_at(self.current_sec)
                    fps = getattr(self.video_info, 'fps', 30.0) or 30.0
                    other_sec = trans.at_sec + (1.0 / max(1.0, fps))
                    other_frame_idx = max(0, int(other_sec * fps))
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, other_frame_idx)
                    ret_other, other_frame = self.cap.read()
                    if ret_other and other_frame is not None:
                        other_rgb = cv2.cvtColor(other_frame, cv2.COLOR_BGR2RGB)
                        if (other_rgb.shape[1], other_rgb.shape[0]) != (w, h):
                            other_rgb = cv2.resize(other_rgb, (w, h))
                        frame_rgb = PhotoshopFX.apply_transition(
                            frame_rgb, other_rgb,
                            transition_type=getattr(trans, 'transition_type', 'Fade'),
                            progress=progress
                        )
                except Exception:
                    pass

        # 2. Videos PIP (Con slip offset, speed, reverse, mascaras, rotacion, opacidad)
        active_vids = [v for v in getattr(self, 'video_clips', []) if v.is_visible_at(self.current_sec)]
        if active_vids:
            for v_clip in active_vids:
                if v_clip.video_path not in self._pip_caps:
                    self._pip_caps[v_clip.video_path] = cv2.VideoCapture(v_clip.video_path)

                pip_cap = self._pip_caps.get(v_clip.video_path)
                if pip_cap and pip_cap.isOpened():
                    try:
                        fps = pip_cap.get(cv2.CAP_PROP_FPS) or 30.0
                        total_frames = int(pip_cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
                        v_dur_sec = float(total_frames) / fps if fps > 0 else 1.0

                        slip_off = getattr(v_clip, 'slip_offset_sec', 0.0)
                        rel_t = (self.current_sec - v_clip.start_sec + slip_off) * getattr(v_clip, 'speed', 1.0)
                        if getattr(v_clip, 'reverse', False):
                            rel_t = v_dur_sec - rel_t

                        loop_t = rel_t % v_dur_sec if v_dur_sec > 0 else 0.0
                        target_frame = int(loop_t * fps) % max(1, total_frames)
                        last_pos = self._pip_last_pos.get(v_clip.video_path, -999)

                        if target_frame != last_pos + 1:
                            pip_cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

                        ret, pip_frame = pip_cap.read()
                        if not ret:
                            pip_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ret, pip_frame = pip_cap.read()

                        if ret and pip_frame is not None:
                            self._pip_last_pos[v_clip.video_path] = target_frame
                            pip_rgb = cv2.cvtColor(pip_frame, cv2.COLOR_BGR2RGB)
                            cur_x, cur_y, cur_w, cur_h, _ = v_clip.get_transform_at(self.current_sec) if hasattr(v_clip, 'get_transform_at') else (v_clip.x_ratio, v_clip.y_ratio, v_clip.width_ratio, v_clip.height_ratio, 40)
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
                                blur_radius=getattr(v_clip, 'blur_radius', 0.0)
                            )

                            if getattr(v_clip, 'mask_path', ''):
                                pip_fx = PhotoshopFX.apply_mask(pip_fx, v_clip.mask_path, getattr(v_clip, 'mask_invert', False))

                            if getattr(v_clip, 'border_radius', 0) > 0 or getattr(v_clip, 'border_width', 0) > 0:
                                pip_fx = PhotoshopFX.apply_border_and_corners(
                                    pip_fx,
                                    radius=getattr(v_clip, 'border_radius', 0),
                                    border_width=getattr(v_clip, 'border_width', 0),
                                    border_color=getattr(v_clip, 'border_color', '#FFFFFF')
                                )

                            cur_rot = v_clip.get_rotation_at(self.current_sec) if hasattr(v_clip, 'get_rotation_at') else getattr(v_clip, 'rotation', 0.0)
                            if abs(cur_rot) > 0.1:
                                pip_fx = PhotoshopFX.apply_rotation(pip_fx, cur_rot)

                            v_op = PhotoshopFX.compute_opacity_with_fade(
                                self.current_sec, v_clip.start_sec, v_clip.end_sec,
                                base_opacity=v_clip.get_opacity_at(self.current_sec) if hasattr(v_clip, 'get_opacity_at') else getattr(v_clip, 'opacity', 1.0),
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

        # 3. Capas de Formas Vectoriales (Shapes)
        active_shapes = [s for s in getattr(self, 'shape_clips', []) if s.is_visible_at(self.current_sec)]
        if active_shapes:
            pil_shapes = Image.fromarray(frame_rgb).convert("RGBA")
            for shp in active_shapes:
                try:
                    cur_x, cur_y, cur_w, cur_h, _ = shp.get_transform_at(self.current_sec) if hasattr(shp, 'get_transform_at') else (shp.x_ratio, shp.y_ratio, shp.width_ratio, shp.height_ratio, 40)
                    target_w = max(10, int(w * cur_w))
                    target_h = max(10, int(h * cur_h))
                    shape_img = PhotoshopFX.render_shape(
                        target_w, target_h,
                        shape_type=getattr(shp, 'shape_type', 'Rectangle'),
                        fill_color=getattr(shp, 'fill_color', '#CBA6F7'),
                        stroke_color=getattr(shp, 'stroke_color', '#FFFFFF'),
                        stroke_width=getattr(shp, 'stroke_width', 2),
                        corner_radius=getattr(shp, 'corner_radius', 0),
                        star_points=getattr(shp, 'star_points', 5)
                    )
                    if getattr(shp, 'mask_path', ''):
                        shape_img = PhotoshopFX.apply_mask(shape_img, shp.mask_path, getattr(shp, 'mask_invert', False))

                    cur_rot = shp.get_rotation_at(self.current_sec) if hasattr(shp, 'get_rotation_at') else getattr(shp, 'rotation', 0.0)
                    if abs(cur_rot) > 0.1:
                        shape_img = PhotoshopFX.apply_rotation(shape_img, cur_rot)

                    shp_op = PhotoshopFX.compute_opacity_with_fade(
                        self.current_sec, shp.start_sec, shp.end_sec,
                        base_opacity=shp.get_opacity_at(self.current_sec) if hasattr(shp, 'get_opacity_at') else getattr(shp, 'opacity', 1.0),
                        fade_in_sec=getattr(shp, 'fade_in_sec', 0.0),
                        fade_out_sec=getattr(shp, 'fade_out_sec', 0.0)
                    )
                    pos_x = int((w - target_w) * cur_x)
                    pos_y = int((h - target_h) * cur_y)

                    if getattr(shp, 'drop_shadow', False):
                        s_box = Image.new("RGBA", shape_img.size, (0, 0, 0, int(120 * shp_op)))
                        s_box = s_box.filter(ImageFilter.GaussianBlur(4))
                        pil_shapes.paste(s_box, (pos_x + 4, pos_y + 4), s_box)

                    pil_shapes = PhotoshopFX.apply_blend_composite(
                        pil_shapes, shape_img, (pos_x, pos_y),
                        blend_mode=getattr(shp, 'blend_mode', 'Normal'), opacity=shp_op
                    )
                except Exception:
                    pass
            frame_rgb = np.array(pil_shapes.convert("RGB"))

        # 4. Capas de Imágenes
        active_imgs = [img for img in getattr(self, 'image_clips', []) if img.is_visible_at(self.current_sec)]
        if active_imgs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            for img_clip in active_imgs:
                try:
                    cur_x, cur_y, cur_w, cur_h, _ = img_clip.get_transform_at(self.current_sec) if hasattr(img_clip, 'get_transform_at') else (img_clip.x_ratio, img_clip.y_ratio, img_clip.width_ratio, img_clip.height_ratio, 40)
                    target_w = max(20, int(w * cur_w))
                    target_h = max(20, int(h * cur_h))

                    overlay_img = self._get_resized_overlay(img_clip.image_path, target_w, target_h)
                    if overlay_img is not None:
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

                        if getattr(img_clip, 'mask_path', ''):
                            img_fx = PhotoshopFX.apply_mask(img_fx, img_clip.mask_path, getattr(img_clip, 'mask_invert', False))

                        if getattr(img_clip, 'border_radius', 0) > 0 or getattr(img_clip, 'border_width', 0) > 0:
                            img_fx = PhotoshopFX.apply_border_and_corners(
                                img_fx,
                                radius=getattr(img_clip, 'border_radius', 0),
                                border_width=getattr(img_clip, 'border_width', 0),
                                border_color=getattr(img_clip, 'border_color', '#FFFFFF')
                            )

                        cur_rot = img_clip.get_rotation_at(self.current_sec) if hasattr(img_clip, 'get_rotation_at') else getattr(img_clip, 'rotation', 0.0)
                        if abs(cur_rot) > 0.1:
                            img_fx = PhotoshopFX.apply_rotation(img_fx, cur_rot)

                        img_op = PhotoshopFX.compute_opacity_with_fade(
                            self.current_sec, img_clip.start_sec, img_clip.end_sec,
                            base_opacity=img_clip.get_opacity_at(self.current_sec) if hasattr(img_clip, 'get_opacity_at') else getattr(img_clip, 'opacity', 1.0),
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

        # 5. Capas de Subtítulos y Texto
        active_subs = [s for s in self.subtitles if s.is_visible_at(self.current_sec)]
        if active_subs:
            pil_img = Image.fromarray(frame_rgb).convert("RGBA")
            draw = ImageDraw.Draw(pil_img)

            for sub in active_subs:
                try:
                    cur_x, cur_y, _, _, cur_fs = sub.get_transform_at(self.current_sec) if hasattr(sub, 'get_transform_at') else (sub.x_ratio, sub.y_ratio, 0.3, 0.3, sub.font_size)
                    ref_h = 720.0
                    scaled_size = max(10, int(cur_fs * max(0.2, h / ref_h)))
                    font = self._get_font(scaled_size)

                    bbox = draw.textbbox((0, 0), sub.text, font=font)
                    text_w = bbox[2] - bbox[0]
                    text_h = bbox[3] - bbox[1]

                    x = int((w - text_w) * cur_x)
                    y = int((h - text_h) * cur_y)

                    t_op = PhotoshopFX.compute_opacity_with_fade(
                        self.current_sec, sub.start_sec, sub.end_sec,
                        base_opacity=sub.get_opacity_at(self.current_sec) if hasattr(sub, 'get_opacity_at') else getattr(sub, 'opacity', 1.0),
                        fade_in_sec=getattr(sub, 'fade_in_sec', 0.0),
                        fade_out_sec=getattr(sub, 'fade_out_sec', 0.0)
                    )

                    # Sombra suave
                    if getattr(sub, 'drop_shadow', True) and t_op > 0.05:
                        draw.text((x + 4, y + 4), sub.text, font=font, fill=(0, 0, 0, int(160 * t_op)))

                    # Borde
                    ox, oy = max(1, int(scaled_size / 14)), max(1, int(scaled_size / 14))
                    b_col = sub.border_color
                    f_col = sub.color
                    draw.text((x - ox, y), sub.text, font=font, fill=b_col)
                    draw.text((x + ox, y), sub.text, font=font, fill=b_col)
                    draw.text((x, y - oy), sub.text, font=font, fill=b_col)
                    draw.text((x, y + oy), sub.text, font=font, fill=b_col)

                    draw.text((x, y), sub.text, font=font, fill=f_col)
                except Exception:
                    pass
            frame_rgb = np.array(pil_img.convert("RGB"))

        # 6. Capas de Ajuste Global (Adjustment Layers)
        active_adj = [a for a in getattr(self, 'adjustment_layers', []) if a.is_active_at(self.current_sec)]
        if active_adj:
            adj_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            for adj in active_adj:
                try:
                    adj_bgr = PhotoshopFX.apply_adjustment_layer(adj_bgr, adj)
                except Exception:
                    pass
            frame_rgb = cv2.cvtColor(adj_bgr, cv2.COLOR_BGR2RGB)

        # Generar QImage y Pixmap para la surface
        q_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        lbl_size = self.video_label.size()
        pixmap = QPixmap.fromImage(q_img)
        scaled_pixmap = pixmap.scaled(lbl_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.video_label.setPixmap(scaled_pixmap)

    # ------------------------------------------------------------------
    # Operaciones de edición llamadas desde preview / menú contextual
    # ------------------------------------------------------------------

    def reset_transform_selected_item(self):
        sel = self.selected_item
        if sel:
            sel.x_ratio = 0.5
            sel.y_ratio = 0.5
            sel.rotation = 0.0
            if hasattr(sel, 'width_ratio'):
                sel.width_ratio = 0.35
                sel.height_ratio = 0.35
            self.item_modified.emit(sel)
            self.seek_to(self.current_sec)
            self.video_label.update()

    def add_keyframe_at_current_sec(self):
        sel = self.selected_item
        if sel:
            sel.enable_keyframes = True
            if hasattr(sel, 'add_keyframe_node'):
                sel.add_keyframe_node(self.current_sec)
            self.item_modified.emit(sel)
            self.seek_to(self.current_sec)
            self.video_label.update()

    def duplicate_selected_item(self):
        if hasattr(self, 'main_win') and self.main_win:
            self.main_win.timeline.canvas.duplicate_selected_item()

    def delete_selected_item(self):
        if hasattr(self, 'main_win') and self.main_win:
            self.main_win.timeline.canvas.delete_selected_item()
        self.selected_item = None
        self.item_selected.emit(None)
        self.seek_to(self.current_sec)
        self.video_label.update()

    def _open_clip_inspector(self, clip=None):
        target = clip or self.selected_item
        if not target:
            return
        from app.gui.timeline_widget import ClipInspectorDialog
        dlg = ClipInspectorDialog(target, self)
        if dlg.exec():
            self.item_modified.emit(target)
            self.seek_to(self.current_sec)
            self.video_label.update()

    # ------------------------------------------------------------------
    # Métodos Auxiliares
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.video_info and self.cap:
            self.seek_to(self.current_sec)

    def _on_trim_changed(self, start_sec, end_sec):
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.spn_start_time.blockSignals(True)
        self.spn_end_time.blockSignals(True)
        self.spn_start_time.setValue(start_sec)
        self.spn_end_time.setValue(end_sec)
        self.spn_start_time.blockSignals(False)
        self.spn_end_time.blockSignals(False)
        self._update_timecode_label()
        self.trimChanged.emit(start_sec, end_sec)

    def _on_spin_start_changed(self, val):
        if val < self.end_sec - 0.1:
            self.start_sec = val
            self.range_slider.setValues(self.start_sec, self.end_sec)
            self.seek_to(val)

    def _on_spin_end_changed(self, val):
        if val > self.start_sec + 0.1:
            self.end_sec = val
            self.range_slider.setValues(self.start_sec, self.end_sec)
            self.seek_to(val)

    def _set_current_as_start(self):
        if self.current_sec < self.end_sec - 0.1:
            self.range_slider.setValues(self.current_sec, self.end_sec)

    def _set_current_as_end(self):
        if self.current_sec > self.start_sec + 0.1:
            self.range_slider.setValues(self.start_sec, self.current_sec)

    def _update_timecode_label(self):
        start_str = VideoInfo.format_time(self.start_sec)
        end_str = VideoInfo.format_time(self.end_sec)
        dur_str = VideoInfo.format_time(self.end_sec - self.start_sec)
        audio_count = len(getattr(self, 'audio_clips', []))
        audio_badge = f" | 🎵 Audio: {audio_count}" if audio_count > 0 else ""
        self.lbl_timecode.setText(f"Trim: {start_str} - {end_str} ({dur_str}){audio_badge}")

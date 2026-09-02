from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDoubleSpinBox, QSpinBox, QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QComboBox, QColorDialog, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from app.core.subtitle import SubtitleItem

class SubtitleManagerDialog(QDialog):
    """
    Dialog to manage subtitles / text overlays: add, edit timing, font size, position, and colors.
    """
    subtitles_changed = pyqtSignal(list)

    def __init__(self, subtitles=None, video_duration=10.0, current_sec=0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestor de Subtítulos y Texto")
        self.resize(550, 480)

        self.subtitles = [SubtitleItem(
            text=s.text, start_sec=s.start_sec, end_sec=s.end_sec,
            x_ratio=s.x_ratio, y_ratio=s.y_ratio, font_size=s.font_size,
            color=s.color, border_color=s.border_color
        ) for s in (subtitles or [])]

        self.video_duration = video_duration
        self.current_sec = current_sec
        self.selected_color = "#FFFFFF"
        self.selected_border_color = "#000000"

        self._init_ui()
        self._refresh_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Subtitles List Group
        list_group = QGroupBox("Subtítulos / Textos Agregados", self)
        list_layout = QVBoxLayout(list_group)

        self.list_widget = QListWidget(list_group)
        self.list_widget.currentRowChanged.connect(self._on_item_selected)
        list_layout.addWidget(self.list_widget)

        btn_list_layout = QHBoxLayout()
        self.btn_new = QPushButton("➕ Agregar Nuevo Subtítulo", list_group)
        self.btn_new.clicked.connect(self._add_new_subtitle)
        self.btn_delete = QPushButton("🗑 Eliminar Seleccionado", list_group)
        self.btn_delete.clicked.connect(self._delete_subtitle)

        btn_list_layout.addWidget(self.btn_new)
        btn_list_layout.addWidget(self.btn_delete)
        list_layout.addLayout(btn_list_layout)

        layout.addWidget(list_group)

        # Editor Form Group
        self.edit_group = QGroupBox("Editar Subtítulo Seleccionado", self)
        edit_layout = QVBoxLayout(self.edit_group)
        edit_layout.setSpacing(8)

        # Text input
        text_layout = QHBoxLayout()
        text_layout.addWidget(QLabel("Texto:", self.edit_group))
        self.txt_content = QLineEdit(self.edit_group)
        self.txt_content.setPlaceholderText("Escribe el texto aquí...")
        text_layout.addWidget(self.txt_content)
        edit_layout.addLayout(text_layout)

        # Timing inputs
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Aparición (seg):", self.edit_group))
        self.spn_start = QDoubleSpinBox(self.edit_group)
        self.spn_start.setRange(0.0, max(0.1, self.video_duration))
        self.spn_start.setDecimals(2)
        time_layout.addWidget(self.spn_start)

        time_layout.addWidget(QLabel("Desaparición (seg):", self.edit_group))
        self.spn_end = QDoubleSpinBox(self.edit_group)
        self.spn_end.setRange(0.0, max(0.1, self.video_duration))
        self.spn_end.setDecimals(2)
        time_layout.addWidget(self.spn_end)
        edit_layout.addLayout(time_layout)

        # Style inputs: Position & Size & Colors
        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("Posición:", self.edit_group))
        self.combo_pos = QComboBox(self.edit_group)
        self.combo_pos.addItems([
            "Abajo (Subtítulo estándar)",
            "Centro",
            "Arriba (Título)",
            "Superior Izquierda",
            "Superior Derecha"
        ])
        style_layout.addWidget(self.combo_pos)

        style_layout.addWidget(QLabel("Tamaño Font:", self.edit_group))
        self.spn_font_size = QSpinBox(self.edit_group)
        self.spn_font_size.setRange(12, 100)
        self.spn_font_size.setValue(28)
        style_layout.addWidget(self.spn_font_size)
        edit_layout.addLayout(style_layout)

        # Colors layout
        colors_layout = QHBoxLayout()
        self.btn_color = QPushButton("🎨 Color Texto", self.edit_group)
        self.btn_color.clicked.connect(self._pick_text_color)
        self.btn_border_color = QPushButton("⬛ Color Borde", self.edit_group)
        self.btn_border_color.clicked.connect(self._pick_border_color)

        colors_layout.addWidget(self.btn_color)
        colors_layout.addWidget(self.btn_border_color)
        edit_layout.addLayout(colors_layout)

        self.btn_save_item = QPushButton("💾 Guardar Cambios del Subtítulo", self.edit_group)
        self.btn_save_item.setStyleSheet("background-color: #89B4FA; color: #11111B; font-weight: bold;")
        self.btn_save_item.clicked.connect(self._save_selected_subtitle)
        edit_layout.addWidget(self.btn_save_item)

        layout.addWidget(self.edit_group)

        # Dialog Buttons (OK / Cancel)
        bottom_layout = QHBoxLayout()
        btn_apply = QPushButton("✔ Aplicar y Cerrar", self)
        btn_apply.setObjectName("primaryButton")
        btn_apply.clicked.connect(self.accept)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_apply)

        layout.addLayout(bottom_layout)

    def _refresh_list(self, target_row: int = 0):
        self.list_widget.clear()
        for idx, sub in enumerate(self.subtitles):
            item_str = f"[{sub.start_sec:.2f}s - {sub.end_sec:.2f}s]  \"{sub.text}\""
            self.list_widget.addItem(QListWidgetItem(item_str))

        if self.subtitles:
            valid_row = max(0, min(len(self.subtitles) - 1, target_row))
            self.list_widget.setCurrentRow(valid_row)
            self._on_item_selected(valid_row)
            self.edit_group.setEnabled(True)
        else:
            self.edit_group.setEnabled(False)

    def _add_new_subtitle(self):
        start = self.current_sec
        end = min(self.video_duration, start + 3.0)
        new_sub = SubtitleItem(text="Nuevo Subtítulo", start_sec=start, end_sec=end, font_size=36)
        self.subtitles.append(new_sub)
        new_index = len(self.subtitles) - 1
        self._refresh_list(target_row=new_index)
        self.subtitles_changed.emit(self.subtitles)

    def _delete_subtitle(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.subtitles):
            self.subtitles.pop(row)
            next_row = max(0, row - 1)
            self._refresh_list(target_row=next_row)
            self.subtitles_changed.emit(self.subtitles)

    def _on_item_selected(self, row):
        if 0 <= row < len(self.subtitles):
            sub = self.subtitles[row]
            self.txt_content.setText(sub.text)
            self.spn_start.setValue(sub.start_sec)
            self.spn_end.setValue(sub.end_sec)
            self.spn_font_size.setValue(sub.font_size)
            self.selected_color = sub.color
            self.selected_border_color = sub.border_color

            # Set position combo
            if sub.y_ratio >= 0.75: self.combo_pos.setCurrentIndex(0) # Abajo
            elif 0.35 <= sub.y_ratio < 0.65: self.combo_pos.setCurrentIndex(1) # Centro
            elif sub.y_ratio < 0.25 and sub.x_ratio < 0.3: self.combo_pos.setCurrentIndex(3) # Top left
            elif sub.y_ratio < 0.25 and sub.x_ratio > 0.7: self.combo_pos.setCurrentIndex(4) # Top right
            else: self.combo_pos.setCurrentIndex(2) # Arriba

    def _pick_text_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Seleccionar Color de Texto")
        if color.isValid():
            self.selected_color = color.name()

    def _pick_border_color(self):
        color = QColorDialog.getColor(QColor(self.selected_border_color), self, "Seleccionar Color de Borde")
        if color.isValid():
            self.selected_border_color = color.name()

    def _save_selected_subtitle(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.subtitles):
            sub = self.subtitles[row]
            sub.text = self.txt_content.text()
            sub.start_sec = self.spn_start.value()
            sub.end_sec = max(sub.start_sec + 0.1, self.spn_end.value())
            sub.font_size = self.spn_font_size.value()
            sub.color = self.selected_color
            sub.border_color = self.selected_border_color

            pos_idx = self.combo_pos.currentIndex()
            if pos_idx == 0: sub.x_ratio, sub.y_ratio = 0.5, 0.85  # Abajo
            elif pos_idx == 1: sub.x_ratio, sub.y_ratio = 0.5, 0.45  # Centro
            elif pos_idx == 2: sub.x_ratio, sub.y_ratio = 0.5, 0.08  # Arriba
            elif pos_idx == 3: sub.x_ratio, sub.y_ratio = 0.05, 0.08 # Top left
            elif pos_idx == 4: sub.x_ratio, sub.y_ratio = 0.95, 0.08 # Top right
            self._refresh_list(target_row=row)
            self.subtitles_changed.emit(self.subtitles)

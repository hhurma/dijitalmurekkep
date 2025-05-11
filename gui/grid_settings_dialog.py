import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QSpinBox, QPushButton, QDialogButtonBox, QColorDialog, QLabel, QDoubleSpinBox, QCheckBox, QHBoxLayout
)
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtCore import Qt, pyqtSignal

def qcolor_to_rgba(color: QColor) -> tuple:
    return (color.redF(), color.greenF(), color.blueF(), color.alphaF())

def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black)
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

class GridSettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grid Ayarları")
        self.setMinimumWidth(350)
        self.current_settings = current_settings.copy()

        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Kalın çizgi aralığı
        self.thick_line_interval_spin = QSpinBox()
        self.thick_line_interval_spin.setRange(1, 20)
        self.thick_line_interval_spin.setValue(self.current_settings.get('grid_thick_line_interval', 4))
        form_layout.addRow("Kalın çizgi aralığı:", self.thick_line_interval_spin)

        # İnce çizgi rengi
        self.thin_color_button = QPushButton()
        thin_rgba = self.current_settings.get('grid_thin_color', (100/255, 100/255, 200/255, 50/255))
        self._update_color_button(self.thin_color_button, rgba_to_qcolor(thin_rgba))
        self.thin_color_button.clicked.connect(lambda: self._pick_color(self.thin_color_button, 'grid_thin_color'))
        form_layout.addRow("İnce çizgi rengi:", self.thin_color_button)

        # Kalın çizgi rengi
        self.thick_color_button = QPushButton()
        thick_rgba = self.current_settings.get('grid_thick_color', (60/255, 60/255, 160/255, 120/255))
        self._update_color_button(self.thick_color_button, rgba_to_qcolor(thick_rgba))
        self.thick_color_button.clicked.connect(lambda: self._pick_color(self.thick_color_button, 'grid_thick_color'))
        form_layout.addRow("Kalın çizgi rengi:", self.thick_color_button)

        # İnce çizgi kalınlığı
        self.thin_width_spin = QDoubleSpinBox()
        self.thin_width_spin.setRange(0.5, 5.0)
        self.thin_width_spin.setSingleStep(0.1)
        self.thin_width_spin.setValue(self.current_settings.get('grid_thin_width', 1.0))
        form_layout.addRow("İnce çizgi kalınlığı:", self.thin_width_spin)

        # Kalın çizgi kalınlığı
        self.thick_width_spin = QDoubleSpinBox()
        self.thick_width_spin.setRange(1.0, 10.0)
        self.thick_width_spin.setSingleStep(0.1)
        self.thick_width_spin.setValue(self.current_settings.get('grid_thick_width', 2.0))
        form_layout.addRow("Kalın çizgi kalınlığı:", self.thick_width_spin)

        # İnce çizgi saydamlığı
        self.thin_alpha_spin = QSpinBox()
        self.thin_alpha_spin.setRange(0, 255)
        thin_rgba = self.current_settings.get('grid_thin_color', (100/255, 100/255, 200/255, 50/255))
        self.thin_alpha_spin.setValue(int(thin_rgba[3]*255) if len(thin_rgba) > 3 else 50)
        form_layout.addRow("İnce çizgi saydamlığı:", self.thin_alpha_spin)

        # Kalın çizgi saydamlığı
        self.thick_alpha_spin = QSpinBox()
        self.thick_alpha_spin.setRange(0, 255)
        thick_rgba = self.current_settings.get('grid_thick_color', (60/255, 60/255, 160/255, 120/255))
        self.thick_alpha_spin.setValue(int(thick_rgba[3]*255) if len(thick_rgba) > 3 else 120)
        form_layout.addRow("Kalın çizgi saydamlığı:", self.thick_alpha_spin)

        # --- YENİ: Tüm sayfalara uygula seçeneği --- #
        self.apply_to_all_checkbox = QCheckBox("Tüm sayfalara uygula")
        self.apply_to_all_checkbox.setChecked(self.current_settings.get('grid_apply_to_all', True))
        form_layout.addRow("", self.apply_to_all_checkbox)

        # --- YENİ: Sadece çizgi aracı seçiliyken göster --- #
        self.only_line_tool_checkbox = QCheckBox("Sadece çizgi aracı seçiliyken göster")
        self.only_line_tool_checkbox.setChecked(self.current_settings.get('grid_only_line_tool', False))
        form_layout.addRow("", self.only_line_tool_checkbox)

        # --- YENİ: Varsayılana döndür butonu --- #
        self.reset_button = QPushButton("Varsayılana Döndür")
        self.reset_button.clicked.connect(self._reset_defaults)
        reset_layout = QHBoxLayout()
        reset_layout.addWidget(self.reset_button)
        form_layout.addRow("", self.reset_button)

        # Buton kutusu
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.button_box)

        self.thick_line_interval_spin.valueChanged.connect(self._emit_settings_changed)
        self.thin_color_button.clicked.connect(self._emit_settings_changed)
        self.thick_color_button.clicked.connect(self._emit_settings_changed)
        self.thin_width_spin.valueChanged.connect(self._emit_settings_changed)
        self.thick_width_spin.valueChanged.connect(self._emit_settings_changed)
        self.thin_alpha_spin.valueChanged.connect(self._emit_settings_changed)
        self.thick_alpha_spin.valueChanged.connect(self._emit_settings_changed)
        self.apply_to_all_checkbox.stateChanged.connect(self._emit_settings_changed)
        self.only_line_tool_checkbox.stateChanged.connect(self._emit_settings_changed)

    def _pick_color(self, button: QPushButton, key: str):
        current_rgba = self.current_settings.get(key, (0,0,0,1))
        color = QColorDialog.getColor(rgba_to_qcolor(current_rgba), self, "Renk Seç")
        if color.isValid():
            self.current_settings[key] = qcolor_to_rgba(color)
            self._update_color_button(button, color)

    def _update_color_button(self, button: QPushButton, color: QColor):
        button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid gray;")

    def _reset_defaults(self):
        self.thick_line_interval_spin.setValue(4)
        self.thin_color_button.setStyleSheet("background-color: #6464c8; border: 1px solid gray;")
        self.thick_color_button.setStyleSheet("background-color: #3c3ca0; border: 1px solid gray;")
        self.thin_width_spin.setValue(1.0)
        self.thick_width_spin.setValue(2.0)
        self.apply_to_all_checkbox.setChecked(True)
        self.only_line_tool_checkbox.setChecked(False)
        self.current_settings['grid_thin_color'] = (100/255, 100/255, 200/255, 50/255)
        self.current_settings['grid_thick_color'] = (60/255, 60/255, 160/255, 120/255)

    def get_settings(self) -> dict:
        # Renklerin alpha değerini güncelle
        thin_rgba = list(self.current_settings.get('grid_thin_color', (100/255, 100/255, 200/255, 50/255)))
        thick_rgba = list(self.current_settings.get('grid_thick_color', (60/255, 60/255, 160/255, 120/255)))
        if len(thin_rgba) < 4:
            thin_rgba += [1.0] * (4 - len(thin_rgba))
        if len(thick_rgba) < 4:
            thick_rgba += [1.0] * (4 - len(thick_rgba))
        thin_rgba[3] = self.thin_alpha_spin.value() / 255.0
        thick_rgba[3] = self.thick_alpha_spin.value() / 255.0
        return {
            'grid_thick_line_interval': self.thick_line_interval_spin.value(),
            'grid_thin_color': tuple(thin_rgba),
            'grid_thick_color': tuple(thick_rgba),
            'grid_thin_width': self.thin_width_spin.value(),
            'grid_thick_width': self.thick_width_spin.value(),
            'grid_apply_to_all': self.apply_to_all_checkbox.isChecked(),
            'grid_only_line_tool': self.only_line_tool_checkbox.isChecked(),
        }

    def _emit_settings_changed(self, *args):
        self.settings_changed.emit(self.get_settings()) 
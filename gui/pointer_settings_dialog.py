import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QDialogButtonBox, QColorDialog, QWidget, QLabel, QHBoxLayout
)
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import pyqtSignal, Qt

# Yardımcı fonksiyonlar (renk dönüşümü için)
def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black)
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

def qcolor_to_rgba(color: QColor) -> tuple:
    # QColor'dan doğrudan float (0-1) değerleri alalım
    return (color.redF(), color.greenF(), color.blueF(), color.alphaF())

class PointerSettingsDialog(QDialog):
    """Lazer ve Geçici İşaretçi ayarları için dialog penceresi."""
    # Ayarlar değiştiğinde emit edilir (OK veya Apply ile)
    settings_applied = pyqtSignal(dict) 
    # Anlık değişiklik sinyalleri (isteğe bağlı, şimdilik eklemeyelim)
    # laser_color_changed = pyqtSignal(tuple) 
    # ... vb.

    def __init__(self, current_settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("İşaretçi Ayarları")
        self.setMinimumWidth(450)

        # Başlangıç ayarlarının kopyasını sakla
        self.current_settings = current_settings.copy() 

        # Ana Layout
        main_layout = QVBoxLayout(self)

        # --- Lazer İşaretçi Grubu ---
        laser_group = QGroupBox("Lazer İşaretçi")
        laser_layout = QFormLayout()

        self.laser_color_button = QPushButton()
        self.laser_color_button.setToolTip("Lazer rengini seçmek için tıklayın")
        self._update_color_button(self.laser_color_button, QColor('#FF0000')) # Başlangıç rengi

        self.laser_size_spin = QSpinBox()
        self.laser_size_spin.setRange(1, 50)
        self.laser_size_spin.setSuffix(" px")
        
        laser_layout.addRow("Renk:", self.laser_color_button)
        laser_layout.addRow("Boyut:", self.laser_size_spin)
        laser_group.setLayout(laser_layout)
        main_layout.addWidget(laser_group)

        # --- Geçici İşaretçi Grubu ---
        temp_group = QGroupBox("Geçici İşaretçi (İz Bırakan)")
        temp_layout = QFormLayout()

        self.temp_color_button = QPushButton()
        self.temp_color_button.setToolTip("İz rengini seçmek için tıklayın")
        self._update_color_button(self.temp_color_button, QColor('#FFA500')) # Başlangıç rengi

        self.temp_width_spin = QDoubleSpinBox() # Kalınlık float olabilir
        self.temp_width_spin.setRange(0.5, 20.0)
        self.temp_width_spin.setSingleStep(0.5)
        self.temp_width_spin.setDecimals(1)
        self.temp_width_spin.setSuffix(" px")

        self.temp_duration_spin = QDoubleSpinBox() # Süre float olabilir
        self.temp_duration_spin.setRange(0.5, 30.0)
        self.temp_duration_spin.setSingleStep(0.5)
        self.temp_duration_spin.setDecimals(1)
        self.temp_duration_spin.setSuffix(" sn")

        # --- YENİ: Görünüm Faktörleri ---
        self.temp_glow_width_spin = QDoubleSpinBox()
        self.temp_glow_width_spin.setRange(0.1, 10.0); self.temp_glow_width_spin.setSingleStep(0.1)
        self.temp_glow_width_spin.setDecimals(1); self.temp_glow_width_spin.setToolTip("Temel genişliğe göre hale genişliği çarpanı")
        
        self.temp_core_width_spin = QDoubleSpinBox()
        self.temp_core_width_spin.setRange(0.1, 1.0); self.temp_core_width_spin.setSingleStep(0.05)
        self.temp_core_width_spin.setDecimals(2); self.temp_core_width_spin.setToolTip("Temel genişliğe göre çekirdek genişliği çarpanı (genellikle < 1)")

        self.temp_glow_alpha_spin = QDoubleSpinBox()
        self.temp_glow_alpha_spin.setRange(0.01, 1.0); self.temp_glow_alpha_spin.setSingleStep(0.05)
        self.temp_glow_alpha_spin.setDecimals(2); self.temp_glow_alpha_spin.setToolTip("Halenin maksimum opaklık çarpanı (0.0 - 1.0)")
        
        self.temp_core_alpha_spin = QDoubleSpinBox()
        self.temp_core_alpha_spin.setRange(0.01, 1.0); self.temp_core_alpha_spin.setSingleStep(0.05)
        self.temp_core_alpha_spin.setDecimals(2); self.temp_core_alpha_spin.setToolTip("Çekirdeğin maksimum opaklık çarpanı (0.0 - 1.0)")
        # --- Bitti: Görünüm Faktörleri ---

        temp_layout.addRow("Renk:", self.temp_color_button)
        temp_layout.addRow("Kalınlık:", self.temp_width_spin)
        temp_layout.addRow("Görünme Süresi:", self.temp_duration_spin)
        temp_layout.addRow("Hale Genişlik Fakt.:", self.temp_glow_width_spin)
        temp_layout.addRow("Çekirdek Genişlik Fakt.:", self.temp_core_width_spin)
        temp_layout.addRow("Hale Opaklık Fakt.:", self.temp_glow_alpha_spin)
        temp_layout.addRow("Çekirdek Opaklık Fakt.:", self.temp_core_alpha_spin)
        
        temp_group.setLayout(temp_layout)
        main_layout.addWidget(temp_group)

        # --- Buton Kutusu ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply 
        )
        main_layout.addWidget(self.button_box)

        # --- Başlangıç Değerlerini Yükle ---
        self._populate_widgets(self.current_settings)

        # --- Sinyal Bağlantıları ---
        self.button_box.accepted.connect(self._apply_and_accept) # OK = Uygula + Kapat
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_changes)
        
        self.laser_color_button.clicked.connect(self._pick_laser_color)
        self.temp_color_button.clicked.connect(self._pick_temp_color)
        
        logging.debug("PointerSettingsDialog oluşturuldu.")

    def _populate_widgets(self, settings: dict):
        """Widget'ları verilen ayarlarla doldurur."""
        # --- YENİ: Gelen ayarları logla ---
        logging.debug(f"_populate_widgets baslangici. Gelen ayarlar: {settings}")
        # --- --- --- --- --- --- --- --- ---
        
        # Lazer
        # --- YENİ: .get() kullanırken rengi doğrula --- 
        laser_color_val = settings.get('laser_pointer_color', '#FF0000') # String veya tuple olabilir
        if isinstance(laser_color_val, (list, tuple)):
             laser_color = rgba_to_qcolor(laser_color_val)
        elif isinstance(laser_color_val, str):
             laser_color = QColor(laser_color_val)
        else:
             laser_color = QColor('#FF0000') # Geçersizse varsayılan
        # --- --- --- --- --- --- --- --- --- --- --- ---
        self._update_color_button(self.laser_color_button, laser_color)
        self.laser_size_spin.setValue(settings.get('laser_pointer_size', 10))

        # Geçici İşaretçi
        # --- YENİ: .get() kullanırken rengi doğrula --- 
        temp_color_val = settings.get('temp_pointer_color', '#FFA500')
        if isinstance(temp_color_val, (list, tuple)):
             temp_color = rgba_to_qcolor(temp_color_val)
        elif isinstance(temp_color_val, str):
             temp_color = QColor(temp_color_val)
        else:
             temp_color = QColor('#FFA500') # Geçersizse varsayılan
        # --- --- --- --- --- --- --- --- --- --- --- ---
        self._update_color_button(self.temp_color_button, temp_color)
        self.temp_width_spin.setValue(settings.get('temp_pointer_width', 3.0))
        self.temp_duration_spin.setValue(settings.get('temp_pointer_duration', 5.0))
        
        # Görünüm Faktörleri
        self.temp_glow_width_spin.setValue(settings.get('temp_glow_width_factor', 2.5))
        self.temp_core_width_spin.setValue(settings.get('temp_core_width_factor', 0.5))
        self.temp_glow_alpha_spin.setValue(settings.get('temp_glow_alpha_factor', 0.55))
        self.temp_core_alpha_spin.setValue(settings.get('temp_core_alpha_factor', 0.9))
        
        # --- YENİ: Hatalı log mesajı kaldırıldı --- 
        # logging.debug(f"_populate_widgets finished. LaserSize={self.laser_size_spin.value()}\")
        # --- --- --- --- --- --- --- --- ---

    def _update_color_button(self, button: QPushButton, color: QColor):
        """Butonun arkaplanını ve metnini günceller."""
        button.setText(f"{color.name(QColor.NameFormat.HexArgb)}") # Hex kodu göster
        # button.setText(f"RGB: ({color.red()},{color.green()},{color.blue()}), Alpha: {color.alpha()}") # Eski
        palette = button.palette()
        if color.isValid():
            palette.setColor(QPalette.ColorRole.Button, color)
        button.setPalette(palette)
        button.setProperty("selected_color", color)

    def _pick_laser_color(self):
        """Lazer rengi seçimi için QColorDialog açar."""
        self._pick_color(self.laser_color_button, "Lazer Rengini Seçin")

    def _pick_temp_color(self):
        """Geçici işaretçi rengi seçimi için QColorDialog açar."""
        self._pick_color(self.temp_color_button, "Geçici İşaretçi Rengini Seçin")

    def _pick_color(self, button: QPushButton, title: str):
        """Genel renk seçme fonksiyonu."""
        initial_color = button.property("selected_color") or QColor()
        color = QColorDialog.getColor(initial_color, self, title, 
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._update_color_button(button, color)
            # Anlık sinyal gerekirse burada emit edilebilir
            # rgba = qcolor_to_rgba(color)
            # if button == self.laser_color_button:
            #     self.laser_color_changed.emit(rgba)
            # ... vb.

    def _apply_changes(self):
        """'Apply' butonuna basıldığında ayarları alır ve sinyal emitler."""
        logging.debug("Pointer Settings Apply button clicked.")
        current_dialog_settings = self.get_settings()
        # Mevcut ayarları güncelle (Dialog açıkken tekrar açılırsa diye)
        self.current_settings = current_dialog_settings.copy() 
        self.settings_applied.emit(current_dialog_settings)

    def _apply_and_accept(self):
        """'OK' butonuna basıldığında ayarları uygular ve diyalogu kapatır."""
        self._apply_changes()
        self.accept()

    def get_settings(self) -> dict:
        """Dialogdaki güncel ayarlarla bir sözlük döndürür."""
        settings = {}
        
        # Lazer
        laser_color = self.laser_color_button.property("selected_color")
        if laser_color and laser_color.isValid():
            # Ayarlara Hex string olarak kaydedelim (JSON uyumlu)
            settings['laser_pointer_color'] = laser_color.name(QColor.NameFormat.HexArgb) 
        settings['laser_pointer_size'] = self.laser_size_spin.value()

        # Geçici İşaretçi
        temp_color = self.temp_color_button.property("selected_color")
        if temp_color and temp_color.isValid():
            settings['temp_pointer_color'] = temp_color.name(QColor.NameFormat.HexArgb)
        settings['temp_pointer_width'] = self.temp_width_spin.value()
        settings['temp_pointer_duration'] = self.temp_duration_spin.value()
        
        # Görünüm Faktörleri
        settings['temp_glow_width_factor'] = self.temp_glow_width_spin.value()
        settings['temp_core_width_factor'] = self.temp_core_width_spin.value()
        settings['temp_glow_alpha_factor'] = self.temp_glow_alpha_spin.value()
        settings['temp_core_alpha_factor'] = self.temp_core_alpha_spin.value()

        logging.debug(f"Alinan pointer ayarlari: {settings}")
        return settings

# Bu bloğu test için çalıştırabilirsiniz: python gui/pointer_settings_dialog.py
if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    
    logging.basicConfig(level=logging.DEBUG) # Test için loglamayı aç
    app = QApplication(sys.argv)
    
    print("Test başlatılıyor...")
    # Örnek başlangıç ayarları
    initial_settings = {
        'laser_pointer_color': '#00FF00',
        'laser_pointer_size': 15,
        'temp_pointer_color': '#0000FF',
        'temp_pointer_width': 5.0,
        'temp_pointer_duration': 10.0
    }
    print(f"Başlangıç Ayarları: {initial_settings}")
    
    dialog = PointerSettingsDialog(initial_settings)
    print("Dialog oluşturuldu.")
    
    result = dialog.exec()
    print(f"Dialog sonucu: {result}")
    
    if result == QDialog.DialogCode.Accepted:
        new_settings = dialog.get_settings()
        print("Kabul Edildi:")
        print(new_settings)
    else:
        print("İptal Edildi")
        
    print("Test bitti.")
    sys.exit(0)
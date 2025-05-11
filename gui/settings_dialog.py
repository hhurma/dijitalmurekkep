import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox, 
    QPushButton, QDialogButtonBox, QColorDialog, QWidget, QLabel, QGroupBox, QHBoxLayout, QRadioButton, QButtonGroup, QDoubleSpinBox
)
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import pyqtSignal, Qt
from handlers import settings_handler
from PyQt6.QtWidgets import QPushButton # QPushButton importu eksikse ekle

from .enums import TemplateType

# Helper to convert RGBA float tuple (0-1) to QColor
def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black) # Varsayılan
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

# Helper to convert QColor to RGBA float tuple (0-1)
def qcolor_to_rgba(color: QColor) -> tuple:
    return (color.redF(), color.greenF(), color.blueF(), color.alphaF())


class TemplateSettingsDialog(QDialog):
    """Sayfa şablonu ayarları için dialog penceresi."""
    # Anlık değişiklik sinyalleri
    line_spacing_changed = pyqtSignal(int)
    grid_spacing_changed = pyqtSignal(int)
    line_color_changed = pyqtSignal(tuple)
    grid_color_changed = pyqtSignal(tuple)
    
    # Uygula butonu için sinyal
    apply_settings_requested = pyqtSignal(dict)
    # --- YENİ: Şablon Oluşturma Sinyali --- #
    generate_templates_requested = pyqtSignal(dict)
    # --- --- --- --- --- --- --- --- --- -- #

    def __init__(self, current_settings: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sayfa Şablonu Ayarları")
        self.setMinimumWidth(400)

        self._main_window = parent # parent'ın MainWindow olduğunu varsayıyoruz
        self.current_settings = current_settings.copy() # Ayarların kopyasını sakla

        # Layoutlar
        main_layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # --- Widget'lar ---
        # Şablon Tipi
        self.template_type_combo = QComboBox()
        self.template_type_combo.addItems([t.name.capitalize() for t in TemplateType])
        
        # Aralıklar (SpinBox)
        self.line_spacing_spin = QSpinBox()
        self.line_spacing_spin.setRange(5, 100) # pt cinsinden makul aralık
        self.line_spacing_spin.setSuffix(" pt")
        
        self.grid_spacing_spin = QSpinBox()
        self.grid_spacing_spin.setRange(5, 100) # pt cinsinden makul aralık
        self.grid_spacing_spin.setSuffix(" pt")

        # Renkler (Buton ile QColorDialog)
        self.line_color_button = QPushButton()
        self.line_color_button.setFlat(False) 
        self.line_color_button.setAutoFillBackground(True)
        self.line_color_button.setToolTip("Çizgi rengini seçmek için tıklayın")
        
        self.grid_color_button = QPushButton()
        self.grid_color_button.setFlat(False)
        self.grid_color_button.setAutoFillBackground(True)
        self.grid_color_button.setToolTip("Izgara rengini seçmek için tıklayın")

        # --- YENİ: PDF Resim Çözünürlüğü ---
        self.pdf_dpi_combo = QComboBox()
        self.pdf_dpi_options = {
            "72 DPI": 72,
            "96 DPI": 96,
            "150 DPI (Varsayılan)": 150,
            "300 DPI": 300
        }
        for text, dpi_val in self.pdf_dpi_options.items():
            self.pdf_dpi_combo.addItem(text, userData=dpi_val)
        
        # --- YENİ: Varsayılan Sayfa Yönü ---
        self.page_orientation_combo = QComboBox()
        self.page_orientation_options = {
            "Dikey": "portrait",
            "Yatay": "landscape"
        }
        for text, val in self.page_orientation_options.items():
            self.page_orientation_combo.addItem(text, userData=val)

        # --- Form Layout'a Ekleme ---
        form_layout.addRow("Şablon Türü:", self.template_type_combo)
        form_layout.addRow("Çizgi Aralığı:", self.line_spacing_spin)
        form_layout.addRow("Çizgi Rengi:", self.line_color_button)
        form_layout.addRow("Izgara Aralığı:", self.grid_spacing_spin)
        form_layout.addRow("Izgara Rengi:", self.grid_color_button)
        form_layout.addRow("PDF Resim Çözünürlüğü:", self.pdf_dpi_combo)
        form_layout.addRow("Varsayılan Sayfa Yönü:", self.page_orientation_combo)

        # --- YENİ: Şablon Oluşturma Butonu ---
        self.generate_template_button = QPushButton("Şablon Arka Planlarını Oluştur (JPG)")
        self.generate_template_button.setToolTip(
            "Mevcut ayarlara göre (A4, boşluklar, renkler) çizgili ve kareli şablonlar için \
            dikey/yatay JPG arka plan resimlerini 'generated_templates' klasörüne oluşturur.\
            PDF dışa aktarma bu resimleri kullanır."
        )

        # --- Buton Kutusu ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply 
        )

        # --- Ana Layout'a Ekleme ---
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.generate_template_button)
        main_layout.addWidget(self.button_box)

        # --- Başlangıç Değerlerini Ayarla ---
        self._populate_widgets()

        # --- Sinyal Bağlantıları ---
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_changes)
        self.template_type_combo.currentIndexChanged.connect(self._update_widget_states)
        self.line_color_button.clicked.connect(self._pick_line_color)
        self.grid_color_button.clicked.connect(self._pick_grid_color)
        # Anlık aralık sinyalleri
        self.line_spacing_spin.valueChanged.connect(self.line_spacing_changed.emit)
        self.grid_spacing_spin.valueChanged.connect(self.grid_spacing_changed.emit)
        
        # YENİ: Şablon oluşturma butonu bağlantısı
        self.generate_template_button.clicked.connect(self._emit_generate_templates_request)
        
        # Başlangıçta widget durumlarını ayarla
        self._update_widget_states()
        
        logging.debug("TemplateSettingsDialog oluşturuldu.")

    def _populate_widgets(self):
        """Widget'ları mevcut ayarlarla doldurur."""
        # Şablon tipi
        try:
            current_template = TemplateType[self.current_settings.get('template_type_name', 'PLAIN')] # Enum adı olarak al (varsa)
            index = self.template_type_combo.findText(current_template.name.capitalize())
            if index != -1:
                 self.template_type_combo.setCurrentIndex(index)
            else:
                 # Eğer settings'de type yoksa, varsayılanı kullanabiliriz
                 # Şimdilik ilk elemanı (PLAIN) seçelim
                 self.template_type_combo.setCurrentIndex(0) 
        except KeyError:
             logging.warning("Ayarlarda 'template_type_name' bulunamadı veya geçersiz, varsayılan kullanılıyor.")
             self.template_type_combo.setCurrentIndex(0)

        # Aralıklar
        self.line_spacing_spin.setValue(self.current_settings.get('line_spacing_pt', 28))
        self.grid_spacing_spin.setValue(self.current_settings.get('grid_spacing_pt', 14))

        # Renkler
        line_rgba = self.current_settings.get('line_color', (0.8, 0.8, 1.0, 0.7))
        self._update_color_button(self.line_color_button, rgba_to_qcolor(line_rgba))
        
        grid_rgba = self.current_settings.get('grid_color', (0.9, 0.9, 0.9, 0.8))
        self._update_color_button(self.grid_color_button, rgba_to_qcolor(grid_rgba))
        
        # --- YENİ: PDF DPI ---
        current_dpi = self.current_settings.get('pdf_export_image_dpi', 150)
        dpi_index = self.pdf_dpi_combo.findData(current_dpi)
        if dpi_index != -1:
            self.pdf_dpi_combo.setCurrentIndex(dpi_index)
        else: # Varsayılan olarak 150 DPI (veya listedeki ilk uygun olan)
            default_dpi_index = self.pdf_dpi_combo.findData(150)
            self.pdf_dpi_combo.setCurrentIndex(default_dpi_index if default_dpi_index !=-1 else 0)

        # --- YENİ: Sayfa Yönü ---
        current_orientation = self.current_settings.get('default_page_orientation', "portrait")
        orientation_index = self.page_orientation_combo.findData(current_orientation)
        if orientation_index != -1:
            self.page_orientation_combo.setCurrentIndex(orientation_index)
        else: # Varsayılan olarak portrait
            default_orientation_index = self.page_orientation_combo.findData("portrait")
            self.page_orientation_combo.setCurrentIndex(default_orientation_index if default_orientation_index != -1 else 0)
        
    def _update_widget_states(self):
        """Seçili şablon türüne göre widget'ların etkinliğini ayarlar."""
        selected_template_text = self.template_type_combo.currentText().upper()
        try:
            selected_template = TemplateType[selected_template_text]
        except KeyError:
            selected_template = TemplateType.PLAIN # Hata durumunda varsayılan

        is_lined = selected_template == TemplateType.LINED
        is_grid = selected_template == TemplateType.GRID

        self.line_spacing_spin.setEnabled(is_lined or is_grid) # Kareli de çizgili aralığını kullanabilir? Veya ayrı? Şimdilik ortak.
        self.line_color_button.setEnabled(is_lined or is_grid)
        self.grid_spacing_spin.setEnabled(is_grid)
        self.grid_color_button.setEnabled(is_grid)

    def _update_color_button(self, button: QPushButton, color: QColor):
        """Butonun arkaplanını ve metnini günceller."""
        button.setText(f"RGB: ({color.red()},{color.green()},{color.blue()}), Alpha: {color.alpha()}")
        palette = button.palette()
        palette.setColor(QPalette.ColorRole.Button, color)
        button.setPalette(palette)
        # Rengi saklamak için geçici bir özellik ekleyelim
        button.setProperty("selected_color", color) 

    def _pick_line_color(self):
        """Çizgi rengi seçimi için QColorDialog açar ve sinyal emitler."""
        initial_color = self.line_color_button.property("selected_color") or QColor(Qt.GlobalColor.blue)
        color = QColorDialog.getColor(initial_color, self, "Çizgi Rengini Seçin", 
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._update_color_button(self.line_color_button, color)
            rgba_color = qcolor_to_rgba(color)
            self.line_color_changed.emit(rgba_color)
            logging.debug(f"Line color picked and signal emitted: {rgba_color}")

    def _pick_grid_color(self):
        """Izgara rengi seçimi için QColorDialog açar ve sinyal emitler."""
        initial_color = self.grid_color_button.property("selected_color") or QColor(Qt.GlobalColor.lightGray)
        color = QColorDialog.getColor(initial_color, self, "Izgara Rengini Seçin", 
                                      QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._update_color_button(self.grid_color_button, color)
            rgba_color = qcolor_to_rgba(color)
            self.grid_color_changed.emit(rgba_color)
            logging.debug(f"Grid color picked and signal emitted: {rgba_color}")
            
    def _apply_changes(self):
        """Uygula butonuna basıldığında çağrılır."""
        logging.debug("Apply button clicked.")
        current_dialog_settings = self.get_settings()
        self.apply_settings_requested.emit(current_dialog_settings)
        
    # --- YENİ: Şablon Oluşturma Sinyalini Gönderen Metod --- #
    def _emit_generate_templates_request(self):
        """Diyaloğun o anki ayarlarıyla generate_templates_requested sinyalini gönderir."""
        logging.debug("Generate templates button clicked, emitting request signal...")
        current_dialog_settings = self.get_settings()
        self.generate_templates_requested.emit(current_dialog_settings)
    # --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def get_settings(self) -> dict:
        """Dialogdaki güncel ayarlarla bir sözlük döndürür."""
        settings = {}
        try:
             template_name = self.template_type_combo.currentText().upper()
             settings['template_type_name'] = template_name # Enum adını sakla
        except Exception:
             settings['template_type_name'] = 'PLAIN' # Hata durumunda
             
        settings['line_spacing_pt'] = self.line_spacing_spin.value()
        settings['grid_spacing_pt'] = self.grid_spacing_spin.value()
        
        line_color = self.line_color_button.property("selected_color")
        if line_color:
            settings['line_color'] = qcolor_to_rgba(line_color)
        
        grid_color = self.grid_color_button.property("selected_color")
        if grid_color:
            settings['grid_color'] = qcolor_to_rgba(grid_color)
            
        # --- YENİ: PDF DPI ve Sayfa Yönü ---
        selected_dpi_data = self.pdf_dpi_combo.currentData()
        if selected_dpi_data is not None:
            settings['pdf_export_image_dpi'] = int(selected_dpi_data)
        else: # Bir sorun olursa varsayılan
            settings['pdf_export_image_dpi'] = 150 

        selected_orientation_data = self.page_orientation_combo.currentData()
        if selected_orientation_data is not None:
            settings['default_page_orientation'] = str(selected_orientation_data)
        else: # Bir sorun olursa varsayılan
            settings['default_page_orientation'] = "portrait"
            
        return settings 

# --- YENİ: İşaretçi Ayarları Dialogu --- #
class PointerSettingsDialog(QDialog):
    """Lazer işaretçi ve geçici çizim işaretçisi ayarlarını düzenlemek için diyalog."""
    # Sinyal tanımlanabilir (anlık güncelleme için, şimdilik gerekli değil)
    # settings_changed = pyqtSignal(dict)

    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("İşaretçi Ayarları")
        self.settings = current_settings.copy() # Ayarların kopyasını al

        layout = QVBoxLayout(self)

        # --- Lazer İşaretçi Ayarları --- #
        laser_group = QGroupBox("Lazer İşaretçi")
        laser_layout = QFormLayout(laser_group)

        # Renk
        self.laser_color_button = QPushButton()
        self.laser_color_button.setToolTip("Lazer işaretçi rengini seçin")
        self._update_color_button_style(self.laser_color_button, self.settings.get('laser_pointer_color', '#FF0000'))
        self.laser_color_button.clicked.connect(lambda: self._select_color(self.laser_color_button, 'laser_pointer_color'))
        laser_layout.addRow("Renk:", self.laser_color_button)

        # Boyut
        self.laser_size_spinbox = QDoubleSpinBox()
        self.laser_size_spinbox.setRange(1.0, 100.0)
        self.laser_size_spinbox.setSingleStep(1.0)
        self.laser_size_spinbox.setValue(self.settings.get('laser_pointer_size', 10.0))
        self.laser_size_spinbox.setToolTip("Lazer işaretçi boyutunu (piksel) ayarlayın")
        laser_layout.addRow("Boyut (px):", self.laser_size_spinbox)

        layout.addWidget(laser_group)

        # --- Geçici İşaretçi Ayarları --- #
        temp_group = QGroupBox("Geçici İşaretçi (Çizim)")
        temp_layout = QFormLayout(temp_group)

        # Renk
        self.temp_color_button = QPushButton()
        self.temp_color_button.setToolTip("Geçici işaretçi rengini seçin")
        self._update_color_button_style(self.temp_color_button, self.settings.get('temp_pointer_color', '#FFA500'))
        self.temp_color_button.clicked.connect(lambda: self._select_color(self.temp_color_button, 'temp_pointer_color'))
        temp_layout.addRow("Renk:", self.temp_color_button)

        # Kalınlık
        self.temp_width_spinbox = QDoubleSpinBox()
        self.temp_width_spinbox.setRange(0.5, 50.0)
        self.temp_width_spinbox.setSingleStep(0.5)
        self.temp_width_spinbox.setValue(self.settings.get('temp_pointer_width', 3.0))
        self.temp_width_spinbox.setToolTip("Geçici işaretçi çizgi kalınlığını (piksel) ayarlayın")
        temp_layout.addRow("Kalınlık (px):", self.temp_width_spinbox)

        # Süre
        self.temp_duration_spinbox = QDoubleSpinBox()
        self.temp_duration_spinbox.setRange(0.5, 60.0) # Saniye cinsinden
        self.temp_duration_spinbox.setSingleStep(0.5)
        self.temp_duration_spinbox.setValue(self.settings.get('temp_pointer_duration', 5.0))
        self.temp_duration_spinbox.setToolTip("Çizginin ekranda kalma süresi (saniye)")
        temp_layout.addRow("Süre (sn):", self.temp_duration_spinbox)
        
        # --- Yeni Görünüm Faktörleri --- #
        temp_appearance_group = QGroupBox("Geçici İşaretçi Görünümü")
        temp_appearance_layout = QFormLayout(temp_appearance_group)
        
        self.temp_glow_width_factor_spin = QDoubleSpinBox()
        self.temp_glow_width_factor_spin.setRange(1.0, 10.0); self.temp_glow_width_factor_spin.setSingleStep(0.1)
        self.temp_glow_width_factor_spin.setValue(self.settings.get('temp_glow_width_factor', 2.5))
        self.temp_glow_width_factor_spin.setToolTip("Dış parlama genişlik çarpanı (kalem kalınlığına göre)")
        temp_appearance_layout.addRow("Parlama Genişlik Çarpanı:", self.temp_glow_width_factor_spin)
        
        self.temp_core_width_factor_spin = QDoubleSpinBox()
        self.temp_core_width_factor_spin.setRange(0.1, 1.0); self.temp_core_width_factor_spin.setSingleStep(0.1)
        self.temp_core_width_factor_spin.setValue(self.settings.get('temp_core_width_factor', 0.5))
        self.temp_core_width_factor_spin.setToolTip("İç çekirdek genişlik çarpanı (kalem kalınlığına göre)")
        temp_appearance_layout.addRow("Çekirdek Genişlik Çarpanı:", self.temp_core_width_factor_spin)
        
        self.temp_glow_alpha_factor_spin = QDoubleSpinBox()
        self.temp_glow_alpha_factor_spin.setRange(0.0, 1.0); self.temp_glow_alpha_factor_spin.setSingleStep(0.05)
        self.temp_glow_alpha_factor_spin.setValue(self.settings.get('temp_glow_alpha_factor', 0.55))
        self.temp_glow_alpha_factor_spin.setToolTip("Dış parlama opaklık çarpanı (0.0 - 1.0)")
        temp_appearance_layout.addRow("Parlama Opaklık Çarpanı:", self.temp_glow_alpha_factor_spin)
        
        self.temp_core_alpha_factor_spin = QDoubleSpinBox()
        self.temp_core_alpha_factor_spin.setRange(0.0, 1.0); self.temp_core_alpha_factor_spin.setSingleStep(0.05)
        self.temp_core_alpha_factor_spin.setValue(self.settings.get('temp_core_alpha_factor', 0.9))
        self.temp_core_alpha_factor_spin.setToolTip("İç çekirdek opaklık çarpanı (0.0 - 1.0)")
        temp_appearance_layout.addRow("Çekirdek Opaklık Çarpanı:", self.temp_core_alpha_factor_spin)
        
        temp_layout.addRow(temp_appearance_group) # Görünüm grubunu ana gruba ekle
        # --- --- --- --- --- --- --- --- #

        layout.addWidget(temp_group)

        # --- OK / Cancel Butonları --- #
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _update_color_button_style(self, button: QPushButton, color_hex: str):
        """Butonun arkaplan rengini ve metnini günceller."""
        try:
            button.setStyleSheet(f"background-color: {color_hex}; color: {self._get_contrasting_text_color(color_hex)};")
            button.setText(color_hex.upper())
        except Exception as e:
            logging.warning(f"Renk butonu stili güncellenirken hata: {e}")
            button.setStyleSheet("") # Hata durumunda stili sıfırla
            button.setText("Renk Seç")
            
    def _get_contrasting_text_color(self, bg_color_hex: str) -> str:
        """Verilen arkaplan rengine göre okunabilir metin rengi (siyah veya beyaz) döndürür."""
        try:
            color = QColor(bg_color_hex)
            # Parlaklık hesaplama (basit formül)
            brightness = (color.red() * 299 + color.green() * 587 + color.blue() * 114) / 1000
            return "#000000" if brightness > 128 else "#FFFFFF"
        except Exception:
            return "#000000" # Hata durumunda siyah

    def _select_color(self, button: QPushButton, setting_key: str):
        """Renk seçme diyaloğunu açar ve seçilen rengi uygular."""
        current_color_hex = self.settings.get(setting_key, '#FFFFFF')
        current_qcolor = QColor(current_color_hex)
        
        color_dialog = QColorDialog(current_qcolor, self)
        # color_dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel) # Alfa kanalı istenirse
        if color_dialog.exec():
            new_color = color_dialog.selectedColor()
            if new_color.isValid():
                new_color_hex = new_color.name().upper() # #RRGGBB formatında al
                self.settings[setting_key] = new_color_hex
                self._update_color_button_style(button, new_color_hex)
                logging.debug(f"Renk ayarı '{setting_key}' güncellendi: {new_color_hex}")
                # Anlık güncelleme istenirse burada sinyal gönderilebilir

    def get_settings(self) -> dict:
        """Dialogdaki kontrollerden güncel ayar değerlerini alır."""
        # Renkler zaten self.settings içinde güncellendi
        self.settings['laser_pointer_size'] = self.laser_size_spinbox.value()
        self.settings['temp_pointer_width'] = self.temp_width_spinbox.value()
        self.settings['temp_pointer_duration'] = self.temp_duration_spinbox.value()
        # Yeni faktörler
        self.settings['temp_glow_width_factor'] = self.temp_glow_width_factor_spin.value()
        self.settings['temp_core_width_factor'] = self.temp_core_width_factor_spin.value()
        self.settings['temp_glow_alpha_factor'] = self.temp_glow_alpha_factor_spin.value()
        self.settings['temp_core_alpha_factor'] = self.temp_core_alpha_factor_spin.value()
        return self.settings
# --- --- --- --- --- --- --- --- --- -- # 
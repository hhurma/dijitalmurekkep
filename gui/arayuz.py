import logging
import json # JSON okumak için eklendi
import os   # Dosya yolu için eklendi
from functools import partial # partial import edildi
# QtWidgets ve QtGui modüllerini ayrı ayrı import edelim
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QToolBar,
    QColorDialog, QPushButton, QApplication, QSizePolicy, QLabel, QSpinBox, QMenu,
    QMessageBox, QHBoxLayout, QTabWidget, QStatusBar, QFileDialog, QSlider, QCheckBox, QScrollArea # QStatusBar ve QFileDialog eklendi, QSlider eklendi, QCheckBox eklendi, QScrollArea eklendi
)
from PyQt6.QtGui import QAction, QIcon, QColor, QActionGroup, QKeySequence, QCloseEvent, QScreen # QScreen eklendi
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, QPoint, QRectF # QTimer eklendi, QRectF eklendi
import qtawesome as qta # qtawesome import edildi
from typing import List
import time
import shutil
import uuid
import sys
import hashlib

from .page import Page
from .page_manager import PageManager
from utils.undo_redo_manager import UndoRedoManager # YENİ: _log_and_call içinde isinstance için gerekli
from .enums import TemplateType, ToolType, Orientation # YENİDEN EKLENDİ
from .grid_settings_dialog import GridSettingsDialog # YENİ EKLENDİ

# Handler importları
from handlers import page_handler, tool_handler, canvas_handler, action_handler, file_handler, settings_handler, pdf_handler # settings_handler ve pdf_handler eklendi
# --- --- --- --- --- --- --- --- --- --- -- #
from handlers import clipboard_handler
from handlers import shape_pool_handler
from handlers import resim_islem_handler # YENİ: Resim işlem handler'ını ekle

def get_config_file_path():
    import sys
    import os
    if getattr(sys, 'frozen', False):
        # PyInstaller ile derlenmiş exe
        base_dir = os.path.dirname(sys.executable)
    else:
        # Normal Python çalıştırması
        base_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(base_dir, 'config')
    os.makedirs(config_dir, exist_ok=True)
    config_filename = 'settings.json'
    return os.path.join(config_dir, config_filename)

CONFIG_FILE = get_config_file_path()
DEFAULT_TEMPLATE_SETTINGS = {
    "template_type_name": "LINED",
    "line_spacing_pt": 30,
    "grid_spacing_pt": 14,
    "line_color": [0.0, 0.3333333432674408, 1.0, 0.6980392336845398],
    "grid_color": [0.8980392217636108, 0.8980392217636108, 0.8980392217636108, 0.800000011920929],
    "pdf_export_image_dpi": 150,
    "default_page_orientation": "landscape"
}

# --- YENİ: Varsayılan Grid Ayarları ---
DEFAULT_GRID_SETTINGS = {
    "grid_snap_enabled": False,
    "grid_visible_on_snap": True,
    "grid_show_for_line_tool_only": False,
    "grid_apply_to_all_pages": True,
    "grid_thick_line_interval": 4,
    "grid_thin_color": [0.0, 0.0, 0.49803921580314636, 0.0784313725490196],
    "grid_thick_color": [0.6666666865348816, 0.0, 0.0, 0.1568627450980392],
    "grid_thin_width": 0.9999999999999992,
    "grid_thick_width": 1.0
}
# --- --- --- --- --- --- --- --- --- ---

# MAX_RECENT_FILES = 5 # Kaldırıldı

LONG_PRESS_DURATION = 600 # Milisaniye

# Yeni: Seçili buton stili
SELECTED_BUTTON_STYLE = """
QPushButton {
    background-color: %s;
    border: 3px solid #007bff; /* Daha belirgin mavi kenarlık */
    border-radius: 5px;
}
"""

# Yeni: Normal buton stili
NORMAL_BUTTON_STYLE = """
QPushButton {
    background-color: %s;
    border: 1px solid gray;
    border-radius: 5px; /* Köşeleri yuvarlat */
}
QPushButton:hover {
    border: 2px solid black; /* Üzerine gelince kenarlık */
}
"""

class MainWindow(QMainWindow):
    """Uygulamanın ana penceresi (Çok sayfalı, Handler yapısı ile)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = {}  # --- HATA DÜZELTME: settings her zaman tanımlı olsun ---
        
        # --- Ayarları Yükle ---
        self._load_settings() # Artık recent_files'ı da yükleyecek
        template_settings = self.settings.get('template_settings', DEFAULT_TEMPLATE_SETTINGS)
        # --- --- ---
        
        # --- Doldurma rengi ve alpha değişkenleri (toolbar'dan önce!) --- #
        self.current_fill_color = QColor(255, 255, 255, 0)  # Başlangıçta şeffaf beyaz
        self.current_fill_alpha = 0  # 0: tamamen şeffaf, 255: tamamen opak
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # --- Page Manager Önce Oluşturulmalı --- #
        # Page Manager ve Durum Çubuğu (Başlık güncellemesinden önce)
        central_widget = QWidget() # Geçici olarak burada oluştur, sonra set et
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0) # Kenar boşlukları sıfırlandı
        # --- DEĞİŞİKLİK: Parent'ı self yap --- #
        self.page_manager = PageManager(parent=self, template_settings=template_settings)
        # --- --- --- --- --- --- --- --- --- -- #
        # --- --- --- --- --- --- --- --- --- --- --- ---

        self.current_notebook_path: str | None = None # Geçerli dosya yolunu tut
        self._update_window_title() # Başlangıç başlığını ayarla (Artık page_manager var)
        
        # --- YENİ: Renk/Kalınlık Başlangıç Değerleri --- #
        self.current_pen_color = QColor(Qt.GlobalColor.black) # Başlangıç rengi
        # --- YENİ: Hızlı Renk Butonları Listesi ve Layout Widget --- #
        self.quick_color_buttons: List[QPushButton] = []
        self.quick_color_widget = QWidget()
        self.quick_color_layout = QHBoxLayout(self.quick_color_widget)
        self.quick_color_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_color_layout.setSpacing(1) # Buton arası 1px boşluk
        # --- YENİ: Uzun basma için zamanlayıcı ve durum --- #
        self.long_press_timer = QTimer(self)
        self.long_press_timer.setInterval(LONG_PRESS_DURATION)
        self.long_press_timer.setSingleShot(True)
        self.long_press_timer.timeout.connect(self._handle_long_press_timeout)
        self.pressed_color_button: QPushButton | None = None
        self.was_long_press = False # Uzun basma gerçekleşti mi?
        # --- YENİ: Seçili renk butonunu takip etmek için --- #
        self.selected_color_button: QPushButton | None = None
        # --- --- --- --- --- --- --- --- --- --- --- --- ---

        window_width = self.settings.get("window_width", 1200)
        window_height = self.settings.get("window_height", 800)
        self.setWindowTitle("Dijital Mürekkep") # Başlangıçta uygulama adı
        self.setGeometry(100, 100, window_width, window_height)

        # Aktif sayfanın undo manager'ını tutmak için referans
        self.current_page_undo_manager = None

        # Page Manager ve Durum Çubuğu (Central widget'ı şimdi set et)
        self.setCentralWidget(central_widget)
        # layout = QVBoxLayout(central_widget) # Layout zaten oluşturuldu
        # layout.setContentsMargins(5, 5, 5, 5)
        # self.page_manager = PageManager(parent=central_widget, template_settings=template_settings) # Yukarı taşındı
        layout.addWidget(self.page_manager, 1) # PageManager'ı layout'a ekle

        # Durum çubuğu (Sayfa numarasını göstermek için)
        self.status_bar = self.statusBar() # QStatusBar nesnesini al
        self.page_label = QLabel("Sayfa: -/-")
        self.status_bar.addPermanentWidget(self.page_label)

        # Başlangıçta bir sayfa ekle
        self.page_manager.add_page()

        # Toolbar ve Menü oluştur (Actionlar artık aktif sayfaya göre çalışacak)
        self._create_actions() # Bu çağrıdan ÖNCE renk/kalınlık tanımlanmalı
        self._create_toolbar() # Bu çağrıdan ÖNCE renk/kalınlık tanımlanmalı
        self._create_menus()

        # Sinyal bağlantıları
        self.page_manager.current_page_changed.connect(self._update_active_page_connections)
        self.page_manager.page_count_changed.connect(self._update_page_label)

        # Başlangıç bağlantılarını yap (ilk sayfa için)
        self._update_active_page_connections(self.page_manager.get_current_page())
        self._update_page_label(self.page_manager.page_count(), self.page_manager.current_index())

        # Aktif sayfa değiştiğinde bağlantıları güncelle
        self.page_manager.current_page_changed.connect(self._update_active_page_connections)
        self.page_manager.page_count_changed.connect(self.update_actions_state)
        
        # --- Dosya Eylem Bağlantıları Güncelleme ---
        self.save_action.triggered.connect(lambda: file_handler.handle_save_notebook(self, self.page_manager, save_as=False))
        self.save_as_action.triggered.connect(lambda: file_handler.handle_save_notebook_as(self, self.page_manager))
        self.load_action.triggered.connect(lambda: file_handler.handle_load_notebook(self, self.page_manager))
        # self.export_pdf_action.triggered.connect(self._trigger_export_pdf) # --- BU SATIR KALDIRILACAK ---
        # --- --- --- --- --- --- --- --- --- --- 

        # --- YENİ: Ayarlardan yüklenen son dosyaları menüye ekle ---
        self._update_recent_files_menu() # Ayarlardan okuyacak
        # --- --- --- --- --- --- --- --- --- --- --- --- ---

        self.update_actions_state()

        logging.info("MainWindow başlatıldı, Page Manager ve Handler yapısı entegre edildi.")

        # self._setup_signals() # Hata veren satır kaldırıldı
        self._load_settings() # Ayarları yükle

        # --- YENİ: Pencereyi Ekran Ortasına Taşı ---
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_geometry = self.frameGeometry()
                window_geometry.moveCenter(screen_geometry.center())
                self.move(window_geometry.topLeft())
                logging.info("Ana pencere ekran ortasına taşındı.")
            else:
                logging.warning("Birincil ekran bilgisi alınamadı, pencere ortalanamadı.")
        except Exception as e:
             logging.error(f"Pencere ortalanırken hata oluştu: {e}", exc_info=True)
        # --- --- --- --- --- --- --- --- --- --- ---

        logging.info("MainWindow başlatıldı.")

        # Timer'ı başlat
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16) # Yaklaşık 60 FPS için

        # --- YENİ: Son kullanılan kaydet/yükle dizinini saklamak için --- #
        self.last_save_load_directory = ""
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: PDF Export çift çağrı kontrolü için --- #
        self._last_export_pdf_call = 0.0 
        # --- --- --- --- --- --- --- --- --- --- --- --- -- #

        # --- SON KONTROL: İlk sayfa için bağlantıları kesinleştir --- #
        self._update_active_page_connections(self.page_manager.get_current_page())
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

    def _create_actions(self):
        """Menü ve Toolbar için QAction nesnelerini oluşturur (ikonlu ve handler bağlantılı)."""
        # ----- Sayfa Yönetimi -----
        self.new_page_action = QAction(self)
        self.new_page_action.setIcon(qta.icon('fa5s.plus-square', color='green'))
        self.new_page_action.setText("Yeni Sayfa")
        self.new_page_action.setToolTip("Yeni Sayfa Ekle (Ctrl+N)")
        self.new_page_action.setShortcut(QKeySequence.StandardKey.New)
        # Handler'a page_manager'ı parametre olarak gönder
        self.new_page_action.triggered.connect(lambda: page_handler.handle_add_page(self.page_manager))

        self.delete_page_action = QAction(self)
        self.delete_page_action.setIcon(qta.icon('fa5s.trash-alt', color='red'))
        self.delete_page_action.setText("Sayfayı Sil")
        self.delete_page_action.setToolTip("Geçerli Sayfayı Sil (Delete)")
        self.delete_page_action.setShortcut(QKeySequence.StandardKey.Delete)
        self.delete_page_action.triggered.connect(lambda: page_handler.handle_remove_current_page(self.page_manager))
        self.delete_page_action.setEnabled(False)

        self.prev_page_action = QAction(self)
        self.prev_page_action.setIcon(qta.icon('fa5s.arrow-left'))
        self.prev_page_action.setText("Önceki Sayfa")
        self.prev_page_action.setToolTip("Önceki Sayfaya Git (PageUp)")
        self.prev_page_action.setShortcut(QKeySequence.StandardKey.MoveToPreviousPage)
        self.prev_page_action.triggered.connect(lambda: page_handler.handle_previous_page(self.page_manager))
        self.prev_page_action.setEnabled(False)

        self.next_page_action = QAction(self)
        self.next_page_action.setIcon(qta.icon('fa5s.arrow-right'))
        self.next_page_action.setText("Sonraki Sayfa")
        self.next_page_action.setToolTip("Sonraki Sayfaya Git (PageDown)")
        self.next_page_action.setShortcut(QKeySequence.StandardKey.MoveToNextPage)
        self.next_page_action.triggered.connect(lambda: page_handler.handle_next_page(self.page_manager))
        self.next_page_action.setEnabled(False)

        # ----- Düzenleme -----
        self.undo_action = QAction(self)
        self.undo_action.setIcon(qta.icon('fa5s.undo'))
        self.undo_action.setText("Geri Al")
        self.undo_action.setToolTip("Geri Al (Ctrl+Z)")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        # Bağlantı _update_active_page_connections içinde yapılacak (aktif manager'a göre)
        self.undo_action.setEnabled(False)

        self.redo_action = QAction(self)
        self.redo_action.setIcon(qta.icon('fa5s.redo'))
        self.redo_action.setText("İleri Al")
        self.redo_action.setToolTip("İleri Al (Ctrl+Y)")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        # Bağlantı _update_active_page_connections içinde yapılacak
        self.redo_action.setEnabled(False)

        self.clear_action = QAction(self)
        self.clear_action.setIcon(qta.icon('fa5s.eraser'))
        self.clear_action.setText("Sayfayı Temizle")
        self.clear_action.setToolTip("Sayfayı Temizle (Shift+Delete)")
        self.clear_action.setShortcut(QKeySequence(Qt.Key.Key_Delete | Qt.KeyboardModifier.ShiftModifier))
        # Bağlantı _update_active_page_connections içinde yapılacak (aktif page_manager'a göre)
        self.clear_action.setEnabled(False) # Başlangıçta aktif sayfa yüklenene kadar pasif

        # --- YENİ: Resim Ekle Action --- #
        self.add_image_action = QAction(self)
        self.add_image_action.setIcon(qta.icon('fa5s.image', color='teal'))
        self.add_image_action.setText("Resim Ekle...")
        self.add_image_action.setToolTip("Sayfaya bir resim dosyası ekle")
        self.add_image_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_I))
        self.add_image_action.triggered.connect(self._handle_select_image_action)
        # --- --- --- --- --- --- --- --- -- #
        
        # --- YENİ: Resmi Sil Action --- #
        self.delete_image_action = QAction(self)
        self.delete_image_action.setIcon(qta.icon('fa5s.trash', color='red'))
        self.delete_image_action.setText("Resmi Sil")
        self.delete_image_action.setToolTip("Seçili resmi sil")
        self.delete_image_action.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_D))
        self.delete_image_action.triggered.connect(self._handle_delete_image_action)
        # --- --- --- --- --- --- --- --- -- #

        # ----- Araç Seçimi -----
        self.tool_actions = QActionGroup(self)
        self.tool_actions.setExclusive(True)

        # Her araç action'ı tool_handler.handle_set_active_tool'u çağıracak
        self.pen_tool_action = QAction(self)
        self.pen_tool_action.setIcon(qta.icon('fa5s.pen'))
        self.pen_tool_action.setText("Kalem")
        self.pen_tool_action.setToolTip("Serbest Çizim Aracı")
        self.pen_tool_action.setCheckable(True)
        self.pen_tool_action.setChecked(True)
        self.pen_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.PEN))
        self.tool_actions.addAction(self.pen_tool_action)

        self.line_tool_action = QAction(self)
        self.line_tool_action.setIcon(qta.icon('fa5s.minus'))
        self.line_tool_action.setText("Çizgi")
        self.line_tool_action.setToolTip("Düz Çizgi Çizme Aracı")
        self.line_tool_action.setCheckable(True)
        self.line_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.LINE))
        self.tool_actions.addAction(self.line_tool_action)

        # Düzenlenebilir Çizgi Aracı
        self.editable_line_tool_action = QAction(self)
        self.editable_line_tool_action.setIcon(qta.icon('fa5s.pen-fancy'))
        self.editable_line_tool_action.setText("Düzenlenebilir Çizgi")
        self.editable_line_tool_action.setToolTip("Düzenlenebilir Çizgi Aracı")
        self.editable_line_tool_action.setCheckable(True)
        self.editable_line_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.EDITABLE_LINE))
        self.tool_actions.addAction(self.editable_line_tool_action)

        self.rect_tool_action = QAction(self)
        self.rect_tool_action.setIcon(qta.icon('fa5s.square'))
        self.rect_tool_action.setText("Dikdörtgen")
        self.rect_tool_action.setToolTip("Dikdörtgen Çizme Aracı")
        self.rect_tool_action.setCheckable(True)
        self.rect_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.RECTANGLE))
        self.tool_actions.addAction(self.rect_tool_action)

        self.circle_tool_action = QAction(self)
        self.circle_tool_action.setIcon(qta.icon('fa5s.circle'))
        self.circle_tool_action.setText("Daire")
        self.circle_tool_action.setToolTip("Daire Çizme Aracı")
        self.circle_tool_action.setCheckable(True)
        self.circle_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.CIRCLE))
        self.tool_actions.addAction(self.circle_tool_action)

        # Seçim Aracı (Yeni)
        self.select_tool_action = QAction(self)
        self.select_tool_action.setIcon(qta.icon('fa5s.mouse-pointer'))
        self.select_tool_action.setText("Seç")
        self.select_tool_action.setToolTip("Seçim Aracı")
        self.select_tool_action.setCheckable(True)
        self.select_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.SELECTOR))
        self.tool_actions.addAction(self.select_tool_action)

        # Silgi Aracı (Yeni)
        self.eraser_tool_action = QAction(self)
        self.eraser_tool_action.setIcon(qta.icon('fa5s.eraser'))
        self.eraser_tool_action.setText("Silgi")
        self.eraser_tool_action.setToolTip("Silgi Aracı")
        self.eraser_tool_action.setCheckable(True)
        self.eraser_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.ERASER))
        self.tool_actions.addAction(self.eraser_tool_action)

        # --- YENİ: Resim Seçim Aracı Action --- #
        self.image_select_action = QAction(self)
        self.image_select_action.setIcon(qta.icon('fa5s.object-group', color='purple')) # Farklı bir ikon deneyelim
        self.image_select_action.setText("Resim Seç")
        self.image_select_action.setToolTip("Eklenen resimleri seç, taşı, boyutlandır")
        self.image_select_action.setCheckable(True)
        self.image_select_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.IMAGE_SELECTOR))
        self.tool_actions.addAction(self.image_select_action)
        # --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Lazer İşaretçi Aracı --- #
        self.laser_pointer_action = QAction(self)
        self.laser_pointer_action.setIcon(qta.icon('fa5s.bullseye', color='red')) # Örnek ikon
        self.laser_pointer_action.setText("Lazer")
        self.laser_pointer_action.setToolTip("Lazer İşaretçi")
        self.laser_pointer_action.setCheckable(True)
        self.laser_pointer_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.LASER_POINTER))
        self.tool_actions.addAction(self.laser_pointer_action)
        # --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Geçici Çizim Aracı --- #
        self.temporary_pointer_action = QAction(self)
        self.temporary_pointer_action.setIcon(qta.icon('fa5s.highlighter', color='orange')) # Örnek ikon
        self.temporary_pointer_action.setText("Geçici Çizim")
        self.temporary_pointer_action.setToolTip("Geçici Çizim Aracı")
        self.temporary_pointer_action.setCheckable(True)
        self.temporary_pointer_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.TEMPORARY_POINTER))
        self.tool_actions.addAction(self.temporary_pointer_action)
        # --- --- --- --- --- --- --- --- -- #

        self.tool_actions.triggered.connect(self._update_width_spinbox_for_tool) # Grup tetiklenince spinbox'ı güncelle

        # ----- Şablon Ayarları -----
        self.plain_template_action = QAction("Düz Beyaz", self, checkable=True)
        self.lined_template_action = QAction("Çizgili", self, checkable=True)
        self.grid_template_action = QAction("Kareli", self, checkable=True)
        # Bağlantılar _update_active_page_connections içinde yapılacak (aktif page_manager'a göre)

        self.template_group = QActionGroup(self)
        self.template_group.addAction(self.plain_template_action)
        self.template_group.addAction(self.lined_template_action)
        self.template_group.addAction(self.grid_template_action)
        self.template_group.setExclusive(True)

        # ----- Sayfa Yönü ----- # YENİ
        self.portrait_action = QAction("Dikey", self, checkable=True)
        self.landscape_action = QAction("Yatay", self, checkable=True)
        # Bağlantılar _update_active_page_connections içinde yapılacak
        
        self.orientation_group = QActionGroup(self)
        self.orientation_group.addAction(self.portrait_action)
        self.orientation_group.addAction(self.landscape_action)
        self.orientation_group.setExclusive(True)
        # --- --- --- --- --- ---

        # --- Dosya Eylemleri --- # YENİ
        self.save_action = QAction(qta.icon('fa5s.save', color='blue'), "&Kaydet", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setStatusTip("Mevcut not defterini kaydet")

        self.save_as_action = QAction(qta.icon('fa5s.save', color='darkblue'), "Farklı Kaydet...", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_as_action.setStatusTip("Not defterini farklı bir isimle kaydet")

        self.load_action = QAction(qta.icon('fa5s.folder-open', color='blue'), "&Aç...", self)
        self.load_action.setShortcut(QKeySequence.StandardKey.Open)
        self.load_action.setStatusTip("Not defteri dosyasını aç")
        
        # --- YENİ: PDF İçe Aktarma Eylemi ---
        self.import_pdf_action = QAction(qta.icon('fa5s.file-import', color='green'), "PDF İçe Aktar...", self)
        self.import_pdf_action.setStatusTip("Bir PDF dosyasını sayfalara aktar")
        # MainWindow (self) ve PageManager örneğini aktar
        self.import_pdf_action.triggered.connect(lambda checked=False, mw=self, pm=self.page_manager: pdf_handler.handle_import_pdf(parent_window=mw, page_manager=pm))
        # --- --- --- --- --- --- --- --- --- ---

        self.export_pdf_action = QAction(QIcon(":/icons/pdf.png"), "PDF Olarak Dışa Aktar", self)
        # --- DÜZELTME: Lambda yerine doğrudan metod bağlantısı --- #
        self.export_pdf_action.triggered.connect(self._trigger_export_pdf)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #
        self.exit_action = QAction(QIcon(":/icons/exit.png"), "Çıkış", self)
        self.exit_action.triggered.connect(self.close) # closeEvent tetikler

        # --- Ayarlar Action --- # YENİ
        self.settings_action = QAction(qta.icon('fa5s.cog', color='gray'), "Sayfa Ayarları...", self)
        self.settings_action.setStatusTip("Sayfa şablonu ayarlarını düzenle")
        # Bağlantı
        self.settings_action.triggered.connect(lambda: settings_handler.handle_open_template_settings(self))
        # --- --- --- --- --- ---

        # --- YENİ: İşaretçi Ayarları Action --- #
        self.pointer_settings_action = QAction(qta.icon('fa5s.mouse-pointer', color='purple'), "İşaretçi Ayarları...", self)
        self.pointer_settings_action.setStatusTip("Lazer ve geçici çizim işaretçisi ayarları")
        self.pointer_settings_action.triggered.connect(lambda: settings_handler.handle_open_pointer_settings(self))
        # --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Görünüm/Zoom Actions --- #
        self.zoom_in_action = QAction(qta.icon('fa5s.search-plus', color='blue'), "Yakınlaş", self)
        self.zoom_in_action.setStatusTip("Görünümü Yakınlaştır (Ctrl++) ")
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.triggered.connect(self._handle_zoom_in_pdf_only)

        self.zoom_out_action = QAction(qta.icon('fa5s.search-minus', color='blue'), "Uzaklaş", self)
        self.zoom_out_action.setStatusTip("Görünümü Uzaklaştır (Ctrl+-) ")
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.triggered.connect(self._handle_zoom_out_pdf_only)

        self.reset_zoom_action = QAction(qta.icon('fa5s.compress', color='blue'), "Görünümü Sıfırla", self)
        self.reset_zoom_action.setStatusTip("Yakınlaştırma ve Kaydırmayı Sıfırla (Ctrl+0)")
        self.reset_zoom_action.setShortcut(QKeySequence(Qt.KeyboardModifier.ControlModifier | Qt.Key.Key_0))
        self.reset_zoom_action.triggered.connect(self._handle_reset_zoom_pdf_only)
        # --- --- --- --- --- --- --- --- -- #

        # --- Düzenleme ---
        self.cut_action = QAction(self)
        self.cut_action.setIcon(qta.icon('fa5s.cut', color='orange'))
        self.cut_action.setText("Kes")
        self.cut_action.setToolTip("Seçili öğeleri kes (Ctrl+X)")
        self.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self.cut_action.triggered.connect(self._handle_cut_action)
        self.cut_action.setEnabled(True)

        self.copy_action = QAction(self)
        self.copy_action.setIcon(qta.icon('fa5s.copy', color='blue'))
        self.copy_action.setText("Kopyala")
        self.copy_action.setToolTip("Seçili öğeleri kopyala (Ctrl+C)")
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.triggered.connect(self._handle_copy_action)
        self.copy_action.setEnabled(True)

        self.paste_action = QAction(self)
        self.paste_action.setIcon(qta.icon('fa5s.paste', color='green'))
        self.paste_action.setText("Yapıştır")
        self.paste_action.setToolTip("Yapıştır (Ctrl+V)")
        self.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.paste_action.triggered.connect(self._handle_paste_action)
        self.paste_action.setEnabled(True)

        # --- Şekil Havuzu Actionları ---
        self.store_shape_action = QAction(qta.icon('fa5s.save', color='orange'), "Şekli Depola...", self)
        self.store_shape_action.setStatusTip("Seçili şekli havuza kaydet")
        self.store_shape_action.triggered.connect(lambda: shape_pool_handler.handle_store_shape(self.page_manager, self))

        self.add_shape_from_pool_action = QAction(qta.icon('fa5s.plus', color='purple'), "Depodan Şekil Ekle...", self)
        self.add_shape_from_pool_action.setStatusTip("Havuzdan seçilen şekli sayfaya ekle")
        self.add_shape_from_pool_action.triggered.connect(lambda: shape_pool_handler.handle_add_shape_from_pool(self.page_manager, self))

        self.delete_shape_from_pool_action = QAction(qta.icon('fa5s.trash', color='red'), "Depodan Şekil Sil...", self)
        self.delete_shape_from_pool_action.setStatusTip("Havuzdan şekil grubunu sil")
        self.delete_shape_from_pool_action.triggered.connect(lambda: shape_pool_handler.handle_delete_shape_from_pool(self.page_manager, self))

        # Düzenlenebilir Çizgi Kontrol Noktası Seçici aracı
        self.node_selector_tool_action = QAction(self)
        self.node_selector_tool_action.setIcon(qta.icon('fa5s.bezier-curve'))
        self.node_selector_tool_action.setText("Kontrol Noktası Seçici")
        self.node_selector_tool_action.setToolTip("Düzenlenebilir Çizgi Kontrol Noktası Seçici")
        self.node_selector_tool_action.setCheckable(True)
        self.node_selector_tool_action.triggered.connect(lambda: tool_handler.handle_set_active_tool(self.page_manager, ToolType.EDITABLE_LINE_NODE_SELECTOR))
        self.tool_actions.addAction(self.node_selector_tool_action)

    def _create_toolbar(self):
        """Toolbar'ı oluşturur ve actionları ekler."""
        toolbar = self.addToolBar("Ana Araçlar")
        toolbar.setObjectName("AnaAraçlar") # Nesne adı ekleyelim
        toolbar.setIconSize(QSize(24, 24))

        # Sayfa Yönetimi
        toolbar.addAction(self.new_page_action)
        toolbar.addAction(self.delete_page_action)
        toolbar.addAction(self.prev_page_action)
        toolbar.addAction(self.next_page_action)
        toolbar.addSeparator()

        # Araç Seçimi (Selector eklendi)
        toolbar.addAction(self.select_tool_action)  # Seçim aracını ekle
        toolbar.addAction(self.pen_tool_action)     # Kalem aracını ekle
        toolbar.addAction(self.line_tool_action)    # Çizgi aracını ekle
        toolbar.addAction(self.rect_tool_action)    # Dikdörtgen aracını ekle
        toolbar.addAction(self.circle_tool_action)  # Daire aracını ekle
        toolbar.addAction(self.eraser_tool_action)  # Silgi aracını ekle
        toolbar.addAction(self.laser_pointer_action)  # Lazer İşaretçi aracını ekle
        toolbar.addAction(self.temporary_pointer_action)  # Geçici İşaretçi aracını ekle
        toolbar.addAction(self.editable_line_tool_action)  # Düzenlenebilir Çizgi aracını ekle
        toolbar.addAction(self.node_selector_tool_action)  # Kontrol Noktası Seçici aracını ekle
        toolbar.addSeparator()

        # --- YENİ: Hızlı Renk Butonları ve Layout Widget --- #
        toolbar.addWidget(self.quick_color_widget) # Layout içeren widget'ı ekle
        self._update_quick_color_buttons() # Butonları layout'a ekleyecek yeni fonksiyon

        # Kalınlık Seçimi (Pen/Eraser için ortak)
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 100)
        self.width_spinbox.setSuffix(" px")
        self.width_spinbox.setValue(self.current_pen_width)
        self.width_spinbox.setToolTip("Kalem Kalınlığı")
        self.width_spinbox.valueChanged.connect(self._handle_width_change)
        toolbar.addWidget(self.width_spinbox)
        # --- --- --- --- --- --- --- --- --- ---

        # Düzenleme
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        toolbar.addAction(self.cut_action)
        toolbar.addAction(self.copy_action)
        toolbar.addAction(self.paste_action)
        toolbar.addAction(self.clear_action)
        toolbar.addSeparator()

        # --- YENİ: PDF İçe Aktarma Butonu ---
        toolbar.addAction(self.import_pdf_action)
        # --- --- --- --- --- --- --- --- --

        # --- YENİ: Resim Ekle Butonu --- #
        toolbar.addAction(self.add_image_action)
        # --- YENİ: Resmi Sil Butonu --- #
        toolbar.addAction(self.delete_image_action)
        toolbar.addSeparator()
        # --- YENİ: Resim Seçim Aracı Butonu --- #
        toolbar.addAction(self.image_select_action) # Action'ı toolbar'a ekle
        # --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Görünüm/Zoom Butonları --- #
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.reset_zoom_action)
        toolbar.addSeparator()
        # --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Çizgi Tipi Toggle Butonu --- #
        self.line_styles = ['solid', 'dashed', 'dotted', 'dashdot', 'double', 'zigzag']
        self.line_style_index = 0
        self.line_style_action = QAction(self)
        self.line_style_action.setCheckable(False)
        self.line_style_action.setChecked(False)
        self.line_style_action.setIcon(qta.icon('fa5s.minus'))
        self.line_style_action.setText("Çizgi Tipi: Düz/Kesikli")
        self.line_style_action.setToolTip("Çizgi Tipi: Düz (tıklayınca değişir)")
        self.line_style_action.triggered.connect(self._toggle_line_style)
        toolbar.addAction(self.line_style_action)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

        # Renk butonları eklenecek
        logging.debug("Toolbar oluşturuldu.")

        # --- Doldurma Rengi ve Şeffaflık --- #
        self.fill_color_button = QPushButton()
        self.fill_color_button.setFixedSize(QSize(24, 24))
        self.fill_color_button.setStyleSheet(f"background-color: {self.current_fill_color.name()}; border: 1px solid gray;")
        self.fill_color_button.setToolTip("Doldurma Rengi Seç")
        self.fill_color_button.clicked.connect(self._handle_fill_color_click)
        toolbar.addWidget(self.fill_color_button)

        self.fill_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.fill_alpha_slider.setRange(0, 255)
        self.fill_alpha_slider.setValue(self.current_fill_alpha)
        self.fill_alpha_slider.setFixedWidth(60)
        self.fill_alpha_slider.setToolTip("Doldurma Şeffaflığı (0: Şeffaf, 255: Opak)")
        self.fill_alpha_slider.valueChanged.connect(self._handle_fill_alpha_change)
        toolbar.addWidget(self.fill_alpha_slider)
        # --- --- --- --- --- --- --- --- --- ---

        # --- Doldurma Aktif/Pasif Checkbox ve Etiket --- #
        self.fill_enable_checkbox = QCheckBox()
        self.fill_enable_checkbox.setChecked(False)  # Varsayılan: işaretsiz (içi boş)
        self.fill_enable_checkbox.setToolTip("Doldurma Aktif/Pasif")
        self.fill_enable_checkbox.stateChanged.connect(self._handle_fill_enable_changed)
        toolbar.addWidget(self.fill_enable_checkbox)
        toolbar.addWidget(QLabel("Doldur"))
        toolbar.addSeparator()
        # --- --- --- --- --- --- --- --- --- ---

        # --- YENİ: Çizgiler grid'e uysun Checkbox --- #
        self.snap_line_to_grid_checkbox = QCheckBox()
        self.snap_line_to_grid_checkbox.setChecked(False)
        self.snap_line_to_grid_checkbox.setToolTip("Düz çizgiler grid'e yapışsın (snap)")
        self.snap_line_to_grid_checkbox.stateChanged.connect(self._handle_snap_line_to_grid_changed)
        toolbar.addWidget(self.snap_line_to_grid_checkbox)
        toolbar.addWidget(QLabel("Çizgiler grid'e uysun"))
        toolbar.addSeparator()
        # --- --- --- --- --- --- --- --- --- ---

    def _create_menus(self):
        """Menü çubuğunu oluşturur."""
        menu_bar = self.menuBar()

        # Dosya Menüsü
        file_menu = menu_bar.addMenu("&Dosya")
        file_menu.addAction(self.new_page_action)
        file_menu.addAction(self.delete_page_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addAction(self.load_action)
        file_menu.addAction(self.import_pdf_action) # PDF İçe Aktar Menü Öğesi
        file_menu.addAction(self.export_pdf_action)
        file_menu.addAction(self.exit_action)
        # PDF Export vs. buraya eklenecek
        file_menu.addSeparator() # Ayraç ekleyelim
        file_menu.addAction(self.add_image_action) # Buraya da ekleyelim
        file_menu.addAction(self.delete_image_action) # YENİ: Resmi Sil menüye ekle
        file_menu.addSeparator() # Ayraç ekleyelim
        self.recent_files_menu = file_menu.addMenu("Son Açılan")
        self.recent_files_actions: List[QAction] = [] # Actionları tutmak için liste
        # self._update_recent_files_menu() # Başlangıçta çağrılacak (init sonunda)
        # --- --- --- --- --- --- --- ---

        view_menu = menu_bar.addMenu("&Görünüm")
        template_menu = view_menu.addMenu("Sayfa Şablonu")
        template_menu.addAction(self.plain_template_action)
        template_menu.addAction(self.lined_template_action)
        template_menu.addAction(self.grid_template_action)
        
        view_menu.addSeparator()
        
        orientation_menu = view_menu.addMenu("Sayfa Yönü") # YENİ
        orientation_menu.addAction(self.portrait_action)
        orientation_menu.addAction(self.landscape_action)

        # Araçlar Menüsü (Selector eklendi)
        tool_menu = menu_bar.addMenu("A&raçlar")
        tool_menu.addAction(self.pen_tool_action)
        tool_menu.addAction(self.line_tool_action)
        tool_menu.addAction(self.editable_line_tool_action)  # Düzenlenebilir Çizgi aracını ekle
        tool_menu.addAction(self.rect_tool_action)
        tool_menu.addAction(self.circle_tool_action)
        tool_menu.addAction(self.select_tool_action)
        tool_menu.addAction(self.eraser_tool_action)
        tool_menu.addSeparator()
        tool_menu.addAction(self.laser_pointer_action)
        tool_menu.addAction(self.temporary_pointer_action)
        tool_menu.addAction(self.editable_line_tool_action)  # Düzenlenebilir Çizgi aracını ekle
        tool_menu.addAction(self.node_selector_tool_action)  # Kontrol Noktası Seçici aracını ekle
        # --- --- --- --- --- --- --- --- -- #

        # --- Ayarlar Menüsü --- # YENİ
        settings_menu = menu_bar.addMenu("&Ayarlar")
        settings_menu.addAction(self.settings_action)
        settings_menu.addAction(self.pointer_settings_action) # Buraya ekle
        # --- --- --- --- --- ---
        
        # --- YENİ: Grid Ayarları Action --- #
        self.grid_settings_action = QAction(qta.icon('fa5s.th', color='blue'), "Grid Ayarları...", self)
        self.grid_settings_action.setStatusTip("Grid çizgi aralığı, renk ve kalınlık ayarlarını düzenle")
        self.grid_settings_action.triggered.connect(self._handle_open_grid_settings)
        settings_menu.addAction(self.grid_settings_action)
        # --- --- --- --- --- ---
        
        # --- YENİ: Son Açılan Menüsü --- #
        file_menu.addSeparator() # Dosya menüsüne ayraç ekle
        self.recent_files_menu = file_menu.addMenu("Son Açılan")
        self.recent_files_actions: List[QAction] = [] # Actionları tutmak için liste
        # self._update_recent_files_menu() # Başlangıçta çağrılacak (init sonunda)
        # --- --- --- --- --- --- --- ---

        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.reset_zoom_action)
        view_menu.addSeparator()
        
        template_menu = view_menu.addMenu("Sayfa Şablonu")
        template_menu.addAction(self.plain_template_action)
        template_menu.addAction(self.lined_template_action)
        template_menu.addAction(self.grid_template_action)
        
        logging.debug("Menüler oluşturuldu.")

        # Düzenleme Menüsü
        edit_menu = self.menuBar().addMenu("&Düzenle")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.cut_action)
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addSeparator()
        # --- Şekil Havuzu Actionları ---
        edit_menu.addAction(self.store_shape_action)
        edit_menu.addAction(self.add_shape_from_pool_action)
        edit_menu.addAction(self.delete_shape_from_pool_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.clear_action)

    @pyqtSlot(Page)
    def _update_active_page_connections(self, current_page: Page | None):
        """Aktif sayfa değiştiğinde genel actionların bağlantılarını günceller (handler kullanarak)."""
        # --- DEĞİŞİKLİK: Log mesajını güncelle --- #
        logging.debug(f"Aktif sayfa bağlantıları güncelleniyor (PageManager içinden gelen): {current_page}")
        # --- --- --- --- --- --- --- --- --- --- #

        # Önceki bağlantıları temizle (özellikle başlık için)
        if hasattr(self, '_last_connected_page') and self._last_connected_page:
            try:
                self._last_connected_page.modified_status_changed.disconnect(self._update_window_title)
            except TypeError:
                 pass # Bağlantı yoksa hata vermez
        self._last_connected_page = None # Referansı temizle

        # Undo manager referansını temizle
        self.current_page_undo_manager = None

        # --- ESKİ UNDO/REDO SİNYAL BAĞLANTILARINI KOPAR --- #
        if hasattr(self, '_last_undo_manager') and self._last_undo_manager:
            try:
                self._last_undo_manager.can_undo_changed.disconnect(self._update_undo_action_enabled) # GÜNCELLENDİ
            except Exception:
                pass
            try:
                self._last_undo_manager.can_redo_changed.disconnect(self._update_redo_action_enabled) # GÜNCELLENDİ
            except Exception:
                pass
        self._last_undo_manager = None
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

        if current_page:
            canvas = current_page.get_canvas()
            manager = current_page.get_undo_manager()
            self.current_page_undo_manager = manager
            self._last_connected_page = current_page # Yeni bağlantı için referansı sakla
            self._last_undo_manager = manager # Undo/redo bağlantılarını takip et

            # --- YENİ: Başlık Güncelleme Bağlantısı --- #
            current_page.modified_status_changed.connect(self._update_window_title)
            # --- --- --- --- --- --- --- --- --- --- #

            # Handler'lara gerekli argümanları lambda ile geçerek bağlantıları yap
            # Önce mevcut bağlantıları kesmeyi dene (varsa)
            try:
                self.undo_action.triggered.disconnect()
            except TypeError: pass
            try:
                self.redo_action.triggered.disconnect()
            except TypeError: pass
            
            self.undo_action.triggered.connect(lambda checked=False, m=manager: self._log_and_call(m.undo, "Undo"))
            self.redo_action.triggered.connect(lambda checked=False, m=manager: self._log_and_call(m.redo, "Redo"))
            self.clear_action.triggered.connect(lambda: canvas_handler.handle_clear_canvas(self.page_manager))
            self.plain_template_action.triggered.connect(lambda: canvas_handler.handle_set_template(self.page_manager, TemplateType.PLAIN))
            self.lined_template_action.triggered.connect(lambda: canvas_handler.handle_set_template(self.page_manager, TemplateType.LINED))
            self.grid_template_action.triggered.connect(lambda: canvas_handler.handle_set_template(self.page_manager, TemplateType.GRID))
            self.portrait_action.triggered.connect(lambda: page_handler.handle_set_orientation(self.page_manager, Orientation.PORTRAIT))
            self.landscape_action.triggered.connect(lambda: page_handler.handle_set_orientation(self.page_manager, Orientation.LANDSCAPE))

            # Undo/Redo enable durumunu ve sinyallerini bağla
            self._update_undo_action_enabled(manager.can_undo()) # GÜNCELLENDİ
            self._update_redo_action_enabled(manager.can_redo()) # GÜNCELLENDİ
            # Önceki bağlantıları yukarıda kestik, şimdi sadece bir kez bağla
            manager.can_undo_changed.connect(self._update_undo_action_enabled) # GÜNCELLENDİ
            manager.can_redo_changed.connect(self._update_redo_action_enabled) # GÜNCELLENDİ

            # Şablon Check Durumu
            current_template = canvas.current_template
            self.plain_template_action.setChecked(current_template == TemplateType.PLAIN)
            self.lined_template_action.setChecked(current_template == TemplateType.LINED)
            self.grid_template_action.setChecked(current_template == TemplateType.GRID)

            # Sayfa Yönü Check Durumu # YENİ
            current_orientation = current_page.orientation # Page nesnesinden al
            self.portrait_action.setChecked(current_orientation == Orientation.PORTRAIT)
            self.landscape_action.setChecked(current_orientation == Orientation.LANDSCAPE)

            # Araç Check Durumu (Selector eklendi)
            current_tool = canvas.current_tool
            self.pen_tool_action.setChecked(current_tool == ToolType.PEN)
            self.line_tool_action.setChecked(current_tool == ToolType.LINE)
            self.rect_tool_action.setChecked(current_tool == ToolType.RECTANGLE)
            self.circle_tool_action.setChecked(current_tool == ToolType.CIRCLE)
            self.select_tool_action.setChecked(current_tool == ToolType.SELECTOR)
            self.eraser_tool_action.setChecked(current_tool == ToolType.ERASER)

            # YENİ: Başlangıçta spinbox'ı ayarla
            self._update_width_spinbox_for_tool(self.tool_actions.checkedAction()) # Seçili action'ı gönder

            # --- YENİ: Canvas'ın başlangıç kalınlıklarını ayarla --- #
            # MainWindow'dan yüklenen/tutulan değerleri canvas'a uygula
            logging.debug(f"  Setting initial canvas widths: Pen={self.current_pen_width}, Eraser={self.current_eraser_width}")
            canvas_handler.handle_set_pen_width(self.page_manager, self.current_pen_width)
            canvas_handler.handle_set_eraser_width(self.page_manager, self.current_eraser_width)
            # --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

            # --- YENİ: Aktif Canvas'a İşaretçi Ayarlarını Uygula --- #
            current_pointer_settings = {
                key: self.settings.get(key)
                for key in [
                    'laser_pointer_color', 'laser_pointer_size',
                    'temp_pointer_color', 'temp_pointer_width',
                    'temp_pointer_duration'
                ]
                if self.settings.get(key) is not None
            }
            if current_pointer_settings: # Sadece ayar varsa uygula
                self.apply_pointer_settings_to_canvas(current_pointer_settings)
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

            self.clear_action.setEnabled(True)
            # --- YENİ: Seçim değiştiğinde spinbox'ı güncelle --- #
            try:
                canvas.selection_changed.disconnect()
            except Exception:
                pass
            canvas.selection_changed.connect(lambda: self._update_width_spinbox_for_tool(self.select_tool_action))

            # --- Doldurma rengi ve alpha'yı da canvas'a uygula --- #
            if canvas:
                rgba = (
                    self.current_fill_color.redF(),
                    self.current_fill_color.greenF(),
                    self.current_fill_color.blueF(),
                    self.current_fill_alpha / 255.0
                )
                canvas.set_fill_rgba(rgba)
                # Doldurma checkbox'ı durumu da canvas'a aktar
                canvas.set_fill_enabled(self.fill_enable_checkbox.isChecked())
                # --- Toolbar'daki buton ve slider'ı güncelle --- #
                if hasattr(self, 'fill_color_button'):
                    self.fill_color_button.setStyleSheet(f"background-color: {self.current_fill_color.name()}; border: 1px solid gray;")
                if hasattr(self, 'fill_alpha_slider'):
                    self.fill_alpha_slider.setValue(self.current_fill_alpha)
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
        else:
            # Aktif sayfa yoksa her şeyi devre dışı bırak
            action_list = [
                self.undo_action, self.redo_action, self.clear_action,
                self.pen_tool_action, self.line_tool_action, self.rect_tool_action, self.circle_tool_action,
                self.select_tool_action, self.eraser_tool_action,
                self.new_page_action, self.delete_page_action, self.prev_page_action, self.next_page_action
            ]
            for action in action_list:
                action.setEnabled(False)
                if action.isCheckable(): action.setChecked(False)

            self.plain_template_action.setChecked(False)
            self.lined_template_action.setChecked(False)
            self.grid_template_action.setChecked(False)
            self.portrait_action.setChecked(False)
            self.landscape_action.setChecked(False)

            # Triggered sinyallerini de kesmek iyi olabilir
            try:
                self.undo_action.triggered.disconnect()
                self.redo_action.triggered.disconnect()
                self.clear_action.triggered.disconnect()
                self.plain_template_action.triggered.disconnect()
                self.lined_template_action.triggered.disconnect()
                self.grid_template_action.triggered.disconnect()
            except TypeError:
                pass

    @pyqtSlot(int, int)
    def _update_page_label(self, page_count: int, current_index: int):
        """Durum çubuğundaki sayfa etiketini günceller."""
        if page_count > 0:
            self.page_label.setText(f"Sayfa: {current_index + 1}/{page_count}")
        else:
            self.page_label.setText("Sayfa: Yok")
            
    def update_actions_state(self):
        """Sayfa sayısına göre eylemlerin etkin/pasif durumunu günceller."""
        page_count = self.page_manager.count()
        has_pages = page_count > 0
        can_navigate_or_delete = page_count > 1

        # Sayfa Yönetimi
        self.delete_page_action.setEnabled(can_navigate_or_delete)
        self.prev_page_action.setEnabled(can_navigate_or_delete)
        self.next_page_action.setEnabled(can_navigate_or_delete)
        # Yeni sayfa her zaman eklenebilir
        self.new_page_action.setEnabled(True) 
        
        # Dosya İşlemleri (Kaydet/PDF Aktar sadece sayfa varsa aktif)
        self.save_action.setEnabled(has_pages)
        self.export_pdf_action.setEnabled(has_pages)
        # Aç her zaman aktif olabilir
        self.load_action.setEnabled(True) 
        
        logging.debug(f"[update_actions_state] Çağrıldı. page_count={page_count}, has_pages={has_pages}, current_page_undo_manager={self.current_page_undo_manager}")

        # --- YENİ: Undo/Redo butonlarını her zaman yığın durumuna göre güncelle --- #
        if self.current_page_undo_manager:
            enabled_undo = self.current_page_undo_manager.can_undo()
            enabled_redo = self.current_page_undo_manager.can_redo()
            logging.debug(f"[update_actions_state] Undo butonu setEnabled({enabled_undo}), Redo butonu setEnabled({enabled_redo})")
            self._update_undo_action_enabled(enabled_undo) # GÜNCELLENDİ
            self._update_redo_action_enabled(enabled_redo) # GÜNCELLENDİ
        else:
            self._update_undo_action_enabled(False) # GÜNCELLENDİ
            self._update_redo_action_enabled(False) # GÜNCELLENDİ

    def _update_undo_action_enabled(self, can_undo: bool):
        blocked = self.undo_action.blockSignals(True)
        self.undo_action.setEnabled(can_undo)
        self.undo_action.blockSignals(blocked)
        logging.debug(f"Undo action enabled: {can_undo} (signals blocked/restored)")

    def _update_redo_action_enabled(self, can_redo: bool):
        blocked = self.redo_action.blockSignals(True)
        self.redo_action.setEnabled(can_redo)
        self.redo_action.blockSignals(blocked)
        logging.debug(f"Redo action enabled: {can_redo} (signals blocked/restored)")

    def _load_settings(self):
        """Uygulama ayarlarını (pencere boyutu, son dosyalar vb.) JSON'dan yükler."""
        try:
            with open(CONFIG_FILE, 'r') as f:
                loaded_settings = json.load(f)
                self.settings = loaded_settings
                fill_color = loaded_settings.get('fill_color', [1.0, 1.0, 1.0, 0.0])
                if isinstance(fill_color, list) and len(fill_color) == 4:
                    self.current_fill_color = QColor.fromRgbF(*fill_color)
                    self.current_fill_alpha = int(fill_color[3] * 255)
                else:
                    self.current_fill_color = QColor(255, 255, 255, 0)
                    self.current_fill_alpha = 0
                if hasattr(self, 'fill_color_button'):
                    self.fill_color_button.setStyleSheet(f"background-color: {self.current_fill_color.name()}; border: 1px solid gray;")
                if hasattr(self, 'fill_alpha_slider'):
                    self.fill_alpha_slider.setValue(self.current_fill_alpha)
                logging.info(f"Ayarlar yüklendi: {CONFIG_FILE}")
        except FileNotFoundError:
            self.settings = {
                "quick_access_colors": [
                    [0.6666666865348816, 0.0, 0.0, 1.0],
                    [0.0, 0.0, 0.49803921580314636, 1.0],
                    [0.0, 0.49803921580314636, 0.0, 1.0]
                ],
                "grid_snap_enabled": False,
                "grid_visible_on_snap": True,
                "grid_show_for_line_tool_only": False,
                "grid_apply_to_all_pages": True,
                "grid_thick_line_interval": 4,
                "grid_thin_color": [0.0, 0.0, 0.49803921580314636, 0.0784313725490196],
                "grid_thick_color": [0.6666666865348816, 0.0, 0.0, 0.1568627450980392],
                "grid_thin_width": 0.9999999999999992,
                "grid_thick_width": 1.0,
                "recent_files": [],
                "window_width": 1280,
                "window_height": 729,
                "pen_width": 2,
                "eraser_width": 10,
                "fill_color": [1.0, 1.0, 1.0, 0.0],
                "template_settings": DEFAULT_TEMPLATE_SETTINGS.copy()
            }
            self.current_fill_color = QColor.fromRgbF(1.0, 1.0, 1.0, 0.0)
            self.current_fill_alpha = 0
        except json.JSONDecodeError:
            self.settings = {
                "quick_access_colors": [
                    [0.6666666865348816, 0.0, 0.0, 1.0],
                    [0.0, 0.0, 0.49803921580314636, 1.0],
                    [0.0, 0.49803921580314636, 0.0, 1.0]
                ],
                "grid_snap_enabled": False,
                "grid_visible_on_snap": True,
                "grid_show_for_line_tool_only": False,
                "grid_apply_to_all_pages": True,
                "grid_thick_line_interval": 4,
                "grid_thin_color": [0.0, 0.0, 0.49803921580314636, 0.0784313725490196],
                "grid_thick_color": [0.6666666865348816, 0.0, 0.0, 0.1568627450980392],
                "grid_thin_width": 0.9999999999999992,
                "grid_thick_width": 1.0,
                "recent_files": [],
                "window_width": 1280,
                "window_height": 729,
                "pen_width": 2,
                "eraser_width": 10,
                "fill_color": [1.0, 1.0, 1.0, 0.0],
                "template_settings": DEFAULT_TEMPLATE_SETTINGS.copy()
            }
            self.current_fill_color = QColor.fromRgbF(1.0, 1.0, 1.0, 0.0)
            self.current_fill_alpha = 0
        # Hızlı renkleri yüklerken doğrula
        max_quick_colors = self.settings.get('max_quick_access_colors', 5)
        quick_colors_raw = self.settings.get('quick_access_colors', [])
        validated_quick_colors = []
        for color_list in quick_colors_raw:
            if isinstance(color_list, list) and len(color_list) == 4:
                if all(isinstance(c, (int, float)) for c in color_list):
                    validated_quick_colors.append(color_list)
                else:
                    logging.warning(f"quick_access_colors içinde geçersiz renk formatı (sayı değil): {color_list}")
            else:
                logging.warning(f"quick_access_colors içinde geçersiz renk formatı (liste değil veya uzunluk 4 değil): {color_list}")
        self.settings['quick_access_colors'] = validated_quick_colors[:max_quick_colors]
        self.current_pen_width = self.settings.get('pen_width', 2)
        self.current_eraser_width = self.settings.get('eraser_width', 10)
        logging.debug(f"Kalınlıklar yüklendi: Pen={self.current_pen_width}, Eraser={self.current_eraser_width}")
        for key, default_value in DEFAULT_GRID_SETTINGS.items():
            self.settings[key] = self.settings.get(key, default_value)
        loaded_grid_settings = {k: self.settings.get(k) for k in DEFAULT_GRID_SETTINGS if k in self.settings}
        logging.debug(f"Grid ayarları yüklendi/varsayılanlar atandı: {loaded_grid_settings}")

    def _save_settings(self, settings: dict):
        """Mevcut uygulama ayarlarını (pencere boyutu, son dosyalar vb.) JSON'a kaydeder."""
        # --- YENİ: Kaydetmeden hemen önce ayarları logla --- 
        # logging.debug(f"_save_settings başlangıcı. Kaydedilecek ayarlar: {settings}")
        # --- --- --- --- --- --- --- --- --- --- --- --- ---
        try:
            # --- YENİ: Yüklenen recent_files'ı doğrula --- #
            recent_files = settings.get('recent_files', [])
            max_files = settings.get('max_recent_files', 5)
            
            # Tekrar doğrulama ve limit uygulama (ekstra güvenlik)
            validated_files = [
                path for path in recent_files 
                if isinstance(path, str) # Kaydederken varlık kontrolü yapmayalım, liste bozulabilir
            ]
            settings['recent_files'] = validated_files[:max_files]
            # --- --- --- --- --- --- --- --- --- --- --- --- ---
            
            # --- YENİ: Hızlı renkleri kaydetmeden önce doğrula/limitle --- #
            quick_colors_raw = settings.get('quick_access_colors', [])
            max_quick_colors = settings.get('max_quick_access_colors', 5)
            validated_quick_colors = []
            for color_list in quick_colors_raw:
                 if isinstance(color_list, list) and len(color_list) == 4 and all(isinstance(c, (int, float)) for c in color_list):
                      validated_quick_colors.append(color_list)
            settings['quick_access_colors'] = validated_quick_colors[:max_quick_colors]
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

            # --- YENİ LOGLAMA --- #
            pen_w = settings.get("pen_width", "YOK")
            eraser_w = settings.get("eraser_width", "YOK")
            # logging.debug(f"_save_settings: JSON'a yazılacak kalınlıklar: Pen={pen_w}, Eraser={eraser_w}")
            # --- --- --- --- --- #

            # Pencere boyutunu ayarlara ekle
            settings['window_width'] = self.width()
            settings['window_height'] = self.height()
            # Kalem/Silgi kalınlığını ekle (closeEvent'te de yapılıyor ama burada da olması iyi olabilir)
            settings['pen_width'] = self.current_pen_width
            settings['eraser_width'] = self.current_eraser_width

            # --- YENİ: Kayıt öncesi son kontrol logu ---
            # logging.debug(f"_save_settings: JSON'a yazılacak son ayarlar: {settings}")
            # --- --- --- --- --- --- --- --- --- --- ---

            # --- Doldurma rengi ve alpha'yı kaydet (float 0-1) --- #
            settings['fill_color'] = [
                self.current_fill_color.redF(),
                self.current_fill_color.greenF(),
                self.current_fill_color.blueF(),
                self.current_fill_alpha / 255.0
            ]

            with open(CONFIG_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            logging.info(f"Ayarlar kaydedildi: {CONFIG_FILE}")
        except Exception as e:
            logging.error(f"Ayarlar kaydedilirken hata oluştu: {e}")

    def _update_window_title(self):
        """Pencere başlığını geçerli dosya yoluna ve değişiklik durumuna göre günceller."""
        base_title = "Dijital Mürekkep"
        prefix = ""
        suffix = ""
        
        if self.current_notebook_path:
            prefix = f"{os.path.basename(self.current_notebook_path)} "
        else:
            prefix = "[Başlıksız] "
            
        if self.page_manager.has_unsaved_changes():
            suffix = "*"
            
        self.setWindowTitle(f"{prefix}{suffix}- {base_title}")

    def set_current_notebook_path(self, path: str | None):
        """Geçerli dosya yolunu ayarlar ve pencere başlığını günceller."""
        self.current_notebook_path = path
        self._update_window_title()

    # --- Diğer Metotlar --- #
    def _prompt_save_before_action(self, action_to_continue) -> bool:
        """Kaydedilmemiş değişiklikler varsa kullanıcıya sorar ve seçime göre işlem yapar.

        Args:
            action_to_continue: Kullanıcı 'Kaydetme' veya başarılı 'Kaydet' sonrası çalıştırılacak fonksiyon.

        Returns:
            bool: Eyleme devam edilip edilmeyeceği (True) veya iptal edildiği (False).
        """
        if not self.page_manager.has_unsaved_changes():
            return True # Değişiklik yoksa devam et

        file_name = os.path.basename(self.current_notebook_path) if self.current_notebook_path else "Başlıksız"
        reply = QMessageBox.question(
            self,
            "Kaydedilmemiş Değişiklikler",
            f"'{file_name}' dosyasında kaydedilmemiş değişiklikler var. Kaydetmek istiyor musunuz?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel # Varsayılan İptal
        )

        if reply == QMessageBox.StandardButton.Save:
            # Kaydetmeyi dene
            # Not: handle_save_notebook kendi içinde hata mesajı gösteriyor
            # ve başarılı olursa mark_all_pages_as_saved çağırıyor.
            # TODO: handle_save_notebook'un başarı durumunu döndürmesi ve ona göre action_to_continue çağırması daha iyi olabilir.
            # Şimdilik, kaydetme işlemini çağırıp action'a devam ediyoruz.
            # Kullanıcı kaydı iptal ederse (dosya seçmezse) handle_save_notebook zaten return edecek.
            # Eğer kaydetme başarılı olursa orijinal eyleme devam etmeli.
            
            # Önce save_as=False ile deneyelim (mevcut dosya varsa)
            success = file_handler.handle_save_notebook(self, self.page_manager, save_as=False)
            if success:
                 # Başarılı kayıttan sonra devam et
                 return True 
            else:
                 # Kaydetme başarısız oldu veya kullanıcı iptal etti, orijinal eyleme devam etme
                 return False
                 
        elif reply == QMessageBox.StandardButton.Discard:
            return True # Kaydetme, devam et
        else: # Cancel
            return False # İptal et, devam etme

    def closeEvent(self, event: QCloseEvent):
        """Uygulama kapatılırken kaydedilmemiş değişiklikleri kontrol eder ve ayarları kaydeder."""
        # --- YENİ: Ayarları kaydetmeden önce güncel değerleri ekle --- #
        # Pencere boyutunu kaydet
        self.settings['window_width'] = self.width()
        self.settings['window_height'] = self.height()
        # Kalem ve silgi kalınlığını kaydet
        self.settings['pen_width'] = self.current_pen_width
        self.settings['eraser_width'] = self.current_eraser_width
        # --- YENİ LOGLAMA --- #
        # logging.debug(f"closeEvent: Kaydedilecek kalınlıklar: Pen={self.settings.get('pen_width')}, Eraser={self.settings.get('eraser_width')}")
        # --- --- --- --- --- #

        if self._prompt_save_before_action(self.close): # Devam edilecek eylem yok, sadece kontrol
            # --- YENİ: Kullanılmayan resim dosyalarını sil --- #
            self._delete_unused_images_on_exit()
            # --- YENİ: Kapatmadan önce ayarları kaydet --- #
            self._save_settings(self.settings)
            # --- --- --- --- --- --- --- --- --- --- --- #
            event.accept() # Kapat
        else:
            event.ignore() # Kapatma

    # --- YENİ: İşaretçi Ayarlarını Canvas'a Uygula --- #
    def apply_pointer_settings_to_canvas(self, settings: dict):
        """Verilen işaretçi ayarlarını mevcut aktif canvas'a uygular."""
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            canvas = current_page.drawing_canvas
            # Canvas'a ayarları uygulayacak yeni bir metod ekleyeceğiz
            canvas.apply_pointer_settings(settings)
            logging.debug(f"İşaretçi ayarları aktif canvas'a uygulandı: {settings}")
        else:
            logging.warning("İşaretçi ayarları uygulanacak aktif canvas bulunamadı.")
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    # --- YENİ: Son Açılan Menüsü --- #
    def _update_recent_files_menu(self):
        """Ayarlardaki son dosyalar listesine göre 'Son Açılan' menüsünü günceller."""
        self.recent_files_menu.clear()
        self.recent_files_actions.clear()
        
        recent_files = self.settings.get('recent_files', []) # Ayarlardan oku
        max_files = self.settings.get('max_recent_files', 5) # Ayarlardan oku

        if not recent_files:
            action = QAction("Liste Boş", self)
            action.setEnabled(False)
            self.recent_files_menu.addAction(action)
            self.recent_files_actions.append(action)
            return

        # Son dosyaları menüye ekle
        for i, filepath in enumerate(recent_files[:max_files]): # Limiti burada da uygula
            # Dosya adını ve yolunu gösterelim (kısa yol olabilir)
            filename = os.path.basename(filepath)
            action_text = f"&{i+1} {filename}"
            action = QAction(action_text, self)
            action.setData(filepath) # Dosya yolunu action'a bağla
            action.setStatusTip(filepath) # Tam yolu tooltip olarak göster
            action.triggered.connect(partial(self._handle_recent_file_triggered, filepath))
            self.recent_files_menu.addAction(action)
            self.recent_files_actions.append(action)
            
        # Ayırıcı ve Temizle seçeneği (isteğe bağlı)
        self.recent_files_menu.addSeparator()
        clear_action = QAction("Listeyi Temizle", self)
        clear_action.triggered.connect(self._clear_recent_files)
        self.recent_files_menu.addAction(clear_action)
        self.recent_files_actions.append(clear_action)

    @pyqtSlot(str)
    def _handle_recent_file_triggered(self, filepath: str):
        """Son açılan dosyalar menüsünden bir eylem tetiklendiğinde çağrılır."""
        if filepath:
            file_handler.handle_open_recent_file(self, self.page_manager, filepath)
            
    def _clear_recent_files(self):
        """Son açılan dosyalar listesini temizler."""
        reply = QMessageBox.question(self, "Listeyi Temizle", 
                                   "Son açılan dosyalar listesini temizlemek istediğinizden emin misiniz?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.settings['recent_files'] = []
            self._save_settings(self.settings)
            self._update_recent_files_menu()
            logging.info("Son açılan dosyalar listesi temizlendi.")

    # --- YENİ: Renk/Kalınlık Handler Bağlantıları ve Yardımcılar --- #
    def _update_quick_color_buttons(self):
        """Ayarlardaki hızlı renkler için butonları ve '+' butonunu layout'a ekler."""
        # Önce mevcutları temizle (layout'tan ve listeden)
        for i in range(self.quick_color_layout.count()): 
            widget = self.quick_color_layout.takeAt(0).widget()
            if widget: 
                widget.deleteLater()
        self.quick_color_buttons.clear()
        # Eskiden kalan add_color_button referansını da temizleyelim (varsa)
        if hasattr(self, 'add_color_button'):
            try: # Widget zaten silinmiş olabilir
                 self.add_color_button.deleteLater()
            except RuntimeError: pass # Already deleted
            del self.add_color_button # Referansı sil

        quick_colors = self.settings.get('quick_access_colors', [])
        max_colors = self.settings.get('max_quick_access_colors', 5)
        button_size = QSize(24, 24) # Daha küçük boyut

        for index, color_list in enumerate(quick_colors):
            if len(self.quick_color_buttons) >= max_colors:
                break # Limite ulaşıldı
                
            qcolor = QColor.fromRgbF(*color_list)
            if qcolor.isValid():
                button = QPushButton()
                button.setFixedSize(button_size)
                button.setStyleSheet(NORMAL_BUTTON_STYLE % qcolor.name())
                button.setToolTip(f"Renk: {qcolor.name()}\nBasılı tut: Düzenle/Sil")
                button.setProperty("color_index", index) # Index'i sakla
                button.setProperty("qcolor", qcolor) # QColor'ı da sakla
                button.pressed.connect(partial(self._handle_quick_color_pressed, button))
                button.released.connect(self._handle_quick_color_released)
                self.quick_color_layout.addWidget(button)
                self.quick_color_buttons.append(button)

        # Ekle (+) butonunu ekle (eğer limite ulaşılmadıysa)
        if len(self.quick_color_buttons) < max_colors:
            self.add_color_button = QPushButton("+")
            self.add_color_button.setFixedSize(button_size)
            self.add_color_button.setToolTip("Hızlı Erişim Rengi Ekle")
            self.add_color_button.clicked.connect(self._handle_add_color_click)
            self.quick_color_layout.addWidget(self.add_color_button)
        # else:
             # Limite ulaşıldıysa add_color_button referansı zaten yukarıda temizlenmişti
             # if hasattr(self, 'add_color_button'):
             #      del self.add_color_button

    def _handle_quick_color_pressed(self, button: QPushButton):
        """Hızlı renk butonu basıldığında zamanlayıcıyı başlatır."""
        self.pressed_color_button = button
        self.was_long_press = False # Her basışta sıfırla
        self.long_press_timer.start()
        logging.debug(f"Quick color button pressed, timer started for index: {button.property('color_index')}")

    def _handle_quick_color_released(self):
        """Hızlı renk butonu bırakıldığında işlemleri yapar."""
        logging.debug("Quick color button released.")
        if self.pressed_color_button:
            if self.long_press_timer.isActive():
                # Zamanlayıcı hala aktifse, kısa basmaydı
                self.long_press_timer.stop()
                logging.debug("Timer stopped, was a short press.")
                if not self.was_long_press: # Zaman aşımı tetiklenmediyse rengi seç
                     color = self.pressed_color_button.property("qcolor")
                     if color and isinstance(color, QColor):
                         logging.debug(f"Short press detected, selecting color: {color.name()}")
                         self._set_drawing_color(color)
            # else: # Zamanlayıcı aktif değilse, zaten zaman aşımı olmuştur (long press)
                 # logging.debug("Timer was not active, long press already handled.")
                 # Ek bir işlem yapmaya gerek yok, _handle_long_press_timeout halletti
                 
        self.pressed_color_button = None # Durumu temizle

    def _handle_long_press_timeout(self):
        """Zamanlayıcı süresi dolduğunda renk düzenleyiciyi açar."""
        logging.debug("Long press timer timeout!")
        if self.pressed_color_button:
            index = self.pressed_color_button.property("color_index")
            if index is not None:
                logging.info(f"Long press detected on index {index}, opening color editor.")
                self.was_long_press = True # Düzenleyici açıldı, kısa basma işlemini engelle
                self._handle_edit_quick_color(index)
            # Zaman aşımından sonra butonu temizlemek doğru mu? Belki release'de temizlemek daha iyi.
            # self.pressed_color_button = None # Belki burada temizlememeliyiz?
        else:
            logging.warning("Long press timeout but no button was stored.")
    # --- --- --- --- --- --- --- --- --- ---

    def _handle_add_color_click(self):
        """Yeni hızlı erişim rengi ekleme butonuna tıklandığında çağrılır."""
        new_color = QColorDialog.getColor(self.current_pen_color, self, "Hızlı Erişim Rengi Seç")
        if new_color.isValid():
            quick_colors = self.settings.get('quick_access_colors', [])
            max_colors = self.settings.get('max_quick_access_colors', 5)
            
            # Rengi RGBA float listesine çevir (0-1 aralığı)
            new_color_list = [new_color.redF(), new_color.greenF(), new_color.blueF(), new_color.alphaF()]
            
            # Zaten var mı kontrolü (yaklaşık kontrol gerekebilir?)
            # Toleranslı float karşılaştırması yapalım
            color_exists = False
            for existing_color in quick_colors:
                if all(abs(a - b) < 1e-6 for a, b in zip(new_color_list, existing_color)):
                    color_exists = True
                    break
                    
            # if new_color_list not in quick_colors and len(quick_colors) < max_colors:
            if not color_exists and len(quick_colors) < max_colors:
                logging.debug(f"Yeni renk listeye ekleniyor: {new_color_list}")
                quick_colors.append(new_color_list)
                self.settings['quick_access_colors'] = quick_colors
                self._save_settings(self.settings)
                # Araç çubuğunu güncelle
                # toolbar = self.findChild(QToolBar, "AnaAraçlar") # Artık toolbar'a doğrudan eklemiyoruz
                # if toolbar:
                #      logging.debug("Toolbar bulundu, hızlı renk butonları güncelleniyor.")
                #      self._add_quick_color_buttons_to_toolbar(toolbar)
                # else:
                #      logging.error("'AnaAraçlar' isimli toolbar bulunamadı!")
                self._update_quick_color_buttons() # Sadece layout'u güncellemek yeterli
                logging.info(f"Yeni hızlı erişim rengi eklendi: {new_color.name()}")
            elif color_exists:
                 logging.debug("Seçilen renk zaten listede var.")
                 QMessageBox.information(self, "Renk Zaten Var", "Seçtiğiniz renk zaten hızlı erişim listesinde.")
            elif len(quick_colors) >= max_colors:
                 logging.debug("Hızlı renk limiti dolu.")
                 QMessageBox.information(self, "Limit Dolu", f"Maksimum hızlı erişim rengi sayısına ({max_colors}) ulaşıldı.")
            else:
                 logging.warning("Renk eklenemedi, bilinmeyen durum.")

    def _handle_edit_quick_color(self, index: int):
        """Belirli bir index'teki hızlı erişim rengini düzenler."""
        quick_colors = self.settings.get('quick_access_colors', [])
        if 0 <= index < len(quick_colors):
            current_color_list = quick_colors[index]
            current_qcolor = QColor.fromRgbF(*current_color_list)
            
            new_color = QColorDialog.getColor(current_qcolor, self, "Rengi Düzenle")
            if new_color.isValid() and new_color != current_qcolor:
                new_color_list = [new_color.redF(), new_color.greenF(), new_color.blueF(), new_color.alphaF()]
                quick_colors[index] = new_color_list
                self.settings['quick_access_colors'] = quick_colors
                self._save_settings(self.settings)
                self._update_quick_color_buttons() # Butonları güncelle
                logging.info(f"Hızlı erişim rengi {index} düzenlendi: {new_color.name()}")
                # --- YENİ: Düzenlenen rengi aktif renk yap --- #
                self.current_pen_color = new_color
                canvas_handler.handle_set_pen_color(self.page_manager, new_color)
                logging.debug(f"Düzenlenen renk ({new_color.name()}) aktif kalem rengi olarak ayarlandı.")
                # --- --- --- --- --- --- --- --- --- --- ---
        else:
             logging.error(f"Düzenlenecek renk index'i geçersiz: {index}")

    def _handle_quick_color_click(self, color: QColor):
        """Hızlı erişim renk butonlarından birine tıklandığında çağrılır."""
        if color.isValid():
            self.current_pen_color = color
            # Aktif canvas'a rengi uygula
            canvas_handler.handle_set_pen_color(self.page_manager, color)
            # İsteğe bağlı: Tıklanan butonu görsel olarak işaretle (örn. kenarlık rengi)
            # Şimdilik gerek yok, ana renk seçici yok

    def _handle_width_change(self, value: int):
        active_tool_action = self.tool_actions.checkedAction()
        if not active_tool_action:
            logging.warning("_handle_width_change: Aktif araç bulunamadı.")
            return
        tool_name = active_tool_action.text()
        logging.debug(f"_handle_width_change: Değer={value}, Aktif Araç='{tool_name}'")
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            canvas = current_page.drawing_canvas
            # --- SEÇİM ARACI AKTİF VE BİR ÖĞE SEÇİLİYSE, SEÇİLİ ÖĞENİN KALINLIĞINI GÜNCELLE --- #
            if canvas.current_tool.name == 'SELECTOR' and len(canvas.selected_item_indices) == 1:
                item_type, index = canvas.selected_item_indices[0]
                if item_type == 'lines' and 0 <= index < len(canvas.lines):
                    canvas.lines[index][1] = float(value)
                    canvas.update()
                    return
                elif item_type == 'shapes' and 0 <= index < len(canvas.shapes):
                    canvas.shapes[index][2] = float(value)
                    canvas.update()
                    return
        # --- KLASİK DAVRANIŞ --- #
        if active_tool_action in [self.pen_tool_action, self.line_tool_action, self.rect_tool_action, self.circle_tool_action]:
            self.current_pen_width = value
            logging.debug(f"  >>> self.current_pen_width güncellendi: {self.current_pen_width}")
            canvas_handler.handle_set_pen_width(self.page_manager, value)
        elif active_tool_action == self.eraser_tool_action:
            self.current_eraser_width = value
            logging.debug(f"  >>> self.current_eraser_width güncellendi: {self.current_eraser_width}")
            canvas_handler.handle_set_eraser_width(self.page_manager, value)
        else:
            logging.debug(f"  >>> Kalınlık değişikliği '{tool_name}' aracı için geçerli değil.")

    @pyqtSlot(QAction)
    def _update_width_spinbox_for_tool(self, action: QAction):
        """Seçilen araca göre kalınlık spinbox'ının değerini ve tooltip'ini günceller."""
        current_page = self.page_manager.get_current_page()
        canvas = current_page.drawing_canvas if current_page and hasattr(current_page, 'drawing_canvas') else None
        # --- SEÇİM ARACI AKTİF VE TEK ÖĞE SEÇİLİYSE --- #
        if action == self.select_tool_action and canvas and len(canvas.selected_item_indices) == 1:
            item_type, index = canvas.selected_item_indices[0]
            if item_type == 'lines' and 0 <= index < len(canvas.lines):
                self.width_spinbox.setToolTip("Çizgi Kalınlığı (Seçili)")
                self.width_spinbox.setValue(int(canvas.lines[index][1]))
                self.width_spinbox.setEnabled(True)
                return
            elif item_type == 'shapes' and 0 <= index < len(canvas.shapes):
                self.width_spinbox.setToolTip("Şekil Kalınlığı (Seçili)")
                self.width_spinbox.setValue(int(canvas.shapes[index][2]))
                self.width_spinbox.setEnabled(True)
                return
        # --- KLASİK DAVRANIŞ --- #
        if action == self.pen_tool_action:
            self.width_spinbox.setToolTip("Kalem Kalınlığı")
            self.width_spinbox.setValue(self.current_pen_width)
            self.width_spinbox.setEnabled(True)
        elif action == self.line_tool_action:
            self.width_spinbox.setToolTip("Çizgi Kalınlığı")
            self.width_spinbox.setValue(self.current_pen_width)
            self.width_spinbox.setEnabled(True)
        elif action == self.rect_tool_action:
            self.width_spinbox.setToolTip("Dikdörtgen Çizgi Kalınlığı")
            self.width_spinbox.setValue(self.current_pen_width)
            self.width_spinbox.setEnabled(True)
        elif action == self.circle_tool_action:
            self.width_spinbox.setToolTip("Daire Çizgi Kalınlığı")
            self.width_spinbox.setValue(self.current_pen_width)
            self.width_spinbox.setEnabled(True)
        elif action == self.eraser_tool_action:
            self.width_spinbox.setToolTip("Silgi Kalınlığı")
            self.width_spinbox.setValue(self.current_eraser_width)
            self.width_spinbox.setEnabled(True)
        else:
            self.width_spinbox.setToolTip("")
            self.width_spinbox.setEnabled(False)
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

    def _log_and_call(self, func, description: str):
        """Bir fonksiyonu loglayarak çağırır (özellikle Undo/Redo için)."""
        # YENİ LOG BAŞLANGIÇ
        manager_info = 'N/A'
        if hasattr(func, '__self__') and isinstance(func.__self__, UndoRedoManager):
            manager_info = f"Manager ID: {id(func.__self__)}, Undo Yığını: {len(func.__self__.undo_stack) if func.__self__.undo_stack else 0}, Redo Yığını: {len(func.__self__.redo_stack) if func.__self__.redo_stack else 0}"
        logging.debug(f"MainWindow._log_and_call: ÇAĞRILDI. İşlem: {description}, {manager_info}")
        # YENİ LOG BİTİŞ
        try:
            func() # Asıl fonksiyonu çağır (örn: manager.undo())
            # logging.debug(f"{description} işlemi tamamlandı.") # Bu log çok sık olabilir
        except Exception as e:
            logging.error(f"{description} işlemi sırasında hata: {e}", exc_info=True)

    def _set_drawing_color(self, color: QColor):
        if not color.isValid():
            logging.warning(f"_set_drawing_color: Geçersiz renk {color}")
            return
        logging.debug(f"_set_drawing_color çağrıldı: {color.name()}")
        self.current_pen_color = color
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            canvas = current_page.drawing_canvas
            # --- SEÇİM ARACI AKTİF VE BİR ÖĞE SEÇİLİYSE, SEÇİLİ ÖĞENİN RENGİNİ GÜNCELLE --- #
            if canvas.current_tool.name == 'SELECTOR' and len(canvas.selected_item_indices) == 1:
                item_type, index = canvas.selected_item_indices[0]
                if item_type == 'lines' and 0 <= index < len(canvas.lines):
                    canvas.lines[index][0] = [color.redF(), color.greenF(), color.blueF(), color.alphaF()]
                    canvas.update()
                    return
                elif item_type == 'shapes' and 0 <= index < len(canvas.shapes):
                    canvas.shapes[index][1] = [color.redF(), color.greenF(), color.blueF(), color.alphaF()]
                    canvas.update()
                    return
            # --- KLASİK DAVRANIŞ --- #
            logging.debug(f"  Canvas rengi ayarlanıyor: {color.name()}")
            canvas.set_color(color)
        # ... (buton stilleri güncellemesi ve diğer kodlar aynı kalacak) ...

    def load_settings(self) -> dict:
        """Uygulama ayarlarını JSON'dan yükler ve döndürür."""
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Ayarlar yüklenirken hata oluştu: {e}")
            return {}

    # --- YENİ: Sinyal bağlantısı için yardımcı metod --- #
    def _trigger_export_pdf(self):
        """PDF dışa aktarma handler'ını çağıran slot."""
        file_handler.handle_export_pdf(self)
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    # --- YENİ: Şablonlar oluşturulduktan sonra canvas'ı güncelleyen metod --- #
    @pyqtSlot(dict) # generate_templates_requested sinyalinden gelen dict'i alır (kullanmasak da)
    def _handle_templates_generated(self, settings_dict: dict):
        """Şablon oluşturma işlemi bittikten sonra aktif canvas'ı günceller."""
        logging.info("Template generation finished signal received, updating active canvas background...")
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            try:
                current_page.drawing_canvas.load_background_template_image()
                logging.debug("Active canvas background reloaded after template generation.")
            except Exception as e:
                logging.error(f"Error reloading canvas background after template generation: {e}")
        else:
            logging.warning("Cannot reload background, no active canvas found after template generation.")
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def _toggle_line_style(self):
        self.line_style_index = (self.line_style_index + 1) % len(self.line_styles)
        new_style = self.line_styles[self.line_style_index]
        current_page = self.page_manager.get_current_page()
        canvas = current_page.drawing_canvas if current_page and hasattr(current_page, 'drawing_canvas') else None
        if canvas:
            canvas.line_style = new_style
            canvas.update()
        # İkon ve tooltip güncelle
        icon_map = {
            'solid': qta.icon('fa5s.minus'),
            'dashed': qta.icon('fa5s.ellipsis-h'),
            'dotted': qta.icon('fa5s.ellipsis-h'),
            'dashdot': qta.icon('fa5s.grip-lines'),  # DÜZELTİLDİ
            'double': qta.icon('fa5s.equals'),
            'zigzag': qta.icon('fa5s.wave-square'),
        }
        self.line_style_action.setIcon(icon_map.get(new_style, qta.icon('fa5s.minus')))
        self.line_style_action.setToolTip(f"Çizgi Tipi: {new_style}")

    def _handle_fill_color_click(self):
        color = QColorDialog.getColor(self.current_fill_color, self, "Doldurma Rengi Seç")
        if color.isValid():
            self.current_fill_color = color
            self.fill_color_button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid gray;")
            # RGBA güncelle
            rgba = (
                color.redF(), color.greenF(), color.blueF(),
                self.current_fill_alpha / 255.0
            )
            current_page = self.page_manager.get_current_page()
            if current_page and current_page.drawing_canvas:
                current_page.drawing_canvas.set_fill_rgba(rgba)

    def _handle_fill_alpha_change(self, value):
        self.current_fill_alpha = value
        # RGBA güncelle
        rgba = (
            self.current_fill_color.redF(), self.current_fill_color.greenF(), self.current_fill_color.blueF(),
            value / 255.0
        )
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            current_page.drawing_canvas.set_fill_rgba(rgba)

    @pyqtSlot(QAction)
    def _update_width_spinbox_for_tool(self, action: QAction):
        # ... mevcut kod ...
        # --- Doldurma rengi ve şeffaflık kontrollerinin aktifliği --- #
        if action in [self.rect_tool_action, self.circle_tool_action]:
            self.fill_color_button.setEnabled(True)
            self.fill_alpha_slider.setEnabled(True)
        else:
            self.fill_color_button.setEnabled(False)
            self.fill_alpha_slider.setEnabled(False)
        # ... mevcut kod ...

    def _handle_fill_enable_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.fill_color_button.setEnabled(enabled)
        self.fill_alpha_slider.setEnabled(enabled)
        # Doldurma pasifse, RGBA'nın alpha'sını 0 yaparak canvas'a aktar
        current_page = self.page_manager.get_current_page()
        if current_page and current_page.drawing_canvas:
            rgba = (
                self.current_fill_color.redF(),
                self.current_fill_color.greenF(),
                self.current_fill_color.blueF(),
                (self.current_fill_alpha / 255.0) if enabled else 0.0
            )
            current_page.drawing_canvas.set_fill_rgba(rgba)
            current_page.drawing_canvas.set_fill_enabled(enabled)

    def _handle_select_image_action(self):
        """Resim seçme iletişim kutusu aç ve seçimi işle."""
        try:
            secilen_yol, _ = QFileDialog.getOpenFileName(
                self,
                "Resim Seç",
                os.path.expanduser("~"),
                "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.gif)"
            )
            if secilen_yol:
                logging.info(f"Seçilen resim yolu: {secilen_yol}")
                canvas = self.page_manager.get_current_page().get_canvas()
                if canvas is None:
                    logging.error("Canvas bulunamadı!")
                    return
                
                # Canvas için add_image_from_path metodu yoksa ekle
                import types
                
                # --- Dosyanın MD5 özetini hesaplayan fonksiyon --- #
                def get_file_md5(file_path):
                    """Dosyanın MD5 özetini hesaplar"""
                    hash_md5 = hashlib.md5()
                    try:
                        with open(file_path, 'rb') as f:
                            for chunk in iter(lambda: f.read(4096), b""):
                                hash_md5.update(chunk)
                        return hash_md5.hexdigest()
                    except Exception as e:
                        logging.error(f"MD5 hesaplanırken hata: {e}")
                        return None
                
                if not hasattr(canvas, 'add_image_from_path'):
                    def add_image_from_path(self, original_image_path):
                        """Verilen yoldaki resmi aktif sayfaya ekler."""
                        try:
                            if not os.path.exists(original_image_path):
                                logging.error(f"Resim dosyası bulunamadı: {original_image_path}")
                                return

                            # images klasörünü oluştur (yoksa)
                            images_dir = os.path.join(os.getcwd(), "images")
                            os.makedirs(images_dir, exist_ok=True)
                            
                            # Resmin MD5 özetini hesapla
                            img_hash = get_file_md5(original_image_path)
                            if img_hash is None:
                                logging.error("Resmin hash değeri hesaplanamadı.")
                                return
                                
                            # Resmin uzantısını al
                            _, ext = os.path.splitext(original_image_path)
                            
                            # Hedef dosya adı oluştur (MD5 + orijinal uzantı)
                            target_filename = f"{img_hash}{ext.lower()}"
                            target_path = os.path.join(images_dir, target_filename)
                            
                            # Resim zaten images klasöründe var mı kontrol et
                            if not os.path.exists(target_path):
                                # Resmi images klasörüne kopyala
                                shutil.copy2(original_image_path, target_path)
                                logging.info(f"Resim images klasörüne kopyalandı: {target_path}")
                            else:
                                logging.info(f"Resim zaten images klasöründe mevcut: {target_path}")

                            # Resmin QPixmap'ini yükle
                            from PyQt6.QtGui import QPixmap
                            pixmap = QPixmap(target_path)
                            if pixmap.isNull():
                                logging.error(f"Resim dosyası yüklenemedi: {target_path}")
                                return

                            # Benzersiz bir UUID oluştur
                            img_uuid = str(uuid.uuid4())
                            
                            # Aktif sayfanın merkezini hesapla
                            page = self._parent_page if hasattr(self, '_parent_page') else None
                            if not page:
                                logging.error("add_image_from_path: page bulunamadı")
                                return

                            # Resmin özelliklerini belirle
                            target_size = min(pixmap.width(), pixmap.height())  # Max 300px veya orijinal boyut
                            if target_size > 300:
                                target_size = 300
                                
                            # Canvas'ın ortasına yerleştir
                            canvas_width = self.width()
                            canvas_height = self.height()
                            x = (canvas_width - target_size) / 2
                            y = (canvas_height - target_size) / 2
                            
                            # Resim verisini oluştur
                            rect = QRectF(x, y, target_size, target_size)
                            image_data = {
                                'rect': rect,
                                'angle': 0.0,
                                'path': target_path,  # Kopyalanan dosyanın yolu
                                'pixmap': pixmap,    # Geçici QPixmap nesnesi (Performans için)
                                'uuid': img_uuid,    # Benzersiz tanımlayıcı
                                'hash': img_hash,    # İçerik özeti
                                'original_path': original_image_path,  # Orijinal yol (bilgi amaçlı)
                                'filepath': target_path  # YENİ: resim_islem_handler için dosya yolu
                            }
                            
                            # Resmi sayfanın images listesine ekle
                            page.images.append(image_data)
                            
                            # YENİ: resim_islem_handler kullan
                            resim_islem_handler.handle_select_image(target_path)
                            
                            # Sayfayı değişti olarak işaretle ve güncelle
                            page.mark_as_modified()
                            self.update()
                        except Exception as e:
                            logging.error(f"Resim eklenirken hata: {e}", exc_info=True)
                    
                    canvas.add_image_from_path = types.MethodType(add_image_from_path, canvas)
                
                canvas.add_image_from_path(secilen_yol)
        except Exception as e:
            logging.error(f"Resim seçme işleminde hata: {e}", exc_info=True)

    def _handle_cut_action(self):
        current_page = self.page_manager.get_current_page()
        if current_page and hasattr(current_page, 'drawing_canvas'):
            clipboard_handler.handle_cut_selection(current_page.drawing_canvas)

    def _handle_copy_action(self):
        current_page = self.page_manager.get_current_page()
        if current_page and hasattr(current_page, 'drawing_canvas'):
            clipboard_handler.handle_copy_selection(current_page.drawing_canvas)

    def _handle_paste_action(self):
        current_page = self.page_manager.get_current_page()
        if current_page and hasattr(current_page, 'drawing_canvas'):
            clipboard_handler.handle_paste_selection(current_page.drawing_canvas)

    def _handle_delete_image_action(self):
        """
        Resmi sil butonuna tıklandığında seçili resmi undo/redo ile siler.
        Disk üzerindeki dosya kaydedilmemiş notla birlikte çıkışta silinir.
        """
        current_page = self.page_manager.get_current_page()
        if not current_page or not hasattr(current_page, 'drawing_canvas'):
            return
        canvas = current_page.drawing_canvas
        if hasattr(canvas, 'selected_item_indices') and canvas.selected_item_indices:
            selected = canvas.selected_item_indices[0]
            if selected[0] == 'images':
                img_index = selected[1]
                if hasattr(canvas._parent_page, 'images') and 0 <= img_index < len(canvas._parent_page.images):
                    # YENİ: Resim dosya yolunu al ve handler'a bildir
                    image_data = canvas._parent_page.images[img_index]
                    image_path = image_data.get('filepath') or image_data.get('path')
                    
                    # Resim bilgisini handler'a bildir (dosyayı SİLMEZ)
                    if image_path:
                        resim_islem_handler.handle_delete_image(image_path)
                    
                    # Undo/redo ile silme işlemi yap (sadece veritabanı referansını siler)
                    from utils.commands import DeleteItemsCommand
                    command = DeleteItemsCommand(canvas, [selected])
                    canvas.undo_manager.execute(command)
        # Artık burada dosya silme yok

    def _delete_unused_images_on_exit(self):
        """
        Uygulama kapatılırken, images klasöründeki kullanılmayan dosyaları siler.
        Eğer not defteri kaydedilmemişse, içindeki resimler de silinir.
        """
        import os
        images_dir = os.path.join(os.getcwd(), "images")
        if not os.path.exists(images_dir):
            return

        # Not defteri kaydedilmemişse ve değişiklikler varsa, resimlerin silinmesi gerekir
        is_notebook_saved = self.current_notebook_path is not None
        notebook_has_changes = self.page_manager.has_unsaved_changes()
        delete_all_current_images = not is_notebook_saved or (is_notebook_saved and notebook_has_changes)
        
        if delete_all_current_images:
            logging.info(f"Not defteri kaydedilmemiş veya değişiklikler var. Resimler silinecek.")

        # Mevcut sayfalardan tüm dosya yollarını topla
        all_image_paths = set()
        if not delete_all_current_images:  # Eğer not kaydedilmişse, kullanılan resimleri koru
            for i in range(self.page_manager.count()):
                scroll_area = self.page_manager.widget(i)
                if hasattr(scroll_area, 'widget') and scroll_area.widget():
                    page = scroll_area.widget()
                    if hasattr(page, 'images'):
                        for img in page.images:
                            path = img.get('path')
                            if path and os.path.exists(path):
                                all_image_paths.add(os.path.abspath(path))
        
        # images klasöründeki her dosyayı kontrol et
        for fname in os.listdir(images_dir):
            if not fname.startswith('.'):  # Gizli dosyaları atla
                fpath = os.path.abspath(os.path.join(images_dir, fname))
                if os.path.isfile(fpath) and (delete_all_current_images or fpath not in all_image_paths):
                    try:
                        os.remove(fpath)
                        logging.info(f"[EXIT] Kullanılmayan resim dosyası silindi: {fpath}")
                    except Exception as e:
                        logging.error(f"[EXIT] Resim dosyası silinirken hata: {e}")

    def _handle_zoom_in_pdf_only(self):
        current_page = self.page_manager.get_current_page()
        if hasattr(current_page, 'is_pdf_page') and current_page.is_pdf_page:
            from handlers import view_handler
            view_handler.handle_zoom_in(self.page_manager)
        else:
            QMessageBox.information(self, "Zoom Kullanılamaz", "Yakınlaştırma sadece PDF sayfalarında kullanılabilir.")

    def _handle_zoom_out_pdf_only(self):
        current_page = self.page_manager.get_current_page()
        if hasattr(current_page, 'is_pdf_page') and current_page.is_pdf_page:
            from handlers import view_handler
            view_handler.handle_zoom_out(self.page_manager)
        else:
            QMessageBox.information(self, "Zoom Kullanılamaz", "Uzaklaştırma sadece PDF sayfalarında kullanılabilir.")

    def _handle_reset_zoom_pdf_only(self):
        current_page = self.page_manager.get_current_page()
        if hasattr(current_page, 'is_pdf_page') and current_page.is_pdf_page:
            from handlers import view_handler
            view_handler.handle_reset_view(self.page_manager)
        else:
            QMessageBox.information(self, "Zoom Kullanılamaz", "Zoom sıfırlama sadece PDF sayfalarında kullanılabilir.")

    def _handle_snap_line_to_grid_changed(self, state):
        """Toolbar'daki grid'e snap checkbox'ı değiştiğinde DrawingCanvas'a ve ayarlara uygula."""
        self.settings['grid_snap_enabled'] = (state == Qt.CheckState.Checked.value)
        current_page = self.page_manager.get_current_page()
        if current_page and hasattr(current_page, 'drawing_canvas'):
            # Tüm grid ayarlarını uygula
            current_page.drawing_canvas.apply_grid_settings(self.settings)

    def _handle_open_grid_settings(self):
        """Grid ayarları penceresini açar."""
        current_page = self.page_manager.get_current_page()
        # --- DÜZELTME: .canvas -> .drawing_canvas ---
        if not current_page or not current_page.drawing_canvas: 
            logging.warning("_handle_open_grid_settings: Aktif sayfa veya drawing_canvas bulunamadı.")
            return

        # --- YENİ: Diyalog açılmadan önceki orijinal grid ayarlarını sakla ---
        original_grid_settings_backup = {
            key: self.settings.get(key, DEFAULT_GRID_SETTINGS[key]) 
            for key in DEFAULT_GRID_SETTINGS.keys()
        }
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

        initial_dialog_settings = {
            key: self.settings.get(key, DEFAULT_GRID_SETTINGS[key]) 
            for key in DEFAULT_GRID_SETTINGS.keys()
        }
        logging.debug(f"GridSettingsDialog için başlangıç ayarları: {initial_dialog_settings}")

        dialog = GridSettingsDialog(current_settings=initial_dialog_settings, parent=self)

        # --- Gerçek zamanlı güncelleme için sinyal/slot bağlantısı ---
        def _realtime_grid_apply(settings_dict):
            # self.settings.update(settings_dict) # BU SATIR KALDIRILDI: self.settings sadece "Tamam" ile güncellenecek.
            logging.debug(f"_realtime_grid_apply: Canvas'lar güncelleniyor: {settings_dict}")
            if settings_dict.get("grid_apply_to_all_pages", False):
                self.page_manager.apply_grid_settings_to_all_canvases(settings_dict)
            else:
                active_page = self.page_manager.get_current_page()
                # --- DÜZELTME: .canvas -> .drawing_canvas ---
                if active_page and active_page.drawing_canvas and hasattr(active_page.drawing_canvas, 'apply_grid_settings'):
                    active_page.drawing_canvas.apply_grid_settings(settings_dict)
        
        dialog.settings_changed.connect(_realtime_grid_apply)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

        if dialog.exec():
            new_settings = dialog.get_settings()
            # Anahtarları dönüştür
            key_map = {
                'grid_apply_to_all': 'grid_apply_to_all_pages',
                'grid_only_line_tool': 'grid_show_for_line_tool_only',
            }
            for old_key, new_key in key_map.items():
                if old_key in new_settings:
                    new_settings[new_key] = new_settings.pop(old_key)
            self.settings.update(new_settings) 
            logging.info(f"Grid ayarları 'Tamam' ile güncellendi ve kaydedilecek: {new_settings}")
            self._save_settings(self.settings) 
            
            # "Tüm sayfalara uygula" seçeneği işaretliyse (veya değilse bile) canvas'lar zaten 
            # _realtime_grid_apply ile güncellenmiş olmalı. Yine de emin olmak için bir daha yapılabilir
            # veya bu kısım kaldırılabilir. Şimdilik bırakalım, zararı olmaz.
            if new_settings.get("grid_apply_to_all_pages", False):
                self.page_manager.apply_grid_settings_to_all_canvases(new_settings)
            else:
                current_page_for_apply = self.page_manager.get_current_page()
                # --- DÜZELTME: .canvas -> .drawing_canvas ---
                if current_page_for_apply and current_page_for_apply.drawing_canvas:
                    current_page_for_apply.drawing_canvas.apply_grid_settings(new_settings)
        else: 
            # --- YENİ: İptal durumunda orijinal ayarlara geri dön ---
            logging.info("Grid ayarları penceresi iptal edildi. Orijinal ayarlara geri dönülüyor.")
            # self.settings'i de eski haline döndür!
            self.settings.update(original_grid_settings_backup)
            # Canvas'ları bu orijinal ayarlarla güncelle
            if original_grid_settings_backup.get("grid_apply_to_all_pages", False):
                 self.page_manager.apply_grid_settings_to_all_canvases(original_grid_settings_backup)
            else:
                active_page = self.page_manager.get_current_page()
                if active_page and active_page.drawing_canvas and hasattr(active_page.drawing_canvas, 'apply_grid_settings'):
                    active_page.drawing_canvas.apply_grid_settings(original_grid_settings_backup)
            # --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    # ... (varsa diğer metodlar) 
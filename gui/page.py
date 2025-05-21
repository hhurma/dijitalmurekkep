from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtProperty, pyqtSignal, QPointF, QSize
from PyQt6.QtGui import QColor, QPalette, QPixmap
import logging
from typing import List, TYPE_CHECKING
import os

from .drawing_canvas import DrawingCanvas
from utils.undo_redo_manager import UndoRedoManager
from .enums import Orientation, TemplateType

# --- YENİ: MainWindow tipi --- #
# if TYPE_CHECKING:
# from .arayuz import MainWindow
# --- --- --- --- --- --- --- -- #

class Page(QWidget):
    """Tek bir not sayfasını ve ilişkili çizim alanını/yöneticisini temsil eder."""

    # --- Sinyaller ---
    modified_status_changed = pyqtSignal(bool)
    view_changed = pyqtSignal()
    page_content_changed = pyqtSignal()

    def __init__(self, page_number: int, main_window: 'MainWindow', 
                 template_settings: dict | None = None, 
                 default_orientation_str: str = "portrait",
                 parent=None):
        super().__init__(parent)
        
        # --- Arka Plan Rengini Ayarla ---
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('white'))
        self.setPalette(palette)
        # --- --- --- --- --- --- --- ---
        
        self.page_number = page_number
        self.template_settings = template_settings if template_settings is not None else {}
        self._is_modified = False
        self._orientation = Orientation.PORTRAIT # YENİ: İlk atama
        self.zoom_level = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        
        # --- YENİ: Resim Veri Listesi --- #
        self.images: List[dict] = []
        # --- --- --- --- --- --- --- -- #

        # --- Undo/Redo Manager Önce Oluşturulmalı --- #
        self.undo_manager = UndoRedoManager()
        self.undo_manager.content_modified.connect(self.mark_as_modified)
        # --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: MainWindow referansını sakla --- #
        self.main_window = main_window
        # --- --- --- --- --- --- --- --- --- --- #

        # Sayfa düzeni
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.drawing_canvas = DrawingCanvas(undo_manager=self.undo_manager, template_settings=self.template_settings)
        self.drawing_canvas.set_parent_page(self)
        layout.addWidget(self.drawing_canvas, 1)

        logging.info(f"Sayfa {self.page_number} oluşturuluyor.")
        
        # --- YENİ: Başlangıç Yönünü Ayarla (Setter aracılığıyla) ---
        try:
            initial_orientation_enum = Orientation[default_orientation_str.upper()]
        except KeyError:
            logging.warning(f"Geçersiz orientation string '{default_orientation_str}' alındı, varsayılan PORTRAIT kullanılacak.")
            initial_orientation_enum = Orientation.PORTRAIT
        self.orientation = initial_orientation_enum # Setter'ı çağırır
        # --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    def get_canvas(self) -> 'DrawingCanvas | None':
        """Çizim canvas'ını döndürür. Pixmap'ların yüklenmesini sağlar."""
        # --- YENİ: Pixmap yüklemesini tetikle ---
        self._ensure_pixmaps_loaded()
        # --- QGraphicsPixmapItem yükleme kısmı zaten kaldırılmıştı ---
        if hasattr(self, 'drawing_canvas') and self.drawing_canvas:
            return self.drawing_canvas
        else:
            logging.error("Page.get_canvas(): drawing_canvas bulunamadı!")
            return None

    def get_undo_manager(self) -> UndoRedoManager:
        """Undo/Redo yöneticisini döndürür."""
        return self.undo_manager

    @pyqtProperty(bool)
    def is_modified(self) -> bool:
        """Sayfada kaydedilmemiş değişiklik olup olmadığını döndürür."""
        return self._is_modified

    def mark_as_modified(self):
        """Sayfayı 'değiştirildi' olarak işaretler ve sinyal yayınlar."""
        if not self._is_modified:
            self._is_modified = True
            self.modified_status_changed.emit(True)
            logging.debug(f"Sayfa {self.page_number} değiştirildi olarak işaretlendi.")
            self.page_content_changed.emit()

    def mark_as_saved(self):
        """Sayfayı 'kaydedildi' olarak işaretler (değiştirilmedi) ve sinyal yayınlar."""
        if self._is_modified:
            self._is_modified = False
            self.modified_status_changed.emit(False)
            logging.debug(f"Sayfa {self.page_number} kaydedildi olarak işaretlendi.")

    # --- Orientation Property --- #
    @pyqtProperty(Orientation)
    def orientation(self) -> Orientation:
        return self._orientation

    @orientation.setter
    def orientation(self, orientation: Orientation):
        """Sayfanın yönünü ayarlar ve canvas'ı günceller."""
        if self._orientation != orientation: # Internal variable check
            self._orientation = orientation # Set internal variable
            logging.debug(f"Page {self.page_number} orientation set to {orientation.name}")
            # Yön değişikliği canvas'ın yeni arkaplan resmini yüklemesini gerektirir
            if hasattr(self, 'drawing_canvas') and self.drawing_canvas:
                self.drawing_canvas.load_background_template_image()
            # self.drawing_widget.update() # Bu satır kaldırıldı/yorum yapıldı

    # --- Template Property --- #
    # Gerekirse template için de benzer property/setter eklenebilir.
    # Şimdilik canvas üzerinden yönetiliyor.

    # İleride sayfaya özel veriler (örn. başlık, arka plan rengi vs.) buraya eklenebilir.

    # --- YENİ: Görünüm Kontrol Metotları --- #
    def set_zoom(self, zoom_level: float):
        """Yakınlaştırma seviyesini ayarlar ve görünümü günceller."""
        # Çok fazla yakınlaşma/uzaklaşmayı engelle
        new_zoom = max(0.1, min(zoom_level, 10.0)) # Örnek sınırlar
        if abs(self.zoom_level - new_zoom) > 1e-6:
            self.zoom_level = new_zoom
            logging.debug(f"Sayfa {self.page_number} zoom seviyesi: {self.zoom_level:.2f}")
            self.view_changed.emit()
            # self.drawing_canvas.update() # Canvas'ı yeniden çiz -> updateGeometry ile yönetilecek
            if hasattr(self.drawing_canvas, 'updateGeometry'):
                self.drawing_canvas.updateGeometry() # Boyut ipuçlarının değiştiğini bildir
            if hasattr(self.drawing_canvas, 'adjustSize'):
                 self.drawing_canvas.adjustSize() # Canvas'ı yeni sizeHint'e göre ayarla
            self.drawing_canvas._cache_dirty = True
            self.drawing_canvas.update() # Son olarak yeniden çizim yap
            
    def set_pan(self, pan_offset: QPointF):
        """Kaydırma ofsetini ayarlar ve görünümü günceller."""
        # Belki ofset sınırları da eklenebilir?
        if self.pan_offset != pan_offset:
             self.pan_offset = pan_offset
             logging.debug(f"Sayfa {self.page_number} pan ofseti: ({self.pan_offset.x():.1f}, {self.pan_offset.y():.1f})")
             self.view_changed.emit()
             self.drawing_canvas._cache_dirty = True
             self.drawing_canvas.update()
             
    def reset_view(self):
        """Yakınlaştırma ve kaydırmayı sıfırlar."""
        changed = False
        if abs(self.zoom_level - 1.0) > 1e-6:
             self.zoom_level = 1.0
             changed = True
        if self.pan_offset != QPointF(0.0, 0.0):
             self.pan_offset = QPointF(0.0, 0.0)
             changed = True
             
        if changed:
            logging.info(f"Sayfa {self.page_number} görünümü sıfırlandı.")
            self.view_changed.emit()
            # self.drawing_canvas.update() 
            if hasattr(self.drawing_canvas, 'updateGeometry'):
                self.drawing_canvas.updateGeometry()
            if hasattr(self.drawing_canvas, 'adjustSize'):
                self.drawing_canvas.adjustSize()
            self.drawing_canvas._cache_dirty = True
            self.drawing_canvas.update()

    # --- YENİ: Pixmap Yükleme Metodu --- #
    def _ensure_pixmaps_loaded(self):
        """images listesindeki pixmap'ı None olan resimleri yükler."""
        # logging.debug(f"Page {self.page_number}: Checking if pixmaps need loading...") # Çok sık log olabilir
        pixmaps_loaded = 0
        for i, img_data in enumerate(self.images):
            # Pixmap yoksa VE path varsa yüklemeyi dene
            if img_data.get('pixmap') is None and img_data.get('path'):
                img_path = img_data['path']
                if os.path.exists(img_path):
                    try:
                        loaded_pixmap = QPixmap(img_path)
                        if not loaded_pixmap.isNull():
                            self.images[i]['pixmap'] = loaded_pixmap
                            pixmaps_loaded += 1
                            logging.debug(f"Page {self.page_number}: Loaded pixmap for image {i} (UUID: {img_data.get('uuid')}) from {img_path}")
                        else:
                            logging.warning(f"Page {self.page_number}: Pixmap could not be loaded (isNull) for image {i} from {img_path}")
                            # Belki burada path'i None yapmak iyi olabilir? Şimdilik kalsın.
                    except Exception as e:
                        logging.error(f"Page {self.page_number}: Error loading pixmap for image {i} from {img_path}: {e}", exc_info=True)
                else:
                    logging.warning(f"Page {self.page_number}: Image file not found for image {i} at path: {img_path}")
                    # Dosya bulunamadıysa path'i None yapabiliriz, böylece tekrar denenmez?
                    # self.images[i]['path'] = None 
            # Else: Ya pixmap var ya da path yok, bir şey yapma
        
        # if pixmaps_loaded > 0:
        #     logging.debug(f"Page {self.page_number}: Loaded {pixmaps_loaded} new pixmaps.")
        #     # Belki canvas'ı güncellemek gerekir? get_canvas içinde çağrıldığı için gerekmemeli.
        #     # self.drawing_canvas.update() 
    # --- --- --- --- --- --- --- --- --- 

    def set_background_image(self, image_path: str):
        """Verilen yoldaki resmi sayfanın özel arka planı olarak ayarlar."""
        if not os.path.exists(image_path):
            logging.error(f"Page {self.page_number}: Arka plan resmi dosyası bulunamadı: {image_path}")
            return False

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            logging.error(f"Page {self.page_number}: Arka plan resmi yüklenemedi (null döndü): {image_path}")
            return False

        if hasattr(self.drawing_canvas, 'set_page_background_pixmap'):
            self.drawing_canvas.set_page_background_pixmap(pixmap, image_path) 
            logging.info(f"Sayfa {self.page_number} için arka plan resmi ayarlandı: {image_path}")
            self.mark_as_modified()
            return True
        else:
            logging.error(f"Page {self.page_number}: DrawingCanvas'ta 'set_page_background_pixmap' metodu bulunamadı.")
            return False

    def get_canvas_size(self) -> QSize:
        """Canvas'ın mevcut boyutunu döndürür."""
        return self.drawing_canvas.size()

    def get_page_data_for_export(self) -> dict:
        """Bu sayfanın içeriğini (çizgiler, şekiller, resimler)
        dışa aktarmaya uygun bir formatta döndürür.
        """
        canvas_data = {
            'lines': [],
            'shapes': [],
            'images': [],
            'pdf_background_source_path': None
        }
        if self.drawing_canvas:
            canvas_data['lines'] = self.drawing_canvas.lines
            canvas_data['shapes'] = self.drawing_canvas.shapes
            # DrawingCanvas'tan resim verilerini al (bu metodun var olduğunu varsayıyoruz)
            # Bu metod, resimlerin yollarını, konumlarını, boyutlarını ve açılarını döndürmeli.
            if hasattr(self.drawing_canvas, 'get_image_export_data'):
                canvas_data['images'] = self.drawing_canvas.get_image_export_data()
            
            # YENİ: PDF'ten gelen özel arka planın yolunu ekle
            if hasattr(self.drawing_canvas, '_pdf_background_source_path'):
                canvas_data['pdf_background_source_path'] = self.drawing_canvas._pdf_background_source_path
            else:
                canvas_data['pdf_background_source_path'] = None
        
        # Sayfanın diğer meta verilerini de ekleyebiliriz (örn. orientation, zoom, pan)
        # Ancak bunlar zaten file_handler.py'da pages_render_data'ya ekleniyor.
        # Bu fonksiyon sadece "içerik" üzerine odaklanmalı.
        return canvas_data

    # --- Mevcut QActions (Kopyala, Yapıştır vb.) ---
    def _create_actions(self):
        pass # Linter hatasını düzeltmek için geçici pass
    
    def get_content_for_clipboard(self) -> dict | None:
        pass # Linter hatasını düzeltmek için geçici pass

    def paste_content_from_clipboard(self, content: dict):
        pass # Linter hatasını düzeltmek için geçici pass

    # --- YENİ: Resim Pixmap'lerini Yükleme --- #
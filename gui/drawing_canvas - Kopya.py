from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QColor, QTabletEvent, QPainter, QPen, QBrush, QCursor, QPaintEvent, QPainterPath, QRadialGradient, QPixmap, QVector2D, QTransform
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from OpenGL import GL
import logging
import os # YENİ: os modülü eklendi
# from enum import Enum, auto # Kaldırıldı
# --- YENİ: QGraphicsPixmapItem import --- #
from PyQt6.QtWidgets import QApplication, QSizePolicy, QGraphicsPixmapItem
# --- --- --- --- --- --- --- --- --- --- -- #
import copy
from PyQt6.QtCore import pyqtSlot, pyqtSignal
import math
import time
# --- YENİ: Optional import --- #
from typing import Optional
# --- --- --- --- --- --- --- #

# Yardımcı çizim fonksiyonlarını import et
# --- DÜZELTME: Mutlak import kullan --- #
from utils import drawing_helpers, geometry_helpers, erasing_helpers # erasing_helpers eklendi
from utils import view_helpers # YENİ: Görünüm yardımcıları
# Komutları ve manager'ı import et
from utils.commands import ( # Komutları toplu import edelim
    DrawLineCommand, ClearCanvasCommand, DrawShapeCommand, MoveItemsCommand,
    ResizeItemsCommand, EraseCommand, RotateItemsCommand # EraseCommand eklendi (henüz tanımlanmadı), RotateItemsCommand eklendi
)
from utils.undo_redo_manager import UndoRedoManager
# Enumları yeni dosyadan import et
# --- DÜZELTME: Bu hala göreceli olmalı --- #
from .enums import TemplateType, ToolType, Orientation # YENİ: Orientation eklendi
# --- --- --- --- --- --- --- --- --- --- #
from typing import List, Tuple, Any
# YENİ: selection_helpers import et
from utils import selection_helpers
# --- --- --- --- --- --- --- --- --- --- -- #

# Sabitler
HANDLE_SIZE = 10 # Tutamaç boyutu (piksel) - Eski haline getirildi (8 -> 10)
DEFAULT_ERASER_WIDTH = 10.0 # Varsayılan silgi genişliği
RESIZE_MOVE_THRESHOLD = 3.0 # YENİ: Yeniden boyutlandırmayı tetiklemek için gereken minimum hareket (piksel)

# --- YENİ: Sabitler ---
TEMPLATE_IMAGE_DIR = "generated_templates" # JPG şablonlarının olduğu klasör
# --- --- --- --- --- ---

# Varsayılan Şablon Ayarları (Eğer dışarıdan gelmezse)
DEFAULT_TEMPLATE_SETTINGS = {
    "line_color": [0.8, 0.8, 1.0, 0.7],
    "grid_color": [0.9, 0.9, 0.9, 0.8],
    "line_spacing_pt": 28,
    "grid_spacing_pt": 14
}

# Punto'yu Piksel'e çevirme (yaklaşık, ekran DPI'ına göre değişebilir)
# Şimdilik sabit bir oran kullanalım veya daha sonra dinamik hale getirelim.
# 96 DPI varsayımıyla: 1 pt = 96/72 piksel = 1.333 piksel
PT_TO_PX = 96 / 72.0

# Helper to convert RGBA float tuple (0-1) to QColor
def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black) # Varsayılan
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

class DrawingCanvas(QWidget):
    """QWidget tabanlı çizim alanı (QPainter ile). Yakınlaştırma/Kaydırma destekler."""
    # --- YENİ: Sinyaller (içerik değişimi için) ---
    content_changed = pyqtSignal() # Canvas içeriği değiştiğinde (çizgi, şekil, resim eklendi/silindi)
    # --- --- --- --- --- --- --- --- --- --- ---

    def __init__(self, undo_manager: UndoRedoManager, parent=None, template_settings: dict | None = None):
        super().__init__(parent)
        # --- Boyut Politikası Ayarı ---
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # --- Arka Planı Beyaz Yap --- (QWidget için gerekli)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)
        # --- --- --- --- --- --- --- ---
        self.undo_manager = undo_manager
        self._parent_page: 'Page' | None = None # DEĞİŞİKLİK: self.parent_page -> self._parent_page
        # Zoom/Pan state'i Page'den alacağız
        # self.zoom_level = 1.0 # KALDIRILDI
        # self.pan_offset = QPointF(0.0, 0.0) # KALDIRILDI

        # Durum Değişkenleri
        self.drawing = False
        self.drawing_shape = False
        self.moving_selection = False
        self.resizing_selection = False
        self.selecting = False # YENİ: Seçim dikdörtgeni çiziliyor mu?
        self.erasing = False # YENİ: Silme durumu
        self.temporary_erasing = False # YENİ: Kalemle geçici silme modu
        self.laser_pointer_active = False # YENİ: Lazer işaretçi modu
        self.temporary_drawing_active = False # YENİ: Geçici çizim modu
        self.rotating_selection = False # YENİ: Döndürme durumu
        self.last_cursor_pos_screen = QPointF() # YENİ: Lazer için ekran koordinatı
        self.select_press_point = None
        self.move_start_point = QPointF()
        self.resize_start_pos = QPointF()
        self.rotation_start_pos_world = QPointF() # YENİ: Döndürme başlangıç noktası (dünya)
        self.rotation_center_world = QPointF() # YENİ: Döndürme merkezi (dünya)
        self.rotation_original_angle = 0.0 # YENİ: Döndürme başlangıç açısı
        self.grabbed_handle_type: str | None = None
        self.resize_original_bbox = QRectF()

        # Çizim Verileri
        self.lines: List[List[Any]] = []
        self.shapes: List[List[Any]] = []
        self.current_line_points: List[QPointF] = []
        self.current_eraser_path: List[QPointF] = [] # YENİ: Silgi yolu
        self.erased_this_stroke: List[Tuple[str, int, Any]] = [] # YENİ: Bu silme işleminde silinenler
        self.shape_start_point = QPointF()
        self.shape_end_point = QPointF()

        # Seçim ve Etkileşim Verisi
        self.selected_item_indices: List[Tuple[str, int]] = []
        self.last_move_pos = QPointF()
        self.current_handles: dict[str, QRectF] = {}
        self.original_resize_states: List[Any] = []
        self.move_original_states: List[Any] = [] # YENİ: Taşıma için orijinal durumlar

        # Aktif Araç ve Ayarları
        self.current_tool = ToolType.PEN
        self.current_color = (0.0, 0.0, 0.0, 1.0)
        self.current_pen_width = 2.0
        self.eraser_width = DEFAULT_ERASER_WIDTH # YENİ: Silgi genişliği
        self.pressure = 1.0
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.resize_threshold_passed = False # YENİ: Resize eşiği geçildi mi?

        # Şablon ayarları
        self.template_settings = template_settings if template_settings is not None else DEFAULT_TEMPLATE_SETTINGS.copy() # Kopyasını al
        self.template_line_color = self.template_settings.get("line_color", DEFAULT_TEMPLATE_SETTINGS["line_color"])
        self.template_grid_color = self.template_settings.get("grid_color", DEFAULT_TEMPLATE_SETTINGS["grid_color"])
        self.line_spacing_pt = self.template_settings.get("line_spacing_pt", DEFAULT_TEMPLATE_SETTINGS["line_spacing_pt"])
        self.grid_spacing_pt = self.template_settings.get("grid_spacing_pt", DEFAULT_TEMPLATE_SETTINGS["grid_spacing_pt"])
        # Başlangıç şablon tipini ayarlardan oku
        try:
             initial_template_name = self.template_settings.get('template_type_name', 'PLAIN')
             self.current_template = TemplateType[initial_template_name]
             logging.debug(f"Başlangıç şablon tipi ayarlardan okundu: {self.current_template}")
        except KeyError:
             logging.warning(f"Ayarlarda geçersiz başlangıç şablon tipi: '{initial_template_name}'. PLAIN kullanılıyor.")
             self.current_template = TemplateType.PLAIN
        except Exception as e:
            logging.error(f"Başlangıç şablon tipi okunurken hata: {e}")

        # --- YENİ: Geçici Çizim Verileri --- #
        self.temporary_lines: List[Tuple[List[Tuple[QPointF, float]], tuple, float]] = [] 
        self.current_temporary_line_points: List[Tuple[QPointF, float]] = [] 
        self._temporary_line_timer = QTimer(self) 
        self._temporary_line_timer.timeout.connect(self._check_temporary_lines)
        self._temporary_line_timer.start(50) 
        # Varsayılan görünüm ayarları
        self.temporary_line_duration = 5.0 
        self.temp_pointer_color = QColor('#FFA500') # Turuncu (Varsayılan)
        self.temp_pointer_width = 3.0 # Piksel (Varsayılan)
        # --- YENİ: Geçici İşaretçi Görünüm Faktörleri --- #
        self.temp_glow_width_factor: float = 2.5
        self.temp_core_width_factor: float = 0.5
        self.temp_glow_alpha_factor: float = 0.55 # Yeni varsayılan opaklık
        self.temp_core_alpha_factor: float = 0.9
        # --- --- --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: İşaretçi Ayarları İçin Varsayılanlar --- #
        self.laser_pointer_color = QColor('#FF0000') 
        self.laser_pointer_size = 10.0 
        # Geçici işaretçi renk/genişlik yukarıda tanımlandı
        # self.temp_pointer_color = QColor('#FFA500')
        # self.temp_pointer_width = 3.0
        # --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: parent_page ve _background_pixmap --- # 
        self._parent_page: 'Page' | None = None # Page referansı için tip ipucu
        self._background_pixmap: QPixmap | None = None # Yüklü arka plan resmi
        # --- --- --- --- --- --- --- --- --- --- --- -- #
        self._current_background_image_path: str | None = None
        # --- YENİ: Arka planı başlangıçta yükle --- #
        self.load_background_template_image() 
        # --- --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Resim Öğeleri için Liste --- #
        self.image_items: List[QGraphicsPixmapItem] = [] # QGraphicsPixmapItem tutar
        # --- --- --- --- --- --- --- --- --- -- #

        logging.info("DrawingCanvas (QWidget) başlatıldı.")

        # --- YENİ: Minimum boyutu ayarla --- #
        if self._background_pixmap and not self._background_pixmap.isNull():
            self.setMinimumSize(self._background_pixmap.size())
            logging.debug(f"Canvas minimum size set to background size: {self._background_pixmap.size().width()}x{self._background_pixmap.size().height()}")
        else:
            # Arka plan yoksa veya yüklenemediyse, varsayılan bir minimum boyut ayarla?
            # Veya scroll area\'nın boyutuna uymasını sağla (setMinimumSize(0,0) ?)
            self.setMinimumSize(600, 800) # Geçici bir varsayılan
        # --- --- --- --- --- --- --- --- --- -- #

        self.update() # Her durumda (yüklense de yüklenmese de) canvas'ı güncelle
    # --- --- --- --- --- --- --- --- --- --- #

    def get_image_export_data(self) -> List[dict]:
        """Sahnedeki resim öğelerinden PDF dışa aktarma için veri toplar."""
        export_data = []
        # NOTE: Bu metodun çalışması için QGraphicsPixmapItem'ların oluşturulurken
        # setData(Qt.ItemDataRole.UserRole + 1, image_path) ile orijinal dosya yolunun
        # saklanmış olması gerekir.
        for item in self.image_items:
            original_path = item.data(Qt.ItemDataRole.UserRole + 1)

            if not original_path or not isinstance(original_path, str):
                logging.warning(f"Resim öğesi ({item}) için geçerli orijinal yol bulunamadı. Dışa aktarma için atlanıyor.")
                continue

            # QGraphicsItem'ın sceneBoundingRect() metodu, öğenin sahnedeki
            # tüm dönüşümleri (pozisyon, ölçek, döndürme) uygulanmış sınırlayıcı kutusunu verir.
            # Bu, PDF'e yerleştirmek için ihtiyacımız olan dünya koordinatlarındaki geometridir.
            sbr = item.sceneBoundingRect() # Scene Bounding Rect

            # QGraphicsPixmapItem için rotation() doğrudan derece cinsinden döndürme verir.
            rotation = item.rotation()

            export_data.append({
                'path': original_path,
                'x': sbr.x(),
                'y': sbr.y(),
                'width': sbr.width(),
                'height': sbr.height(),
                'rotation': rotation
            })
            logging.debug(f"  PDF Export - Image Data: path={original_path}, x={sbr.x():.2f}, y={sbr.y():.2f}, w={sbr.width():.2f}, h={sbr.height():.2f}, rot={rotation:.2f}")
        return export_data

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Arka Planı Çiz (Artık Ölçekleme Yok) ---
        if self._background_pixmap and not self._background_pixmap.isNull():
            painter.drawPixmap(0, 0, self._background_pixmap) # (0,0)\'dan itibaren çiz
        else:
            # Arka plan yoksa yine de beyaz doldur
            painter.fillRect(self.rect(), Qt.GlobalColor.white)
        # --- --- --- --- --- --- --- --- --- --- ---

        # --- Dünya Dönüşümlerini Uygula (Zoom/Pan) --- #
        painter.save() 
        if self._parent_page:
            zoom = self._parent_page.zoom_level
            pan = self._parent_page.pan_offset
            # Önce scale sonra translate
            painter.scale(zoom, zoom)
            painter.translate(-pan.x(), -pan.y())
        # --- --- --- --- --- --- --- --- --- --- --- #
        
        # 1. Şablonu Çiz - ARTIK GEREKLİ DEĞİL, ARKA PLAN PIXMAP İLE YAPILIYOR
        # self._draw_template(painter) 
        
        # 2. Öğeleri Çiz
        # _draw_items metodunu çağır (self içinden)
        self._draw_items(painter)

        # 3. Geçici Çizimler (Çizim/Şekil sırasında)
        # Bu metodlar doğrudan helper'ları çağırabilir veya kendi içlerinde çizebilirler.
        # Şimdilik doğrudan helper çağıralım.
        if self.drawing:
            if self.current_tool == ToolType.PEN:
                if len(self.current_line_points) > 1:
                    drawing_helpers.draw_pen_stroke(painter, self.current_line_points, self.current_color, self.current_pen_width)
            # Selector dikdörtgeni ekran koordinatlarında çizilmeli (aşağıda)
            elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                 if self.drawing_shape and not self.shape_start_point.isNull() and not self.shape_end_point.isNull():
                    temp_shape_data = [self.current_tool, self.current_color, self.current_pen_width, self.shape_start_point, self.shape_end_point]
                    drawing_helpers.draw_shape(painter, temp_shape_data)

        # --- YENİ: Mevcut Geçici Çizgiyi Çiz --- #
        if self.temporary_drawing_active and len(self.current_temporary_line_points) > 1:
            temp_color = (self.temp_pointer_color.redF(), self.temp_pointer_color.greenF(), 
                          self.temp_pointer_color.blueF(), self.temp_pointer_color.alphaF())
            temp_width = self.temp_pointer_width
            # --- YENİ: Faktörleri canvas'tan al --- #
            drawing_helpers.draw_temporary_pointer_stroke(painter, 
                                                           self.current_temporary_line_points, 
                                                           temp_color, 
                                                           temp_width, 
                                                           self.temporary_line_duration,
                                                           self.temp_glow_width_factor,
                                                           self.temp_core_width_factor,
                                                           self.temp_glow_alpha_factor,
                                                           self.temp_core_alpha_factor)
            # --- --- --- --- --- --- --- --- --- -- #
        # --- --- --- --- --- --- --- --- --- --- -- #

        # 4. Geçici Silgi Yolu
        if self.erasing and len(self.current_eraser_path) > 1:
             drawing_helpers.draw_temporary_eraser_path(painter, self.current_eraser_path, self.eraser_width)
             
        # --- Dünya Dönüşümlerini Geri Al --- 
        painter.restore() # Orijinal painter durumuna dön (Ekran Koordinatları)
        # --- --- --- --- --- --- --- --- ---

        # --- Ekran Koordinatlarında Çizilecekler --- #
        
        # --- YENİ: Seçim Çerçeveleri ve Tutamaçlar --- #
        self._draw_selection_overlay(painter)
        # --- --- --- --- --- --- --- --- --- --- --- -- #

        # 5. Seçim Dikdörtgeni (Geçici)
        if self.current_tool == ToolType.SELECTOR and self.selecting:
             self._draw_selection_rectangle(painter) # QPainter versiyonu
             
        # 6. Silgi Önizlemesi
        if self.current_tool == ToolType.ERASER and self.underMouse():
             self._draw_eraser_preview(painter)
        # --- --- --- --- --- --- --- --- --- --- --- ---
             
        # --- DETAYLI LAZER LOG (PAINT) --- #
        log_paint = f"Paint Check Laser: Active={self.laser_pointer_active}, LastPos={self.last_cursor_pos_screen}, isNull={self.last_cursor_pos_screen.isNull()}"
        logging.debug(log_paint)
        # --- --- --- --- --- --- --- --- --- #

        # --- YENİ: Lazer İşaretçiyi Çiz (Ekran Koordinatlarında) --- #
        if self.laser_pointer_active and not self.last_cursor_pos_screen.isNull():
             # --- DEBUG LOG --- #
             logging.debug(f"Painting laser pointer at {self.last_cursor_pos_screen} (Size: {self.laser_pointer_size}, Color: {self.laser_pointer_color.name()})")
             # --- --- --- --- #
             painter.save()
             painter.setRenderHint(QPainter.RenderHint.Antialiasing)
             painter.setPen(Qt.PenStyle.NoPen)

             center_pos = self.last_cursor_pos_screen
             base_size = self.laser_pointer_size
             radius = base_size * 0.8 # Glow efekti için yarıçapı biraz artıralım
             
             # --- YENİ: Radyal Gradyan Kullan --- #
             gradient = QRadialGradient(center_pos, radius)
             
             # Merkez renk (daha opak)
             center_color = QColor(self.laser_pointer_color)
             center_color.setAlpha(220) 
             gradient.setColorAt(0.0, center_color) # Merkez (0.0)

             # Orta renk (yarı saydam)
             mid_color = QColor(self.laser_pointer_color)
             mid_color.setAlpha(100) 
             gradient.setColorAt(0.4, mid_color) # Merkezin biraz dışı (0.4)
             
             # Dış renk (tamamen saydam)
             outer_color = QColor(self.laser_pointer_color)
             outer_color.setAlpha(0)
             gradient.setColorAt(1.0, outer_color) # Kenar (1.0)

             painter.setBrush(QBrush(gradient))
             # Gradyanı tüm glow alanına uygula
             # drawEllipse merkezi değil sol üst köşeyi alır, dikkat!
             painter.drawEllipse(center_pos, radius, radius)
             # --- --- --- --- --- --- --- --- --- -- #

             painter.restore()
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

        painter.end()

    # --- Yardımcı Çizim Metodları (QPainter Kullanacak Şekilde Güncellendi) ---
    def _draw_items(self, painter: QPainter):
        """Tüm kalıcı öğeleri (çizgiler, şekiller, resimler) çizer."""
        # --- ÖNCE RESİMLERİ ÇİZ --- #
        if hasattr(self, 'image_items') and self.image_items:
            for item in self.image_items:
                if isinstance(item, QGraphicsPixmapItem) and item.pixmap() and not item.pixmap().isNull():
                    painter.save() # Mevcut painter durumunu kaydet

                    # QGraphicsPixmapItem'ın pozisyonu ve dönüşümü zaten dünya koordinatlarında
                    # veya _draw_items'a gelen painter'ın koordinat sistemine göredir.
                    item_pos = item.pos()  # Öğenin sol üst köşesinin pozisyonu
                    item_origin = item.transformOriginPoint() # Öğenin kendi içindeki dönüşüm merkezi
                    item_rotation = item.rotation() # Derece cinsinden

                    # 1. Öğenin pozisyonuna git (sol üst köşe)
                    painter.translate(item_pos.x(), item_pos.y())
                    
                    # 2. Dönüşüm merkezine git
                    painter.translate(item_origin.x(), item_origin.y())
                    # 3. Döndür
                    painter.rotate(item_rotation)
                    # 4. Dönüşüm merkezini geri al (pixmap'i (0,0)'dan çizmek için)
                    painter.translate(-item_origin.x(), -item_origin.y())
                    
                    # Pixmap'i (artık doğru şekilde konumlandırılmış ve döndürülmüş olan)
                    # koordinat sisteminin (0,0) noktasına çiz.
                    painter.drawPixmap(0, 0, item.pixmap())
                    
                    painter.restore() # Painter durumunu geri yükle
        # --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # Çizgileri Çiz
        if hasattr(self, 'lines') and self.lines:
            for line_data in self.lines:
                # Çizgi çizme mantığı... (kısaltıldı)
                if len(line_data) >= 3:
                    color_tuple, width, points = line_data[0], line_data[1], line_data[2]
                    if not points:
                        continue
                    pen = QPen(rgba_to_qcolor(color_tuple), width)
                    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(pen)
                    
                    path = QPainterPath()
                    path.moveTo(points[0])
                    for point in points[1:]:
                        path.lineTo(point)
                    painter.drawPath(path)

        # Şekilleri Çiz
        if hasattr(self, 'shapes') and self.shapes:
            for shape_data in self.shapes:
                # Şekil çizme mantığı... (kısaltıldı)
                if not shape_data or len(shape_data) < 5: continue
                tool_type, color_tuple, width, p1, p2 = shape_data[0], shape_data[1], shape_data[2], shape_data[3], shape_data[4]
                pen = QPen(rgba_to_qcolor(color_tuple), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

                if tool_type == ToolType.RECTANGLE:
                    painter.drawRect(QRectF(p1, p2).normalized())
                elif tool_type == ToolType.CIRCLE: # DEĞİŞİKLİK: ELLIPSE -> CIRCLE
                    painter.drawEllipse(QRectF(p1, p2).normalized())
                elif tool_type == ToolType.LINE:
                    painter.drawLine(p1, p2)
                # Diğer şekiller eklenebilir...

        # --- GÜNCELLENMİŞ RESİM ÇİZME MANTIĞI --- # (BU BLOK YUKARI TAŞINDI)
        # if hasattr(self, 'image_items') and self.image_items:
        #     for item in self.image_items:
        #         ...
        # --- --- --- --- --- --- --- --- --- --- --- --- --- #

    def _draw_selection_overlay(self, painter: QPainter):
        """Ekran koordinatlarında seçili öğelerin çerçevesini ve tutamaçlarını çizer."""
        self.current_handles.clear() # Her çizimden önce tutamaçları temizle

        if not self.selected_item_indices or not self._parent_page:
            return

        is_image_selection = False
        is_mixed_selection = False
        first_item_type = self.selected_item_indices[0][0]

        # Seçim tipini belirle (hepsi resim mi, hepsi çizim mi, karışık mı?)
        if first_item_type == 'images':
            is_image_selection = all(item[0] == 'images' for item in self.selected_item_indices)
        else: # İlk öğe çizgi veya şekil ise
            is_image_selection = False # Resim olamaz
            is_mixed_selection = any(item[0] == 'images' for item in self.selected_item_indices)

        # Şimdilik sadece tek bir resim veya birden çok çizim/şekil seçimine izin veriyoruz
        # Karışık veya birden çok resim seçiliyse çerçeve çizme
        if is_mixed_selection or (is_image_selection and len(self.selected_item_indices) > 1):
            # logging.debug("_draw_selection_overlay: Karışık veya çoklu resim seçimi, çerçeve çizilmiyor.")
            return

        # --- Tek Resim Seçiliyse --- #
        if is_image_selection and len(self.selected_item_indices) == 1:
            img_index = self.selected_item_indices[0][1]
            if 0 <= img_index < len(self._parent_page.images):
                img_data = self._parent_page.images[img_index]
                current_rect = img_data.get('rect', QRectF())
                current_angle = img_data.get('angle', 0.0)
                zoom = self._parent_page.zoom_level

                if not current_rect.isNull():
                    # 1. Döndürülmüş çerçeveyi çiz (selection_helpers kullanarak)
                    selection_helpers.draw_rotated_selection_frame(painter, current_rect, current_angle, zoom) # DEĞİŞİKLİK: self.world_to_screen argümanı kaldırıldı
                    
                    # --- DEĞİŞİKLİK: Tutamaç pozisyonlarını burada hesapla ---
                    # 2. Tutamaçların dünya koordinatlarını hesapla
                    rotated_corners = selection_helpers.get_rotated_corners(current_rect, current_angle)
                    handle_positions_world = {
                        'top-left': rotated_corners[0], 'top-right': rotated_corners[1],
                        'bottom-right': rotated_corners[2], 'bottom-left': rotated_corners[3],
                        'middle-top': (rotated_corners[0] + rotated_corners[1]) / 2.0,
                        'middle-right': (rotated_corners[1] + rotated_corners[2]) / 2.0,
                        'middle-bottom': (rotated_corners[2] + rotated_corners[3]) / 2.0,
                        'middle-left': (rotated_corners[3] + rotated_corners[0]) / 2.0,
                    }
                    # Döndürme tutamacını ekle
                    bottom_mid_point_world = handle_positions_world['middle-bottom']
                    center_world = current_rect.center()
                    # selection_helpers'dan import et
                    rotation_handle_offset_world = selection_helpers.ROTATION_HANDLE_OFFSET / zoom if zoom > 0 else selection_helpers.ROTATION_HANDLE_OFFSET
                    
                    vec_center_to_bottom = bottom_mid_point_world - center_world
                    if vec_center_to_bottom.manhattanLength() > 1e-6:
                        vec_center_to_bottom = vec_center_to_bottom * (1 + rotation_handle_offset_world / vec_center_to_bottom.manhattanLength())
                    rotation_handle_center_world = center_world + vec_center_to_bottom
                    
                    handle_positions_world['rotate'] = rotation_handle_center_world

                    # 3. Ekran koordinatlarını hesapla ve sakla
                    # handle_positions_world = selection_helpers.get_handle_positions_world(current_rect, current_angle, zoom) # --- BU SATIR KALDIRILDI ---
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    # --- TUTAMAÇ TİPİNE GÖRE BOYUT/TOLERANS ---
                    for handle_type, center_world in handle_positions_world.items():
                        center_screen = self.world_to_screen(center_world)
                        current_handle_size_screen = handle_size_screen
                        if handle_type == 'rotate':
                            current_handle_size_screen *= selection_helpers.ROTATION_HANDLE_SIZE_FACTOR
                        current_half_handle_screen = current_handle_size_screen / 2.0
                        # --- --- --- --- --- --- --- --- --- ---
                        handle_rect_screen = QRectF(
                            center_screen.x() - current_half_handle_screen, 
                            center_screen.y() - current_half_handle_screen,
                            current_handle_size_screen, 
                            current_handle_size_screen
                        )
                        self.current_handles[handle_type] = handle_rect_screen
            else:
                logging.warning(f"_draw_selection_overlay: Geçersiz resim indeksi: {img_index}")
                
        # --- Çizim/Şekil Seçiliyse --- #
        elif not is_image_selection: # is_mixed_selection zaten false
            combined_bbox_world = self._get_combined_bbox([]) # Argüman olarak boş liste verilebilir, çünkü selected_item_indices kullanıyor
            if not combined_bbox_world.isNull():
                # 1. Normal (döndürülmemiş) seçim çerçevesi çiz
                zoom = self._parent_page.zoom_level # Zoom seviyesini al
                selection_helpers.draw_standard_selection_frame(painter, combined_bbox_world, zoom) # YENİ FONKSİYON ÇAĞRISI
                
                # 2. Tutamaçların ekran koordinatlarını hesapla ve sakla
                # zoom = self._parent_page.zoom_level # Zaten yukarıda alındı
                handle_positions_world = {
                    'top-left': combined_bbox_world.topLeft(),
                    'top-right': combined_bbox_world.topRight(),
                    'bottom-left': combined_bbox_world.bottomLeft(),
                    'bottom-right': combined_bbox_world.bottomRight(),
                    'middle-left': QPointF(combined_bbox_world.left(), combined_bbox_world.center().y()),
                    'middle-right': QPointF(combined_bbox_world.right(), combined_bbox_world.center().y()),
                    'middle-top': QPointF(combined_bbox_world.center().x(), combined_bbox_world.top()),
                    'middle-bottom': QPointF(combined_bbox_world.center().x(), combined_bbox_world.bottom())
                }
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                for handle_type, center_world in handle_positions_world.items():
                    center_screen = self.world_to_screen(center_world)
                    handle_rect_screen = QRectF(
                        center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen,
                        handle_size_screen, handle_size_screen
                    )
                    self.current_handles[handle_type] = handle_rect_screen
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

    def _draw_selection_rectangle(self, painter: QPainter):
         # Bu metod artık paintEvent sonunda, ekran koordinatlarında çağrılıyor
         if not self.selecting or self.shape_start_point.isNull() or self.shape_end_point.isNull():
             return
             
         # Başlangıç/bitiş dünya koordinatları, ekran koordinatlarına çevir
         screen_start = self.world_to_screen(self.shape_start_point)
         screen_end = self.world_to_screen(self.shape_end_point)
         selection_rect = QRectF(screen_start, screen_end).normalized()
         
         painter.save()
         painter.setPen(QPen(QColor(0, 0, 255, 150), 1, Qt.PenStyle.DashLine))
         painter.setBrush(QBrush(QColor(0, 100, 255, 30)))
         painter.drawRect(selection_rect)
         painter.restore()
         
    # _draw_temporary_eraser_path - paintEvent içinde doğrudan helper çağrılıyor
         
    def _draw_eraser_preview(self, painter: QPainter):
        # Bu metod paintEvent sonunda, ekran koordinatlarında çağrılıyor
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(Qt.GlobalColor.gray, 1, Qt.PenStyle.SolidLine)
        brush = QBrush(QColor(128, 128, 128, 100))
        painter.setPen(pen)
        painter.setBrush(brush)
        radius = self.eraser_width / 2.0 # Silgi genişliği ekran pikseli cinsinden mi? Evet.
        pos_int = self.mapFromGlobal(QCursor.pos())
        if self.rect().contains(pos_int):
            painter.drawEllipse(QPointF(pos_int), radius, radius)
        painter.restore()

    def screen_to_world(self, screen_pos: QPointF) -> QPointF:
        # tabletEvent başında _parent_page kontrolü yapıldığı için,
        # burada tekrar kontrol etmeye gerek yok ve doğrudan _parent_page kullanabiliriz.
        # if not self._parent_page:
        #     logging.error("screen_to_world: parent_page referansı yok!")
        #     return QPointF()
        # Doğrudan _parent_page kullan
        if self._parent_page:
            return view_helpers.screen_to_world(
            screen_pos, self.width(), self.height(), 
                self._parent_page.zoom_level, self._parent_page.pan_offset
        )
        else:
            # Bu durum normalde tabletEvent kontrolünden dolayı olmamalı
            # ama bir güvenlik önlemi olarak loglayıp boş nokta döndürelim.
            logging.error("screen_to_world: _parent_page is None despite check in tabletEvent!")
            return QPointF()

    def world_to_screen(self, world_pos: QPointF) -> QPointF:
        # Benzer şekilde, world_to_screen kullanan metodlar da _parent_page kontrolü yapmalı
        # veya burada kontrolü tekrarlayabiliriz.
        if not self._parent_page:
             logging.error("world_to_screen: _parent_page referansı yok!")
             return QPointF()
        
        # --- YENİ: Girdi ve sonuç için None kontrolü ---
        if world_pos is None:
            logging.error("world_to_screen: Girdi olarak verilen world_pos None!")
            return QPointF()

        result = view_helpers.world_to_screen(
            world_pos, self.width(), self.height(), 
            self._parent_page.zoom_level, self._parent_page.pan_offset
        )
        
        if result is None:
            logging.error("view_helpers.world_to_screen None döndürdü! Canvas boyutu: %dx%d, zoom: %s, pan: %s, world_pos: %s",
                          self.width(), self.height(), self._parent_page.zoom_level, self._parent_page.pan_offset, world_pos)
            return QPointF() # Varsayılan QPointF döndür
            
        return result
        # --- --- --- --- --- --- --- --- --- --- --- -- #
         
    def _world_rect_to_screen_rect(self, world_rect: QRectF) -> QRectF:
         top_left_screen = self.world_to_screen(world_rect.topLeft())
         bottom_right_screen = self.world_to_screen(world_rect.bottomRight())
         return QRectF(top_left_screen, bottom_right_screen).normalized()
         
    def _update_projection(self):
         if self._parent_page:
             view_helpers.set_projection(
                 self.width(), self.height(), 
                 self._parent_page.zoom_level, self._parent_page.pan_offset
             )
         else:
              view_helpers.set_projection(self.width(), self.height(), 1.0, QPointF(0,0))

    def tabletEvent(self, event: QTabletEvent):
        # --- >>> YENİ: parent_page Kontrolü ve Loglama <<< ---
        if self._parent_page is None: # KONTROL: self.parent_page -> self._parent_page (zaten doğruymuş ama teyit)
            logging.error(f"tabletEvent received but self._parent_page is None! Ignoring event type: {event.type()}")
            event.ignore()
            return
        logging.debug(f"tabletEvent received: Type={event.type()}, ParentPage={self._parent_page.page_number}, ScreenPos={event.position()}")
        # --- >>> <<< ---
        
        # ScreenPos'u DÜNYA KOORDİNATINA çevir (parent_page artık None değil)
        pos = self.screen_to_world(event.position())
        self.pressure = event.pressure()

        event_type = event.type()

        if event_type == QTabletEvent.Type.TabletPress:
            self._handle_tablet_press(pos, event)
        elif event_type == QTabletEvent.Type.TabletMove:
            self._handle_tablet_move(pos, event)
        elif event_type == QTabletEvent.Type.TabletRelease:
            self._handle_tablet_release(pos, event)
        else:
            event.ignore() 

    def _handle_tablet_press(self, pos: QPointF, event: QTabletEvent):
        # Aktif araca göre handler'ı çağır
        if self.current_tool == ToolType.IMAGE_SELECTOR:
            logging.debug(f"--- IMAGE_SELECTOR Press Detected at World Pos: {pos} ---")
            if self._parent_page and hasattr(self._parent_page, 'main_window') and self._parent_page.main_window: # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                
                # --- YENİ: Döndürülmüş Tutamaca Tıklandı mı Kontrol Et --- #
                screen_pos = event.position()
                self.grabbed_handle_type = None # Önce sıfırla
                selected_img_rect = QRectF()
                selected_img_angle = 0.0
                
                # Sadece tek resim seçiliyken döndürme/boyutlandırma yapabiliriz (şimdilik)
                if len(self.selected_item_indices) == 1 and self.selected_item_indices[0][0] == 'images':
                    img_index = self.selected_item_indices[0][1]
                    if 0 <= img_index < len(self._parent_page.images): # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                        img_data = self._parent_page.images[img_index] # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                        selected_img_rect = img_data.get('rect', QRectF())
                        selected_img_angle = img_data.get('angle', 0.0)
                        
                        if not selected_img_rect.isNull():
                             zoom = self._parent_page.zoom_level if self._parent_page else 1.0 # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                             self.grabbed_handle_type = selection_helpers.get_handle_at_rotated_point(
                                 screen_pos, 
                                 selected_img_rect, 
                                 selected_img_angle, 
                                 zoom, 
                                 self.world_to_screen # Callback fonksiyonu
                             )
                             logging.debug(f"  Handle check result: {self.grabbed_handle_type}")
                    else:
                        logging.warning("Image Selector Press: Invalid image index in selection.")
                else:
                     logging.debug("Image Selector Press: Rotation/Resize handles require exactly one image selected.")

                # --- Tutamaç Tipine Göre İşlem Yap --- #
                if self.grabbed_handle_type == 'rotate':
                    logging.debug("Image Selector Press: Rotation handle grabbed. Starting rotation.")
                    self.rotating_selection = True
                    self.resize_threshold_passed = False # Reset flag
                    self.resizing_selection = False
                    self.moving_selection = False
                    self.drawing = False
                    self.selecting = False
                    
                    self.rotation_start_pos_world = pos # Döndürmeye başlanan dünya koordinatı
                    self.rotation_center_world = selected_img_rect.center() # Döndürme merkezi
                    self.rotation_original_angle = selected_img_angle # Başlangıç açısını sakla
                    
                    # Orijinal açıları komut için sakla (şimdilik tek öğe)
                    self.original_resize_states = [self.rotation_original_angle] # Resize state listesini kullanalım?
                    
                    QApplication.setOverrideCursor(selection_helpers.get_resize_cursor('rotate'))
                    self.update()
                    return # Başka bir işlem yapma
                    # --- --- --- --- --- --- --- --- --- -- #
                elif self.grabbed_handle_type: # Boyutlandırma tutamacı
                    logging.debug(f"Image Selector Press: Resize handle grabbed: {self.grabbed_handle_type}. Starting resize.")
                    self.resizing_selection = True
                    self.resize_threshold_passed = False # Reset flag
                    self.rotating_selection = False # Diğer modları kapat
                    self.moving_selection = False
                    self.drawing = False
                    self.selecting = False
                    self.resize_start_pos = pos # Dünya koordinatı
                    # Boyutlandırma için orijinal durumları (tüm dict) sakla
                    self.original_resize_states = self._get_current_selection_states(self._parent_page) # DEĞİŞİKLİK: self._parent_page argümanı eklendi
                    self.resize_original_bbox = selected_img_rect # Yakalanan resmin bbox'ı
                    
                    if self.resize_original_bbox.isNull():
                         logging.error("Resize start: Could not get original bbox of selected image.")
                         self.resizing_selection = False # Başlatma
                         return
                         
                    QApplication.setOverrideCursor(selection_helpers.get_resize_cursor(self.grabbed_handle_type))
                    self.update()
                    return # Başka bir işlem yapma
                # --- --- --- --- --- --- --- --- --- --- --- --- -- #

                # --- Tutamaç Yoksa, Resim veya Boş Alan Kontrolü --- #
                # (Mevcut kod: taşıma veya seçim güncelleme)
                clicked_item_info = self._get_item_at(pos)
                is_image_clicked = clicked_item_info and clicked_item_info[0] == 'images'
                # Seçili olan resme mi tıklandı?
                is_selected_image_clicked = clicked_item_info in self.selected_item_indices
                
                logging.debug(f"  No handle grabbed. Item clicked: {clicked_item_info}, Is image: {is_image_clicked}, Is selected image: {is_selected_image_clicked}")

                if is_selected_image_clicked:
                    logging.debug(f"Image Selector Press: Starting move for selected image at {pos}")
                    self.moving_selection = True
                    self.resize_threshold_passed = False # Reset flag
                    self.drawing = False # Diğer modları kapat
                    self.resizing_selection = False
                    self.rotating_selection = False
                    self.selecting = False
                    self.move_start_point = pos # Dünya koordinatı
                    self.last_move_pos = pos
                    # Orijinal durumları kaydet (artık resimleri de destekliyor)
                    self.move_original_states = self._get_current_selection_states(self._parent_page) # DEĞİŞİKLİK: self._parent_page argümanı eklendi (Bu satır zaten doğru olabilir, ama kontrol ettim)
                    QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    logging.debug(f"Image Selector Press: Click on non-selected item or empty space. Calling canvas_handler.handle_canvas_click")
                    self.resize_threshold_passed = False # Reset flag (harmless)
                    from handlers import canvas_handler # Dosya başında import etmek daha iyi
                    canvas_handler.handle_canvas_click(self._parent_page.main_window, # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                                                       self._parent_page.main_window.page_manager, # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                                                       pos, 
                                                       event)
            else:
                logging.error("IMAGE_SELECTOR Press: MainWindow reference could not be obtained.")
        elif self.current_tool == ToolType.PEN:
            self._handle_pen_press(pos, event)
        elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
            self._handle_shape_press(pos)
        elif self.current_tool == ToolType.SELECTOR:
            self._handle_selector_press(pos, event)
        elif self.current_tool == ToolType.ERASER:
            self._handle_eraser_press(pos)
        elif self.current_tool == ToolType.TEMPORARY_POINTER:
            self._handle_temporary_drawing_press(pos)
        # Lazer işaretçi basma olayında bir şey yapmaz
        # self.update() # Buradaki update gereksiz olabilir, handler'lar veya diğer press metodları zaten yapıyor
        # --- --- --- --- --- --- --- --- --- --- --- -- #

    def _handle_tablet_move(self, pos: QPointF, event: QTabletEvent):
        updated = False
        
        if self.current_tool == ToolType.IMAGE_SELECTOR:
            if self.moving_selection:
                 # --- TAŞIMA MANTIĞI --- 
                if not self.last_move_pos.isNull():
                    dx = pos.x() - self.last_move_pos.x()
                    dy = pos.y() - self.last_move_pos.y()
                    if abs(dx) > 1e-6 or abs(dy) > 1e-6: 
                        if self._parent_page and hasattr(self._parent_page, 'images'): # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                            moved_count = 0
                            for item_type, index in self.selected_item_indices:
                                if item_type == 'images' and 0 <= index < len(self._parent_page.images): # DEĞİŞİKLİK: self.parent_page -> self._parent_page
                                    try:
                                        img_data = self._parent_page.images[index]
                                        current_rect = img_data['rect'] 
                                        new_rect = QRectF(current_rect.topLeft() + QPointF(dx, dy), current_rect.size())
                                        img_data['rect'] = new_rect
                                        
                                        # --- YENİ: QGraphicsPixmapItem'ı Güncelle ---
                                        pixmap_item = img_data.get('pixmap_item')
                                        if isinstance(pixmap_item, QGraphicsPixmapItem):
                                            pixmap_item.setPos(new_rect.topLeft())
                                            logging.debug(f"  Moved QGraphicsPixmapItem (uuid: {img_data.get('uuid')}) to {new_rect.topLeft()}")
                                        else:
                                            logging.warning(f"  Could not find/update QGraphicsPixmapItem for image at index {index} during move. pixmap_item: {pixmap_item}")
                                        # --- --- --- --- --- --- --- --- --- ---

                                        moved_count += 1
                                    except Exception as e:
                                        logging.error(f"Image move sırasında hata (images[{index}]): {e}")
                            if moved_count > 0:
                                self.last_move_pos = pos 
                                updated = True
                else:
                    self.last_move_pos = pos 
                 # --- TAŞIMA MANTIĞI SONU ---
            elif self.resizing_selection:
                 # --- Eşik Kontrolü --- 
                if not self.resize_threshold_passed:
                    delta_move = (pos - self.resize_start_pos).manhattanLength()
                    if delta_move > RESIZE_MOVE_THRESHOLD:
                        self.resize_threshold_passed = True
                        logging.debug("Image Resize threshold passed.")
                else:
                     # --- Eşik geçilmiş, boyutlandırma yap --- 
                     # --- >>> DETAYLI LOGLAMA BAŞLANGIÇ <<< ---
                    log_prefix = f"Resize Move (H:{self.grabbed_handle_type}, Thr:Passed): "
                    logging.debug(f"{log_prefix} Current Pos={pos}, Start Pos={self.resize_start_pos}")
                     # --- <<< DETAYLI LOGLAMA BAŞLANGIÇ <<< ---
                    if not self.resize_start_pos.isNull() and self.grabbed_handle_type and not self.resize_original_bbox.isNull() and self.original_resize_states:
                        # --- EKSİK KODU GERİ EKLE --- #
                        original_state = self.original_resize_states[0]
                        original_angle = original_state.get('angle', 0.0)
                        original_center = self.resize_original_bbox.center()
                        original_width = self.resize_original_bbox.width()
                        original_height = self.resize_original_bbox.height()
                        # --- --- --- --- --- --- --- -- #
                        aspect_ratio = original_width / original_height if original_height > 1e-6 else 1.0
                        logging.debug(f"{log_prefix} Orig BBox={self.resize_original_bbox}, Angle={original_angle:.1f}, Ratio={aspect_ratio:.2f}") # Log ekle
                        
                        new_bbox = QRectF()
                        valid_calculation = False

                        if 'middle' in self.grabbed_handle_type:
                            # --- Kenar Ortası TUTAMAÇLARI (YENİ GÖRECELİ YAKLAŞIM) --- #
                            delta = pos - self.resize_start_pos # Başlangıca göre toplam hareket
                            
                            # Resmin kendi eksen vektörleri (normalize edilmemiş)
                            angle_rad = math.radians(original_angle)
                            cos_a = math.cos(angle_rad)
                            sin_a = math.sin(angle_rad)
                            # X ekseni (örneğin sağa doğru) dünya koordinatlarında
                            axis_x_world = QVector2D(cos_a, sin_a) 
                            # Y ekseni (örneğin aşağı doğru) dünya koordinatlarında
                            axis_y_world = QVector2D(-sin_a, cos_a)
                            
                            projected_dx = 0.0
                            projected_dy = 0.0
                            
                            # Hareketi resmin eksenlerine izdüşür
                            if axis_x_world.lengthSquared() > 1e-12:
                                projected_dx = QVector2D.dotProduct(QVector2D(delta), axis_x_world.normalized())
                            if axis_y_world.lengthSquared() > 1e-12:
                                projected_dy = QVector2D.dotProduct(QVector2D(delta), axis_y_world.normalized())

                            new_width = original_width
                            new_height = original_height

                            if self.grabbed_handle_type in ['middle-left', 'middle-right']:
                                # Projected_dx, sağ tutamaç için pozitif, sol için negatif olmalı
                                # Sol tutamaç için delta_x negatif olmalı, genişliği azaltır
                                change_factor = 1.0 if self.grabbed_handle_type == 'middle-right' else -1.0
                                new_width = original_width + (projected_dx * 2.0 * change_factor)
                                if new_width < 1.0: new_width = 1.0 # Minimum boyut
                                new_height = new_width / aspect_ratio if aspect_ratio > 1e-6 else 0
                            elif self.grabbed_handle_type in ['middle-top', 'middle-bottom']:
                                # Projected_dy, alt tutamaç için pozitif, üst için negatif olmalı
                                # Üst tutamaç için delta_y negatif olmalı, yüksekliği azaltır
                                change_factor = 1.0 if self.grabbed_handle_type == 'middle-bottom' else -1.0
                                new_height = original_height + (projected_dy * 2.0 * change_factor)
                                if new_height < 1.0: new_height = 1.0 # Minimum boyut
                                new_width = new_height * aspect_ratio if aspect_ratio > 1e-6 else 0
                                
                            # Yeni bbox'u oluştur (merkez sabit)
                            if new_width >= 1.0 and new_height >= 1.0:
                                new_top_left = QPointF(original_center.x() - new_width / 2.0, original_center.y() - new_height / 2.0)
                                new_bbox = QRectF(new_top_left, QPointF(new_top_left.x() + new_width, new_top_left.y() + new_height))
                                logging.debug(f"{log_prefix} Middle Handle RELATIVE Calc -> New Size=({new_width:.1f},{new_height:.1f}), New BBox={new_bbox}") # Yeni log
                            else:
                                new_bbox = QRectF()
                                logging.debug(f"{log_prefix} Middle Handle RELATIVE Calc -> Invalid size ({new_width:.1f},{new_height:.1f})") # Yeni log
                            # --- --- --- --- --- --- --- --- --- --- --- --- -- #
                            if not new_bbox.isNull(): valid_calculation = True
                        else: 
                            # --- KÖŞE TUTAMAÇLARI (DÖNDÜRÜLMÜŞ - YENİ DOĞRU MANTIK) ---
                            anchor_point = QPointF() # Sabit kalacak köşe (Dünya Koordinatı)
                            rotated_corners = selection_helpers.get_rotated_corners(self.resize_original_bbox, original_angle)
                            if self.grabbed_handle_type == 'top-left': anchor_point = rotated_corners[2] # bottom-right
                            elif self.grabbed_handle_type == 'top-right': anchor_point = rotated_corners[3] # bottom-left
                            elif self.grabbed_handle_type == 'bottom-left': anchor_point = rotated_corners[1] # top-right
                            elif self.grabbed_handle_type == 'bottom-right': anchor_point = rotated_corners[0] # top-left

                            if not anchor_point.isNull():
                                # Vektör: sabit köşeden mevcut pozisyona
                                vec_anchor_to_pos = pos - anchor_point

                                # Orijinal (döndürülmüş) eksenler
                                angle_rad = math.radians(original_angle)
                                cos_a = math.cos(angle_rad)
                                sin_a = math.sin(angle_rad)
                                axis_x = QVector2D(cos_a, sin_a).normalized() # Sağ
                                axis_y = QVector2D(-sin_a, cos_a).normalized() # Aşağı

                                # Vektörü eksenlere izdüşür
                                projected_x = QVector2D.dotProduct(QVector2D(vec_anchor_to_pos), axis_x)
                                projected_y = QVector2D.dotProduct(QVector2D(vec_anchor_to_pos), axis_y)

                                # En boy oranına göre hangi izdüşümün baskın olduğunu bul
                                target_width = 0.0
                                target_height = 0.0
                                if abs(projected_x * aspect_ratio) > abs(projected_y): # X baskın
                                    target_width = abs(projected_x)
                                    target_height = target_width / aspect_ratio if aspect_ratio > 1e-6 else 0
                                else: # Y baskın
                                    target_height = abs(projected_y)
                                    target_width = target_height * aspect_ratio if aspect_ratio > 1e-6 else 0
                                
                                # Yeni merkezi hesapla (anchor ile pos arasında, orantılı)
                                # Yeni bbox'u oluşturmak daha kolay olabilir
                                # Yeni boyutlarla, anchor'a göre yerel koordinatta bbox oluştur
                                local_new_half_w = target_width / 2.0
                                local_new_half_h = target_height / 2.0
                                
                                # Anchor'ın yerel konumu (orijinal bbox'un döndürülmüşü)
                                # Bu hesaplama karmaşık, doğrudan yeni merkezi bulmak daha kolay olabilir.
                                
                                # Yeni yaklaşım: Yeni köşeyi hesapla
                                # İzdüşümleri kullanarak anchor'dan yeni köşe vektörünü oluştur
                                new_corner_vec = projected_x * axis_x + projected_y * axis_y
                                # --- DÜZELTME: QVector2D'yi QPointF'ye çevir --- #
                                new_corner_pos = anchor_point + new_corner_vec.toPointF()
                                
                                # Yeni köşenin ve anchor'ın ortası yeni merkezdir
                                new_center = (anchor_point + new_corner_pos) / 2.0
                                
                                # Yeni bbox'u bu merkez ve boyutlarla oluştur
                                new_top_left = QPointF(new_center.x() - target_width / 2.0, new_center.y() - target_height / 2.0)
                                new_bbox = QRectF(new_top_left, QPointF(new_top_left.x() + target_width, new_top_left.y() + target_height))
                                
                                logging.debug(f"{log_prefix} Corner Handle ROTATED Calc -> New Size=({target_width:.1f},{target_height:.1f}), New Center={new_center}, New BBox={new_bbox}")
                                if not new_bbox.isNull() and new_bbox.isValid() and target_width >= 1 and target_height >= 1:
                                    valid_calculation = True
                                else:
                                    new_bbox = QRectF() # Geçersizse sıfırla
                            else:
                                logging.warning(f"{log_prefix} Anchor point could not be determined.")
                            # --- KÖŞE MANTIĞI SONU (DÖNDÜRÜLMÜŞ) ---

                        # --- Yeni BBox'ı Uygula --- #
                        if valid_calculation and not new_bbox.isNull() and new_bbox.isValid():
                            if self.selected_item_indices and self.selected_item_indices[0][0] == 'images':
                                image_index = self.selected_item_indices[0][1]
                                if self._parent_page and 0 <= image_index < len(self._parent_page.images):
                                    try:
                                        img_data = self._parent_page.images[image_index]
                                        img_data['rect'] = new_bbox
                                        
                                        pixmap_item = img_data.get('pixmap_item')
                                        original_pixmap_for_scaling = img_data.get('original_pixmap_for_scaling')

                                        if isinstance(pixmap_item, QGraphicsPixmapItem) and isinstance(original_pixmap_for_scaling, QPixmap):
                                            if not original_pixmap_for_scaling.isNull() and new_bbox.isValid() and new_bbox.width() > 0 and new_bbox.height() > 0:
                                                # En boy oranını koruyarak yeni pixmap oluştur
                                                final_scaled_pixmap = original_pixmap_for_scaling.scaled(
                                                    new_bbox.size().toSize(), # QSize bekleniyor
                                                    Qt.AspectRatioMode.KeepAspectRatio, # En boy oranını koru
                                                    Qt.TransformationMode.SmoothTransformation
                                                )
                                                
                                                if not final_scaled_pixmap.isNull():
                                                    pixmap_item.setPixmap(final_scaled_pixmap)
                                                    pixmap_item.setPos(new_bbox.topLeft())
                                                    # Döndürme için orijini ve açıyı ayarla
                                                    # Orijinal açı, boyutlandırma başlamadan önceki açıdır.
                                                    current_angle = img_data.get('angle', 0.0) # Mevcut (veya orijinal) açıyı al
                                                    pixmap_item.setTransformOriginPoint(new_bbox.width() / 2, new_bbox.height() / 2)
                                                    pixmap_item.setRotation(current_angle)
                                                    
                                                    logging.debug(f"  Resized QGraphicsPixmapItem (uuid: {img_data.get('uuid')}). New BBox: {new_bbox}, Pixmap W: {final_scaled_pixmap.width()}, H: {final_scaled_pixmap.height()}, Angle: {current_angle}")
                                                else:
                                                    logging.warning(f"  Failed to create final_scaled_pixmap for {img_data.get('uuid')}.")
                                            else:
                                                logging.warning(f"  Cannot resize QGraphicsPixmapItem (uuid: {img_data.get('uuid')}). original_pixmap_for_scaling isNull: {original_pixmap_for_scaling.isNull()}, new_bbox invalid or zero size: {new_bbox}")
                                        else:
                                            logging.warning(f"  Could not find pixmap_item ({type(pixmap_item)}) or original_pixmap_for_scaling ({type(original_pixmap_for_scaling)}) for image UUID {img_data.get('uuid')} during resize.")
                                        # --- --- --- --- --- --- --- --- --- ---
                                        updated = True 
                                    except Exception as e:
                                        logging.error(f"Resize move sırasında hata (images[{image_index}]): {e}", exc_info=True) # exc_info eklendi
                                # (else warnings remain the same)
                        # (else invalid bbox log remains the same)
                        logging.debug(f"{log_prefix} Applying New BBox: {new_bbox}") # Log ekle
                    else: 
                        logging.warning(f"{log_prefix} Başlangıç verileri eksik...") # Log ekle
                 # --- Eşik Kontrolü Sonu ---
            elif self.rotating_selection:
                 # --- Döndürme Mantığı --- #
                if not self.rotation_center_world.isNull() and self.selected_item_indices:
                    # --- DÖNDÜRME HESAPLAMALARINI VE try/except'i GERİ EKLE ---
                    # Sadece ilk seçili resmi döndür (şimdilik)
                    item_type, index = self.selected_item_indices[0]
                    if item_type == 'images' and self._parent_page and 0 <= index < len(self._parent_page.images):
                        # Başlangıç vektörü (merkez -> başlangıç noktası)
                        start_vector = self.rotation_start_pos_world - self.rotation_center_world
                        # Mevcut vektör (merkez -> mevcut nokta)
                        current_vector = pos - self.rotation_center_world
                        
                        # İki vektör arasındaki açıyı hesapla (atan2 kullanarak)
                        angle_start = math.atan2(start_vector.y(), start_vector.x())
                        angle_current = math.atan2(current_vector.y(), current_vector.x())
                        
                        # Açı farkını (delta) derece cinsinden hesapla
                        angle_delta_rad = angle_current - angle_start
                        angle_delta_deg = math.degrees(angle_delta_rad)
                        
                        # Yeni açıyı hesapla (orijinal + delta)
                        new_angle = (self.rotation_original_angle + angle_delta_deg) % 360.0
                        
                        # Canvas'taki resmin açısını doğrudan güncelle
                        try:
                            img_data = self._parent_page.images[index]
                            img_data['angle'] = new_angle
                            
                            pixmap_item = img_data.get('pixmap_item')
                            if isinstance(pixmap_item, QGraphicsPixmapItem):
                                item_rect = img_data.get('rect', QRectF()) # Güncel rect'i al (pozisyon için)
                                if not item_rect.isNull():
                                    pixmap_item.setPos(item_rect.topLeft())
                                    # Döndürme merkezi öğenin kendi (ölçeklenmiş) merkezidir
                                    pixmap_item.setTransformOriginPoint(item_rect.width() / 2, item_rect.height() / 2)
                                    pixmap_item.setRotation(new_angle)
                                    logging.debug(f"  Rotated QGraphicsPixmapItem (uuid: {img_data.get('uuid')}) to {new_angle:.1f} deg. Origin: {pixmap_item.transformOriginPoint()}, Pos: {pixmap_item.pos()}")
                                else:
                                    logging.warning(f"  Cannot set rotation for QGraphicsPixmapItem (uuid: {img_data.get('uuid')}) because rect is null.")
                            else:
                                logging.warning(f"  Could not find pixmap_item for image UUID {img_data.get('uuid')} during rotation.")
                            # --- --- --- --- --- --- --- --- --- ---
                            updated = True
                        except Exception as e:
                            logging.error(f"Rotate move sırasında hata (images[{index}]): {e}", exc_info=True) # exc_info eklendi
                    else:
                         logging.warning("Rotate move: Geçersiz öğe tipi veya index.")
                else:
                    logging.warning("Rotate move: Döndürme merkezi veya seçim bilgisi eksik.")
                 # --- Döndürme Mantığı Sonu --- #
        # --- --- --- --- --- # End of IMAGE_SELECTOR block

        # --- DİĞER TOOL TYPE'LARI --- # 
        # --- DÜZELTME: Girintileri ve Yapıyı Düzelt --- #
        elif self.current_tool == ToolType.PEN:
            if self.drawing or self.temporary_erasing:
                self._handle_pen_move(pos)
                updated = True
        elif self.current_tool == ToolType.SELECTOR:
            if self.moving_selection:
                self._handle_selector_move_selection(pos, event)
                updated = True 
            elif self.resizing_selection:
                if not self.resize_threshold_passed:
                    delta_move = (pos - self.resize_start_pos).manhattanLength()
                    if delta_move > RESIZE_MOVE_THRESHOLD:
                        self.resize_threshold_passed = True
                        logging.debug("Selector Resize threshold passed.")
                else:
                    # Eşik geçilmiş
                    self._handle_selector_resize_move(pos, event)
                updated = True
            elif self.selecting:
                self._handle_selector_rect_select_move(pos, event)
                updated = True
        elif self.current_tool == ToolType.ERASER:
            if self.erasing:
                self._handle_eraser_move(pos)
                updated = True
        elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
            if self.drawing_shape:
                self._handle_shape_move(pos)
                updated = True
        elif self.current_tool == ToolType.TEMPORARY_POINTER:
            if self.temporary_drawing_active:
                self._handle_temporary_drawing_move(pos)
                updated = True
        # --- --- --- --- --- #

        # --- Fonksiyonun sonu: Ekranı güncelle --- #
        if updated:
            self.update()

    def _handle_tablet_release(self, pos: QPointF, event: QTabletEvent):
        # --- IMAGE_SELECTOR için taşıma veya boyutlandırma veya DÖNDÜRME bitişi --- #
        if self.current_tool == ToolType.IMAGE_SELECTOR:
            if self.moving_selection:
                # --- Taşıma Bitiş Kodu --- #
                logging.debug(f"Image Selector Release: Finalizing move at {pos}")
                if not self.move_start_point.isNull() and (pos - self.move_start_point).manhattanLength() > 1e-6:
                    if self.selected_item_indices and self.move_original_states:
                        final_states = self._get_current_selection_states(self._parent_page) # DEĞİŞİKLİK: self._parent_page argümanı eklendi
                        try:
                            indices_copy = copy.deepcopy(self.selected_item_indices)
                            command = MoveItemsCommand(self, indices_copy, self.move_original_states, final_states)
                            if self._parent_page: self._parent_page.get_undo_manager().execute(command)
                            else: logging.error("MoveItemsCommand (images) oluşturuldu ama parent_page yok!")
                        except Exception as e: logging.error(f"MoveItemsCommand (images) oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
                    else: logging.debug("Move release: No items selected or original states missing, no command created.")
                else: logging.debug("Move release: No significant movement detected, no command created.")
                # --- Durum Sıfırlama --- #
                QApplication.restoreOverrideCursor()
                self.moving_selection = False
                self.move_start_point = QPointF()
                self.last_move_pos = QPointF()
                self.move_original_states.clear()
                self.update()
                return # Diğer release mantığına girme
            elif self.resizing_selection:
                # --- Boyutlandırma Bitiş Kodu --- #
                logging.debug(f"Image Selector Release: Finalizing resize at {pos}")
                if self.grabbed_handle_type and self.original_resize_states and not self.resize_original_bbox.isNull():
                    final_states = self._get_current_selection_states(self._parent_page) # DEĞİŞİKLİK: self._parent_page argümanı eklendi
                    final_bbox = self._get_combined_bbox(final_states) # Son bbox'ı state'lerden al
                    
                    # BBox değişti mi kontrol et (küçük farkları tolere et)
                    if not final_bbox.isNull() and (abs((final_bbox.topLeft() - self.resize_original_bbox.topLeft()).manhattanLength()) > 1e-6 \
                       or abs(final_bbox.width() - self.resize_original_bbox.width()) > 1e-6 \
                       or abs(final_bbox.height() - self.resize_original_bbox.height()) > 1e-6):
                        try:
                            indices_copy = copy.deepcopy(self.selected_item_indices)
                            # ResizeItemsCommand'ın resimleri desteklediğini varsayıyoruz
                            command = ResizeItemsCommand(self, indices_copy, # Kopyayı kullan
                                                self.original_resize_states, 
                                                final_states)
                            if self._parent_page: self._parent_page.get_undo_manager().execute(command)
                            else: logging.error("ResizeItemsCommand (images) oluşturuldu ama parent_page yok!")
                        except Exception as e: logging.error(f"ResizeItemsCommand (images) oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
                    else: logging.debug("Resize release: No significant change detected, no command created.")
                else: logging.warning("Resize release: Missing data (handle, original_states, original_bbox).")
                # --- Durum Sıfırlama --- #
                QApplication.restoreOverrideCursor()
                self.resizing_selection = False
                self.grabbed_handle_type = None
                self.original_resize_states.clear()
                self.resize_original_bbox = QRectF()
                self.resize_start_pos = QPointF()
                self.update()
                return # Diğer release mantığına girme
                # --- --- --- --- --- --- -- #
            # --- YENİ: Döndürme Bitişi --- #
            elif self.rotating_selection:
                logging.debug(f"Image Selector Release: Finalizing rotation at {pos}")
                if self.selected_item_indices and len(self.original_resize_states) > 0: # original_resize_states'i açı için kullandık
                    item_type, index = self.selected_item_indices[0]
                    if item_type == 'images' and self._parent_page and 0 <= index < len(self._parent_page.images):
                        final_angle = self._parent_page.images[index].get('angle', self.rotation_original_angle)
                        original_angle = self.original_resize_states[0] # Sakladığımız orijinal açı
                        
                        # Açı değişti mi kontrol et (küçük farkları tolere et)
                        # Derece cinsinden çalıştığımız için 0.1 derece tolerans yeterli olabilir
                        if abs(final_angle - original_angle) > 0.1:
                            try:
                                # RotateItemsCommand'a orijinal ve son açıları ver
                                indices_copy = copy.deepcopy(self.selected_item_indices)
                                command = RotateItemsCommand(self, indices_copy, 
                                                               [original_angle], # Liste olarak ver
                                                               [final_angle])   # Liste olarak ver
                                if self._parent_page: self._parent_page.get_undo_manager().execute(command)
                                else: logging.error("RotateItemsCommand oluşturuldu ama parent_page yok!")
                                logging.debug(f"RotateItemsCommand executed. Original: {original_angle:.1f}, Final: {final_angle:.1f}")
                            except Exception as e:
                                logging.error(f"RotateItemsCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
                        else:
                             logging.debug("Rotate release: No significant angle change detected, no command created.")
                    else:
                        logging.warning("Rotate release: Geçersiz öğe tipi veya index.")
                else:
                    logging.warning("Rotate release: Seçim veya orijinal açı bilgisi eksik.")
                
                # --- Durum Sıfırlama --- #
                QApplication.restoreOverrideCursor()
                self.rotating_selection = False
                self.rotation_original_angle = 0.0
                self.rotation_center_world = QPointF()
                self.rotation_start_pos_world = QPointF()
                self.original_resize_states.clear() # Açı için kullandığımız listeyi temizle
                self.grabbed_handle_type = None # Bunu da sıfırlayalım
                self.update()
                return # Diğer release mantığına girme
            # --- --- --- --- --- --- --- -- #
        # --- --- --- --- --- --- --- --- --- --- --- -- #
            
        # --- Normal Çizim/Şekil/Silgi/Seçim Bitişi --- #
        elif self.drawing or self.erasing or self.moving_selection or self.resizing_selection or self.selecting:
            # --- Aktif araca göre bitirme işlemini yap --- #
            if self.current_tool == ToolType.PEN:
                self._handle_pen_release(pos)
            elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                self._handle_shape_release(pos)
            elif self.current_tool == ToolType.ERASER:
                self._handle_eraser_release(pos)
            elif self.current_tool == ToolType.SELECTOR:
                # --- DÜZELTME: Seçim release mantığını buraya taşı --- #
                if self.moving_selection:
                     self._handle_selector_move_selection_release(pos, event)
                elif self.resizing_selection:
                     self._handle_selector_resize_release(pos, event)
                elif self.selecting: # Dikdörtgen çizerek seçim bitişi
                     self._handle_selector_select_release(pos, event)
                else:
                    # Sadece tıklama (seçimi değiştirme) durumu? Bu press'te handle ediliyor.
                    # Release'de özel bir şey yapmaya gerek yok gibi?
                    logging.debug("Selector Release: No drawing/moving/resizing/selecting active.")
                    # Belki imleci resetlemek gerekir?
                    QApplication.restoreOverrideCursor()
                # --- --- --- --- --- --- --- --- --- --- --- --- --- #
            
            # --- Genel Durum Sıfırlama --- #
            # Not: Bu sıfırlamalar ilgili handle_..._release metodları içinde de yapılabilir.
            # Ama burada toplu yapmak daha garanti olabilir.
            self.drawing = False
            self.drawing_shape = False
            self.moving_selection = False
            self.resizing_selection = False
            self.selecting = False # Selecting flag'ını da sıfırla
            self.erasing = False
            self.temporary_erasing = False # Bunu da sıfırlayalım
            self.grabbed_handle_type = None
            self.current_line_points.clear()
            self.current_eraser_path.clear()
            self.erased_this_stroke.clear()
            self.shape_start_point = QPointF()
            self.shape_end_point = QPointF()
            self.original_resize_states.clear()
            self.move_original_states.clear()
            self.move_start_point = QPointF() # Move state'i de sıfırla
            self.last_move_pos = QPointF()
            self.resize_start_pos = QPointF() # Resize state'i de sıfırla
            self.resize_original_bbox = QRectF()
            # İmleci restore et (eğer özel bir cursor ayarlandıysa)
            # QApplication.restoreOverrideCursor() # Zaten handle_..._release içinde yapılıyor olmalı
            self.update()
            # --- --- --- --- --- --- --- --- --- --- #
            
        # --- Diğer Özel Release Durumları --- #
        elif self.current_tool == ToolType.TEMPORARY_POINTER:
            self._handle_temporary_drawing_release(pos)
        # Lazer release'de bir şey yapmaz.
        # elif self.current_tool == ToolType.SELECTOR: # Bu blok artık gereksiz
        #    self._handle_selector_release(pos, event) # Zaten yukarıda handle edildi

        # --- Genel Durum Sıfırlama (Release sonunda) --- #
        # ... (reset flags and lists)
        self.resize_threshold_passed = False # Bayrağı burada da sıfırla
        self.update()

    def _handle_pen_press(self, pos: QPointF, event: QTabletEvent):
        # logging.debug(f"_handle_pen_press: Tool={self.current_tool.name}, WorldPos={pos}, Button={event.button()}") # LOG EKLE
        right_button_pressed = event.button() == Qt.MouseButton.RightButton

        if right_button_pressed:
            logging.debug("Pen Press with Stylus Button (Right Click mapped): Starting temporary erase.")
            self.temporary_erasing = True
            self.erasing = True
            self.last_move_pos = pos 
            self.current_eraser_path = [pos]
            self.drawing = False
        else:
            logging.debug("Pen Press: Start drawing line.")
            self.drawing = True
            self.temporary_erasing = False
            self.current_line_points = [pos]

    def _handle_pen_move(self, pos: QPointF):
        # logging.debug(f"_handle_pen_move: Drawing={self.drawing}, TempErasing={self.temporary_erasing}, WorldPos={pos}") # LOG EKLE
        if self.temporary_erasing:
            if not self.erasing:
                 logging.warning("Pen Move: temporary_erasing is True but erasing is False!")
                 self.erasing = True
                 self.current_eraser_path = [self.last_move_pos, pos]
            else:
                 self.current_eraser_path.append(pos)
            self.last_move_pos = pos
            self.update()
        elif self.drawing:
            self.current_line_points.append(pos)
            self.update()

    def _handle_pen_release(self, pos: QPointF):
        # logging.debug(f"_handle_pen_release: Drawing={self.drawing}, TempErasing={self.temporary_erasing}, WorldPos={pos}") # LOG EKLE
        # --- GEÇİCİ SİLME KONTROLÜ (Stylus Butonu) --- #
        if self.temporary_erasing and self.current_eraser_path:
            logging.debug("Pen Release with Stylus Button: Finalizing temporary erase.")
            self.temporary_erasing = False
            if self.current_eraser_path:
                 calculated_changes = erasing_helpers.calculate_erase_changes(
                     self.lines, self.shapes, self.current_eraser_path, self.eraser_width
                 )
                 logging.debug(f"Calculated temporary erase changes: {calculated_changes}")
                 if calculated_changes['lines'] or calculated_changes['shapes']:
                     try:
                         command = EraseCommand(self, calculated_changes)
                         self.undo_manager.execute(command)
                         logging.debug(f"Temporary EraseCommand created and executed.")
                     except Exception as e:
                         logging.error(f"Temporary EraseCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
                 else:
                      logging.debug("No effective changes calculated after temporary erase stroke, no command created.")
            self.current_eraser_path = [] # Yolu temizle
            # Not: self.drawing False olmalı, çünkü çizim yapmıyorduk
            self.drawing = False # Güvenlik için False yapalım
            self.current_line_points = [] # Bunu da temizleyelim

        # --- NORMAL ÇİZİM KONTROLÜ --- #
        elif self.drawing and self.current_line_points:
            logging.debug("Pen Release: Finalizing drawing line.")
            if len(self.current_line_points) > 1: # En az 2 nokta varsa çiz
                # --- YENİ: Noktaları manuel kopyala --- #
                final_points = [QPointF(p.x(), p.y()) for p in self.current_line_points]
                # --- --- --- --- --- --- --- --- ---
                line_data = [
                    self.current_color,
                    self.current_pen_width,
                    final_points # Manuel kopyalanmış noktaları kullan
                ]
                command = DrawLineCommand(self, line_data)
                self.undo_manager.execute(command)
                # logging.debug(f"Pen Release: DrawLineCommand executed with {len(final_points)} points.")
            else:
                # logging.debug("Pen Release: Line too short, not added to commands.")
                pass

            self.drawing = False # Çizim bitti
            self.current_line_points = [] # Çizim listesini TEMİZLE
        
        # --- Diğer Durumlar --- #
        else:
             # Ne çizim ne de geçici silme aktifse, logla (beklenmedik durum olabilir)
             if not self.temporary_erasing and not self.drawing:
                  logging.debug("Pen Release: No active drawing or temporary erasing to finalize.")
             elif not self.current_line_points and self.drawing:
                  logging.debug("Pen Release: Drawing was active but no points were recorded.")
             elif not self.current_eraser_path and self.temporary_erasing:
                  logging.debug("Pen Release: Temporary erasing was active but no path was recorded.")
             # Durumları sıfırla (güvenlik önlemi)
             self.drawing = False
             self.temporary_erasing = False
             self.current_line_points = []
             self.current_eraser_path = []

    def _handle_shape_press(self, pos: QPointF):
        self.drawing = True
        self.drawing_shape = True
        self.shape_start_point = pos
        self.shape_end_point = pos
        logging.debug(f"Shape Press: Start drawing {self.current_tool.name}.")

    def _handle_shape_move(self, pos: QPointF):
        self.shape_end_point = pos
        self.update()

    def _handle_shape_release(self, pos: QPointF):
        if self.drawing_shape:
            self.shape_end_point = pos
            logging.debug(f"Shape Release: Finalizing {self.current_tool.name} from {self.shape_start_point} to {self.shape_end_point}")
            
            # Geçerli bir şekil oluştu mu kontrol et (örn. başlangıç ve bitiş farklı)
            # Basit bir kontrol, daha iyisi yapılabilir
            if (self.shape_end_point - self.shape_start_point).manhattanLength() > 2:
                # --- KOMUT OLUŞTURMA ---
                # Derin kopyalarla shape_data oluştur
                shape_data = [
                    self.current_tool, # Enum
                    copy.deepcopy(self.current_color),
                    self.current_pen_width,
                    QPointF(self.shape_start_point), # QPointF kopyası
                    QPointF(self.shape_end_point)   # QPointF kopyası
                ]
                command = DrawShapeCommand(self, shape_data)
                self.undo_manager.execute(command)
                logging.debug(f"Shape Release: DrawShapeCommand executed for {self.current_tool.name}.")
            else:
                logging.debug("Shape Release: Shape too small or invalid, not added to commands.")

            self.drawing_shape = False
            self.shape_start_point = QPointF()
            self.shape_end_point = QPointF()
            self.update() # Geçici şekli temizlemek için
        else:
             logging.debug("Shape Release: drawing_shape was False.")

    def _handle_selector_press(self, pos: QPointF, event: QTabletEvent):
        screen_pos = event.position() # Tablet olayından gelen ekran koordinatları
        
        # --- Tutamaç Kontrolü (Ekran Koordinatları + Tolerans) --- #
        self.grabbed_handle_type = None
        click_tolerance = 5.0 # Daha makul bir tolerans
        click_rect = QRectF(screen_pos.x() - click_tolerance, 
                           screen_pos.y() - click_tolerance, 
                           click_tolerance * 2, 
                           click_tolerance * 2)
                           
        logging.debug(f"Selector Press: Screen Pos = ({screen_pos.x():.1f}, {screen_pos.y():.1f}), World Pos = ({pos.x():.1f}, {pos.y():.1f}), Click Rect = {click_rect}")
        if not self.current_handles:
            logging.debug("Selector Press: self.current_handles is EMPTY.")
        else:
            logging.debug(f"Selector Press: Checking against handles: {self.current_handles}")
            # Döngü içinde loglama:
            for handle_type, handle_rect_screen in self.current_handles.items():
                intersects = handle_rect_screen.intersects(click_rect)
                logging.debug(f"  Checking handle '{handle_type}': rect={handle_rect_screen}, intersects={intersects}")
                if intersects:
                    self.grabbed_handle_type = handle_type
                    logging.debug(f"  >>> Handle grabbed: {self.grabbed_handle_type}")
                    break
            
        # --- Tutamaç Yakalanmadıysa Öğeyi Kontrol Et --- #
        if not self.grabbed_handle_type:
            point_on_selection = self.is_point_on_selection(pos)
            logging.debug(f"Selector Press: No handle grabbed. Checking point on selection (World Pos: {pos.x():.1f}, {pos.y():.1f})... Result: {point_on_selection}")
            if point_on_selection:
                self.moving_selection = True
                self.drawing = False
                self.resizing_selection = False
                self.selecting = False
                # self.drawing_shape = False # Bu satır zaten doğruydu veya etkisizdi, kalsın.
                self.move_start_point = pos
                self.last_move_pos = pos
                # --- DEĞİŞİKLİK: page_ref'i fonksiyona geç --- #
                self.move_original_states = self._get_current_selection_states(self._parent_page)
                # --- --- --- --- --- --- --- --- --- --- --- -- #
                logging.debug(f"Moving selection started, start world pos: {pos}")
                QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
            else:
                # Boş alana tıklandı
                if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    logging.debug("Clearing previous selection.")
                    self.selected_item_indices.clear()
                self.drawing = True
                self.selecting = True
                # self.drawing_shape = True # --- YANLIŞ: Bu satır kaldırıldı ---
                self.resizing_selection = False
                self.moving_selection = False
                self.shape_start_point = pos
                self.shape_end_point = pos
                logging.debug(f"Selection rectangle started world pos: {pos}")
                QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        # --- Tutamaç Yakalandıysa Boyutlandırma Başlat --- #
        else: # self.grabbed_handle_type varsa
            self.resizing_selection = True
            self.drawing = False
            self.moving_selection = False
            self.resize_start_pos = pos # Dünya koordinatı
            
            # --- YENİ DIAGNOSTIC LOG ---
            if self._parent_page:
                logging.debug(f"_handle_selector_press (RESIZE BRANCH): self._parent_page IS Page {self._parent_page.page_number}")
            else:
                logging.error("_handle_selector_press (RESIZE BRANCH): self._parent_page IS NONE HERE!")
            # --- --- --- --- --- --- ---

            # --- DEĞİŞİKLİK: page_ref'i fonksiyona geç --- #
            self.original_resize_states = self._get_current_selection_states(self._parent_page)
            # --- --- --- --- --- --- --- --- --- --- --- -- #

            self.resize_original_bbox = self._get_combined_bbox(self.original_resize_states) # <<< _get_combined_bbox'u self.selected_item_indices ile çağır
            logging.debug(f"Resizing started, handle: {self.grabbed_handle_type}, start world pos: {pos}")
            # --- YENİ: Uzunluk Kontrolü Logu ---
            logging.debug(f"  >>> Length Check @ Press: original_states={len(self.original_resize_states)}, selected_indices={len(self.selected_item_indices)}")
            if len(self.original_resize_states) != len(self.selected_item_indices):
                 logging.error("  >>> MISMATCH DETECTED AT PRESS EVENT!")
            # --- --- --- --- --- --- --- --- ---
            QApplication.setOverrideCursor(geometry_helpers.get_resize_cursor(self.grabbed_handle_type))
            
        self.update()

    def _handle_selector_move_selection(self, pos: QPointF, event: QTabletEvent):
        if not self.move_start_point.isNull():
            dx = pos.x() - self.last_move_pos.x()
            dy = pos.y() - self.last_move_pos.y()
            # --- >>> DEBUG LOGLAMA (Taşıma Sırası) <<< ---
            log_msg = f"Selector Move Selection: World Pos=({pos.x():.1f},{pos.y():.1f}), dx={dx:.2f}, dy={dy:.2f}"
            # İlk seçili öğenin ilk noktasını logla (varsa)
            if self.selected_item_indices:
                item_type, index = self.selected_item_indices[0]
                try:
                    item_list = getattr(self, item_type)
                    if 0 <= index < len(item_list):
                        points = item_list[index][2 if item_type == 'lines' else 3]
                        first_point = points[0] if isinstance(points, list) and points else (points if isinstance(points, QPointF) else None)
                        if first_point: log_msg += f" | Before move: First item's p1=({first_point.x():.1f},{first_point.y():.1f})"
                except Exception:
                    pass # Loglama hatası ana işlemi engellemesin
            logging.debug(log_msg)
            # --- >>> <<< ---
            if dx != 0 or dy != 0:
                geometry_helpers.move_items_by(self.lines, self.shapes, self.selected_item_indices, dx, dy)
                # --- >>> DEBUG LOGLAMA (Taşıma Sonrası) <<< ---
                log_msg_after = "  After move:"
                if self.selected_item_indices:
                    item_type, index = self.selected_item_indices[0]
                    try:
                        item_list = getattr(self, item_type)
                        if 0 <= index < len(item_list):
                            points = item_list[index][2 if item_type == 'lines' else 3]
                            first_point = points[0] if isinstance(points, list) and points else (points if isinstance(points, QPointF) else None)
                            if first_point: log_msg_after += f" First item's p1=({first_point.x():.1f},{first_point.y():.1f})"
                    except Exception:
                        pass
                logging.debug(log_msg_after)
                # --- >>> <<< ---
                self.last_move_pos = pos
                self.update()

    def _handle_selector_rect_select_move(self, pos: QPointF, event: QTabletEvent):
        self.shape_end_point = pos
        self.update()

    def _handle_selector_move_selection_release(self, pos: QPointF, event: QTabletEvent):
        if not self.move_start_point.isNull():
            manhattan_dist = (pos - self.move_start_point).manhattanLength()
            logging.debug(f"Move selection finished. Start: {self.move_start_point}, End: {pos}, Manhattan Distance: {manhattan_dist:.2f}")
            
            # --- YENİ: Komut oluşturmadan önce seçili öğe kontrolü --- #
            if manhattan_dist > 1e-6 and self.selected_item_indices and self.move_original_states:
                 # --- DEĞİŞİKLİK: page_ref'i fonksiyona geç --- #
                 final_states = self._get_current_selection_states(self._parent_page)
                 # --- --- --- --- --- --- --- --- --- --- --- -- #
                 # --- >>> DEBUG LOGLAMA (Orijinal/Final State Özeti) <<< ---
                 orig_state_summary = "N/A"
                 final_state_summary = "N/A"
                 try:
                     if self.move_original_states and self.move_original_states[0]:
                         p_orig = self.move_original_states[0][2][0] if self.move_original_states[0][0] == 'lines' else self.move_original_states[0][3]
                         orig_state_summary = f"({p_orig.x():.1f},{p_orig.y():.1f})"
                     if final_states and final_states[0]:
                         p_final = final_states[0][2][0] if final_states[0][0] == 'lines' else final_states[0][3]
                         final_state_summary = f"({p_final.x():.1f},{p_final.y():.1f})"
                 except Exception:
                     pass
                 logging.debug(f"  Creating MoveItemsCommand: Original state (p1): {orig_state_summary}, Final state (p1): {final_state_summary}")
                 # --- >>> <<< ---
                 try:
                     # --- YENİ: item_indices kopyası oluştur --- #
                     indices_copy = copy.deepcopy(self.selected_item_indices)
                     command = MoveItemsCommand(self, indices_copy,
                                                self.move_original_states, 
                                                final_states) 
                     logging.debug(f"  Attempting undo_manager.execute(MoveItemsCommand) with {len(indices_copy)} items.") # Log'a öğe sayısını ekle
                     self.undo_manager.execute(command)
                     logging.debug("  MoveItemsCommand executed via manager.")
                 except Exception as e:
                     logging.error(f"MoveItemsCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
            elif not self.selected_item_indices:
                 logging.debug("Move selection finished: No items were selected when release occurred.")
            elif not self.move_original_states:
                 logging.debug("Move selection finished: Original states were not recorded.")
            else: 
                 logging.debug("Move selection finished: No significant movement detected or other issue, no command created.")
            
        QApplication.restoreOverrideCursor()
        self.move_start_point = QPointF()
        self.moving_selection = False
        self.move_original_states.clear() 
        self.update()

    def _handle_selector_resize_move(self, pos: QPointF, event: QTabletEvent):
        if not self.resize_start_pos.isNull() and self.grabbed_handle_type and not self.resize_original_bbox.isNull():
            new_bbox = geometry_helpers.calculate_new_bbox(self.resize_original_bbox, self.grabbed_handle_type, pos, self.resize_start_pos)
            
            # --- >>> DEBUG LOGLAMA <<< ---
            logging.debug(f"Selector Resize Move: World Pos=({pos.x():.1f},{pos.y():.1f}), Handle='{self.grabbed_handle_type}', Original BBox={self.resize_original_bbox}, New BBox={new_bbox}")
            # --- >>> <<< ---
            
            if not new_bbox.isNull() and new_bbox.isValid():
                # --- YENİ GÜNCELLEME MANTIĞI (transform_items KULLANMADAN) --- #
                original_center = self.resize_original_bbox.center()
                new_center = new_bbox.center()
                translate_delta = new_center - original_center

                original_width = self.resize_original_bbox.width()
                original_height = self.resize_original_bbox.height()
                new_width = new_bbox.width()
                new_height = new_bbox.height()

                scale_x = new_width / original_width if original_width > 1e-6 else 1.0
                scale_y = new_height / original_height if original_height > 1e-6 else 1.0
                
                # --- YENİ DETAYLI LOGLAMA ---
                logging.debug(f"  Resize Calc: OrigCenter={original_center}, NewCenter={new_center}, Translate={translate_delta}")
                logging.debug(f"  Resize Calc: ScaleX={scale_x:.4f}, ScaleY={scale_y:.4f}")
                # --- --- --- --- --- --- ---

                # Doğrudan canvas öğelerini, orijinal durumdan yola çıkarak güncelle
                if len(self.original_resize_states) != len(self.selected_item_indices):
                     logging.error("Resize Move: original_resize_states ve selected_item_indices uzunlukları farklı!")
                     return
                     
                for i, (item_type, index) in enumerate(self.selected_item_indices):
                    original_item_data = self.original_resize_states[i]
                    if not original_item_data: continue # Orijinal state kaydedilememişse atla
                    
                    try:
                        if item_type == 'lines':
                            if 0 <= index < len(self.lines):
                                original_points = original_item_data[2]
                                transformed_points = []
                                # --- YENİ LOGLAMA (İlk nokta için) ---
                                if original_points:
                                     logging.debug(f"  Line[{index}] Point 0 (Original): {original_points[0]}")
                                # --- --- --- --- --- --- --- --- ---
                                for p_idx, p in enumerate(original_points):
                                    relative_p = p - original_center
                                    scaled_p = QPointF(relative_p.x() * scale_x, relative_p.y() * scale_y)
                                    transformed_p = scaled_p + original_center + translate_delta
                                    transformed_points.append(transformed_p)
                                    # --- YENİ LOGLAMA (Sadece ilk nokta için) ---
                                    if p_idx == 0:
                                        logging.debug(f"    Point 0 (Transformed): {transformed_p}")
                                    # --- --- --- --- --- --- --- --- --- ---
                                self.lines[index][2] = transformed_points # Canvas'taki noktaları güncelle
                            else: logging.warning(f"Resize Move: Geçersiz lines index {index}")
                        elif item_type == 'shapes':
                            if 0 <= index < len(self.shapes):
                                original_p1 = original_item_data[3]
                                original_p2 = original_item_data[4]
                                
                                # --- YENİ LOGLAMA ---
                                logging.debug(f"  Shape[{index}] P1 (Original): {original_p1}, P2 (Original): {original_p2}")
                                # --- --- --- --- --- ---
                                
                                relative_p1 = original_p1 - original_center
                                scaled_p1 = QPointF(relative_p1.x() * scale_x, relative_p1.y() * scale_y)
                                transformed_p1 = scaled_p1 + original_center + translate_delta
                                
                                relative_p2 = original_p2 - original_center
                                scaled_p2 = QPointF(relative_p2.x() * scale_x, relative_p2.y() * scale_y)
                                transformed_p2 = scaled_p2 + original_center + translate_delta
                                
                                # --- YENİ LOGLAMA ---
                                logging.debug(f"    P1 (Transformed): {transformed_p1}, P2 (Transformed): {transformed_p2}")
                                # --- --- --- --- --- ---
                                
                                self.shapes[index][3] = transformed_p1 # Canvas'taki p1'i güncelle
                                self.shapes[index][4] = transformed_p2 # Canvas'taki p2'yi güncelle
                            else: logging.warning(f"Resize Move: Geçersiz shapes index {index}")
                    except Exception as e:
                         logging.error(f"Resize Move sırasında öğe ({item_type}[{index}]) güncellenirken hata: {e}", exc_info=True)
                         
                self.update()

    # YENİ: Boyutlandırma bittiğinde çağrılır
    def _handle_selector_resize_release(self, pos: QPointF, event: QTabletEvent):
        logging.debug(f"Resize selection finished. Handle: {self.grabbed_handle_type}, End World Pos: {pos}")
        
        if self.grabbed_handle_type and self.original_resize_states:
            # --- DEĞİŞİKLİK: page_ref'i fonksiyona geç --- #
            final_states = self._get_current_selection_states(self._parent_page)
            # --- --- --- --- --- --- --- --- --- --- --- -- #
            # Basit bir değişiklik kontrolü: BBox değişti mi?
            final_bbox = self._get_combined_bbox(final_states)
            # Not: final_bbox'u self.selected_item_indices üzerinden hesaplamak daha güvenilir olabilir
            # final_bbox = self._get_combined_bbox(self.selected_item_indices) # Alternatif
            
            # --- DEBUG LOGLAMA ---
            orig_bbox_str = f"({self.resize_original_bbox.x():.1f},{self.resize_original_bbox.y():.1f}, w={self.resize_original_bbox.width():.1f}, h={self.resize_original_bbox.height():.1f})"
            final_bbox_str = f"({final_bbox.x():.1f},{final_bbox.y():.1f}, w={final_bbox.width():.1f}, h={final_bbox.height():.1f})" if not final_bbox.isNull() else "Null"
            logging.debug(f"  Creating ResizeItemsCommand: Original BBox: {orig_bbox_str}, Final BBox: {final_bbox_str}")
            # --- --- --- --- ---

            # BBox'lar farklıysa komutu oluştur
            # Dikkat: Çok küçük değişiklikleri tolere etmek için bir epsilon karşılaştırması daha iyi olabilir.
            if not final_bbox.isNull() and abs((final_bbox.topLeft() - self.resize_original_bbox.topLeft()).manhattanLength()) > 1e-6 \
               or abs(final_bbox.width() - self.resize_original_bbox.width()) > 1e-6 \
               or abs(final_bbox.height() - self.resize_original_bbox.height()) > 1e-6:
                 try:
                     # --- YENİ: item_indices kopyası oluştur --- #
                     indices_copy = copy.deepcopy(self.selected_item_indices)
                     command = ResizeItemsCommand(self, indices_copy, # Kopyayı kullan
                                                self.original_resize_states, 
                                                final_states)
                     logging.debug(f"  Attempting undo_manager.execute(ResizeItemsCommand) with {len(indices_copy)} items.") # Log'a öğe sayısını ekle
                     self.undo_manager.execute(command)
                     logging.debug("  ResizeItemsCommand executed via manager.")
                 except Exception as e:
                     logging.error(f"ResizeItemsCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
            else:
                 logging.debug("Resize selection finished: No significant change detected, no command created.")
        elif not self.grabbed_handle_type:
            logging.warning("Resize release called but no handle was grabbed.")
        elif not self.original_resize_states:
            logging.warning("Resize release called but no original states were recorded.")

        QApplication.restoreOverrideCursor()
        self.resizing_selection = False
        self.grabbed_handle_type = None
        self.original_resize_states.clear()
        self.resize_original_bbox = QRectF()
        self.resize_start_pos = QPointF()
        self.update()

    def _handle_selector_select_release(self, pos: QPointF, event: QTabletEvent):
        self.shape_end_point = pos
        selection_world_rect = QRectF(self.shape_start_point, self.shape_end_point).normalized()
        logging.debug(f"Selection rectangle finished: {selection_world_rect}")
        
        newly_selected = []
        for i, line_data in enumerate(self.lines):
            line_bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
            if not line_bbox.isNull() and selection_world_rect.intersects(line_bbox):
                newly_selected.append(('lines', i))
        for i, shape_data in enumerate(self.shapes):
            shape_bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
            if not shape_bbox.isNull() and selection_world_rect.intersects(shape_bbox):
                 newly_selected.append(('shapes', i))
                 
        shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        
        if shift_pressed:
            for item_type, index in newly_selected:
                if (item_type, index) in self.selected_item_indices:
                    self.selected_item_indices.remove((item_type, index))
                else:
                    self.selected_item_indices.append((item_type, index))
        else:
            self.selected_item_indices = newly_selected
            
        logging.debug(f"Selection updated: {len(self.selected_item_indices)} items selected.")
        QApplication.restoreOverrideCursor()
        self.drawing = False
        self.selecting = False
        self.drawing_shape = False
        self.shape_start_point = QPointF()
        self.shape_end_point = QPointF()
        self.update()

    def _handle_eraser_press(self, pos: QPointF):
        logging.debug("Eraser Press: Start erasing.")
        self.erasing = True
        self.last_move_pos = pos 
        self.current_eraser_path = [pos] 
        self.current_stroke_changes: EraseChanges = {'lines': {}, 'shapes': {}}

    def _handle_eraser_move(self, pos: QPointF):
        if not self.erasing:
            return
        self.current_eraser_path.append(pos)
        self.last_move_pos = pos
        self.update()

    def _handle_eraser_release(self, pos: QPointF):
        logging.debug("Eraser Release: Finish erasing.")
        if not self.erasing:
            return
        self.erasing = False
        self.current_eraser_path.append(pos)

        calculated_changes = erasing_helpers.calculate_erase_changes(
            self.lines, self.shapes, self.current_eraser_path, self.eraser_width
        )
        logging.debug(f"Calculated erase changes: {calculated_changes}")

        self.current_eraser_path = []

        if calculated_changes['lines'] or calculated_changes['shapes']:
            try:
                command = EraseCommand(self, calculated_changes) 
                self.undo_manager.execute(command)
                logging.debug(f"EraseCommand created and executed.")
            except Exception as e:
                logging.error(f"EraseCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
        else:
             logging.debug("No effective changes calculated after erase stroke, no command created.")

        # --- YENİ: Geçici çizim için de durum sıfırlama --- #
        self.temporary_drawing_active = False
        # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def _get_current_selection_states(self, page_ref: Optional['Page']) -> List[Any]:
        """Verilen sayfa referansına göre seçili öğelerin mevcut durumlarını döndürür."""
        states = []
        if not page_ref:
             logging.error("_get_current_selection_states: Fonksiyona geçerli bir 'page_ref' sağlanmadı!")
             return states

        for item_type, index in self.selected_item_indices:
            item_data_source = None
            current_item_state = None
            try:
                if item_type == 'lines':
                    if 0 <= index < len(self.lines):
                        item_data_source = self.lines[index]
                    current_item_state = copy.deepcopy(item_data_source) if item_data_source else None
                elif item_type == 'shapes':
                     if 0 <= index < len(self.shapes):
                        item_data_source = self.shapes[index]
                        current_item_state = copy.deepcopy(item_data_source) if item_data_source else None
                elif item_type == 'images':
                    if hasattr(page_ref, 'images') and isinstance(page_ref.images, list):
                        if 0 <= index < len(page_ref.images):
                            item_data_source = page_ref.images[index]
                            if item_data_source:
                                current_item_state = {}
                                for key, value in item_data_source.items():
                                    if key in ['pixmap', 'original_pixmap_for_scaling'] and isinstance(value, QPixmap):
                                        current_item_state[key] = value.copy() # QPixmap.copy() kullan
                                    elif key == 'pixmap_item' and isinstance(value, QGraphicsPixmapItem):
                                        current_item_state[key] = value # Referansı kopyala (deepcopy sorun yaratabilir)
                                    else:
                                        current_item_state[key] = copy.deepcopy(value)
                            else:
                                logging.warning(f"_get_current_selection_states: images[{index}] için item_data_source None.")
                        else:
                            logging.warning(f"_get_current_selection_states: Geçersiz images index: {index}")
                    else:
                         logging.warning(f"_get_current_selection_states: page_ref.images bulunamadı veya liste değil.")
                else:
                    logging.warning(f"_get_current_selection_states: Bilinmeyen öğe tipi: {item_type}[{index}]")

                states.append(current_item_state)
            except Exception as e:
                logging.error(f"_get_current_selection_states hatası ({item_type}[{index}] için veri alınırken): {e}", exc_info=True)
                states.append(None) # Hata durumunda None ekle
        return states
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    def _get_combined_bbox(self, states: List[Any]) -> QRectF:
        # BU FONKSİYON ARTIK DOĞRUDAN TAM ÖĞE VERİLERİNİ ALACAK (STATE YERİNE)
        combined_bbox = QRectF()
        # Gelen 'states' listesi artık _get_current_selection_states'ten
        # [(item_type, index, full_item_data_copy), ...] formatında gelmeli.
        # VEYA doğrudan self.selected_item_indices kullanarak canvas'tan okuyabilir.
        # Şimdilik ikincisini kullanalım, daha basit.

        for item_type, index in self.selected_item_indices:
            item_data = None
            if item_type == 'lines' and 0 <= index < len(self.lines):
                item_data = self.lines[index]
            elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                item_data = self.shapes[index]
            # --- YENİ: Resimler için _parent_page kontrolü ---
            elif item_type == 'images' and self._parent_page and hasattr(self._parent_page, 'images') and 0 <= index < len(self._parent_page.images):
                 item_data = self._parent_page.images[index] # Burası rect veya angle gibi veriler için
            # --- --- --- --- --- --- --- --- --- --- --- ---

            # --- DÜZELTME: item_data kontrolü ve bounding box alma ---
            bbox = QRectF() # Önce null yap
            if item_data:
                if item_type in ['lines', 'shapes']:
                     bbox = geometry_helpers.get_item_bounding_box(item_data, item_type)
                elif item_type == 'images' and 'rect' in item_data:
                     bbox = item_data['rect'] # Resimler için doğrudan rect'i al
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

            if not bbox.isNull():
                if combined_bbox.isNull():
                    combined_bbox = bbox
                else:
                    combined_bbox = combined_bbox.united(bbox)
            else:
                 # Hata durumunda veya geçersiz öğe durumunda loglama (isteğe bağlı)
                 if item_type != 'images': # Resimler için item_data olmayabilir, loglama yapma
                     logging.warning(f"_get_combined_bbox: Geçersiz öğe referansı veya bbox hesaplanamadı: {item_type}[{index}]")
                 elif item_type == 'images' and not item_data:
                     logging.warning(f"_get_combined_bbox: Geçersiz resim referansı: images[{index}] (parent_page: {self._parent_page is not None})")


        return combined_bbox

    def is_point_on_selection(self, point: QPointF, tolerance: float = 5.0) -> bool:
        logging.debug(f"--- is_point_on_selection checking point {point} ---")
        result = False
        for item_type, index in self.selected_item_indices:
            item_data = None
            if item_type == 'lines' and 0 <= index < len(self.lines):
                item_data = self.lines[index]
            elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                item_data = self.shapes[index]

            if item_data:
                bbox = geometry_helpers.get_item_bounding_box(item_data, item_type)
                logging.debug(f"  Checking item {item_type}[{index}] with bbox {bbox}")
                if bbox.contains(point):
                    # logging.debug("  Point is inside bbox. Performing finer check if line...") # Eski log
                    # --- ÇİZGİ SEGMENT KONTROLÜ KALDIRILDI --- #
                    # Kullanıcının taşımak için tam çizginin üzerine tıklaması gerekmeyebilir.
                    # Bbox içinde olmak yeterli kabul edilsin.
                    # if item_type == 'lines':
                    #     points = item_data[2]
                    #     line_width = item_data[1]
                    #     effective_tolerance = tolerance + line_width / 2.0
                    #     for i in range(len(points) - 1):
                    #         on_segment = geometry_helpers.is_point_on_line(point, points[i], points[i+1], effective_tolerance)
                    #         logging.debug(f"    Segment check {i}-{i+1}: {on_segment}")
                    #         if on_segment:
                    #             result = True
                    #             break
                    # else: # Şekiller için bbox yeterli
                    #     result = True
                    # --- --- --- --- --- --- --- --- --- --- ---
                    result = True # Bbox içindeyse True dön
                    
                    if result:
                         logging.debug(f"  >>> Point IS considered on selected item (bbox check): {item_type}[{index}]")
                         break 
        
        logging.debug(f"--- is_point_on_selection result: {result} ---")
        return result

    def move_selected_items(self, dx: float, dy: float):
        moved = False
        for item_type, index in self.selected_item_indices:
            item_data = None
            if item_type == 'lines' and 0 <= index < len(self.lines):
                item_data = self.lines[index]
            elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                item_data = self.shapes[index]
            if item_data:
                moving_helpers.move_item(item_data, dx, dy)
                moved = True

    def set_tool(self, tool: ToolType):
        """Aktif çizim aracını ayarlar ve ilgili modları sıfırlar."""
        logging.debug(f"Setting tool to: {tool.name}")
        previous_tool = self.current_tool
        self.current_tool = tool

        # Araç değiştiğinde aktif durumları sıfırla
        self.drawing = False
        self.drawing_shape = False
        self.moving_selection = False
        self.resizing_selection = False
        self.selecting = False
        self.erasing = False
        self.temporary_erasing = False
        self.laser_pointer_active = (tool == ToolType.LASER_POINTER) # Lazer durumunu ayarla
        # --- YENİ LOG --- #
        logging.debug(f"  laser_pointer_active set to: {self.laser_pointer_active}")
        # --- --- --- -- #

        # Seçim modundan çıkıldıysa seçimi temizle
        if previous_tool == ToolType.SELECTOR and tool != ToolType.SELECTOR:
             self.selected_item_indices.clear()
             self.current_handles.clear()
             self.update() # Ekranı temizle

        # Silgi moduna girildi veya çıkıldıysa imleci güncelle
        if tool == ToolType.ERASER:
            self.setCursor(Qt.CursorShape.PointingHandCursor) # Veya özel bir silgi cursoru
        elif previous_tool == ToolType.ERASER:
             self.unsetCursor()

        # --- YENİ: Lazer modu için imleç --- #
        if tool == ToolType.LASER_POINTER:
             self.setCursor(Qt.CursorShape.BlankCursor) # İmleci gizle (isteğe bağlı)
        elif previous_tool == ToolType.LASER_POINTER:
             self.unsetCursor()
        # --- --- --- --- --- --- --- --- --- #

        # TODO: Diğer araçlara özel cursorlar eklenebilir (örn. Crosshair)

    def clear_canvas(self):
        command = ClearCanvasCommand(self)
        self.undo_manager.execute(command)

    def set_color(self, color: QColor):
        new_color = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
        if self.current_color != new_color:
            self.current_color = new_color
            logging.debug(f"Çizim rengi ayarlandı: {self.current_color}")

    def set_pen_width(self, width: float):
        new_width = max(1.0, width)
        if self.current_pen_width != new_width:
            self.current_pen_width = new_width
            logging.debug(f"Kalem kalınlığı ayarlandı: {self.current_pen_width}")

    def set_template(self, template_type: TemplateType):
        if isinstance(template_type, TemplateType):
            if self.current_template != template_type:
                self.current_template = template_type
                logging.info(f"Arka plan şablonu değiştirildi: {template_type.name}")
                self.update()
        else:
            logging.warning(f"Geçersiz şablon tipi: {template_type}")

    def set_eraser_width(self, width: float):
        new_width = max(1.0, width)
        if self.eraser_width != new_width:
            self.eraser_width = new_width
            logging.debug(f"Silgi kalınlığı ayarlandı: {self.eraser_width}")
            if self.current_tool == ToolType.ERASER:
                self.update()

    def hoverMoveEvent(self, event):
        pos_screen = event.position()
        # --- YENİ: Lazer İşaretçi Konumunu Güncelle --- #
        if self.laser_pointer_active:
            # --- YENİ LOG --- #
            logging.debug(f"hoverMoveEvent: Updating laser pos to {pos_screen}")
            # --- --- --- -- #
            self.last_cursor_pos_screen = pos_screen
            self.update() # Lazerin yerini güncellemek için ekranı yeniden çiz
        # --- --- --- --- --- --- --- --- --- --- --- -- #

        # --- Silgi Önizlemesi İçin Güncelle --- #
        if self.current_tool == ToolType.ERASER:
            self.update() # Silgi önizlemesinin yerini güncelle
        # --- --- --- --- --- --- --- --- --- #

        # Tooltip gösterme (isteğe bağlı)
        # world_pos = self.screen_to_world(pos_screen)
        # self.setToolTip(f"X: {world_pos.x():.1f}, Y: {world_pos.y():.1f}")
        # print(f"Hover Screen: ({pos_screen.x():.1f}, {pos_screen.y():.1f}), World: ({world_pos.x():.1f}, {world_pos.y():.1f})")

        super().hoverMoveEvent(event)
        
    def leaveEvent(self, event):
        # --- YENİ: Lazer işaretçiyi temizle --- #
        if self.laser_pointer_active:
            self.last_cursor_pos_screen = QPointF() # Konumu sıfırla
            logging.debug("Leave Event: Clearing laser pointer position.")
            self.update() # Ekranı güncelle
        # --- --- --- --- --- --- --- --- --- -- #
        QApplication.restoreOverrideCursor()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
        
    @pyqtSlot(int)
    def update_line_spacing(self, spacing_pt: int):
        logging.debug(f"Anlık çizgi aralığı güncelleniyor: {spacing_pt} pt")
        self.line_spacing_pt = spacing_pt
        self.update()

    @pyqtSlot(int)
    def update_grid_spacing(self, spacing_pt: int):
        logging.debug(f"Anlık ızgara aralığı güncelleniyor: {spacing_pt} pt")
        self.grid_spacing_pt = spacing_pt
        self.update()
        
    @pyqtSlot(tuple)
    def update_line_color(self, color_rgba: tuple):
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            logging.debug(f"Anlık çizgi rengi güncelleniyor: {color_rgba}")
            self.template_line_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık çizgi rengi verisi alındı: {color_rgba}")

    @pyqtSlot(tuple)
    def update_grid_color(self, color_rgba: tuple):
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            logging.debug(f"Anlık ızgara rengi güncelleniyor: {color_rgba}")
            self.template_grid_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık ızgara rengi verisi alındı: {color_rgba}")
        
    def apply_template_settings(self, settings: dict):
        logging.debug(f"Canvas'a yeni şablon ayarları uygulanıyor: {settings}")
        self.template_line_color = settings.get("line_color", self.template_line_color)
        self.template_grid_color = settings.get("grid_color", self.template_grid_color)
        self.line_spacing_pt = settings.get("line_spacing_pt", self.line_spacing_pt)
        self.grid_spacing_pt = settings.get("grid_spacing_pt", self.grid_spacing_pt)
        
        try:
            template_name = settings.get('template_type_name')
            if template_name:
                self.current_template = TemplateType[template_name]
        except KeyError:
             logging.warning(f"Ayarlarda geçersiz template_type_name: '{template_name}', şablon tipi değiştirilmedi.")
        except Exception as e:
            logging.error(f"Şablon tipi güncellenirken hata: {e}")
            
        template_changed = False
        try:
            template_name = settings.get('template_type_name')
            if template_name:
                # Ayarlardan gelen isim büyük/küçük harf duyarlı olabilir, Enum ile eşleştir
                new_template = TemplateType[template_name.upper()] 
                if self.current_template != new_template:
                    self.current_template = new_template
                    template_changed = True
        except KeyError:
             # Eğer settings'de template_type_name yoksa veya geçersizse, hata logla ama çökme
             logging.warning(f"Ayarlarda geçersiz veya eksik template_type_name: '{settings.get('template_type_name')}', şablon tipi değiştirilmedi.")
        except Exception as e:
            logging.error(f"Şablon tipi güncellenirken hata: {e}")
            
        # Eğer şablon tipi değiştiyse, yeni arka planı yükle, aksi takdirde sadece güncelle
        if template_changed:
            logging.debug("Template type changed, reloading background image.")
            self.load_background_template_image() # Arka planı yeniden yükle
        else:
            # Sadece renk/aralık gibi diğer ayarlar değiştiyse update yeterli
            # (load_background_template_image zaten update çağırıyor)
            self.update()
    # --- --- --- --- --- --- --- --- --- ---

    def set_parent_page(self, page: 'Page'):
        """DrawingCanvas'ın ait olduğu Page nesnesini ayarlar."""
        self._parent_page = page
        # --- YENİ: Sayfa değiştikçe zoom/pan bilgilerini de güncelle --- #
        if self._parent_page:
            pass # Zoom ve pan bilgileri artık doğrudan _parent_page üzerinden kullanılacak
                 # Bu yüzden burada özel bir güncelleme gerekmiyor gibi.
                 # Ancak, sayfa değiştiğinde bazı durumları sıfırlamak gerekebilir (örn. seçim).
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # Arka planı yeni sayfanın şablonuna göre güncelle/yeniden yükle
        self.load_background_template_image() 
        self.update()
        logging.debug(f"DrawingCanvas parent_page set to: {page.page_number if page else 'None'}")

    @pyqtSlot(int)
    def update_line_spacing(self, spacing_pt: int):
        """Dialogdan gelen sinyal üzerine çizgi aralığını günceller (anlık)."""
        logging.debug(f"Anlık çizgi aralığı güncelleniyor: {spacing_pt} pt")
        self.line_spacing_pt = spacing_pt
        self.update()

    @pyqtSlot(int)
    def update_grid_spacing(self, spacing_pt: int):
        """Dialogdan gelen sinyal üzerine ızgara aralığını günceller (anlık)."""
        logging.debug(f"Anlık ızgara aralığı güncelleniyor: {spacing_pt} pt")
        self.grid_spacing_pt = spacing_pt
        self.update()
        
    @pyqtSlot(tuple)
    def update_line_color(self, color_rgba: tuple):
        """Dialogdan gelen sinyal üzerine çizgi rengini günceller (anlık)."""
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            logging.debug(f"Anlık çizgi rengi güncelleniyor: {color_rgba}")
            self.template_line_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık çizgi rengi verisi alındı: {color_rgba}")

    @pyqtSlot(tuple)
    def update_grid_color(self, color_rgba: tuple):
        """Dialogdan gelen sinyal üzerine ızgara rengini günceller (anlık)."""
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            logging.debug(f"Anlık ızgara rengi güncelleniyor: {color_rgba}")
            self.template_grid_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık ızgara rengi verisi alındı: {color_rgba}")
        
    def apply_template_settings(self, settings: dict):
        """Verilen ayarlardan tüm şablon parametrelerini günceller."""
        logging.debug(f"Canvas'a yeni şablon ayarları uygulanıyor: {settings}")
        self.template_line_color = settings.get("line_color", self.template_line_color)
        self.template_grid_color = settings.get("grid_color", self.template_grid_color)
        self.line_spacing_pt = settings.get("line_spacing_pt", self.line_spacing_pt)
        self.grid_spacing_pt = settings.get("grid_spacing_pt", self.grid_spacing_pt)
        
        try:
            template_name = settings.get('template_type_name')
            if template_name:
                self.current_template = TemplateType[template_name]
        except KeyError:
             logging.warning(f"Ayarlarda geçersiz template_type_name: '{template_name}', şablon tipi değiştirilmedi.")
        except Exception as e:
            logging.error(f"Şablon tipi güncellenirken hata: {e}")
            
        self.update()
    # --- --- --- --- --- --- --- --- --- ---

    # --- YENİ: Geçici Çizim Handler Metodları --- #
    def _handle_temporary_drawing_press(self, pos: QPointF):
        """Geçici çizim aracı için basma olayını yönetir."""
        self.temporary_drawing_active = True
        # --- YENİ: İlk noktayı da zaman damgası ile ekle --- #
        self.current_temporary_line_points = [(pos, time.time())] 
        # --- --- --- --- --- --- --- --- --- --- --- --- -- #
        logging.debug("Temporary drawing started.")

    def _handle_temporary_drawing_move(self, pos: QPointF):
        """Geçici çizim aracı için hareket olayını yönetir."""
        if self.temporary_drawing_active:
            # --- YENİ: Noktayı zaman damgası ile ekle --- #
            self.current_temporary_line_points.append((pos, time.time()))
            # --- --- --- --- --- --- --- --- --- --- --- -- #
            self.update()

    def _handle_temporary_drawing_release(self, pos: QPointF):
        """Geçici çizim aracı için bırakma olayını yönetir."""
        if self.temporary_drawing_active and len(self.current_temporary_line_points) > 1:
            # --- YENİ: Son noktayı da ekle --- #
            self.current_temporary_line_points.append((pos, time.time()))
            # --- --- --- --- --- --- --- --- --- #
            # Çizgiyi kaydet (artık timestamp eklemeye gerek yok)
            # Ayarlardan renk/kalınlık alınacak
            # --- YENİ: Ayarları kullan --- #
            temp_color = (self.temp_pointer_color.redF(), self.temp_pointer_color.greenF(), 
                          self.temp_pointer_color.blueF(), self.temp_pointer_color.alphaF())
            temp_width = self.temp_pointer_width
            # --- --- --- --- --- --- --- -- #
            # Derin kopya oluştur (nokta listesi için)
            line_copy = copy.deepcopy(self.current_temporary_line_points)
            self.temporary_lines.append((line_copy, temp_color, temp_width))
            logging.debug(f"Temporary line added with {len(line_copy)} points.")
        else:
            logging.debug("Temporary drawing too short, not added.")

        self.temporary_drawing_active = False
        self.current_temporary_line_points = []
        self.update()

    def _check_temporary_lines(self):
        """Zamanlayıcı tarafından çağrılır, süresi dolan geçici ÇİZGİ NOKTALARINI siler."""
        current_time = time.time()
        something_changed = False
        
        # Listenin kopyası üzerinde işlem yapalım veya dikkatlice yönetelim
        new_temporary_lines = []
        
        for points_with_ts, color, width in self.temporary_lines:
            # Süresi dolmayan noktaları filtrele
            valid_points_with_ts = [
                (point, timestamp) for point, timestamp in points_with_ts
                if current_time - timestamp < self.temporary_line_duration
            ]
            
            # Eğer çizgide hala nokta kaldıysa listeye geri ekle
            if valid_points_with_ts:
                new_temporary_lines.append((valid_points_with_ts, color, width))
                # Eğer nokta sayısı azaldıysa değişiklik oldu demektir
                if len(valid_points_with_ts) != len(points_with_ts):
                    something_changed = True
            else:
                 # Çizgide hiç nokta kalmadıysa, tamamen silindi
                 something_changed = True 
                 logging.debug("A temporary line completely expired.")
                 
        # Ana listeyi güncelle
        self.temporary_lines = new_temporary_lines

        # Eğer herhangi bir değişiklik olduysa ekranı güncelle
        if something_changed:
            # logging.debug(f"Checked temporary lines. Remaining lines: {len(self.temporary_lines)}") # Çok sık log olabilir
            self.update()
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

    # --- YENİ: İşaretçi Ayarlarını Uygula --- #
    def apply_pointer_settings(self, settings: dict):
        """Verilen sözlükten işaretçi ayarlarını alır ve uygular."""
        # Lazer ayarları (varsa)
        # Renk QColor'a çevrilmeli
        try:
            laser_color_hex = settings.get('laser_pointer_color')
            if laser_color_hex:
                self.laser_pointer_color = QColor(laser_color_hex)
        except Exception as e:
             logging.warning(f"Geçersiz lazer rengi ayarı ({laser_color_hex}): {e}")
        self.laser_pointer_size = settings.get('laser_pointer_size', self.laser_pointer_size)

        # Geçici çizim ayarları (varsa)
        try:
            temp_color_hex = settings.get('temp_pointer_color')
            if temp_color_hex:
                self.temp_pointer_color = QColor(temp_color_hex)
        except Exception as e:
             logging.warning(f"Geçersiz geçici çizgi rengi ayarı ({temp_color_hex}): {e}")
        self.temp_pointer_width = settings.get('temp_pointer_width', self.temp_pointer_width)
        self.temporary_line_duration = settings.get('temp_pointer_duration', self.temporary_line_duration)
        
        # --- YENİ: Görünüm Faktörlerini Ayarlardan Oku --- #
        # Not: Ayarlar dict'indeki anahtar isimleri ('temp_glow_width_factor' vb.) 
        #      settings dialog ve json dosyasında kullanılanlarla eşleşmeli.
        self.temp_glow_width_factor = settings.get('temp_glow_width_factor', self.temp_glow_width_factor)
        self.temp_core_width_factor = settings.get('temp_core_width_factor', self.temp_core_width_factor)
        self.temp_glow_alpha_factor = settings.get('temp_glow_alpha_factor', self.temp_glow_alpha_factor)
        self.temp_core_alpha_factor = settings.get('temp_core_alpha_factor', self.temp_core_alpha_factor)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
        
        logging.debug(f"Canvas işaretçi ayarları güncellendi. Süre: {self.temporary_line_duration}, Faktörler: GW={self.temp_glow_width_factor:.2f}, CW={self.temp_core_width_factor:.2f}, GA={self.temp_glow_alpha_factor:.2f}, CA={self.temp_core_alpha_factor:.2f}")
        self.update() # Gerekirse görünümü güncelle
    # --- --- --- --- --- --- --- --- --- --- #

    # --- YENİ: Belirli Bir Noktadaki Öğeyi Bulma --- #
    def _get_item_at(self, world_pos: QPointF, tolerance: float = 5.0) -> Tuple[str, int] | None:
        """Verilen dünya koordinatındaki en üstteki öğeyi (varsa) döndürür.
           'lines', 'shapes', 'images' tiplerini kontrol eder.
        """
        logging.debug(f"--- _get_item_at called for World Pos: {world_pos} ---")
        
        # 1. Resimleri Kontrol Et (Sondan başa doğru)
        if self._parent_page and hasattr(self._parent_page, 'images') and self._parent_page.images:
            logging.debug(f"  Checking {len(self._parent_page.images)} images...")
            for i in range(len(self._parent_page.images) - 1, -1, -1):
                img_data = self._parent_page.images[i]
                # --- GÜNCELLEME: Döndürülmüş kontrol --- #
                rect = img_data.get('rect')
                angle = img_data.get('angle', 0.0)
                if rect and isinstance(rect, QRectF):
                    # contains yerine is_point_in_rotated_rect kullan
                    contains = geometry_helpers.is_point_in_rotated_rect(world_pos, rect, angle)
                    logging.debug(f"    Checking image {i} (uuid: {img_data.get('uuid')}) with rect: {rect}, angle: {angle:.1f}. Contains point? {contains}")
                    if contains:
                        logging.debug(f"  >>> Image found at index {i}")
                        return ('images', i)
                # --- --- --- --- --- --- --- --- --- --- #
                else:
                    logging.warning(f"_get_item_at: images[{i}] içinde geçerli 'rect' yok.")

        # 2. Şekilleri Kontrol Et (Sondan başa doğru)
        logging.debug(f"  Checking {len(self.shapes)} shapes...")
        for i in range(len(self.shapes) - 1, -1, -1):
            shape_data = self.shapes[i]
            bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
            contains = bbox.contains(world_pos)
            logging.debug(f"    Checking shape {i} with bbox: {bbox}. Contains point? {contains}")
            if contains:
                 logging.debug(f"  >>> Shape found at index {i}")
                 return ('shapes', i)

        # 3. Çizgileri Kontrol Et (Sondan başa doğru)
        logging.debug(f"  Checking {len(self.lines)} lines...")
        for i in range(len(self.lines) - 1, -1, -1):
            line_data = self.lines[i]
            bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
            contains_bbox = bbox.contains(world_pos)
            logging.debug(f"    Checking line {i} with bbox: {bbox}. Contains point? {contains_bbox}")
            if contains_bbox: # Önce bbox kontrolü
                 points = line_data[2]
                 line_width = line_data[1]
                 effective_tolerance = tolerance + line_width / 2.0
                 for j in range(len(points) - 1):
                     if geometry_helpers.is_point_on_line(world_pos, points[j], points[j+1], effective_tolerance):
                         logging.debug(f"  >>> Line found at index {i} (segment check)")
                         return ('lines', i)
                 logging.debug(f"    Line {i} bbox contains point, but segment check failed.")
        
        logging.debug("--- _get_item_at: No item found. ---")
        return None
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def _get_handle_at(self, screen_pos: QPointF, tolerance: float = 5.0) -> str | None:
        """Verilen ekran koordinatında bir boyutlandırma tutamacı olup olmadığını kontrol eder."""
        click_rect = QRectF(screen_pos.x() - tolerance, 
                           screen_pos.y() - tolerance, 
                           tolerance * 2, 
                           tolerance * 2)
                           
        for handle_type, handle_rect_screen in self.current_handles.items():
            if handle_rect_screen.intersects(click_rect):
                return handle_type
        return None
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def load_background_template_image(self):
        """Sayfanın yönelimine ve seçili şablon türüne göre JPG arka planını yükler."""
        self._background_pixmap = None
        self._current_background_image_path = None

        if self._parent_page is None:
            self.update()
            return

        page_orientation = self._parent_page.orientation
        template_type = self.current_template

        if template_type == TemplateType.PLAIN:
            self._current_background_image_path = None
            self.update()
            return

        orientation_str = "portrait" if page_orientation == Orientation.PORTRAIT else "landscape"
        template_name_str = template_type.name.lower()
        filename = f"{template_name_str}_{orientation_str}_screen.jpg"
        filepath = os.path.join(TEMPLATE_IMAGE_DIR, filename)

        if os.path.exists(filepath):
            try:
                loaded_pixmap = QPixmap(filepath)
                if loaded_pixmap.isNull():
                    logging.error(f"Canvas: Arka plan resmi yüklenemedi (isNull): {filepath}")
                    self._background_pixmap = None
                    self._current_background_image_path = None
                else:
                    self._background_pixmap = loaded_pixmap
                    self._current_background_image_path = filepath
                    logging.info(f"Canvas: Arka plan resmi başarıyla yüklendi: {filepath}")
            except Exception as e:
                logging.error(f"Canvas: Arka plan resmi yüklenirken hata: {filepath} - {e}", exc_info=True)
                self._background_pixmap = None
                self._current_background_image_path = None
        else:
            logging.warning(f"Canvas: Arka plan resmi bulunamadı: {filepath}. Beyaz arka plan kullanılacak.")
            self._background_pixmap = None
            self._current_background_image_path = None
        
        if self._background_pixmap and not self._background_pixmap.isNull():
            self.setMinimumSize(self._background_pixmap.size())
            logging.debug(f"Canvas minimum size set to background size: {self._background_pixmap.size().width()}x{self._background_pixmap.size().height()}")
        else:
            self.setMinimumSize(600, 800)

        self.update()

    def resizeEvent(self, event):
        """Widget yeniden boyutlandırıldığında çağrılır."""
        super().resizeEvent(event)
        logging.info(f"DrawingCanvas yeniden boyutlandırıldı: Genişlik={self.width()}px, Yükseklik={self.height()}px")

    # --- YENİ: is_point_on_selection güncellendi ---
    def is_point_on_selection(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Verilen noktanın seçili öğelerden birinin üzerinde olup olmadığını kontrol eder."""
        logging.debug(f"--- is_point_on_selection checking point {point} ---")
        result = False
        for item_type, index in self.selected_item_indices:
            if item_type == 'images':
                if self._parent_page and 0 <= index < len(self._parent_page.images):
                    img_data = self._parent_page.images[index]
                    rect = img_data.get('rect')
                    angle = img_data.get('angle', 0.0)
                    if rect and isinstance(rect, QRectF):
                        # Döndürülmüş kontrolü kullan
                        if geometry_helpers.is_point_in_rotated_rect(point, rect, angle):
                            logging.debug(f"  >>> Point IS considered on selected item (rotated rect check): {item_type}[{index}]")
                            result = True
                            break # Seçili bir öğe bulunduysa döngüden çık
                else:
                    logging.warning(f"is_point_on_selection: Invalid image index: {index}")
            else: # Çizgi veya Şekil
                item_data = None
                if item_type == 'lines' and 0 <= index < len(self.lines):
                    item_data = self.lines[index]
                elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                    item_data = self.shapes[index]

                if item_data:
                    bbox = geometry_helpers.get_item_bounding_box(item_data, item_type)
                    logging.debug(f"  Checking selected item {item_type}[{index}] with bbox {bbox}")
                    if bbox.contains(point):
                        # Çizgiler için daha hassas kontrol (isteğe bağlı)
                        if item_type == 'lines':
                            points = item_data[2]
                            line_width = item_data[1]
                            effective_tolerance = tolerance + line_width / 2.0 
                            for j in range(len(points) - 1):
                                if geometry_helpers.is_point_on_line(point, points[j], points[j+1], effective_tolerance):
                                    result = True
                                    break
                            if result: break # İç döngüden de çık
                        else: # Şekiller için bbox yeterli
                            result = True 
                            break 
                    if result:
                         logging.debug(f"  >>> Point IS considered on selected item (bbox or line check): {item_type}[{index}]")
                         break # Seçili bir öğe bulunduysa döngüden çık
        
        logging.debug(f"--- is_point_on_selection result: {result} ---")
        return result
    # --- --- --- --- --- --- --- --- --- --- --- --- ---

    # --- YENİ: Resim Öğelerini Page'den Yükle --- #
    def _load_qgraphics_pixmap_items_from_page(self):
        if not self._parent_page or not hasattr(self._parent_page, 'images'):
            # logging.debug("_load_qgraphics_pixmap_items_from_page: Parent page veya images listesi yok.")
            return

        # Mevcut image_items'ı UUID'lerine göre bir haritada sakla (güncellemeler için)
        existing_items_map = {item.data(Qt.ItemDataRole.UserRole): item for item in self.image_items if item.data(Qt.ItemDataRole.UserRole)}
        new_image_items_list = []
        
        items_changed_or_added = False

        for i, img_data in enumerate(self._parent_page.images):
            uuid = img_data.get('uuid')
            loaded_pixmap = img_data.get('pixmap')
            current_rect = img_data.get('rect')
            current_angle = img_data.get('angle', 0.0)
            original_path = img_data.get('path') 

            if not uuid or not loaded_pixmap or loaded_pixmap.isNull() or not current_rect or not current_rect.isValid():
                # logging.debug(f"  Skipping image {i} for item creation: uuid={uuid}, pixmap_isNull={loaded_pixmap.isNull() if loaded_pixmap else 'N/A'}, rect_isNull={current_rect.isNull() if current_rect else 'N/A'}")
                continue

            pixmap_item_in_page_data = img_data.get('pixmap_item')
            existing_item_from_map = existing_items_map.get(uuid)

            current_item_to_process = None

            if pixmap_item_in_page_data and isinstance(pixmap_item_in_page_data, QGraphicsPixmapItem):
                current_item_to_process = pixmap_item_in_page_data
                if uuid not in existing_items_map: # Haritada yoksa, yeni eklenmiş gibi davran
                    items_changed_or_added = True
            elif existing_item_from_map:
                current_item_to_process = existing_item_from_map
                 # Page datada yoksa, canvas'taki item'ı page dataya yazalım.
                if self._parent_page.images[i].get('pixmap_item') is None:
                    self._parent_page.images[i]['pixmap_item'] = current_item_to_process
                    items_changed_or_added = True # Page data güncellendi
            else:
                # Yeni item oluştur
                current_item_to_process = QGraphicsPixmapItem(loaded_pixmap)
                current_item_to_process.setData(Qt.ItemDataRole.UserRole, uuid)
                self._parent_page.images[i]['pixmap_item'] = current_item_to_process
                items_changed_or_added = True
                logging.debug(f"  Created new QGraphicsPixmapItem for UUID: {uuid}")

            # Her zaman orijinal yolu item'da sakla (PDF export için kritik)
            current_item_to_process.setData(Qt.ItemDataRole.UserRole + 1, original_path)
            
            # Pixmap değişmişse güncelle
            if current_item_to_process.pixmap() is not loaded_pixmap or \
               (current_item_to_process.pixmap() and loaded_pixmap and current_item_to_process.pixmap().cacheKey() != loaded_pixmap.cacheKey()):
                current_item_to_process.setPixmap(loaded_pixmap)
                items_changed_or_added = True
                logging.debug(f"  Updated pixmap for QGraphicsPixmapItem UUID: {uuid}")
            
            # Pozisyon, orijin ve döndürmeyi her zaman ayarla
            if current_item_to_process.pos() != current_rect.topLeft():
                current_item_to_process.setPos(current_rect.topLeft())
                items_changed_or_added = True

            # Orijini, pixmap'in kendi merkezi olarak ayarla
            # QGraphicsPixmapItem kendi içinde ölçekleme yapmadığı için, pixmap'in orijinal boyutu kullanılır.
            origin_point = QPointF(loaded_pixmap.width() / 2.0, loaded_pixmap.height() / 2.0)
            if current_item_to_process.transformOriginPoint() != origin_point:
                 current_item_to_process.setTransformOriginPoint(origin_point)
                 items_changed_or_added = True

            if abs(current_item_to_process.rotation() - current_angle) > 1e-4: # Küçük farkları tolere et
                 current_item_to_process.setRotation(current_angle)
                 items_changed_or_added = True
            
            # Resmin gerçek boyutu rect'in boyutuna uymuyorsa, pixmap'i ölçekle ve item'a ata
            # Bu, QPainter'da çizim yapılırken item.pixmap() çağrıldığında doğru boyutta olmasını sağlar.
            # _draw_items QPainter kullandığı için bu önemli.
            # Ancak, AddImageCommand zaten başlangıçta bir rect ve ona uygun bir pixmap veriyor olmalı.
            # Bu kısım daha çok, rect değiştiğinde pixmap'in de yeniden ölçeklenmesi için.
            # QGraphicsPixmapItem kendisi otomatik ölçekleme yapmaz; setPixmap ile verilen pixmap neyse onu kullanır.
            # Eğer _draw_items'da pixmap'i current_rect boyutlarına göre çiziyorsak bu gereksiz olabilir.
            # Mevcut _draw_items item.pixmap()'i doğrudan item.pos()'a çiziyor ve sonra transform uyguluyor.
            # Bu yüzden item.pixmap()'in doğru boyutta olması iyi olur.

            target_size = current_rect.size().toSize()
            if loaded_pixmap.size() != target_size:
                # Orijinal pixmap'i (Page.images[i]['pixmap']) kullanarak ölçekle, item'dakini değil.
                # Bu, tekrar tekrar ölçeklemeden kaynaklanan kalite kaybını önler.
                # Ancak 'original_pixmap_for_scaling' gibi bir şey yoksa, mevcut 'loaded_pixmap'i kullanmak zorundayız.
                # Şimdilik en son yüklenen pixmap'i (loaded_pixmap) kullanalım.
                # AddImageCommand'da 'original_pixmap_for_scaling' eklemiştik. Page.images'da bu olmalı.
                
                original_pixmap_for_scaling = self._parent_page.images[i].get('original_pixmap_for_scaling', loaded_pixmap)
                if original_pixmap_for_scaling.isNull(): 
                    original_pixmap_for_scaling = loaded_pixmap # Fallback

                scaled_pixmap = original_pixmap_for_scaling.scaled(
                    target_size,
                    Qt.AspectRatioMode.IgnoreAspectRatio, # Rect'e tam sığdır
                    Qt.TransformationMode.SmoothTransformation
                )
                if not scaled_pixmap.isNull() and (current_item_to_process.pixmap().isNull() or current_item_to_process.pixmap().cacheKey() != scaled_pixmap.cacheKey()):
                    current_item_to_process.setPixmap(scaled_pixmap)
                    items_changed_or_added = True
                    # logging.debug(f"  Re-scaled pixmap for UUID: {uuid} to size {target_size} for QGraphicsPixmapItem.")

            new_image_items_list.append(current_item_to_process)

        # self.image_items listesini sadece gerçekten bir değişiklik olduysa veya sıralama farklıysa güncelle
        if items_changed_or_added or \
           len(self.image_items) != len(new_image_items_list) or \
           any(self.image_items[j].data(Qt.ItemDataRole.UserRole) != new_image_items_list[j].data(Qt.ItemDataRole.UserRole) for j in range(len(new_image_items_list))):
            self.image_items = new_image_items_list
            logging.debug(f"  _load_qgraphics_pixmap_items_from_page: self.image_items updated. Count: {len(self.image_items)}")
            self.update() # Canvas'ı yeniden çiz
        # else:
            # logging.debug(f"  _load_qgraphics_pixmap_items_from_page: No changes to self.image_items. Count: {len(self.image_items)}")

    # --- --- --- --- --- --- --- --- --- --- --- -- #
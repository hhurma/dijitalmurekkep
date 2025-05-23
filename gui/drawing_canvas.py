import numpy as np
from scipy.interpolate import splev, splprep
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget, QSizePolicy, QApplication
from PyQt6.QtGui import QColor, QTabletEvent, QPainter, QPen, QBrush, QCursor, QPaintEvent, QPainterPath, QRadialGradient, QPixmap, QVector2D, QTransform, QTouchEvent, QEventPoint
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QSize, QEvent
from collections import defaultdict
from OpenGL import GL
import logging
import os 
from PyQt6.QtWidgets import QGraphicsPixmapItem
import copy
from PyQt6.QtCore import pyqtSlot, pyqtSignal
import math
import time
from typing import Optional, Tuple

from utils import drawing_helpers as utils_drawing_helpers # Alias vererek utils'teki helper ile karışmasını önleyelim
from utils import geometry_helpers, erasing_helpers, moving_helpers # YENİ: moving_helpers buraya eklendi
from utils import view_helpers 
from utils.commands import (
    DrawLineCommand, ClearCanvasCommand, DrawShapeCommand, MoveItemsCommand,
    ResizeItemsCommand, EraseCommand, RotateItemsCommand, DrawBsplineCommand, 
    UpdateBsplineControlPointCommand # YENİ: UpdateBsplineControlPointCommand import edildi
)
from utils.undo_redo_manager import UndoRedoManager
from .enums import TemplateType, ToolType, Orientation 
from typing import List, Any
from utils import selection_helpers

# --- YENİ: Tablet Handler Import --- #
from gui import canvas_tablet_handler
# --- --- --- --- --- --- --- --- --- #

# --- YENİ: Çizim Yardımcıları Import --- #
from . import canvas_drawing_helpers # YENİ: Çizim yardımcıları importu
# --- --- --- --- --- --- --- --- --- #

# --- YENİ: DrawingWidget Import --- #
from .widgets.drawing_widget import DrawingWidget
# --- --- --- --- --- --- --- --- --- #

# Sabitler
HANDLE_SIZE = 10
DEFAULT_ERASER_WIDTH = 10.0
TEMPLATE_IMAGE_DIR = "generated_templates"
DEFAULT_TEMPLATE_SETTINGS = {
    "line_color": [0.8, 0.8, 1.0, 0.7],
    "grid_color": [0.9, 0.9, 0.9, 0.8],
    "line_spacing_pt": 28,
    "grid_spacing_pt": 14
}
PT_TO_PX = 96 / 72.0

# --- YENİ: DrawingCanvas için Varsayılan Grid Ayarları ---
CANVAS_DEFAULT_GRID_SETTINGS = {
    "grid_snap_enabled": False,
    "grid_visible_on_snap": True,
    "grid_show_for_line_tool_only": False,
    "grid_apply_to_all_pages": True, # Bu ayar canvas'tan çok dialog/mainwindow ile ilgili ama tutarlılık için burada da olabilir.
    "grid_thick_line_interval": 4,
    "grid_thin_color": (200/255.0, 200/255.0, 220/255.0, 100/255.0), # RGBA float 0-1
    "grid_thick_color": (150/255.0, 150/255.0, 180/255.0, 150/255.0),# RGBA float 0-1
    "grid_thin_width": 1.0,
    "grid_thick_width": 1.5,
}
# --- --- --- --- --- --- --- --- --- --- --- --- --- ---

def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black) 
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

class FakeTabletEventFromTouch:
    """QTouchEvent'i QTabletEvent gibi davranacak bir arayüze dönüştürür."""
    def __init__(self, touch_event: QTouchEvent, primary_touch_point: 'QTouchEvent.TouchPoint'):
        self._touch_event = touch_event
        self._primary_touch_point = primary_touch_point
        self._event_type = self._determine_event_type(primary_touch_point.state())

    def _determine_event_type(self, state: Qt.TouchPointState) -> QTabletEvent.Type:
        if state == Qt.TouchPointState.TouchPointPressed:
            return QTabletEvent.Type.TabletPress
        elif state == Qt.TouchPointState.TouchPointMoved:
            return QTabletEvent.Type.TabletMove
        elif state == Qt.TouchPointState.TouchPointReleased:
            return QTabletEvent.Type.TabletRelease
        return QTabletEvent.Type.TabletMove  # Bilinmeyen durumlar için varsayılan olarak TabletMove

    def type(self) -> QTabletEvent.Type:
        return self._event_type

    def position(self) -> QPointF:
        return self._primary_touch_point.position()

    def globalPosition(self) -> QPointF:
        return self._primary_touch_point.screenPosition()

    def pressure(self) -> float:
        return self._primary_touch_point.pressure()

    def button(self) -> Qt.MouseButton:
        return Qt.MouseButton.LeftButton

    def buttons(self) -> Qt.MouseButton:
        return Qt.MouseButton.LeftButton

    def modifiers(self) -> Qt.KeyboardModifier: # Tip ipucu Qt.KeyboardModifier olarak düzeltildi
        return self._touch_event.modifiers()

    def pointerType(self) -> 'QTabletEvent.PointerType': # Tip ipucu string literali olarak değiştirildi
        return QTabletEvent.PointerType.Pen 

    def deviceType(self) -> 'QTabletEvent.DeviceType': # Tip ipucu string literali olarak değiştirildi
        return QTabletEvent.DeviceType.Stylus

    def uniqueId(self) -> int:
        return self._primary_touch_point.id()

    def x(self) -> int:
        return int(self._primary_touch_point.position().x())

    def y(self) -> int:
        return int(self._primary_touch_point.position().y())
        
    def globalX(self) -> int:
        return int(self.globalPosition().x())

    def globalY(self) -> int:
        return int(self.globalPosition().y())
        
    def accept(self):
        """Olayın kabul edildiğini belirten metot."""
        self._touch_event.accept()
        
    def accept(self):
        """Olayın kabul edildiğini belirten metot."""
        self._touch_event.accept()


class DrawingCanvas(QWidget):
    content_changed = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self, undo_manager: UndoRedoManager, parent=None, template_settings: dict | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.installEventFilter(self)
        # Yakınlaştırma için tablet event takibi
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._parent_page = parent  # EditablePage referansı
        self.scaled_width = None
        self.scaled_height = None
        
        # Undo/Redo Manager
        self.undo_manager = undo_manager

        # YENİ: B-Spline Widget örneği ve veri saklama
        self.b_spline_widget = DrawingWidget() # Örnek oluştur
        self.b_spline_strokes = self.b_spline_widget.strokes # YENİ: Referans olarak ata!

        # Renkler ve Kalem Ayarları
        self.current_color = (0.0, 0.0, 0.0, 1.0)
        self.background_color = (1.0, 1.0, 1.0, 1.0)
        self.line_style = 'solid'
        
        self.current_pen_width = 2.0
        self.eraser_width = 10

        # Metin ayarları
        self.current_text = ""
        self.current_font_family = "Arial"
        self.current_font_size = 12
        self.current_font_bold = False
        self.current_font_italic = False
        self.current_font_underline = False
        self.current_text_edit = None
        
        # Resim dosyası için
        self.current_image = None
        self.restore_cursor_after_stroke = False

        # Çizim veri yapıları
        self.lines = []  # çizgi noktaları 
        self.shapes = []  # şekiller (dikdörtgen, daire vb.)
        self.points = []  # geçici nokta listesi (şu an çizilen)
        
        # Şekil ve seçim değişkenleri
        self.shape_start_point = QPointF()
        self.shape_end_point = QPointF()
        self.drawing = False  # Şu anda çizim yapılıyor mu?
        
        self.current_tool = ToolType.PEN
        self.fill_color = (0.5, 0.5, 0.5, 0.25)  # Gri seviye, %25 opaklık
        
        # Pan ve Zoom ayarları
        self.current_zoom_level = 1.0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)  # Fare takibi
        
        # Seçim ve taşıma değişkenleri
        self.selected_item_indices = []
        self.current_handles = {}
        self.active_handle = None
        self.moving_items = False
        self.moving_start_pos = None
        self.selecting = False
        self.resizing = False
        self.original_positions = []
        self.original_resize_states = []
        
        # Şablon ölçekleri
        self.template_scales = defaultdict(float)
        if template_settings is not None:
            self.template_scales = {int(key): value for key, value in template_settings.get('scales', {}).items()}
            # Template için varsayılan zoom düzeyi
            default_zoom_level = template_settings.get('default_zoom_level')
            if default_zoom_level is not None:
                self.current_zoom_level = default_zoom_level

        # Düzenlenebilir çizgi için değişkenler
        self.bezier_control_points = []
        self.current_editable_line_points = []
        self.active_handle_index = -1
        self.active_bezier_handle_index = -1
        self.is_dragging_bezier_handle = False
        
        # B-Spline ilgili değişkenler
        self.spline_control_points = []  # B-spline kontrol noktaları (scipy formatında)
        self.spline_knots = None  # B-spline düğüm noktaları
        self.spline_degree = None  # B-spline derecesi
        self.spline_u = None  # B-spline parametre değerleri
        
        # Düzenleme modu değişkenleri
        self.current_handles = {}  # Tutamaç noktaları
        self.active_handle = None  # Aktif tutamaç
        self.resizing = False  # Yeniden boyutlandırma
        self.original_resize_states = []  # Boyut değiştirme öncesi durumlar
        
        # Editable Line ve araç değişkenleri
        self.current_tool = ToolType.PEN
        self.bezier_control_points = []  # Bezier kontrol noktaları
        self.current_editable_line_points = []  # Düzenlenebilir çizgi noktaları
        self.active_handle_index = -1  # Aktif tutamaç indeksi
        self.active_bezier_handle_index = -1  # Aktif bezier tutamacı indeksi
        self.is_dragging_bezier_handle = False
        
        # Undo manager ve geri alma redo
        self.undo_manager = UndoRedoManager()
        
        # Çizgi stili
        self.line_style = 'solid'
        
        # Şekil dolgu rengi (gri seviye % 25 opaklık)
        self.fill_color = (0.5, 0.5, 0.5, 0.25)
        
        # Metin değişkenleri
        self.current_text_edit = None
        self.current_text = ""
        self.current_font_family = "Arial"
        self.current_font_size = 12
        self.current_font_bold = False
        self.current_font_italic = False
        self.current_font_underline = False
        
        # Sinyal bağlantıları
        if parent:
            # İçeriği değiştirdiğimizi parent'a bildir
            self.content_changed = QSignal()
            self.content_changed.connect(parent.mark_as_modified)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.installEventFilter(self)
        self.RESIZE_MOVE_THRESHOLD = 3.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)
        
        self.undo_manager = undo_manager
        self._parent_page = parent
        self.shapes = []
        self.lines = []
        # YENİ: Düzenlenebilir çizgiler için ayrı bir depo
        self.editable_lines = []
        self._selected_item_indices = []
        self.current_handles = {}
        self.hovered_handle = None
        self.current_resize_handle = None
        self.drawing = False
        self.drawing_shape = False
        self.moving_selection = False
        self.resizing_selection = False
        self.selecting = False 
        self.erasing = False 
        self.temporary_erasing = False 
        self.laser_pointer_active = False 
        self.temporary_drawing_active = False 
        self.rotating_selection = False 
        self.last_cursor_pos_screen = QPointF() 
        self.select_press_point = None
        
        # Geçici işaretçi (kuyruklu yıldız) için değişkenler
        self.pointer_trail_points = []
        self.pointer_trail_duration = 4.0  # İzlerin ekranda kalma süresi (saniye)
        self.pointer_trail_timer = QTimer(self)
        self.pointer_trail_timer.setInterval(100)  # 100ms'de bir güncelle
        self.pointer_trail_timer.timeout.connect(self._update_pointer_trail)
        self.pointer_trail_timer.start()
        
        # Geçici çizgi değişkenleri
        self.temp_pointer_color = QColor(255, 80, 80, 220)  # Kırmızımsı renk
        self.temp_pointer_width = 3.0  # Çizgi kalınlığı
        self.current_temporary_line_points = []  # Aktif çizim için noktalar
        self.temporary_lines = []  # Tamamlanmış geçici çizgiler [(points, color, width, start_time, expired), ...]
        self.temporary_line_duration = 8.0  # Geçici çizgilerin ekranda kalma süresi (saniye)
        self.temp_glow_width_factor = 3.0  # Glow efekti için genişlik faktörü
        self.temp_core_width_factor = 1.0  # Merkez çizgi için genişlik faktörü
        self.temp_glow_alpha_factor = 0.3  # Glow efekti için saydamlık faktörü
        self.temp_core_alpha_factor = 0.9  # Merkez çizgi için saydamlık faktörü
        
        self.move_start_point = QPointF()
        self.resize_start_pos = QPointF()
        self.rotation_start_pos_world = QPointF() 
        self.rotation_center_world = QPointF() 
        self.grabbed_handle_type: str | None = None
        self.resize_original_bbox = QRectF()
        self.current_line_points: List[QPointF] = []
        self.current_eraser_path: List[QPointF] = [] 
        self.erased_this_stroke: List[Tuple[str, int, Any]] = [] 
        self.shape_start_point = QPointF()
        self.shape_end_point = QPointF()
        self.last_move_pos = QPointF()
        self.original_resize_states: List[Any] = [] 
        self.move_original_states: List[Any] = [] 
        self.current_tool = ToolType.PEN
        self.current_color = (0.0, 0.0, 0.0, 1.0)
        self.current_pen_width = 2.0
        self.eraser_width = DEFAULT_ERASER_WIDTH 
        self.pressure = 1.0
        
        # --- YENİ: Düzenlenebilir Çizgi Aracı Özellikleri --- #
        self.current_editable_line_points = []
        self.active_handle_index = -1
        self.active_bezier_handle_index = -1
        self.is_dragging_bezier_handle = False
        self.bezier_control_points = []  # [p0, c1, c2, p1] formatında kontrol noktaları
        # --- --- --- --- --- --- --- --- --- --- --- --- --- #
        
        # --- YENİ: Kontrol Noktası Seçici Aracı Özellikleri --- #
        self.hovered_node_index = -1  # Fare üzerindeyken vurgulanan ana nokta indeksi
        self.hovered_bezier_handle_index = -1  # Fare üzerindeyken vurgulanan kontrol noktası indeksi
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
        
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.resize_threshold_passed = False 
        self.template_settings = template_settings if template_settings is not None else DEFAULT_TEMPLATE_SETTINGS.copy()
        self.template_line_color = self.template_settings.get("line_color", DEFAULT_TEMPLATE_SETTINGS["line_color"])
        self.template_grid_color = self.template_settings.get("grid_color", DEFAULT_TEMPLATE_SETTINGS["grid_color"])
        self.line_spacing_pt = self.template_settings.get("line_spacing_pt", DEFAULT_TEMPLATE_SETTINGS["line_spacing_pt"])
        self.grid_spacing_pt = self.template_settings.get("grid_spacing_pt", DEFAULT_TEMPLATE_SETTINGS["grid_spacing_pt"])
        try:
             initial_template_name = self.template_settings.get('template_type_name', 'PLAIN')
             self.current_template = TemplateType[initial_template_name]
        except KeyError:
             logging.warning(f"Ayarlarda geçersiz başlangıç şablon tipi: '{initial_template_name}'. PLAIN kullanılıyor.")
             self.current_template = TemplateType.PLAIN
        except Exception as e:
            logging.error(f"Başlangıç şablon tipi okunurken hata: {e}")
        self.temporary_lines: List[Tuple[List[Tuple[QPointF, float]], tuple, float]] = [] 
        self.current_temporary_line_points: List[Tuple[QPointF, float]] = [] 
        self.current_temporary_line_timer = QTimer(self) 
        self.current_temporary_line_timer.timeout.connect(self._check_temporary_lines)
        self.current_temporary_line_timer.start(30)  # Daha akıcı animasyon için 30ms
        self.temporary_line_duration = 5.0 
        self.temp_pointer_color = QColor('#FFA500') 
        self.temp_pointer_width = 3.0 
        self.temp_glow_width_factor: float = 4.0  # Daha geniş glow
        self.temp_core_width_factor: float = 0.5
        self.temp_glow_alpha_factor: float = 0.85  # Daha opak glow
        self.temp_core_alpha_factor: float = 0.9
        self.laser_pointer_color = QColor('#FF0000') 
        self.laser_pointer_size = 10.0 
        self._parent_page: 'Page' | None = None 
        self._background_pixmap: QPixmap | None = None 
        self._page_background_pixmap: QPixmap | None = None
        self._pdf_background_source_path: str | None = None
        self._has_page_background: bool = False
        self._current_background_image_path: str | None = None
        # --- YENİ: Çizgiler grid'e uysun özelliği --- #
        self.snap_lines_to_grid = False
        self.load_background_template_image() 
        logging.info("DrawingCanvas (QWidget) başlatıldı.")
        if self._background_pixmap and not self._background_pixmap.isNull():
            self.setMinimumSize(self._background_pixmap.size())
        else:
            self.setMinimumSize(600, 800) 
        self.update()
        self._last_pinch_dist = None
        self._last_pinch_center = None
        self._pinch_active = False
        self.line_style = 'solid'
        self.current_fill_rgba = (1.0, 1.0, 1.0, 0.0)
        self.fill_enabled = False
        self.image_items = []

        # --- Grid ayarlarını settings'ten başlat --- #
        page_parent = parent 
        main_window_settings = None
        if page_parent and hasattr(page_parent, 'main_window') and page_parent.main_window and hasattr(page_parent.main_window, 'settings'):
            main_window_settings = page_parent.main_window.settings

            # --- YENİ: Eksik grid ayarlarını settings.json'dan tamamla ---
            import json
            import os
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'settings.json')
            config_path = os.path.normpath(config_path)
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_settings = json.load(f)
                for key in CANVAS_DEFAULT_GRID_SETTINGS.keys():
                    if key in file_settings:
                        main_window_settings[key] = file_settings[key]
            except Exception as e:
                logging.warning(f"DrawingCanvas: settings.json dosyasından grid ayarları okunamadı: {e}")
        else:
            self.grid_thick_line_interval = CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_line_interval']
            self.grid_thin_color = CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color']
            self.grid_thick_color = CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color']
            self.grid_thin_width = CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_width']
            self.grid_thick_width = CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_width']
            self.grid_apply_to_all_pages = CANVAS_DEFAULT_GRID_SETTINGS['grid_apply_to_all_pages']
            self.grid_show_for_line_tool_only = CANVAS_DEFAULT_GRID_SETTINGS['grid_show_for_line_tool_only']
            self.snap_lines_to_grid = CANVAS_DEFAULT_GRID_SETTINGS['grid_snap_enabled']
            self.grid_visible_on_snap = CANVAS_DEFAULT_GRID_SETTINGS['grid_visible_on_snap']

        self.pointer_trail_points = []  # (QPointF, timestamp)
        self.pointer_trail_duration = 1.2  # Saniye
        self.pointer_trail_timer = QTimer(self)
        self.pointer_trail_timer.timeout.connect(self._update_pointer_trail)
        self.pointer_trail_timer.start(20)

        # --- YENİ: Kontrol Noktası Seçici Aracı Özellikleri (B-Spline için) --- #
        self.active_bspline_stroke_index: int | None = None
        self.active_bspline_control_index: int | None = None
        self.is_dragging_bspline_handle: bool = False
        self.bspline_drag_start_cp_pos: np.ndarray | None = None # YENİ: Sürükleme başlangıç pozisyonu
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

        # --- YENİ: Düzenlenebilir Çizgi (Eski Bezier) Kontrol Noktası Seçici Aracı Özellikleri --- # 

        # --- CACHE EKLEME --- #
        self._static_content_cache: QPixmap | None = None
        self._cache_dirty: bool = True

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
            # logging.debug(f"  PDF Export - Image Data: path={original_path}, x={sbr.x():.2f}, y={sbr.y():.2f}, w={sbr.width():.2f}, h={sbr.height():.2f}, rot={rotation:.2f}") # Yorum satırı yapıldı
        return export_data

    def paintEvent(self, event: QPaintEvent):
        #logging.info(f"[PAINT] paintEvent çağrıldı. dirty={self._cache_dirty}, cache var mı={self._static_content_cache is not None}")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # --- CACHE KULLANIMI --- #
        cache_needs_update = False
        if self._static_content_cache is None:
            cache_needs_update = True
        else:
            dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
            cache_size = self.size() * dpr
            if (self._static_content_cache.size().width() != int(cache_size.width()) or
                self._static_content_cache.size().height() != int(cache_size.height())):
                cache_needs_update = True
        if self._cache_dirty or cache_needs_update:
            #logging.info(f"[CACHE] paintEvent: Cache güncellenecek. dirty={self._cache_dirty}, cache_needs_update={cache_needs_update}")
            self._update_static_content_cache()
        else:
            #logging.info(f"[CACHE] paintEvent: Cache kullanılacak. dirty={self._cache_dirty}, cache_needs_update={cache_needs_update}")
            pass
        if self._static_content_cache:
            painter.drawPixmap(0, 0, self._static_content_cache)
        # --- SADECE GEÇİCİ/AKTİF ÇİZİMLER --- #
        if self.drawing:
            if self.current_tool == ToolType.PEN:
                if len(self.current_line_points) > 1:
                    utils_drawing_helpers.draw_pen_stroke(
                        painter, self.current_line_points, self.current_color, self.current_pen_width
                    )
            elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                if self.drawing_shape and not self.shape_start_point.isNull() and not self.shape_end_point.isNull():
                    temp_shape_data = [
                        self.current_tool, 
                        self.current_color, 
                        self.current_pen_width,
                        self.shape_start_point, 
                        self.shape_end_point,
                        self.line_style if hasattr(self, 'line_style') else 'solid'
                    ]
                    if self.current_tool in [ToolType.RECTANGLE, ToolType.CIRCLE] and self.fill_enabled:
                        temp_shape_data.append(self.current_fill_rgba) 
                    utils_drawing_helpers.draw_shape(painter, temp_shape_data)
        # --- SADECE OVERLAY VE SEÇİM KUTUSU --- #
        canvas_drawing_helpers.draw_selection_overlay(self, painter)
        canvas_drawing_helpers.draw_selection_rectangle(self, painter)
        # --- GEÇİCİ ÇİZİMLER, SİLGİ ÖNİZLEMESİ vb. --- #
        # ... diğer geçici çizimler ve overlay kodları ...

        # YENİ: B-Spline çizgilerini ve kontrol noktalarını çiz (DrawingWidget'tan alınan mantıkla)
        if self.current_tool == ToolType.EDITABLE_LINE or (self.b_spline_widget and self.b_spline_widget.strokes): # YENİ KOŞUL: b_spline_widget ve onun strokes'ları kontrol ediliyor
            # painter.save() # Gerekirse painter durumunu koru
            
            # DrawingWidget'ın paintEvent'indeki gibi strokes'ları çiz
            # pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin) # ESKİ SABİT PEN
            # painter.setPen(pen) # ESKİ

            # Tamamlanmış B-spline'ları çiz
            # for stroke_data in self.b_spline_strokes: # self.b_spline_widget.strokes yerine canvas'taki kopyayı kullan # ESKİ DÖNGÜ
            if self.b_spline_widget: # b_spline_widget'ın varlığını kontrol et
                for i, stroke_data in enumerate(self.b_spline_widget.strokes): # YENİ DÖNGÜ: enumerate ile index (i) alınıyor
                    control_points_np = stroke_data.get('control_points')
                    knots = stroke_data.get('knots')
                    degree = stroke_data.get('degree')
                    u_params = stroke_data.get('u')
                    
                    if control_points_np is None or knots is None or degree is None or u_params is None:
                        #logging.warning(f"DrawingCanvas paintEvent: B-Spline stroke data missing for a stroke. Skipping.")
                        continue

                    stroke_thickness_from_data = stroke_data.get('thickness')
                    # Kalınlık için widget'ın varsayılanını veya genel bir varsayılanı kullanabiliriz.
                    # Şimdilik widget'ın varsayılanını kullanalım, eğer stroke'ta yoksa.
                    effective_thickness = stroke_thickness_from_data if stroke_thickness_from_data is not None else self.b_spline_widget.default_line_thickness
                    
                    # YENİ: Her stroke için dinamik pen
                    stroke_color_data = stroke_data.get('color', [0.0, 0.0, 0.0, 1.0]) # Varsayılan siyah
                    current_pen_qcolor = rgba_to_qcolor(stroke_color_data) 
                    try:
                        pen = QPen(current_pen_qcolor, float(effective_thickness), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                        painter.setPen(pen)
                    except Exception as e:
                        #logging.error(f"DrawingCanvas paintEvent: Error creating QPen for B-Spline stroke with thickness {effective_thickness}: {e}")
                        default_pen_for_error = QPen(Qt.GlobalColor.magenta, 1) # Hata durumunda farklı renkte çiz
                        painter.setPen(default_pen_for_error)
                    
                    # original_points_with_pressure = stroke_data.get('original_points_with_pressure', [])

                    # tck'yı yeniden oluştur
                    try:
                        # Kontrol noktalarını (2, N) formatına getir
                        # Önce kontrol noktalarının geçerliliğini kontrol edelim
                        if not control_points_np or not isinstance(control_points_np, list) or not all(isinstance(cp, np.ndarray) and cp.shape == (2,) for cp in control_points_np):
                            #logging.error(f"DrawingCanvas paintEvent: Invalid control_points_np for tck creation. Stroke index {i}. Skipping. CP Data: {control_points_np}") # stroke_data'nın indexini logla
                            continue
                        if len(control_points_np) < degree + 1: # k+1 kontrol noktası olmalı (scipy için)
                            #logging.error(f"DrawingCanvas paintEvent: Not enough control points for degree {degree}. Need {degree+1}, got {len(control_points_np)}. Stroke index {i}. Skipping.")
                            continue

                        control_points_for_scipy = np.array(control_points_np).T 
                        tck = (knots, control_points_for_scipy, degree)

                        # YENİ LOGLAR BAŞLANGIÇ (Doğru Konum)
                        #logging.debug(f"DrawingCanvas paintEvent: Stroke {i} - About to call splev.") # i'yi stroke_data'nın indexi olarak kullan
                        #logging.debug(f"  knots (t): shape={knots.shape if hasattr(knots, 'shape') else 'N/A'}, len={len(knots) if knots is not None else 'N/A'}")
                        
                        cp_shape_str = 'N/A'
                        N_cp_str = 'N/A'
                        if hasattr(control_points_for_scipy, 'shape'):
                            cp_shape_str = str(control_points_for_scipy.shape)
                            if len(control_points_for_scipy.shape) == 2: # (ndim, n_control_points)
                                N_cp_str = str(control_points_for_scipy.shape[1])
                        
                        #logging.debug(f"  control_points_for_scipy (c): shape={cp_shape_str}, N_cp={N_cp_str}")
                        #logging.debug(f"  degree (k): {degree}")
                        
                        if u_params is not None and len(u_params) > 0:
                             # u_params'ın son elemanının varlığını ve içeriğini kontrol et
                             if u_params[-1] is not None:
                                 #logging.debug(f"  u_params for splev: min_u={np.min(u_params)}, max_u={np.max(u_params)}, num_eval_points=100, u_last={u_params[-1]}")
                                 pass
                             else:
                                 #logging.error(f"  u_params for splev: u_params[-1] is None. Stroke index {i}. Skipping splev.")
                                 continue # splev'i atla
                        else:
                             #logging.error(f"  u_params for splev: u_params is None or empty. Stroke index {i}. Skipping splev.")
                             continue # splev'i atla
                        # YENİ LOGLAR BİTİŞ

                    except Exception as e:
                        #logging.error(f"DrawingCanvas paintEvent: Error reconstructing tck for B-Spline (Stroke index {i}): {e}. Control Points: {control_points_np}, Knots: {knots}, Degree: {degree}") # stroke_data'nın indexini logla
                        continue


                    # B-spline eğrisini çiz
                    # TODO: Koordinat dönüşümlerini uygula (world_to_screen)
                    # Şu an DrawingWidget kendi koordinatlarında çiziyor, canvas'a uyarlamalıyız.
                    # SciPy'den gelen noktalar doğrudan ekran koordinatı gibi varsayılıyor.
                    # Eğer dünya koordinatlarında saklanıyorsa screen_to_world / world_to_screen dönüşümü gerekir.
                    # Şimdilik event.pos() ile gelen canvas pixel koordinatları kullanıldığını varsayıyoruz.
                    try:
                        x_fine, y_fine = splev(np.linspace(0, u_params[-1], 100), tck)
                        path = QPainterPath()
                        if len(x_fine) > 0:
                            # BURADAKİ world_to_screen KULLANIMI DOĞRU GÖRÜNÜYOR, DrawingWidget'tan gelen noktalar
                            # zaten tabletReleaseEvent içinde dünya koordinatları olarak kabul ediliyor.
                            path.moveTo(self.world_to_screen(QPointF(x_fine[0], y_fine[0]))) 
                            for i in range(1, len(x_fine)):
                                path.lineTo(self.world_to_screen(QPointF(x_fine[i], y_fine[i]))) 
                            painter.drawPath(path)
                    except Exception as e:
                        #logging.error(f"DrawingCanvas paintEvent: Error drawing B-Spline path: {e}")
                        continue

                    # B-Spline kontrol noktalarını çiz (kırmızı)
                    # YENİ KOŞUL: Sadece EDITABLE_LINE_NODE_SELECTOR aracı aktifse kontrol noktalarını çiz
                    if self.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
                        painter.save()
                        painter.setPen(QPen(Qt.GlobalColor.red, 5, Qt.PenStyle.SolidLine))
                        for cp_np in control_points_np:
                            # cp_np bir numpy array [x, y]
                            screen_cp = self.world_to_screen(QPointF(cp_np[0], cp_np[1])) 
                            painter.drawPoint(screen_cp) 
                        painter.restore()

                        # Seçili B-Spline kontrol noktasını farklı çiz (DrawingWidget'ta yok, eklenebilir)
                        # BU BLOK DA AYNI KOŞULA TAŞINACAK
                        # if self.b_spline_widget.selected_control_point is not None: # b_spline_widget kontrolü yukarıda yapıldı
                        if self.b_spline_widget and self.b_spline_widget.selected_control_point is not None:
                            stroke_idx_widget, cp_idx_widget = self.b_spline_widget.selected_control_point
                            # self.b_spline_widget.strokes içindeki index ile eşleşmeli
                            # Bu döngü zaten self.b_spline_widget.strokes üzerinde olduğu için stroke_idx_widget'ı
                            # mevcut stroke ile karşılaştırabiliriz veya doğrudan kullanabiliriz eğer indexler tutarlıysa.
                            # Şimdilik, seçili kontrol noktasının koordinatlarını doğrudan alalım.
                            
                            # Mevcut stroke_data'nın indeksi lazım. enumerate(self.b_spline_widget.strokes) kullanılabilir.
                            # Veya seçili stroke'u bulmak için:
                            current_stroke_index_in_widget_list = -1
                            for idx_w, s_w_data in enumerate(self.b_spline_widget.strokes):
                                if s_w_data is stroke_data: # Referans eşitliği ile kontrol
                                    current_stroke_index_in_widget_list = idx_w
                                    break

                            if stroke_idx_widget == current_stroke_index_in_widget_list and 0 <= cp_idx_widget < len(control_points_np):
                                selected_cp_np = control_points_np[cp_idx_widget] # Doğrudan mevcut stroke'un kontrol noktasını al
                                selected_cp_world = QPointF(selected_cp_np[0], selected_cp_np[1])
                                selected_cp_screen = self.world_to_screen(selected_cp_world) 
                                painter.save()
                                painter.setPen(QPen(Qt.GlobalColor.magenta, 8, Qt.PenStyle.SolidLine))
                                painter.setBrush(Qt.GlobalColor.magenta)
                                painter.drawEllipse(selected_cp_screen, 4, 4) 
                                painter.restore()
                    # YENİ KOŞUL SONU (Kontrol noktası ve seçili nokta çizimi için)

            # Aktif (çizilmekte olan) B-spline stroke'u çiz (DrawingWidget'taki gibi)
            if self.b_spline_widget and len(self.b_spline_widget.current_stroke) > 1: # b_spline_widget kontrolü eklendi
                painter.save()
                for i in range(len(self.b_spline_widget.current_stroke) - 1):
                    point1_world_qpoint, pressure1 = self.b_spline_widget.current_stroke[i]
                    point2_world_qpoint, pressure2 = self.b_spline_widget.current_stroke[i+1]
                    
                    # pointX_world_qpoint QPointF nesneleri (dünya koordinatlarında)
                    point1_screen = self.world_to_screen(point1_world_qpoint) # YENİ: world_to_screen
                    point2_screen = self.world_to_screen(point2_world_qpoint) # YENİ: world_to_screen

                    pen_width = 1 + pressure1 * 9 # Basınca göre kalınlık
                    pen = QPen(Qt.GlobalColor.blue, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(pen)
                    painter.drawLine(point1_screen, point2_screen) # YENİ: screen koordinatlarını kullan
                painter.restore()
            
            # Seçili B-Spline kontrol noktasını farklı çiz (DrawingWidget'ta yok, eklenebilir)
            if self.b_spline_widget.selected_control_point is not None:
                stroke_idx, cp_idx = self.b_spline_widget.selected_control_point
                if 0 <= stroke_idx < len(self.b_spline_widget.strokes):
                    selected_cp_np = self.b_spline_widget.strokes[stroke_idx]['control_points'][cp_idx]
                    selected_cp_world = QPointF(selected_cp_np[0], selected_cp_np[1])
                    selected_cp_screen = self.world_to_screen(selected_cp_world) # YENİ: world_to_screen
                    painter.save()
                    painter.setPen(QPen(Qt.GlobalColor.magenta, 8, Qt.PenStyle.SolidLine))
                    painter.setBrush(Qt.GlobalColor.magenta)
                    painter.drawEllipse(selected_cp_screen, 4, 4) # YENİ: screen koordinatlarını kullan
                    painter.restore()
            # YENİ KOŞUL SONU (Kontrol noktası çizimi için)
            
            # painter.restore() # Eğer başta save yapıldıysa

        # Geçici işaretçi izini çiz
        if self.current_tool == ToolType.TEMPORARY_POINTER and self.pointer_trail_points:
            # Dış Halo (en geniş kısım)
            path = QPainterPath()
            path.moveTo(self.pointer_trail_points[0][0])
            for p, _ in self.pointer_trail_points[1:]:
                path.lineTo(p)
            glow_pen = QPen(QColor(255, 80, 0, 40), 25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(path)
            
            # Orta katman (ana parlaklık)
            path = QPainterPath()
            path.moveTo(self.pointer_trail_points[0][0])
            for p, _ in self.pointer_trail_points[1:]:
                path.lineTo(p)
            mid_pen = QPen(QColor(255, 160, 30, 90), 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(mid_pen)
            painter.drawPath(path)
            
            # İç çekirdek (en parlak kısım)
            path = QPainterPath()
            path.moveTo(self.pointer_trail_points[0][0])
            for p, _ in self.pointer_trail_points[1:]:
                path.lineTo(p)
            core_pen = QPen(QColor(255, 255, 180, 200), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(core_pen)
            painter.drawPath(path)

        # --- YENİ: Lazer İşaretçiyi Çiz (Ekran Koordinatlarında) --- #
        if self.laser_pointer_active and not self.last_cursor_pos_screen.isNull():
             painter.save()
             painter.setRenderHint(QPainter.RenderHint.Antialiasing)
             painter.setPen(Qt.PenStyle.NoPen)

             center_pos = self.last_cursor_pos_screen
             base_size = self.laser_pointer_size
             radius = base_size * 0.8 # Glow efekti için yarıçapı biraz artıralım
             
             # Radyal gradyan oluştur
             gradient = QRadialGradient(center_pos, radius)
             
             # Merkez renk (daha opak)
             center_color = QColor(self.laser_pointer_color)
             center_color.setAlpha(220) 
             gradient.setColorAt(0.0, center_color)

             # Orta renk (yarı saydam)
             mid_color = QColor(self.laser_pointer_color)
             mid_color.setAlpha(100) 
             gradient.setColorAt(0.4, mid_color)
             
             # Dış renk (tamamen saydam)
             outer_color = QColor(self.laser_pointer_color)
             outer_color.setAlpha(0)
             gradient.setColorAt(1.0, outer_color)

             painter.setBrush(QBrush(gradient))
             painter.drawEllipse(center_pos, radius, radius)
             painter.restore()
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #
        
        # --- YENİ: Geçici Çizgileri Çiz (tamamlanmış izler) --- #
        if hasattr(self, 'temporary_lines') and self.temporary_lines:
            for points, color_tuple, width, start_time, animating in self.temporary_lines:
                if len(points) > 1:
                    # Önce dış parlama çizgisi (glow efekti)
                    path = QPainterPath()
                    path.moveTo(points[0][0])
                    for p, _ in points[1:]:
                        path.lineTo(p)
                    
                    # Dış glow - daha kalın ve yarı saydam
                    glow_width = width * 5.0  # Daha geniş glow efekti
                    glow_color = QColor()
                    glow_color.setRgbF(color_tuple[0], color_tuple[1], color_tuple[2], color_tuple[3] * 0.5)
                    glow_pen = QPen(glow_color, glow_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(glow_pen)
                    painter.drawPath(path)
                    
                    # Orta katman - parlak
                    path = QPainterPath()
                    path.moveTo(points[0][0])
                    for p, _ in points[1:]:
                        path.lineTo(p)
                    mid_width = width * 2.0
                    mid_color = QColor()
                    mid_color.setRgbF(1.0, 0.9, 0.5, 0.7)  # Sarımsı parlak
                    mid_pen = QPen(mid_color, mid_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(mid_pen)
                    painter.drawPath(path)
                    
                    # İç çekirdek çizgi - ince ve beyaz
                    path = QPainterPath()
                    path.moveTo(points[0][0])
                    for p, _ in points[1:]:
                        path.lineTo(p)
                    core_width = width * 0.8
                    core_color = QColor(255, 255, 255, 220)  # Beyaz ve opak
                    core_pen = QPen(core_color, core_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    painter.setPen(core_pen)
                    painter.drawPath(path)
        
        # Aktif geçici çizimi çiz
        if self.current_tool == ToolType.TEMPORARY_POINTER and self.temporary_drawing_active and len(self.current_temporary_line_points) > 1:
            # Dış glow (en geniş parçalı halo efekti)
            path = QPainterPath()
            path.moveTo(self.current_temporary_line_points[0][0])
            for p, _ in self.current_temporary_line_points[1:]:
                path.lineTo(p)
            glow_width = self.temp_pointer_width * 8.0  # Daha geniş dış halo
            glow_color = QColor(255, 100, 30, 80)  # Turuncu çok hafif saydam
            glow_pen = QPen(glow_color, glow_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(path)
            
            # Orta katman (ana parlaklık)
            path = QPainterPath()
            path.moveTo(self.current_temporary_line_points[0][0])
            for p, _ in self.current_temporary_line_points[1:]:
                path.lineTo(p)
            mid_width = self.temp_pointer_width * 4.0  # Daha kalın orta katman
            mid_color = QColor(255, 180, 50, 150)  # Altın sarısı, yarı saydam
            mid_pen = QPen(mid_color, mid_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(mid_pen)
            painter.drawPath(path)
            
            # İç çekirdek (en parlak kısım)
            path = QPainterPath()
            path.moveTo(self.current_temporary_line_points[0][0])
            for p, _ in self.current_temporary_line_points[1:]:
                path.lineTo(p)
            core_width = self.temp_pointer_width * 1.5  # Daha kalın çekirdek
            core_color = QColor(255, 255, 255, 250)  # Neredeyse opak beyaz
            core_pen = QPen(core_color, core_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(core_pen)
            painter.drawPath(path)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

        # Seçim overlayı
        canvas_drawing_helpers.draw_selection_overlay(self, painter)
        
        # Seçim dikdörtgeni çiz
        canvas_drawing_helpers.draw_selection_rectangle(self, painter)

        # --- Silgi Önizlemesi --- #
        if self.current_tool == ToolType.ERASER and self.underMouse(): # Sadece fare canvas üzerindeyken çiz
            last_pos_screen_qpoint = self.mapFromGlobal(QCursor.pos()) # Global fare pozisyonunu widget koordinatlarına çevir (QPoint döndürür)
            if self.rect().contains(last_pos_screen_qpoint): # Widget sınırları içindeyse
                painter.save()
                eraser_radius = self.eraser_width / 2.0 # Bu float
                
                # QPoint'i QPointF'ye dönüştür
                last_pos_screen_qpointf = QPointF(last_pos_screen_qpoint)
                
                # Silgi önizlemesi için renk ve fırça
                preview_color = QColor(128, 128, 128, 100) # Yarı şeffaf gri
                painter.setBrush(QBrush(preview_color))
                painter.setPen(Qt.PenStyle.NoPen) # Kenarlık olmasın
                
                # Daire şeklinde önizleme çiz (QPointF merkez ve float yarıçaplarla)
                painter.drawEllipse(last_pos_screen_qpointf, eraser_radius, eraser_radius)
                painter.restore()
        # --- --- --- --- --- -- #
        painter.end()

    def screen_to_world(self, screen_pos: QPointF) -> QPointF:
        if self._parent_page:
            zoom = self._parent_page.zoom_level
            pan_offset = self._parent_page.pan_offset
            if zoom > 1e-6: # Sıfıra bölme hatasını önle
                # Önce pan ofsetini ekleyerek (0,0) noktasının ekran konumuna göre düzelt
                # Sonra zoom ile ölçekle
                # DÜZELTME: Önce zoom ile ölçekle, sonra pan ofsetini ekle
                world_x = (screen_pos.x() / zoom) + pan_offset.x()
                world_y = (screen_pos.y() / zoom) + pan_offset.y()
                return QPointF(world_x, world_y)
            else:
                # Zoom çok küçükse veya sıfırsa, varsayılan bir değer döndür veya hata ver
                logging.warning("screen_to_world: Zoom level is too small or zero.")
                return screen_pos # Veya QPointF(0,0) ?
        else:
            # parent_page yoksa 1:1 dönüşüm yap
            return screen_pos

    def world_to_screen(self, world_pos: QPointF) -> QPointF:
        if self._parent_page:
            zoom = self._parent_page.zoom_level
            pan_offset = self._parent_page.pan_offset
            # Önce pan ofsetini çıkar, sonra zoom ile çarp
            screen_x = (world_pos.x() - pan_offset.x()) * zoom
            screen_y = (world_pos.y() - pan_offset.y()) * zoom
            return QPointF(screen_x, screen_y)
        else:
            # parent_page yoksa 1:1 dönüşüm yap
            return world_pos
         
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
        # logging.debug(f"Canvas Tablet Event: {event.type()}, Pos: {event.position()}, GlobalPos: {event.globalPosition()}, Pressure: {event.pressure()}, Button: {event.button()}, Buttons: {event.buttons()}, Device: {event.deviceType().name}, Pointer: {event.pointerType().name}, UniqueID: {event.uniqueId()}")
        # Dokunmatik ekran olaylarını ve fare olaylarını tablet olaylarına dönüştür
        # self._handle_tablet_event_common(event)
        # logging.debug(f"[DrawingCanvas ({id(self)})] tabletEvent: {event.type()}, tool: {self.current_tool}")
        # logging.debug(f"  b_spline_widget ID: {id(self.b_spline_widget)}, b_spline_strokes ID (before widget call): {id(self.b_spline_strokes)}")
        # logging.debug(f"  Strokes in widget (before call, len={len(self.b_spline_widget.strokes)}): {self.b_spline_widget.strokes}")
        # logging.debug(f"  Strokes in canvas (before call, len={len(self.b_spline_strokes)}): {self.b_spline_strokes}")

        # self._update_projection() # Pan/zoom değişikliklerini uygula
        world_pos = self.screen_to_world(event.position())
        event_type = event.type()

        # --- YENİ: Olayı doğrudan canvas_tablet_handler'a yönlendir ---
        # Önce, hangi araç tipinin hangi handler'ı kullanacağını belirleyelim.
        
        # --- Özel durum: EDITABLE_LINE ---
        # Bu araç, kendi widget'ı (b_spline_widget) üzerinden yönetiliyor.
        # Komut oluşturma vb. DrawingCanvas'ta kalmalı.
        if self.current_tool == ToolType.EDITABLE_LINE:
            # Olayları b_spline_widget'a yönlendir (yeni stroke çizimi için)
            if self.b_spline_widget:
                if event_type == QTabletEvent.Type.TabletPress:
                    self.b_spline_widget.tabletPressEvent(world_pos, event)
                    # logging.debug("[EDITABLE_LINE] TabletPress forwarded to b_spline_widget.")
                elif event_type == QTabletEvent.Type.TabletMove:
                    self.b_spline_widget.tabletMoveEvent(world_pos, event)
                    # logging.debug("[EDITABLE_LINE] TabletMove forwarded to b_spline_widget.")
                elif event_type == QTabletEvent.Type.TabletRelease:
                    # logging.debug("[EDITABLE_LINE] TabletRelease: Calling b_spline_widget.tabletReleaseEvent...")
                    # strokes_before_release = len(self.b_spline_strokes) # widget.strokes ile aynı
                    
                    # YENİ: tabletReleaseEvent artık stroke_data döndürüyor
                    created_stroke_data = self.b_spline_widget.tabletReleaseEvent(world_pos, event)
                    # logging.debug(f"[EDITABLE_LINE] TabletRelease: b_spline_widget.tabletReleaseEvent returned: {type(created_stroke_data)}")
                    # if isinstance(created_stroke_data, dict):
                    #     logging.debug(f"  Returned stroke data keys: {list(created_stroke_data.keys())}")

                    # strokes_after_release = len(self.b_spline_strokes) # Bu artık anlamlı değil, widget listeyi değiştirmiyor
                    
                    # YENİ: Eğer widget geçerli bir stroke oluşturduysa komut oluştur
                    if created_stroke_data:
                        # logging.debug(f"[EDITABLE_LINE] TabletRelease: Valid stroke data received from widget. Creating DrawBsplineCommand.")
                        # new_stroke_data_ref = self.b_spline_strokes[added_stroke_index_by_widget] # ESKİ
                        command = DrawBsplineCommand(self, created_stroke_data) # YENİ: stroke_index yok
                        self.undo_manager.execute(command)
                        # logging.debug(f"[EDITABLE_LINE] TabletRelease: DrawBsplineCommand executed. Canvas strokes len: {len(self.b_spline_strokes)}")
                        if self._parent_page:
                            self._parent_page.mark_as_modified() # YENİ: Sayfayı değiştirildi olarak işaretle
                    else:
                        # logging.debug("[EDITABLE_LINE] TabletRelease: No valid stroke data returned from widget. No command created.")
                        pass
                    
                    # logging.debug(f"Strokes in widget (after release, len={len(self.b_spline_widget.strokes)}): {self.b_spline_widget.strokes}")
                    # logging.debug(f"Strokes in canvas (after release, len={len(self.b_spline_strokes)}): {self.b_spline_strokes}")
            else:
                # logging.warning("[EDITABLE_LINE] b_spline_widget is None!")
                pass
            self.update()
            return # EDITABLE_LINE için canvas_tablet_handler'a gitme
            
        # --- Özel durum: EDITABLE_LINE_NODE_SELECTOR ---
        # NODE_SELECTOR aracı da b_spline_widget içindeki seç-taşı fonksiyonlarını kullanır
        elif self.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
            if self.b_spline_widget:
                if event_type == QTabletEvent.Type.TabletPress:
                    # Kontrol noktasını seçmeyi dene
                    selected = self.b_spline_widget.select_control_point(world_pos, tolerance=10.0)
                    if selected:
                        logging.debug(f"[EDITABLE_LINE_NODE_SELECTOR] Kontrol noktası seçildi.")
                    self.update()
                elif event_type == QTabletEvent.Type.TabletMove:
                    # Eğer bir kontrol noktası seçiliyse, taşı
                    if self.b_spline_widget.selected_control_point is not None:
                        self.b_spline_widget.move_control_point(world_pos)
                        self.update()
                elif event_type == QTabletEvent.Type.TabletRelease:
                    # Kontrol noktası taşımayı tamamla
                    if self.b_spline_widget.selected_control_point is not None:
                        # release_control_point'ten 4 değer dönüyor: stroke_idx, cp_idx, old_pos, new_pos
                        stroke_idx, cp_idx, old_pos, new_pos = self.b_spline_widget.release_control_point()
                        if stroke_idx is not None:
                            # Komutu oluştur ve uygula
                            command = UpdateBsplineControlPointCommand(self, stroke_idx, cp_idx, old_pos, new_pos)
                            self.undo_manager.execute(command)
                            if self._parent_page:
                                self._parent_page.mark_as_modified()
                    self.update()
                    
            # EDITABLE_LINE_NODE_SELECTOR için canvas_tablet_handler'a gitme
            return
        
        # --- Diğer tüm araçlar için canvas_tablet_handler'ı kullan ---
        if event_type == QTabletEvent.Type.TabletPress:
            canvas_tablet_handler.handle_tablet_press(self, world_pos, event)
        elif event_type == QTabletEvent.Type.TabletMove:
            canvas_tablet_handler.handle_tablet_move(self, world_pos, event)
        elif event_type == QTabletEvent.Type.TabletRelease:
            canvas_tablet_handler.handle_tablet_release(self, world_pos, event)
        else:
            event.ignore()
    
    def _get_current_selection_states(self, page_ref: Optional['Page']) -> List[Any]:
        states = []
        if not page_ref:
             logging.error("_get_current_selection_states: Fonksiyona geçerli bir 'page_ref' sağlanmadı!")
             return states
        for item_type, index in self._selected_item_indices:
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
                                    if key not in ['pixmap', 'original_pixmap_for_scaling', 'pixmap_item']:
                                        try:
                                            current_item_state[key] = copy.deepcopy(value) # DİKKAT: Buradaki '\\' kaldırıldı
                                        except TypeError as e:
                                            logging.warning(f"_get_current_selection_states: images[{index}] için '{key}' anahtarı kopyalanamadı (TypeError): {e}. Bu anahtar atlanıyor.")
                                
                                if not current_item_state: 
                                    logging.warning(f"_get_current_selection_states: images[{index}] için kopyalanacak güvenli veri bulunamadı.")
                                    current_item_state = {'uuid': item_data_source.get('uuid')} # En azından UUID'yi sakla
                                elif 'uuid' not in current_item_state and 'uuid' in item_data_source: # UUID eksikse ekle
                                    current_item_state['uuid'] = item_data_source['uuid']

                            else:
                                logging.warning(f"_get_current_selection_states: images[{index}] için item_data_source None.")
                        else:
                            logging.warning(f"_get_current_selection_states: Geçersiz images index: {index}")
                    else:
                         logging.warning(f"_get_current_selection_states: page_ref.images bulunamadı veya liste değil.")
                elif item_type == 'bspline_strokes': # YENİ: B-Spline Strokes için durum alma
                    if 0 <= index < len(self.b_spline_strokes):
                        item_data_source = self.b_spline_strokes[index]
                        # B-Spline stroke_data genellikle numpy array'ler içerir, deepcopy güvenli olmalı.
                        current_item_state = copy.deepcopy(item_data_source) if item_data_source else None
                    else:
                        #logging.warning(f"_get_current_selection_states: Geçersiz bspline_strokes index: {index}")
                        pass
                else:
                    #logging.warning(f"_get_current_selection_states: Bilinmeyen öğe tipi: {item_type}[{index}]")
                    pass

                states.append(current_item_state)
            except Exception as e:
                #logging.error(f"_get_current_selection_states hatası ({item_type}[{index}] için veri alınırken): {e}", exc_info=True)
                states.append(None) 
        return states

    def _get_combined_bbox(self, states: List[Any]) -> QRectF:
        combined_bbox = QRectF()
        for item_type, index in self._selected_item_indices:
            item_data = None
            bbox = QRectF() # Önce null yap
            if item_type == 'lines' and 0 <= index < len(self.lines):
                item_data = self.lines[index]
                bbox = geometry_helpers.get_item_bounding_box(item_data, 'lines')
            elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                item_data = self.shapes[index]
                bbox = geometry_helpers.get_item_bounding_box(item_data, 'shapes')
            elif item_type == 'images' and self._parent_page and hasattr(self._parent_page, 'images') and 0 <= index < len(self._parent_page.images):
                item_data = self._parent_page.images[index]
                if 'rect' in item_data:
                    bbox = item_data['rect']
            elif item_type == 'bspline_strokes' and 0 <= index < len(self.b_spline_strokes):
                item_data = self.b_spline_strokes[index]
                #logging.debug(f"[_get_combined_bbox] bspline_strokes[{index}] item_data: {item_data}")
                bbox = geometry_helpers.get_bspline_bounding_box(item_data)
                #logging.debug(f"[_get_combined_bbox] bspline_strokes[{index}] bbox: {bbox}")
            else:
                bbox = QRectF()
            #logging.debug(f"[_get_combined_bbox] {item_type}[{index}] bbox: {bbox}")
            if not bbox.isNull():
                if combined_bbox.isNull():
                    combined_bbox = bbox
                else:
                    combined_bbox = combined_bbox.united(bbox)
            else:
                if item_type != 'images':
                    logging.warning(f"_get_combined_bbox: Geçersiz öğe referansı veya bbox hesaplanamadı: {item_type}[{index}]")
                elif item_type == 'images' and not item_data:
                    logging.warning(f"_get_combined_bbox: Geçersiz resim referansı: images[{index}] (parent_page: {self._parent_page is not None})")
        return combined_bbox

    def is_point_on_selection(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Verilen noktanın seçili öğe üzerinde olup olmadığını kontrol eder."""
        #logging.debug(f"--- is_point_on_selection checking point {point} ---")
        result = False

        if not self.selected_item_indices:  # Seçili bir öğe yoksa, noktada bir şey olamaz
            logging.debug(f"--- is_point_on_selection result: {result} ---")
            return result

        # Taşıma için toleransı artır - özellikle tablet kalemi ile taşımak daha kolay olsun
        effective_tolerance = tolerance * 3.0  # Toleransı 3 kat artır

        try:
            for item_type, index in self.selected_item_indices:
                if item_type == 'lines' and 0 <= index < len(self.lines):
                    item_data = self.lines[index]
                    
                    # Çizgi için çoklu nokta kontrolü
                    if len(item_data) > 2 and isinstance(item_data[2], list):
                        points = item_data[2]
                        line_width = item_data[1]
                        
                        # Çizginin bounding box'ını hesapla
                        bbox = geometry_helpers.get_item_bounding_box(item_data, 'lines')
                        # Tolerans ile genişletilmiş bbox kontrolü
                        extended_bbox = bbox.adjusted(-effective_tolerance, -effective_tolerance, 
                                                     effective_tolerance, effective_tolerance)
                        
                        # Önce bbox kontrolü yap (daha hızlı)
                        if extended_bbox.contains(point):
                            # Bbox içindeyse, segment kontrolü yap
                            for i in range(len(points) - 1):
                                p1, p2 = points[i], points[i+1]
                                if geometry_helpers.is_point_on_line(point, p1, p2, effective_tolerance):
                                    result = True
                                    #logging.debug(f"  >>> Point IS on line: {item_type}[{index}], segment between points {i} and {i+1}")
                                    break
            
                elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                    shape_data = self.shapes[index]
                    tool_type = shape_data[0]

                    # Şeklin bounding box'ını hesapla
                    bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                    # Tolerans ile genişletilmiş bbox kontrolü
                    extended_bbox = bbox.adjusted(-effective_tolerance, -effective_tolerance, 
                                                 effective_tolerance, effective_tolerance)
                    
                    # RECTANGLE ve CIRCLE için özel içinde olma kontrolü
                    if tool_type == ToolType.RECTANGLE or tool_type == ToolType.CIRCLE:
                        # Dikdörtgen/daire verilerini çıkar
                        p1 = shape_data[3]
                        p2 = shape_data[4]
                        rect = QRectF(p1, p2).normalized()  # Normalleştirilmiş dikdörtgen
                        
                        # Daire için noktanın merkeze uzaklığını kontrol et
                        if tool_type == ToolType.CIRCLE:
                            center = rect.center()
                            rx = rect.width() / 2.0
                            ry = rect.height() / 2.0
                            
                            # Elips içinde mi kontrolü (x^2/a^2 + y^2/b^2 <= 1)
                            if rx > 0 and ry > 0:
                                dx = (point.x() - center.x()) / rx
                                dy = (point.y() - center.y()) / ry
                                distance_normalized = dx*dx + dy*dy
                                
                                # Elips içinde veya yakınında mı?
                                is_in_or_near_circle = distance_normalized <= 1.0 + (effective_tolerance / min(rx, ry))
                                if is_in_or_near_circle:
                                    result = True
                                    #logging.debug(f"  >>> Point IS in or near CIRCLE: {item_type}[{index}]")
                                    break
                        # Dikdörtgen için genişletilmiş dikdörtgen içinde mi kontrolü
                        elif extended_bbox.contains(point):
                            result = True
                            #logging.debug(f"  >>> Point IS in RECTANGLE: {item_type}[{index}]")
                            break
                    # Önce genişletilmiş bbox ile hızlı kontrol
                    elif extended_bbox.contains(point):
                        result = True
                        #logging.debug(f"  >>> Point IS on shape's extended bbox: {item_type}[{index}], type={tool_type}")
                        break
                    
                    # PATH şekli için özel kontrol
                    if tool_type == ToolType.PATH and not result:
                        if isinstance(shape_data[3], list):
                            points = shape_data[3]
                            line_width = shape_data[2]
                            
                            # PATH'in her parçası için kontrol
                            for i in range(len(points) - 1):
                                p1, p2 = points[i], points[i+1]
                                if geometry_helpers.is_point_on_line(point, p1, p2, effective_tolerance):
                                    result = True
                                    logging.debug(f"  >>> Point IS on PATH: {item_type}[{index}], segment between points {i} and {i+1}")
                                    break
                
                # Düzgün şekiller için diğer kontroller
                # (toleransı artırdık ve bbox kontrolü ile çakışmaları ele aldık, bu yüzden diğer kontrollere gerek yok)
                    
        except Exception as e:
            logging.error(f"Error in is_point_on_selection: {e}")
                        
        #logging.debug(f"--- is_point_on_selection result: {result} ---")
        return result

    def _reposition_selected_items_from_initial(self, total_dx: float, total_dy: float):
        """
        Seçili öğeleri, sürüklemenin başlangıcındaki orijinal durumlarına göre
        total_dx ve total_dy kadar yeniden konumlandırır.
        self.move_original_states (başlangıç durumları) ve 
        self.selected_item_indices (tür ve orijinal indeks) kullanılır.
        """
        if len(self.selected_item_indices) != len(self.move_original_states):
            logging.error(
                "_reposition_selected_items_from_initial: self.selected_item_indices uzunluğu (%d) "
                "ile self.move_original_states uzunluğu (%d) eşleşmiyor.",
                len(self.selected_item_indices), len(self.move_original_states)
            )
            logging.error(f"  selected_item_indices: {self.selected_item_indices}")
            logging.error(f"  move_original_states: {[type(s) for s in self.move_original_states]}")
            return

        # LOG: Taşıma başında hangi öğeler taşınacak?
        #logging.debug(f"[TAŞIMA BAŞLANGICI] Seçili öğeler: {self.selected_item_indices}")
        for i, (item_type, item_original_idx) in enumerate(self.selected_item_indices):
            #logging.debug(f"  {i}: type={item_type}, index={item_original_idx}")
            pass

        something_moved = False
        for i, (item_type, item_original_idx) in enumerate(self.selected_item_indices):
            if i >= len(self.move_original_states):
                logging.warning(f"_reposition_selected_items_from_initial: move_original_states öğe sayısı yetersiz (index {i}). Atlama.")
                continue

            original_item_data = self.move_original_states[i]
            if original_item_data is None:
                # logging.warning(f"_reposition_selected_items_from_initial: original_item_data None (index {i}). Atlama.") # Çok sık log üretebilir
                continue

            if item_type == 'lines':
                if 0 <= item_original_idx < len(self.lines):
                    original_points = original_item_data[2] 
                    if original_points and all(isinstance(p, QPointF) for p in original_points):
                        # --- SNAP TO GRID --- #
                        if getattr(self, 'snap_lines_to_grid', False):
                            new_points = [self._snap_point_to_grid(QPointF(p.x() + total_dx, p.y() + total_dy)) for p in original_points]
                        else:
                            new_points = [QPointF(p.x() + total_dx, p.y() + total_dy) for p in original_points]
                        self.lines[item_original_idx][2] = new_points
                    else:
                        pass
                else:
                    pass
            elif item_type == 'shapes':
                if 0 <= item_original_idx < len(self.shapes):
                    shape_tool_type = self.shapes[item_original_idx][0]
                    if shape_tool_type == ToolType.EDITABLE_LINE: # Bezier eğrileri için
                        original_control_points = original_item_data[3] # Bezier kontrol noktaları (QPointF listesi)
                        if original_control_points and all(isinstance(p, QPointF) for p in original_control_points):
                            new_control_points = [QPointF(p.x() + total_dx, p.y() + total_dy) for p in original_control_points]
                            self.shapes[item_original_idx][3] = new_control_points
                        else:
                            pass
                    elif shape_tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                        original_p1 = original_item_data[3]
                        original_p2 = original_item_data[4];
                        if isinstance(original_p1, QPointF) and isinstance(original_p2, QPointF):
                            # --- SNAP TO GRID --- #
                            if getattr(self, 'snap_lines_to_grid', False):
                                new_p1 = self._snap_point_to_grid(QPointF(original_p1.x() + total_dx, original_p1.y() + total_dy))
                                new_p2 = self._snap_point_to_grid(QPointF(original_p2.x() + total_dx, original_p2.y() + total_dy))
                            else:
                                new_p1 = QPointF(original_p1.x() + total_dx, original_p1.y() + total_dy)
                                new_p2 = QPointF(original_p2.x() + total_dx, original_p2.y() + total_dy)
                            self.shapes[item_original_idx][3] = new_p1
                            self.shapes[item_original_idx][4] = new_p2
                        else:
                            pass
                    else: # Diğer şekiller
                        original_p1 = original_item_data[3]
                        original_p2 = original_item_data[4]
                        if isinstance(original_p1, QPointF) and isinstance(original_p2, QPointF):
                            self.shapes[item_original_idx][3] = QPointF(original_p1.x() + total_dx, original_p1.y() + total_dy)
                            self.shapes[item_original_idx][4] = QPointF(original_p2.x() + total_dx, original_p2.y() + total_dy)
                        else:
                            pass
                else:
                    pass
            elif item_type == 'images':
                if self._parent_page and 0 <= item_original_idx < len(self._parent_page.images):
                    original_rect = original_item_data.get('rect')
                    if isinstance(original_rect, QRectF):
                        new_rect = QRectF(original_rect)
                        new_rect.translate(total_dx, total_dy)
                        self._parent_page.images[item_original_idx]['rect'] = new_rect
                    else:
                        pass
                else:
                    pass
            elif item_type == 'bspline_strokes':
                if 0 <= item_original_idx < len(self.b_spline_strokes):
                    if original_item_data and 'control_points' in original_item_data:
                        original_control_points = original_item_data['control_points']
                        if isinstance(original_control_points, np.ndarray) and original_control_points.ndim == 2 and original_control_points.shape[1] == 2:
                            original_control_points = [np.array(row) for row in original_control_points]
                        if isinstance(original_control_points, list) and original_control_points and all(isinstance(cp, np.ndarray) and cp.shape == (2,) for cp in original_control_points):
                            new_control_points = [
                                np.array([cp[0] + total_dx, cp[1] + total_dy]) for cp in original_control_points
                            ]
                            self.b_spline_strokes[item_original_idx]['control_points'] = new_control_points
                        else:
                            logging.error(f"_reposition: bspline_strokes[{item_original_idx}] için original_control_points beklenen formatta değil. Veri: {original_control_points}")
                            continue # Bu stroke için işlemi atla
                    else:
                        logging.warning(f"_reposition: bspline_strokes[{item_original_idx}] için original_item_data (move_original_states'ten) veya control_points bulunamadı.")
                else:
                    logging.warning(f"_reposition: Geçersiz bspline_strokes index: {item_original_idx}")
            else:
                pass
            something_moved = True
        if something_moved:
            if self._parent_page:
                 self._parent_page.mark_as_modified() # Taşıma yapıldıysa sayfayı değiştirilmiş olarak işaretle
        # self.update() # Bu metodun kendisi update çağırmamalı, çağıran yer (örn. mouseMove) yapmalı.

    def set_tool(self, tool: ToolType):
        # YENİ: Bir önceki aracı kaydet
        previous_tool = self.current_tool
        
        # Aktif aracı güncelle
        self.current_tool = tool
        
        # WIP notu düzenliyorsa iptal et
        if self.current_text_edit:
            self.current_text_edit.deleteLater()
            self.current_text_edit = None

        # Seçim işlemi devam ediyorsa iptal et
        if self.drawing:
            self.drawing = False
            self.current_line_points = []

        # Şekil çizimi devam ediyorsa iptal et
        if self.drawing_shape:
            self.drawing_shape = False

        # Şekil araçları için özel durumlar (dikdörtgen, daire vs.)
        if self.current_tool == ToolType.RECTANGLE or self.current_tool == ToolType.CIRCLE:
            self.setCursor(Qt.CursorShape.CrossCursor)
        
        # --- YENİ: Lazer İşaretçi Durumu --- #
        self.laser_pointer_active = (tool == ToolType.LASER_POINTER) # Lazer durumunu ayarla
        
        if tool == ToolType.LASER_POINTER:
            self.setCursor(Qt.CursorShape.BlankCursor)  # Fareyi gizle
        # --- --- --- --- --- --- --- --- --- --- #
        
        # --- YENİ: Seçim ve Node Seçici Araç Geçişleri --- #
        if previous_tool == ToolType.SELECTOR and tool != ToolType.SELECTOR:
            # Seçimi temizle (seçimden başka araca geçtiğimizde)
            self.selected_item_indices = []
            self.current_handles = {}
        
        if previous_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR and tool != ToolType.EDITABLE_LINE_NODE_SELECTOR:
            # Kontrol noktası vurgulamasını temizle
            self.hovered_node_index = -1
            self.hovered_bezier_handle_index = -1
        # --- --- --- --- --- --- --- --- --- --- --- --- --- #
            
        # --- YENİ: Araç Geçişlerinde İmleç Ayarları --- #
        if tool == ToolType.ERASER:
            # Silgi için özel imleç - yuvarlak şeklinde
            self.setCursor(Qt.CursorShape.CrossCursor)  # Şimdilik çarpı, ileride özel imleç yapılabilir
        elif previous_tool == ToolType.ERASER:
            # Silgiden çıkınca normal fare imlecine dön
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
        if tool == ToolType.LASER_POINTER:
            # Lazer işaretçi için imleci gizle (çünkü işaretçi çiziyoruz)
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif previous_tool == ToolType.LASER_POINTER:
            # Lazer işaretçiden çıkınca normal fare imlecine dön
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.laser_pointer_active = False  # Lazer işaretçiyi devre dışı bırak
            
        # --- YENİ: Geçici İşaretçi Ayarları --- #
        if tool == ToolType.TEMPORARY_POINTER:
            # Geçici işaretçi seçildiğinde timeri başlat
            if not self.pointer_trail_timer.isActive():
                self.pointer_trail_timer.start()
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif previous_tool == ToolType.TEMPORARY_POINTER:
            # Geçici işaretçiden çıkınca timer'ı durdur ve noktaları temizle
            self.pointer_trail_points = []
            self.temporary_drawing_active = False
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

        # Seçim modundan çıkıldıysa seçimi temizle
        if previous_tool == ToolType.SELECTOR and tool != ToolType.SELECTOR:
             self._selected_item_indices.clear()
             self.current_handles.clear()
             self.update() # Ekranı temizle
             
        # --- YENİ: Düzenlenebilir çizgi seçim aracından çıkıldıysa seçimi temizle --- #
        if previous_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR and tool != ToolType.EDITABLE_LINE_NODE_SELECTOR:
            self._selected_item_indices.clear()
            self.active_handle_index = -1
            self.active_bezier_handle_index = -1
            self.is_dragging_bezier_handle = False
            self.hovered_node_index = -1
            self.hovered_bezier_handle_index = -1
            self.update() # Ekranı temizle
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

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

        # Pointer trail timer kontrolü
        if tool == ToolType.TEMPORARY_POINTER:
            if not self.pointer_trail_timer.isActive():
                self.pointer_trail_timer.start(20)
        else:
            if self.pointer_trail_timer.isActive():
                self.pointer_trail_timer.stop()

    def clear_canvas(self):
        command = ClearCanvasCommand(self)
        self.undo_manager.execute(command)

    def set_color(self, color: QColor):
        """Aktif çizim rengini ayarlar."""
        # QColor'ı RGBA float tuple'ına dönüştür (0-1 aralığında)
        self.current_color = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
        #logging.debug(f"DrawingCanvas: Renk değiştirildi -> {self.current_color}")
        # YENİ: B-Spline widget'ına da rengi ilet
        if hasattr(self, 'b_spline_widget') and self.b_spline_widget:
            self.b_spline_widget.setDefaultStrokeColor(self.current_color)

    def set_pen_width(self, width: float):
        new_width = max(1.0, width)
        if self.current_pen_width != new_width:
            self.current_pen_width = new_width
            # logging.debug(f"Kalem kalınlığı ayarlandı: {self.current_pen_width}") # Yorum satırı yapıldı (isteğe bağlı)

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
            # logging.debug(f"Silgi kalınlığı ayarlandı: {self.eraser_width}") # Yorum satırı yapıldı (isteğe bağlı)
            if self.current_tool == ToolType.ERASER:
                self.update()

    def hoverMoveEvent(self, event):
        pos_screen = event.position()
        # --- YENİ: Lazer İşaretçi Konumunu Güncelle --- #
        if self.laser_pointer_active:
            # --- YENİ LOG --- #
            # logging.debug(f"hoverMoveEvent: Updating laser pos to {pos_screen}") # Yorum satırı yapıldı
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
            # logging.debug("Leave Event: Clearing laser pointer position.") # Yorum satırı yapıldı
            self.update() # Ekranı güncelle
        # --- --- --- --- --- --- --- --- --- -- #
        QApplication.restoreOverrideCursor()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
        
    @pyqtSlot(int)
    def update_line_spacing(self, spacing_pt: int):
        # logging.debug(f"Anlık çizgi aralığı güncelleniyor: {spacing_pt} pt") # Yorum satırı yapıldı
        self.line_spacing_pt = spacing_pt
        self.update()

    @pyqtSlot(int)
    def update_grid_spacing(self, spacing_pt: int):
        # logging.debug(f"Anlık ızgara aralığı güncelleniyor: {spacing_pt} pt") # Yorum satırı yapıldı
        self.grid_spacing_pt = spacing_pt
        self.update()
        
    @pyqtSlot(tuple)
    def update_line_color(self, color_rgba: tuple):
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            # logging.debug(f"Anlık çizgi rengi güncelleniyor: {color_rgba}") # Yorum satırı yapıldı
            self.template_line_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık çizgi rengi verisi alındı: {color_rgba}")

    @pyqtSlot(tuple)
    def update_grid_color(self, color_rgba: tuple):
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            # logging.debug(f"Anlık ızgara rengi güncelleniyor: {color_rgba}") # Yorum satırı yapıldı
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
                if self.current_template == TemplateType.PLAIN:
                    self._background_pixmap = None
                    self._current_background_image_path = None
                    self._static_content_cache = None
        except KeyError:
            logging.warning(f"Ayarlarda geçersiz template_type_name: '{template_name}', şablon tipi değiştirilmedi.")
        except Exception as e:
            logging.error(f"Şablon tipi güncellenirken hata: {e}")
        
        self.invalidate_cache(reason="Şablon ayarı değişti")
        self.load_background_template_image()
        self.update()
        self.invalidate_cache(reason="Arka plan şablonu yüklendi")
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
        # logging.debug(f"DrawingCanvas parent_page set to: {page.page_number if page else 'None'}") # Yorum satırı yapıldı

    @pyqtSlot(int)
    def update_line_spacing(self, spacing_pt: int):
        """Dialogdan gelen sinyal üzerine çizgi aralığını günceller (anlık)."""
        # logging.debug(f"Anlık çizgi aralığı güncelleniyor: {spacing_pt} pt") # Yorum satırı yapıldı
        self.line_spacing_pt = spacing_pt
        self.update()

    @pyqtSlot(int)
    def update_grid_spacing(self, spacing_pt: int):
        """Dialogdan gelen sinyal üzerine ızgara aralığını günceller (anlık)."""
        # logging.debug(f"Anlık ızgara aralığı güncelleniyor: {spacing_pt} pt") # Yorum satırı yapıldı
        self.grid_spacing_pt = spacing_pt
        self.update()
        
    @pyqtSlot(tuple)
    def update_line_color(self, color_rgba: tuple):
        """Dialogdan gelen sinyal üzerine çizgi rengini günceller (anlık)."""
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            # logging.debug(f"Anlık çizgi rengi güncelleniyor: {color_rgba}") # Yorum satırı yapıldı
            self.template_line_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık çizgi rengi verisi alındı: {color_rgba}")

    @pyqtSlot(tuple)
    def update_grid_color(self, color_rgba: tuple):
        """Dialogdan gelen sinyal üzerine ızgara rengini günceller (anlık)."""
        if isinstance(color_rgba, (list, tuple)) and len(color_rgba) >= 3:
            # logging.debug(f"Anlık ızgara rengi güncelleniyor: {color_rgba}") # Yorum satırı yapıldı
            self.template_grid_color = color_rgba
            self.update()
        else:
             logging.warning(f"Geçersiz anlık ızgara rengi verisi alındı: {color_rgba}")
        
    def apply_template_settings(self, settings: dict):
        """Verilen ayarlardan tüm şablon parametrelerini günceller."""
        logging.debug(f"Canvas'a yeni şablon ayarları uygulanıyor: {settings}") # Bu kalsın
        self.template_line_color = settings.get("line_color", self.template_line_color)
        self.template_grid_color = settings.get("grid_color", self.template_grid_color)
        self.line_spacing_pt = settings.get("line_spacing_pt", self.line_spacing_pt)
        self.grid_spacing_pt = settings.get("grid_spacing_pt", self.grid_spacing_pt)
        
        try:
            template_name = settings.get('template_type_name')
            if template_name:
                self.current_template = TemplateType[template_name]
                if self.current_template == TemplateType.PLAIN:
                    self._background_pixmap = None
                    self._current_background_image_path = None
                    self._static_content_cache = None
        except KeyError:
             logging.warning(f"Ayarlarda geçersiz template_type_name: '{template_name}', şablon tipi değiştirilmedi.")
        except Exception as e:
            logging.error(f"Şablon tipi güncellenirken hata: {e}")
            
        self.update()
    # --- --- --- --- --- --- --- --- --- ---

    def _check_temporary_lines(self):
        """Zamanlayıcı tarafından çağrılır, süresi dolan geçici pointer çizgilerini animasyonlu olarak siler."""
        current_time = time.time()
        something_changed = False
        new_temporary_lines = []
        animasyon_suresi = 1.0  # Silme animasyonu süresi (saniye)
        # timer_interval = 0.05   # Timer aralığı (saniye) - Artık kullanılmayacak

        for line in self.temporary_lines:
            points, color, width, start_time, animasyon_basladi = line
            if not animasyon_basladi:
                if current_time - start_time < self.temporary_line_duration:
                    new_temporary_lines.append([points, color, width, start_time, False])
                else:
                    if len(points) > 0:
                        new_temporary_lines.append([points, color, width, start_time, True])
                        something_changed = True
            else:
                # Animasyon başladıysa, her adımda sadece 1 nokta sil
                if len(points) > 0:
                    points.pop()
                    if len(points) > 0:
                        new_temporary_lines.append([points, color, width, start_time, True])
                        something_changed = True
                    else:
                        something_changed = True
                else:
                    something_changed = True
        # --- paintEvent'te aktif çizim için fade-out başlat ---
        if self.temporary_drawing_active and len(self.current_temporary_line_points) > 1:
            ilk_zaman = self.current_temporary_line_points[0][1]
            if current_time - ilk_zaman > self.temporary_line_duration:
                self.current_temporary_line_points.pop(0)
                something_changed = True
        self.temporary_lines = new_temporary_lines
        # Sadece bir değişiklik olduysa ve ekranda geçici çizgi veya aktif çizim varsa update çağır
        if something_changed and (self.temporary_lines or self.temporary_drawing_active):
            self.update()
        # Timer'ı durdurma kodu kaldırıldı

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
        
        # logging.debug(f"Canvas işaretçi ayarları güncellendi. Süre: {self.temporary_line_duration}, Faktörler: GW={self.temp_glow_width_factor:.2f}, CW={self.temp_core_width_factor:.2f}, GA={self.temp_glow_alpha_factor:.2f}, CA={self.temp_core_alpha_factor:.2f}") # Yorum satırı yapıldı
        self.update() # Gerekirse görünümü güncelle
    # --- --- --- --- --- --- --- --- --- --- #

    # --- YENİ: Belirli Bir Noktadaki Öğeyi Bulma --- #
    def _get_item_at(self, world_pos: QPointF, tolerance: float = 5.0) -> Tuple[str, int] | None:
        """Verilen dünya koordinatındaki en üstteki öğeyi (varsa) döndürür.
           'lines', 'shapes', 'images' tiplerini kontrol eder.
        """
        #logging.debug(f"--- _get_item_at called for World Pos: {world_pos}, tolerance: {tolerance} ---")
        
        # 1. Resimleri Kontrol Et (Sondan başa doğru)
        if self._parent_page and hasattr(self._parent_page, 'images') and self._parent_page.images:
            #logging.debug(f"  _get_item_at: Checking {len(self._parent_page.images)} images...")
            for i in range(len(self._parent_page.images) - 1, -1, -1):
                img_data = self._parent_page.images[i]
                rect = img_data.get('rect')
                angle = img_data.get('angle', 0.0)
                if rect and isinstance(rect, QRectF):
                    contains = geometry_helpers.is_point_in_rotated_rect(world_pos, rect, angle)
                    #logging.debug(f"    _get_item_at: Checking image {i} with rect: {rect}, angle: {angle:.1f}. Contains point? {contains}")
                    if contains:
                        #logging.debug(f"  >>> _get_item_at: Image found at index {i}")
                        return ('images', i)
                else:
                    #logging.warning(f"_get_item_at: images[{i}] içinde geçerli 'rect' yok.")
                    pass

        # 2. Şekilleri Kontrol Et (Sondan başa doğru)
        #logging.debug(f"  _get_item_at: Checking {len(self.shapes)} shapes...")
        for i in range(len(self.shapes) - 1, -1, -1):
            shape_data = self.shapes[i]
            #logging.debug(f"    _get_item_at: Checking shape index {i}, data type: {type(shape_data[0])}, data: {shape_data}")

            item_tool_type = shape_data[0]

            if item_tool_type == ToolType.LINE:
                p1 = shape_data[3]
                p2 = shape_data[4]
                line_width = shape_data[2]
                effective_tolerance = tolerance + (line_width / 2.0)
                
                #logging.debug(f"      _get_item_at (Shape as Line): Checking line {i} with p1={p1}, p2={p2}, width={line_width}, eff_tol={effective_tolerance}, world_pos={world_pos}")
                if geometry_helpers.is_point_on_line(world_pos, p1, p2, effective_tolerance):
                    #logging.debug(f"  >>> _get_item_at: Shape (Line) found at index {i} by is_point_on_line")
                    return ('shapes', i)
                else:
                    #logging.debug(f"      _get_item_at (Shape as Line): Line {i} NOT matched by is_point_on_line.")
                    pass
            elif item_tool_type == ToolType.EDITABLE_LINE:
                # Düzenlenebilir çizgi için özel kontrol
                control_points = shape_data[3]  # Kontrol noktaları
                line_width = shape_data[2]
                effective_tolerance = tolerance + (line_width / 2.0)
                
                # Önce genel sınırlayıcı kutuyu kontrol et - daha hızlı bir ilk kontrol
                bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                if bbox.contains(world_pos):
                    logging.debug(f"      _get_item_at (EDITABLE_LINE): BBox contains the point. Checking individual segments...")
                    
                    # Tüm noktalar arasında doğrusal bağlantıları kontrol et
                    for j in range(len(control_points) - 1):
                        p1 = control_points[j]
                        p2 = control_points[j + 1]
                        
                        if geometry_helpers.is_point_on_line(world_pos, p1, p2, effective_tolerance):
                            logging.debug(f"  >>> _get_item_at: Shape (EDITABLE_LINE) found at index {i} by is_point_on_line segment {j}-{j+1}")
                            return ('shapes', i)
                    
                    # Tüm doğrudan çizgiler kontrol edildi, şekil sınırlayıcı kutu içinde ancak segmentlerde değil
                    # Yine de seçilebilir olması için döndürelim
                    logging.debug(f"  >>> _get_item_at: Shape (EDITABLE_LINE) selected by bounding box at index {i}")
                    return ('shapes', i)
                else:
                    logging.debug(f"      _get_item_at (EDITABLE_LINE): BBox does not contain the point, skipping segment checks.")
            elif item_tool_type == ToolType.PATH:
                # PATH için özel kontrol
                points = shape_data[3] if len(shape_data) > 3 else []
                line_width = shape_data[2]
                effective_tolerance = tolerance + (line_width / 2.0)
                if points and len(points) > 1:
                    for j in range(len(points) - 1):
                        p1 = points[j]
                        p2 = points[j + 1]
                        if geometry_helpers.is_point_on_line(world_pos, p1, p2, effective_tolerance):
                            logging.debug(f"  >>> _get_item_at: Shape (PATH) found at index {i} by is_point_on_line segment {j}-{j+1}")
                            return ('shapes', i)
            else:
                bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                #logging.debug(f"    _get_item_at (Shape as Other): Checking shape {i} (type: {item_tool_type}) with bbox: {bbox}. Point: {world_pos}")
                if bbox.contains(world_pos):
                    #logging.debug(f"  >>> _get_item_at: Shape (Other) found at index {i} by bbox.contains")
                    return ('shapes', i)
                else:
                    #logging.debug(f"      _get_item_at (Shape as Other): Shape {i} NOT matched by bbox.contains.")
                    pass
        # 3. Çizgileri Kontrol Et (Sondan başa doğru)
        #logging.debug(f"  _get_item_at: Checking {len(self.lines)} lines...")
        for i in range(len(self.lines) - 1, -1, -1):
            line_data = self.lines[i]
            bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
            #logging.debug(f"    [GET_ITEM_AT_DEBUG] Line {i}: BBox={bbox}, BBox.width={bbox.width():.2f}, BBox.height={bbox.height():.2f}")
            contains_bbox = bbox.contains(world_pos)
            #logging.debug(f"    [GET_ITEM_AT_DEBUG]   Line {i}: world_pos={world_pos}, bbox_contains_world_pos={contains_bbox}")
            if contains_bbox: 
                points = line_data[2]
                line_width = line_data[1]
                effective_tolerance = tolerance + line_width / 2.0
                #logging.debug(f"      [GET_ITEM_AT_DEBUG]     Line {i}: Calling is_point_on_line with effective_tolerance={effective_tolerance:.2f}")
                for j in range(len(points) - 1):
                    if geometry_helpers.is_point_on_line(world_pos, points[j], points[j+1], effective_tolerance):
                        #logging.debug(f"  >>> _get_item_at: Line found at index {i} (segment {j}-{j+1} check PASSED)")
                        return ('lines', i)
                    else: 
                        #logging.debug(f"      [GET_ITEM_AT_DEBUG]       Line {i}, Segment {j}-{j+1}: is_point_on_line FAILED.")
                #logging.debug(f"    [GET_ITEM_AT_DEBUG]     Line {i}: BBox contained point, but all segment checks failed.")
                        pass
        # 3. B-Spline Eğrilerini Kontrol Et (Sondan başa doğru)
        # Not: B-spline'lar self.b_spline_strokes içinde saklanıyor.
        # Eğer normal şekil seçimiyle çakışmaması için ayrı bir tool ile yönetilecekse
        # bu kısım sadece ilgili tool aktifken çalışmalı veya hiç olmamalı.
        # Şimdilik genel seçici (_get_item_at) içinde deneyelim.
        if hasattr(self, 'b_spline_strokes') and self.b_spline_strokes:
            #logging.debug(f"  _get_item_at: Checking {len(self.b_spline_strokes)} B-Spline strokes...")
            for i in range(len(self.b_spline_strokes) - 1, -1, -1):
                stroke_data = self.b_spline_strokes[i]
                #logging.debug(f"    _get_item_at: For B-Spline stroke {i}, attempting to get bbox. World pos: {world_pos}") # YENİ LOG
                # B-spline'ın sınırlayıcı kutusunu al
                # Bu fonksiyonun utils.geometry_helpers içinde tanımlı olması gerekiyor.
                try:
                    bbox = geometry_helpers.get_bspline_bounding_box(stroke_data)
                    #logging.debug(f"    _get_item_at: B-Spline stroke {i} bbox: {bbox}. IsNull: {bbox.isNull() if bbox else 'N/A'}") # YENİ LOG
                    if not bbox.isNull() and bbox.contains(world_pos):
                        #logging.debug(f"  >>> _get_item_at: B-Spline stroke {i} CONTAINS world_pos. Returning ('bspline_strokes', {i})") # YENİ LOG
                        # TODO: Daha hassas bir "nokta eğri üzerinde mi" kontrolü eklenebilir.
                        # Şimdilik sadece bbox yeterli.
                        # logging.debug(f"  >>> _get_item_at: B-Spline stroke found at index {i} by bbox.contains") # ESKİ LOG
                        return ('bspline_strokes', i) # Yeni bir item_type tanımlıyoruz
                    elif bbox.isNull():
                        #logging.debug(f"    _get_item_at: B-Spline stroke {i} bbox isNull. Skipping contains check.") # YENİ LOG
                        pass
                    else:
                        #logging.debug(f"    _get_item_at: B-Spline stroke {i} bbox DOES NOT contain world_pos.") # YENİ LOG
                        pass
                except Exception as e:
                    #logging.error(f"_get_item_at: B-Spline bbox alınırken hata (stroke {i}): {e}", exc_info=True)
                    pass

        #logging.debug("--- _get_item_at: No item found. ---")
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

    # YENİ METOT: B-Spline Kontrol Noktası Bulma
    def _get_bspline_control_point_at(self, world_pos: QPointF, tolerance: float = 10.0) -> Tuple[int, int] | None:
        """Verilen dünya koordinatına en yakın B-Spline kontrol noktasını bulur.
           (stroke_index, control_point_index) veya None döndürür.
        """
        # Toleransı dünya birimlerinde düşünmeliyiz.
        # world_to_screen dönüşümü ile ekran piksel toleransını dünya birimine çevirebiliriz,
        # ancak bu zoom seviyesine göre değişir. Şimdilik sabit bir dünya toleransı kullanalım.
        # Daha gelişmiş bir çözüm, ekran pikseli toleransını anlık zoom'a göre dünyaya çevirmek olabilir.

        for stroke_idx, stroke_data in enumerate(self.b_spline_strokes):
            control_points_np = stroke_data.get('control_points')
            if control_points_np is not None:
                for cp_idx, cp_np in enumerate(control_points_np):
                    # cp_np, [x, y] şeklinde bir numpy array
                    cp_qpointf = QPointF(cp_np[0], cp_np[1])
                    # Basit manhattan uzaklığı veya Öklid mesafesi kullanılabilir
                    if (world_pos - cp_qpointf).manhattanLength() < tolerance:
                        return (stroke_idx, cp_idx)
        return None
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def load_background_template_image(self, image_path: str | None = None, force_reload: bool = False):
        """Verilen yoldan veya mevcut _current_background_image_path'den şablon arka planını yükler."""
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
            # logging.debug(f"Canvas minimum size set to background size: {self._background_pixmap.size().width()}x{self._background_pixmap.size().height()}") # Yorum satırı yapıldı (yukarıda zaten var)
        else:
            self.setMinimumSize(600, 800)

        self.update()
        self.invalidate_cache(reason="Arka plan şablonu yüklendi")

    def resizeEvent(self, event):
        """Widget yeniden boyutlandırıldığında çağrılır."""
        super().resizeEvent(event)
        logging.info(f"DrawingCanvas yeniden boyutlandırıldı: Genişlik={self.width()}px, Yükseklik={self.height()}px")

    def set_page_background_pixmap(self, pixmap: QPixmap, image_path: str | None = None):
        """Sayfaya özel bir arka plan pixmap'i (örn. PDF sayfasından) ayarlar."""
        if pixmap and not pixmap.isNull():
            self._page_background_pixmap = pixmap
            self._has_page_background = True
            if image_path: # YENİ
                self._pdf_background_source_path = image_path # YENİ
            else: # YENİ
                self._pdf_background_source_path = None # YENİ: Eğer yol verilmezse temizle
            logging.info(f"DrawingCanvas ({id(self)}): Özel sayfa arka planı ayarlandı. _has_page_background = {self._has_page_background}. Pixmap boyutu: {pixmap.size()}. Kaynak Yolu: {self._pdf_background_source_path}")
            self.setMinimumSize(pixmap.size())
            self.update() 
            self.updateGeometry() # Geometri güncellemesini iste
            self.adjustSize() # Boyutu içeriğe göre ayarla
        else:
            self._page_background_pixmap = None
            self._has_page_background = False
            self._pdf_background_source_path = None # YENİ: Arka plan kaldırılırsa yolu da temizle
            logging.warning(f"DrawingCanvas ({id(self)}): set_page_background_pixmap çağrıldı ama pixmap geçersiz. Özel arka plan kaldırıldı. _has_page_background = {self._has_page_background}")
            self.load_background_template_image() # Özel arka plan yoksa şablonu yükle
            self.update()
            self.updateGeometry()
            self.adjustSize()
    # --- --- --- --- --- --- --- --- --- --- --- -- #

    def sizeHint(self) -> QSize:
        """Widget için ideal boyutu döndürür (zoom dikkate alınmadan, temel boyut)."""
        base_size = QSize(600, 800) # Varsayılan boyut
        current_pixmap_to_use = None

        if self._has_page_background and self._page_background_pixmap and not self._page_background_pixmap.isNull():
            current_pixmap_to_use = self._page_background_pixmap
        elif self._background_pixmap and not self._background_pixmap.isNull():
            current_pixmap_to_use = self._background_pixmap
        
        if current_pixmap_to_use:
            base_size = current_pixmap_to_use.size()
        
        # logging.debug(f"sizeHint: base_size={base_size} (zoom dikkate alınmadı)") # Yorum satırı yapıldı
        return base_size

    def minimumSizeHint(self) -> QSize:
        """Widget için minimum ideal boyutu döndürür."""
        # Genellikle sizeHint ile aynı olabilir veya daha küçük bir alt sınır belirlenebilir.
        return self.sizeHint()

    # YENİ: Olay Filtresi Metodu
    def eventFilter(self, source, event: QEvent) -> bool:
        # logging.debug(f"DrawingCanvas EventFilter: Source={type(source).__name__}, EventType={event.type()}") # Yorum satırı yapıldı
        if isinstance(event, QTouchEvent):
            # logging.debug("Touch event received in DrawingCanvas eventFilter") # Yorum satırı yapıldı
            self.touchEvent(event)
            return True 
        
        return super().eventFilter(source, event)

    # Mevcut Dokunma Olayı İşleyicisi (eventFilter tarafından çağrılacak)
    def touchEvent(self, event: QTouchEvent):
        touch_points = event.points()
        if not touch_points:
            event.ignore()
            return

        from PyQt6.QtGui import QEventPoint
        if self._parent_page is None:
            logging.error(f"touchEvent received but self._parent_page is None! Ignoring event.")
            event.ignore()
            return

        # İki veya daha fazla parmakla dokunma olayı
        if len(touch_points) >= 2:
            # İki parmağın pozisyonlarını al
            p1, p2 = touch_points[0], touch_points[1]
            
            # Ekran koordinatlarını dünya koordinatlarına çevir
            pos1_screen = p1.position()
            pos2_screen = p2.position()
            
            # İki parmağın ortası (ekran koordinatlarında)
            center_screen = QPointF((pos1_screen.x() + pos2_screen.x()) / 2.0, 
                                 (pos1_screen.y() + pos2_screen.y()) / 2.0)
            
            # Dünya koordinatlarına çevir
            pos1_world = self.screen_to_world(pos1_screen)
            pos2_world = self.screen_to_world(pos2_screen)
            center_world = self.screen_to_world(center_screen)
            
            # İki parmak arası mesafe (ekran pikseli cinsinden)
            dist_screen = (pos1_screen - pos2_screen).manhattanLength()
            
            # Pinch başlangıcı
            if not self._pinch_active:
                self._last_pinch_dist = dist_screen
                self._last_pinch_center = center_world
                self._pinch_active = True
                logging.debug(f"Pinch başladı: dist={dist_screen}, center={center_world}")
            else:
                # Aktif pinch hareketi - zoom ve pan uygula
                if self._last_pinch_dist and self._last_pinch_dist > 0:
                    # Zoom faktörünü hesapla (küçük değişimler için daha hassas)
                    scale_factor = (dist_screen / self._last_pinch_dist)
                    
                    # Üstel bir eğri kullanarak ani/büyük değişimleri yumuşat
                    # Daha küçük üs daha yavaş değişim demektir (0.3 yerine 0.2 kullanıyoruz)
                    scale = scale_factor ** 0.2
                    
                    # Mevcut ve yeni zoom değerleri
                    old_zoom = self._parent_page.zoom_level
                    new_zoom = max(0.1, min(10.0, old_zoom * scale))
                    
                    # Pan kaydırma miktarını hesapla
                    # Merkezler arasındaki farkı kullan, küçük değişimler için daha büyük etki
                    delta = (center_world - self._last_pinch_center) * 0.8
                    
                    # Değişiklikleri uygula
                    self._parent_page.zoom_level = new_zoom
                    self._parent_page.pan_offset -= delta
                    
                    # Yeni değerleri kaydet
                    self._last_pinch_dist = dist_screen
                    self._last_pinch_center = center_world
                    
                    # Loglama
                    logging.debug(f"Pinch güncellendi: scale={scale:.2f}, yeni zoom={new_zoom:.2f}, delta={delta}")
                    
                    # Ekranı güncelle
                    self.update()
            
            # İki parmak işlemi tamamlandı, başka işleyicilere gönderme
            event.accept()
            return
        else:
            # Pinch işlemi bitti, değişkenleri temizle
            self._pinch_active = False
            self._last_pinch_dist = None
            self._last_pinch_center = None

        # Tek parmak ile dokunma olayını tablet olayına dönüştür ve işle
        primary_point = touch_points[0]
        world_pos = self.screen_to_world(primary_point.position()) 
        state = primary_point.state()
        fake_event = FakeTabletEventFromTouch(event, primary_point)

        if state == QEventPoint.State.Pressed:
            canvas_tablet_handler.handle_tablet_press(self, world_pos, fake_event)
        elif state == QEventPoint.State.Updated:
            canvas_tablet_handler.handle_tablet_move(self, world_pos, fake_event)
        elif state == QEventPoint.State.Released:
            canvas_tablet_handler.handle_tablet_release(self, world_pos, fake_event)
        else:
            event.ignore()
            return
        
        self.update()
        event.accept()

    def _handle_pen_release(self, pos: QPointF):
        # logging.debug(f"_handle_pen_release: Drawing={self.drawing}, TempErasing={self.temporary_erasing}, WorldPos={pos}") # KALDIRILDI
        if self.temporary_erasing and self.current_eraser_path:
            # ... (mevcut silme kodu aynı kalır) ...
            self.current_eraser_path = []
            self.drawing = False
            self.current_line_points = []
        elif self.drawing and self.current_line_points:
            # logging.debug("Pen Release: Finalizing drawing line.") # KALDIRILDI
            if len(self.current_line_points) > 1:
                final_points = [QPointF(p.x(), p.y()) for p in self.current_line_points]
                line_data = [
                    self.current_color,
                    self.current_pen_width,
                    final_points,
                    self.line_style
                ]
                command = DrawLineCommand(self, line_data)
                self.undo_manager.execute(command)
                # logging.debug(f"Pen Release: DrawLineCommand executed with {len(final_points)} points.") # KALDIRILDI
            else:
                # logging.debug("Pen Release: Line too short, not added to commands.") # KALDIRILDI
                pass
            self.drawing = False
            self.current_line_points = []
        # ... (mevcut kodun geri kalanı aynı) ...

    def _handle_shape_release(self, pos: QPointF):
        if self.drawing_shape:
            self.shape_end_point = pos
            current_tool_name_for_log = "Unknown"
            try:
                current_tool_name_for_log = self.current_tool.name
            except AttributeError:
                current_tool_name_for_log = str(self.current_tool)
            # logging.debug(f"Shape Release: Finalizing {current_tool_name_for_log} from {self.shape_start_point} to {self.shape_end_point}") # KALDIRILDI
            
            if (self.shape_end_point - self.shape_start_point).manhattanLength() > 2:
                shape_data = [
                    self.current_tool,
                    self.current_color,
                    self.current_pen_width,
                    self.shape_start_point,
                    self.shape_end_point,
                    self.line_style
                ]
                # logging.debug(f"  Initial shape_data (len: {len(shape_data)}): {shape_data}") # KALDIRILDI

                if self.current_tool == ToolType.RECTANGLE or self.current_tool == ToolType.CIRCLE:
                    # logging.debug(f"    Tool is {self.current_tool.name}. Preparing to add RGBA.") # KALDIRILDI
                    fill_r, fill_g, fill_b, fill_a = self.current_fill_rgba
                    actual_fill_a = fill_a if self.fill_enabled else 0.0
                    actual_fill_rgba_tuple = (fill_r, fill_g, fill_b, actual_fill_a)
                    shape_data.append(actual_fill_rgba_tuple)
                    # logging.debug(f"    RGBA appended. Shape_data is now (len: {len(shape_data)}): {shape_data}") # KALDIRILDI
                else:
                    # logging.debug(f"    Tool is {self.current_tool.name}. RGBA not added.") # KALDIRILDI
                    pass
                
                final_len = len(shape_data)
                # logging.debug(f"  Final shape_data before creating command (len: {final_len}): {shape_data}") # KALDIRILDI
                
                tool_type_cmd = shape_data[0]
                color_cmd = shape_data[1]
                width_cmd = shape_data[2]
                p1_cmd = shape_data[3]
                p2_cmd = shape_data[4]
                line_style_cmd = shape_data[5]
                fill_rgba_cmd = shape_data[6] if final_len > 6 else None

                command = DrawShapeCommand(self, 
                                         tool_type_cmd, color_cmd, width_cmd, 
                                         p1_cmd, p2_cmd, line_style_cmd, 
                                         fill_rgba_cmd)
                
                try:
                    command_data_len_check = len(command.shape_data) if hasattr(command, 'shape_data') and command.shape_data is not None else 'N/A'
                    # logging.debug(f"    Shape data INSIDE created command object (len: {command_data_len_check}): {getattr(command, 'shape_data', 'N/A')}") # KALDIRILDI
                    if (tool_type_cmd == ToolType.RECTANGLE or tool_type_cmd == ToolType.CIRCLE) and command_data_len_check != 7:
                         logging.error(f"    !!!! HATA: Komut içindeki shape_data beklenen uzunlukta değil (Beklenen 7, Gelen {command_data_len_check}) !!!!") # HATA LOGU KALABİLİR
                except AttributeError:
                     logging.error("    Could not access command.shape_data after creation.") # HATA LOGU KALABİLİR
                
                self.undo_manager.execute(command)
                if self._parent_page: 
                    self._parent_page.mark_as_modified()
                # logging.debug(f"Shape Release: DrawShapeCommand executed for {current_tool_name_for_log}.") # KALDIRILDI
            else:
                # logging.debug("Shape Release: Shape too small, not creating command.") # KALDIRILDI
                pass
            
            self.drawing_shape = False
            self.shape_start_point = QPointF()
            self.shape_end_point = QPointF()
            self.update()
        elif self.drawing and self.current_tool == ToolType.PEN and len(self.current_line_points) > 1:
            line_data_final_pen = [self.current_color, self.current_pen_width, self.current_line_points, self.line_style]
            command_pen = DrawLineCommand(self, line_data_final_pen)
            self.undo_manager.execute(command_pen)
            if self._parent_page: self._parent_page.mark_as_modified()
            self.drawing = False
            self.current_line_points = []
            self.update()
            # logging.debug(f"Pen Release: DrawLineCommand executed. Style: {self.line_style}") # KALDIRILDI

    @property
    def selected_item_indices(self):
        return self._selected_item_indices

    @selected_item_indices.setter
    def selected_item_indices(self, value):
        self._selected_item_indices = value
        self.selection_changed.emit()

    def set_fill_rgba(self, rgba_tuple):
        self.current_fill_rgba = rgba_tuple

    def set_fill_enabled(self, enabled: bool):
        self.fill_enabled = enabled
        self.update()

    def update(self, *args, **kwargs):
        # logging.debug(f"[drawing_canvas] update: shapes id={id(self.shapes)}, içerik={self.shapes}")
        super().update(*args, **kwargs)
        
    # --- YENİ: Tutamaçları güncelle ---
    def update_current_handles(self):
        """
        Seçili öğelerin tutamaçlarını hesaplar ve current_handles sözlüğüne ekler.
        Bu metot, seçilmiş öğelerin boyutu veya konumu değiştiğinde çağrılmalıdır.
        """
        self.current_handles.clear()  # Mevcut tutamaçları temizle
        
        if not self.selected_item_indices:
            return  # Seçili öğe yoksa işlem yapma
            
        # Kombine bbox'u hesapla
        bbox = self._get_combined_bbox([])
        if bbox.isNull() or not bbox.isValid():
            return
            
        # Eğer tek bir resim seçiliyse ve açısı varsa, döndürülmüş tutamaçları hesapla
        if len(self.selected_item_indices) == 1 and self.selected_item_indices[0][0] == 'images':
            item_type, index = self.selected_item_indices[0]
            if self._parent_page and index < len(self._parent_page.images):
                img_data = self._parent_page.images[index]
                angle = img_data.get('angle', 0.0)
                rect = img_data.get('rect')
                
                if rect and not rect.isNull() and rect.isValid():
                    # Döndürülmüş tutamaçları hesapla
                    from utils import selection_helpers
                    handle_positions_world = selection_helpers.calculate_handle_positions_for_rotated_rect(rect, angle)
                    
                    # Tutamaçları ekrana dönüştür ve sakla
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    
                    for handle_type, pos_world in handle_positions_world.items():
                        pos_screen = self.world_to_screen(pos_world)
                        handle_rect_screen = QRectF(
                            pos_screen.x() - half_handle_screen,
                            pos_screen.y() - half_handle_screen,
                            handle_size_screen,
                            handle_size_screen
                        )
                        self.current_handles[handle_type] = handle_rect_screen
                    return
                
        # Normal dikdörtgen tutamaçları hesapla (standart öğeler için)
        from utils import geometry_helpers
        handle_positions_world = geometry_helpers.get_standard_handle_positions(bbox)
        
        # Tutamaçları ekrana dönüştür ve sakla
        from utils import selection_helpers
        handle_size_screen = selection_helpers.HANDLE_SIZE
        half_handle_screen = handle_size_screen / 2.0
        
        for handle_type, pos_world in handle_positions_world.items():
            pos_screen = self.world_to_screen(pos_world)
            handle_rect_screen = QRectF(
                pos_screen.x() - half_handle_screen,
                pos_screen.y() - half_handle_screen,
                handle_size_screen,
                handle_size_screen
            )
            self.current_handles[handle_type] = handle_rect_screen
    # --- --- --- --- --- --- --- ---
        
    def _snap_point_to_grid(self, point: QPointF) -> QPointF:
        """Verilen noktayı grid'e en yakın noktaya yuvarlar."""
        spacing = self.grid_spacing_pt * PT_TO_PX
        if spacing <= 0:
            return point
        x = round(point.x() / spacing) * spacing
        y = round(point.y() / spacing) * spacing
        return QPointF(x, y)

    def apply_grid_settings(self, settings_dict):
        print('[DEBUG] apply_grid_settings çağrıldı:', settings_dict)
        import logging
        logging.info(f'[DEBUG] apply_grid_settings çağrıldı: {settings_dict}')
        
        self.grid_thick_line_interval = settings_dict.get('grid_thick_line_interval', getattr(self, 'grid_thick_line_interval', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_line_interval']))
        
        raw_thin_color = settings_dict.get('grid_thin_color', getattr(self, 'grid_thin_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color']))
        if isinstance(raw_thin_color, list) and len(raw_thin_color) == 4 and all(isinstance(x, (int, float)) for x in raw_thin_color): # Gelen [200,200,220,100] veya [0.7,0.7,0.8,0.4] olabilir
            if all(isinstance(x, int) for x in raw_thin_color): # int ise 0-255 aralığında
                 self.grid_thin_color = tuple(c/255.0 for c in raw_thin_color)
            else: # float ise 0-1 aralığında varsayılır
                 self.grid_thin_color = tuple(float(c) for c in raw_thin_color)
        elif isinstance(raw_thin_color, tuple) and len(raw_thin_color) == 4 and all(isinstance(x, float) for x in raw_thin_color): # Zaten (0.7,0.7,0.8,0.4) ise
            self.grid_thin_color = raw_thin_color
        else:
            self.grid_thin_color = getattr(self, 'grid_thin_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color']) # Mevcut değeri koru veya varsayılana dön
            logging.warning(f"apply_grid_settings: Beklenmeyen grid_thin_color formatı: {raw_thin_color}, varsayılan/mevcut kullanıldı.")

        raw_thick_color = settings_dict.get('grid_thick_color', getattr(self, 'grid_thick_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color']))
        if isinstance(raw_thick_color, list) and len(raw_thick_color) == 4 and all(isinstance(x, (int, float)) for x in raw_thick_color):
            if all(isinstance(x, int) for x in raw_thick_color):
                 self.grid_thick_color = tuple(c/255.0 for c in raw_thick_color)
            else:
                 self.grid_thick_color = tuple(float(c) for c in raw_thick_color)
        elif isinstance(raw_thick_color, tuple) and len(raw_thick_color) == 4 and all(isinstance(x, float) for x in raw_thick_color):
            self.grid_thick_color = raw_thick_color
        else:
            self.grid_thick_color = getattr(self, 'grid_thick_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color'])
            logging.warning(f"apply_grid_settings: Beklenmeyen grid_thick_color formatı: {raw_thick_color}, varsayılan/mevcut kullanıldı.")

        self.grid_thin_width = settings_dict.get('grid_thin_width', getattr(self, 'grid_thin_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_width']))
        self.grid_thick_width = settings_dict.get('grid_thick_width', getattr(self, 'grid_thick_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_width']))
        self.grid_apply_to_all_pages = settings_dict.get('grid_apply_to_all_pages', getattr(self, 'grid_apply_to_all_pages', CANVAS_DEFAULT_GRID_SETTINGS['grid_apply_to_all_pages']))
        self.grid_show_for_line_tool_only = settings_dict.get('grid_show_for_line_tool_only', getattr(self, 'grid_show_for_line_tool_only', CANVAS_DEFAULT_GRID_SETTINGS['grid_show_for_line_tool_only']))
        self.snap_lines_to_grid = settings_dict.get('grid_snap_enabled', getattr(self, 'snap_lines_to_grid', CANVAS_DEFAULT_GRID_SETTINGS['grid_snap_enabled']))
        self.grid_visible_on_snap = settings_dict.get('grid_visible_on_snap', getattr(self, 'grid_visible_on_snap', CANVAS_DEFAULT_GRID_SETTINGS['grid_visible_on_snap']))
        self.update()

    def _update_pointer_trail(self):
        if self.current_tool == ToolType.TEMPORARY_POINTER:
            now = time.time()
            self.pointer_trail_points = [(p, t) for (p, t) in self.pointer_trail_points if now - t < self.pointer_trail_duration]
            self.update()

    def mousePressEvent(self, event):
        if self.current_tool == ToolType.TEMPORARY_POINTER and event.button() == Qt.MouseButton.LeftButton:
            logging.info(f"Mouse PRESS for TEMPORARY_POINTER at {event.position()}")
            self.pointer_trail_points = [(event.position(), time.time())]
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_tool == ToolType.TEMPORARY_POINTER and event.buttons() & Qt.MouseButton.LeftButton:
            logging.info(f"Mouse MOVE for TEMPORARY_POINTER at {event.position()}")
            self.pointer_trail_points.append((event.position(), time.time()))
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_tool == ToolType.TEMPORARY_POINTER and event.button() == Qt.MouseButton.LeftButton:
            logging.info(f"Mouse RELEASE for TEMPORARY_POINTER at {event.position()}")
            pass  # Çizim bitince iz fade-out ile silinecek
        # --- RESİM TAŞIMA --- #
        if self.moving_selection and self.selected_item_indices:
            # Sadece resim seçiliyse ve hareket olduysa komut oluştur
            if len(self.selected_item_indices) == 1 and self.selected_item_indices[0][0] == 'images' and self._parent_page:
                import copy
                from utils.commands import MoveItemsCommand
                indices_copy = copy.deepcopy(self.selected_item_indices)
                original_states = getattr(self, 'move_original_states', [])
                final_states = self._get_current_selection_states(self._parent_page)
                if original_states and final_states and original_states != final_states:
                    command = MoveItemsCommand(self, indices_copy, original_states, final_states)
                    self._parent_page.get_undo_manager().execute(command)
            self.moving_selection = False
            self.move_original_states = []
        # --- RESİM BOYUTLANDIRMA --- #
        if self.resizing_selection and self.selected_item_indices:
            if len(self.selected_item_indices) == 1 and self.selected_item_indices[0][0] == 'images' and self._parent_page:
                import copy
                from utils.commands import ResizeItemsCommand
                indices_copy = copy.deepcopy(self.selected_item_indices)
                original_states = getattr(self, 'original_resize_states', [])
                final_states = self._get_current_selection_states(self._parent_page)
                if original_states and final_states and original_states != final_states:
                    command = ResizeItemsCommand(self, indices_copy, original_states, final_states)
                    self._parent_page.get_undo_manager().execute(command)
            self.resizing_selection = False
            self.original_resize_states = []
        # ... mevcut kod ...
        super().mouseReleaseEvent(event)

    def _calculate_final_states_for_move(self, original_states: List[Any], 
                                         selected_indices: List[Tuple[str, int]], 
                                         dx: float, dy: float) -> List[Any]:
        final_states = []
        if len(original_states) != len(selected_indices):
            logging.error("_calculate_final_states_for_move: original_states ve selected_indices uzunlukları farklı!")
            return [copy.deepcopy(s) for s in original_states] 

        for i, (item_type, index) in enumerate(selected_indices):
            initial_item_state = original_states[i]
            if initial_item_state is None:
                final_states.append(None)
                continue

            final_item_state_data = copy.deepcopy(initial_item_state)

            if item_type == 'lines':
                if len(initial_item_state) > 2 and isinstance(initial_item_state[2], list):
                    original_points = initial_item_state[2]
                    if all(isinstance(p, QPointF) for p in original_points):
                        final_points = [QPointF(p.x() + dx, p.y() + dy) for p in original_points]
                        final_item_state_data[2] = final_points
                    else:
                        logging.warning(f"_calculate_final_states: lines[{index}] için initial_item_state[2] (points) QPointF listesi değil.")
                else:
                    logging.warning(f"_calculate_final_states: lines[{index}] için initial_item_state formatı beklenmedik.")
            
            elif item_type == 'shapes':
                shape_tool_type = initial_item_state[0]
                if shape_tool_type == ToolType.EDITABLE_LINE:
                    if len(initial_item_state) > 3 and isinstance(initial_item_state[3], list):
                        original_control_points = initial_item_state[3]
                        if all(isinstance(p, QPointF) for p in original_control_points):
                            final_control_points = [QPointF(p.x() + dx, p.y() + dy) for p in original_control_points]
                            final_item_state_data[3] = final_control_points
                        else:
                            logging.warning(f"_calculate_final_states: EDITABLE_LINE[{index}] için control_points QPointF listesi değil.")
                    else:
                        logging.warning(f"_calculate_final_states: EDITABLE_LINE[{index}] için initial_item_state formatı beklenmedik.")
                else: 
                    if len(initial_item_state) > 4 and isinstance(initial_item_state[3], QPointF) and isinstance(initial_item_state[4], QPointF):
                        original_p1 = initial_item_state[3]
                        original_p2 = initial_item_state[4]
                        final_item_state_data[3] = QPointF(original_p1.x() + dx, original_p1.y() + dy)
                        final_item_state_data[4] = QPointF(original_p2.x() + dx, original_p2.y() + dy)
                    else:
                        logging.warning(f"_calculate_final_states: shapes[{index}] (type: {shape_tool_type}) için initial_item_state formatı beklenmedik veya p1/p2 QPointF değil.")

            elif item_type == 'images':
                if isinstance(initial_item_state, dict) and 'rect' in initial_item_state:
                    original_rect = initial_item_state['rect']
                    if isinstance(original_rect, QRectF):
                        final_rect = QRectF(original_rect)
                        final_rect.translate(dx, dy)
                        final_item_state_data['rect'] = final_rect
                    else:
                        logging.warning(f"_calculate_final_states: images[{index}] için 'rect' QRectF değil.")
                else:
                    logging.warning(f"_calculate_final_states: images[{index}] için initial_item_state dict değil veya 'rect' anahtarı yok.")
            
            elif item_type == 'bspline_strokes':
                if isinstance(initial_item_state, dict) and 'control_points' in initial_item_state:
                    original_control_points = initial_item_state['control_points']
                    
                    # YENİ: Format kontrolü ve dönüşüm
                    if isinstance(original_control_points, np.ndarray) and original_control_points.ndim == 2 and original_control_points.shape[1] == 2:
                        original_control_points = [np.array(row) for row in original_control_points]
                        
                    if isinstance(original_control_points, list) and original_control_points and all(isinstance(cp, np.ndarray) and cp.shape == (2,) for cp in original_control_points):
                        final_control_points = [
                            np.array([cp[0] + dx, cp[1] + dy]) for cp in original_control_points
                        ]
                        final_item_state_data['control_points'] = final_control_points
                    else:
                        logging.error(f"_calculate_final_states: bspline_strokes[{index}] için 'control_points' ({type(original_control_points)}) beklenen formatta değil (List[np.array]). Veri: {original_control_points}")
                else:
                    logging.warning(f"_calculate_final_states: bspline_strokes[{index}] için initial_item_state dict değil veya 'control_points' anahtarı yok.")
            
            else:
                logging.warning(f"_calculate_final_states_for_move: Bilinmeyen öğe tipi: {item_type}")

            final_states.append(final_item_state_data)
        
        return final_states

    def apply_grid_settings(self, settings_dict):
        # print('[DEBUG] apply_grid_settings çağrıldı:', settings_dict) # Artık logging kullanılıyor
        logging.info(f'[apply_grid_settings] Canvas\'a grid ayarları uygulanıyor: {settings_dict}')
        
        self.grid_thick_line_interval = settings_dict.get('grid_thick_line_interval', getattr(self, 'grid_thick_line_interval', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_line_interval']))
        
        raw_thin_color = settings_dict.get('grid_thin_color', getattr(self, 'grid_thin_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color']))
        if isinstance(raw_thin_color, list) and len(raw_thin_color) == 4 and all(isinstance(x, (int, float)) for x in raw_thin_color):
            if all(isinstance(x, int) for x in raw_thin_color): 
                 self.grid_thin_color = tuple(c/255.0 for c in raw_thin_color)
            else: 
                 self.grid_thin_color = tuple(float(c) for c in raw_thin_color)
        elif isinstance(raw_thin_color, tuple) and len(raw_thin_color) == 4 and all(isinstance(x, float) for x in raw_thin_color):
            self.grid_thin_color = raw_thin_color
        else:
            self.grid_thin_color = getattr(self, 'grid_thin_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color'])
            logging.warning(f"apply_grid_settings: Beklenmeyen grid_thin_color formatı: {raw_thin_color}, varsayılan/mevcut kullanıldı.")

        raw_thick_color = settings_dict.get('grid_thick_color', getattr(self, 'grid_thick_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color']))
        if isinstance(raw_thick_color, list) and len(raw_thick_color) == 4 and all(isinstance(x, (int, float)) for x in raw_thick_color):
            if all(isinstance(x, int) for x in raw_thick_color):
                 self.grid_thick_color = tuple(c/255.0 for c in raw_thick_color)
            else:
                 self.grid_thick_color = tuple(float(c) for c in raw_thick_color)
        elif isinstance(raw_thick_color, tuple) and len(raw_thick_color) == 4 and all(isinstance(x, float) for x in raw_thick_color):
            self.grid_thick_color = raw_thick_color
        else:
            self.grid_thick_color = getattr(self, 'grid_thick_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color'])
            logging.warning(f"apply_grid_settings: Beklenmeyen grid_thick_color formatı: {raw_thick_color}, varsayılan/mevcut kullanıldı.")

        self.grid_thin_width = settings_dict.get('grid_thin_width', getattr(self, 'grid_thin_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_width']))
        self.grid_thick_width = settings_dict.get('grid_thick_width', getattr(self, 'grid_thick_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_width']))
        self.grid_apply_to_all_pages = settings_dict.get('grid_apply_to_all_pages', getattr(self, 'grid_apply_to_all_pages', CANVAS_DEFAULT_GRID_SETTINGS['grid_apply_to_all_pages']))
        self.grid_show_for_line_tool_only = settings_dict.get('grid_show_for_line_tool_only', getattr(self, 'grid_show_for_line_tool_only', CANVAS_DEFAULT_GRID_SETTINGS['grid_show_for_line_tool_only']))
        self.snap_lines_to_grid = settings_dict.get('grid_snap_enabled', getattr(self, 'snap_lines_to_grid', CANVAS_DEFAULT_GRID_SETTINGS['grid_snap_enabled']))
        self.grid_visible_on_snap = settings_dict.get('grid_visible_on_snap', getattr(self, 'grid_visible_on_snap', CANVAS_DEFAULT_GRID_SETTINGS['grid_visible_on_snap']))
        
        logging.info(f"[apply_grid_settings] Grid ayarları uygulandı. Snap: {self.snap_lines_to_grid}, Visible on Snap: {self.grid_visible_on_snap}")
        self.update()

    def invalidate_cache(self, reason: str = ""): 
        """Cache'i geçersiz kılar, bir sonraki paint'te güncellenir. Sebep loglanır."""
        #logging.info(f"[CACHE] invalidate_cache çağrıldı. Sebep: {reason}, Önceki dirty={self._cache_dirty}")
        self._cache_dirty = True
        #logging.info(f"[CACHE] invalidate_cache sonrası dirty={self._cache_dirty}")
        self.update()

    def _update_static_content_cache(self):
        """Sabit içerik cache'ini günceller. Log eklenir."""
        if self.width() <= 0 or self.height() <= 0:
            #logging.info("[CACHE] _update_static_content_cache: Boyutlar geçersiz, cache güncellenmedi.")
            return
        dpr = self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0
        cache_size = self.size() * dpr
        # Transparanlık gereksinimine göre format seç
        needs_alpha = self.background_color[3] < 1.0 if len(self.background_color) > 3 else False
        from PyQt6.QtGui import QImage
        if needs_alpha:
            img_format = QImage.Format.Format_ARGB32_Premultiplied
            format_name = "ARGB32_Premultiplied"
        else:
            img_format = QImage.Format.Format_RGB32
            format_name = "RGB32"
        image = QImage(int(cache_size.width()), int(cache_size.height()), img_format)
        image.setDevicePixelRatio(dpr)
        image.fill(rgba_to_qcolor(self.background_color))
        with QPainter(image) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            if self._has_page_background and self._page_background_pixmap and not self._page_background_pixmap.isNull():
                painter.drawPixmap(0, 0, self._page_background_pixmap)
            elif self._background_pixmap and not self._background_pixmap.isNull():
                painter.drawPixmap(0, 0, self._background_pixmap)
            canvas_drawing_helpers.draw_items(self, painter)
            canvas_drawing_helpers.draw_grid_and_template(self, painter)
        pixmap = QPixmap.fromImage(image)
        self._static_content_cache = pixmap
        self._cache_dirty = False
        #logging.info(f"[CACHE] _update_static_content_cache: Cache güncellendi. DPI: {dpr}, Boyut: {self.size().width()}x{self.size().height()}, Format: {format_name}")
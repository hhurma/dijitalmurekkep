from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QWidget, QSizePolicy, QApplication
from PyQt6.QtGui import QColor, QTabletEvent, QPainter, QPen, QBrush, QCursor, QPaintEvent, QPainterPath, QRadialGradient, QPixmap, QVector2D, QTransform, QTouchEvent, QEventPoint
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QSize, QEvent
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
from utils import geometry_helpers, erasing_helpers 
from utils import view_helpers 
from utils.commands import (
    DrawLineCommand, ClearCanvasCommand, DrawShapeCommand, MoveItemsCommand,
    ResizeItemsCommand, EraseCommand, RotateItemsCommand 
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


class DrawingCanvas(QWidget):
    content_changed = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self, undo_manager: UndoRedoManager, parent=None, template_settings: dict | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.installEventFilter(self)
        self.RESIZE_MOVE_THRESHOLD = 3.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.white)
        self.setPalette(palette)
        
        self.undo_manager = undo_manager
        self._parent_page: 'Page' | None = None
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
        self.move_start_point = QPointF()
        self.resize_start_pos = QPointF()
        self.rotation_start_pos_world = QPointF() 
        self.rotation_center_world = QPointF() 
        self.grabbed_handle_type: str | None = None
        self.resize_original_bbox = QRectF()
        self.lines: List[List[Any]] = []
        self.shapes: List[List[Any]] = []
        self.current_line_points: List[QPointF] = []
        self.current_eraser_path: List[QPointF] = [] 
        self.erased_this_stroke: List[Tuple[str, int, Any]] = [] 
        self.shape_start_point = QPointF()
        self.shape_end_point = QPointF()
        self._selected_item_indices: List[Tuple[str, int]] = []
        self.last_move_pos = QPointF()
        self.current_handles: dict[str, QRectF] = {}
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
        # logging.debug(f"PaintEvent - Grid Ayarları: ThinColor={getattr(self, 'grid_thin_color', 'Yok')}, ThickInterval={getattr(self, 'grid_thick_line_interval', 'Yok')}")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Arka Plan Çizimi
        if self._has_page_background and self._page_background_pixmap and not self._page_background_pixmap.isNull():
            if self._parent_page: # parent_page varsa zoom ve pan bilgilerini al
                zoom = self._parent_page.zoom_level
                pan_offset_x = self._parent_page.pan_offset.x()
                pan_offset_y = self._parent_page.pan_offset.y()

                target_w = int(self._page_background_pixmap.width() * zoom)
                target_h = int(self._page_background_pixmap.height() * zoom)
                
                # PDF'in sol üst köşesinin canvas üzerinde nereye geleceğini hesapla
                # Pan ofseti, PDF'in ne kadar kaydırılacağını belirtir.
                # Pozitif pan_offset_x, PDF'i sola kaydırır (içerik sağa gider)
                # Pozitif pan_offset_y, PDF'i yukarı kaydırır (içerik aşağı gider)
                draw_x = -pan_offset_x 
                draw_y = -pan_offset_y

                target_rect = QRectF(draw_x, draw_y, target_w, target_h)
                source_rect = QRectF(self._page_background_pixmap.rect()) # QRectF'ye dönüştürüldü
                painter.drawPixmap(target_rect, self._page_background_pixmap, source_rect)
            else: # parent_page yoksa (olmamalı ama), normal çiz
                 painter.drawPixmap(self.rect(), self._page_background_pixmap)
        elif self._background_pixmap and not self._background_pixmap.isNull():
            painter.drawPixmap(self.rect(), self._background_pixmap)
        else:
            painter.fillRect(self.rect(), Qt.GlobalColor.white)
        # Öğeleri Çiz
        canvas_drawing_helpers.draw_items(self, painter)
        # Geçici Çizimler
        if self.drawing:
            if self.current_tool == ToolType.PEN:
                if len(self.current_line_points) > 1:
                    utils_drawing_helpers.draw_pen_stroke(painter, self.current_line_points, self.current_color, self.current_pen_width, self.line_style)
            elif self.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                 if self.drawing_shape and not self.shape_start_point.isNull() and not self.shape_end_point.isNull():
                    temp_shape_data = [self.current_tool, self.current_color, self.current_pen_width, self.shape_start_point, self.shape_end_point, self.line_style]
                    if self.current_tool in [ToolType.RECTANGLE, ToolType.CIRCLE] and self.fill_enabled:
                        fill_r, fill_g, fill_b, fill_a = self.current_fill_rgba
                        actual_fill_rgba_tuple = (fill_r, fill_g, fill_b, fill_a) # temporary alpha is always the chosen alpha
                        temp_shape_data.append(actual_fill_rgba_tuple)
                    utils_drawing_helpers.draw_shape(painter, temp_shape_data, self.line_style)
            # --- YENİ: Düzenlenebilir Çizgi Aracı Çizimi --- #
            elif self.current_tool == ToolType.EDITABLE_LINE:
                # Önce kontur noktaları her durumda çizelim (bezier kontrol noktaları olmasa bile)
                pen = QPen(QColor.fromRgbF(*self.current_color), self.current_pen_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                
                # Düz çizgi olarak çiz (her zaman görünür olmalı)
                if len(self.current_editable_line_points) > 0:
                    path = QPainterPath()
                    if len(self.current_editable_line_points) == 1:
                        # Tek nokta varsa küçük bir daire çiz
                        painter.drawEllipse(self.current_editable_line_points[0], 2, 2)
                    else:
                        # Noktaları birleştiren düz çizgiler çiz
                        path.moveTo(self.current_editable_line_points[0])
                        for point in self.current_editable_line_points[1:]:
                            path.lineTo(point)
                        painter.drawPath(path)
                
                # Daha sonra bezier eğrisi varsa onu çiz
                if len(self.bezier_control_points) >= 4:
                    path = QPainterPath()
                    path.moveTo(self.bezier_control_points[0])  # İlk nokta
                    
                    # Tüm bezier segmentlerini çiz
                    for i in range(0, len(self.bezier_control_points) - 3, 3):
                        # Eğer bir bezier eğrisi segmenti için yeterli nokta varsa
                        if i + 3 < len(self.bezier_control_points):
                            # Her segment: [p0, c1, c2, p1]
                            # p0 zaten path içindedir, c1, c2 ve p1 ile kubik bezier oluştur
                            path.cubicTo(
                                self.bezier_control_points[i + 1],  # c1
                                self.bezier_control_points[i + 2],  # c2
                                self.bezier_control_points[i + 3]   # p1
                            )
                    
                    # Eğriyi önceki çizginin üzerine çiz
                    painter.drawPath(path)
                
                # Çizgi üzerindeki ana tutamaçları (handle) çiz
                for i, point in enumerate(self.current_editable_line_points):
                    if i == self.active_handle_index:
                        # Aktif tutamaç farklı renkte
                        painter.setBrush(QBrush(QColor(255, 0, 0, 180)))
                    else:
                        painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                    painter.setPen(QPen(QColor(255, 255, 255), 1.5))
                    painter.drawEllipse(point, HANDLE_SIZE/2, HANDLE_SIZE/2)
                
                # Bezier kontrol noktalarını çiz
                if len(self.bezier_control_points) >= 4:
                    # Tüm bezier kontrol noktaları için kontrol çizgilerini ve noktaları çiz
                    for i in range(0, len(self.bezier_control_points) - 3, 3):
                        # Kontrol çizgilerini çiz (p0->c1 ve c2->p1)
                        if i + 3 < len(self.bezier_control_points):
                            painter.setPen(QPen(QColor(120, 120, 120, 150), 1, Qt.PenStyle.DashLine))
                            painter.drawLine(self.bezier_control_points[i], self.bezier_control_points[i + 1])  # p0->c1
                            painter.drawLine(self.bezier_control_points[i + 2], self.bezier_control_points[i + 3])  # c2->p1
                            
                            # Kontrol noktalarını çiz (c1, c2)
                            for j in range(1, 3):
                                ctrl_idx = i + j
                                if ctrl_idx == self.active_bezier_handle_index:
                                    painter.setBrush(QBrush(QColor(255, 165, 0, 180)))  # Aktif kontrol noktası turuncu
                                else:
                                    painter.setBrush(QBrush(QColor(120, 120, 120, 180)))
                                
                                painter.setPen(QPen(QColor(255, 255, 255), 1.5))
                                painter.drawEllipse(self.bezier_control_points[ctrl_idx], HANDLE_SIZE/3, HANDLE_SIZE/3)
        # Mevcut Geçici İşaretçi Çizgisi
        if len(self.current_temporary_line_points) > 1:
            temp_color = (self.temp_pointer_color.redF(), self.temp_pointer_color.greenF(), 
                          self.temp_pointer_color.blueF(), self.temp_pointer_color.alphaF())
            temp_width = self.temp_pointer_width
            utils_drawing_helpers.draw_temporary_pointer_stroke(painter, 
                                                           self.current_temporary_line_points, 
                                                           temp_color, 
                                                           temp_width, 
                                                           self.temporary_line_duration,
                                                           self.temp_glow_width_factor,
                                                           self.temp_core_width_factor,
                                                           self.temp_glow_alpha_factor,
                                                           self.temp_core_alpha_factor)
        # --- YENİ: finalize edilmiş geçici pointer çizgilerini çiz ---
        if hasattr(self, 'temporary_lines'):
            for line in self.temporary_lines:
                line_points, color_tuple, width = line[0], line[1], line[2]
                utils_drawing_helpers.draw_temporary_pointer_stroke(
                    painter,
                    line_points,
                    color_tuple,
                    width,
                    self.temporary_line_duration,
                    self.temp_glow_width_factor,
                    self.temp_core_width_factor,
                    self.temp_glow_alpha_factor,
                    self.temp_core_alpha_factor
                )
        # Geçici Silgi Yolu
        if self.erasing and len(self.current_eraser_path) > 1:
             utils_drawing_helpers.draw_temporary_eraser_path(painter, self.current_eraser_path, self.eraser_width)
        # Ekran Koordinatlarında Çizilecekler
        canvas_drawing_helpers.draw_selection_overlay(self, painter)
        if self.current_tool == ToolType.SELECTOR and self.selecting:
             canvas_drawing_helpers.draw_selection_rectangle(self, painter)
        if self.current_tool == ToolType.ERASER and self.underMouse():
             canvas_drawing_helpers.draw_eraser_preview(self, painter)
        if self.laser_pointer_active and not self.last_cursor_pos_screen.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            center_pos = self.last_cursor_pos_screen
            base_size = self.laser_pointer_size
            radius = base_size * 0.8
            from PyQt6.QtGui import QRadialGradient
            gradient = QRadialGradient(center_pos, radius)
            center_color = QColor(self.laser_pointer_color)
            center_color.setAlpha(220)
            gradient.setColorAt(0.0, center_color)
            mid_color = QColor(self.laser_pointer_color)
            mid_color.setAlpha(100)
            gradient.setColorAt(0.4, mid_color)
            outer_color = QColor(self.laser_pointer_color)
            outer_color.setAlpha(0)
            gradient.setColorAt(1.0, outer_color)
            painter.setBrush(QBrush(gradient))
            painter.drawEllipse(center_pos, radius, radius)
            painter.restore()
        # --- YENİ: Grid Overlay (Çizgiler grid'e uysun seçiliyse) --- #
        grid_show_for_line_tool_only_val = getattr(self, 'grid_show_for_line_tool_only', False)
        grid_visible_on_snap_val = getattr(self, 'grid_visible_on_snap', True)

        show_grid = self.snap_lines_to_grid and self.grid_spacing_pt > 0
        if not grid_visible_on_snap_val: # Eğer görünürlük snap'e bağlı değilse (yani her zaman göster veya asla gösterme gibi bir durum)
            show_grid = False # Ya da bu ayarı farklı bir şekilde mi ele almalıyız? Şimdilik snap'e bağlı değilse göstermiyor.
                               # TODO: grid_visible_on_snap False ise ne olmalı? Belki de bu ayar "grid_visible" olmalıydı.
                               # Şimdilik, eğer grid_visible_on_snap False ise, grid gösterilmeyecek.

        if grid_show_for_line_tool_only_val:
            show_grid = show_grid and self.current_tool == ToolType.LINE
        
        # Önceki show_grid mantığı şuydu: self.snap_lines_to_grid and self.grid_spacing_pt > 0
        # Ve eğer grid_only_line_tool aktifse: show_grid = show_grid and self.current_tool == ToolType.LINE
        # Yeni mantıkta grid_visible_on_snap ayarı da var.
        # Eğer self.snap_lines_to_grid True ise ve grid_visible_on_snap da True ise, o zaman grid gösterilir (ve line tool kontrolü yapılır)
        # Eğer self.snap_lines_to_grid True ama grid_visible_on_snap False ise, grid gösterilmez.

        if self.snap_lines_to_grid and getattr(self, 'grid_visible_on_snap', CANVAS_DEFAULT_GRID_SETTINGS['grid_visible_on_snap']) and self.grid_spacing_pt > 0:
            actual_show_grid = True
            if getattr(self, 'grid_show_for_line_tool_only', CANVAS_DEFAULT_GRID_SETTINGS['grid_show_for_line_tool_only']):
                if self.current_tool != ToolType.LINE:
                    actual_show_grid = False
            
            if actual_show_grid:
                painter.save()
                thick_line_interval = getattr(self, 'grid_thick_line_interval', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_line_interval'])
                thin_color_tuple_float = getattr(self, 'grid_thin_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_color']) 
                thick_color_tuple_float = getattr(self, 'grid_thick_color', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_color'])
                thin_width = getattr(self, 'grid_thin_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thin_width'])
                thick_width = getattr(self, 'grid_thick_width', CANVAS_DEFAULT_GRID_SETTINGS['grid_thick_width'])
                
                def clamp(val, minv, maxv):
                    return max(minv, min(maxv, val))

                thin_r, thin_g, thin_b = int(thin_color_tuple_float[0]*255), int(thin_color_tuple_float[1]*255), int(thin_color_tuple_float[2]*255)
                thin_a = clamp(int(round(thin_color_tuple_float[3]*255)), 0, 255) if len(thin_color_tuple_float) > 3 else 100
                thick_r, thick_g, thick_b = int(thick_color_tuple_float[0]*255), int(thick_color_tuple_float[1]*255), int(thick_color_tuple_float[2]*255)
                thick_a = clamp(int(round(thick_color_tuple_float[3]*255)), 0, 255) if len(thick_color_tuple_float) > 3 else 150

                thin_color = QColor(thin_r, thin_g, thin_b, thin_a)
                thick_color = QColor(thick_r, thick_g, thick_b, thick_a)
                spacing = self.grid_spacing_pt * PT_TO_PX
                w, h = self.width(), self.height()
                # Dikey çizgiler
                x = 0
                i = 0
                while x < w:
                    if i % thick_line_interval == 0:
                        pen = QPen(thick_color)
                        pen.setWidthF(thick_width)
                        painter.setPen(pen)
                    else:
                        pen = QPen(thin_color)
                        pen.setWidthF(thin_width)
                    painter.setPen(pen)
                    painter.drawLine(int(x), 0, int(x), h)
                    x += spacing
                    i += 1
                # Yatay çizgiler
                y = 0
                j = 0
                while y < h:
                    if j % thick_line_interval == 0:
                        pen = QPen(thick_color)
                        pen.setWidthF(thick_width)
                        painter.setPen(pen)
                    else:
                        pen = QPen(thin_color)
                        pen.setWidthF(thin_width)
                    painter.setPen(pen)
                    painter.drawLine(0, int(y), w, int(y))
                    y += spacing
                    j += 1
                painter.restore()
        painter.end()
        
        # --- Pointer Tool Glow/Fade-out Trail ---
        if self.current_tool == ToolType.TEMPORARY_POINTER and len(self.pointer_trail_points) > 1:
            for glow in range(8, 0, -1):
                path = QPainterPath()
                path.moveTo(self.pointer_trail_points[0][0])
                for p, _ in self.pointer_trail_points[1:]:
                    path.lineTo(p)
                alpha = int(60 * (glow / 8.0))
                width = 18 * (glow / 8.0)
                color = QColor(255, 80, 80, alpha)
                pen = QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawPath(path)
            path = QPainterPath()
            path.moveTo(self.pointer_trail_points[0][0])
            for p, _ in self.pointer_trail_points[1:]:
                path.lineTo(p)
            pen = QPen(QColor(255, 255, 255, 220), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)

        # --- YENİ: Kontrol Noktası Seçici aracı için overlay çizimi --- #
        from gui.tool_handlers import editable_line_node_selector_handler
        editable_line_node_selector_handler.draw_node_selector_overlay(self, painter)
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

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
        if self._parent_page is None:
            logging.error(f"tabletEvent received but self._parent_page is None! Ignoring event type: {event.type()}")
            event.ignore()
            return
        pos = self.screen_to_world(event.position())
        self.pressure = event.pressure()
        event_type = event.type()
        if event_type == QTabletEvent.Type.TabletPress:
            canvas_tablet_handler.handle_tablet_press(self, pos, event)
        elif event_type == QTabletEvent.Type.TabletMove:
            canvas_tablet_handler.handle_tablet_move(self, pos, event)
        elif event_type == QTabletEvent.Type.TabletRelease:
            canvas_tablet_handler.handle_tablet_release(self, pos, event)
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
                else:
                    logging.warning(f"_get_current_selection_states: Bilinmeyen öğe tipi: {item_type}[{index}]")

                states.append(current_item_state)
            except Exception as e:
                logging.error(f"_get_current_selection_states hatası ({item_type}[{index}] için veri alınırken): {e}", exc_info=True)
                states.append(None) 
        return states

    def _get_combined_bbox(self, states: List[Any]) -> QRectF:
        combined_bbox = QRectF()
        # Gelen 'states' listesi artık _get_current_selection_states'ten
        # [(item_type, index, full_item_data_copy), ...] formatında gelmeli.
        # VEYA doğrudan self._selected_item_indices kullanarak canvas'tan okuyabilir.
        # Şimdilik ikincisini kullanalım, daha basit.

        for item_type, index in self._selected_item_indices:
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
        """Verilen noktanın seçili öğelerden birinin üzerinde olup olmadığını kontrol eder."""
        logging.debug(f"--- is_point_on_selection checking point {point} ---")
        result = False
        for item_type, index in self._selected_item_indices:
            if item_type == 'images':
                if self._parent_page and 0 <= index < len(self._parent_page.images):
                    img_data = self._parent_page.images[index]
                    rect = img_data.get('rect')
                    angle = img_data.get('angle', 0.0)
                    if rect and isinstance(rect, QRectF):
                        if geometry_helpers.is_point_in_rotated_rect(point, rect, angle):
                            logging.debug(f"  >>> Point IS considered on selected item (rotated rect check): {item_type}[{index}]")
                            result = True
                            break 
                else:
                    logging.warning(f"is_point_on_selection: Invalid image index: {index}")
            else: 
                item_data = None
                if item_type == 'lines' and 0 <= index < len(self.lines):
                    item_data = self.lines[index]
                elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                    item_data = self.shapes[index]
                    # Düzenlenebilir çizgi için kontrol
                    if item_data[0] == ToolType.EDITABLE_LINE:
                        # Düzenlenebilir çizgi noktalarını kontrol et
                        control_points = item_data[3]  # Bezier kontrol noktaları
                        for i in range(0, len(control_points) - 3, 3):
                            p0 = control_points[i]
                            p3 = control_points[i + 3] if i + 3 < len(control_points) else control_points[-1]
                            
                            # Çizgi parçası üzerinde nokta var mı kontrol et
                            line_width = item_data[2]
                            effective_tolerance = tolerance + line_width / 2.0
                            if geometry_helpers.is_point_on_line(point, p0, p3, effective_tolerance):
                                result = True
                                logging.debug(f"  >>> Point IS on EDITABLE_LINE: {item_type}[{index}], segment between points {i} and {i+3}")
                                break

                if item_data:
                    if not result:  # Yukarıdaki özel kontroller sonucu seçilmediyse standart kontrolleri yap
                        bbox = geometry_helpers.get_item_bounding_box(item_data, item_type)
                        logging.debug(f"  is_point_on_selection: Checking selected item {item_type}[{index}] with bbox {bbox}")
                        if bbox.contains(point):
                            if item_type == 'lines':
                                points = item_data[2]
                                line_width = item_data[1]
                                effective_tolerance = tolerance + line_width / 2.0 
                                for j in range(len(points) - 1):
                                    if geometry_helpers.is_point_on_line(point, points[j], points[j+1], effective_tolerance):
                                        result = True
                                        break
                                if result: break 
                            else: 
                                result = True 
                                break 
                    if result:
                         logging.debug(f"  >>> Point IS considered on selected item (bbox or line check): {item_type}[{index}]")
                         break 
        
        logging.debug(f"--- is_point_on_selection result: {result} ---")
        return result

    def move_selected_items(self, dx: float, dy: float):
        moved = False
        for item_type, index in self._selected_item_indices:
            item_data = None
            if item_type == 'lines' and 0 <= index < len(self.lines):
                item_data = self.lines[index]
            elif item_type == 'shapes' and 0 <= index < len(self.shapes):
                item_data = self.shapes[index]
            if item_data:
                moving_helpers.move_item(item_data, dx, dy)
                moved = True

    def set_tool(self, tool: ToolType):
        previous_tool = self.current_tool
        # --- YENİ: Araç değişiminde yarım kalan çizgiyi finalize et --- #
        if self.drawing and len(self.current_line_points) > 1:
            final_points = [QPointF(p.x(), p.y()) for p in self.current_line_points]
            line_data = [
                self.current_color,
                self.current_pen_width,
                final_points,
                self.line_style
            ]
            from utils.commands import DrawLineCommand
            command = DrawLineCommand(self, line_data)
            self.undo_manager.execute(command)
            if self._parent_page:
                self._parent_page.mark_as_modified()
            self.drawing = False
            self.current_line_points = []
        # --- YENİ: Araç değişiminde yarım kalan şekli finalize et --- #
        if self.drawing_shape and (self.shape_start_point != self.shape_end_point):
            if (self.shape_end_point - self.shape_start_point).manhattanLength() > 2:
                shape_data = [
                    self.current_tool,
                    self.current_color,
                    self.current_pen_width,
                    self.shape_start_point,
                    self.shape_end_point,
                    self.line_style
                ]
                if self.current_tool == ToolType.RECTANGLE or self.current_tool == ToolType.CIRCLE:
                    fill_r, fill_g, fill_b, fill_a = self.current_fill_rgba
                    actual_fill_a = fill_a if self.fill_enabled else 0.0
                    actual_fill_rgba_tuple = (fill_r, fill_g, fill_b, actual_fill_a)
                    shape_data.append(actual_fill_rgba_tuple)
                try:
                    tool_type_cmd = shape_data[0]
                    color_cmd = shape_data[1]
                    width_cmd = shape_data[2]
                    p1_cmd = shape_data[3]
                    p2_cmd = shape_data[4]
                    line_style_cmd = shape_data[5]
                    fill_rgba_cmd = shape_data[6] if len(shape_data) > 6 else None
                    from utils.commands import DrawShapeCommand
                    command = DrawShapeCommand(self, 
                                             tool_type_cmd, color_cmd, width_cmd, 
                                             p1_cmd, p2_cmd, line_style_cmd, 
                                             fill_rgba_cmd)
                    self.undo_manager.execute(command)
                    if self._parent_page:
                        self._parent_page.mark_as_modified()
                except Exception as e:
                    logging.error(f"set_tool: Araç değişiminde şekil finalize edilirken hata: {e}. Data: {shape_data}", exc_info=True)
            self.drawing = False
            self.drawing_shape = False
            self.shape_start_point = QPointF()
            self.shape_end_point = QPointF()
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
        self.current_tool = tool
        self.drawing = False
        self.moving_selection = False
        self.resizing_selection = False
        self.selecting = False
        self.erasing = False
        self.temporary_erasing = False
        self.laser_pointer_active = (tool == ToolType.LASER_POINTER) # Lazer durumunu ayarla
        # --- YENİ LOG --- #
        # logging.debug(f"  laser_pointer_active set to: {self.laser_pointer_active}") # Yorum satırı yapıldı
        # --- --- --- -- #

        # Seçim modundan çıkıldıysa seçimi temizle
        if previous_tool == ToolType.SELECTOR and tool != ToolType.SELECTOR:
             self._selected_item_indices.clear()
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
        new_color = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
        if self.current_color != new_color:
            self.current_color = new_color
            # logging.debug(f"Çizim rengi ayarlandı: {self.current_color}") # Yorum satırı yapıldı (isteğe bağlı)

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
        # logging.debug(f"Canvas'a yeni şablon ayarları uygulanıyor: {settings}") # Bu kalsın, bu ikinciyi kapatalım (eğer iki tane varsa)
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
            # logging.debug("Template type changed, reloading background image.") # Yorum satırı yapıldı
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
        logging.debug(f"--- _get_item_at called for World Pos: {world_pos}, tolerance: {tolerance} ---")
        
        # 1. Resimleri Kontrol Et (Sondan başa doğru)
        if self._parent_page and hasattr(self._parent_page, 'images') and self._parent_page.images:
            logging.debug(f"  _get_item_at: Checking {len(self._parent_page.images)} images...")
            for i in range(len(self._parent_page.images) - 1, -1, -1):
                img_data = self._parent_page.images[i]
                rect = img_data.get('rect')
                angle = img_data.get('angle', 0.0)
                if rect and isinstance(rect, QRectF):
                    contains = geometry_helpers.is_point_in_rotated_rect(world_pos, rect, angle)
                    logging.debug(f"    _get_item_at: Checking image {i} with rect: {rect}, angle: {angle:.1f}. Contains point? {contains}")
                    if contains:
                        logging.debug(f"  >>> _get_item_at: Image found at index {i}")
                        return ('images', i)
                else:
                    logging.warning(f"_get_item_at: images[{i}] içinde geçerli 'rect' yok.")

        # 2. Şekilleri Kontrol Et (Sondan başa doğru)
        logging.debug(f"  _get_item_at: Checking {len(self.shapes)} shapes...")
        for i in range(len(self.shapes) - 1, -1, -1):
            shape_data = self.shapes[i]
            logging.debug(f"    _get_item_at: Checking shape index {i}, data type: {type(shape_data[0])}, data: {shape_data}")

            item_tool_type = shape_data[0]

            if item_tool_type == ToolType.LINE:
                p1 = shape_data[3]
                p2 = shape_data[4]
                line_width = shape_data[2]
                effective_tolerance = tolerance + (line_width / 2.0)
                
                logging.debug(f"      _get_item_at (Shape as Line): Checking line {i} with p1={p1}, p2={p2}, width={line_width}, eff_tol={effective_tolerance}, world_pos={world_pos}")
                if geometry_helpers.is_point_on_line(world_pos, p1, p2, effective_tolerance):
                    logging.debug(f"  >>> _get_item_at: Shape (Line) found at index {i} by is_point_on_line")
                    return ('shapes', i)
                else:
                    logging.debug(f"      _get_item_at (Shape as Line): Line {i} NOT matched by is_point_on_line.")
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
            else:
                bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                logging.debug(f"    _get_item_at (Shape as Other): Checking shape {i} (type: {item_tool_type}) with bbox: {bbox}. Point: {world_pos}")
                if bbox.contains(world_pos):
                    logging.debug(f"  >>> _get_item_at: Shape (Other) found at index {i} by bbox.contains")
                    return ('shapes', i)
                else:
                    logging.debug(f"      _get_item_at (Shape as Other): Shape {i} NOT matched by bbox.contains.")

        # 3. Çizgileri Kontrol Et (Sondan başa doğru)
        logging.debug(f"  _get_item_at: Checking {len(self.lines)} lines...")
        for i in range(len(self.lines) - 1, -1, -1):
            line_data = self.lines[i]
            bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
            logging.debug(f"    [GET_ITEM_AT_DEBUG] Line {i}: BBox={bbox}, BBox.width={bbox.width():.2f}, BBox.height={bbox.height():.2f}")
            contains_bbox = bbox.contains(world_pos)
            logging.debug(f"    [GET_ITEM_AT_DEBUG]   Line {i}: world_pos={world_pos}, bbox_contains_world_pos={contains_bbox}")
            if contains_bbox: 
                points = line_data[2]
                line_width = line_data[1]
                effective_tolerance = tolerance + line_width / 2.0
                logging.debug(f"      [GET_ITEM_AT_DEBUG]     Line {i}: Calling is_point_on_line with effective_tolerance={effective_tolerance:.2f}")
                for j in range(len(points) - 1):
                    if geometry_helpers.is_point_on_line(world_pos, points[j], points[j+1], effective_tolerance):
                        logging.debug(f"  >>> _get_item_at: Line found at index {i} (segment {j}-{j+1} check PASSED)")
                        return ('lines', i)
                    else: 
                        logging.debug(f"      [GET_ITEM_AT_DEBUG]       Line {i}, Segment {j}-{j+1}: is_point_on_line FAILED.")
                logging.debug(f"    [GET_ITEM_AT_DEBUG]     Line {i}: BBox contained point, but all segment checks failed.")
        
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

        if len(touch_points) >= 2:
            p1, p2 = touch_points[0], touch_points[1]
            pos1 = self.screen_to_world(p1.position())
            pos2 = self.screen_to_world(p2.position())
            center = QPointF((pos1.x() + pos2.x()) / 2, (pos1.y() + pos2.y()) / 2)
            dist = (pos1 - pos2).manhattanLength()
            if not self._pinch_active:
                self._last_pinch_dist = dist
                self._last_pinch_center = center
                self._pinch_active = True
            else:
                if self._last_pinch_dist and self._last_pinch_dist != 0:
                    scale = (dist / self._last_pinch_dist) ** 0.3
                    old_zoom = self._parent_page.zoom_level
                    new_zoom = max(0.2, min(5.0, old_zoom * scale))
                    self._parent_page.zoom_level = new_zoom
                    delta = (center - self._last_pinch_center) * 0.5
                    self._parent_page.pan_offset -= delta
                    self._last_pinch_dist = dist
                    self._last_pinch_center = center
                    self.update()
            event.accept()
            return
        else:
            self._pinch_active = False
            self._last_pinch_dist = None
            self._last_pinch_center = None

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
        return super().update(*args, **kwargs)

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
            self.pointer_trail_points = [(event.position(), time.time())]
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_tool == ToolType.TEMPORARY_POINTER and event.buttons() & Qt.MouseButton.LeftButton:
            self.pointer_trail_points.append((event.position(), time.time()))
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_tool == ToolType.TEMPORARY_POINTER and event.button() == Qt.MouseButton.LeftButton:
            pass  # Çizim bitince iz fade-out ile silinecek
        super().mouseReleaseEvent(event)


from abc import ABC, abstractmethod
import logging
import copy # Derin kopya için gerekebilir
from typing import TYPE_CHECKING, List, Tuple, Any, Protocol, Dict
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPixmap, QPainter, QTransform # QTransform buraya taşındı
from PyQt6.QtWidgets import QGraphicsPixmapItem
import uuid
import hashlib
import numpy as np # YENİ: NumPy importu eklendi

from gui.enums import ToolType # ToolType import'u EKLENDİ

# Type hints
if TYPE_CHECKING:
    from gui.drawing_canvas import DrawingCanvas, ToolType
    from .erasing_helpers import EraseChanges # EraseChanges import'u eklendi
    # from PyQt6.QtCore import QPointF

# Type definitions for clarity
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]

class Command(ABC):
    """Undo/Redo edilebilir işlemler için soyut temel sınıf."""
    @abstractmethod
    def execute(self):
        """Komutu uygular."""
        pass

    @abstractmethod
    def undo(self):
        """Komutun etkisini geri alır."""
        pass


class DrawLineCommand(Command):
    """Bir çizgi çizme işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', line_data: LineDataType):
        """Başlatıcı.

        Args:
            canvas: İşlemin uygulanacağı DrawingCanvas örneği.
            line_data: Çizgi verisi (color_tuple, width_float, points_list_QPointF).
        """
        self.canvas = canvas
        try:
            self.line_data = copy.deepcopy(line_data)
            if len(line_data) < 3:
                pass
            if len(self.line_data) < 3:
                 self.line_data = [ (0,0,0,1), 1.0, [] ]
            elif not isinstance(self.line_data[2], list):
                self.line_data = [ (0,0,0,1), 1.0, [] ]
        except Exception as e:
            self.line_data = [ (0,0,0,1), 1.0, [] ]
        self._line_added = False
        self._added_index = -1

    def execute(self):
        """Çizgiyi canvas'a ekler veya (redo ise) orijinal indeksine geri ekler."""
        try:
            if not hasattr(self.canvas, 'lines') or not isinstance(self.canvas.lines, list):
                logging.error("DrawLineCommand: Canvas.lines bulunamadı veya liste değil.")
                self._line_added = False
                return

            if self._line_added: # Redo durumu
                if 0 <= self._added_index <= len(self.canvas.lines):
                    self.canvas.lines.insert(self._added_index, copy.deepcopy(self.line_data))
                else:
                    self.canvas.lines.append(copy.deepcopy(self.line_data))
                    self._added_index = len(self.canvas.lines) - 1  # REDO'da index güncelle
                logging.debug(f"DrawLineCommand: Redo, _added_index={self._added_index}")
            elif not self._line_added:
                self.canvas.lines.append(copy.deepcopy(self.line_data))
                self._added_index = len(self.canvas.lines) - 1
                self._line_added = True
                #logging.debug(f"DrawLineCommand: Çizgi eklendi, _added_index={self._added_index}")
            else:
                return

            self.canvas.update()
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
        except Exception as e:
            self._line_added = False
            self._added_index = -1

    def undo(self):
        """Çizgiyi canvas'tan kaldırır."""
        if not self._line_added or self._added_index < 0:
            return
        try:
            if 0 <= self._added_index < len(self.canvas.lines):
                del self.canvas.lines[self._added_index]
                self.canvas.update()
            else:
                pass
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
        except IndexError:
            pass
        except Exception as e:
            pass


class DrawShapeCommand(Command):
    """Bir şekil çizme işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', 
                 tool_type: ToolType, color: tuple, width: float, 
                 p1: QPointF, p2: QPointF, line_style: str, 
                 fill_rgba: tuple | None = None):
        """Başlatıcı (Ayrı parametrelerle).

        Args:
            canvas: İşlemin uygulanacağı DrawingCanvas örneği.
            tool_type: Çizilecek şeklin tipi (ToolType enum).
            color: Renk tuple'ı (R, G, B, A -> 0-1 float).
            width: Çizgi kalınlığı.
            p1: Başlangıç noktası (QPointF).
            p2: Bitiş noktası (QPointF).
            line_style: Çizgi stili ('solid', 'dashed', vb.).
            fill_rgba: Doldurma rengi tuple'ı (R, G, B, A -> 0-1 float) veya None.
        """
        self.canvas = canvas
        
        # Gelen parametreleri self.shape_data listesinde sakla
        self.shape_data = [
            tool_type,
            color,
            width,
            copy.deepcopy(p1), # QPointF'lerin kopyasını sakla
            copy.deepcopy(p2),
            line_style,
        ]
        # Fill_rgba None değilse ekle (liste 7 elemanlı olacak)
        if fill_rgba is not None:
            self.shape_data.append(fill_rgba)

        self._shape_added = False
        self._added_index = -1

    def execute(self):
        #logging.debug("DrawShapeCommand: execute() çağrıldı.")
        try:
            if not hasattr(self.canvas, 'shapes') or not isinstance(self.canvas.shapes, list):
                #logging.error("DrawShapeCommand: Canvas.shapes bulunamadı veya liste değil.")
                self._shape_added = False
                return

            shape_data_to_add = copy.deepcopy(self.shape_data)

            if self._shape_added: # Redo durumu
                if 0 <= self._added_index <= len(self.canvas.shapes):
                    self.canvas.shapes.insert(self._added_index, shape_data_to_add)
                else:
                    self.canvas.shapes.append(shape_data_to_add)
            elif not self._shape_added:
                self._added_index = len(self.canvas.shapes)
                self.canvas.shapes.append(shape_data_to_add)
                self._shape_added = True

            self.canvas.update()
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
        except Exception as e:
            self._shape_added = False
            self._added_index = -1
        #logging.debug("DrawShapeCommand: execute() tamamlandı.")

    def undo(self):
        logging.debug(f"DrawShapeCommand.undo: BAŞLANGIÇ. Canvas.shapes id={id(self.canvas.shapes)}, içerik={self.canvas.shapes}") # YENİ LOG
        """Eklenen şekli canvas'tan kaldırır."""
        if not self._shape_added or self._added_index < 0:
            return
        try:
            if 0 <= self._added_index < len(self.canvas.shapes):
                del self.canvas.shapes[self._added_index]
                self._shape_added = False
                self.canvas.update()
                if hasattr(self.canvas, 'selection_changed'):
                    self.canvas.selection_changed.emit()
        except IndexError:
            logging.error(f"DrawShapeCommand undo: Index hatası oluştu. index={self._added_index}, shapes_len={len(self.canvas.shapes)}", exc_info=True)
        except Exception as e:
            self._shape_added = False


class ClearCanvasCommand(Command):
    """Canvas'ı temizleme işlemini temsil eder (lines, shapes, images ve b_spline_strokes)."""
    def __init__(self, canvas: 'DrawingCanvas'):
        self.canvas = canvas
        self._previous_lines: List[LineDataType] = []
        self._previous_shapes: List[ShapeDataType] = []
        self._previous_images: list = []
        self._previous_b_splines: List[dict] = [] # YENİ: b_spline_strokes için
        self._was_cleared = False
        self._was_images_cleared = False
        self._was_b_splines_cleared = False # YENİ: b_spline_strokes için

    def execute(self):
        """Canvas'ı temizler ve eski durumu saklar."""
        try:
            lines_exist = hasattr(self.canvas, 'lines') and isinstance(self.canvas.lines, list)
            shapes_exist = hasattr(self.canvas, 'shapes') and isinstance(self.canvas.shapes, list)
            images_exist = hasattr(self.canvas, '_parent_page') and hasattr(self.canvas._parent_page, 'images') and isinstance(self.canvas._parent_page.images, list)
            b_splines_exist = hasattr(self.canvas, 'b_spline_strokes') and isinstance(self.canvas.b_spline_strokes, list) # YENİ

            if not lines_exist or not shapes_exist: # b_splines_exist kontrolü buraya eklenebilir, ama lines/shapes temel kabul ediliyor
                logging.error("ClearCanvasCommand: Canvas.lines veya Canvas.shapes bulunamadı/liste değil.")
                self._was_cleared = False
                return

            # Sadece en az bir liste doluysa temizle
            canvas_is_empty = not self.canvas.lines and \
                              not self.canvas.shapes and \
                              (not images_exist or not self.canvas._parent_page.images) and \
                              (not b_splines_exist or not self.canvas.b_spline_strokes) # YENİ
            
            if canvas_is_empty:
                logging.debug("ClearCanvasCommand execute: Canvas zaten boş.")
                self._was_cleared = False
                self._was_images_cleared = False
                self._was_b_splines_cleared = False # YENİ
                return

            self._previous_lines = copy.deepcopy(self.canvas.lines)
            self._previous_shapes = copy.deepcopy(self.canvas.shapes)
            
            if images_exist:
                from utils.commands import _copy_image_data_without_qpixmap
                self._previous_images = [
                    _copy_image_data_without_qpixmap(img)
                    for img in self.canvas._parent_page.images
                ]
                self._was_images_cleared = bool(self.canvas._parent_page.images)
                self.canvas._parent_page.images.clear()
            else:
                self._previous_images = []
                self._was_images_cleared = False

            if b_splines_exist: # YENİ
                self._previous_b_splines = copy.deepcopy(self.canvas.b_spline_strokes)
                self._was_b_splines_cleared = bool(self.canvas.b_spline_strokes)
                self.canvas.b_spline_strokes.clear()
            else:
                self._previous_b_splines = []
                self._was_b_splines_cleared = False

            self.canvas.lines.clear()
            self.canvas.shapes.clear()

            if hasattr(self.canvas, 'current_line_points'):
                self.canvas.current_line_points.clear()
            self.canvas.drawing = False
            self.canvas.drawing_shape = False
            self._was_cleared = True # Bu genel bir flag olarak kalabilir
            self.canvas.update()
            logging.debug("ClearCanvasCommand executed (lines, shapes, images ve b_spline_strokes).") # Log güncellendi
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
            if hasattr(self.canvas, '_load_qgraphics_pixmap_items_from_page'):
                self.canvas._load_qgraphics_pixmap_items_from_page()
        except Exception as e:
            logging.error(f"ClearCanvasCommand execute hatası: {e}", exc_info=True)
            self._was_cleared = False
            self._was_images_cleared = False
            self._was_b_splines_cleared = False # YENİ

    def undo(self):
        """Temizlenmiş canvas'ı eski haline getirir."""
        try:
            if not self._was_cleared and not self._was_images_cleared and not self._was_b_splines_cleared: # YENİ
                return
            self.canvas.lines = copy.deepcopy(self._previous_lines)
            self.canvas.shapes.clear()
            self.canvas.shapes.extend(copy.deepcopy(self._previous_shapes))
            
            if hasattr(self.canvas, '_parent_page') and hasattr(self.canvas._parent_page, 'images'):
                self.canvas._parent_page.images.clear()
                self.canvas._parent_page.images.extend(copy.deepcopy(self._previous_images))
            
            if hasattr(self.canvas, 'b_spline_strokes'): # YENİ
                self.canvas.b_spline_strokes.clear()
                self.canvas.b_spline_strokes.extend(copy.deepcopy(self._previous_b_splines))

            self.canvas.drawing = False
            self.canvas.drawing_shape = False
            self.canvas.update()
            logging.debug("ClearCanvasCommand undo: Canvas eski haline getirildi (lines, shapes, images ve b_spline_strokes).") # Log güncellendi
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
            if hasattr(self.canvas, '_load_qgraphics_pixmap_items_from_page'):
                self.canvas._load_qgraphics_pixmap_items_from_page()
        except Exception as e:
            logging.error(f"ClearCanvasCommand undo: Hata oluştu: {e}", exc_info=True)


# --- Yeni Komutlar (Taşıma, Boyutlandırma, Silme) --- #

from utils import moving_helpers # Döngüsel importu önlemek için burada import et

# YENİ: Durum kopyalama için yardımcı fonksiyon
def _copy_states_without_pixmap(states: List[Any]) -> List[Any]:
    """
    Verilen durum listesinin derin bir kopyasını oluşturur,
    ancak 'pixmap' ve 'original_pixmap_for_scaling' anahtarları QPixmap ise QPixmap.copy() kullanır,
    'pixmap_item' anahtarı QGraphicsPixmapItem ise referans olarak kopyalar.
    """
    new_states = []
    if not states:
        return new_states
    for state in states:
        if state is None: # Olası bir None durumu için kontrol
            new_states.append(None)
            continue
        if isinstance(state, dict):
            new_state_dict = {}
            for key, value in state.items():
                if key in ['pixmap', 'original_pixmap_for_scaling'] and isinstance(value, QPixmap):
                    new_state_dict[key] = value.copy() if value else None
                elif key == 'pixmap_item' and isinstance(value, QGraphicsPixmapItem):
                    new_state_dict[key] = value  # Referans olarak kopyala, deepcopy yapma
                else:
                    try:
                        new_state_dict[key] = copy.deepcopy(value)
                    except Exception as e:
                        # Deepcopy hatası olursa logla ve None ata (veya hatayı yükselt)
                        logging.error(f"_copy_states_without_pixmap: Deepcopy failed for key '{key}' (value type: {type(value)}): {e}")
                        new_state_dict[key] = None # Veya value
            new_states.append(new_state_dict)
        else:
            try:
                new_states.append(copy.deepcopy(state)) # Diğer tipler için normal deepcopy
            except Exception as e:
                logging.error(f"_copy_states_without_pixmap: Deepcopy failed for non-dict state (type: {type(state)}): {e}")
                new_states.append(None) # Veya state
    return new_states

# Taşıma Komutu (YENİDEN YAPILANDIRILDI - State Tabanlı)
class MoveItemsCommand(Command):
    """Seçili öğeleri taşıma işlemini temsil eder (State Tabanlı)."""
    def __init__(self, canvas: 'DrawingCanvas', item_indices: List[Tuple[str, int]], original_states: List[Any], final_states: List[Any]):
        self.canvas = canvas
        self.item_indices = item_indices # [('lines', 0), ('shapes', 5), ...]
        # Derin kopyaları sakla
        self.original_states = _copy_states_without_pixmap(original_states)
        self.final_states = _copy_states_without_pixmap(final_states)
        self.description = f"Move {len(item_indices)} items"

    def execute(self):
        self._apply_state(self.final_states)
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def undo(self):
        self._apply_state(self.original_states)
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def _apply_state(self, states: List[Any]):
        """Verilen state listesini (tam öğe verileri içeren) canvas'a uygular."""
        if len(states) != len(self.item_indices):
            logging.error(f"MoveItemsCommand._apply_state: State sayısı ({len(states)}) ile indeks sayısı ({len(self.item_indices)}) eşleşmiyor!")
            return

        try:
            if not self.canvas._parent_page:
                logging.error("MoveItemsCommand._apply_state: Canvas'ın _parent_page referansı yok!")
                return
                
            for i, (item_type, index) in enumerate(self.item_indices):
                item_full_data = states[i]
                if item_full_data is None:
                    logging.warning(f"MoveItemsCommand._apply_state: Öğenin state'i None: {item_type}[{index}]")
                    continue

                if item_type == 'lines':
                    if 0 <= index < len(self.canvas.lines):
                        self.canvas.lines[index] = copy.deepcopy(item_full_data)
                    else:
                        logging.warning(f"MoveItemsCommand._apply_state: Geçersiz lines index: {index}")
                elif item_type == 'shapes':
                    if 0 <= index < len(self.canvas.shapes):
                        self.canvas.shapes[index] = copy.deepcopy(item_full_data)
                    else:
                        logging.warning(f"MoveItemsCommand._apply_state: Geçersiz shapes index: {index}")
                elif item_type == 'images':
                    if hasattr(self.canvas._parent_page, 'images') and isinstance(self.canvas._parent_page.images, list):
                        if 0 <= index < len(self.canvas._parent_page.images):
                            new_image_data = {}
                            for key, value in item_full_data.items():
                                if key == 'pixmap':
                                    new_image_data[key] = value
                                elif key == 'original_pixmap_for_scaling' and isinstance(value, QPixmap):
                                    new_image_data[key] = value
                                elif key == 'pixmap_item' and isinstance(value, QGraphicsPixmapItem):
                                    new_image_data[key] = value
                                else:
                                    new_image_data[key] = copy.deepcopy(value)
                            self.canvas._parent_page.images[index] = new_image_data
                        else:
                            logging.warning(f"MoveItemsCommand._apply_state: Geçersiz images index: {index}")
                    else:
                        logging.warning(f"MoveItemsCommand._apply_state: Canvas._parent_page.images bulunamadı veya liste değil.")
                elif item_type == 'bspline_strokes': # YENİ: B-Spline Strokes için state uygulama
                    if hasattr(self.canvas, 'b_spline_strokes') and isinstance(self.canvas.b_spline_strokes, list):
                        if 0 <= index < len(self.canvas.b_spline_strokes):
                            # item_full_data zaten taşınmış/dönüştürülmüş state olmalı.
                            # Bu state'in derin bir kopyasını atamak yeterli.
                            self.canvas.b_spline_strokes[index] = copy.deepcopy(item_full_data)
                        else:
                            logging.warning(f"MoveItemsCommand._apply_state: Geçersiz bspline_strokes index: {index}")
                    else:
                        logging.warning(f"MoveItemsCommand._apply_state: Canvas.b_spline_strokes bulunamadı veya liste değil.")
                else:
                    logging.warning(f"MoveItemsCommand._apply_state: Bilinmeyen öğe tipi: {item_type}[{index}]") # Index bilgisi eklendi
        except Exception as e:
            logging.error(f"MoveItemsCommand._apply_state hatası: {e}", exc_info=True)

# TODO: ResizeItemsCommand, DeleteItemsCommand eklenecek 

class ResizeItemsCommand(Command):
    """Seçili öğeleri yeniden boyutlandırma işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', item_indices: List[Tuple[str, int]], original_states: List[Any], final_states: List[Any]):
        self.canvas = canvas
        self.item_indices = item_indices # [('lines', 0), ('shapes', 5), ...]
        # deepcopy kullanarak orijinal ve son halleri sakla
        self.original_states = _copy_states_without_pixmap(original_states)
        self.final_states = _copy_states_without_pixmap(final_states)
        self._is_first_execution = True
        self.description = f"Resize {len(item_indices)} items"

    def execute(self):
        if self._is_first_execution:
            self._is_first_execution = False
        else:
            self._apply_state(self.final_states)
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def undo(self):
        self._apply_state(self.original_states)
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def _apply_state(self, states: List[Any]):
        """Verilen state listesini (tam öğe verileri içeren) canvas'a uygular."""
        if len(states) != len(self.item_indices):
            logging.error(f"ResizeItemsCommand._apply_state: State sayısı ({len(states)}) ile indeks sayısı ({len(self.item_indices)}) eşleşmiyor!")
            return

        try:
            if not self.canvas._parent_page:
                logging.error("ResizeItemsCommand._apply_state: Canvas'ın _parent_page referansı yok!")
                return
                
            for i, (item_type, index) in enumerate(self.item_indices):
                item_full_data = states[i]
                if item_full_data is None: 
                    logging.warning(f"ResizeItemsCommand._apply_state: Öğenin state'i None: {item_type}[{index}]")
                    continue

                if item_type == 'lines':
                    if 0 <= index < len(self.canvas.lines):
                        self.canvas.lines[index] = copy.deepcopy(item_full_data)
                    else:
                        logging.warning(f"ResizeItemsCommand._apply_state: Geçersiz lines index: {index}")
                elif item_type == 'shapes':
                    if 0 <= index < len(self.canvas.shapes):
                        self.canvas.shapes[index] = copy.deepcopy(item_full_data)
                    else:
                        logging.warning(f"ResizeItemsCommand._apply_state: Geçersiz shapes index: {index}")
                elif item_type == 'images':
                    if hasattr(self.canvas._parent_page, 'images') and isinstance(self.canvas._parent_page.images, list):
                        if 0 <= index < len(self.canvas._parent_page.images):
                            new_image_data = {}
                            for key, value in item_full_data.items():
                                if key == 'pixmap':
                                    new_image_data[key] = value
                                elif key == 'original_pixmap_for_scaling' and isinstance(value, QPixmap):
                                    new_image_data[key] = value
                                elif key == 'pixmap_item' and isinstance(value, QGraphicsPixmapItem):
                                    new_image_data[key] = value
                                else:
                                    new_image_data[key] = copy.deepcopy(value)
                            self.canvas._parent_page.images[index] = new_image_data
                        else:
                            logging.warning(f"ResizeItemsCommand._apply_state: Geçersiz images index: {index}")
                    else:
                        logging.warning(f"ResizeItemsCommand._apply_state: Canvas._parent_page.images bulunamadı veya liste değil.")
                elif item_type == 'bspline_strokes': # YENİ: B-Spline Strokes için state uygulama
                    if hasattr(self.canvas, 'b_spline_strokes') and isinstance(self.canvas.b_spline_strokes, list):
                        if 0 <= index < len(self.canvas.b_spline_strokes):
                            # item_full_data zaten taşınmış/dönüştürülmüş state olmalı.
                            # Bu state'in derin bir kopyasını atamak yeterli.
                            self.canvas.b_spline_strokes[index] = copy.deepcopy(item_full_data)
                        else:
                            logging.warning(f"ResizeItemsCommand._apply_state: Geçersiz bspline_strokes index: {index}")
                    else:
                        logging.warning(f"ResizeItemsCommand._apply_state: Canvas.b_spline_strokes bulunamadı veya liste değil.")
                else:
                    logging.warning(f"ResizeItemsCommand._apply_state: Bilinmeyen öğe tipi: {item_type}")

        except Exception as e:
            logging.error(f"ResizeItemsCommand._apply_state hatası: {e}", exc_info=True)

# TODO: DeleteItemsCommand eklenecek 

# Silme Komutu (YENİ - Biriktirilmiş Değişiklikler Uyumlu)
class EraseCommand(Command):
    """Çizgi noktalarını veya tüm şekilleri/b-spline'ları silme işlemini ve geri almayı yönetir."""
    def __init__(self, canvas: 'DrawingCanvas', changes: 'EraseChanges'):
        """Başlatıcı.

        Args:
            canvas: İşlemin uygulanacağı DrawingCanvas örneği.
            changes: erase_items_along_path tarafından DOLDURULAN değişiklikler sözlüğü.
                     {
                         'lines': {index: {'original_points': [...], 'original_color': (r,g,b), 
                                       'original_width': float, 'final_points': [...]}},
                         'shapes': {index: original_shape_data_copy},
                         'b_spline_strokes': {index: original_bspline_data_copy}
                     }
        """
        self.canvas = canvas
        self._changes = changes 
        self._lines_before_erase = copy.deepcopy(canvas.lines)
        self._shapes_before_erase = copy.deepcopy(canvas.shapes)
        self._b_splines_before_erase = copy.deepcopy(getattr(canvas, 'b_spline_strokes', []))
        
        """ logging.debug(
            f"EraseCommand created. Stored current state (lines: {len(self._lines_before_erase)}, "
            f"shapes: {len(self._shapes_before_erase)}, b_splines: {len(self._b_splines_before_erase)}). "
            f"Changes to apply: lines={list(changes.get('lines', {}).keys())}, "
            f"shapes={list(changes.get('shapes', {}).keys())}, "
            f"b_splines={list(changes.get('b_spline_strokes', {}).keys())}"
        ) """

    def execute(self):
        """Hesaplanan değişiklikleri canvas'a uygular (asıl silme işlemi burada yapılır)."""
        #logging.debug(f"Executing EraseCommand...")
        lines_applied = 0
        shapes_applied = 0
        b_splines_applied = 0
        indices_to_delete_completely = []

        # 1. Çizgileri Güncelle/Sil
        line_changes = self._changes.get('lines', {})
        for index, change_data in line_changes.items():
            final_points = change_data.get('final_points')
            if final_points is None:
                logging.warning(f"EraseCommand execute: Missing final_points for line {index}")
                continue
            
            try:
                if 0 <= index < len(self.canvas.lines):
                    if final_points: 
                        self.canvas.lines[index][2] = final_points
                        lines_applied += 1
                    else: 
                        indices_to_delete_completely.append(index)
                else:
                    logging.warning(f"EraseCommand execute: Line {index} not found in canvas.lines.")
            except Exception as e:
                logging.error(f"Error applying changes for line {index} during execute: {e}", exc_info=True)

        indices_to_delete_completely.sort(reverse=True)
        for index in indices_to_delete_completely:
            try:
                del self.canvas.lines[index]
            except IndexError:
                logging.warning(f"EraseCommand execute: Index {index} out of range while deleting line.")
            except Exception as e:
                logging.error(f"Error deleting line {index} during execute: {e}", exc_info=True)

        # 2. Şekilleri Sil
        shape_changes = self._changes.get('shapes', {})
        sorted_shape_indices = sorted(shape_changes.keys(), reverse=True)
        for index in sorted_shape_indices:
            try:
                if 0 <= index < len(self.canvas.shapes):
                    del self.canvas.shapes[index]
                    shapes_applied += 1
                else:
                    logging.warning(f"EraseCommand execute: Shape {index} not found in canvas.shapes.")
            except Exception as e:
                logging.error(f"Error removing shape {index} during execute: {e}", exc_info=True)
        
        # 3. B-Spline Stroklarını Sil
        bspline_changes = self._changes.get('b_spline_strokes', {})
        sorted_bspline_indices = sorted(bspline_changes.keys(), reverse=True)
        for index in sorted_bspline_indices:
            try:
                if hasattr(self.canvas, 'b_spline_strokes') and 0 <= index < len(self.canvas.b_spline_strokes):
                    del self.canvas.b_spline_strokes[index]
                    b_splines_applied += 1
                else:
                    logging.warning(f"EraseCommand execute: B-Spline stroke {index} not found in canvas.b_spline_strokes.")
            except Exception as e:
                logging.error(f"Error removing B-Spline stroke {index} during execute: {e}", exc_info=True)

        """ logging.debug(
            f"EraseCommand execute finished. Applied changes to {lines_applied} lines, "
            f"removed {shapes_applied} shapes, removed {b_splines_applied} b-splines."
        ) """
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def undo(self):
        logging.debug(
            f"Undoing EraseCommand: Restoring state to {len(self._lines_before_erase)} lines, "
            f"{len(self._shapes_before_erase)} shapes, {len(self._b_splines_before_erase)} b-splines."
        )
        try:
            self.canvas.lines = copy.deepcopy(self._lines_before_erase)
            self.canvas.shapes.clear()
            self.canvas.shapes.extend(copy.deepcopy(self._shapes_before_erase))
            if hasattr(self.canvas, 'b_spline_strokes'):
                self.canvas.b_spline_strokes.clear()
                self.canvas.b_spline_strokes.extend(copy.deepcopy(self._b_splines_before_erase))

            self.canvas.update()
            logging.debug("Undo finished: Canvas state restored.")
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
        except Exception as e:
            logging.error(f"Error during EraseCommand undo: {e}", exc_info=True)

    def __str__(self):
        lines_affected = len(self._changes.get('lines', {}))
        shapes_affected = len(self._changes.get('shapes', {}))
        b_splines_affected = len(self._changes.get('b_spline_strokes', {}))
        return f"EraseCommand(lines_affected={lines_affected}, shapes_affected={shapes_affected}, b_splines_affected={b_splines_affected})"

# --- YENİ: Dosya hash hesaplama fonksiyonu ---
def get_file_md5(file_path):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logging.error(f"MD5 hesaplanırken hata: {e}")
        return None

# --- YENİ: Resim Ekleme Komutu --- #
class AddImageCommand(Command):
    """Bir resim ekleme işlemini temsil eder."""
    def __init__(self, page: 'Page', image_data: dict):
        """Başlatıcı.

        Args:
            page: Resmin ekleneceği Page nesnesi.
            image_data: Resim verisi (path, pixmap, rect, angle, uuid içerir).
        """
        self.page = page
        self.canvas = page.get_canvas() if page else None
        
        # --- YENİ LOG: Gelen rect'i logla --- #
        received_rect = image_data.get('rect')
        logging.debug(f"AddImageCommand __init__: Received rect in image_data: {received_rect}")
        # --- --- --- --- --- --- --- --- --- #
        
        self.image_data = {}
        for key, value in image_data.items():
            if isinstance(value, QPixmap):
                if key == 'pixmap': # Bu, handle_add_image'dan gelen, başlangıçta ölçeklenmiş pixmap
                    self.image_data[key] = value 
                    self.image_data['original_pixmap_for_scaling'] = value.copy() # Ölçekleme için temel kopya
                else: # Başka bir QPixmap alanı varsa (beklenmiyor ama güvenli)
                    self.image_data[key] = value
            else:
                self.image_data[key] = copy.deepcopy(value)
        
        self._item_successfully_added_to_page_list = False

    def execute(self):
        """Resim verisini Page.images'a ekler."""
        if not self.page:
            logging.error("AddImageCommand execute: Geçerli page bulunamadı.")
            return
        
        if not hasattr(self.page, 'images') or not isinstance(self.page.images, list):
            self.page.images = []

        # --- YENİ: Aynı hash'e sahip resim var mı kontrolü ---
        new_path = self.image_data.get('path')
        new_hash = get_file_md5(new_path) if new_path else None
        if new_hash:
            for img in self.page.images:
                img_path = img.get('path')
                img_hash = get_file_md5(img_path) if img_path else None
                if img_hash == new_hash:
                    logging.info(f"Aynı içeriğe sahip resim zaten ekli: {new_path}")
                    return  # Aynı resim tekrar eklenmez
        # --- --- ---

        try:
            # Pixmap null kontrolü __init__ veya handle_add_image'da yapılmalı, burada tekrar gerekmez.
            # QGraphicsPixmapItem oluşturma kaldırıldı.
            # self.item_to_add = QGraphicsPixmapItem(pixmap) ...

            # Page listesine ekle (eğer daha önce eklenmemişse)
            uuid_to_add = self.image_data.get('uuid')
            already_in_page_list = False
            if uuid_to_add and hasattr(self.page, 'images'):
                for img_dict in self.page.images:
                    if img_dict.get('uuid') == uuid_to_add:
                        already_in_page_list = True
                        break
            
            if not already_in_page_list and hasattr(self.page, 'images'):
                # item_to_add ataması kaldırıldı.
                # self.image_data['pixmap_item'] = self.item_to_add 
                self.page.images.append(self.image_data) # Sadece veriyi ekle
                self._item_successfully_added_to_page_list = True # Bayrak hala kullanılabilir

            # if self.canvas: self.canvas.update() # Doğrudan canvas update'i yerine page değişikliğini işaretle
            if self.page and self._item_successfully_added_to_page_list:
                 self.page.mark_as_modified()
                 # Canvas'ın kendisini güncellemesi page değişikliği sinyali ile tetiklenmeli.
                 if self.page.drawing_canvas:
                     self.page.drawing_canvas.update()
                 logging.info(f"AddImageCommand executed: Image UUID={uuid_to_add} added to page list.")

        except Exception as e:
            logging.error(f"Komut execute edilirken hata oluştu: AddImageCommand - {e}", exc_info=True)
            # Başarısız olduysa bayrakları sıfırla
            # self._item_successfully_added_to_canvas_list = False # Kaldırıldı
            self._item_successfully_added_to_page_list = False

    def undo(self):
        """Eklenen resmi Page'den kaldırır."""
        try:
            # Canvas listesinden kaldırma kaldırıldı.
            # if self._item_successfully_added_to_canvas_list and self.canvas and self.item_to_add in self.canvas.image_items:
            #     self.canvas.image_items.remove(self.item_to_add)
            #     self._item_successfully_added_to_canvas_list = False 
            # ... (diğer canvas ile ilgili kontroller kaldırıldı)
            
            # Page.images listesinden UUID'ye göre kaldır
            uuid_to_remove = self.image_data.get('uuid')
            if self._item_successfully_added_to_page_list and self.page and hasattr(self.page, 'images') and uuid_to_remove:
                original_len = len(self.page.images)
                item_found_in_page_list = False
                for i, img_dict in enumerate(self.page.images):
                    if img_dict.get('uuid') == uuid_to_remove:
                        del self.page.images[i]
                        item_found_in_page_list = True
                        break
                
                if item_found_in_page_list:
                    self._item_successfully_added_to_page_list = False 
                else:
                    logging.warning(f"AddImageCommand undo: UUID {uuid_to_remove} page.images'da bulunamadı (bayrak True olmasına rağmen).")
                    self._item_successfully_added_to_page_list = False
            # ... (bayrak False iken kontrol etme mantığı aynı kalabilir)
            
            # if self.canvas: self.canvas.update() # Doğrudan canvas update'i yerine page değişikliğini işaretle
            if self.page:
                self.page.mark_as_modified()
                # Canvas'ın kendisini güncellemesi page değişikliği sinyali ile tetiklenmeli.
                if self.page.drawing_canvas:
                     self.page.drawing_canvas.update()
            logging.info(f"AddImageCommand undone: Image UUID={self.image_data.get('uuid')}")
        except Exception as e:
            logging.error(f"Komut undo edilirken hata oluştu: AddImageCommand - {e}", exc_info=True)

# --- YENİ: Döndürme Komutu --- #
class RotateItemsCommand(Command):
    """Seçili öğelerin döndürülmesini temsil eder (şimdilik sadece resimler)."""
    def __init__(self, canvas: 'DrawingCanvas', item_indices: List[Tuple[str, int]], 
                 original_states: List[Dict[str, Any]], # Bunlar _get_current_selection_states'ten geliyor ve QPixmap içermiyor olmalı
                 final_states: List[Dict[str, Any]]):   # Bunlar _get_current_selection_states'ten geliyor ve QPixmap içermiyor olmalı
        super().__init__() 
        self.canvas = canvas
        self.item_indices = copy.deepcopy(item_indices) 
        
        # original_states ve final_states zaten _get_current_selection_states'ten
        # QPixmap/QGraphicsPixmapItem olmadan geldiği varsayılıyor.
        # Bu yüzden doğrudan deepcopy yapabiliriz.
        self.original_states_safe = copy.deepcopy(original_states)
        self.final_states_safe = copy.deepcopy(final_states)
        
        self.item_type = item_indices[0][0] if item_indices else None
        self.description = f"Rotate {len(item_indices)} {self.item_type if self.item_type else 'item'}(s)"

        if self.original_states_safe and len(self.original_states_safe) > 0 and self.original_states_safe[0] and \
           self.final_states_safe and len(self.final_states_safe) > 0 and self.final_states_safe[0]:
            pass
        elif not (self.original_states_safe and self.final_states_safe):
             logging.warning("RotateCommand: original_states_safe veya final_states_safe listesi boş.")
        elif not (len(self.original_states_safe) > 0 and self.original_states_safe[0] and len(self.final_states_safe) > 0 and self.final_states_safe[0]):
            logging.warning("RotateCommand: İlk state listelerinden biri boş veya ilk state'lerden biri None.")

    def _apply_item_states(self, states_to_apply: List[Dict[str, Any]]):
        """Verilen state listesini (tam öğe verileri içeren) canvas'a uygular."""
        if len(states_to_apply) != len(self.item_indices):
            logging.error(f"RotateItemsCommand._apply_item_states: State sayısı ({len(states_to_apply)}) ile indeks sayısı ({len(self.item_indices)}) eşleşmiyor!")
            return

        try:
            if not self.canvas._parent_page:
                logging.error("RotateItemsCommand._apply_item_states: Canvas'ın _parent_page referansı yok!")
                return
                
            for i, (item_type, index) in enumerate(self.item_indices):
                item_full_data = states_to_apply[i]
                if item_full_data is None:
                    logging.warning(f"RotateItemsCommand._apply_item_states: Öğenin state'i None: {item_type}[{index}]")
                    continue

                if item_type == 'images':
                    if 0 <= index < len(self.canvas._parent_page.images):
                        img_data_ref = self.canvas._parent_page.images[index] # Referans olarak al
                        
                        new_angle = item_full_data.get('angle', 0.0)
                        new_rect_world = QRectF(item_full_data.get('rect', QRectF())) # QRectF olduğundan emin ol

                        if new_rect_world.isNull():
                            logging.warning(f"RotateItemsCommand: Uygulanacak state için rect null: {item_type}[{index}]")
                            continue

                        img_data_ref['angle'] = new_angle
                        img_data_ref['rect'] = new_rect_world # img_data içindeki rect'i de güncelle

                        pixmap_item = img_data_ref.get('pixmap_item')
                        scaled_pixmap_from_state = item_full_data.get('pixmap') 

                        if pixmap_item and isinstance(pixmap_item, QGraphicsPixmapItem):
                            current_pixmap_on_item = pixmap_item.pixmap()
                            pixmap_to_set = None
                            
                            if scaled_pixmap_from_state and not scaled_pixmap_from_state.isNull():
                                pixmap_to_set = scaled_pixmap_from_state
                            elif current_pixmap_on_item and not current_pixmap_on_item.isNull():
                                pixmap_to_set = current_pixmap_on_item 
                            elif img_data_ref.get('original_pixmap_for_scaling'):
                                original_pixmap = img_data_ref['original_pixmap_for_scaling']
                                if original_pixmap and not original_pixmap.isNull():
                                    pixmap_to_set = original_pixmap.scaled(
                                        new_rect_world.size().toSize(),
                                        Qt.AspectRatioMode.IgnoreAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation
                                    )
                                else:
                                    logging.warning(f"  RotateCommand: original_pixmap_for_scaling is null for item {index}.")
                                    continue 
                            else:
                                logging.warning(f"  RotateCommand: No valid pixmap found for item {index}.")
                                continue 

                            if not pixmap_to_set or pixmap_to_set.isNull():
                                logging.warning(f"  RotateCommand: pixmap_to_set is null before applying to item {index}")
                                continue

                            pixmap_item.setPixmap(pixmap_to_set)
                            
                            pixmap_local_center = QPointF(pixmap_to_set.width() / 2.0, pixmap_to_set.height() / 2.0)
                            pixmap_item.setTransformOriginPoint(pixmap_local_center)
                            
                            final_transform = QTransform()
                            final_transform.translate(new_rect_world.center().x(), new_rect_world.center().y())
                            final_transform.rotate(new_angle)
                            final_transform.translate(-pixmap_local_center.x(), -pixmap_local_center.y())
                            
                            final_pos_for_item = final_transform.map(QPointF(0.0, 0.0))

                            pixmap_item.setRotation(new_angle) 
                            pixmap_item.setPos(final_pos_for_item)
                        elif not pixmap_item:
                            logging.warning(f"RotateItemsCommand: pixmap_item not found in img_data for index {index}")
                    else:
                        logging.warning(f"RotateItemsCommand._apply_item_states: Geçersiz resim indexi {index}.")
                else:
                    logging.warning(f"RotateItemsCommand._apply_item_states: Desteklenmeyen öğe tipi: {item_type}")
            self.canvas.update() 
        except Exception as e:
            logging.error(f"RotateItemsCommand._apply_item_states hatası: {e}", exc_info=True)

    def execute(self):
        # logging.debug(f"RotateCommand execute: Applying final states for {len(self.final_states_safe)} items.") # Log eklendi
        self._apply_item_states(self.final_states_safe)
        if self.canvas:
            # self.canvas._load_qgraphics_pixmap_items_from_page() # KALDIRILDI
            self.canvas.update()
            self.canvas.selection_changed.emit() # Seçim değişmese de tutamaçlar vs. güncellenebilir
        # logging.debug("RotateCommand execute finished.") # Log eklendi

    def undo(self):
        # logging.debug(f"RotateCommand undo: Applying original states for {len(self.original_states_safe)} items.") # Log eklendi
        self._apply_item_states(self.original_states_safe)
        if self.canvas:
            # self.canvas._load_qgraphics_pixmap_items_from_page() # KALDIRILDI
            self.canvas.update()
            self.canvas.selection_changed.emit()
        # logging.debug("RotateCommand undo finished.") # Log eklendi


# --- --- --- --- --- --- --- -- #

class PasteItemsCommand(Command):
    """Clipboard'dan öğeleri yapıştırmak için kullanılan komut sınıfı."""
    
    def __init__(self, canvas, items_to_paste):
        self.canvas = canvas
        self.items_to_paste = items_to_paste
        self.pasted_indices = []  # Yapıştırılan öğelerin indisleri
    
    def execute(self):
        self.pasted_indices = []
        for item_type, item_data in self.items_to_paste:
            yeni_data = copy.deepcopy(item_data)
            if item_type == 'lines' and len(yeni_data) > 2:
                yeni_data[2] = [QPointF(pt.x()+20, pt.y()+20) for pt in yeni_data[2]]
                self.canvas.lines.append(yeni_data)
                self.pasted_indices.append(('lines', len(self.canvas.lines)-1))
            elif item_type == 'shapes' and len(yeni_data) > 4:
                # Şekil tipine göre kontrol yaparak işlem gerçekleştir
                if yeni_data[0] == ToolType.EDITABLE_LINE and len(yeni_data) > 3:
                    # Düzenlenebilir çizgi için özel işlem
                    # Kontrol noktalarını öteleme
                    control_points = yeni_data[3]
                    control_points = [[p[0]+20, p[1]+20] for p in control_points]
                    yeni_data[3] = control_points
                else:
                    # Normal şekiller için
                    # Dikdörtgen ve oval gibi şekilleri öteleme
                    rect = yeni_data[1]
                    if isinstance(rect, QRectF):
                        yeni_data[1] = QRectF(rect.x()+20, rect.y()+20, rect.width(), rect.height())
                
                self.canvas.shapes.append(yeni_data)
                self.pasted_indices.append(('shapes', len(self.canvas.shapes)-1))
            
            elif item_type == 'bspline_strokes' and hasattr(self.canvas, 'b_spline_strokes'):
                # B-Spline çizgileri için özel işlem
                if 'control_points' in yeni_data:
                    # Kontrol noktalarını öteleme (20 piksel sağa ve aşağıya)
                    import numpy as np
                    if isinstance(yeni_data['control_points'], np.ndarray):
                        yeni_data['control_points'] = yeni_data['control_points'] + np.array([20, 20])
                
                # Yapıştırılan B-spline'ı ekle ve indisini kaydet
                self.canvas.b_spline_strokes.append(yeni_data)
                self.pasted_indices.append(('bspline_strokes', len(self.canvas.b_spline_strokes)-1))
                logging.info(f"B-spline çizgisi yapıştırıldı. İndis: {len(self.canvas.b_spline_strokes)-1}")
            
            elif item_type == 'images' and hasattr(self.canvas._parent_page, 'images'):
                # Resim verisi
                if len(yeni_data) >= 3:  # rect, path, pixmap
                    # Resimleri öteleme
                    rect = yeni_data.get('rect')
                    if isinstance(rect, QRectF):
                        yeni_data['rect'] = QRectF(rect.x()+20, rect.y()+20, rect.width(), rect.height())
                
                self.canvas._parent_page.images.append(yeni_data)
                self.pasted_indices.append(('images', len(self.canvas._parent_page.images)-1))
        
        # Canvas'ı yeniden çiz
        if hasattr(self.canvas, '_load_qgraphics_items'):
            self.canvas._load_qgraphics_items()
        self.canvas.update()
        return True
    
    def undo(self):
        # Yapıştırılan öğeleri geri al
        for item_type, idx in sorted(self.pasted_indices, reverse=True):
            if item_type == 'lines' and 0 <= idx < len(self.canvas.lines):
                del self.canvas.lines[idx]
            elif item_type == 'shapes' and 0 <= idx < len(self.canvas.shapes):
                del self.canvas.shapes[idx]
            elif item_type == 'bspline_strokes' and hasattr(self.canvas, 'b_spline_strokes') and 0 <= idx < len(self.canvas.b_spline_strokes):
                del self.canvas.b_spline_strokes[idx]
            elif item_type == 'images' and hasattr(self.canvas._parent_page, 'images') and 0 <= idx < len(self.canvas._parent_page.images):
                del self.canvas._parent_page.images[idx]
        
        if hasattr(self.canvas, '_load_qgraphics_items'):
            self.canvas._load_qgraphics_items()
        self.canvas.update()
        logging.info("PasteItemsCommand: Undo ile yapıştırılan öğeler kaldırıldı.")
        return True

# QPixmap ve QGraphicsPixmapItem gibi nesneleri kopyalamadan atlayan yardımcı fonksiyon

def _copy_image_data_without_qpixmap(img_data):
    safe_data = {}
    for k, v in img_data.items():
        if k in ('pixmap', 'original_pixmap_for_scaling', 'pixmap_item'):
            continue
        safe_data[k] = copy.deepcopy(v)
    return safe_data

class DeleteItemsCommand(Command):
    """Seçili öğeleri silme işlemini Undo/Redo ile yönetir."""
    def __init__(self, canvas: 'DrawingCanvas', item_indices: list):
        self.canvas = canvas
        self.item_indices = sorted(item_indices, reverse=True)  # [('lines', idx), ...] - Büyükten küçüğe silinecek
        self.deleted_items = []  # [('lines', idx, data), ...]

    def execute(self):
        self.deleted_items = []
        for item_type, idx in self.item_indices:
            if item_type == 'lines' and 0 <= idx < len(self.canvas.lines):
                data = copy.deepcopy(self.canvas.lines[idx])
                del self.canvas.lines[idx]
                self.deleted_items.append(('lines', idx, data))
            elif item_type == 'shapes' and 0 <= idx < len(self.canvas.shapes):
                data = copy.deepcopy(self.canvas.shapes[idx])
                del self.canvas.shapes[idx]
                self.deleted_items.append(('shapes', idx, data))
            elif item_type == 'bspline_strokes' and hasattr(self.canvas, 'b_spline_strokes') and 0 <= idx < len(self.canvas.b_spline_strokes):
                data = copy.deepcopy(self.canvas.b_spline_strokes[idx])
                del self.canvas.b_spline_strokes[idx]
                self.deleted_items.append(('bspline_strokes', idx, data))
            elif item_type == 'images' and hasattr(self.canvas._parent_page, 'images') and 0 <= idx < len(self.canvas._parent_page.images):
                data = _copy_image_data_without_qpixmap(self.canvas._parent_page.images[idx])
                del self.canvas._parent_page.images[idx]
                self.deleted_items.append(('images', idx, data))
        if hasattr(self.canvas, '_load_qgraphics_pixmap_items_from_page'):
            self.canvas._load_qgraphics_pixmap_items_from_page()
        self.canvas.selected_item_indices = []
        self.canvas.update()
        logging.info(f"DeleteItemsCommand: {len(self.deleted_items)} öğe silindi.")
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def undo(self):
        # Silinen öğeleri eski indekslerine geri ekle
        for item_type, idx, data in sorted(self.deleted_items, key=lambda x: x[1]):
            if item_type == 'lines':
                self.canvas.lines.insert(idx, data)
            elif item_type == 'shapes':
                self.canvas.shapes.insert(idx, data)
                logging.debug(f"DeleteItemsCommand.undo: shapes'e eklenen veri: {data}")
                logging.debug(f"DeleteItemsCommand.undo: shapes'in son hali: {self.canvas.shapes}")
            elif item_type == 'bspline_strokes' and hasattr(self.canvas, 'b_spline_strokes'):
                self.canvas.b_spline_strokes.insert(idx, data)
                logging.debug(f"DeleteItemsCommand.undo: b_spline_strokes'a eklenen veri: {data}")
            elif item_type == 'images' and hasattr(self.canvas._parent_page, 'images'):
                # QPixmap'ı path üzerinden tekrar yükle
                from PyQt6.QtGui import QPixmap
                img_data = dict(data) # Kopya oluştur
                if 'path' in img_data:
                    pixmap = QPixmap(img_data['path'])
                    img_data['pixmap'] = pixmap
                    img_data['original_pixmap_for_scaling'] = pixmap
                self.canvas._parent_page.images.insert(idx, img_data)
        if hasattr(self.canvas, '_load_qgraphics_pixmap_items_from_page'):
            self.canvas._load_qgraphics_pixmap_items_from_page()
        self.canvas.update()
        logging.debug(f"DeleteItemsCommand.undo: canvas.update() çağrıldı, id={id(self.canvas)}")
        logging.info("DeleteItemsCommand: Undo ile silinen öğeler geri getirildi.")
        logging.debug(f"DeleteItemsCommand.undo: BİTİŞ. shapes id={id(self.canvas.shapes)}, içerik={self.canvas.shapes}")
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

class DrawEditableLineCommand(Command):
    """Düzenlenebilir Bezier çizgisi çizme işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', 
                 control_points: List[QPointF], 
                 color: tuple, 
                 width: float,
                 line_style: str = 'solid'):
        """Başlatıcı.

        Args:
            canvas: İşlemin uygulanacağı DrawingCanvas örneği.
            control_points: Bezier eğrisi kontrol noktaları listesi [p0, c1, c2, p1, ...].
            color: Renk tuple'ı (R, G, B, A -> 0-1 float).
            width: Çizgi kalınlığı.
            line_style: Çizgi stili ('solid', 'dashed', vb.).
        """
        self.canvas = canvas
        
        # Bezier eğrisi verilerini sakla
        self.line_data = {
            'tool_type': ToolType.EDITABLE_LINE,
            'control_points': copy.deepcopy(control_points),
            'color': color,
            'width': width,
            'line_style': line_style
        }

        self._line_added = False
        self._added_index = -1

    def execute(self):
        logging.debug("DrawEditableLineCommand: execute() çağrıldı.")
        try:
            if not hasattr(self.canvas, 'shapes') or not isinstance(self.canvas.shapes, list):
                logging.error("DrawEditableLineCommand: Canvas.shapes bulunamadı veya liste değil.")
                self._line_added = False
                return

            # DrawEditableLineCommand verilerini Shape formatına dönüştür
            shape_data_to_add = [
                self.line_data['tool_type'],
                self.line_data['color'],
                self.line_data['width'],
                copy.deepcopy(self.line_data['control_points']),  # Tüm kontrol noktaları
                self.line_data['line_style']
            ]

            if self._line_added: # Redo durumu
                if 0 <= self._added_index <= len(self.canvas.shapes):
                    self.canvas.shapes.insert(self._added_index, shape_data_to_add)
                else:
                    self.canvas.shapes.append(shape_data_to_add)
            elif not self._line_added:
                self._added_index = len(self.canvas.shapes)
                self.canvas.shapes.append(shape_data_to_add)
                self._line_added = True

            self.canvas.update()
            if hasattr(self.canvas, 'content_changed'):
                self.canvas.content_changed.emit()
            if hasattr(self.canvas, 'selection_changed'):
                self.canvas.selection_changed.emit()
        except Exception as e:
            logging.error(f"DrawEditableLineCommand execute hatası: {e}", exc_info=True)
            self._line_added = False
            self._added_index = -1
        logging.debug("DrawEditableLineCommand: execute() tamamlandı.")

    def undo(self):
        logging.debug("DrawEditableLineCommand.undo: BAŞLANGIÇ.")
        """Eklenen düzenlenebilir çizgiyi canvas'tan kaldırır."""
        if not self._line_added or self._added_index < 0:
            return
        try:
            if 0 <= self._added_index < len(self.canvas.shapes):
                del self.canvas.shapes[self._added_index]
                self._line_added = False
                self.canvas.update()
                if hasattr(self.canvas, 'content_changed'):
                    self.canvas.content_changed.emit()
                if hasattr(self.canvas, 'selection_changed'):
                    self.canvas.selection_changed.emit()
        except IndexError:
            logging.error(f"DrawEditableLineCommand undo: Index hatası oluştu. index={self._added_index}, shapes_len={len(self.canvas.shapes)}", exc_info=True)
        except Exception as e:
            logging.error(f"DrawEditableLineCommand undo hatası: {e}", exc_info=True)
            self._line_added = False

# TODO: ResizeItemsCommand, DeleteItemsCommand eklenecek

class UpdateEditableLineCommand:
    """Düzenlenebilir çizginin kontrol noktalarını, kalınlığını ve rengini güncelleyen komut."""
    
    def __init__(self, canvas, shape_index, original_points, new_points, original_width=None, new_width=None, original_color=None, new_color=None):
        """
        Args:
            canvas: Çizim canvas'ı referansı
            shape_index: Düzenlenen shape'in indeksi
            original_points: Orijinal kontrol noktaları listesi
            new_points: Yeni kontrol noktaları listesi
            original_width: Orijinal çizgi kalınlığı (float)
            new_width: Yeni çizgi kalınlığı (float)
            original_color: Orijinal renk (tuple)
            new_color: Yeni renk (tuple)
        """
        self.canvas = canvas
        self.shape_index = shape_index
        self.original_points = original_points.copy()
        self.new_points = new_points.copy()
        self.original_width = original_width
        self.new_width = new_width
        self.original_color = original_color
        self.new_color = new_color
        self.description = "Düzenlenebilir Çizgi Güncelleme"
    
    def execute(self):
        """Komutu uygular: Düzenlenebilir çizginin kontrol noktalarını, kalınlığını ve rengini günceller."""
        if 0 <= self.shape_index < len(self.canvas.shapes):
            self.canvas.shapes[self.shape_index][3] = self.new_points.copy()
            if self.new_width is not None:
                self.canvas.shapes[self.shape_index][2] = self.new_width
            if self.new_color is not None:
                self.canvas.shapes[self.shape_index][1] = self.new_color
            self.canvas.update()
    
    def undo(self):
        """Komutu geri alır: Düzenlenebilir çizginin kontrol noktalarını, kalınlığını ve rengini orijinal haline döndürür."""
        if 0 <= self.shape_index < len(self.canvas.shapes):
            self.canvas.shapes[self.shape_index][3] = self.original_points.copy()
            if self.original_width is not None:
                self.canvas.shapes[self.shape_index][2] = self.original_width
            if self.original_color is not None:
                self.canvas.shapes[self.shape_index][1] = self.original_color
            self.canvas.update()
    
    def redo(self):
        """Komutu yeniden uygular: Düzenlenebilir çizginin kontrol noktalarını, kalınlığını ve rengini tekrar günceller."""
        self.execute()

class DrawBsplineCommand(Command):
    """Bir B-Spline stroke çizme işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', stroke_data: dict):
        """
        Args:
            canvas: İşlemin uygulanacağı DrawingCanvas örneği.
            stroke_data: Çizilecek B-Spline verisi.
        """
        self.canvas = canvas
        self.stroke_data = copy.deepcopy(stroke_data) # Derin kopya al
        self._stroke_added = False # Stroke'un listeye eklenip eklenmediğini takip eder
        self._added_index = -1     # Listeye eklendiği indeksi saklar

    def execute(self):
        """Stroke'u canvas'ın b_spline_strokes listesine ekler."""
        # logging.debug(f"DrawBsplineCommand execute: _stroke_added={self._stroke_added}, _added_index={self._added_index}")
        
        if not hasattr(self.canvas, 'b_spline_strokes') or not isinstance(self.canvas.b_spline_strokes, list):
            logging.error("DrawBsplineCommand: Canvas.b_spline_strokes bulunamadı veya liste değil.")
            self._stroke_added = False # Emin olmak için
            self._added_index = -1
            return

        if not self._stroke_added: # İlk execute
            self.canvas.b_spline_strokes.append(copy.deepcopy(self.stroke_data))
            self._added_index = len(self.canvas.b_spline_strokes) - 1
            self._stroke_added = True
            logging.debug(f"DrawBsplineCommand execute (initial): Stroke added at index {self._added_index}.")
        else: # Redo durumu (self._stroke_added zaten True)
            # Stroke'un redo için doğru indekse eklenmesi gerekir.
            if 0 <= self._added_index <= len(self.canvas.b_spline_strokes):
                self.canvas.b_spline_strokes.insert(self._added_index, copy.deepcopy(self.stroke_data))
                logging.debug(f"DrawBsplineCommand execute (redo): Stroke inserted at index {self._added_index}.")
            else:
                # Bu durum beklenmedik, belki sona ekleyebiliriz veya hata verebiliriz.
                logging.warning(f"DrawBsplineCommand execute (redo): Invalid _added_index {self._added_index}. Appending to end.")
                self.canvas.b_spline_strokes.append(copy.deepcopy(self.stroke_data))
                self._added_index = len(self.canvas.b_spline_strokes) - 1 # Index'i güncelle
        
        self.canvas.update()
        if hasattr(self.canvas, 'selection_changed'):
            self.canvas.selection_changed.emit()

    def undo(self):
        """Stroke'u self._added_index'ten kaldırır."""
        # logging.debug(f"DrawBsplineCommand undo: _stroke_added={self._stroke_added}, _added_index={self._added_index}")

        if not self._stroke_added: # Eğer execute hiç başarılı olmadıysa veya zaten undo yapıldıysa
            logging.debug("DrawBsplineCommand undo: Stroke was not added or already undone. Skipping.")
            return

        try:
            if 0 <= self._added_index < len(self.canvas.b_spline_strokes):
                # Stroke'u silmeden önce bir kontrol (opsiyonel): self.canvas.b_spline_strokes[self._added_index] == self.stroke_data
                del self.canvas.b_spline_strokes[self._added_index]
                logging.debug(f"DrawBsplineCommand undo: Stroke removed from index {self._added_index}.")
                # self._stroke_added = False # UNDO SONRASI FALSE YAPMA, REDO İÇİN TRUE KALMALI VE INDEX KORUNMALI
                                        # Diğer komutlar (DrawLine, DrawShape) da kendi flag'lerini undo'da değiştirmiyor.
                self.canvas.update()
                if hasattr(self.canvas, 'selection_changed'):
                    self.canvas.selection_changed.emit()
            else:
                logging.warning(f"DrawBsplineCommand undo: Invalid _added_index {self._added_index} or stroke not found at index. len(strokes)={len(self.canvas.b_spline_strokes)}")
        except IndexError:
            logging.error(f"DrawBsplineCommand undo: Index hatası. _added_index={self._added_index}", exc_info=True)
        except Exception as e:
            logging.error(f"DrawBsplineCommand undo: Stroke kaldırılırken hata: {e}", exc_info=True)

class UpdateBsplineControlPointCommand(Command):
    """Bir B-Spline kontrol noktasının pozisyonunu güncelleme işlemini temsil eder."""
    def __init__(self, canvas: 'DrawingCanvas', stroke_idx: int, cp_idx: int, old_pos_np, new_pos_np):
        self.canvas = canvas
        self.stroke_idx = stroke_idx
        self.cp_idx = cp_idx
        self.old_pos_np = old_pos_np.copy() # Pozisyonları kopyala
        self.new_pos_np = new_pos_np.copy()

    def _set_control_point_position(self, pos_array: np.ndarray):
        """Belirtilen pozisyonu stroke'taki kontrol noktasına atar."""
        try:
            if 0 <= self.stroke_idx < len(self.canvas.b_spline_strokes):
                stroke_data = self.canvas.b_spline_strokes[self.stroke_idx]
                if 'control_points' in stroke_data and \
                   0 <= self.cp_idx < len(stroke_data['control_points']):
                    stroke_data['control_points'][self.cp_idx] = pos_array.copy()
                    self.canvas.update()
                    if hasattr(self.canvas, 'content_changed'):
                        self.canvas.content_changed.emit()
                    return True
            logging.warning(f"UpdateBsplineControlPointCommand: Geçersiz stroke_index ({self.stroke_idx}) veya cp_index ({self.cp_idx}).")
            return False
        except Exception as e:
            logging.error(f"UpdateBsplineControlPointCommand _set_control_point_position: Hata. {e}", exc_info=True)
            return False

    def execute(self):
        """Kontrol noktasının pozisyonunu yeni değere günceller."""
        logging.debug(f"UpdateBsplineControlPointCommand executing: Stroke {self.stroke_idx}, CP {self.cp_idx} to {self.new_pos_np}")
        self._set_control_point_position(self.new_pos_np)

    def undo(self):
        """Kontrol noktasının pozisyonunu eski değere geri döndürür."""
        logging.debug(f"UpdateBsplineControlPointCommand undoing: Stroke {self.stroke_idx}, CP {self.cp_idx} to {self.old_pos_np}")
        self._set_control_point_position(self.old_pos_np)
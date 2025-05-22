"""
DrawingCanvas için temel çizim yardımcı fonksiyonları.
Bu fonksiyonlar genellikle DrawingCanvas.paintEvent() içinden çağrılır.
"""
import logging
from typing import TYPE_CHECKING
import math

from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QCursor, QPainterPath, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsPixmapItem

from utils import selection_helpers, geometry_helpers # selection_helpers ve geometry_helpers gerekebilir
# from utils import geometry_helpers # _draw_selection_overlay içinde kullanılıyor
# from gui.enums import ToolType # _draw_items içinde kullanılıyor
# from .drawing_canvas import rgba_to_qcolor # _draw_items içinde kullanılıyor

if TYPE_CHECKING:
    from .drawing_canvas import DrawingCanvas # ../drawing_canvas.py olmalı, ama aynı seviyede varsayalım
    from .enums import ToolType

def rgba_to_qcolor_local(rgba: tuple) -> QColor:
    """rgba_to_qcolor'ın yerel bir kopyası, circular import önlemek için.
       DrawingCanvas'taki ile aynı olmalı.
    """
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        return QColor(Qt.GlobalColor.black) 
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    return QColor(r, g, b, a)

def draw_items(canvas: 'DrawingCanvas', painter: QPainter):
    """Tüm kalıcı öğeleri (çizgiler, şekiller, resimler) çizer. Optimizasyonlu."""
    from .enums import ToolType
    from utils.drawing_helpers import draw_pen_stroke, draw_shape
    # --- RESİMLERİ ÇİZ (scaled_pixmap cache ile) --- #
    if canvas._parent_page and hasattr(canvas._parent_page, 'images') and canvas._parent_page.images:
        for item_index, img_data in enumerate(canvas._parent_page.images):
            current_pixmap = img_data.get('pixmap')
            current_rect = img_data.get('rect')
            current_angle = img_data.get('angle', 0.0)
            uuid = img_data.get('uuid')
            if current_pixmap and not current_pixmap.isNull() and current_rect and current_rect.isValid():
                item_size = current_rect.size()
                cache_key = (int(item_size.width()), int(item_size.height()), float(current_angle))
                if img_data.get('_scaled_pixmap_cache_key') != cache_key:
                    scaled_pixmap = current_pixmap.scaled(
                        int(item_size.width()), int(item_size.height()),
                        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    img_data['_scaled_pixmap'] = scaled_pixmap
                    img_data['_scaled_pixmap_cache_key'] = cache_key
                else:
                    scaled_pixmap = img_data.get('_scaled_pixmap')
                if scaled_pixmap is None:
                    continue  # Pixmap yoksa çizme
                offset_x = (item_size.width() - scaled_pixmap.width()) / 2
                offset_y = (item_size.height() - scaled_pixmap.height()) / 2
                if current_angle != 0.0:
                    painter.save()
                    item_pos = current_rect.topLeft()
                    painter.translate(item_pos.x(), item_pos.y())
                    painter.translate(item_size.width() / 2, item_size.height() / 2)
                    painter.rotate(current_angle)
                    painter.translate(-item_size.width() / 2, -item_size.height() / 2)
                    painter.drawPixmap(QPointF(offset_x, offset_y), scaled_pixmap)
                    painter.restore()
                else:
                    item_pos = current_rect.topLeft()
                    painter.drawPixmap(QPointF(item_pos.x() + offset_x, item_pos.y() + offset_y), scaled_pixmap)
    # --- ÇİZGİLERİ ÇİZ --- #
    if hasattr(canvas, 'lines') and canvas.lines:
        for line_data in canvas.lines:
            if len(line_data) >= 4:
                color, width, points, line_style = line_data[0], line_data[1], line_data[2], line_data[3]
            else:
                color, width, points = line_data[0], line_data[1], line_data[2]
                line_style = 'solid'
            draw_pen_stroke(painter, points, color, width, line_style)
    # --- ŞEKİLLERİ ÇİZ --- #
    if hasattr(canvas, 'shapes') and canvas.shapes:
        for i, shape_data in enumerate(canvas.shapes):
            if not shape_data or len(shape_data) < 5:
                continue
            if len(shape_data) >= 6:
                line_style = shape_data[5]
            else:
                line_style = 'solid'
            draw_shape(painter, shape_data, line_style)
    elif hasattr(canvas, 'shapes'):
        # logging.debug("draw_items: Shapes listesi var ama boş.")
        pass
    else:
        # logging.debug("draw_items: Shapes listesi (nitelik olarak) yok.")
        pass

def draw_selection_overlay(canvas: 'DrawingCanvas', painter: QPainter):
    from gui.enums import ToolType
    
    if not canvas.selected_item_indices:
        canvas.current_handles.clear()
        return
        
    # canvas.current_handles.clear() # Her çizimden önce tutamaçları temizle (her blok kendi yönetecek)

    # --- ÇOKLU SEÇİM DURUMU --- #
    if len(canvas.selected_item_indices) > 1:
        painter.save() 
        combined_bbox_world = QRectF()
        for item_type_loop, index_loop in canvas.selected_item_indices:
            current_item_bbox_world = QRectF()
            if item_type_loop == 'lines' and 0 <= index_loop < len(canvas.lines):
                item_data_loop = canvas.lines[index_loop]
                current_item_bbox_world = geometry_helpers.get_item_bounding_box(item_data_loop, item_type_loop)
            elif item_type_loop == 'shapes' and 0 <= index_loop < len(canvas.shapes):
                item_data_loop = canvas.shapes[index_loop]
                if canvas.shapes[index_loop][0] == ToolType.EDITABLE_LINE and canvas.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
                    continue 
                current_item_bbox_world = geometry_helpers.get_item_bounding_box(item_data_loop, item_type_loop)
            elif item_type_loop == 'bspline_strokes' and 0 <= index_loop < len(canvas.b_spline_strokes):
                item_data_loop = canvas.b_spline_strokes[index_loop]
                current_item_bbox_world = geometry_helpers.get_bspline_bounding_box(item_data_loop)
            elif item_type_loop == 'images' and canvas._parent_page and 0 <= index_loop < len(canvas._parent_page.images):
                img_data = canvas._parent_page.images[index_loop]
                rect = img_data.get('rect')
                if rect: # Döndürmeyi de hesaba katmak gerekirse get_rotated_corners kullanılmalı
                    current_item_bbox_world = QRectF(rect) # Şimdilik basit bbox
            
            if not current_item_bbox_world.isNull():
                if combined_bbox_world.isNull():
                    combined_bbox_world = current_item_bbox_world
                else:
                    combined_bbox_world = combined_bbox_world.united(current_item_bbox_world)
        
        if not combined_bbox_world.isNull():
            screen_top_left = canvas.world_to_screen(combined_bbox_world.topLeft())
            screen_bottom_right = canvas.world_to_screen(combined_bbox_world.bottomRight())
            selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
            frame_pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine); frame_pen.setCosmetic(True)
            painter.setPen(frame_pen); painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection_rect_screen)

            handle_size_screen = selection_helpers.HANDLE_SIZE
            half_handle_screen = handle_size_screen / 2.0
            handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
            handle_brush = QBrush(QColor(0, 100, 255, 128))
            painter.setPen(handle_pen); painter.setBrush(handle_brush)
            handle_positions_world = geometry_helpers.get_standard_handle_positions(combined_bbox_world)
            canvas.current_handles.clear() # Burada temizle
            for handle_name, pos_world in handle_positions_world.items():
                pos_screen = canvas.world_to_screen(pos_world)
                handle_rect_screen = QRectF(pos_screen.x() - half_handle_screen, pos_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                painter.drawRect(handle_rect_screen)
                canvas.current_handles[handle_name] = handle_rect_screen
        painter.restore()
        return # Çoklu seçim işlendi, çık

    # --- TEKİL SEÇİM DURUMU (len(canvas.selected_item_indices) == 1) --- #
    item_type, item_index = canvas.selected_item_indices[0]
    canvas.current_handles.clear() # Tekil seçim için de en başta temizle

    if item_type == 'images' and canvas._parent_page:
        painter.save() 
        # ... (mevcut images bloğu aynı kalır, sadece canvas.current_handles.clear() kendi bloğunun başına alınabilir)
        # ... (canvas.current_handles.clear() zaten yukarıda yapıldı)
        index = item_index 
        if 0 <= index < len(canvas._parent_page.images):
            img_data = canvas._parent_page.images[index]
            rect = img_data.get('rect')
            angle = img_data.get('angle', 0.0)
            if rect and isinstance(rect, QRectF):
                transformed_rect_poly = selection_helpers.get_rotated_rect_polygon(rect, angle)
                screen_poly = QPolygonF([canvas.world_to_screen(p) for p in transformed_rect_poly])
                painter.setPen(QPen(QColor(0, 0, 255, 200), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(screen_poly)
                
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                
                # canvas.current_handles.clear() # Zaten yukarıda yapıldı
                # if len(canvas.selected_item_indices) == 1: # Bu kontrol artık gereksiz, çünkü tekil seçim bloğundayız
                handle_positions_world = selection_helpers.calculate_handle_positions_for_rotated_rect(rect, angle)
                handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setWidth(2); handle_pen.setCosmetic(True)
                painter.setPen(handle_pen); painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                for handle_type_key, center_world in handle_positions_world.items():
                    center_screen = canvas.world_to_screen(center_world)
                    handle_rect = QRectF(center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                    painter.drawRect(handle_rect)
                    canvas.current_handles[handle_type_key] = handle_rect
                
                # Döndürme tutamacı
                top_center_world = QPointF(rect.center().x(), rect.top() - rect.height() * 0.2)
                if angle != 0:
                    angle_rad = math.radians(angle)
                    rect_center = rect.center()
                    dx = top_center_world.x() - rect_center.x()
                    dy = top_center_world.y() - rect_center.y()
                    rotated_x = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
                    rotated_y = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
                    top_center_world = QPointF(rect_center.x() + rotated_x, rect_center.y() + rotated_y)
                top_center_screen = canvas.world_to_screen(top_center_world)
                center_screen = canvas.world_to_screen(rect.center())
                painter.setPen(QPen(QColor(0, 0, 0, 150), 1, Qt.PenStyle.DashLine))
                painter.drawLine(center_screen, top_center_screen)
                rotation_handle_pen = QPen(QColor(0,0,0,150)); rotation_handle_pen.setCosmetic(True)
                painter.setPen(rotation_handle_pen)
                painter.setBrush(QBrush(QColor(255, 100, 100, 150)))
                rotation_handle_rect = QRectF(top_center_screen.x() - half_handle_screen, top_center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                painter.drawEllipse(rotation_handle_rect)
                canvas.current_handles['rotation'] = rotation_handle_rect
        painter.restore() 
        return 

    # --- TEKİL SEÇİM: Çizgi (PEN ile çizilen) veya Şekil (PATH dahil) ---
    # YENİ YAPI: Önce 'lines' mı 'shapes' mı diye ayır.
    elif item_type == 'lines': # PEN ile çizilen serbest çizimler (Path'ler)
        painter.save()
        if 0 <= item_index < len(canvas.lines):
            line_data = canvas.lines[item_index]
            # line_data yapısı: [color_tuple, width_float, List[QPointF], line_style_str]
            points_world = line_data[2] if len(line_data) > 2 else []

            if not points_world or len(points_world) < 1: # En az 1 nokta olmalı (bbox için 2 daha iyi)
                painter.restore()
                return

            # 1. Sınırlayıcı kutuyu (bounding box) çiz
            bbox_world = geometry_helpers.get_item_bounding_box(line_data, 'lines')
            if not bbox_world.isNull():
                screen_top_left = canvas.world_to_screen(bbox_world.topLeft())
                screen_bottom_right = canvas.world_to_screen(bbox_world.bottomRight())
                selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
                frame_pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine)
                frame_pen.setCosmetic(True)
                painter.setPen(frame_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(selection_rect_screen)

                # 2. Tutamaçları çiz (sadece bbox köşe ve kenar ortaları)
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                handle_brush = QBrush(QColor(0, 100, 255, 128)) # Mavi tutamaçlar
                painter.setPen(handle_pen); painter.setBrush(handle_brush)

                handle_positions_world = geometry_helpers.get_standard_handle_positions(bbox_world)
                # canvas.current_handles.clear() # Zaten en başta temizlenmişti.
                for handle_name, pos_world in handle_positions_world.items():
                    pos_screen = canvas.world_to_screen(pos_world)
                    handle_rect_screen = QRectF(
                        pos_screen.x() - half_handle_screen,
                        pos_screen.y() - half_handle_screen,
                        handle_size_screen, handle_size_screen
                    )
                    painter.drawRect(handle_rect_screen)
                    canvas.current_handles[handle_name] = handle_rect_screen # Anahtarlar standart olacak (top_left, bottom_right vb.)
        painter.restore()
        return

    elif item_type == 'shapes':
        painter.save() 
        if 0 <= item_index < len(canvas.shapes):
            shape_data = canvas.shapes[item_index]
            tool_type = shape_data[0]
            if tool_type == ToolType.LINE:
                p1, p2 = shape_data[3], shape_data[4]
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                start_screen = canvas.world_to_screen(p1)
                end_screen = canvas.world_to_screen(p2)
                handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                handle_brush = QBrush(QColor(0, 100, 255, 128))
                painter.setPen(handle_pen); painter.setBrush(handle_brush)
                for key, center in [('start', start_screen), ('end', end_screen)]:
                    handle_rect = QRectF(center.x() - half_handle_screen, center.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                    painter.drawRect(handle_rect)
                    canvas.current_handles[key] = handle_rect
                painter.restore() 
                return 
            elif tool_type == ToolType.EDITABLE_LINE and canvas.current_tool != ToolType.EDITABLE_LINE_NODE_SELECTOR:
                control_points = shape_data[3]
                if not control_points or len(control_points) < 1:
                    painter.restore() 
                    return
                bbox_world = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                if not bbox_world.isNull():
                    screen_top_left = canvas.world_to_screen(bbox_world.topLeft())
                    screen_bottom_right = canvas.world_to_screen(bbox_world.bottomRight())
                    selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
                    frame_pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine); frame_pen.setCosmetic(True)
                    painter.setPen(frame_pen); painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(selection_rect_screen)
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                    handle_brush = QBrush(QColor(0, 100, 255, 128))
                    painter.setPen(handle_pen); painter.setBrush(handle_brush)
                    handle_positions_world = geometry_helpers.get_standard_handle_positions(bbox_world)
                    for handle_name, pos_world in handle_positions_world.items():
                        pos_screen = canvas.world_to_screen(pos_world)
                        handle_rect_screen = QRectF(pos_screen.x() - half_handle_screen, pos_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                        painter.drawRect(handle_rect_screen)
                        canvas.current_handles[handle_name] = handle_rect_screen
                painter.restore() 
                return
            elif tool_type in [ToolType.RECTANGLE, ToolType.CIRCLE]:
                bbox_world = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                if not bbox_world.isNull():
                    screen_top_left = canvas.world_to_screen(bbox_world.topLeft())
                    screen_bottom_right = canvas.world_to_screen(bbox_world.bottomRight())
                    selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
                    frame_pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine)
                    frame_pen.setCosmetic(True)
                    painter.setPen(frame_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(selection_rect_screen)
                    # --- Tutamaçları çiz ---
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                    handle_brush = QBrush(QColor(0, 100, 255, 128))
                    painter.setPen(handle_pen); painter.setBrush(handle_brush)
                    handle_positions_world = geometry_helpers.get_standard_handle_positions(bbox_world)
                    for handle_name, pos_world in handle_positions_world.items():
                        pos_screen = canvas.world_to_screen(pos_world)
                        handle_rect_screen = QRectF(
                            pos_screen.x() - half_handle_screen,
                            pos_screen.y() - half_handle_screen,
                            handle_size_screen, handle_size_screen
                        )
                        painter.drawRect(handle_rect_screen)
                        canvas.current_handles[handle_name] = handle_rect_screen
            elif tool_type == ToolType.PATH:
                # PATH için bbox ve tutamaçlar
                bbox_world = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                if not bbox_world.isNull():
                    screen_top_left = canvas.world_to_screen(bbox_world.topLeft())
                    screen_bottom_right = canvas.world_to_screen(bbox_world.bottomRight())
                    selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
                    frame_pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine)
                    frame_pen.setCosmetic(True)
                    painter.setPen(frame_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(selection_rect_screen)
                    # Tutamaçlar: PATH noktalarının hepsine tutamaç çiz
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                    handle_brush = QBrush(QColor(0, 100, 255, 128))
                    painter.setPen(handle_pen); painter.setBrush(handle_brush)
                    points = shape_data[3] if len(shape_data) > 3 else []
                    for idx, pt in enumerate(points):
                        pos_screen = canvas.world_to_screen(pt)
                        handle_rect_screen = QRectF(
                            pos_screen.x() - half_handle_screen,
                            pos_screen.y() - half_handle_screen,
                            handle_size_screen, handle_size_screen
                        )
                        painter.drawRect(handle_rect_screen)
                        canvas.current_handles[f'pt_{idx}'] = handle_rect_screen
                painter.restore()
                return
        painter.restore() 
        return 

    elif item_type == 'bspline_strokes':
        painter.save() 
        # ... (mevcut bspline_strokes bloğu aynı kalır, canvas.current_handles.clear() kendi bloğunun başına alınabilir)
        # ... (canvas.current_handles.clear() zaten yukarıda yapıldı)
        if 0 <= item_index < len(canvas.b_spline_strokes):
            stroke_data = canvas.b_spline_strokes[item_index]
            bbox_world = geometry_helpers.get_bspline_bounding_box(stroke_data)
            if not bbox_world.isNull():
                screen_top_left = canvas.world_to_screen(bbox_world.topLeft())
                screen_bottom_right = canvas.world_to_screen(bbox_world.bottomRight())
                selection_rect_screen = QRectF(screen_top_left, screen_bottom_right).normalized()
                pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine); pen.setCosmetic(True)
                painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(selection_rect_screen)

                handle_size_screen = selection_helpers.HANDLE_SIZE 
                half_handle_screen = handle_size_screen / 2.0
                handle_pen = QPen(Qt.GlobalColor.black); handle_pen.setCosmetic(True)
                handle_brush = QBrush(QColor(0, 100, 255, 128))
                painter.setPen(handle_pen); painter.setBrush(handle_brush)
                handle_positions_world = geometry_helpers.get_standard_handle_positions(bbox_world)
                # canvas.current_handles.clear() # Zaten yukarıda yapıldı
                for handle_name, pos_world in handle_positions_world.items():
                    pos_screen = canvas.world_to_screen(pos_world)
                    handle_rect_screen = QRectF(pos_screen.x() - half_handle_screen, pos_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                    painter.drawRect(handle_rect_screen)
                    canvas.current_handles[handle_name] = handle_rect_screen
        painter.restore() 
        return 
    
    # else bloğu kaldırıldı, çünkü ya çoklu seçim ya da tekil seçim yukarıda işlendi.
    # Eğer hiçbir koşul karşılanmazsa (ki bu olmamalı selected_item_indices doluysa), hiçbir şey çizilmez.

def draw_selection_rectangle(canvas: 'DrawingCanvas', painter: QPainter):
    #logging.debug(f"[canvas_drawing_helpers] draw_selection_rectangle: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    if not canvas.selecting or canvas.shape_start_point.isNull() or canvas.shape_end_point.isNull():
        return
    screen_start = canvas.world_to_screen(canvas.shape_start_point)
    screen_end = canvas.world_to_screen(canvas.shape_end_point)
    selection_rect = QRectF(screen_start, screen_end).normalized()
    painter.save()
    painter.setPen(QPen(QColor(0, 0, 255, 150), 1, Qt.PenStyle.DashLine))
    painter.setBrush(QBrush(QColor(0, 100, 255, 30)))
    painter.drawRect(selection_rect)
    painter.restore()

def draw_eraser_preview(canvas: 'DrawingCanvas', painter: QPainter):
    #logging.debug(f"[canvas_drawing_helpers] draw_eraser_preview: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(Qt.GlobalColor.gray, 1, Qt.PenStyle.SolidLine)
    brush = QBrush(QColor(128, 128, 128, 100))
    painter.setPen(pen)
    painter.setBrush(brush)
    radius = canvas.eraser_width / 2.0
    # QCursor.pos() global screen coordinates, need to map to widget
    pos_int = canvas.mapFromGlobal(QCursor.pos())
    if canvas.rect().contains(pos_int):
        painter.drawEllipse(QPointF(pos_int), radius, radius)
    painter.restore() 

def draw_grid_and_template(canvas: 'DrawingCanvas', painter: QPainter):
    from .enums import TemplateType

    # Eğer arka plan pixmap yüklüyse ve şablon tipi grid/çizgili ise tekrar çizme
    if (
        canvas._background_pixmap is not None and not canvas._background_pixmap.isNull() and
        canvas.current_template in [TemplateType.GRID, TemplateType.LINES_AND_GRID, TemplateType.LINED, TemplateType.DOT_GRID]
    ):
        return

    painter.save()
    # Gerekirse dünya koordinatlarına geçiş (eğer grid dünya birimleriyle tanımlanıyorsa)
    # Ama grid genellikle ekran bazlı çizilir.
    # painter.setTransform(canvas.get_world_transform()) 

    # Grid görünürlük koşulları
    should_draw_grid = False
    if canvas.snap_lines_to_grid and canvas.grid_visible_on_snap:
        if canvas.grid_show_for_line_tool_only:
            if canvas.current_tool == ToolType.LINE or \
               canvas.current_tool == ToolType.RECTANGLE or \
               canvas.current_tool == ToolType.CIRCLE or \
               canvas.current_tool == ToolType.EDITABLE_LINE: # Düzenlenebilir çizgi de eklenebilir
                should_draw_grid = True
        else:
            should_draw_grid = True
    
    # Ayrıca, şablon tipi GRID ise her zaman çiz (snap_lines_to_grid kapalı olsa bile)
    if canvas.current_template == TemplateType.GRID or \
       canvas.current_template == TemplateType.LINES_AND_GRID or \
       canvas.current_template == TemplateType.DOT_GRID:
        should_draw_grid = True

    if not should_draw_grid:
        painter.restore()
        return

    # Grid ayarlarını al
    spacing_pt = canvas.grid_spacing_pt
    # PT_TO_PX dönüşümü canvas'ta veya burada yapılmalı. Canvas'ta böyle bir dönüşüm olmadığını varsayarak, burada bir sabit kullanalım.
    # TODO: Bu PT_TO_PX değeri DrawingCanvas'tan veya bir config'den gelmeli.
    PT_TO_PX = 96.0 / 72.0 
    spacing_px = spacing_pt * PT_TO_PX * canvas.current_zoom_level # Zoom'u da hesaba kat

    if spacing_px < 3: # Çok küçükse çizme
        painter.restore()
        return

    thin_color_rgba = getattr(canvas, 'grid_thin_color', (0.85, 0.85, 0.85, 0.7))
    thick_color_rgba = getattr(canvas, 'grid_thick_color', (0.75, 0.75, 0.75, 0.8))
    thin_width = getattr(canvas, 'grid_thin_width', 1.0) * canvas.current_zoom_level
    thick_width = getattr(canvas, 'grid_thick_width', 1.5) * canvas.current_zoom_level
    thick_line_interval = getattr(canvas, 'grid_thick_line_interval', 4)

    thin_pen = QPen(rgba_to_qcolor_local(thin_color_rgba), thin_width)
    thin_pen.setCosmetic(True)
    thick_pen = QPen(rgba_to_qcolor_local(thick_color_rgba), thick_width)
    thick_pen.setCosmetic(True)

    width = canvas.width()
    height = canvas.height()

    # Pan ofsetini dikkate alarak başlangıç noktalarını ayarla
    # Grid, ekranın sol üstünden başlamalı, pan ne olursa olsun.
    # Bu yüzden pan_offset'i grid koordinatlarını hesaplarken kullanacağız.
    pan_offset_x = canvas.pan_offset_x * canvas.current_zoom_level
    pan_offset_y = canvas.pan_offset_y * canvas.current_zoom_level
    
    # Yatay çizgiler
    start_y = -pan_offset_y % spacing_px # Pan ofsetine göre ilk çizginin y'si
    line_count = 0
    current_y = start_y
    while current_y < height:
        is_thick_line = (line_count % thick_line_interval == 0)
        painter.setPen(thick_pen if is_thick_line else thin_pen)
        painter.drawLine(QPointF(0, current_y), QPointF(width, current_y))
        current_y += spacing_px
        line_count += 1

    # Dikey çizgiler
    start_x = -pan_offset_x % spacing_px # Pan ofsetine göre ilk çizginin x'i
    line_count = 0
    current_x = start_x
    while current_x < width:
        is_thick_line = (line_count % thick_line_interval == 0)
        painter.setPen(thick_pen if is_thick_line else thin_pen)
        painter.drawLine(QPointF(current_x, 0), QPointF(current_x, height))
        current_x += spacing_px
        line_count += 1
        
    painter.restore() 
"""
DrawingCanvas için temel çizim yardımcı fonksiyonları.
Bu fonksiyonlar genellikle DrawingCanvas.paintEvent() içinden çağrılır.
"""
import logging
from typing import TYPE_CHECKING

from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QCursor, QPainterPath
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsPixmapItem

from utils import selection_helpers # selection_helpers ve geometry_helpers gerekebilir
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
    """Tüm kalıcı öğeleri (çizgiler, şekiller, resimler) çizer."""
    # --- YENİ: Painter durumunu sıfırlama denemesi ---
    painter.resetTransform()  # Tüm transformasyonları sıfırla
    painter.setClipping(False) # Klip bölgesini kaldır
    painter.setOpacity(1.0)    # Opaklığı tam yap
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver) # Varsayılan kompozisyon modu
    # --- --- --- --- --- --- --- --- --- --- --- ---
    from .enums import ToolType # Fonksiyon içinde import
    from utils.drawing_helpers import draw_pen_stroke, draw_shape
    # logging.debug(f"draw_items: shapes id={id(canvas.shapes)}, canvas id={id(canvas)}")
    # --- ÖNCE RESİMLERİ ÇİZ (YENİ: img_data kullanarak) --- #
    if canvas._parent_page and hasattr(canvas._parent_page, 'images') and canvas._parent_page.images:
        for item_index, img_data in enumerate(canvas._parent_page.images):
            current_pixmap = img_data.get('pixmap')
            current_rect = img_data.get('rect')
            current_angle = img_data.get('angle', 0.0)
            uuid = img_data.get('uuid')

            if current_pixmap and not current_pixmap.isNull() and current_rect and current_rect.isValid():
                # logging.debug(f"draw_items: Drawing image index {item_index} (UUID: {uuid}) using img_data - rect: {current_rect}, angle: {current_angle:.1f}, pixmap_size: {current_pixmap.size()}")
                painter.save()
                item_pos = current_rect.topLeft()
                item_size = current_rect.size()
                item_rotation = current_angle

                # Pixmap'i rect boyutuna göre orantılı ölçekle
                scaled_pixmap = current_pixmap.scaled(
                    int(item_size.width()), int(item_size.height()),
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )

                # Ortalamak için offset hesapla
                offset_x = (item_size.width() - scaled_pixmap.width()) / 2
                offset_y = (item_size.height() - scaled_pixmap.height()) / 2

                # Dönüşüm ve çizim
                painter.translate(item_pos.x(), item_pos.y())
                painter.translate(item_size.width() / 2, item_size.height() / 2)
                painter.rotate(item_rotation)
                painter.translate(-item_size.width() / 2, -item_size.height() / 2)
                painter.drawPixmap(QPointF(offset_x, offset_y), scaled_pixmap)
                painter.restore()
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
        # logging.debug(f"draw_items: Shapes listesi dolu, {len(canvas.shapes)} adet şekil var. İçerik: {canvas.shapes}")
        for i, shape_data in enumerate(canvas.shapes):
            if not shape_data or len(shape_data) < 5:
                logging.warning(f"draw_items: Geçersiz shape_data atlanıyor: index={i}, data={shape_data}")
                continue
            # line_style ve fill_rgba shape_data'da varsa draw_shape'a aktar
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
    # logging.debug(f"[canvas_drawing_helpers] draw_selection_overlay: selected_item_indices={canvas.selected_item_indices}, current_handles={canvas.current_handles}")
    from gui.enums import ToolType
    canvas.current_handles.clear()
    if not canvas.selected_item_indices or not canvas._parent_page:
        return

    is_image_selection = False
    is_mixed_selection = False
    first_item_type = canvas.selected_item_indices[0][0]

    if first_item_type == 'images':
        is_image_selection = all(item[0] == 'images' for item in canvas.selected_item_indices)
    else:
        is_image_selection = False
        is_mixed_selection = any(item[0] == 'images' for item in canvas.selected_item_indices)

    if is_mixed_selection or (is_image_selection and len(canvas.selected_item_indices) > 1):
        return

    if is_image_selection and len(canvas.selected_item_indices) == 1:
        img_index = canvas.selected_item_indices[0][1]
        if 0 <= img_index < len(canvas._parent_page.images):
            img_data = canvas._parent_page.images[img_index]
            current_rect = img_data.get('rect', QRectF())
            current_angle = img_data.get('angle', 0.0)
            zoom = canvas._parent_page.zoom_level
            if not current_rect.isNull():
                selection_helpers.draw_rotated_selection_frame(painter, current_rect, current_angle, zoom)
                rotated_corners = selection_helpers.get_rotated_corners(current_rect, current_angle)
                handle_positions_world = {
                    'top-left': rotated_corners[0], 'top-right': rotated_corners[1],
                    'bottom-right': rotated_corners[2], 'bottom-left': rotated_corners[3],
                    'middle-top': (rotated_corners[0] + rotated_corners[1]) / 2.0,
                    'middle-right': (rotated_corners[1] + rotated_corners[2]) / 2.0,
                    'middle-bottom': (rotated_corners[2] + rotated_corners[3]) / 2.0,
                    'middle-left': (rotated_corners[3] + rotated_corners[0]) / 2.0,
                }
                bottom_mid_point_world = handle_positions_world['middle-bottom']
                center_world = current_rect.center()
                rotation_handle_offset_world = selection_helpers.ROTATION_HANDLE_OFFSET / zoom if zoom > 0 else selection_helpers.ROTATION_HANDLE_OFFSET
                vec_center_to_bottom = bottom_mid_point_world - center_world
                if vec_center_to_bottom.manhattanLength() > 1e-6:
                    vec_center_to_bottom = vec_center_to_bottom * (1 + rotation_handle_offset_world / vec_center_to_bottom.manhattanLength())
                rotation_handle_center_world = center_world + vec_center_to_bottom
                handle_positions_world['rotate'] = rotation_handle_center_world
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                for handle_type, center_w in handle_positions_world.items(): # center_world -> center_w
                    center_screen = canvas.world_to_screen(center_w)
                    current_handle_size_screen = handle_size_screen
                    if handle_type == 'rotate':
                        current_handle_size_screen *= selection_helpers.ROTATION_HANDLE_SIZE_FACTOR
                    current_half_handle_screen = current_handle_size_screen / 2.0
                    handle_rect_screen = QRectF(
                        center_screen.x() - current_half_handle_screen, 
                        center_screen.y() - current_half_handle_screen,
                        current_handle_size_screen, 
                        current_handle_size_screen
                    )
                    canvas.current_handles[handle_type] = handle_rect_screen
        else:
            logging.warning(f"_draw_selection_overlay: Geçersiz resim indeksi: {img_index}")
    elif not is_image_selection:
        # --- DÜZ ÇİZGİ (LINE) için özel tutamaç --- #
        if len(canvas.selected_item_indices) == 1 and canvas.selected_item_indices[0][0] == 'shapes':
            shape_index = canvas.selected_item_indices[0][1]
            if 0 <= shape_index < len(canvas.shapes):
                shape_data = canvas.shapes[shape_index]
                tool_type = shape_data[0]
                if tool_type == ToolType.LINE:
                    p1, p2 = shape_data[3], shape_data[4]
                    handle_size_screen =  selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    # Baş ve son noktaları ekran koordinatına çevir
                    start_screen = canvas.world_to_screen(p1)
                    end_screen = canvas.world_to_screen(p2)
                    # Tutamaçları çiz
                    painter.save()
                    handle_pen = QPen(Qt.GlobalColor.black)
                    handle_pen.setCosmetic(True)
                    handle_brush = QBrush(QColor(0, 100, 255, 128))
                    painter.setPen(handle_pen)
                    painter.setBrush(handle_brush)
                    for key, center in [('start', start_screen), ('end', end_screen)]:
                        handle_rect = QRectF(center.x() - half_handle_screen, center.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                        painter.drawRect(handle_rect)
                        canvas.current_handles[key] = handle_rect
                    painter.restore()
                    return # Diğer seçim kutusu ve tutamaçlar çizilmesin
                
                # --- YENİ: Düzenlenebilir Çizgi (EDITABLE_LINE) için özel tutamaç --- #
                elif tool_type == ToolType.EDITABLE_LINE:
                    control_points = shape_data[3]  # Bezier kontrol noktaları
                    if not control_points or len(control_points) < 4:
                        return
                    
                    handle_size_screen = selection_helpers.HANDLE_SIZE
                    half_handle_screen = handle_size_screen / 2.0
                    bezier_handle_size_screen = handle_size_screen * 0.8
                    half_bezier_handle_screen = bezier_handle_size_screen / 2.0
                    
                    # Önce, çizginin kendisini çizelim (seçili olduğunu belirtmek için)
                    painter.save()
                    selection_pen = QPen(QColor(0, 100, 255, 150), 1, Qt.PenStyle.DashLine)
                    selection_pen.setCosmetic(True)
                    painter.setPen(selection_pen)
                    
                    # Bezier çizgilerini çizmek için QPainterPath kullan
                    path = QPainterPath()
                    path.moveTo(canvas.world_to_screen(control_points[0]))
                    
                    # Cubic Bezier eğrilerini çiz
                    for i in range(0, len(control_points) - 3, 3):
                        p0_screen = canvas.world_to_screen(control_points[i])
                        p1_screen = canvas.world_to_screen(control_points[i + 1])
                        p2_screen = canvas.world_to_screen(control_points[i + 2])
                        p3_screen = canvas.world_to_screen(control_points[i + 3])
                        
                        path.cubicTo(p1_screen, p2_screen, p3_screen)
                    
                    painter.drawPath(path)
                    
                    # Şimdi kontrol noktalarını çizelim
                    handle_pen = QPen(Qt.GlobalColor.black)
                    handle_pen.setCosmetic(True)
                    
                    for i in range(0, len(control_points), 3):
                        # Ana noktalar (kubik bezier eğrilerinin uç noktaları)
                        if i < len(control_points):
                            p_screen = canvas.world_to_screen(control_points[i])
                            
                            # Ana nokta tutamaçlarını çiz (mavi)
                            painter.setPen(handle_pen)
                            painter.setBrush(QBrush(QColor(0, 100, 255, 128)))  # Mavi
                            
                            handle_rect = QRectF(
                                p_screen.x() - half_handle_screen,
                                p_screen.y() - half_handle_screen,
                                handle_size_screen,
                                handle_size_screen
                            )
                            painter.drawRect(handle_rect)
                            
                            # Tutamaç bilgisini canvas'a kaydet
                            handle_key = f"main_{i}"
                            canvas.current_handles[handle_key] = handle_rect
                        
                        # Bezier kontrol noktaları (ara noktalar)
                        # İlk kontrol noktası (C1)
                        if i + 1 < len(control_points):
                            # Kontrol çizgisini çiz
                            if i < len(control_points):
                                p0_screen = canvas.world_to_screen(control_points[i])
                                c1_screen = canvas.world_to_screen(control_points[i + 1])
                                painter.setPen(QPen(QColor(0, 200, 0, 100), 1, Qt.PenStyle.DashLine))
                                painter.drawLine(p0_screen, c1_screen)
                            
                            # Kontrol noktası tutamacını çiz (yeşil)
                            c1_screen = canvas.world_to_screen(control_points[i + 1])
                            painter.setPen(handle_pen)
                            painter.setBrush(QBrush(QColor(0, 200, 0, 128)))  # Yeşil
                            
                            handle_rect = QRectF(
                                c1_screen.x() - half_bezier_handle_screen,
                                c1_screen.y() - half_bezier_handle_screen,
                                bezier_handle_size_screen,
                                bezier_handle_size_screen
                            )
                            painter.drawEllipse(handle_rect)
                            
                            # Tutamaç bilgisini canvas'a kaydet
                            handle_key = f"control1_{i+1}"
                            canvas.current_handles[handle_key] = handle_rect
                        
                        # İkinci kontrol noktası (C2)
                        if i + 2 < len(control_points):
                            # Kontrol çizgisini çiz
                            if i + 3 < len(control_points):
                                p3_screen = canvas.world_to_screen(control_points[i + 3])
                                c2_screen = canvas.world_to_screen(control_points[i + 2])
                                painter.setPen(QPen(QColor(200, 0, 0, 100), 1, Qt.PenStyle.DashLine))
                                painter.drawLine(p3_screen, c2_screen)
                            
                            # Kontrol noktası tutamacını çiz (kırmızı)
                            c2_screen = canvas.world_to_screen(control_points[i + 2])
                            painter.setPen(handle_pen)
                            painter.setBrush(QBrush(QColor(200, 0, 0, 128)))  # Kırmızı
                            
                            handle_rect = QRectF(
                                c2_screen.x() - half_bezier_handle_screen,
                                c2_screen.y() - half_bezier_handle_screen,
                                bezier_handle_size_screen,
                                bezier_handle_size_screen
                            )
                            painter.drawEllipse(handle_rect)
                            
                            # Tutamaç bilgisini canvas'a kaydet
                            handle_key = f"control2_{i+2}"
                            canvas.current_handles[handle_key] = handle_rect
                    
                    painter.restore()
                    return  # Diğer seçim kutuları ve tutamaçlar çizilmesin
        # --- Diğer şekiller için klasik seçim kutusu ve tutamaçlar --- #
        combined_bbox_world = canvas._get_combined_bbox([])
        if not combined_bbox_world.isNull():
            zoom = canvas._parent_page.zoom_level
            selection_helpers.draw_standard_selection_frame(painter, combined_bbox_world, zoom)
            handle_positions_world = {
                'top-left': combined_bbox_world.topLeft(), 'top-right': combined_bbox_world.topRight(),
                'bottom-left': combined_bbox_world.bottomLeft(), 'bottom-right': combined_bbox_world.bottomRight(),
                'middle-left': QPointF(combined_bbox_world.left(), combined_bbox_world.center().y()),
                'middle-right': QPointF(combined_bbox_world.right(), combined_bbox_world.center().y()),
                'middle-top': QPointF(combined_bbox_world.center().x(), combined_bbox_world.top()),
                'middle-bottom': QPointF(combined_bbox_world.center().x(), combined_bbox_world.bottom())
            }
            handle_size_screen = selection_helpers.HANDLE_SIZE
            half_handle_screen = handle_size_screen / 2.0
            for handle_type, center_w in handle_positions_world.items():
                center_screen = canvas.world_to_screen(center_w)
                handle_rect_screen = QRectF(
                    center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen,
                    handle_size_screen, handle_size_screen
                )
                canvas.current_handles[handle_type] = handle_rect_screen

def draw_selection_rectangle(canvas: 'DrawingCanvas', painter: QPainter):
    logging.debug(f"[canvas_drawing_helpers] draw_selection_rectangle: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
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
    logging.debug(f"[canvas_drawing_helpers] draw_eraser_preview: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
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
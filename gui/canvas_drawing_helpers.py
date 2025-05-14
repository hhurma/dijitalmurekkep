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
    
    # Seçili öğe yoksa hemen çık
    if not canvas.selected_item_indices:
        canvas.current_handles.clear()
        return
        
    painter.save()
    # İmleç koordinat hesaplamada kullanılabilecek ekran dönüşüm metodları
    is_image_selection = False
    
    # İlk önce görüntüleri kontrol et (daha basit durum)
    if canvas.selected_item_indices[0][0] == 'images' and canvas._parent_page:
        index = canvas.selected_item_indices[0][1]
        if 0 <= index < len(canvas._parent_page.images):
            is_image_selection = True
            img_data = canvas._parent_page.images[index]
            rect = img_data.get('rect')
            angle = img_data.get('angle', 0.0)
            if rect and isinstance(rect, QRectF):
                # Gelen görüntü için kutu çizme
                # Kutuyu çevreleyen bir dikdörtgen çiz
                transformed_rect_poly = selection_helpers.get_rotated_rect_polygon(rect, angle)
                screen_poly = QPolygonF([canvas.world_to_screen(p) for p in transformed_rect_poly])
                painter.setPen(QPen(QColor(0, 0, 255, 200), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolygon(screen_poly)
                
                # Tutamaçları çiz, birden fazla görüntü seçiliyse, kenar tutamaçlarını atla
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                
                if len(canvas.selected_item_indices) == 1:
                    # Yeniden boyutlandırma için - 8 tutamaç
                    handle_positions_world = selection_helpers.calculate_handle_positions_for_rotated_rect(rect, angle)
                    
                    handle_pen = QPen(Qt.GlobalColor.black)
                    handle_pen.setWidth(2)
                    handle_pen.setCosmetic(True)
                    
                    painter.setPen(handle_pen)
                    painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                    
                    for handle_type, center_world in handle_positions_world.items():
                        center_screen = canvas.world_to_screen(center_world)
                        handle_rect = QRectF(center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                        painter.drawRect(handle_rect)
                        canvas.current_handles[handle_type] = handle_rect
                
                # Döndürme tutamacı ekle (merkez üstünde, kenarlardan uzakta)
                if len(canvas.selected_item_indices) == 1:
                    top_center_world = QPointF(rect.center().x(), rect.top() - rect.height() * 0.2)
                    if angle != 0:
                        # Açıyı radyana çevir
                        angle_rad = math.radians(angle)
                        # Merkezi al
                        rect_center = rect.center()
                        # Rotasyon matrisi uygula
                        dx = top_center_world.x() - rect_center.x()
                        dy = top_center_world.y() - rect_center.y()
                        rotated_x = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
                        rotated_y = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
                        # Döndürülmüş noktayı hesapla
                        top_center_world = QPointF(rect_center.x() + rotated_x, rect_center.y() + rotated_y)
                    
                    top_center_screen = canvas.world_to_screen(top_center_world)
                    center_screen = canvas.world_to_screen(rect.center())
                    
                    # Merkez ile döndürme tutamacı arasına çizgi çiz
                    painter.setPen(QPen(QColor(0, 0, 0, 150), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(center_screen, top_center_screen)
                    
                    # Döndürme tutamacını çiz
                    handle_pen.setColor(QColor(0, 0, 0, 150))
                    painter.setPen(handle_pen)
                    handle_brush = QBrush(QColor(255, 100, 100, 150))
                    painter.setBrush(handle_brush)
                    
                    rotation_handle_rect = QRectF(top_center_screen.x() - half_handle_screen, top_center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                    painter.drawEllipse(rotation_handle_rect)
                    canvas.current_handles['rotation'] = rotation_handle_rect
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
                    # Düzenlenebilir çizgi tutamaçlarını sadece EDITABLE_LINE_NODE_SELECTOR aracı seçiliyse göster,
                    # aksi takdirde sadece normal seçim çerçevesini göster
                    if canvas.current_tool != ToolType.EDITABLE_LINE_NODE_SELECTOR:
                        # Sadece etrafında bir çerçeve göster
                        control_points = shape_data[3]
                        if not control_points or len(control_points) < 1:
                            return
                        
                        # Çizginin sınırlayıcı kutusunu hesapla ve çiz
                        bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                        if not bbox.isNull():
                            painter.setPen(QPen(QColor(0, 0, 255, 150), 1, Qt.PenStyle.DashLine))
                            painter.setBrush(Qt.BrushStyle.NoBrush)
                            bbox_rect_screen = QRectF(
                                canvas.world_to_screen(bbox.topLeft()),
                                canvas.world_to_screen(bbox.bottomRight())
                            )
                            painter.drawRect(bbox_rect_screen)
                            
                            # Boyutlandırma için standart tutamaçları göster
                            handle_size_screen = selection_helpers.HANDLE_SIZE
                            half_handle_screen = handle_size_screen / 2.0
                            
                            # Dünya koordinatlarındaki 8 tutamaç pozisyonu
                            handle_positions_world = {
                                'top-left': bbox.topLeft(),
                                'top-right': bbox.topRight(),
                                'bottom-left': bbox.bottomLeft(),
                                'bottom-right': bbox.bottomRight(),
                                'middle-top': QPointF(bbox.center().x(), bbox.top()),
                                'middle-bottom': QPointF(bbox.center().x(), bbox.bottom()),
                                'middle-left': QPointF(bbox.left(), bbox.center().y()),
                                'middle-right': QPointF(bbox.right(), bbox.center().y())
                            }
                            
                            # Tutamaçları çiz
                            handle_pen = QPen(Qt.GlobalColor.black)
                            handle_pen.setWidth(2)
                            handle_pen.setCosmetic(True)
                            painter.setPen(handle_pen)
                            painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                            
                            for handle_type, center_world in handle_positions_world.items():
                                center_screen = canvas.world_to_screen(center_world)
                                handle_rect = QRectF(center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                                painter.drawRect(handle_rect)
                                canvas.current_handles[handle_type] = handle_rect
                        return
                    
                    # EDITABLE_LINE_NODE_SELECTOR aracı seçiliyse kontrol noktalarını göster
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
                    handle_pen.setWidth(1)
                    handle_pen.setCosmetic(True)
                    
                    # Ana noktaları çiz (P0, P3, P6, ...)
                    for i in range(0, len(control_points), 3):
                        if i < len(control_points):
                            p_screen = canvas.world_to_screen(control_points[i])
                            
                            # Ana nokta
                            painter.setPen(handle_pen)
                            painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                            
                            handle_rect = QRectF(
                                p_screen.x() - half_handle_screen, 
                                p_screen.y() - half_handle_screen, 
                                handle_size_screen, 
                                handle_size_screen
                            )
                            
                            # Ana nokta kare şeklinde
                            painter.drawRect(handle_rect)
                            
                            # Handle'ı kaydet
                            handle_name = f"main_{i}"
                            canvas.current_handles[handle_name] = handle_rect
                    
                    # Kontrol noktalarına çizgiler ve kontrol noktaları
                    handle_pen.setColor(QColor(120, 120, 120, 150))
                    handle_pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(handle_pen)
                    
                    # Kontrol noktalarını çiz ve kontrol çizgilerini çiz
                    for i in range(0, len(control_points) - 3, 3):
                        # P0 -> C1 (kontrol noktası 1)
                        p0 = canvas.world_to_screen(control_points[i])
                        c1 = canvas.world_to_screen(control_points[i + 1])
                        painter.drawLine(p0, c1)
                        
                        # C2 -> P3 (kontrol noktası 2 -> sonraki ana nokta)
                        c2 = canvas.world_to_screen(control_points[i + 2])
                        p3 = canvas.world_to_screen(control_points[i + 3])
                        painter.drawLine(c2, p3)
                        
                        # Kontrol noktaları (C1, C2) - farklı şekil veya renkte
                        for j in range(1, 3):
                            ctrl_index = i + j
                            if ctrl_index < len(control_points):
                                ctrl_screen = canvas.world_to_screen(control_points[ctrl_index])
                                
                                # Kontrol noktaları için farklı stil
                                painter.setPen(QPen(Qt.GlobalColor.black, 1))
                                painter.setBrush(QBrush(QColor(200, 200, 200, 150)))
                                
                                handle_rect = QRectF(
                                    ctrl_screen.x() - half_bezier_handle_screen,
                                    ctrl_screen.y() - half_bezier_handle_screen,
                                    bezier_handle_size_screen,
                                    bezier_handle_size_screen
                                )
                                
                                # Kontrol noktaları yuvarlak
                                painter.drawEllipse(handle_rect)
                                
                                # Handle'ı kaydet (j=1 için control1, j=2 için control2)
                                handle_name = f"control{j}_{ctrl_index}"
                                canvas.current_handles[handle_name] = handle_rect
                    
                    painter.restore()
                    return
                
        # --- Standart seçim kutusu ve tutamaçlar --- #
        # Shape'lerin sınırlayıcı kutusunu hesapla
        bbox = QRectF()
        for item_type, index in canvas.selected_item_indices:
            try:
                if item_type == 'lines' and 0 <= index < len(canvas.lines):
                    line_data = canvas.lines[index]
                    item_bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
                elif item_type == 'shapes' and 0 <= index < len(canvas.shapes):
                    shape_data = canvas.shapes[index]
                    item_bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
                elif item_type == 'editable_lines' and 0 <= index < len(canvas.editable_lines):
                    editable_line_data = canvas.editable_lines[index]
                    item_bbox = geometry_helpers.get_item_bounding_box(editable_line_data, 'editable_lines')
                else:
                    continue
                
                if bbox.isNull():
                    bbox = item_bbox
                else:
                    bbox = bbox.united(item_bbox)
            except Exception as e:
                logging.warning(f"Sınırlayıcı kutu hesaplanırken hata: {e}")
                
        if not bbox.isNull():
            # Seçim kutusunu çiz
            bbox_screen = QRectF(canvas.world_to_screen(bbox.topLeft()), 
                                canvas.world_to_screen(bbox.bottomRight()))
            painter.setPen(QPen(QColor(0, 0, 255, 150), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(bbox_screen)
            
            # Tutamaçları hesapla ve çiz
            if len(canvas.selected_item_indices) > 0:
                handle_size_screen = selection_helpers.HANDLE_SIZE
                half_handle_screen = handle_size_screen / 2.0
                
                # Dünya koordinatlarındaki 8 tutamaç pozisyonu
                handle_positions_world = {
                    'top-left': bbox.topLeft(),
                    'top-right': bbox.topRight(),
                    'bottom-left': bbox.bottomLeft(),
                    'bottom-right': bbox.bottomRight(),
                    'middle-top': QPointF(bbox.center().x(), bbox.top()),
                    'middle-bottom': QPointF(bbox.center().x(), bbox.bottom()),
                    'middle-left': QPointF(bbox.left(), bbox.center().y()),
                    'middle-right': QPointF(bbox.right(), bbox.center().y())
                }
                
                # Tutamaçları çiz
                handle_pen = QPen(Qt.GlobalColor.black)
                handle_pen.setWidth(2)
                handle_pen.setCosmetic(True)
                painter.setPen(handle_pen)
                painter.setBrush(QBrush(QColor(0, 120, 255, 180)))
                
                for handle_type, center_world in handle_positions_world.items():
                    center_screen = canvas.world_to_screen(center_world)
                    handle_rect = QRectF(center_screen.x() - half_handle_screen, center_screen.y() - half_handle_screen, handle_size_screen, handle_size_screen)
                    painter.drawRect(handle_rect)
                    canvas.current_handles[handle_type] = handle_rect
    
    painter.restore()

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
"""
Düzenlenebilir Çizgi Kontrol Noktası Seçici aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, List, Tuple, Dict, Optional
import math

from PyQt6.QtCore import QPointF, Qt, QRectF
from PyQt6.QtGui import QTabletEvent, QColor, QPen, QPainter
from PyQt6.QtWidgets import QApplication

from utils.commands import UpdateEditableLineCommand
from utils import geometry_helpers
from ..enums import ToolType

# Sabitler
HANDLE_SIZE = 15  # Tablet kalemi için normal tutucu boyutundan daha büyük
BEZIER_HANDLE_SIZE = 10  # Bezier kontrol noktaları için daha küçük tutucu
SELECTION_HIGHLIGHT_COLOR = QColor(255, 165, 0, 200)  # Turuncu
NODE_COLOR = QColor(0, 120, 255, 180)  # Mavi
BEZIER_HANDLE_COLOR = QColor(120, 120, 120, 180)  # Gri
ACTIVE_NODE_COLOR = QColor(255, 0, 0, 180)  # Kırmızı
HANDLE_CONNECT_COLOR = QColor(120, 120, 120, 150)  # Kontrol noktası bağlantı çizgileri

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas

def handle_node_selector_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi kontrol noktası seçici aracı için basma olayını yönetir."""
    logging.debug(f"Node Selector Press: Checking for selectable nodes at position {pos}")
    
    # Sağ tuş kontrolü
    right_button_pressed = event.button() == Qt.MouseButton.RightButton
    
    # Seçili bir düzenlenebilir çizgi var mı kontrol et
    if not canvas.selected_item_indices:
        logging.debug("Node Selector Press: No selected items, looking for editable line at click point")
        
        # Düzenlenebilir çizgileri manuel olarak kontrol et
        found_editable_line = False
        for i in range(len(canvas.shapes) - 1, -1, -1):  # En üstteki şekilden başla
            shape_data = canvas.shapes[i]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                logging.debug(f"Node Selector Press: Checking editable line at index {i}")
                control_points = shape_data[3]
                line_width = shape_data[2]
                effective_tolerance = HANDLE_SIZE + (line_width / 2.0)  # Genişletilmiş tolerans
                
                # Kontrol noktalarını kontrol et (ana noktalar)
                for j in range(0, len(control_points), 3):
                    if j < len(control_points):
                        point = control_points[j]
                        distance = (pos - point).manhattanLength()
                        if distance <= effective_tolerance:
                            # Ana nokta seçildi - tüm çizgiyi seç
                            canvas.selected_item_indices = [('shapes', i)]
                            logging.debug(f"Node Selector Press: Selected editable line {i} by main point {j}, distance={distance}")
                            found_editable_line = True
                            canvas.update()
                            break
                
                # Eğer ana noktalarda bulamadıysak, segmentleri kontrol et
                if not found_editable_line:
                    for j in range(len(control_points) - 1):
                        p1 = control_points[j]
                        p2 = control_points[j + 1]
                        
                        # Doğrudan segmenti kontrol et
                        if geometry_helpers.is_point_on_line(pos, p1, p2, effective_tolerance):
                            canvas.selected_item_indices = [('shapes', i)]
                            logging.debug(f"Node Selector Press: Selected editable line {i} by segment {j}-{j+1}")
                            found_editable_line = True
                            canvas.update()
                            break
                
                if found_editable_line:
                    break
        
        # Eğer manuel kontrolde bir çizgi bulunamadıysa, _get_item_at ile dene
        if not found_editable_line:
            item_at_click = canvas._get_item_at(pos)
            logging.debug(f"Node Selector Press: Item at click: {item_at_click}")
            
            if item_at_click and item_at_click[0] == 'shapes':
                shape_index = item_at_click[1]
                if 0 <= shape_index < len(canvas.shapes):
                    shape_data = canvas.shapes[shape_index]
                    logging.debug(f"Node Selector Press: Found shape: {shape_data[0]}")
                    
                    if shape_data[0] == ToolType.EDITABLE_LINE:
                        # Düzenlenebilir çizgiyi seç
                        canvas.selected_item_indices = [('shapes', shape_index)]
                        canvas.update()
                        #logging.debug(f"Node Selector Press: Editable line {shape_index} selected")
                    else:
                        #logging.debug(f"Node Selector Press: Shape is not an editable line, type={shape_data[0]}")
                        pass
                else:
                    #logging.debug(f"Node Selector Press: Shape index {shape_index} out of range (shapes count: {len(canvas.shapes)})")
                    pass
            else:
                if item_at_click:
                    #logging.debug(f"Node Selector Press: Item is not a shape, type={item_at_click[0]}")
                    pass
                else:
                    #logging.debug("Node Selector Press: No item found at click position")
                    pass
    else:
        #logging.debug(f"Node Selector Press: Already have selected items: {canvas.selected_item_indices}")
        pass
    
    # Seçili bir şekil varsa, noktalara bakma
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        #logging.debug(f"Node Selector Press: Checking selected item: {item_type}, index={index}")
        pass
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                #logging.debug(f"Node Selector Press: Found editable line with {len(shape_data[3])} control points")
                pass
                # Bezier kontrol noktaları
                control_points = shape_data[3]
                
                # 1. Önce ana kontrol noktalarını kontrol et (p0, p1, p2, ...)
                for i in range(0, len(control_points), 3):
                    if i < len(control_points):
                        point = control_points[i]
                        distance = (pos - point).manhattanLength()
                        if distance <= HANDLE_SIZE:
                            # Ana nokta seçildi
                            canvas.active_handle_index = i
                            canvas.active_bezier_handle_index = -1
                            canvas.is_dragging_bezier_handle = False
                            canvas.drawing = True
                            
                            # Orijinal durumu kaydet (geri alma için)
                            canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
                            
                            logging.debug(f"Node Selector Press: Main point {i} selected, distance={distance}")
                            canvas.update()
                            return
                
                # 2. Bezier kontrol noktalarını kontrol et (tüm c1, c2'ler)
                for i in range(len(control_points)):
                    if i % 3 != 0:  # Ana noktalar değil, sadece kontrol noktaları (c1, c2)
                        point = control_points[i]
                        distance = (pos - point).manhattanLength()
                        if distance <= BEZIER_HANDLE_SIZE:
                            # Bezier kontrol noktası seçildi
                            canvas.active_bezier_handle_index = i
                            canvas.active_handle_index = -1
                            canvas.is_dragging_bezier_handle = True
                            canvas.drawing = True
                            
                            # Orijinal durumu kaydet
                            canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
                            
                            logging.debug(f"Node Selector Press: Bezier control point {i} selected, distance={distance}")
                            canvas.update()
                            return
                
                logging.debug(f"Node Selector Press: No control point found near click position")
                
                # Hiçbir nokta seçilmediyse ve sağ tuşa basıldıysa, bağlam menüsü göster veya işlemi iptal et
                if right_button_pressed:
                    # İptal işlemi veya bağlam menüsü gösterme
                    canvas.active_handle_index = -1
                    canvas.active_bezier_handle_index = -1
                    canvas.is_dragging_bezier_handle = False
                    canvas.drawing = False
                    canvas.update()
                    logging.debug("Node Selector Press: Right button click, canceling operation")
                    return
            else:
                logging.debug(f"Node Selector Press: Selected shape is not an editable line, type={shape_data[0]}")
        else:
            logging.debug(f"Node Selector Press: Selected item is not a valid shape")
    
    # Hiçbir şey seçilmediyse veya işlenmediyse, mevcut durumu temizle
    canvas.active_handle_index = -1
    canvas.active_bezier_handle_index = -1
    canvas.is_dragging_bezier_handle = False
    canvas.drawing = False
    canvas.update()
    logging.debug("Node Selector Press: No action performed, cleared state")

def handle_node_selector_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi kontrol noktası seçici aracı için hareket olayını yönetir."""
    if not canvas.drawing:
        # Fareyi hareket ettirirken üzerine gelinen noktalara vurgu yapılabilir
        highlight_node_on_hover(canvas, pos)
        return
    
    # Seçili bir çizgi var mı kontrol et
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                control_points = shape_data[3]
                
                if canvas.is_dragging_bezier_handle and canvas.active_bezier_handle_index != -1:
                    # Bezier kontrol noktasını taşı
                    if 0 <= canvas.active_bezier_handle_index < len(control_points):
                        # Önceki pozisyonu hatırla
                        old_position = control_points[canvas.active_bezier_handle_index]
                        
                        # Yeni pozisyonu ayarla
                        control_points[canvas.active_bezier_handle_index] = pos
                        
                        # Ana noktanın karşı tarafındaki kontrol noktasını da güncelle (simetrik hareket için)
                        # Bu simetrik güncellemeyi isteğe bağlı yapabiliriz (belki Shift tuşu basılıyken)
                        shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                        if shift_pressed:
                            update_opposite_control_point(canvas, control_points, pos)
                        
                        logging.debug(f"Node Selector Move: Bezier kontrol noktası {canvas.active_bezier_handle_index} taşındı")
                        canvas.update()
                
                elif canvas.active_handle_index != -1:
                    # Ana noktayı taşı
                    if 0 <= canvas.active_handle_index < len(control_points):
                        node_index = canvas.active_handle_index
                        
                        # Önceki pozisyonu hatırla
                        old_position = control_points[node_index]
                        
                        # Yeni pozisyonu ayarla
                        control_points[node_index] = pos
                        
                        # Ana noktaya bağlı kontrol noktalarını da taşı (相対的なposition)
                        move_related_control_points(canvas, control_points, node_index, old_position, pos)
                        
                        logging.debug(f"Node Selector Move: Ana nokta {node_index} taşındı")
                        canvas.update()

def highlight_node_on_hover(canvas: 'DrawingCanvas', pos: QPointF):
    """Fare kontrol noktasının üzerine geldiğinde o noktayı vurgula."""
    # Seçili bir şekil varsa
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                control_points = shape_data[3]
                
                # Önceki vurguları temizle
                canvas.hovered_node_index = -1
                canvas.hovered_bezier_handle_index = -1
                
                # 1. Ana kontrol noktalarını kontrol et
                for i in range(0, len(control_points), 3):
                    if i < len(control_points):
                        point = control_points[i]
                        distance = (pos - point).manhattanLength()
                        if distance <= HANDLE_SIZE:
                            canvas.hovered_node_index = i
                            canvas.update()
                            # İmleç değiştir
                            QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
                            return
                
                # 2. Bezier kontrol noktalarını kontrol et
                for i in range(len(control_points)):
                    if i % 3 != 0:  # Sadece kontrol noktalarına bak
                        point = control_points[i]
                        distance = (pos - point).manhattanLength()
                        if distance <= BEZIER_HANDLE_SIZE:
                            canvas.hovered_bezier_handle_index = i
                            canvas.update()
                            # İmleç değiştir
                            QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
                            return
                
                # Hiçbir şey bulunamadıysa imleci normal haline getir
                QApplication.restoreOverrideCursor()

def update_opposite_control_point(canvas: 'DrawingCanvas', control_points: List[QPointF], new_pos: QPointF):
    """Bir bezier kontrol noktası taşındığında, karşısındaki kontrol noktasını da simetrik olarak günceller."""
    active_idx = canvas.active_bezier_handle_index
    if active_idx == -1 or active_idx % 3 == 0:  # Ana nokta veya geçersiz indeks
        return
    
    # Active kontrolün hangi ana noktaya bağlı olduğunu bul
    if active_idx % 3 == 1:  # c1 tipi kontrol noktası
        anchor_node_idx = active_idx - 1
    else:  # c2 tipi kontrol noktası
        anchor_node_idx = active_idx + 1
    
    # Ana nokta geçerli mi?
    if anchor_node_idx < 0 or anchor_node_idx >= len(control_points):
        return
    
    anchor_point = control_points[anchor_node_idx]
    
    # Aynı ana noktaya bağlı diğer kontrol noktasını bul
    opposite_idx = -1
    if active_idx % 3 == 1:  # Aktif c1 ise, c2'yi bul
        opposite_idx = anchor_node_idx - 1
    else:  # Aktif c2 ise, c1'i bul
        opposite_idx = anchor_node_idx + 1
    
    if opposite_idx < 0 or opposite_idx >= len(control_points) or opposite_idx % 3 == 0:
        return  # Geçersiz karşı nokta
    
    # Yeni pozisyona göre simetrik konum hesapla
    # Ana noktadan aktif kontrele olan vektörü al, ters çevir, ve karşı kontrele uygula
    vec_to_active = new_pos - anchor_point
    opposite_pos = anchor_point - vec_to_active  # Simetri için vektörü ters çevir
    
    # Karşı kontrolü güncelle
    control_points[opposite_idx] = opposite_pos

def move_related_control_points(canvas: 'DrawingCanvas', control_points: List[QPointF], 
                               node_index: int, old_position: QPointF, new_position: QPointF):
    """Ana nokta taşındığında, ona bağlı kontrol noktalarını da taşır."""
    if node_index % 3 != 0:  # Sadece ana noktalarda çalış
        return
    
    # Ana noktanın hareketi
    delta = new_position - old_position
    
    # Önce, önceki control point (c2) için kontrol et
    prev_control_idx = node_index - 1
    if prev_control_idx >= 0 and prev_control_idx % 3 == 2:  # Geçerli bir c2 kontrol noktası
        control_points[prev_control_idx] = control_points[prev_control_idx] + delta
    
    # Sonra, sonraki control point (c1) için kontrol et
    next_control_idx = node_index + 1
    if next_control_idx < len(control_points) and next_control_idx % 3 == 1:  # Geçerli bir c1 kontrol noktası
        control_points[next_control_idx] = control_points[next_control_idx] + delta

def handle_node_selector_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi kontrol noktası seçici aracı için bırakma olayını yönetir."""
    if not canvas.drawing:
        return
    
    # Seçili bir çizgi var mı kontrol et
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                # Değişiklikleri kaydet
                original_control_points = []
                if canvas.original_resize_states and canvas.original_resize_states[0]:
                    original_control_points = canvas.original_resize_states[0][3]
                
                current_control_points = shape_data[3]
                
                # Eğer değişiklik varsa, değişimi uygula
                if original_control_points and current_control_points and original_control_points != current_control_points:
                    command = UpdateEditableLineCommand(
                        canvas,
                        index,
                        original_control_points,
                        current_control_points
                    )
                    canvas.undo_manager.execute(command)
                    
                    if canvas._parent_page:
                        canvas._parent_page.mark_as_modified()
                    if hasattr(canvas, 'content_changed'):
                        canvas.content_changed.emit()
                        
                    logging.debug(f"Node Selector Release: Kontrol noktası değişiklikleri kaydedildi.")
    
    # Son yapılan değişikliği tamamla
    canvas.is_dragging_bezier_handle = False
    canvas.active_bezier_handle_index = -1
    canvas.active_handle_index = -1
    canvas.drawing = False
    canvas.original_resize_states = []
    
    # Fare imlecini normal haline getir
    QApplication.restoreOverrideCursor()
    
    canvas.update()

def draw_node_selector_overlay(canvas: 'DrawingCanvas', painter: QPainter):
    """Düzenlenebilir çizgi kontrol noktası seçici aracı için ekstra görsel elemanlar çizer."""
    # Eğer bu araç seçili değilse, çıkış yap
    if canvas.current_tool != ToolType.EDITABLE_LINE_NODE_SELECTOR:
        return
    
    # Seçili bir çizgi var mı kontrol et
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                control_points = shape_data[3]
                
                # Önce gerçek B-spline kontrol noktaları varsa onları göster
                if hasattr(canvas, 'spline_control_points') and canvas.spline_control_points:
                    # İlk olarak B-spline kontrol noktaları arasındaki bağlantıları çiz
                    painter.save()
                    pen = QPen(QColor(180, 80, 80, 150), 1, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    for i in range(len(canvas.spline_control_points)-1):
                        p1 = canvas.spline_control_points[i]
                        p2 = canvas.spline_control_points[i+1]
                        painter.drawLine(p1, p2)
                    
                    # Ardından B-spline kontrol noktalarını çiz (kırmızı)
                    for i, cp in enumerate(canvas.spline_control_points):
                        painter.setBrush(QColor(255, 0, 0, 200))  # Kırmızı
                        painter.setPen(QPen(Qt.GlobalColor.white, 1.0))
                        painter.drawRect(QRectF(cp.x()-4, cp.y()-4, 8, 8))  # Kare şeklinde kontrol noktaları
                    painter.restore()
                
                # Bezier kontrol çizgilerini çiz
                pen = QPen(HANDLE_CONNECT_COLOR, 1, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                
                # Her ana noktayı ve kontrol noktalarını çiz
                for i in range(0, len(control_points), 3):
                    if i < len(control_points):  # Ana nokta
                        main_point = control_points[i]
                        
                        # Kontrol çizgilerini çiz (her ana nokta için 2 kontrol noktası var)
                        if i + 1 < len(control_points):  # c1 için
                            painter.drawLine(main_point, control_points[i + 1])
                        
                        if i - 1 >= 0 and i % 3 == 0:  # c2 için (önceki segmentin)
                            painter.drawLine(main_point, control_points[i - 1])
                
                # Ana noktaları çiz (mavi)
                for i in range(0, len(control_points), 3):
                    if i < len(control_points):
                        point = control_points[i]
                        
                        # Seçili veya vurgulanmış nokta için farklı renk
                        if i == canvas.active_handle_index:
                            painter.setBrush(ACTIVE_NODE_COLOR)
                        elif hasattr(canvas, 'hovered_node_index') and i == canvas.hovered_node_index:
                            painter.setBrush(SELECTION_HIGHLIGHT_COLOR)
                        else:
                            painter.setBrush(NODE_COLOR)  # Normal durum: Mavi
                        
                        painter.setPen(QPen(Qt.GlobalColor.white, 1.5))
                        painter.drawEllipse(point, HANDLE_SIZE/2, HANDLE_SIZE/2)
                
                # Bezier kontrol noktalarını çiz (gri)
                for i in range(len(control_points)):
                    if i % 3 != 0:  # Sadece kontrol noktaları
                        point = control_points[i]
                        
                        # Seçili veya vurgulanmış kontrol noktası için farklı renk (gri yerine kırmızı)
                        if i == canvas.active_bezier_handle_index:
                            painter.setBrush(ACTIVE_NODE_COLOR)  # Kırmızı
                        elif hasattr(canvas, 'hovered_bezier_handle_index') and i == canvas.hovered_bezier_handle_index:
                            painter.setBrush(SELECTION_HIGHLIGHT_COLOR)  # Turuncu
                        else:
                            painter.setBrush(QColor(160, 160, 160, 160))  # Gri
                        
                        painter.setPen(QPen(Qt.GlobalColor.white, 1.0))
                        # Kontrol noktalarını küçük kare şeklinde göster
                        painter.drawRect(QRectF(point.x()-3, point.y()-3, 6, 6)) 
"""
Seçici (Selector) aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, List, Tuple, Any
import copy
import math
import numpy as np

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPolygonF, QTabletEvent
from PyQt6.QtWidgets import QApplication

from utils import geometry_helpers, selection_helpers # selection_helpers da gerekebilir
from utils.commands import MoveItemsCommand, ResizeItemsCommand
from gui.enums import ToolType

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas
    # from ..page import Page # Doğrudan Page kullanılmıyor, canvas._parent_page üzerinden erişiliyor

def handle_selector_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçici aracı için basma olayını yönetir."""
    #logging.debug(f"[selector_tool_handler] handle_selector_press: Tool={canvas.current_tool.name}, WorldPos={pos}")
    screen_pos = event.position() 
    canvas.grabbed_handle_type = None
    # click_tolerance, _get_handle_at içinde ve _get_item_at içinde zaten tanımlı, burada genel bir belirleme yapalım
    
    # Önce tutamaç kontrolü
    canvas.grabbed_handle_type = canvas._get_handle_at(screen_pos, tolerance=canvas.RESIZE_MOVE_THRESHOLD * 2) # Daha büyük tolerans

    if not canvas.grabbed_handle_type:
        #logging.debug("Selector Press: No handle grabbed. Checking for item selection or starting drag.")
        # Eğer zaten seçilmiş öğeler varsa ve tıklama bu seçimin üzerindeyse, taşıma başlat
        if canvas.selected_item_indices and canvas.is_point_on_selection(pos, tolerance=canvas.RESIZE_MOVE_THRESHOLD * 2):
            #logging.debug("Selector Press: Point is on existing selection. Starting move.")
            canvas.moving_selection = True
            canvas.drawing = False
            canvas.resizing_selection = False
            canvas.selecting = False
            canvas.move_start_point = QPointF(pos) 
            # canvas.last_move_pos KULLANIMDAN KALDIRILDI
            canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
            if not canvas.move_original_states and canvas.selected_item_indices:
                #logging.warning("Selector Press (Move): move_original_states boş ama selected_item_indices dolu!")
                pass
            elif len(canvas.move_original_states) != len(canvas.selected_item_indices):
                #logging.warning(f"Selector Press (Move): move_original_states ({len(canvas.move_original_states)}) ve selected_item_indices ({len(canvas.selected_item_indices)}) uzunlukları farklı!")
                pass

            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor) # YENİ İMLEÇ
            canvas.update()
            return # Taşıma başladığı için diğer işlemlere gerek yok
        
        # Seçili öğe yoksa veya tıklama mevcut seçimin üzerinde değilse, yeni bir öğe seçmeyi dene
        # veya çoklu seçim (Ctrl) / tekil seçim yap
        ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        item_at_click = canvas._get_item_at(pos, tolerance=canvas.RESIZE_MOVE_THRESHOLD)
        
        selection_made_now = False
        if item_at_click:
            clicked_item_tuple = item_at_click # (item_type, item_index)
            
            # Seçimin değişip değişmediğini izlemek için mevcut seçimin bir kopyasını alalım
            previous_selection = list(canvas.selected_item_indices)

            if ctrl_pressed:
                if clicked_item_tuple in canvas.selected_item_indices:
                    canvas.selected_item_indices.remove(clicked_item_tuple)
                else:
                    canvas.selected_item_indices.append(clicked_item_tuple)
            else:
                # Eğer tıklanan öğe zaten seçiliyse ve birden fazla öğe seçiliyse, seçimi değiştirme!
                if clicked_item_tuple in canvas.selected_item_indices and len(canvas.selected_item_indices) > 1:
                    # Seçimi koru, sadece taşıma başlat
                    pass
                else:
                    # Diğer durumlarda tekil seçim yap
                    canvas.selected_item_indices = [clicked_item_tuple]

            if previous_selection != canvas.selected_item_indices: # Seçim gerçekten değişti mi?
                selection_made_now = True

        else: # Boş bir alana tıklandı
            if not ctrl_pressed and canvas.selected_item_indices: # Ctrl basılı değilse ve bir şeyler seçiliyse, seçimi temizle
                canvas.selected_item_indices.clear()
                selection_made_now = True
        
        # SEÇİM GÜNCELLENDİKTEN SONRA ORİJİNAL DURUMLARI AYARLA
        if selection_made_now:
            canvas.selection_changed.emit() # Sinyali burada yay
            if canvas.selected_item_indices:
                canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
                if len(canvas.selected_item_indices) == 1:
                    # Tekil seçimse, boyutlandırma için de orijinal durumları ve bbox'u al
                    canvas.original_resize_states = list(canvas.move_original_states) 
                    canvas.resize_original_bbox = canvas._get_combined_bbox([]) 
                else:
                    # Çoklu seçimse, boyutlandırma durumlarını temizle (çoklu boyutlandırma henüz desteklenmiyor olabilir)
                    canvas.original_resize_states.clear()
                    canvas.resize_original_bbox = QRectF()
            else: # Hiçbir şey seçili değilse tüm orijinal durumları temizle
                canvas.move_original_states.clear()
                canvas.original_resize_states.clear()
                canvas.resize_original_bbox = QRectF()

            # Eğer item_at_click varsa ve seçim yapıldıysa (veya mevcut seçim korunduysa) ve ctrl basılı değilse taşıma başlatılabilir.
            # Ancak bu mantık zaten en baştaki "if canvas.selected_item_indices and canvas.is_point_on_selection" içinde ele alınıyor.
            # Burada önemli olan, selection_made_now ise durumların güncellenmesi.

        # Taşıma başlatma (eğer yukarıdaki ilk blokta taşıma başlamadıysa ve şimdi bir öğe seçiliyse)
        # Bu genellikle, boş bir alana tıklayıp sonra bir öğeye tıklayarak YENİ bir seçim yapıldığında ve 
        # bu seçim üzerinde hemen sürükleme başlatıldığında devreye girer.
        if not canvas.moving_selection and not canvas.grabbed_handle_type and item_at_click and item_at_click in canvas.selected_item_indices:
            # Eğer selection_made_now True ise, move_original_states zaten yukarıda ayarlandı.
            # Eğer selection_made_now False ise (yani öğe zaten seçiliydi ve üzerine tıklandı, ve ilk blokta yakalanmadıysa - ki bu zor bir durum),
            # move_original_states'i burada tekrar almak güvenli olabilir.
            if not canvas.move_original_states and canvas.selected_item_indices: # Güvenlik için
                 canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
            # YENİ KONTROL: move_original_states varsa ama selected_item_indices ile uzunluğu eşleşmiyorsa, yeniden al.
            # Bu, çoklu seçim senaryolarında bir tutarsızlık varsa durumu düzeltebilir.
            elif canvas.selected_item_indices and canvas.move_original_states and len(canvas.move_original_states) != len(canvas.selected_item_indices):
                 logging.warning(f"Selector Press (Final Move Check): Mismatch between move_original_states ({len(canvas.move_original_states)}) and selected_item_indices ({len(canvas.selected_item_indices)}). Re-fetching states.")
                 canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
            
            #logging.debug(f"Selector Press: Starting move for newly/re-confirmed selection: {item_at_click}")
            canvas.moving_selection = True
            canvas.drawing = False; canvas.resizing_selection = False; canvas.selecting = False
            canvas.move_start_point = QPointF(pos)
            QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)        # Boş bir alana tıklandıysa ve seçim temizlendiyse veya hiç seçim yoksa dikdörtgenle seçim başlat
        # (Ctrl+Shift durumu hariç)
        if not canvas.grabbed_handle_type and not item_at_click and not canvas.selected_item_indices and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier and ctrl_pressed):
            #logging.debug(f"Selector Press: Selection rectangle started at world_pos: {pos}")
            canvas.shape_start_point = pos # BAŞLANGIÇ NOKTASINI AYARLA            canvas.drawing = True 
            canvas.selecting = True 
            canvas.resizing_selection = False

    else: # Bir tutamaç yakalandı
        if canvas.grabbed_handle_type == 'rotate':
            logging.debug(f"Selector Press: Rotate handle grabbed. Starting rotation.")
            canvas.resizing_selection = True  # Döndürme de teknik olarak resizing kategorisinde
            canvas.drawing = False
            canvas.moving_selection = False
            canvas.selecting = False
            canvas.resize_start_pos = pos 
            
            # Orijinal durumları ve bbox'u al
            canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
            canvas.resize_original_bbox = canvas._get_combined_bbox([]) 
            
            # Store original selection bbox dimensions for consistent selection frame during rotation
            canvas.original_selection_bbox = QRectF(canvas.resize_original_bbox)
            canvas.selection_rotation_angle = 0.0  # Reset rotation angle
            
            QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)
        else:
            logging.debug(f"Selector Press: Handle '{canvas.grabbed_handle_type}' grabbed. Starting resize. Seçili öğe sayısı: {len(canvas.selected_item_indices)}")
            canvas.resizing_selection = True
            canvas.drawing = False
            canvas.moving_selection = False
            canvas.selecting = False
            canvas.resize_start_pos = pos 
            
            # Orijinal durumları ve bbox'u al
            # _get_current_selection_states, canvas.selected_item_indices'i kullanır
            canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
            canvas.resize_original_bbox = canvas._get_combined_bbox([]) 
            
            logging.debug(f"[RESIZE BAŞLANGICI] Tutamaç: {canvas.grabbed_handle_type}, Seçili öğe sayısı: {len(canvas.selected_item_indices)}, original_resize_states: {len(canvas.original_resize_states)}, resize_original_bbox: {canvas.resize_original_bbox}")
            if not canvas.original_resize_states:
                logging.error("Selector Press (Resize): original_resize_states alınamadı veya boş!")
            elif len(canvas.original_resize_states) != len(canvas.selected_item_indices):
                 logging.error(f"Selector Press (Resize): original_resize_states ({len(canvas.original_resize_states)}) ve selected_item_indices ({len(canvas.selected_item_indices)}) uzunlukları farklı!")
            
            logging.debug(f"  Resize Details: Handle={canvas.grabbed_handle_type}, StartWorldPos={pos}, OriginalBBox={canvas.resize_original_bbox}")
            QApplication.setOverrideCursor(geometry_helpers.get_resize_cursor(canvas.grabbed_handle_type))
        
    canvas.update()

def handle_selector_move_selection(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin (çizim/şekil/B-spline) taşınmasını yönetir."""
    # Bu fonksiyon artık doğrudan çağrılmayacak, taşıma mantığı handle_selector_move içinde olacak.
    # Ancak eğer canvas.moving_selection True ise bu mantık çalışmalı.
    # Bu fonksiyonu handle_selector_move içinde bir alt fonksiyon gibi düşünebiliriz.

    if not canvas.moving_selection or canvas.move_start_point.isNull():
        # logging.debug("handle_selector_move_selection: Not in moving_selection mode or move_start_point is null.")
        return

    current_pos_world = pos # Zaten dünya koordinatları
    
    total_dx = current_pos_world.x() - canvas.move_start_point.x()
    total_dy = current_pos_world.y() - canvas.move_start_point.y()
    
    # log_msg = f"Selector Move Selection (via _reposition): WorldPos=({current_pos_world.x():.1f},{current_pos_world.y():.1f}), "
    # log_msg += f"TotalDelta=({total_dx:.1f},{total_dy:.1f}), StartPoint=({canvas.move_start_point.x():.1f},{canvas.move_start_point.y():.1f})"
    # logging.debug(log_msg)
        
    if (abs(total_dx) > 0.01 or abs(total_dy) > 0.01): # Çok küçük hareketleri filtrele
        try:
            # _reposition_selected_items_from_initial, orijinal durumlara göre hareket ettirir
            # ve canvas'taki öğeleri doğrudan günceller.
            canvas._reposition_selected_items_from_initial(total_dx, total_dy)
            # canvas.content_changed.emit() # Emit burada yapılmamalı, komut sonrası.
            # Sayfa durumu (modified) _reposition_selected_items_from_initial içinde ayarlanıyor.
            canvas.update()
        except Exception as e:
            logging.error(f"Taşıma sırasında (_reposition_selected_items_from_initial) hata: {e}", exc_info=True)
    
    # last_move_pos artık kullanılmıyor.

def handle_selector_rect_select_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Dikdörtgen ile seçim yaparkenki hareketi yönetir."""
    canvas.shape_end_point = pos
    canvas.update()

def handle_selector_resize_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    # --- DÖNDÜRME TUTAMAÇ --- #
    if canvas.grabbed_handle_type == 'rotate' and canvas.selected_item_indices:
        from utils import rotation_helpers
        import math
        
        bbox = canvas.resize_original_bbox
        center = bbox.center()
        
        # İlk sürüklemede başlangıç açısını kaydet
        if not hasattr(canvas, 'rotation_start_angle'):
            start_vector = canvas.resize_start_pos - center
            canvas.rotation_start_angle = math.atan2(start_vector.y(), start_vector.x())
            canvas.rotation_start_pos = canvas.resize_start_pos  # Başlangıç pozisyonunu da kaydet
            logging.debug(f"[ROTATION] Döndürme başladı - Merkez: {center}, Başlangıç açısı: {math.degrees(canvas.rotation_start_angle):.1f}°")
          # Mevcut açıyı hesapla (başlangıç pozisyonundan değil mevcut pozisyondan)
        current_vector = pos - center
        angle_now = math.atan2(current_vector.y(), current_vector.x())
        delta_angle = angle_now - canvas.rotation_start_angle
        
        # Seçim çerçevesinin döndürme açısını güncelle (derece cinsinden)
        canvas.selection_rotation_angle = math.degrees(delta_angle)
        
        logging.debug(f"[ROTATION] Pos: {pos}, Mevcut açı: {math.degrees(angle_now):.1f}°, Delta: {math.degrees(delta_angle):.1f}°, Selection angle: {canvas.selection_rotation_angle:.1f}°")
        
        # Tüm seçili öğeleri döndür (orijinal durumlarından)
        for i, (item_type, index) in enumerate(canvas.selected_item_indices):
            if i >= len(canvas.original_resize_states):
                continue
                
            if item_type == 'lines' and index < len(canvas.lines):
                # Pen çizgisi döndürme
                original_points = canvas.original_resize_states[i][2]
                rotated_points = []
                for point in original_points:
                    rotated_point = rotation_helpers.rotate_point(
                        (point.x(), point.y()), 
                        (center.x(), center.y()), 
                        delta_angle
                    )
                    rotated_points.append(QPointF(*rotated_point))
                canvas.lines[index][2] = rotated_points
                logging.debug(f"[ROTATION] Çizgi {index} döndürüldü, {len(rotated_points)} nokta, ilk nokta: {rotated_points[0] if rotated_points else 'YOK'}")
                
            elif item_type == 'shapes' and index < len(canvas.shapes):
                # Şekil döndürme
                shape = canvas.shapes[index]
                if shape[0] == ToolType.LINE:
                    original_shape = canvas.original_resize_states[i]
                    p1_rot = rotation_helpers.rotate_point(
                        (original_shape[3].x(), original_shape[3].y()),
                        (center.x(), center.y()),
                        delta_angle
                    )
                    p2_rot = rotation_helpers.rotate_point(
                        (original_shape[4].x(), original_shape[4].y()),
                        (center.x(), center.y()),
                        delta_angle
                    )
                    canvas.shapes[index][3] = QPointF(*p1_rot)
                    canvas.shapes[index][4] = QPointF(*p2_rot)
                    logging.debug(f"[ROTATION] Şekil {index} döndürüldü, P1: {QPointF(*p1_rot)}, P2: {QPointF(*p2_rot)}")
        
        logging.debug(f"[ROTATION] Canvas güncelleme çağrılıyor...")
        canvas.update()
        return
    """Seçili öğelerin (çizim/şekil) yeniden boyutlandırılmasını yönetir."""
    #logging.debug(f"[handle_selector_resize_move] Çağrıldı. Seçili öğe sayısı: {len(canvas.selected_item_indices)}, Tutamaç: {canvas.grabbed_handle_type}, resizing_selection: {canvas.resizing_selection}")
    #logging.debug(f"[handle_selector_resize_move] original_resize_states: {len(canvas.original_resize_states)}, resize_original_bbox: {canvas.resize_original_bbox}")
    #logging.debug(f"[selector_tool_handler] handle_selector_resize_move: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    
    # --- YENİ: DÜZENLENEBILIR ÇIZGI için özel tutamaç işlemi --- #
    if (
        len(canvas.selected_item_indices) == 1 and
        canvas.selected_item_indices[0][0] == 'shapes' and
        canvas.grabbed_handle_type and
        (canvas.grabbed_handle_type.startswith('main_') or 
         canvas.grabbed_handle_type.startswith('control1_') or 
         canvas.grabbed_handle_type.startswith('control2_')) and
        canvas.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR
    ):
        shape_index = canvas.selected_item_indices[0][1]
        if 0 <= shape_index < len(canvas.shapes):
            shape_data = canvas.shapes[shape_index]
            tool_type = shape_data[0]
            
            if tool_type == ToolType.EDITABLE_LINE:
                # Bezier kontrol noktaları
                control_points = shape_data[3]
                
                # Handle tipi inceleniyor
                if canvas.grabbed_handle_type.startswith('main_'):
                    # Ana kontrol noktası taşınıyor
                    idx = int(canvas.grabbed_handle_type.split('_')[1])
                    if 0 <= idx < len(control_points):
                        # Ana noktayı güncelle
                        control_points[idx] = pos
                        
                        # Komşu kontrol noktalarını da güncelle (eğer varsa)
                        if idx > 0 and idx-1 < len(control_points):  # Önceki kontrol noktası
                            # Önceki kontrol noktasıyla yeni ana nokta arasındaki vektörü koru
                            if idx-2 >= 0:  # Önceki ana nokta
                                prev_main = control_points[idx-3]
                                old_control = control_points[idx-1]
                                # Eski ana noktadan kontrol noktasına vektör
                                old_vector = old_control - prev_main
                                # Bu vektörü yeni konuma uygula
                                control_points[idx-1] = pos - old_vector
                        
                        if idx+1 < len(control_points):  # Sonraki kontrol noktası
                            # Sonraki kontrol noktasıyla yeni ana nokta arasındaki vektörü koru
                            control_points[idx+1] = pos + (control_points[idx+1] - control_points[idx])
                
                elif canvas.grabbed_handle_type.startswith('control1_'):
                    # İlk kontrol noktası taşınıyor (C1)
                    idx = int(canvas.grabbed_handle_type.split('_')[1])
                    if 0 <= idx < len(control_points):
                        # Kontrol noktasını güncelle
                        control_points[idx] = pos
                
                elif canvas.grabbed_handle_type.startswith('control2_'):
                    # İkinci kontrol noktası taşınıyor (C2)
                    idx = int(canvas.grabbed_handle_type.split('_')[1])
                    if 0 <= idx < len(control_points):
                        # Kontrol noktasını güncelle
                        control_points[idx] = pos
                
                # Değişiklikleri canvas'a uygula
                canvas.update()
                return

    # --- DÜZ ÇİZGİ (LINE) için özel uç tutamaç işlemi --- #
    if (
        len(canvas.selected_item_indices) == 1 and
        canvas.selected_item_indices[0][0] == 'shapes' and
        canvas.grabbed_handle_type in ('start', 'end')
    ):
        shape_index = canvas.selected_item_indices[0][1]
        if 0 <= shape_index < len(canvas.shapes):
            shape_data = canvas.shapes[shape_index]
            tool_type = shape_data[0]
            if tool_type == ToolType.LINE:
                tolerance_px = 8
                if canvas.grabbed_handle_type == 'start':
                    new_pos = pos
                    if getattr(canvas, 'snap_lines_to_grid', False):
                        snap_pos = canvas._snap_point_to_grid(new_pos)
                        if (new_pos - snap_pos).manhattanLength() <= tolerance_px:
                            new_pos = snap_pos
                    canvas.shapes[shape_index][3] = new_pos
                elif canvas.grabbed_handle_type == 'end':
                    new_pos = pos
                    if getattr(canvas, 'snap_lines_to_grid', False):
                        snap_pos = canvas._snap_point_to_grid(new_pos)
                        if (new_pos - snap_pos).manhattanLength() <= tolerance_px:
                            new_pos = snap_pos
                    canvas.shapes[shape_index][4] = new_pos
                canvas.update()
                return
                
    # --- KLASİK DAVRANIŞ (diğer şekiller ve klasik tutamaçlar) --- #
    if not canvas.resize_start_pos.isNull() and canvas.grabbed_handle_type and not canvas.resize_original_bbox.isNull():
        new_bbox = geometry_helpers.calculate_new_bbox(canvas.resize_original_bbox, canvas.grabbed_handle_type, pos, canvas.resize_start_pos)
        logging.debug(f"Selector Resize Move: World Pos=({pos.x():.1f},{pos.y():.1f}), Handle='{canvas.grabbed_handle_type}', Original BBox={canvas.resize_original_bbox}, New BBox={new_bbox}")
        if not new_bbox.isNull() and new_bbox.isValid():
            original_center = canvas.resize_original_bbox.center()
            new_center = new_bbox.center()
            translate_delta = new_center - original_center
            original_width = canvas.resize_original_bbox.width()
            original_height = canvas.resize_original_bbox.height()
            new_width = new_bbox.width()
            new_height = new_bbox.height()
            scale_x = new_width / original_width if original_width > 1e-6 else 1.0
            scale_y = new_height / original_height if original_height > 1e-6 else 1.0
            logging.debug(f"  Resize Calc: OrigCenter={original_center}, NewCenter={new_center}, Translate={translate_delta}")
            logging.debug(f"  Resize Calc: ScaleX={scale_x:.4f}, ScaleY={scale_y:.4f}")
            if len(canvas.original_resize_states) != len(canvas.selected_item_indices):
                 logging.error("Resize Move: original_resize_states ve selected_item_indices uzunlukları farklı!")
                 return
            for i, (item_type, index) in enumerate(canvas.selected_item_indices):
                original_item_data = canvas.original_resize_states[i]
                if not original_item_data: continue
                try:
                    if item_type == 'lines':
                        if 0 <= index < len(canvas.lines):
                            original_points = original_item_data[2]
                            transformed_points = []
                            if original_points: logging.debug(f"  Line[{index}] Point 0 (Original): {original_points[0]}")
                            for p_idx, p_val in enumerate(original_points):
                                relative_p = p_val - original_center
                                scaled_p = QPointF(relative_p.x() * scale_x, relative_p.y() * scale_y)
                                transformed_p = scaled_p + original_center + translate_delta
                                transformed_points.append(transformed_p)
                                if p_idx == 0: logging.debug(f"    Point 0 (Transformed): {transformed_p}")
                            canvas.lines[index][2] = transformed_points
                        else: logging.warning(f"Resize Move: Geçersiz lines index {index}")
                    elif item_type == 'shapes':
                        if 0 <= index < len(canvas.shapes):
                            shape_tool_type = canvas.shapes[index][0]
                            # Düzenlenebilir çizgi için özel boyutlandırma
                            if shape_tool_type == ToolType.EDITABLE_LINE:
                                original_points = original_item_data[3]  # Bezier kontrol noktaları
                                transformed_points = []
                                for p_idx, p_val in enumerate(original_points):
                                    relative_p = p_val - original_center
                                    scaled_p = QPointF(relative_p.x() * scale_x, relative_p.y() * scale_y)
                                    transformed_p = scaled_p + original_center + translate_delta
                                    transformed_points.append(transformed_p)
                                canvas.shapes[index][3] = transformed_points
                            else:
                                # Diğer şekiller için standart işlemler
                                original_p1 = original_item_data[3];
                                original_p2 = original_item_data[4];
                                logging.debug(f"  Shape[{index}] P1 (Original): {original_p1}, P2 (Original): {original_p2}");
                                relative_p1 = original_p1 - original_center;
                                scaled_p1 = QPointF(relative_p1.x() * scale_x, relative_p1.y() * scale_y);
                                transformed_p1 = scaled_p1 + original_center + translate_delta;
                                relative_p2 = original_p2 - original_center;
                                scaled_p2 = QPointF(relative_p2.x() * scale_x, relative_p2.y() * scale_y);
                                transformed_p2 = scaled_p2 + original_center + translate_delta;
                                logging.debug(f"    P1 (Transformed): {transformed_p1}, P2 (Transformed): {transformed_p2}");
                                # --- SNAP TO GRID --- #
                                if shape_tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE] and getattr(canvas, 'snap_lines_to_grid', False):
                                    transformed_p1 = canvas._snap_point_to_grid(transformed_p1)
                                    transformed_p2 = canvas._snap_point_to_grid(transformed_p2)
                                canvas.shapes[index][3] = transformed_p1;
                                canvas.shapes[index][4] = transformed_p2;
                        else: logging.warning(f"Resize Move: Geçersiz shapes index {index}")
                    # --- YENİ: B-Spline (düzenlenebilir çizgi) için boyutlandırma --- #
                    elif item_type == 'bspline_strokes':
                        # Bu blokta artık klasik bbox ölçekleme yapılmayacak!
                        continue
                except Exception as e:
                     logging.error(f"Resize Move sırasında öğe ({item_type}[{index}]) güncellenirken hata: {e}", exc_info=True)
            canvas.update()

    # --- B-Spline için özel ölçekleme ---
    # Eğer seçili öğeler arasında bspline_strokes varsa, kontrol noktalarını yeni bbox'a göre ölçekle
    if canvas.resizing_selection and canvas.grabbed_handle_type and not canvas.resize_original_bbox.isNull():
        for i, (item_type, index) in enumerate(canvas.selected_item_indices):
            if item_type == 'bspline_strokes' and i < len(canvas.original_resize_states):
                original_state = canvas.original_resize_states[i]
                if not original_state:
                    continue
                # Orijinal bbox ve yeni bbox'u al
                orig_bbox = canvas.resize_original_bbox
                new_bbox = geometry_helpers.calculate_new_bbox(orig_bbox, canvas.grabbed_handle_type, pos, canvas.resize_start_pos)
                if new_bbox.isNull() or not new_bbox.isValid():
                    continue
                # Orijinal kontrol noktalarını al
                cps = original_state.get('control_points')
                if cps is not None:
                    orig_min = np.array([orig_bbox.left(), orig_bbox.top()])
                    orig_size = np.array([orig_bbox.width(), orig_bbox.height()])
                    new_min = np.array([new_bbox.left(), new_bbox.top()])
                    new_size = np.array([new_bbox.width(), new_bbox.height()])
                    scaled_cps = []
                    for cp in cps:
                        # cp: QPointF, tuple, list veya np.array olabilir
                        if isinstance(cp, QPointF):
                            cp_arr = np.array([cp.x(), cp.y()])
                        elif isinstance(cp, (tuple, list)) and len(cp) == 2:
                            cp_arr = np.array(cp)
                        elif isinstance(cp, np.ndarray) and cp.shape == (2,):
                            cp_arr = cp
                        else:
                            logging.error(f"B-Spline control_points içinde beklenmeyen tip: {type(cp)} - {cp}")
                            continue
                        rel = (cp_arr - orig_min) / orig_size if np.all(orig_size > 0) else np.zeros(2)
                        new_cp_arr = new_min + rel * new_size
                        scaled_cps.append(np.array([float(new_cp_arr[0]), float(new_cp_arr[1])]))
                    # Canvas'taki kontrol noktalarını güncelle (her zaman QPointF listesi!)
                    canvas.b_spline_strokes[index]['control_points'] = scaled_cps
                    if hasattr(canvas, 'b_spline_widget') and canvas.b_spline_widget and index < len(canvas.b_spline_widget.strokes):
                        canvas.b_spline_widget.strokes[index]['control_points'] = scaled_cps

def handle_selector_move_selection_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin taşınmasının bırakılmasını yönetir."""
    #logging.debug(f"[selector_tool_handler] handle_selector_move_selection_release: WorldPos={pos}")

    if not canvas.moving_selection:
        # logging.debug("handle_selector_move_selection_release: Not in moving_selection mode.")
        return

    canvas.moving_selection = False
    QApplication.restoreOverrideCursor()

    if canvas.move_start_point.isNull():
        logging.warning("handle_selector_move_selection_release: move_start_point is Null. Komut oluşturulmayacak.")
        canvas.move_original_states.clear()
        canvas.update()
        return

    current_pos_world = pos
    total_dx = current_pos_world.x() - canvas.move_start_point.x()
    total_dy = current_pos_world.y() - canvas.move_start_point.y()

    # logging.debug(f"  Move Release: total_dx={total_dx:.2f}, total_dy={total_dy:.2f}")

    # Eğer gerçekten bir taşıma yapıldıysa ve orijinal durumlar mevcutsa komut oluştur
    # REVERT_THRESHOLD gibi bir eşik kullanılabilir veya direkt 0.1
    if (abs(total_dx) > 0.1 or abs(total_dy) > 0.1) and canvas.move_original_states:
        #logging.debug(f"  Actual move detected. Creating MoveItemsCommand. Original states count: {len(canvas.move_original_states)}")
        
        initial_states_for_command = canvas.move_original_states 
        # selected_refs, move_original_states alındığı andaki selected_item_indices olmalı.
        # Ancak, _get_current_selection_states, selected_item_indices'e göre çalışır.
        # Bu yüzden, komuta gönderilecek selected_refs, initial_states ile aynı öğeleri işaret etmeli.
        # _get_current_selection_states zaten (type, index, data) formatında.
        # Komutun, bu type ve index'i kullanarak öğelere erişmesi gerekiyor.
        # selected_item_indices, komut oluşturulmadan hemen önce alınabilir.
        
        current_selected_refs = list(canvas.selected_item_indices) # Komut için o anki seçimi al

        # Final states'i, canvas._calculate_final_states_for_move ile hesapla.
        # Bu fonksiyon, initial_states'in bir kopyasını alıp dx, dy kadar taşır.
        # ÖNEMLİ: canvas._calculate_final_states_for_move, initial_states'deki *her bir öğe için*
        # item_type ve index'e ihtiyaç duyar. initial_states_for_command zaten bu formatta olmalı.
        # ('type': ..., 'index': ..., 'data': ...)
        # selected_item_indices'i de (type, index) tuple listesi olarak bekler.
        
        # initial_states_for_command (ki bu canvas.move_original_states) zaten _get_current_selection_states'ten
        # [{ 'type': ..., 'index': ..., 'data': ...}, ...] formatında gelmeli.
        # selected_refs de [(type, index), ...] formatında olmalı.
        # _calculate_final_states_for_move'a bu selected_refs'i ve initial_states_for_command'ı verebiliriz.

        # _get_current_selection_states, selected_item_indices'e göre çalışır.
        # Taşıma bittiğinde, canvas'taki öğeler zaten son konumlarındadır (_reposition sayesinde).
        # Bu yüzden final_states'i doğrudan canvas'tan okuyabiliriz.
        final_states_for_command = canvas._get_current_selection_states(canvas._parent_page)

        if not final_states_for_command:
            logging.error("Move Release: final_states_for_command alınamadı veya boş! Komut oluşturulmayacak.")
        elif len(initial_states_for_command) != len(final_states_for_command):
             logging.error(f"Move Release: initial_states ({len(initial_states_for_command)}) ve final_states ({len(final_states_for_command)}) uzunlukları farklı! Komut oluşturulmayacak.")
        elif len(initial_states_for_command) != len(current_selected_refs):
             logging.error(f"Move Release: initial_states ({len(initial_states_for_command)}) ve current_selected_refs ({len(current_selected_refs)}) uzunlukları farklı! Komut oluşturulmayacak.")
        else:
            # Komut için selected_item_refs, initial_states ile aynı öğeleri göstermeli.
            # initial_states_for_command her bir state için {'type': ..., 'index': ...} içeriyor.
            # Komutun bunu işlemesi lazım.
            # MoveItemsCommand'ın __init__ imzası: (canvas, item_indices: List[Tuple[str, int]], original_states: List[Any], final_states: List[Any])
            # Buradaki item_indices, bizim current_selected_refs'e karşılık geliyor.
            # original_states ve final_states ise [{'type': ..., 'index': ..., 'data': ...}] listeleri.
            
            # Kontrol: Acaba _calculate_final_states_for_move daha mı doğru olurdu?
            # Evet, çünkü _reposition_selected_items_from_initial anlık olarak canvas'ı güncellerken,
            # komut için "taşıma öncesi" ve "taşıma sonrası" net durumlar gerekir.
            # _calculate_final_states_for_move, initial_states'e dx, dy uygulayarak final_states'i verir.
            
            calculated_final_states = canvas._calculate_final_states_for_move(
                initial_states_for_command, # Bu zaten [{type, index, data}, ...] formatında
                current_selected_refs,      # Bu [(type, index), ...] formatında
                total_dx,
                total_dy
            )

            if not calculated_final_states or len(calculated_final_states) != len(initial_states_for_command):
                logging.error("Move Release: _calculate_final_states_for_move beklenen sonucu vermedi. Komut oluşturulmayacak.")
            else:
                # --- SNAP TO GRID (TOLERANSLI) --- #
                tolerance_px = 8
                for i, (item_type, index) in enumerate(current_selected_refs):
                    if item_type == 'shapes' and i < len(calculated_final_states):
                        shape_data = calculated_final_states[i]
                        tool_type = shape_data[0]
                        if tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE] and getattr(canvas, 'snap_lines_to_grid', False):
                            p1 = shape_data[3]
                            p2 = shape_data[4]
                            snap_p1 = canvas._snap_point_to_grid(p1)
                            snap_p2 = canvas._snap_point_to_grid(p2)
                            if (p1 - snap_p1).manhattanLength() <= tolerance_px:
                                shape_data[3] = snap_p1
                            if (p2 - snap_p2).manhattanLength() <= tolerance_px:
                                shape_data[4] = snap_p2
                # --- --- --- --- --- --- --- --- --- #
                command = MoveItemsCommand(
                    canvas=canvas,
                    item_indices=current_selected_refs, # [(type, index), ...]
                    original_states=initial_states_for_command, # [{'type':..., 'index':..., 'data':...}, ...]
                    final_states=calculated_final_states      # [{'type':..., 'index':..., 'data':...}, ...]
                    # page_ref is not directly passed to MoveItemsCommand in its definition, it uses canvas._parent_page
                )
                canvas.undo_manager.execute(command)
                # content_changed.emit() komutun execute'u içinde yapılabilir veya burada.
                # Şimdilik komuta bırakalım veya command execute sonrası canvas'tan emit edilebilir.
                # canvas.content_changed.emit() # Sayfa içeriği değişti
                #logging.debug("  MoveItemsCommand executed.")

    else:
        logging.debug("  No significant move detected or no original states. No command created.")

    canvas.move_start_point = QPointF() # veya None
    canvas.move_original_states.clear()
    # canvas.last_move_pos = QPointF() # Kullanımdan kaldırıldı

    canvas.update()

def handle_selector_resize_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    # --- DÖNDÜRME TUTAMAÇ --- #
    if canvas.grabbed_handle_type == 'rotate' and canvas.selected_item_indices:
        # Döndürme işlemi bittiğinde komut olarak kaydet (undo/redo için)
        from utils.commands import MoveItemsCommand
        
        if canvas.original_resize_states:
            final_states = canvas._get_current_selection_states(canvas._parent_page)
            command = MoveItemsCommand(
                canvas, 
                canvas.selected_item_indices.copy(), 
                canvas.original_resize_states.copy(), 
                final_states
            )
            canvas.undo_manager.execute(command)
        
        # Temizlik
        if hasattr(canvas, 'rotation_start_angle'):
            del canvas.rotation_start_angle
        
        QApplication.restoreOverrideCursor()
        canvas.resizing_selection = False
        canvas.grabbed_handle_type = None
        canvas.original_resize_states.clear()
        canvas.resize_original_bbox = QRectF()
        canvas.resize_start_pos = QPointF()
        canvas.update()
        return
    """Seçili öğelerin yeniden boyutlandırılmasının bittiği olayı yönetir."""
    #logging.debug(f"[selector_tool_handler] handle_selector_resize_release: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    #logging.debug(f"Resize selection finished. Handle: {canvas.grabbed_handle_type}, End World Pos: {pos}")
    
    # --- YENİ: DÜZENLENEBILIR ÇIZGI için özel tutamaç işlemi --- #
    if (
        len(canvas.selected_item_indices) == 1 and
        canvas.selected_item_indices[0][0] == 'shapes' and
        canvas.grabbed_handle_type and
        (canvas.grabbed_handle_type.startswith('main_') or 
         canvas.grabbed_handle_type.startswith('control1_') or 
         canvas.grabbed_handle_type.startswith('control2_'))
    ):
        shape_index = canvas.selected_item_indices[0][1]
        if 0 <= shape_index < len(canvas.shapes):
            shape_data = canvas.shapes[shape_index]
            tool_type = shape_data[0]
            
            if tool_type == ToolType.EDITABLE_LINE:
                # Değişiklikleri kalıcı hale getirmek için
                from utils.commands import UpdateEditableLineCommand
                
                original_control_points = []
                if canvas.original_resize_states and canvas.original_resize_states[0]:
                    original_control_points = canvas.original_resize_states[0][3]
                
                current_control_points = shape_data[3]
                
                # Değişikliği kaydet
                if original_control_points and current_control_points and original_control_points != current_control_points:
                    command = UpdateEditableLineCommand(
                        canvas,
                        shape_index,
                        original_control_points,
                        current_control_points
                    )
                    canvas.undo_manager.execute(command)
                    
                    if canvas._parent_page:
                        canvas._parent_page.mark_as_modified()
                    if hasattr(canvas, 'content_changed'):
                        canvas.content_changed.emit()
                
                # UI ve durum temizleme
                QApplication.restoreOverrideCursor()
                canvas.resizing_selection = False
                canvas.grabbed_handle_type = None
                canvas.original_resize_states.clear()
                canvas.resize_original_bbox = QRectF()
                canvas.resize_start_pos = QPointF()
                canvas.update()
                return
    
    if canvas.grabbed_handle_type and canvas.original_resize_states:
        final_states = canvas._get_current_selection_states(canvas._parent_page)
        # --- SNAP TO GRID (TOLERANSLI) --- #
        tolerance_px = 8
        for i, (item_type, index) in enumerate(canvas.selected_item_indices):
            if item_type == 'shapes' and i < len(final_states):
                shape_data = final_states[i]
                tool_type = shape_data[0]
                if tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE] and getattr(canvas, 'snap_lines_to_grid', False):
                    p1 = shape_data[3]
                    p2 = shape_data[4]
                    snap_p1 = canvas._snap_point_to_grid(p1)
                    snap_p2 = canvas._snap_point_to_grid(p2)
                    if (p1 - snap_p1).manhattanLength() <= tolerance_px:
                        shape_data[3] = snap_p1
                    if (p2 - snap_p2).manhattanLength() <= tolerance_px:
                        shape_data[4] = snap_p2
        # --- --- --- --- --- --- --- --- --- #
        final_bbox = canvas._get_combined_bbox([]) # Pass empty list, it uses canvas.selected_item_indices
        orig_bbox_str = f"({canvas.resize_original_bbox.x():.1f},{canvas.resize_original_bbox.y():.1f}, w={canvas.resize_original_bbox.width():.1f}, h={canvas.resize_original_bbox.height():.1f})"
        final_bbox_str = f"({final_bbox.x():.1f},{final_bbox.y():.1f}, w={final_bbox.width():.1f}, h={final_bbox.height():.1f})" if not final_bbox.isNull() else "Null"
        logging.debug(f"  Creating ResizeItemsCommand: Original BBox: {orig_bbox_str}, Final BBox: {final_bbox_str}")
        if not final_bbox.isNull() and abs((final_bbox.topLeft() - canvas.resize_original_bbox.topLeft()).manhattanLength()) > 1e-6 \
           or abs(final_bbox.width() - canvas.resize_original_bbox.width()) > 1e-6 \
           or abs(final_bbox.height() - canvas.resize_original_bbox.height()) > 1e-6:
             try:
                 indices_copy = copy.deepcopy(canvas.selected_item_indices)
                 command = ResizeItemsCommand(canvas, indices_copy, canvas.original_resize_states, final_states)
                 logging.debug(f"  Attempting undo_manager.execute(ResizeItemsCommand) with {len(indices_copy)} items.")
                 canvas.undo_manager.execute(command)
                 logging.debug("  ResizeItemsCommand executed via manager.")
                 # --- YENİ: Resim handler entegrasyonu (boyutlandırma ve döndürme) --- #
                 item_type, index = canvas.selected_item_indices[0]
                 if item_type == 'images' and canvas._parent_page and 0 <= index < len(canvas._parent_page.images):
                     img_data = canvas._parent_page.images[index]
                     dosya_yolu = img_data.get('path', None)
                     if dosya_yolu:
                         # Boyutlandırma
                         yeni_genislik = int(img_data['rect'].width())
                         yeni_yukseklik = int(img_data['rect'].height())
                         try:
                             from handlers import resim_islem_handler
                             resim_islem_handler.handle_resize_image(dosya_yolu, yeni_genislik, yeni_yukseklik)
                         except Exception as e:
                             logging.error(f"Resim handler'a boyutlandırma aktarılırken hata: {e}")
                         # Döndürme
                         yeni_aci = float(img_data.get('angle', 0.0))
                         try:
                             from handlers import resim_islem_handler
                             resim_islem_handler.handle_rotate_image(dosya_yolu, yeni_aci)
                         except Exception as e:
                             logging.error(f"Resim handler'a döndürme aktarılırken hata: {e}")
                 # --- --- --- --- --- --- --- --- --- --- --- #
             except Exception as e: logging.error(f"ResizeItemsCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
        else: logging.debug("Resize selection finished: No significant change detected, no command created.")
    elif not canvas.grabbed_handle_type: logging.warning("Resize release called but no handle was grabbed.")
    elif not canvas.original_resize_states: logging.warning("Resize release called but no original states were recorded.")
    QApplication.restoreOverrideCursor()
    canvas.resizing_selection = False
    canvas.grabbed_handle_type = None
    canvas.original_resize_states.clear()
    canvas.resize_original_bbox = QRectF() # Bu da temizlenmeli
    canvas.resize_start_pos = QPointF()
    canvas.update()

def handle_selector_select_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Dikdörtgen ile seçim yapmanın bittiği olayı yönetir."""
    #logging.debug(f"[selector_tool_handler] handle_selector_select_release: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    canvas.shape_end_point = pos
    selection_world_rect = QRectF(canvas.shape_start_point, canvas.shape_end_point).normalized()
    #logging.debug(f"Selection rectangle finished: {selection_world_rect}")
    selected_item_refs = []
    for i, line_data in enumerate(canvas.lines):
        line_bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        if not line_bbox.isNull() and selection_world_rect.intersects(line_bbox):
            selected_item_refs.append(('lines', i))
    
    for i, shape_data in enumerate(canvas.shapes):
        # Şekil için sınırlayıcı kutuyu hesapla
        bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        
        # Sınırlayıcı kutu seçim kutusuyla kesişiyorsa şekli seç
        if bbox.isNull():
            continue
        
        if selection_world_rect.intersects(bbox):
            #logging.debug(f"  SHAPE {i} (type: {shape_data[0]}): BBox={bbox}, SelRect={selection_world_rect}, QtIntersects={selection_world_rect.intersects(bbox)}")
            
            # Tüm şekilleri normal şekilde seç, EdiatbleLine şekilleri için özel işlem yapma
            selected_item_refs.append(('shapes', i))
    
    # YENİ: Düzenlenebilir çizgileri kontrol et
    for i, editable_line_data in enumerate(canvas.editable_lines):
        editable_line_bbox = geometry_helpers.get_item_bounding_box(editable_line_data, 'editable_lines')
        if not editable_line_bbox.isNull() and selection_world_rect.intersects(editable_line_bbox):
            selected_item_refs.append(('editable_lines', i))
    
    # YENİ: Mevcut resim öğelerini kontrol et
    if canvas._parent_page and hasattr(canvas._parent_page, 'images') and canvas._parent_page.images:
        for i, img_data in enumerate(canvas._parent_page.images):
            rect = img_data.get('rect')
            angle = img_data.get('angle', 0.0)
            if rect and isinstance(rect, QRectF):
                # Döndürülmüş resim bbox'ını al
                rotated_corners = geometry_helpers.get_rotated_corners(rect, angle)
                item_bbox_polygon = QPolygonF(rotated_corners)
                if selection_world_rect.intersects(item_bbox_polygon.boundingRect()): # Polygonun bbox'ı ile kesişim
                    selected_item_refs.append(('images', i))
    
    # YENİ: B-Spline çizgilerini kontrol et
    if hasattr(canvas, 'b_spline_strokes') and canvas.b_spline_strokes:
        #logging.debug(f"  handle_selector_select_release: Checking {len(canvas.b_spline_strokes)} B-Spline strokes for selection rect: {selection_world_rect}")
        for i, stroke_data in enumerate(canvas.b_spline_strokes):
            try:
                item_bbox = geometry_helpers.get_bspline_bounding_box(stroke_data)
                #logging.debug(f"    B-Spline stroke {i} bbox: {item_bbox}")
                if not item_bbox.isNull() and selection_world_rect.intersects(item_bbox):
                    #logging.debug(f"      >>> B-Spline stroke {i} INTERSECTS selection rect.")
                    selected_item_refs.append(('bspline_strokes', i))
                elif item_bbox.isNull():
                    #logging.debug(f"      B-Spline stroke {i} bbox isNull.")
                    pass
                else:
                    #logging.debug(f"      B-Spline stroke {i} does NOT intersect selection rect.")
                    pass    
            except Exception as e:
                #logging.error(f"handle_selector_select_release: B-Spline bbox alınırken/kontrol edilirken hata (stroke {i}): {e}", exc_info=True)
                pass
    # YENİ KONTROL SONU

    # Yeni seçimleri ayarla
    if selected_item_refs:
        canvas.selected_item_indices = selected_item_refs
        canvas.update()
        #logging.debug(f"Selection updated: {len(selected_item_refs)} items selected.")
    
    canvas.selecting = False
    
    # Her durumda işaret olarak seçimi bırak
    canvas.selecting = False
    canvas.drawing = False
    canvas.drawing_shape = False # Şekil çizim moduyla ilgili bayrakları da sıfırla
    canvas.shape_start_point = QPointF()
    canvas.shape_end_point = QPointF()
    canvas.update()

    # Ctrl basılı değilse ve yeni bir seçim yapılmadıysa eski seçimi koru
    if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and not selected_item_refs:
        canvas.selected_item_indices = selected_item_refs
        canvas.update()
        logging.debug(f"Selected items updated: {len(selected_item_refs)} items selected.")
    
    canvas.selecting = False
    
    # Her durumda işaret olarak seçimi bırak
    canvas.selecting = False
    canvas.drawing = False
    canvas.drawing_shape = False # Şekil çizim moduyla ilgili bayrakları da sıfırla
    canvas.shape_start_point = QPointF()
    canvas.shape_end_point = QPointF()
    canvas.update() 
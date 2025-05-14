"""
Seçici (Selector) aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, List, Tuple, Any
import copy

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QTabletEvent
from PyQt6.QtWidgets import QApplication

from utils import geometry_helpers, selection_helpers # selection_helpers da gerekebilir
from utils.commands import MoveItemsCommand, ResizeItemsCommand
from gui.enums import ToolType

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas
    # from ..page import Page # Doğrudan Page kullanılmıyor, canvas._parent_page üzerinden erişiliyor

def handle_selector_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçici aracı için basma olayını yönetir."""
    logging.debug(f"[selector_tool_handler] handle_selector_press: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    screen_pos = event.position() 
    canvas.grabbed_handle_type = None
    click_tolerance = 5.0 
    click_rect = QRectF(screen_pos.x() - click_tolerance, 
                       screen_pos.y() - click_tolerance, 
                       click_tolerance * 2, 
                       click_tolerance * 2)
                       
    logging.debug(f"Selector Press: Screen Pos = ({screen_pos.x():.1f}, {screen_pos.y():.1f}), World Pos = ({pos.x():.1f}, {pos.y():.1f}), Click Rect = {click_rect}")
    if not canvas.current_handles:
        logging.debug("Selector Press: canvas.current_handles is EMPTY.")
    else:
        logging.debug(f"Selector Press: Checking against handles: {canvas.current_handles}")
        for handle_type, handle_rect_screen in canvas.current_handles.items():
            intersects = handle_rect_screen.intersects(click_rect)
            logging.debug(f"  Checking handle '{handle_type}': rect={handle_rect_screen}, intersects={intersects}")
            if intersects:
                canvas.grabbed_handle_type = handle_type
                logging.debug(f"  >>> Handle grabbed: {canvas.grabbed_handle_type}")
                break
            
    if not canvas.grabbed_handle_type:
        point_on_selection = canvas.is_point_on_selection(pos)
        logging.debug(f"Selector Press: No handle grabbed. Checking point on selection (World Pos: {pos.x():.1f}, {pos.y():.1f})... Result: {point_on_selection}")
        if point_on_selection:
            canvas.moving_selection = True
            canvas.drawing = False
            canvas.resizing_selection = False
            canvas.selecting = False
            canvas.move_start_point = pos
            canvas.last_move_pos = pos
            canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
            logging.debug(f"Moving selection started, start world pos: {pos}")
            QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
        else:
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                logging.debug("Clearing previous selection.")
                canvas.selected_item_indices.clear()
            canvas.drawing = True
            canvas.selecting = True
            canvas.resizing_selection = False
            canvas.moving_selection = False
            canvas.shape_start_point = pos
            canvas.shape_end_point = pos
            logging.debug(f"Selection rectangle started world pos: {pos}")
            QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
    else: 
        canvas.resizing_selection = True
        canvas.drawing = False
        canvas.moving_selection = False
        canvas.resize_start_pos = pos 
        if canvas._parent_page:
            logging.debug(f"_handle_selector_press (RESIZE BRANCH): canvas._parent_page IS Page {canvas._parent_page.page_number}")
        else:
            logging.error("_handle_selector_press (RESIZE BRANCH): canvas._parent_page IS NONE HERE!")
        canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
        canvas.resize_original_bbox = canvas._get_combined_bbox([]) # Boş liste ile çağırabiliriz, canvas.selected_item_indices'i kullanır
        logging.debug(f"Resizing started, handle: {canvas.grabbed_handle_type}, start world pos: {pos}")
        logging.debug(f"  >>> Length Check @ Press: original_states={len(canvas.original_resize_states)}, selected_indices={len(canvas.selected_item_indices)}")
        if len(canvas.original_resize_states) != len(canvas.selected_item_indices):
             logging.error("  >>> MISMATCH DETECTED AT PRESS EVENT!")
        QApplication.setOverrideCursor(geometry_helpers.get_resize_cursor(canvas.grabbed_handle_type))
        
    canvas.update()

def handle_selector_move_selection(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin (çizim/şekil) taşınmasını yönetir."""
    logging.debug(f"[selector_tool_handler] handle_selector_move_selection: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    if not canvas.move_start_point.isNull():
        dx = pos.x() - canvas.last_move_pos.x()
        dy = pos.y() - canvas.last_move_pos.y()
        log_msg = f"Selector Move Selection: World Pos=({pos.x():.1f},{pos.y():.1f}), dx={dx:.2f}, dy={dy:.2f}"
        if canvas.selected_item_indices:
            item_type, index = canvas.selected_item_indices[0]
            try:
                item_list = getattr(canvas, item_type)
                if 0 <= index < len(item_list):
                    points_data = item_list[index][2 if item_type == 'lines' else 3]
                    first_point = points_data[0] if isinstance(points_data, list) and points_data else (points_data if isinstance(points_data, QPointF) else None)
                    if first_point: log_msg += f" | Before move: First item's p1=({first_point.x():.1f},{first_point.y():.1f})"
            except Exception: pass
        logging.debug(log_msg)
        if dx != 0 or dy != 0:
            geometry_helpers.move_items_by(canvas.lines, canvas.shapes, canvas.selected_item_indices, dx, dy)
            log_msg_after = "  After move:"
            if canvas.selected_item_indices:
                item_type, index = canvas.selected_item_indices[0]
                try:
                    item_list = getattr(canvas, item_type)
                    if 0 <= index < len(item_list):
                        points_data = item_list[index][2 if item_type == 'lines' else 3]
                        first_point = points_data[0] if isinstance(points_data, list) and points_data else (points_data if isinstance(points_data, QPointF) else None)
                        if first_point: log_msg_after += f" First item's p1=({first_point.x():.1f},{first_point.y():.1f})"
                except Exception: pass
            logging.debug(log_msg_after)
            canvas.last_move_pos = pos
            canvas.update()

def handle_selector_rect_select_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Dikdörtgen ile seçim yaparkenki hareketi yönetir."""
    canvas.shape_end_point = pos
    canvas.update()

def handle_selector_resize_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin (çizim/şekil) yeniden boyutlandırılmasını yönetir."""
    logging.debug(f"[selector_tool_handler] handle_selector_resize_move: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    
    # --- YENİ: DÜZENLENEBILIR ÇIZGI için özel tutamaç işlemi --- #
    if (
        len(canvas.selected_item_indices) == 1 and
        canvas.selected_item_indices[0][0] == 'shapes' and
        canvas.grabbed_handle_type
    ):
        shape_index = canvas.selected_item_indices[0][1]
        if 0 <= shape_index < len(canvas.shapes):
            shape_data = canvas.shapes[shape_index]
            tool_type = shape_data[0]
            
            # Düzenlenebilir çizgi işlemi
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
                if canvas.grabbed_handle_type == 'start':
                    canvas.shapes[shape_index][3] = pos
                elif canvas.grabbed_handle_type == 'end':
                    canvas.shapes[shape_index][4] = pos
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
                                original_p1 = original_item_data[3]
                                original_p2 = original_item_data[4]
                                logging.debug(f"  Shape[{index}] P1 (Original): {original_p1}, P2 (Original): {original_p2}")
                                relative_p1 = original_p1 - original_center
                                scaled_p1 = QPointF(relative_p1.x() * scale_x, relative_p1.y() * scale_y)
                                transformed_p1 = scaled_p1 + original_center + translate_delta
                                relative_p2 = original_p2 - original_center
                                scaled_p2 = QPointF(relative_p2.x() * scale_x, relative_p2.y() * scale_y)
                                transformed_p2 = scaled_p2 + original_center + translate_delta
                                logging.debug(f"    P1 (Transformed): {transformed_p1}, P2 (Transformed): {transformed_p2}")
                                canvas.shapes[index][3] = transformed_p1
                                canvas.shapes[index][4] = transformed_p2
                        else: logging.warning(f"Resize Move: Geçersiz shapes index {index}")
                except Exception as e:
                     logging.error(f"Resize Move sırasında öğe ({item_type}[{index}]) güncellenirken hata: {e}", exc_info=True)
            canvas.update()

def handle_selector_move_selection_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin taşınmasının bittiği olayı yönetir."""
    logging.debug(f"[selector_tool_handler] handle_selector_move_selection_release: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    if not canvas.move_start_point.isNull():
        manhattan_dist = (pos - canvas.move_start_point).manhattanLength()
        logging.debug(f"Move selection finished. Start: {canvas.move_start_point}, End: {pos}, Manhattan Distance: {manhattan_dist:.2f}")
        if manhattan_dist > 1e-6 and canvas.selected_item_indices and canvas.move_original_states:
             final_states = canvas._get_current_selection_states(canvas._parent_page)
             orig_state_summary = "N/A"
             final_state_summary = "N/A"
             try:
                 if canvas.move_original_states and canvas.move_original_states[0]:
                     p_orig = canvas.move_original_states[0][2][0] if canvas.move_original_states[0][0] == 'lines' else canvas.move_original_states[0][3]
                     orig_state_summary = f"({p_orig.x():.1f},{p_orig.y():.1f})"
                 if final_states and final_states[0]:
                     p_final = final_states[0][2][0] if final_states[0][0] == 'lines' else final_states[0][3]
                     final_state_summary = f"({p_final.x():.1f},{p_final.y():.1f})"
             except Exception: pass
             logging.debug(f"  Creating MoveItemsCommand: Original state (p1): {orig_state_summary}, Final state (p1): {final_state_summary}")
             try:
                 indices_copy = copy.deepcopy(canvas.selected_item_indices)
                 # --- YENİ: Sadece images için özel taşıma --- #
                 item_type, index = canvas.selected_item_indices[0]
                 if item_type == 'images' and canvas._parent_page and 0 <= index < len(canvas._parent_page.images):
                     img_data = canvas._parent_page.images[index]
                     dosya_yolu = img_data.get('path', None)
                     if dosya_yolu:
                         yeni_x = int(pos.x() - img_data['rect'].width() / 2)
                         yeni_y = int(pos.y() - img_data['rect'].height() / 2)
                         try:
                             from handlers import resim_islem_handler
                             sonuc = resim_islem_handler.handle_move_image(dosya_yolu, yeni_x, yeni_y)
                             # Sadece handler'dan dönen yeni konumu uygula
                             img_data['rect'].moveTo(yeni_x, yeni_y)
                             canvas.update()
                         except Exception as e:
                             logging.error(f"Resim handler'a taşıma aktarılırken hata: {e}")
                 else:
                     # Eski kod: sadece images dışı için çalışsın
                     command = MoveItemsCommand(canvas, indices_copy, canvas.move_original_states, final_states) 
                     logging.debug(f"  Attempting undo_manager.execute(MoveItemsCommand) with {len(indices_copy)} items.")
                     canvas.undo_manager.execute(command)
                     logging.debug("  MoveItemsCommand executed via manager.")
                 # --- --- --- --- --- --- --- --- --- --- --- #
             except Exception as e: logging.error(f"MoveItemsCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
        elif not canvas.selected_item_indices: logging.debug("Move selection finished: No items were selected when release occurred.")
        elif not canvas.move_original_states: logging.debug("Move selection finished: Original states were not recorded.")
        else: logging.debug("Move selection finished: No significant movement detected or other issue, no command created.")
    QApplication.restoreOverrideCursor()
    canvas.move_start_point = QPointF()
    canvas.moving_selection = False
    canvas.move_original_states.clear() 
    canvas.update()

def handle_selector_resize_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Seçili öğelerin yeniden boyutlandırılmasının bittiği olayı yönetir."""
    logging.debug(f"[selector_tool_handler] handle_selector_resize_release: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    logging.debug(f"Resize selection finished. Handle: {canvas.grabbed_handle_type}, End World Pos: {pos}")
    
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
    logging.debug(f"[selector_tool_handler] handle_selector_select_release: shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    canvas.shape_end_point = pos
    selection_world_rect = QRectF(canvas.shape_start_point, canvas.shape_end_point).normalized()
    logging.debug(f"Selection rectangle finished: {selection_world_rect}")
    newly_selected: List[Tuple[str, int]] = []
    for i, line_data in enumerate(canvas.lines):
        line_bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        if not line_bbox.isNull() and selection_world_rect.intersects(line_bbox):
            newly_selected.append(('lines', i))
    for i, shape_data in enumerate(canvas.shapes):
        shape_bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        intersects_result = False
        manual_intersects = False # Yeni değişken
        if not shape_bbox.isNull():
            intersects_result = selection_world_rect.intersects(shape_bbox)
            
            # --- Manuel kesişim kontrolü ---
            sel_left = selection_world_rect.left()
            sel_right = selection_world_rect.right()
            sel_top = selection_world_rect.top()
            sel_bottom = selection_world_rect.bottom()

            item_left = shape_bbox.left()
            item_right = shape_bbox.right()
            item_top = shape_bbox.top()
            item_bottom = shape_bbox.bottom()

            # Genişlik veya yükseklik sıfır olsa bile bu kontrol çalışmalı
            x_overlap = (item_left <= sel_right) and (item_right >= sel_left)
            y_overlap = (item_top <= sel_bottom) and (item_bottom >= sel_top)
            manual_intersects = x_overlap and y_overlap
            # --- --- --- --- --- --- --- --- ---

        logging.debug(f"  Checking shape {i} (type: {shape_data[0]}): BBox={shape_bbox}, SelRect={selection_world_rect}, QtIntersects={intersects_result}, ManualIntersects={manual_intersects}")
        
        # if not shape_bbox.isNull() and selection_world_rect.intersects(shape_bbox): # ESKİ KONTROL
        if not shape_bbox.isNull() and manual_intersects: # YENİ KONTROL
             newly_selected.append(('shapes', i))
    shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
    if shift_pressed:
        for item_type, index in newly_selected:
            if (item_type, index) in canvas.selected_item_indices:
                canvas.selected_item_indices.remove((item_type, index))
            else:
                canvas.selected_item_indices.append((item_type, index))
    else:
        canvas.selected_item_indices = newly_selected
    logging.debug(f"Selection updated: {len(canvas.selected_item_indices)} items selected.")
    QApplication.restoreOverrideCursor()
    canvas.drawing = False
    canvas.selecting = False
    canvas.drawing_shape = False # Şekil çizim moduyla ilgili bayrakları da sıfırla
    canvas.shape_start_point = QPointF()
    canvas.shape_end_point = QPointF()
    canvas.update() 
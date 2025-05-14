"""
Düzenlenebilir Çizgi aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, List
import math

from PyQt6.QtCore import QPointF, Qt, QDateTime
from PyQt6.QtGui import QTabletEvent

from utils.commands import DrawEditableLineCommand, UpdateEditableLineCommand
from ..enums import ToolType

# Sabitler
HANDLE_SIZE = 15  # Tablet kalemi için normal tutucu boyutundan daha büyük
MIN_POINT_DISTANCE = 10  # İki nokta arasındaki minimum mesafe (piksel)
SIMPLIFICATION_EPSILON = 3.0  # Douglas-Peucker algoritması için epsilon değeri 

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas

# Bezier eğrisi kontrol noktalarını oluşturmak için yardımcı fonksiyon
def calculate_bezier_control_points(p0: QPointF, p1: QPointF) -> List[QPointF]:
    """İki nokta arasında varsayılan cubic bezier kontrol noktaları hesaplar."""
    dx = p1.x() - p0.x()
    dy = p1.y() - p0.y()
    distance = math.sqrt(dx * dx + dy * dy)
    
    # Kontrol noktaları, mesafenin 1/3'ü kadar uzaklıkta
    control_distance = distance / 3
    
    # Kontrol noktaları, p0 ve p1 arasındaki doğrultuda yerleşir
    angle = math.atan2(dy, dx)
    
    # İlk kontrol noktası (p0'dan)
    c1_x = p0.x() + control_distance * math.cos(angle)
    c1_y = p0.y() + control_distance * math.sin(angle)
    
    # İkinci kontrol noktası (p1'den)
    c2_x = p1.x() - control_distance * math.cos(angle)
    c2_y = p1.y() - control_distance * math.sin(angle)
    
    return [p0, QPointF(c1_x, c1_y), QPointF(c2_x, c2_y), p1]

def handle_editable_line_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi aracı için basma olayını yönetir."""
    logging.debug("Editable Line Press: Checking for handles or starting new line.")
    
    right_button_pressed = event.button() == Qt.MouseButton.RightButton
    
    # Eğer sağ tuşa basılmışsa aktif noktayı sil, böylece tablet kalemi sağ düğmesiyle düzenleme iptal edilebilir
    if right_button_pressed:
        canvas.active_handle_index = -1
        canvas.active_bezier_handle_index = -1
        canvas.is_dragging_bezier_handle = False
        return
    
    # Önce mevcut tutamaçları (handle) kontrol et
    handle_found = False
    
    # Bezier kontrol noktalarını kontrol et
    if len(canvas.bezier_control_points) >= 4:
        for i, point in enumerate(canvas.bezier_control_points):
            if i % 3 == 0:  # Ana noktalar (p0, p1, p2, ...)
                continue
                
            # Noktaya yakın mı kontrol et (tablet için daha geniş tolerans)
            distance = (pos - point).manhattanLength()
            if distance <= HANDLE_SIZE:
                canvas.active_bezier_handle_index = i
                canvas.is_dragging_bezier_handle = True
                handle_found = True
                logging.debug(f"Editable Line Press: Bezier kontrol noktası {i} seçildi.")
                break
    
    # Eğer bezier kontrol noktası bulunamadıysa, ana noktaları kontrol et
    if not handle_found:
        for i, point in enumerate(canvas.current_editable_line_points):
            # Noktaya yakın mı kontrol et (tablet için daha geniş tolerans)
            distance = (pos - point).manhattanLength()
            if distance <= HANDLE_SIZE:
                canvas.active_handle_index = i
                handle_found = True
                logging.debug(f"Editable Line Press: Ana nokta {i} seçildi.")
                
                # Bezier kontrol noktalarını güncelle
                update_bezier_control_points(canvas)
                break
    
    # Eğer hiçbir tutamaç bulunamadıysa yeni çizim başlat
    if not handle_found:
        # Mevcut çizimleri temizle ve yeni çizime başla
        canvas.current_editable_line_points = [pos]  # İlk noktayı ekle
        canvas.active_handle_index = -1
        canvas.active_bezier_handle_index = -1
        canvas.is_dragging_bezier_handle = False
        canvas.bezier_control_points = [pos]
        logging.debug(f"Editable Line Press: Yeni çizim başlatıldı.")
    
    canvas.drawing = True
    # Ekranı hemen güncelle ki kullanıcı yeni noktayı ve çizgiyi görebilsin
    canvas.update()

def update_bezier_control_points(canvas: 'DrawingCanvas'):
    """Mevcut editable_line_points'e göre bezier kontrol noktalarını günceller.
    Her iki nokta arasında bir cubic bezier eğrisi oluşturur.
    """
    points = canvas.current_editable_line_points
    
    # Tek nokta bile olsa gösterilmesi için
    if len(points) == 0:
        canvas.bezier_control_points = []
        return
    elif len(points) == 1:
        # Tek nokta varsa, sadece o noktayı ekleyelim
        canvas.bezier_control_points = [points[0]]
        return
    
    # Tüm noktalar için kontrol noktalarını hesapla
    bezier_points = []
    
    for i in range(len(points) - 1):
        p0 = points[i]
        p1 = points[i + 1]
        
        # Her iki nokta arasındaki kontrol noktalarını hesapla
        segment_points = calculate_bezier_segment(p0, p1)
        
        # İlk segment için tüm noktaları ekle
        if i == 0:
            bezier_points.extend(segment_points)
        else:
            # Sonraki segmentler için ilk noktayı atlayarak ekle (zaten eklenmiş durumda)
            bezier_points.extend(segment_points[1:])
    
    canvas.bezier_control_points = bezier_points

def calculate_bezier_segment(p0: QPointF, p1: QPointF) -> List[QPointF]:
    """İki nokta arasında kubik bezier eğrisi segmenti için kontrol noktalarını hesaplar."""
    dx = p1.x() - p0.x()
    dy = p1.y() - p0.y()
    distance = math.sqrt(dx * dx + dy * dy)
    
    # Kontrol noktaları, mesafenin 1/3'ü kadar uzaklıkta
    control_distance = distance / 3
    
    # Kontrol noktaları, p0 ve p1 arasındaki doğrultuda yerleşir
    angle = math.atan2(dy, dx)
    
    # İlk kontrol noktası (p0'dan)
    c1_x = p0.x() + control_distance * math.cos(angle)
    c1_y = p0.y() + control_distance * math.sin(angle)
    
    # İkinci kontrol noktası (p1'den)
    c2_x = p1.x() - control_distance * math.cos(angle)
    c2_y = p1.y() - control_distance * math.sin(angle)
    
    return [p0, QPointF(c1_x, c1_y), QPointF(c2_x, c2_y), p1]

def handle_editable_line_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi aracı için hareket olayını yönetir."""
    if not canvas.drawing:
        return
    
    if canvas.is_dragging_bezier_handle and canvas.active_bezier_handle_index != -1:
        # Bezier kontrol noktasını güncelle
        canvas.bezier_control_points[canvas.active_bezier_handle_index] = pos
        logging.debug(f"Editable Line Move: Bezier kontrol noktası {canvas.active_bezier_handle_index} güncellendi.")
    elif canvas.active_handle_index != -1:
        # Ana noktayı güncelle
        canvas.current_editable_line_points[canvas.active_handle_index] = pos
        logging.debug(f"Editable Line Move: Ana nokta {canvas.active_handle_index} güncellendi.")
        
        # Bezier kontrol noktalarını da güncelle
        update_bezier_control_points(canvas)
    else:
        # Yeni çizim modunda, noktaları ekliyoruz
        if len(canvas.current_editable_line_points) > 0:
            # Son nokta ile yeni nokta arasındaki mesafeyi kontrol et
            last_point = canvas.current_editable_line_points[-1]
            distance = math.sqrt((pos.x() - last_point.x())**2 + (pos.y() - last_point.y())**2)
            
            # Eğer minimum mesafeyi aşıyorsa yeni nokta ekle
            if distance >= MIN_POINT_DISTANCE:
                canvas.current_editable_line_points.append(pos)
                update_bezier_control_points(canvas)
                # logging.debug(f"Editable Line Move: Yeni nokta eklendi. Toplam nokta sayısı: {len(canvas.current_editable_line_points)}")
    
    canvas.update()

# Douglas-Peucker algoritması ile çizgi basitleştirme
def douglas_peucker_simplify(points: List[QPointF], epsilon: float) -> List[QPointF]:
    """Douglas-Peucker algoritması ile bir dizi noktayı basitleştirir."""
    if len(points) <= 2:
        return points
    
    # Noktalar arasındaki en uzak noktayı ve mesafeyi bul
    dmax = 0
    index = 0
    end = len(points) - 1
    
    # İlk ve son nokta arasındaki doğru için noktaların uzaklığını hesapla
    for i in range(1, end):
        d = perpendicular_distance(points[i], points[0], points[end])
        if d > dmax:
            index = i
            dmax = d
    
    # Eğer maksimum mesafe epsilon'dan büyükse, rekursif olarak basitleştir
    if dmax > epsilon:
        # Rekursif olarak alt kümeleri basitleştir
        first_part = douglas_peucker_simplify(points[:index+1], epsilon)
        second_part = douglas_peucker_simplify(points[index:], epsilon)
        
        # İlk kısmın son noktası ve ikinci kısmın ilk noktası aynı olduğu için birleştirirken 
        # ikinci kısmın ilk noktasını atlayarak birleştiriyoruz
        return first_part[:-1] + second_part
    else:
        # Sadece ilk ve son noktayı döndür
        return [points[0], points[end]]

def perpendicular_distance(point: QPointF, line_start: QPointF, line_end: QPointF) -> float:
    """Bir noktanın iki nokta arasındaki doğruya olan dikey uzaklığını hesaplar."""
    # İki nokta aynıysa, noktadan olan uzaklığı döndür
    if line_start == line_end:
        return math.sqrt((point.x() - line_start.x())**2 + (point.y() - line_start.y())**2)
    
    # Doğru üzerindeki en yakın noktayı bul
    line_length = math.sqrt((line_end.x() - line_start.x())**2 + (line_end.y() - line_start.y())**2)
    
    if line_length == 0:
        return 0
    
    # Doğru üzerindeki en yakın noktayı bulmak için vektör projeksiyonu kullan
    t = ((point.x() - line_start.x()) * (line_end.x() - line_start.x()) + 
         (point.y() - line_start.y()) * (line_end.y() - line_start.y())) / (line_length**2)
    
    # t değerini 0 ile 1 arasında sınırla (doğru parçası üzerindeki en yakın nokta)
    t = max(0, min(1, t))
    
    # Doğru üzerindeki en yakın nokta
    proj_x = line_start.x() + t * (line_end.x() - line_start.x())
    proj_y = line_start.y() + t * (line_end.y() - line_start.y())
    
    # Noktadan en yakın noktaya olan uzaklığı hesapla
    return math.sqrt((point.x() - proj_x)**2 + (point.y() - proj_y)**2)

def handle_editable_line_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi aracı için bırakma olayını yönetir."""
    if not canvas.drawing:
        return
    
    if canvas.is_dragging_bezier_handle:
        canvas.is_dragging_bezier_handle = False
        logging.debug("Editable Line Release: Bezier kontrol noktası sürükleme bitti.")
    elif canvas.active_handle_index != -1:
        logging.debug(f"Editable Line Release: Ana nokta {canvas.active_handle_index} sürükleme bitti.")
    else:
        # Son kontrol noktasını ekliyoruz (eğer gerekiyorsa)
        if len(canvas.current_editable_line_points) > 0:
            last_point = canvas.current_editable_line_points[-1]
            distance = math.sqrt((pos.x() - last_point.x())**2 + (pos.y() - last_point.y())**2)
            
            if distance >= MIN_POINT_DISTANCE:
                canvas.current_editable_line_points.append(pos)
        
        # Eğer çizimde yeterli nokta varsa
        if len(canvas.current_editable_line_points) >= 2:
            logging.debug(f"Editable Line Release: Çizim tamamlandı. Nokta sayısı: {len(canvas.current_editable_line_points)}")
            
            # Douglas-Peucker algoritması ile noktaları azalt
            if len(canvas.current_editable_line_points) > 2:
                # Önce kaç nokta var, sonra kaç nokta kaldı
                original_points_count = len(canvas.current_editable_line_points)
                canvas.current_editable_line_points = douglas_peucker_simplify(
                    canvas.current_editable_line_points, 
                    SIMPLIFICATION_EPSILON
                )
                logging.debug(f"Editable Line Release: Noktalar basitleştirildi. {original_points_count} nokta -> {len(canvas.current_editable_line_points)} nokta")
            
            # Bezier kontrol noktalarını yeniden hesapla
            update_bezier_control_points(canvas)
            
            # Çizimi kalıcı hale getir
            from utils.commands import DrawEditableLineCommand
            
            # Bezier kontrol noktalarını canvas'tan al
            control_points = canvas.bezier_control_points
            
            # DrawEditableLineCommand'ı oluştur ve uygula
            command = DrawEditableLineCommand(
                canvas,
                control_points,
                canvas.current_color,
                canvas.current_pen_width,
                canvas.line_style
            )
            
            canvas.undo_manager.execute(command)
            
            # Parent page'i modified olarak işaretle ve content_changed sinyalini gönder
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            if hasattr(canvas, 'content_changed'):
                canvas.content_changed.emit()
            
            # Çizimden sonra yeni çizim için değişkenleri sıfırla
            canvas.current_editable_line_points = []
            canvas.active_handle_index = -1
            canvas.active_bezier_handle_index = -1
            canvas.is_dragging_bezier_handle = False
            canvas.bezier_control_points = []
            
            logging.debug("Editable Line Release: Bezier eğrisi kalıcı olarak kaydedildi.")
        else:
            logging.debug("Editable Line Release: Yeterli nokta yok, çizim kaydedilmedi.")
    
    # Çizimi bitir
    canvas.drawing = False
    canvas.update()

# --- YENİ: Düzenlenebilir Çizgi Editörü İçin Fonksiyonlar --- #

def handle_editable_line_editor_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi düzenleme aracı için basma olayını yönetir."""
    logging.debug("Editable Line Editor Press: Checking for existing lines or handles")
    
    # Tutamaçlara bakmadan önce, seçili bir düzenlenebilir çizgi var mı kontrol et
    if not canvas.selected_item_indices:
        # Tıklanan noktada bir düzenlenebilir çizgi olup olmadığını kontrol et
        item_at_click = canvas._get_item_at(pos)
        if item_at_click and item_at_click[0] == 'shapes':
            shape_index = item_at_click[1]
            if 0 <= shape_index < len(canvas.shapes):
                shape_data = canvas.shapes[shape_index]
                if shape_data[0] == ToolType.EDITABLE_LINE:
                    # Düzenlenebilir çizgiyi seç
                    canvas.selected_item_indices = [('shapes', shape_index)]
                    canvas.update()
                    logging.debug(f"Editable Line Editor: Çizgi {shape_index} seçildi")
        
    # Seçili çizgi var mı kontrol et
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                control_points = shape_data[3]
                
                # İlk olarak tutamaçları kontrol et
                for handle_type, handle_rect in canvas.current_handles.items():
                    if handle_rect.contains(canvas.world_to_screen(pos)):
                        # Tutamaç türünü belirle
                        if handle_type.startswith('main_'):
                            idx = int(handle_type.split('_')[1])
                            canvas.active_handle_index = idx
                            canvas.is_dragging_bezier_handle = False
                            logging.debug(f"Editable Line Editor: Ana nokta {idx} seçildi")
                        elif handle_type.startswith('control1_') or handle_type.startswith('control2_'):
                            idx = int(handle_type.split('_')[1])
                            canvas.active_bezier_handle_index = idx
                            canvas.is_dragging_bezier_handle = True
                            logging.debug(f"Editable Line Editor: Bezier kontrol noktası {idx} seçildi")
                        
                        # Orijinal kontrol noktaları durumunu sakla (geri alma işlemi için)
                        canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
                        canvas.drawing = True
                        return
    
    # Hiçbir şey seçilmediyse veya seçili değilse, mevcut tutamaçları temizle
    canvas.active_handle_index = -1
    canvas.active_bezier_handle_index = -1
    canvas.is_dragging_bezier_handle = False
    canvas.selected_item_indices = []
    canvas.current_handles.clear()
    canvas.update()

def handle_editable_line_editor_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi düzenleme aracı için hareket olayını yönetir."""
    if not canvas.drawing:
        return
    
    # Seçili çizgi var mı kontrol et
    if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
        item_type, index = canvas.selected_item_indices[0]
        if item_type == 'shapes' and 0 <= index < len(canvas.shapes):
            shape_data = canvas.shapes[index]
            if shape_data[0] == ToolType.EDITABLE_LINE:
                control_points = shape_data[3]
                
                # Kontrol noktası taşınıyor
                if canvas.is_dragging_bezier_handle and canvas.active_bezier_handle_index != -1:
                    if 0 <= canvas.active_bezier_handle_index < len(control_points):
                        control_points[canvas.active_bezier_handle_index] = pos
                        logging.debug(f"Editable Line Editor Move: Bezier kontrol noktası {canvas.active_bezier_handle_index} güncellendi")
                # Ana nokta taşınıyor
                elif canvas.active_handle_index != -1:
                    if 0 <= canvas.active_handle_index < len(control_points):
                        control_points[canvas.active_handle_index * 3] = pos
                        
                        # Komşu kontrol noktalarını da güncelle
                        if canvas.active_handle_index > 0:
                            # Önceki kontrol noktası
                            prev_idx = canvas.active_handle_index * 3 - 1
                            if 0 <= prev_idx < len(control_points):
                                control_points[prev_idx] = pos - (control_points[canvas.active_handle_index * 3 - 2] - control_points[prev_idx])
                        
                        if canvas.active_handle_index < (len(control_points) - 1) // 3:
                            # Sonraki kontrol noktası
                            next_idx = canvas.active_handle_index * 3 + 1
                            if 0 <= next_idx < len(control_points):
                                control_points[next_idx] = pos + (control_points[next_idx] - control_points[canvas.active_handle_index * 3])
                        
                        logging.debug(f"Editable Line Editor Move: Ana nokta {canvas.active_handle_index} güncellendi")
    
    canvas.update()

def handle_editable_line_editor_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Düzenlenebilir çizgi düzenleme aracı için bırakma olayını yönetir."""
    if not canvas.drawing:
        return
    
    # Seçili çizgi var mı kontrol et
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
    
    # Taşıma durumunu sıfırla
    canvas.is_dragging_bezier_handle = False
    canvas.active_bezier_handle_index = -1
    canvas.active_handle_index = -1
    canvas.drawing = False
    canvas.original_resize_states = []
    canvas.update()

# --- --- --- --- --- --- --- --- --- --- --- # 
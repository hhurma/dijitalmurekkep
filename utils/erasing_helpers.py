"""Silgi aracıyla ilgili yardımcı fonksiyonlar."""

import logging
from typing import TYPE_CHECKING, List, Tuple, Any, Dict
from PyQt6.QtCore import QPointF, QRectF
import copy # Deepcopy için

# Döngüsel importu önlemek için Type Hinting
if TYPE_CHECKING:
    from gui.drawing_canvas import DrawingCanvas
    # utils içinden importları fonksiyon içinde yapacağız

# Sabitler
# LINE_ERASE_THRESHOLD = 0.7 # Kaldırıldı

# Type definitions for clarity
# Değişiklikleri temsil edecek yeni format
# {'lines': {index1: {'original_points': [...], 'final_points': [...]}, index2: ...},
#  'shapes': [index1, index2, ...]} # Şekiller şimdilik tam siliniyor
EraseChanges = Dict[str, Any]

def erase_at_position(canvas: 'DrawingCanvas', position: QPointF, eraser_width: float):
    """Belirtilen pozisyonda silgiyi uygular.

    Args:
        canvas: DrawingCanvas örneği
        position: Silginin uygulanacağı dünya koordinatı
        eraser_width: Silginin genişliği
    """
    from utils.commands import EraseCommand
    
    # Silgi yolu olarak sadece tek bir nokta koy
    erase_path = [position]
    
    # Silgi değişikliklerini hesapla
    changes = calculate_erase_changes(canvas.lines, canvas.shapes, getattr(canvas, 'b_spline_strokes', []), erase_path, eraser_width)
    
    if changes['lines'] or changes['shapes'] or changes['b_spline_strokes']:
        # Silme komutu oluştur
        command = EraseCommand(canvas, changes)
        
        # Komutu uygula
        canvas.undo_manager.execute(command)
        
        # Canvas'ı güncelle
        canvas.update()
        
        # İçerik değişti sinyalini gönder (eğer varsa)
        if hasattr(canvas, 'content_changed'):
            canvas.content_changed.emit()
            
        # Eğer bir sayfaya bağlıysa, sayfayı değişmiş olarak işaretle
        if canvas._parent_page:
            canvas._parent_page.mark_as_modified()
            
        return True
    
    return False

def _get_eraser_bounding_rect(path: List[QPointF], width: float) -> QRectF:
    """Silgi yolunun sınırlayıcı dikdörtgenini hesaplar."""
    if not path:
        return QRectF()
    min_x = min(p.x() for p in path) - width / 2
    min_y = min(p.y() for p in path) - width / 2
    max_x = max(p.x() for p in path) + width / 2
    max_y = max(p.y() for p in path) + width / 2
    return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))

def _erase_points_from_line(line_points: List[QPointF], erase_path: List[QPointF], eraser_width: float) -> Tuple[List[QPointF], bool]:
    """Bir çizginin noktalarından, silgi yolu ve genişliğine göre silinmesi gerekenleri çıkarır.

    Args:
        line_points: Güncellenecek çizgi nokta listesi (yerinde değiştirilebilir).
        erase_path: Silginin geçtiği noktaların listesi.
        eraser_width: Silginin genişliği.

    Returns:
        Tuple[List[QPointF], bool]: (Potansiyel olarak değiştirilmiş nokta listesi, Nokta silinip silinmediği)
    """
    from utils import geometry_helpers

    if not line_points or not erase_path:
        return line_points, False

    points_to_remove_indices = set()
    eraser_radius_sq = (eraser_width / 2.0) ** 2

    if len(erase_path) == 1:
        # Silgi yolu tek nokta ise, her çizgi noktasının bu noktaya uzaklığını kontrol et
        erase_point = erase_path[0]
        for j, point in enumerate(line_points):
            dist_sq = (point.x() - erase_point.x()) ** 2 + (point.y() - erase_point.y()) ** 2
            if dist_sq < eraser_radius_sq:
                points_to_remove_indices.add(j)
    else:
        # Silgi yolu segment ise, mevcut mantıkla devam et
        for i in range(len(erase_path) - 1):
            p1_erase = erase_path[i]
            p2_erase = erase_path[i+1]
            for j, point in enumerate(line_points):
                if j in points_to_remove_indices:
                    continue
                dist_sq = geometry_helpers.point_segment_distance_sq(point, p1_erase, p2_erase)
                if dist_sq < eraser_radius_sq:
                    points_to_remove_indices.add(j)

    if not points_to_remove_indices:
        return line_points, False

    final_points = [p for i, p in enumerate(line_points) if i not in points_to_remove_indices]
    logging.debug(f"Erasing points check: Original count={len(line_points)}, To remove count={len(points_to_remove_indices)}, Final count={len(final_points)}")
    return final_points, True


def calculate_erase_changes(lines: List[List[Any]], shapes: List[List[Any]], b_spline_strokes: List[dict], erase_path: List[QPointF], eraser_width: float) -> EraseChanges:
    """Silgi yolu boyunca silinecek çizgi NOKTALARINI, şekillerin ve B-Spline'ların TAMAMINI HESAPLAR.
    
    Canvas verisini DEĞİŞTİRMEZ.
    Yapılacak değişiklikleri bir 'changes' sözlüğü olarak DÖNDÜRÜR.
    changes = {
        'lines': {index: {'original_points': [...], 'final_points': [...]}},
        'shapes': {index: original_data},
        'b_spline_strokes': {index: original_data} # YENİ
    }
    """
    from utils import geometry_helpers # Helperları burada import et
    from gui.enums import ToolType  # ToolType'a erişim için import eklendi

    logging.debug("[DEBUG] calculate_erase_changes çağrıldı")
    logging.debug(f"[DEBUG] SHAPES: {len(shapes)} öğe mevcut")
    for i, s in enumerate(shapes):
        if s and len(s) > 0:
            if isinstance(s[0], ToolType):
                logging.debug(f"[DEBUG] SHAPE[{i}]: type={s[0].name}, color={s[1]}, width={s[2]}")
            else:
                logging.debug(f"[DEBUG] SHAPE[{i}]: type={s[0]}, color={s[1]}, width={s[2]}")

    changes: EraseChanges = {'lines': {}, 'shapes': {}, 'b_spline_strokes': {}}

    if not erase_path or len(erase_path) < 1:
        return changes # Değişiklik yok

    eraser_rect = _get_eraser_bounding_rect(erase_path, eraser_width)
    logging.debug(f"[Eraser] Eraser Rect: {eraser_rect}")

    # 1. Lines (Nokta Bazlı Silme Hesaplaması)
    lines_to_delete = []
    for i, line_data in enumerate(lines):
        # BBox hesapla
        bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        logging.debug(f"[Eraser-Line {i}] BBox={bbox}")
        # Silgi ile kesişiyor mu?
        if not bbox.isNull() and eraser_rect.intersects(bbox):
            logging.debug(f"[Eraser-Line {i}] Kesişim tespit edildi, silme değerlendirilecek")
            lines_to_delete.append(i)

    for i in lines_to_delete:
        current_points = lines[i][2]
        final_points, points_were_erased = _erase_points_from_line(current_points, erase_path, eraser_width)

        if points_were_erased:
            logging.debug(f"Line {i} intersects with erase path. Marking for complete deletion.")
            final_points = [] 

            changes['lines'][i] = {
                'original_points': copy.deepcopy(current_points),
                'original_color': lines[i][0],
                'original_width': lines[i][1],
                'final_points': final_points
            }

    # 2. Shapes (Tamamen Silinecekleri Hesapla)
    for i, shape_data in enumerate(shapes):
        if not shape_data or len(shape_data) < 3:
            logging.debug(f"[Eraser-Shape {i}] Geçersiz shape verisi, atlanıyor")
            continue
            
        # PATH türü shape'ler için özel kontrol
        if isinstance(shape_data[0], ToolType) and shape_data[0] == ToolType.PATH:
            logging.debug(f"[Eraser-Shape {i}] PATH tipi şekil tespit edildi")
            
            # PATH için points verisini doğru indeksten al
            path_points = None
            if len(shape_data) > 3 and isinstance(shape_data[3], list):
                path_points = shape_data[3]
                logging.debug(f"[Eraser-Shape {i}] PATH points verisi bulundu: {len(path_points)} nokta")
            else:
                logging.debug(f"[Eraser-Shape {i}] PATH için points verisi doğru formatta değil")
                continue
                
            if not path_points or len(path_points) < 2:
                logging.debug(f"[Eraser-Shape {i}] PATH noktaları yetersiz, atlanıyor")
                continue
                
            # Noktalardan sınırlayıcı kutu oluştur
            min_x = min(p.x() for p in path_points)
            min_y = min(p.y() for p in path_points)
            max_x = max(p.x() for p in path_points)
            max_y = max(p.y() for p in path_points)
            path_rect = QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
            
            logging.debug(f"[Eraser-Shape {i}] PATH sınırlayıcı kutusu: {path_rect}")
            
            # Kesişim kontrolü
            if not path_rect.isNull() and eraser_rect.intersects(path_rect):
                logging.debug(f"[Eraser-Shape {i}] PATH silgi ile kesişiyor, silinecek!")
                changes['shapes'][i] = copy.deepcopy(shape_data)
        else:
            # Normal şekiller için mevcut mantığı kullan
            shape_rect = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
            
            if isinstance(shape_data[0], ToolType):
                shape_type_name = shape_data[0].name
            else:
                shape_type_name = str(shape_data[0])
                
            logging.debug(f"[Eraser-Shape {i}] Type={shape_type_name}, BBox={shape_rect}")
            
            # Kesişim kontrolü
            if not shape_rect.isNull() and eraser_rect.intersects(shape_rect):
                logging.debug(f"[Eraser-Shape {i}] {shape_type_name} silgi ile kesişiyor, silinecek!")
                changes['shapes'][i] = copy.deepcopy(shape_data)

    # 3. B-Spline Strokes
    for i, spline_data in enumerate(b_spline_strokes):
        spline_rect = geometry_helpers.get_bspline_bounding_box(spline_data)
        
        if not spline_rect.isNull() and eraser_rect.intersects(spline_rect):
            logging.debug(f"[Eraser-BSpline {i}] BSpline silgi ile kesişiyor, silinecek!")
            changes['b_spline_strokes'][i] = copy.deepcopy(spline_data)

    logging.debug(f"[Eraser] Sonuç: {len(changes['lines'])} çizgi, {len(changes['shapes'])} şekil, {len(changes['b_spline_strokes'])} B-Spline silinecek")
    return changes

# Eski erase_items_along_path fonksiyonunu kaldırabiliriz veya yorumda bırakabiliriz.
# def erase_items_along_path(canvas: 'DrawingCanvas', changes: EraseChanges):
#    ... (eski kod) ... 
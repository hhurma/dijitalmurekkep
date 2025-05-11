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
    from utils import geometry_helpers # Helper'ı burada import et

    if not line_points or not erase_path:
        return line_points, False # Değişiklik yok

    points_to_remove_indices = set()
    eraser_radius_sq = (eraser_width / 2.0) ** 2

    # Silgi yolu boyunca her segmenti kontrol et
    for i in range(len(erase_path) - 1):
        p1_erase = erase_path[i]
        p2_erase = erase_path[i+1]

        # Çizgi noktalarını kontrol et
        for j, point in enumerate(line_points):
            if j in points_to_remove_indices:
                continue # Zaten silinecek

            # Noktanın silgi segmentine olan uzaklığının karesini hesapla
            dist_sq = geometry_helpers.point_segment_distance_sq(point, p1_erase, p2_erase)

            if dist_sq < eraser_radius_sq:
                points_to_remove_indices.add(j)

    # Silinecek nokta yoksa orijinal listeyi döndür
    if not points_to_remove_indices:
        return line_points, False

    # Silinecek noktaları çıkararak YENİ bir liste oluştur (orijinali değiştirmeyelim)
    final_points = [p for i, p in enumerate(line_points) if i not in points_to_remove_indices]

    logging.debug(f"Erasing points check: Original count={len(line_points)}, To remove count={len(points_to_remove_indices)}, Final count={len(final_points)}")

    # Yeni listeyi ve değişiklik olduğunu döndür
    return final_points, True


def calculate_erase_changes(lines: List[List[Any]], shapes: List[List[Any]], erase_path: List[QPointF], eraser_width: float) -> EraseChanges:
    """Silgi yolu boyunca silinecek çizgi NOKTALARINI ve şekillerin TAMAMINI HESAPLAR.
    
    Canvas verisini DEĞİŞTİRMEZ.
    Yapılacak değişiklikleri bir 'changes' sözlüğü olarak DÖNDÜRÜR.
    changes = {'lines': {index: {'original_points': [...], 'final_points': [...]}}, 'shapes': {index: original_data}}
    """
    from utils import geometry_helpers # Helperları burada import et

    changes: EraseChanges = {'lines': {}, 'shapes': {}}

    if not erase_path or len(erase_path) < 1:
        return changes # Değişiklik yok

    eraser_rect = _get_eraser_bounding_rect(erase_path, eraser_width)
    logging.debug(f"[Eraser] Eraser Rect: {eraser_rect}") # Eraser rect logu

    # 1. Lines (Nokta Bazlı Silme Hesaplaması)
    for i, line_data in enumerate(lines):
        line_rect = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        
        qt_intersects = False
        manual_intersects = False
        if not line_rect.isNull():
            qt_intersects = eraser_rect.intersects(line_rect)
            # Manuel kesişim kontrolü
            er_left, er_right, er_top, er_bottom = eraser_rect.left(), eraser_rect.right(), eraser_rect.top(), eraser_rect.bottom()
            lr_left, lr_right, lr_top, lr_bottom = line_rect.left(), line_rect.right(), line_rect.top(), line_rect.bottom()
            x_overlap = (lr_left <= er_right) and (lr_right >= er_left)
            y_overlap = (lr_top <= er_bottom) and (lr_bottom >= er_top)
            manual_intersects = x_overlap and y_overlap

        logging.debug(f"  [Eraser-Line {i}] BBox={line_rect}, QtIntersects={qt_intersects}, ManualIntersects={manual_intersects}")

        # if line_rect.isNull() or not eraser_rect.intersects(line_rect): # ESKİ KONTROL
        if line_rect.isNull() or not manual_intersects: # YENİ KONTROL (Manuel kesişime göre)
            continue # Kesişmiyorsa atla
        
        current_points = line_data[2]
        final_points, points_were_erased = _erase_points_from_line(current_points, erase_path, eraser_width)

        if points_were_erased:
            # Eşik kontrolü kaldırıldı. Eğer herhangi bir nokta silindiyse, çizgiyi tamamen sil.
            logging.debug(f"Line {i} intersects with erase path. Marking for complete deletion.")
            final_points = [] # Tamamen silinecek olarak işaretle

            changes['lines'][i] = {
                'original_points': copy.deepcopy(current_points), # Orijinali sakla
                'original_color': line_data[0], # Geri alma için renk/kalınlık
                'original_width': line_data[1],
                'final_points': final_points # Yeni (potansiyel olarak boş) liste
            }

    # 2. Shapes (Tamamen Silinecekleri Hesapla)
    for i, shape_data in enumerate(shapes):
        shape_rect = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        
        qt_intersects_shape = False
        manual_intersects_shape = False
        if not shape_rect.isNull():
            qt_intersects_shape = eraser_rect.intersects(shape_rect)
            # Manuel kesişim kontrolü
            er_left, er_right, er_top, er_bottom = eraser_rect.left(), eraser_rect.right(), eraser_rect.top(), eraser_rect.bottom()
            sr_left, sr_right, sr_top, sr_bottom = shape_rect.left(), shape_rect.right(), shape_rect.top(), shape_rect.bottom()
            x_overlap_shape = (sr_left <= er_right) and (sr_right >= er_left)
            y_overlap_shape = (sr_top <= er_bottom) and (sr_bottom >= er_top)
            manual_intersects_shape = x_overlap_shape and y_overlap_shape

        logging.debug(f"  [Eraser-Shape {i}] Type={shape_data[0]}, BBox={shape_rect}, QtIntersects={qt_intersects_shape}, ManualIntersects={manual_intersects_shape}")

        # if not shape_rect.isNull() and eraser_rect.intersects(shape_rect): # ESKİ KONTROL
        if not shape_rect.isNull() and manual_intersects_shape: # YENİ KONTROL (Manuel kesişime göre)
            # Bu şekil silinecek, orijinal verisini kaydet
            changes['shapes'][i] = copy.deepcopy(shape_data)

    return changes

# Eski erase_items_along_path fonksiyonunu kaldırabiliriz veya yorumda bırakabiliriz.
# def erase_items_along_path(canvas: 'DrawingCanvas', changes: EraseChanges):
#    ... (eski kod) ... 
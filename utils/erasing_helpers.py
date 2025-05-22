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

def erase_at_position(canvas: 'DrawingCanvas', erase_path: List[QPointF], eraser_width: float):
    """Belirtilen silgi yolu boyunca silgiyi uygular.

    Args:
        canvas: DrawingCanvas örneği
        erase_path: Silgi yolunu oluşturan noktaların listesi (en az 1 nokta)
        eraser_width: Silginin genişliği
    """
    from utils.commands import EraseCommand
    
    if not erase_path or len(erase_path) < 1:
        return False
    
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
    #logging.debug(f"Erasing points check: Original count={len(line_points)}, To remove count={len(points_to_remove_indices)}, Final count={len(final_points)}")
    return final_points, True


def calculate_erase_changes(lines: List[List[Any]], shapes: List[List[Any]], b_spline_strokes: List[dict], erase_path: List[QPointF], eraser_width: float) -> EraseChanges:
    """Silgi yolu boyunca silinecek çizgi NOKTALARINI, şekillerin ve B-Spline'ların TAMAMINI HESAPLAR.
    Sadece silgi yolunun toplam bounding box'ı ile kesişen öğeler kontrol edilir (en hızlı yöntem).
    """
    from utils import geometry_helpers # Helperları burada import et
    from gui.enums import ToolType  # ToolType'a erişim için import eklendi

    changes: EraseChanges = {'lines': {}, 'shapes': {}, 'b_spline_strokes': {}}

    if not erase_path or len(erase_path) < 1:
        return changes # Değişiklik yok

    eraser_rect = _get_eraser_bounding_rect(erase_path, eraser_width)

    # 1. Lines (Nokta Bazlı Silme Hesaplaması)
    for i, line_data in enumerate(lines):
        bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        if bbox.isNull() or not eraser_rect.intersects(bbox):
            continue
        current_points = line_data[2]
        final_points, points_were_erased = _erase_points_from_line(current_points, erase_path, eraser_width)
        if points_were_erased:
            final_points = []
            changes['lines'][i] = {
                'original_points': copy.deepcopy(current_points),
                'original_color': line_data[0],
                'original_width': line_data[1],
                'final_points': final_points
            }

    # 2. Shapes (Tamamen Silinecekleri Hesapla)
    for i, shape_data in enumerate(shapes):
        if not shape_data or len(shape_data) < 3:
            continue
        if isinstance(shape_data[0], ToolType) and shape_data[0] == ToolType.PATH:
            path_points = shape_data[3] if len(shape_data) > 3 and isinstance(shape_data[3], list) else None
            if not path_points or len(path_points) < 2:
                continue
            min_x = min(p.x() for p in path_points)
            min_y = min(p.y() for p in path_points)
            max_x = max(p.x() for p in path_points)
            max_y = max(p.y() for p in path_points)
            path_rect = QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
            if path_rect.isNull() or not eraser_rect.intersects(path_rect):
                continue
            changes['shapes'][i] = copy.deepcopy(shape_data)
        else:
            shape_rect = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
            if shape_rect.isNull() or not eraser_rect.intersects(shape_rect):
                continue
            changes['shapes'][i] = copy.deepcopy(shape_data)

    # 3. B-Spline Strokes
    for i, spline_data in enumerate(b_spline_strokes):
        spline_rect = geometry_helpers.get_bspline_bounding_box(spline_data)
        if spline_rect.isNull() or not eraser_rect.intersects(spline_rect):
            continue
        changes['b_spline_strokes'][i] = copy.deepcopy(spline_data)

    return changes

# Eski erase_items_along_path fonksiyonunu kaldırabiliriz veya yorumda bırakabiliriz.
# def erase_items_along_path(canvas: 'DrawingCanvas', changes: EraseChanges):
#    ... (eski kod) ... 
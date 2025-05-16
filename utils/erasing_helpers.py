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

    print("[DEBUG] LINES LİSTESİ:")
    for i, l in enumerate(lines):
        print(f"[DEBUG] LINES[{i}]: color={l[0]}, width={l[1]}, points={l[2] if len(l)>2 else None}")

    changes: EraseChanges = {'lines': {}, 'shapes': {}, 'b_spline_strokes': {}} # YENİ

    if not erase_path or len(erase_path) < 1:
        return changes # Değişiklik yok

    eraser_rect = _get_eraser_bounding_rect(erase_path, eraser_width)
    logging.debug(f"[Eraser] Eraser Rect: {eraser_rect}")

    # 1. Lines (Nokta Bazlı Silme Hesaplaması)
    lines_to_delete = []
    for i, line_data in enumerate(lines):
        # BBox hesapla
        bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        print(f"[DEBUG] LINE {i}: bbox={bbox}")
        # Silgi ile kesişiyor mu?
        if not bbox.isNull() and eraser_rect.intersects(bbox):
            print(f"[DEBUG] LINE {i} siliniyor!")
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
        shape_rect = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        print(f"[DEBUG] SHAPE {i}: type={shape_data[0]}, bbox={shape_rect}")
        
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

        print(f"[DEBUG] SHAPE {i}: type={shape_data[0]}, qt_intersects={qt_intersects_shape}, manual_intersects={manual_intersects_shape}")

        if not shape_rect.isNull() and manual_intersects_shape: 
            print(f"[DEBUG] SHAPE {i} SİLİNECEK! type={shape_data[0]}")
            changes['shapes'][i] = copy.deepcopy(shape_data)

    # 3. B-Spline Strokes (Tamamen Silinecekleri Hesapla) # YENİ BÖLÜM
    for i, spline_data in enumerate(b_spline_strokes):
        spline_rect = geometry_helpers.get_bspline_bounding_box(spline_data) # B-Spline için özel bbox fonksiyonu
        
        qt_intersects_spline = False
        manual_intersects_spline = False
        if not spline_rect.isNull():
            qt_intersects_spline = eraser_rect.intersects(spline_rect)
            # Manuel kesişim kontrolü (yukarıdakilere benzer şekilde)
            er_left, er_right, er_top, er_bottom = eraser_rect.left(), eraser_rect.right(), eraser_rect.top(), eraser_rect.bottom()
            spl_left, spl_right, spl_top, spl_bottom = spline_rect.left(), spline_rect.right(), spline_rect.top(), spline_rect.bottom()
            x_overlap_spline = (spl_left <= er_right) and (spl_right >= er_left)
            y_overlap_spline = (spl_top <= er_bottom) and (spl_bottom >= er_top)
            manual_intersects_spline = x_overlap_spline and y_overlap_spline

        logging.debug(f"  [Eraser-BSpline {i}] BBox={spline_rect}, QtIntersects={qt_intersects_spline}, ManualIntersects={manual_intersects_spline}")

        if not spline_rect.isNull() and manual_intersects_spline:
            changes['b_spline_strokes'][i] = copy.deepcopy(spline_data)

    return changes

# Eski erase_items_along_path fonksiyonunu kaldırabiliriz veya yorumda bırakabiliriz.
# def erase_items_along_path(canvas: 'DrawingCanvas', changes: EraseChanges):
#    ... (eski kod) ... 
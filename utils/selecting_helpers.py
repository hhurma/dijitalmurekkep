# utils/selecting_helpers.py
"""Çizim nesnelerini seçme ile ilgili yardımcı fonksiyonlar."""
import logging
from typing import List, Tuple, Any, Optional
# Import geometry helpers and necessary Qt classes
from . import geometry_helpers
from PyQt6.QtCore import QPointF, QRectF

# Gerekli importlar (örn. QPointF, QRectF) ve fonksiyonlar buraya eklenecek

def select_item_at(point: QPointF, lines: List[Any], shapes: List[Any], tolerance: float = 5.0) -> Optional[Tuple[str, int]]:
    """Belirtilen noktadaki en üstteki çizim öğesini bulur ve referansını döndürür."""
    # logging.warning("select_item_at henüz implemente edilmedi.")
    # Şekilleri önce kontrol et (genellikle üstte olurlar)
    # Iterate in reverse to select the topmost item first
    for i in range(len(shapes) - 1, -1, -1):
        shape_data = shapes[i]
        bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        if bbox.contains(point):
            # Şekiller için bbox yeterli (şimdilik)
            logging.debug(f"Item found at point (shape): {('shapes', i)}")
            return ('shapes', i)

    # Sonra çizgileri kontrol et
    for i in range(len(lines) - 1, -1, -1):
        line_data = lines[i]
        line_width = line_data[1] if len(line_data) > 1 else 2.0 # Default width if not found
        bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        # Genişletilmiş tolerans: temel tolerans + çizgi kalınlığının yarısı
        effective_tolerance = tolerance + line_width / 2.0
        # Önce bbox kontrolü (hızlı eleme)
        # Tolerans kadar genişletilmiş bbox kontrolü
        expanded_bbox = bbox.adjusted(-effective_tolerance, -effective_tolerance, effective_tolerance, effective_tolerance)
        if expanded_bbox.contains(point):
            # Bbox içindeyse hassas kontrol yap
            points = line_data[2] if len(line_data) > 2 else []
            for j in range(len(points) - 1):
                if geometry_helpers.is_point_on_line(point, points[j], points[j+1], effective_tolerance):
                    logging.debug(f"Item found at point (line): {('lines', i)}")
                    return ('lines', i)

    logging.debug("No item found at point.")
    return None # Seçilen nesne yoksa

def select_items_in_rect(rect: QRectF, lines: List[Any], shapes: List[Any]) -> List[Tuple[str, int]]:
    """Belirtilen dikdörtgen alan içindeki veya kesişen tüm çizim öğelerini seçer."""
    # logging.warning("select_items_in_rect henüz implemente edilmedi.")
    selected_indices: List[Tuple[str, int]] = []

    for i, line_data in enumerate(lines):
        bbox = geometry_helpers.get_item_bounding_box(line_data, 'lines')
        # Dikdörtgenler kesişiyorsa veya biri diğerini içeriyorsa seç
        if not bbox.isNull() and rect.intersects(bbox):
            selected_indices.append(('lines', i))

    for i, shape_data in enumerate(shapes):
        bbox = geometry_helpers.get_item_bounding_box(shape_data, 'shapes')
        if not bbox.isNull() and rect.intersects(bbox):
             selected_indices.append(('shapes', i))

    logging.debug(f"Items selected in rect {rect.topLeft()}-{rect.bottomRight()}: {selected_indices}")
    return selected_indices 
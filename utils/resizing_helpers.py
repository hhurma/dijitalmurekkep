# utils/resizing_helpers.py
"""Seçili öğeleri yeniden boyutlandırma ile ilgili yardımcı fonksiyonlar."""
import logging
from typing import List, Any
from PyQt6.QtCore import QPointF, QRectF, qFuzzyCompare
from gui.enums import ToolType
from . import geometry_helpers # geometry_helpers'ı import et

# Type definitions for clarity
LineDataType = List[Any]
ShapeDataType = List[Any]

MIN_SIZE = 5.0 # Yeniden boyutlandırmada izin verilen minimum genişlik/yükseklik

# --- YENİ resize_item Fonksiyonu (Artımlı Delta ile) ---
def resize_item(item_data: List[Any], handle_type: str, incremental_delta: QPointF):
    """Verilen öğeyi (şekil veya çizgi) tutamaca göre artımlı olarak yeniden boyutlandırır."""
    # Loglama Ekle
    logging.debug(f"--- resize_item (incremental) --- Handle: {handle_type}, Delta: {incremental_delta}")
    if not item_data or incremental_delta.isNull():
        return

    is_shape = isinstance(item_data[0], ToolType) and len(item_data) >= 5 and isinstance(item_data[3], QPointF)
    is_line = not is_shape and len(item_data) >= 3 and isinstance(item_data[2], list) and item_data[2]

    if not is_shape and not is_line:
        logging.warning(f"resize_item: Invalid item_data format or empty line points: {item_data}")
        return

    try:
        if is_shape:
            tool_type: ToolType = item_data[0]
            if tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                p1: QPointF = item_data[3]
                p2: QPointF = item_data[4]
                
                # Yeni p1, p2'yi mevcut olana göre başlat
                new_p1 = QPointF(p1)
                new_p2 = QPointF(p2)

                # Tutamaç tipine göre hangi noktanın/koordinatın değişeceğini belirle
                # ve incremental_delta'yı uygula.
                left_edge_p = new_p1 if qFuzzyCompare(p1.x(), min(p1.x(), p2.x())) else new_p2
                right_edge_p = new_p1 if qFuzzyCompare(p1.x(), max(p1.x(), p2.x())) else new_p2
                top_edge_p = new_p1 if qFuzzyCompare(p1.y(), min(p1.y(), p2.y())) else new_p2
                bottom_edge_p = new_p1 if qFuzzyCompare(p1.y(), max(p1.y(), p2.y())) else new_p2

                if 'left' in handle_type:
                    left_edge_p.setX(left_edge_p.x() + incremental_delta.x())
                elif 'right' in handle_type:
                    right_edge_p.setX(right_edge_p.x() + incremental_delta.x())
                
                if 'top' in handle_type:
                    top_edge_p.setY(top_edge_p.y() + incremental_delta.y())
                elif 'bottom' in handle_type:
                    bottom_edge_p.setY(bottom_edge_p.y() + incremental_delta.y())

                # Loglama Ekle
                logging.debug(f"  Calculated new potential points: p1={new_p1}, p2={new_p2}")

                # Minimum boyut kontrolü
                temp_bbox = QRectF(new_p1, new_p2).normalized()
                valid_resize = True
                
                original_p1 = QPointF(p1) # Minimum boyut kontrolü için orijinali sakla
                original_p2 = QPointF(p2)

                if temp_bbox.width() < MIN_SIZE:
                    valid_resize = False
                    logging.debug(f"  Resize invalid: Width {temp_bbox.width()} < {MIN_SIZE}")
                    # Hangi x koordinatını geri yüklemeli? Delta'nın yönüne göre.
                    if incremental_delta.x() != 0:
                        if 'left' in handle_type:
                            left_edge_p.setX(original_p1.x() if left_edge_p == new_p1 else original_p2.x())
                        elif 'right' in handle_type:
                            right_edge_p.setX(original_p1.x() if right_edge_p == new_p1 else original_p2.x())
                        
                if temp_bbox.height() < MIN_SIZE:
                     valid_resize = False
                     logging.debug(f"  Resize invalid: Height {temp_bbox.height()} < {MIN_SIZE}")
                     if incremental_delta.y() != 0:
                         if 'top' in handle_type:
                             top_edge_p.setY(original_p1.y() if top_edge_p == new_p1 else original_p2.y())
                         elif 'bottom' in handle_type:
                             bottom_edge_p.setY(original_p1.y() if bottom_edge_p == new_p1 else original_p2.y())
                
                # Geri yüklemeler sonrası son p1,p2'yi al
                final_p1 = QPointF(left_edge_p if left_edge_p == new_p1 else right_edge_p)
                final_p2 = QPointF(top_edge_p if top_edge_p == new_p2 else bottom_edge_p)

                # Loglama Ekle
                logging.debug(f"  Minimum size check passed: {valid_resize}")

                # Yeni noktaları ata (minimum boyut kontrolü sonrası)
                item_data[3] = final_p1
                item_data[4] = final_p2
                logging.debug(f"  >>> Applied resize. New data p1: {item_data[3]}, p2: {item_data[4]}") # Loglama Ekle

            else:
                 logging.debug(f"resize_item (incremental): {tool_type.name} resizing not supported.")

        elif is_line:
            logging.debug("--- Starting incremental resize for LINE ---")
            points: List[QPointF] = item_data[2]
            if not points:
                logging.warning("Cannot resize line with no points.")
                return

            # 1. Mevcut bounding box'ı al
            current_bbox = geometry_helpers.get_item_bounding_box(item_data, 'lines')
            if current_bbox.isNull() or current_bbox.width() < 1e-6 or current_bbox.height() < 1e-6:
                logging.warning(f"Cannot resize line with invalid bbox: {current_bbox}")
                return
            
            logging.debug(f"  Current line bbox: {current_bbox}")

            # 2. Yeni bounding box'ı hesapla (tutamaç ve deltaya göre)
            # Önceki şekil mantığına benzer şekilde, bbox'ın kenarlarını hareket ettir
            new_bbox_rect = QRectF(current_bbox) # Kopyala

            if 'left' in handle_type:
                new_bbox_rect.setLeft(current_bbox.left() + incremental_delta.x())
            elif 'right' in handle_type:
                new_bbox_rect.setRight(current_bbox.right() + incremental_delta.x())
            
            if 'top' in handle_type:
                new_bbox_rect.setTop(current_bbox.top() + incremental_delta.y())
            elif 'bottom' in handle_type:
                new_bbox_rect.setBottom(current_bbox.bottom() + incremental_delta.y())
            
            # Normalize et (genişlik/yükseklik negatif olabilir)
            new_bbox_rect = new_bbox_rect.normalized()
            logging.debug(f"  Potential new line bbox (normalized): {new_bbox_rect}")

            # 3. Minimum boyut kontrolü
            valid_resize = True
            if new_bbox_rect.width() < MIN_SIZE:
                 valid_resize = False
                 logging.debug(f"  Line resize invalid: Width {new_bbox_rect.width()} < {MIN_SIZE}")
                 # Geri al: Hangi kenarı geri almalı? Delta'nın etkilediğini.
                 if 'left' in handle_type: new_bbox_rect.setLeft(current_bbox.left())
                 elif 'right' in handle_type: new_bbox_rect.setRight(current_bbox.right())
                 # Eğer hem left hem right tutamacı değilse (örn. middle-top), genişliği korumak için diğer kenarı ayarla
                 elif current_bbox.width() > 1e-6 : # Avoid division by zero
                     if new_bbox_rect.width() < MIN_SIZE : # Check again after potential revert
                         if new_bbox_rect.left() != current_bbox.left(): new_bbox_rect.setRight(new_bbox_rect.left() + current_bbox.width())
                         else: new_bbox_rect.setLeft(new_bbox_rect.right() - current_bbox.width())


            if new_bbox_rect.height() < MIN_SIZE:
                 valid_resize = False
                 logging.debug(f"  Line resize invalid: Height {new_bbox_rect.height()} < {MIN_SIZE}")
                 if 'top' in handle_type: new_bbox_rect.setTop(current_bbox.top())
                 elif 'bottom' in handle_type: new_bbox_rect.setBottom(current_bbox.bottom())
                 # Eğer hem top hem bottom tutamacı değilse, yüksekliği koru
                 elif current_bbox.height() > 1e-6:
                     if new_bbox_rect.height() < MIN_SIZE: # Check again after potential revert
                         if new_bbox_rect.top() != current_bbox.top(): new_bbox_rect.setBottom(new_bbox_rect.top() + current_bbox.height())
                         else: new_bbox_rect.setTop(new_bbox_rect.bottom() - current_bbox.height())

            # Boyut kontrolünden sonraki son hedef bbox
            target_bbox = new_bbox_rect.normalized() 
            logging.debug(f"  Final target line bbox (after min size check): {target_bbox}")

            # 4. Ölçekleme ve taşıma faktörlerini hesapla
            # Sıfır genişlik/yükseklik durumunu ele al
            sx = target_bbox.width() / current_bbox.width() if current_bbox.width() > 1e-6 else 1.0
            sy = target_bbox.height() / current_bbox.height() if current_bbox.height() > 1e-6 else 1.0
            tx = target_bbox.left() - current_bbox.left() * sx
            ty = target_bbox.top() - current_bbox.top() * sy
            
            logging.debug(f"  Calculated transform: sx={sx}, sy={sy}, tx={tx}, ty={ty}")

            # 5. Tüm noktaları dönüştür ve item_data[2]'yi güncelle
            new_points = []
            for p in points:
                new_x = p.x() * sx + tx
                new_y = p.y() * sy + ty
                new_points.append(QPointF(new_x, new_y))
            
            # Orijinal listeyi doğrudan güncelle
            item_data[2][:] = new_points 
            logging.debug(f"  >>> Applied resize to line. {len(new_points)} points updated.")


    except (IndexError, TypeError, ValueError) as e: # ValueError eklendi (min/max için)
        logging.error(f"resize_item (incremental): Error updating item data: {e}", exc_info=True)

# --- Transformation Helper ---
def transform_points(points: List[QPointF], sx: float, sy: float, tx: float, ty: float) -> List[QPointF]:
    """Applies an affine transformation (scale sx, sy; translate tx, ty) to a list of points."""
    new_points = []
    for p in points:
        new_x = p.x() * sx + tx
        new_y = p.y() * sy + ty
        new_points.append(QPointF(new_x, new_y))
    return new_points

# --- ESKİ resize_item Fonksiyonu (Referans için yorumda bırakıldı) ---
# def resize_item(item_data: List[Any], handle_type: str, current_pos: QPointF, start_pos: QPointF, original_rect: QRectF):
#     """Verilen öğeyi (şekil veya çizgi) yakalanan tutamaca göre yeniden boyutlandırır."""
#     # ... (önceki kod) ...

# Eski fonksiyon tanımı (kullanılmıyor, kaldırılabilir)
# def resize_item(item_data, scale_factor, anchor_point):
#     """Verilen bir çizim öğesini boyutlandırır."""
#     logging.warning("resize_item henüz implemente edilmedi.")
#     # TODO: item_data'nın tipine göre anchor_point etrafında
#     #       noktalarını scale_factor oranında ölçekle
#     pass 
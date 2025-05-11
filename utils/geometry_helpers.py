# utils/geometry_helpers.py
"""Geometrik hesaplamalar için yardımcı fonksiyonlar."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPolygonF, QPainterPath, QTransform
from typing import List, Tuple, Any
import math
import copy
import logging

from gui.enums import ToolType

# Type definitions
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]
ItemRef = Tuple[str, int] # ('lines', index) veya ('shapes', index)

def get_item_bounding_box(item_data: List[Any], item_type: str) -> QRectF:
    """Verilen çizgi veya şekil verisi için sınırlayıcı dikdörtgeni hesaplar."""
    min_x, min_y = math.inf, math.inf
    max_x, max_y = -math.inf, -math.inf

    if item_type == 'lines' and len(item_data) >= 3:
        points: List[QPointF] = item_data[2]
        if not points:
            return QRectF() # Boş rect
        for p in points:
            min_x = min(min_x, p.x())
            min_y = min(min_y, p.y())
            max_x = max(max_x, p.x())
            max_y = max(max_y, p.y())
        # YENİ LOG
        # logging.debug(f"[BBOX_DEBUG] Line: p1={points[0] if points else 'N/A'}, p2={points[-1] if points else 'N/A'}, min_x={min_x:.2f}, min_y={min_y:.2f}, max_x={max_x:.2f}, max_y={max_y:.2f}, rect_width={max_x-min_x:.2f}, rect_height={max_y-min_y:.2f}")

    elif item_type == 'shapes' and len(item_data) >= 5:
        tool_type: ToolType = item_data[0]
        p1: QPointF = item_data[3]
        p2: QPointF = item_data[4]

        if tool_type == ToolType.LINE:
            min_x = min(p1.x(), p2.x())
            min_y = min(p1.y(), p2.y())
            max_x = max(p1.x(), p2.x())
            max_y = max(p1.y(), p2.y())
        elif tool_type == ToolType.RECTANGLE:
            min_x = min(p1.x(), p2.x())
            min_y = min(p1.y(), p2.y())
            max_x = max(p1.x(), p2.x())
            max_y = max(p1.y(), p2.y())
        elif tool_type == ToolType.CIRCLE:
            center_x = (p1.x() + p2.x()) / 2
            center_y = (p1.y() + p2.y()) / 2
            radius = abs(p1.x() - p2.x()) / 2
            min_x = center_x - radius
            min_y = center_y - radius
            max_x = center_x + radius
            max_y = center_y + radius
        else:
            return QRectF()
    else:
        return QRectF()

    return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))

def is_point_on_line(point: QPointF, p1: QPointF, p2: QPointF, tolerance: float = 5.0) -> bool:
    """Bir noktanın belirli bir toleransla bir doğru parçası üzerinde olup olmadığını kontrol eder."""
    # YENİ LOGLAR
    logging.debug(f"[IS_POINT_ON_LINE_DEBUG] Checking point {point} against line ({p1} to {p2}) with tolerance {tolerance:.2f}")
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    logging.debug(f"[IS_POINT_ON_LINE_DEBUG] dx={dx:.4f}, dy={dy:.4f}")

    # 1. Eğer çizgi çok kısaysa (neredeyse bir nokta)
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        logging.debug("[IS_POINT_ON_LINE_DEBUG] Path: Line is a point.")
        return (point - p1).manhattanLength() < tolerance

    min_x_line, max_x_line = min(p1.x(), p2.x()), max(p1.x(), p2.x())
    min_y_line, max_y_line = min(p1.y(), p2.y()), max(p1.y(), p2.y())
    
    epsilon_hv = 1e-4 # Yatay/Dikey için tolerans

    # 2. Neredeyse Dikey Çizgi Kontrolü
    if abs(dx) < epsilon_hv:
        logging.debug("[IS_POINT_ON_LINE_DEBUG] Path: Checking for nearly vertical line.")
        is_x_close = abs(point.x() - p1.x()) < tolerance
        is_y_in_range = (min_y_line - tolerance <= point.y() <= max_y_line + tolerance)
        logging.debug(f"[IS_POINT_ON_LINE_DEBUG]   Vertical: is_x_close={is_x_close} (target_x={p1.x():.2f}, point_x={point.x():.2f}), is_y_in_range={is_y_in_range}")
        if is_x_close and is_y_in_range:
            logging.debug("[IS_POINT_ON_LINE_DEBUG]   Vertical: Match!")
            return True

    # 3. Neredeyse Yatay Çizgi Kontrolü
    if abs(dy) < epsilon_hv: 
        logging.debug("[IS_POINT_ON_LINE_DEBUG] Path: Checking for nearly horizontal line.")
        is_y_close = abs(point.y() - p1.y()) < tolerance
        is_x_in_range = (min_x_line - tolerance <= point.x() <= max_x_line + tolerance)
        logging.debug(f"[IS_POINT_ON_LINE_DEBUG]   Horizontal: is_y_close={is_y_close} (target_y={p1.y():.2f}, point_y={point.y():.2f}), is_x_in_range={is_x_in_range}")
        if is_y_close and is_x_in_range:
            logging.debug("[IS_POINT_ON_LINE_DEBUG]   Horizontal: Match!")
            return True

    # 4. Genel Durum: Sınırlayıcı Kutu ve Dik Uzaklık
    logging.debug("[IS_POINT_ON_LINE_DEBUG] Path: General case (bounding box and perpendicular distance).")
    if not (min_x_line - tolerance <= point.x() <= max_x_line + tolerance and
            min_y_line - tolerance <= point.y() <= max_y_line + tolerance):
        logging.debug("[IS_POINT_ON_LINE_DEBUG]   General: Outside bounding box.")
        return False 

    line_len_sq = dx * dx + dy * dy
    if line_len_sq < 1e-12: 
        logging.debug("[IS_POINT_ON_LINE_DEBUG]   General: Line length too small (already checked, but for safety).")
        return (point - p1).manhattanLength() < tolerance

    t = ((point.x() - p1.x()) * dx + (point.y() - p1.y()) * dy) / line_len_sq
    logging.debug(f"[IS_POINT_ON_LINE_DEBUG]   General: t = {t:.4f}")

    if t < 0: 
        closest_p = p1
    elif t > 1: 
        closest_p = p2
    else: 
        closest_p = p1 + t * QPointF(dx, dy)

    dist_sq = (point.x() - closest_p.x())**2 + (point.y() - closest_p.y())**2
    result = dist_sq < tolerance * tolerance
    logging.debug(f"[IS_POINT_ON_LINE_DEBUG]   General: closest_p={closest_p}, dist_sq={dist_sq:.4f}, tolerance_sq={tolerance*tolerance:.4f}, result={result}")
    return result

# --- YENİ: Noktadan Doğru Parçasına Uzaklığın Karesi ---
def point_segment_distance_sq(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Bir p noktasının, a ve b noktalarıyla tanımlanan doğru parçasına olan en kısa uzaklığının karesini hesaplar."""
    l2 = (b.x() - a.x())**2 + (b.y() - a.y())**2
    if l2 == 0.0: # a ve b aynı nokta
        return (p.x() - a.x())**2 + (p.y() - a.y())**2

    # Doğru parçasının üzerindeki en yakın noktanın parametresini (t) bul
    # t = [(p-a) . (b-a)] / |b-a|^2
    t = ((p.x() - a.x()) * (b.x() - a.x()) + (p.y() - a.y()) * (b.y() - a.y())) / l2
    t = max(0.0, min(1.0, t)) # t'yi [0, 1] aralığına sıkıştır

    # En yakın noktayı (projection) hesapla
    projection_x = a.x() + t * (b.x() - a.x())
    projection_y = a.y() + t * (b.y() - a.y())

    # p ile en yakın nokta arasındaki uzaklığın karesini döndür
    return (p.x() - projection_x)**2 + (p.y() - projection_y)**2

# --- YENİ: Yeniden Boyutlandırma İmlecini Alma ---
def get_resize_cursor(handle_type: str) -> Qt.CursorShape:
    """Verilen tutamaç tipine göre uygun yeniden boyutlandırma imlecini döndürür."""
    if handle_type in ['top-left', 'bottom-right']:
        return Qt.CursorShape.SizeFDiagCursor # Çapraz (\)
    elif handle_type in ['top-right', 'bottom-left']:
        return Qt.CursorShape.SizeBDiagCursor # Çapraz (/)
    elif handle_type in ['middle-top', 'middle-bottom']:
        return Qt.CursorShape.SizeVerCursor   # Dikey
    elif handle_type in ['middle-left', 'middle-right']:
        return Qt.CursorShape.SizeHorCursor   # Yatay
    else:
        return Qt.CursorShape.ArrowCursor     # Varsayılan

# --- YENİ: Yeniden Boyutlandırma Sonrası Yeni BBox Hesaplama ---
def calculate_new_bbox(original_bbox: QRectF, handle_type: str, current_pos: QPointF, start_pos: QPointF) -> QRectF:
    """Yeniden boyutlandırma sırasında yeni sınırlayıcı kutuyu hesaplar."""
    new_bbox = QRectF(original_bbox) # Orijinalinden başla
    delta = current_pos - start_pos

    # Hangi kenarların/köşelerin hareket ettiğini belirle ve yeni bbox'ı ayarla
    if 'left' in handle_type:
        new_bbox.setLeft(original_bbox.left() + delta.x())
    if 'right' in handle_type:
        new_bbox.setRight(original_bbox.right() + delta.x())
    if 'top' in handle_type:
        new_bbox.setTop(original_bbox.top() + delta.y())
    if 'bottom' in handle_type:
        new_bbox.setBottom(original_bbox.bottom() + delta.y())

    # Genişlik veya yükseklik sıfır veya negatif olmamalı
    if new_bbox.width() <= 0 or new_bbox.height() <= 0:
        return QRectF() # Geçersiz bbox
        
    return new_bbox

# --- YENİ: Seçili Öğeleri Dönüştürme ---
def transform_items(original_states: List[dict], 
                    selected_indices: List[Tuple[str, int]], 
                    center_original: QPointF, 
                    scale_x: float, 
                    scale_y: float, 
                    center_new: QPointF
                    ) -> Tuple[List[Tuple[str, int, dict]], List[Tuple[str, int, dict]]]:
    """Verilen orijinal durumları, ölçekleme ve taşıma parametrelerine göre dönüştürür."""
    transformed_lines = []
    transformed_shapes = []
    
    translate_delta = center_new - center_original

    for i, (item_type, index) in enumerate(selected_indices):
        if i >= len(original_states): # Güvenlik kontrolü
             logging.warning(f"transform_items: index {i} original_states sınırları dışında.")
             continue
        state = original_states[i]
        if not state: # Önceki _get_current_selection_states'ten None gelmişse
             logging.warning(f"transform_items: index {i} için state None, atlanıyor.")
             continue
             
        new_state = copy.deepcopy(state) # Yeni state oluştur

        if item_type == 'lines' and 'points' in new_state:
            transformed_points = []
            for p in new_state['points']:
                # 1. Merkeze göre göreceli konumu bul
                relative_p = p - center_original
                # 2. Ölçekle
                scaled_p = QPointF(relative_p.x() * scale_x, relative_p.y() * scale_y)
                # 3. Yeni merkeze göre mutlak konumu bul ve taşıma ekle
                transformed_p = scaled_p + center_original + translate_delta
                transformed_points.append(transformed_p)
            new_state['points'] = transformed_points
            transformed_lines.append((item_type, index, new_state))
        elif item_type == 'shapes' and 'p1' in new_state and 'p2' in new_state:
            for key in ['p1', 'p2']:
                p = new_state[key]
                relative_p = p - center_original
                scaled_p = QPointF(relative_p.x() * scale_x, relative_p.y() * scale_y)
                transformed_p = scaled_p + center_original + translate_delta
                new_state[key] = transformed_p
            transformed_shapes.append((item_type, index, new_state))
        else:
            logging.warning(f"transform_items: Bilinmeyen öğe tipi veya state formatı: {item_type}, state keys: {state.keys() if isinstance(state, dict) else 'Not a dict'}")

    return transformed_lines, transformed_shapes

# --- YENİ: Seçili Öğeleri Taşıma --- #
def move_items_by(lines: List[List[Any]], 
                  shapes: List[List[Any]], 
                  selected_indices: List[Tuple[str, int]], 
                  dx: float, 
                  dy: float):
    """Verilen öğe listelerindeki seçili öğeleri dx, dy kadar taşır (yerinde değiştirir)."""
    delta = QPointF(dx, dy)
    for item_type, index in selected_indices:
        try:
            if item_type == 'lines':
                if 0 <= index < len(lines):
                    line_data = lines[index] # [color, width, points_list]
                    if len(line_data) > 2 and isinstance(line_data[2], list):
                        lines[index][2] = [p + delta for p in line_data[2]]
            elif item_type == 'shapes':
                if 0 <= index < len(shapes):
                    shape_data = shapes[index] # [type, color, width, p1, p2]
                    if len(shape_data) > 4:
                        shapes[index][3] = shape_data[3] + delta # p1
                        shapes[index][4] = shape_data[4] + delta # p2
        except Exception as e:
            logging.error(f"move_items_by hatası ({item_type}[{index}]): {e}", exc_info=True)

# --- Mesafe ve Projeksiyon Yardımcıları --- 

def calculate_new_bbox_aspect_ratio(original_bbox: QRectF, handle_type: str, current_pos: QPointF, original_aspect_ratio: float) -> QRectF:
    """Orijinal bbox, tutamaç tipi, mevcut konum ve en boy oranına göre yeni bbox hesaplar.
       Köşe tutamaçları için karşı köşeyi sabit tutar.
    """
    if original_bbox.isNull() or original_aspect_ratio <= 0:
        logging.warning("calculate_new_bbox_aspect_ratio: Geçersiz girdi (original_bbox null veya aspect_ratio <= 0)")
        return QRectF()

    # 1. Çapa noktasını belirle (sabit kalacak köşe)
    anchor_point = QPointF()
    if handle_type == 'top-left': anchor_point = original_bbox.bottomRight()
    elif handle_type == 'top-right': anchor_point = original_bbox.bottomLeft()
    elif handle_type == 'bottom-left': anchor_point = original_bbox.topRight()
    elif handle_type == 'bottom-right': anchor_point = original_bbox.topLeft()
    elif handle_type == 'middle-left': anchor_point = original_bbox.center() # Kenarlar için merkez veya karşı kenar ortası daha iyi olabilir
    elif handle_type == 'middle-right': anchor_point = original_bbox.center()
    elif handle_type == 'middle-top': anchor_point = original_bbox.center()
    elif handle_type == 'middle-bottom': anchor_point = original_bbox.center()
    else:
        logging.warning(f"calculate_new_bbox_aspect_ratio: Bilinmeyen tutamaç tipi: {handle_type}")
        return QRectF(original_bbox) # Değişiklik yapma

    # 2. Hedef genişlik ve yüksekliği fare pozisyonuna göre hesapla
    target_width = abs(current_pos.x() - anchor_point.x())
    target_height = abs(current_pos.y() - anchor_point.y())

    # 3. En boy oranını koruyarak yeni genişlik ve yüksekliği belirle
    new_width = 0.0
    new_height = 0.0

    if 'middle' in handle_type: # Kenar tutamaçları
        if handle_type in ['middle-left', 'middle-right']:
            # Merkeze olan mesafeyi 2 ile çarparak tam hedef genişliği bul
            full_target_width = target_width * 2.0
            new_width = full_target_width
            new_height = new_width / original_aspect_ratio
        elif handle_type in ['middle-top', 'middle-bottom']:
            # Merkeze olan mesafeyi 2 ile çarparak tam hedef yüksekliği bul
            full_target_height = target_height * 2.0
            new_height = full_target_height
        new_width = new_height * original_aspect_ratio
    else: # Köşe tutamaçları
        # İmlecin çapa noktasına göre hangi eksende daha fazla hareket ettiğine bakarak
        # hangi boyutu öncelikli alacağımıza karar verebiliriz.
        # Alternatif olarak, her iki potansiyel oranı hesaplayıp orijinaline yakın olanı seçebiliriz.
        # Şimdilik, daha basit bir yaklaşım: Genişliğe göre oranı koru.
        # TODO: Daha iyi bir köşe boyutlandırma mantığı gerekebilir.
        width_from_height = target_height * original_aspect_ratio
        height_from_width = target_width / original_aspect_ratio
        
        # Genişlikteki değişim oranı ile yükseklikteki değişim oranını karşılaştır.
        # Hangi eksendeki değişim daha büyükse, o ekseni baz al.
        original_width = original_bbox.width()
        original_height = original_bbox.height()
        
        delta_x_ratio = abs(target_width - original_width) / original_width if original_width > 1e-6 else float('inf')
        delta_y_ratio = abs(target_height - original_height) / original_height if original_height > 1e-6 else float('inf')

        if delta_x_ratio >= delta_y_ratio:
             new_width = target_width
             new_height = height_from_width
             # logging.debug(f"Corner resize: Using width ({new_width:.1f}) to determine height ({new_height:.1f})")
        else:
             new_height = target_height
             new_width = width_from_height
             # logging.debug(f"Corner resize: Using height ({new_height:.1f}) to determine width ({new_width:.1f})")

    # 4. Yeni bbox'ı çapa noktası ve boyutlara göre oluştur
    new_top_left = QPointF()
    if handle_type == 'top-left': new_top_left = QPointF(anchor_point.x() - new_width, anchor_point.y() - new_height)
    elif handle_type == 'top-right': new_top_left = QPointF(anchor_point.x(), anchor_point.y() - new_height)
    elif handle_type == 'bottom-left': new_top_left = QPointF(anchor_point.x() - new_width, anchor_point.y())
    elif handle_type == 'bottom-right': new_top_left = QPointF(anchor_point.x(), anchor_point.y())
    elif handle_type == 'middle-left': new_top_left = QPointF(anchor_point.x() - new_width / 2, anchor_point.y() - new_height / 2)
    elif handle_type == 'middle-right': new_top_left = QPointF(anchor_point.x() - new_width / 2, anchor_point.y() - new_height / 2)
    elif handle_type == 'middle-top': new_top_left = QPointF(anchor_point.x() - new_width / 2, anchor_point.y() - new_height / 2)
    elif handle_type == 'middle-bottom': new_top_left = QPointF(anchor_point.x() - new_width / 2, anchor_point.y() - new_height / 2)

    # Boyutlar çok küçülürse veya negatif olursa engelle
    if new_width < 1.0 or new_height < 1.0:
        # logging.debug("calculate_new_bbox_aspect_ratio: Calculated size too small, returning original.")
        return QRectF(original_bbox) # Veya minimum boyutlu bir rect

    final_bbox = QRectF(new_top_left, QPointF(new_top_left.x() + new_width, new_top_left.y() + new_height))
    # logging.debug(f"calculate_new_bbox_aspect_ratio: Handle='{handle_type}', Anchor={anchor_point}, New Size=({new_width:.1f},{new_height:.1f}), Final BBox={final_bbox}")
    return final_bbox

# --- YENİ: Noktanın Döndürülmüş Dikdörtgen İçinde Olup Olmadığını Kontrol Et --- #
def is_point_in_rotated_rect(point_world: QPointF, rect_world: QRectF, angle_degrees: float) -> bool:
    """Verilen bir noktanın, belirtilen açı kadar döndürülmüş bir dikdörtgenin içinde olup olmadığını kontrol eder.
    
    Args:
        point_world: Kontrol edilecek noktanın dünya koordinatları.
        rect_world: Döndürülmemiş dikdörtgenin dünya koordinatları.
        angle_degrees: Dikdörtgenin dönüş açısı (derece cinsinden).
        
    Returns:
        Nokta döndürülmüş dikdörtgenin içindeyse True, aksi takdirde False.
    """
    if rect_world.isNull() or point_world.isNull():
        return False
        
    # 1. Noktayı, dikdörtgenin merkezi etrafında ters yönde döndür.
    center = rect_world.center()
    transform = QTransform()
    transform.translate(center.x(), center.y())
    transform.rotate(-angle_degrees) # Ters yönde döndür
    transform.translate(-center.x(), -center.y())
    
    rotated_point = transform.map(point_world)
    
    # 2. Döndürülmüş noktanın, orijinal (döndürülmemiş) dikdörtgenin içinde olup olmadığını kontrol et.
    return rect_world.contains(rotated_point)
# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

# ... rest of the file ... 
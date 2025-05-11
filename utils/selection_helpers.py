import math
from PyQt6.QtCore import QPointF, QRectF, QLineF, Qt # Qt import edildi
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QTransform
from PyQt6.QtWidgets import QApplication # İmleç için
from typing import List, Tuple, Dict, Optional # Optional import edildi

HANDLE_SIZE = 15 # Piksel (Eski haline getirildi)
ROTATION_HANDLE_OFFSET = 25 # Döndürme tutamacının bbox'tan uzaklığı (piksel) (Artırıldı - KALMALI)
ROTATION_HANDLE_SIZE_FACTOR = 1.5 # YENİ: Döndürme tutamacının normal tutamaca göre boyut faktörü

# --- YENİ: Standart Seçim Çerçevesi Çiz ---
def draw_standard_selection_frame(
    painter: QPainter, 
    bbox_world: QRectF, 
    zoom_level: float
):
    """
    Eksenlere paralel standart seçim çerçevesini ve boyutlandırma tutamaçlarını çizer.
    Tutamaçların ekran koordinatları DrawingCanvas'ta ayrıca hesaplanır.
    """
    if bbox_world.isNull() or not bbox_world.isValid():
        return

    painter.save()

    # 1. Seçim Dikdörtgenini Çiz (kesikli çizgi)
    pen = QPen(QColor(0, 100, 255, 200), 1, Qt.PenStyle.DashLine) # Maviye yakın bir renk
    pen.setCosmetic(True) # Zoom'dan bağımsız 1px kalınlık
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(bbox_world)

    # 2. Boyutlandırma Tutamaçlarını Çiz (Dünya Koordinatlarında)
    handle_size_world = HANDLE_SIZE / zoom_level if zoom_level > 0 else HANDLE_SIZE
    half_handle_world = handle_size_world / 2.0
    
    handle_pen = QPen(Qt.GlobalColor.black)
    handle_pen.setCosmetic(True)
    handle_brush = QBrush(QColor(0, 100, 255, 128)) # Yarı şeffaf mavi
    
    painter.setPen(handle_pen)
    painter.setBrush(handle_brush)

    handle_positions_world = [
        bbox_world.topLeft(), bbox_world.topRight(),
        bbox_world.bottomLeft(), bbox_world.bottomRight(),
        QPointF(bbox_world.center().x(), bbox_world.top()),
        QPointF(bbox_world.center().x(), bbox_world.bottom()),
        QPointF(bbox_world.left(), bbox_world.center().y()),
        QPointF(bbox_world.right(), bbox_world.center().y())
    ]

    for pos in handle_positions_world:
        handle_rect_world = QRectF(
            pos.x() - half_handle_world, pos.y() - half_handle_world,
            handle_size_world, handle_size_world
        )
        painter.drawRect(handle_rect_world)

    painter.restore()
# --- --- --- --- --- --- --- --- --- --- ---

# --- YENİ: Döndürülmüş Köşeleri Hesapla ---
def get_rotated_corners(rect: QRectF, angle: float) -> List[QPointF]:
    """Verilen QRectF'nin merkez etrafında döndürülmüş köşelerini hesaplar."""
    center = rect.center()
    corners = [
        rect.topLeft(),
        rect.topRight(),
        rect.bottomRight(),
        rect.bottomLeft()
    ]
    
    rotated_corners = []
    transform = QTransform().translate(center.x(), center.y()).rotate(angle).translate(-center.x(), -center.y())
    for corner in corners:
        rotated_corners.append(transform.map(corner))
        
    return rotated_corners
# --- --- --- --- --- --- --- --- --- --- ---

# --- YENİ: Döndürülmüş Seçim Çerçevesi Çiz ---
def draw_rotated_selection_frame(
    painter: QPainter, 
    rect: QRectF, 
    angle: float, 
    zoom_level: float
) -> Dict[str, QRectF]:
    """
    Döndürülmüş seçim çerçevesini, boyutlandırma tutamaçlarını ve döndürme 
    tutamacını çizer. Ekran koordinatlarındaki tutamaç dikdörtgenlerini döndürür.
    """
    if rect.isNull() or not rect.isValid():
        return {}

    painter.save()
    
    # 1. Döndürülmüş Dikdörtgeni Çiz
    rotated_corners = get_rotated_corners(rect, angle)
    rotated_polygon = QPolygonF(rotated_corners)
    
    pen = QPen(QColor(128, 0, 128), 1, Qt.PenStyle.DashLine) # Mor çerçeve
    pen.setCosmetic(True) # Zoom'dan bağımsız 1px kalınlık
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPolygon(rotated_polygon)

    # 2. Boyutlandırma Tutamaçlarını Çiz
    handle_size_world = HANDLE_SIZE / zoom_level if zoom_level > 0 else HANDLE_SIZE
    half_handle_world = handle_size_world / 2.0
    handle_pen = QPen(Qt.GlobalColor.black)
    handle_pen.setCosmetic(True)
    handle_brush = QBrush(QColor(128, 0, 128, 150)) # Yarı şeffaf mor
    painter.setPen(handle_pen)
    painter.setBrush(handle_brush)

    # Köşe tutamaçları (döndürülmüş köşelerde)
    handle_positions = {
        'top-left': rotated_corners[0],
        'top-right': rotated_corners[1],
        'bottom-right': rotated_corners[2],
        'bottom-left': rotated_corners[3],
    }
    
    # Kenar ortası tutamaçları (döndürülmüş kenarların ortasında)
    handle_positions['middle-top'] = (rotated_corners[0] + rotated_corners[1]) / 2.0
    handle_positions['middle-right'] = (rotated_corners[1] + rotated_corners[2]) / 2.0
    handle_positions['middle-bottom'] = (rotated_corners[2] + rotated_corners[3]) / 2.0
    handle_positions['middle-left'] = (rotated_corners[3] + rotated_corners[0]) / 2.0

    screen_handles: Dict[str, QRectF] = {} # Ekran koordinatlarındaki tutamaçlar

    for handle_type, pos in handle_positions.items():
        handle_rect_world = QRectF(
            pos.x() - half_handle_world, pos.y() - half_handle_world, 
            handle_size_world, handle_size_world
        )
        painter.drawRect(handle_rect_world)
        # Ekran koordinatlarını saklamak için canvas'ın world_to_screen'i gerekir.
        # Bu fonksiyon sadece çizer, ekran koordinatları saklama işi Canvas'ta yapılır.
        # Şimdilik sadece dünya koordinatlarını çiziyoruz.
        
    # 3. Döndürme Tutamacını Çiz (Alt Kenarın Ortasında, Biraz Dışarıda)
    bottom_mid_point = handle_positions['middle-bottom']
    center = rect.center()
    # Vektörü al (merkezden alt ortaya)
    vec_center_to_bottom = bottom_mid_point - center
    # Normalleştir ve biraz uzat (daha sonra zoom'a göre ayarlanacak)
    rotation_handle_offset_world = ROTATION_HANDLE_OFFSET / zoom_level if zoom_level > 0 else ROTATION_HANDLE_OFFSET
    if vec_center_to_bottom.manhattanLength() > 1e-6: # Sıfır vektör değilse
         vec_center_to_bottom = vec_center_to_bottom * (1 + rotation_handle_offset_world / vec_center_to_bottom.manhattanLength())
    
    # Döndürme tutamacının merkezi
    rotation_handle_center = center + vec_center_to_bottom
    # rotation_handle_center = bottom_mid_point + rotated_normal_vector * rotation_handle_offset_world

    # --- YENİ: Döndürme tutamacı boyutunu faktörle çarp --- #
    rotation_handle_size_world = handle_size_world * ROTATION_HANDLE_SIZE_FACTOR
    half_rotation_handle_world = rotation_handle_size_world / 2.0
    # --- --- --- --- --- --- --- --- --- --- --- --- ---

    rotation_handle_rect_world = QRectF(
        rotation_handle_center.x() - half_rotation_handle_world, # Yeni yarıçapı kullan
        rotation_handle_center.y() - half_rotation_handle_world, # Yeni yarıçapı kullan
        rotation_handle_size_world, # Yeni boyutu kullan
        rotation_handle_size_world # Yeni boyutu kullan
    )
    
    # Farklı renk/şekil (örneğin daire)
    painter.setBrush(QBrush(QColor(0, 150, 0, 200))) # Yeşilimsi
    painter.drawEllipse(rotation_handle_rect_world)

    painter.restore()

    # Canvas'ın bu fonksiyonu çağırırken bu tutamaçları da eklemesi gerekecek.
    # Şimdilik boş dönelim veya dünya koordinatlarını dönelim? 
    # Canvas'ın hesaplaması daha mantıklı. Boş dönelim.
    return {} # Canvas bu tutamaçların ekran koordinatlarını hesaplamalı.
# --- --- --- --- --- --- --- --- --- --- ---

# --- YENİ: Döndürülmüş Noktada Tutamacı Bul ---
def get_handle_at_rotated_point(
    screen_pos: QPointF, 
    rect: QRectF, 
    angle: float, 
    zoom_level: float, 
    world_to_screen_func # Canvas'tan gelecek fonksiyon: world_pos -> screen_pos
) -> Optional[str]:
    """
    Verilen *ekran* koordinatında, döndürülmüş bir öğenin hangi tutamacının
    (boyutlandırma veya döndürme) olduğunu bulur.
    """
    if rect.isNull() or not rect.isValid():
        return None

    handle_size_world = HANDLE_SIZE / zoom_level if zoom_level > 0 else HANDLE_SIZE
    half_handle_world = handle_size_world / 2.0
    tolerance_screen = HANDLE_SIZE / 2.0 # Ekran pikseli cinsinden tolerans
    
    # 1. Boyutlandırma Tutamaç Pozisyonları (Dünya Koordinatları)
    rotated_corners = get_rotated_corners(rect, angle)
    handle_positions_world = {
        'top-left': rotated_corners[0], 'top-right': rotated_corners[1],
        'bottom-right': rotated_corners[2], 'bottom-left': rotated_corners[3],
        'middle-top': (rotated_corners[0] + rotated_corners[1]) / 2.0,
        'middle-right': (rotated_corners[1] + rotated_corners[2]) / 2.0,
        'middle-bottom': (rotated_corners[2] + rotated_corners[3]) / 2.0,
        'middle-left': (rotated_corners[3] + rotated_corners[0]) / 2.0,
    }

    # 2. Döndürme Tutamacı Pozisyonu (Dünya Koordinatları)
    bottom_mid_point_world = handle_positions_world['middle-bottom']
    center_world = rect.center()
    rotation_handle_offset_world = ROTATION_HANDLE_OFFSET / zoom_level if zoom_level > 0 else ROTATION_HANDLE_OFFSET
    
    vec_center_to_bottom = bottom_mid_point_world - center_world
    if vec_center_to_bottom.manhattanLength() > 1e-6:
         vec_center_to_bottom = vec_center_to_bottom * (1 + rotation_handle_offset_world / vec_center_to_bottom.manhattanLength())
    rotation_handle_center_world = center_world + vec_center_to_bottom
    
    handle_positions_world['rotate'] = rotation_handle_center_world # Döndürme tutamacını ekle

    # 3. Tıklama Kontrolü (Ekran Koordinatlarında)
    for handle_type, handle_center_world in handle_positions_world.items():
        handle_center_screen = world_to_screen_func(handle_center_world)
        # --- YENİ: Tıklama toleransını tutamaç tipine göre ayarla --- #
        current_handle_size_screen = HANDLE_SIZE
        if handle_type == 'rotate':
            current_handle_size_screen *= ROTATION_HANDLE_SIZE_FACTOR
        current_tolerance_screen = current_handle_size_screen / 2.0
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
        # Ekran koordinatlarında tutamaç merkezine olan uzaklığı kontrol et
        delta = screen_pos - handle_center_screen
        # if delta.manhattanLength() <= tolerance_screen: # Eski kontrol
        if delta.manhattanLength() <= current_tolerance_screen: # Yeni kontrol
            return handle_type # Tutamacı bulduk

    return None # Hiçbir tutamaç bulunamadı
# --- --- --- --- --- --- --- --- --- --- ---

def adjust_corner_for_aspect_ratio(
    moving_corner: QPointF,
    fixed_corner: QPointF,
    aspect_ratio: float,
    handle_type: str # Hangi köşenin hareket ettiğini bilmek için (opsiyonel ama faydalı olabilir)
) -> QPointF:
    """
    Verilen hareketli köşe pozisyonunu, sabit köşe ve hedef en-boy oranına göre ayarlar.
    """
    
    # İki aday nokta hesapla: Biri X'i sabitler, diğeri Y'yi sabitler.
    # Hedef 'moving_corner'a en yakın olanı seç.

    # Aday 1: X'i moving_corner'dan al, Y'yi en boy oranına göre hesapla
    delta_x1 = moving_corner.x() - fixed_corner.x()
    new_height_1 = abs(delta_x1 / aspect_ratio) if aspect_ratio > 1e-9 else 0
    new_y1 = fixed_corner.y() + new_height_1 if (moving_corner.y() - fixed_corner.y()) > 0 else fixed_corner.y() - new_height_1
    candidate1 = QPointF(moving_corner.x(), new_y1)

    # Aday 2: Y'yi moving_corner'dan al, X'i en boy oranına göre hesapla
    delta_y2 = moving_corner.y() - fixed_corner.y()
    new_width_2 = abs(delta_y2 * aspect_ratio)
    new_x2 = fixed_corner.x() + new_width_2 if (moving_corner.x() - fixed_corner.x()) > 0 else fixed_corner.x() - new_width_2
    candidate2 = QPointF(new_x2, moving_corner.y())

    # Hedef noktaya (moving_corner) daha yakın olan adayı seç
    # Basit Manhattan mesafesi veya kareli Öklid mesafesi kullanılabilir.
    dist1_sq = (candidate1.x() - moving_corner.x())**2 + (candidate1.y() - moving_corner.y())**2
    dist2_sq = (candidate2.x() - moving_corner.x())**2 + (candidate2.y() - moving_corner.y())**2

    if dist1_sq <= dist2_sq:
        return candidate1
    else:
        return candidate2

# (Var olan get_resize_cursor ve diğerleri aşağıda devam eder)
# ... existing code ...

def get_resize_cursor(handle_type: Optional[str]) -> Qt.CursorShape:
    """Verilen tutamaç tipine göre uygun imleç şeklini döndürür."""
    if handle_type is None:
        return Qt.CursorShape.ArrowCursor # Veya seçici için farklı bir imleç

    if handle_type in ['top-left', 'bottom-right']:
        return Qt.CursorShape.SizeFDiagCursor
    elif handle_type in ['top-right', 'bottom-left']:
        return Qt.CursorShape.SizeBDiagCursor
    elif handle_type in ['middle-top', 'middle-bottom']:
        return Qt.CursorShape.SizeVerCursor
    elif handle_type in ['middle-left', 'middle-right']:
        return Qt.CursorShape.SizeHorCursor
    # --- YENİ: Döndürme imleci ---
    elif handle_type == 'rotate':
        # Özel bir döndürme imleci yüklenebilir veya standart bir imleç kullanılabilir
        return Qt.CursorShape.CrossCursor # Şimdilik CrossCursor
    # --- --- --- --- --- --- --- ---
    else:
        return Qt.CursorShape.ArrowCursor # Bilinmeyen tutamaç tipi 
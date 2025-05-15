# utils/geometry_helpers.py
"""Geometrik hesaplamalar için yardımcı fonksiyonlar."""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QPolygonF, QPainterPath, QTransform
from typing import List, Tuple, Any
import math
import copy
import logging
import numpy as np # YENİ: NumPy importu
from scipy.interpolate import splev # YENİ: splev importu

from gui.enums import ToolType

# Type definitions
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]
ItemRef = Tuple[str, int] # ('lines', index) veya ('shapes', index)

def get_item_bounding_box(item_data, item_type: str) -> QRectF:
    """Verilen öğe için sınırlayıcı kutuyu hesaplar."""
    if item_type == 'lines':
        # Lines: [color_tuple, width_float, List[QPointF], Optional[line_style_str]]
        points = item_data[2]
        if len(points) < 2:
            return QRectF() 
        
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)
        
        # Çizginin kalınlığını da hesaba kat
        line_width = item_data[1]
        min_x -= line_width/2
        min_y -= line_width/2
        max_x += line_width/2
        max_y += line_width/2
        
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    elif item_type == 'editable_lines':
        # Düzenlenebilir çizgiler: [ToolType.EDITABLE_LINE, color_tuple, width_float, points_list, line_style]
        # veya normal çizgiler için: [color_tuple, width_float, points_list, line_style]
        
        # Düzenlenebilir çizginin noktalarını al
        if isinstance(item_data[0], ToolType):
            # Düzenlenebilir çizgi formatı: [ToolType.EDITABLE_LINE, color, width, points, line_style]
            points = item_data[3]
            line_width = item_data[2]
        else:
            # Normal çizgi formatı: [color, width, points, line_style]
            points = item_data[2]
            line_width = item_data[1]
        
        if not points or len(points) < 2:
            return QRectF()
        
        # Noktaların sınırlarını hesapla
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)
        
        # Çizginin kalınlığını da hesaba kat
        min_x -= line_width/2
        min_y -= line_width/2
        max_x += line_width/2
        max_y += line_width/2
        
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    elif item_type == 'shapes':
        # Şekil verisi: [ToolType, color, width, ...]
        if len(item_data) < 5:
            return QRectF()
        
        tool_type = item_data[0]
        
        if tool_type == ToolType.EDITABLE_LINE:
            # Düzenlenebilir çizgi için özel işlem
            # [ToolType.EDITABLE_LINE, color, width, control_points, line_style]
            control_points = item_data[3]
            line_width = item_data[2]
            
            if not control_points or len(control_points) < 2:
                return QRectF()
            
            # Kontrol noktalarının sınırlarını hesapla
            min_x = min(p.x() for p in control_points)
            max_x = max(p.x() for p in control_points)
            min_y = min(p.y() for p in control_points)
            max_y = max(p.y() for p in control_points)
            
            # Çizginin kalınlığını da hesaba kat
            min_x -= line_width/2
            min_y -= line_width/2
            max_x += line_width/2
            max_y += line_width/2
            
            return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
            
        elif tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
            # Standart şekiller: [ToolType, color, width, p1, p2, ...]
            p1 = item_data[3]
            p2 = item_data[4]
            line_width = item_data[2]
            
            # p1 ve p2'den sınırlayıcı kutuyu hesapla
            min_x = min(p1.x(), p2.x())
            max_x = max(p1.x(), p2.x())
            min_y = min(p1.y(), p2.y())
            max_y = max(p1.y(), p2.y())
            
            # Çizginin kalınlığını da hesaba kat
            min_x -= line_width/2
            min_y -= line_width/2
            max_x += line_width/2
            max_y += line_width/2
            
            return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        
        elif tool_type == ToolType.PATH:
            # PATH: [ToolType.PATH, color, width, points, line_style]
            points = item_data[3]
            line_width = item_data[2]
            if not points or len(points) < 2:
                return QRectF()
            min_x = min(p.x() for p in points)
            max_x = max(p.x() for p in points)
            min_y = min(p.y() for p in points)
            max_y = max(p.y() for p in points)
            min_x -= line_width/2
            min_y -= line_width/2
            max_x += line_width/2
            max_y += line_width/2
            return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    # Diğer türler için boş bir dikdörtgen döndür
    return QRectF()

def get_bspline_bounding_box(stroke_data: dict, num_samples: int = 100) -> QRectF:
    """
    Verilen B-Spline stroke verisi için sınırlayıcı kutuyu hesaplar.
    Eksik anahtar veya None değer varsa, fallback olarak sadece 'control_points' listesinin bbox'unu döndür.
    """
    logging.debug(f"[get_bspline_bounding_box] stroke_data: {stroke_data}")
    # Anahtarlar eksikse veya None ise, fallback olarak bbox'u kontrol noktalarından hesapla
    if not isinstance(stroke_data, dict) or 'control_points' not in stroke_data:
        logging.warning("get_bspline_bounding_box: stroke_data dict değil veya 'control_points' anahtarı yok.")
        return QRectF()
    control_points = stroke_data.get('control_points')
    # Eğer numpy array değilse, QPointF listesi olabilir
    if isinstance(control_points, list) and len(control_points) > 0 and isinstance(control_points[0], QPointF):
        min_x = min(p.x() for p in control_points)
        max_x = max(p.x() for p in control_points)
        min_y = min(p.y() for p in control_points)
        max_y = max(p.y() for p in control_points)
        return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
    # Eski anahtar kontrolleri ve numpy array işlemleri
    if not all(k in stroke_data for k in ['control_points', 'knots', 'degree', 'u']):
        logging.warning("get_bspline_bounding_box: stroke_data eksik anahtarlar içeriyor.")
        return QRectF()
    control_points_np = stroke_data.get('control_points')
    knots = stroke_data.get('knots')
    degree = stroke_data.get('degree')
    u_params = stroke_data.get('u')
    if control_points_np is None or knots is None or degree is None or u_params is None or len(control_points_np) == 0:
        logging.warning("get_bspline_bounding_box: stroke_data içindeki bazı değerler None veya kontrol noktaları boş.")
        return QRectF()
    
    if not isinstance(control_points_np, np.ndarray):
        logging.warning("get_bspline_bounding_box: control_points_np bir numpy array değil.")
        # Hata durumunda sadece kontrol noktalarının bbox'ını döndürmeyi dene (eğer liste ise np array'e çevir)
        try:
            if isinstance(control_points_np, list) and len(control_points_np) > 0:
                # Eğer QPointF listesi ise np array'e çevir
                if all(isinstance(p, QPointF) for p in control_points_np):
                    control_points_np = np.array([(p.x(), p.y()) for p in control_points_np])
                else: # Değilse ve hala liste ise, np.array ile çevirmeyi dene
                    control_points_np = np.array(control_points_np)
            
            if not isinstance(control_points_np, np.ndarray) or control_points_np.ndim != 2 or control_points_np.shape[1] != 2:
                 logging.error("get_bspline_bounding_box: control_points_np uygun numpy formatına çevrilemedi.")
                 return QRectF()
                 
            min_x = np.min(control_points_np[:, 0])
            max_x = np.max(control_points_np[:, 0])
            min_y = np.min(control_points_np[:, 1])
            max_y = np.max(control_points_np[:, 1])
            return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
        except Exception as e_fallback:
            logging.error(f"get_bspline_bounding_box (fallback numpy dönüşümü): Kontrol noktası bbox hesaplanırken hata: {e_fallback}")
            return QRectF()

    if len(u_params) == 0: 
        if len(control_points_np) > 0:
            min_x = np.min(control_points_np[:, 0])
            max_x = np.max(control_points_np[:, 0])
            min_y = np.min(control_points_np[:, 1])
            max_y = np.max(control_points_np[:, 1])
            return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
        return QRectF()

    try:
        # control_points_np zaten (N,2) formatında olmalı.
        # splev, tck'nın ikinci elemanı için (dims, N) bekler, yani (2,N).
        tck = (knots, control_points_np.T, degree)
        
        if len(u_params) < 1 or u_params[-1] <= u_params[0]:
            if len(control_points_np) > 0:
                min_x = np.min(control_points_np[:, 0])
                max_x = np.max(control_points_np[:, 0])
                min_y = np.min(control_points_np[:, 1])
                max_y = np.max(control_points_np[:, 1])
                return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
            return QRectF()

        x_coords, y_coords = splev(np.linspace(u_params[0], u_params[-1], num_samples), tck)

        if not isinstance(x_coords, np.ndarray) or not isinstance(y_coords, np.ndarray) or x_coords.size == 0 or y_coords.size == 0:
            logging.warning("get_bspline_bounding_box: splev beklenen numpy array'leri döndürmedi veya boş array döndürdü.")
            # Fallback to control points bbox
            if len(control_points_np) > 0:
                min_x = np.min(control_points_np[:, 0]); max_x = np.max(control_points_np[:, 0])
                min_y = np.min(control_points_np[:, 1]); max_y = np.max(control_points_np[:, 1])
                return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
            return QRectF()

        min_x = np.min(x_coords)
        max_x = np.max(x_coords)
        min_y = np.min(y_coords)
        max_y = np.max(y_coords)

        return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))

    except Exception as e:
        logging.error(f"get_bspline_bounding_box: B-Spline örneklenirken hata: {e}", exc_info=True)
        try:
            if len(control_points_np) > 0 and isinstance(control_points_np, np.ndarray) and control_points_np.ndim == 2 and control_points_np.shape[1] == 2:
                min_x = np.min(control_points_np[:, 0])
                max_x = np.max(control_points_np[:, 0])
                min_y = np.min(control_points_np[:, 1])
                max_y = np.max(control_points_np[:, 1])
                return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))
        except Exception as e_fallback:
            logging.error(f"get_bspline_bounding_box (fallback): Kontrol noktası bbox hesaplanırken hata: {e_fallback}")
        return QRectF()

def is_point_on_line(point, line_start, line_end, tolerance=5.0):
    """Bir noktanın çizgi üzerinde olup olmadığını kontrol eder.
    
    Args:
        point (QPointF): Kontrol edilecek nokta
        line_start (QPointF): Çizginin başlangıç noktası
        line_end (QPointF): Çizginin bitiş noktası
        tolerance (float): Mesafe toleransı. Varsayılan değer 5.0 pixeldir.
    
    Returns:
        bool: Nokta çizgi üzerindeyse True, değilse False
    """
    # Nokta ile çizgi arasındaki mesafenin karesini hesapla
    # Eğer mesafe kare, tolerans karesinden küçükse, nokta çizgi üzerindedir
    # Hesaplama, çizgiye olan projeksiyon hesabı ile yapılır
    distance_sq = point_segment_distance_sq(point, line_start, line_end)
    
    # YENİ: Taşıma işlemleri için daha geniş tolerans
    effective_tolerance = tolerance * 2.5  # Toleransı 2.5 kat artır
    
    return distance_sq <= effective_tolerance * effective_tolerance

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
    from gui.enums import ToolType  # ToolType'ı bu fonksiyonun içinde import et
    
    delta = QPointF(dx, dy)
    for item_type, index in selected_indices:
        try:
            if item_type == 'lines':
                if 0 <= index < len(lines):
                    line_data = lines[index] # [color, width, points_list]
                    if len(line_data) > 2 and isinstance(line_data[2], list):
                        # Çizginin tüm noktalarını taşı
                        lines[index][2] = [p + delta for p in line_data[2]]
                        logging.debug(f"Line {index} moved by ({dx}, {dy})")
            elif item_type == 'shapes':
                if 0 <= index < len(shapes):
                    shape_data = shapes[index] # [type, color, width, p1, p2]
                    
                    # Önce şekil tipini al
                    if len(shape_data) == 0:
                        logging.error(f"Shape {index} has empty data, skipping move")
                        continue
                        
                    shape_type = shape_data[0]
                    logging.debug(f"Moving shape {index} (type: {shape_type}) by ({dx}, {dy})")
                    
                    if shape_type == ToolType.EDITABLE_LINE:
                        # Düzenlenebilir çizgi için tüm kontrol noktalarını taşı
                        if isinstance(shape_data[3], list):
                            shape_data[3] = [p + delta for p in shape_data[3]]
                            logging.debug(f"EDITABLE_LINE {index} moved by ({dx}, {dy})")
                    elif shape_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                        # Standart şekiller için p1 ve p2'yi taşı
                        if len(shape_data) > 4:
                            # Orijinal değerler
                            old_p1 = QPointF(shape_data[3])
                            old_p2 = QPointF(shape_data[4])
                            
                            # Yeni değerler
                            shape_data[3] = old_p1 + delta # p1
                            shape_data[4] = old_p2 + delta # p2
                            
                            logging.debug(f"Shape {index} (type: {shape_type}) moved from ({old_p1.x():.1f}, {old_p1.y():.1f})-({old_p2.x():.1f}, {old_p2.y():.1f}) to ({shape_data[3].x():.1f}, {shape_data[3].y():.1f})-({shape_data[4].x():.1f}, {shape_data[4].y():.1f})")
                    else:
                        # Diğer şekiller (bilinmeyen türler) için genel yaklaşım
                        # Eğer p1 ve p2 pozisyonları varsa onları taşı
                        if len(shape_data) > 4:
                            old_p1 = QPointF(shape_data[3])
                            old_p2 = QPointF(shape_data[4])
                            
                            shape_data[3] = old_p1 + delta # p1
                            shape_data[4] = old_p2 + delta # p2
                            
                            logging.debug(f"Unknown shape {index} (type: {shape_type}) moved from ({old_p1.x():.1f}, {old_p1.y():.1f})-({old_p2.x():.1f}, {old_p2.y():.1f}) to ({shape_data[3].x():.1f}, {shape_data[3].y():.1f})-({shape_data[4].x():.1f}, {shape_data[4].y():.1f})")
            elif item_type == 'images':
                # Canvas'ta images listesi mevcut ise
                canvas = None
                for selected_type, selected_idx in selected_indices:
                    if selected_type == 'shapes' or selected_type == 'lines':
                        try:
                            canvas = lines[0][0].parent() if lines and len(lines) > 0 else None
                            if not canvas and shapes and len(shapes) > 0:
                                canvas = shapes[0][0].parent()
                            break
                        except Exception:
                            pass
                
                if canvas and hasattr(canvas, '_parent_page') and canvas._parent_page and hasattr(canvas._parent_page, 'images'):
                    if 0 <= index < len(canvas._parent_page.images):
                        img_data = canvas._parent_page.images[index]
                        if 'rect' in img_data and isinstance(img_data['rect'], QRectF):
                            # Resmin dikdörtgenini taşı
                            img_data['rect'].translate(delta)
                            logging.debug(f"Image {index} moved by ({dx}, {dy})")
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
        # Şimdilik, daha basit bir yaklaşım: Genişlikteki değişim oranı ile yükseklikteki değişim oranını karşılaştır.
        # Hangi eksendeki değişim daha büyükse, o ekseni baz al.
        original_width = original_bbox.width()
        original_height = original_bbox.height()
        
        delta_x_ratio = abs(target_width - original_width) / original_width if original_width > 1e-6 else float('inf')
        delta_y_ratio = abs(target_height - original_height) / original_height if original_height > 1e-6 else float('inf')

        if delta_x_ratio >= delta_y_ratio:
             new_width = target_width
             new_height = new_width / original_aspect_ratio
             # logging.debug(f"Corner resize: Using width ({new_width:.1f}) to determine height ({new_height:.1f})")
        else:
             new_height = target_height
             new_width = new_height * original_aspect_ratio
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

# YENİ: Standart Tutamaç Pozisyonları
def get_standard_handle_positions(bbox: QRectF) -> dict:
    """
    Verilen bir QRectF (sınırlayıcı kutu) için standart 8 boyutlandırma
    tutamacının dünya koordinatlarındaki pozisyonlarını bir sözlük olarak döndürür.
    """
    if bbox.isNull() or not bbox.isValid():
        return {}
    return {
        'top-left': bbox.topLeft(),
        'top-right': bbox.topRight(),
        'bottom-left': bbox.bottomLeft(),
        'bottom-right': bbox.bottomRight(),
        'middle-top': QPointF(bbox.center().x(), bbox.top()),
        'middle-bottom': QPointF(bbox.center().x(), bbox.bottom()),
        'middle-left': QPointF(bbox.left(), bbox.center().y()),
        'middle-right': QPointF(bbox.right(), bbox.center().y())
    }
# --- --- --- --- --- --- --- --- --- ---

# ... rest of the file ... 
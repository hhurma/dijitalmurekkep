"""
Düzenlenebilir Çizgi aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, List
import math
import numpy as np
from scipy import interpolate

from PyQt6.QtCore import QPointF, Qt, QDateTime
from PyQt6.QtGui import QTabletEvent

from utils.commands import DrawEditableLineCommand, UpdateEditableLineCommand
from ..enums import ToolType

# Sabitler
HANDLE_SIZE = 15  # Tablet kalemi için normal tutucu boyutundan daha büyük
MIN_POINT_DISTANCE = 15  # İki nokta arasındaki minimum mesafe (piksel) - Daha fazla nokta için azaltıldı
SIMPLIFICATION_EPSILON = 8.0  # Douglas-Peucker algoritması için epsilon değeri - Düşük değer daha fazla nokta saklar
CONTROL_POINT_SCALE = 1.5  # Kontrol noktası mesafesi için ölçek faktörü - Daha yüksek = daha belirgin eğriler
CONTROL_POINT_PERPENDICULAR_SCALE = 1.2  # Çizgiye dik yöndeki uzaklık ölçeği - Daha yüksek = daha çıkık eğriler
USE_TRUE_BSPLINE = True  # Gerçek B-spline algoritması kullanılsın mı
B_SPLINE_RESOLUTION = 50  # B-spline eğrisinin çözünürlüğü - Daha yüksek değer daha pürüzsüz eğriler
STRAIGHT_LINE_THRESHOLD = 0.5  # Düz çizgi tespiti için eşik değeri - Yüksek değer neredeyse hiçbir çizgiyi düz kabul etmez

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas

def update_bezier_control_points(canvas: 'DrawingCanvas'):
    """
    Mevcut editable_line_points'e göre kontrol noktalarını günceller.
    True B-spline algoritması kullanılırsa, bezier_control_points kontrolnoktaları ve eğri noktalarını içerir.
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
    
    if USE_TRUE_BSPLINE and len(points) >= 2:
        # SciPy B-spline algoritması kullan
        create_scipy_bspline(canvas, points)
    else:
        # Klasik bezier interpolasyonu kullan
        create_bezier_curves(canvas, points)

def create_bezier_curves(canvas: 'DrawingCanvas', points: List[QPointF]):
    """Klasik bezier interpolasyonu ile kontrol noktalarını hesaplar."""
    bezier_points = []
    
    for i in range(len(points) - 1):
        p0 = points[i]
        p1 = points[i + 1]
        
        segment_points = calculate_bezier_segment(p0, p1)
        
        # İlk segment için tüm noktaları ekle
        if i == 0:
            bezier_points.extend(segment_points)
        else:
            # Sonraki segmentler için ilk noktayı atlayarak ekle (zaten eklenmiş durumda)
            bezier_points.extend(segment_points[1:])
    
    canvas.bezier_control_points = bezier_points

def create_scipy_bspline(canvas: 'DrawingCanvas', control_points: List[QPointF]):
    """
    SciPy kütüphanesi kullanarak yumuşak B-spline eğrisi oluşturur.
    Daha az sayıda kontrol noktası ve çizginin dışında kontrol noktaları kullanarak
    doğal görünümlü yumuşak eğriler oluşturur.
    
    Args:
        canvas: Çizim tuvali
        control_points: Kullanıcının çizdiği kontrol noktaları
    """
    if len(control_points) < 4:
        # Cubic B-spline için en az 4 nokta gerekli
        canvas.bezier_control_points = control_points
        return
    
    try:
        # Önce kontrol noktalarını sadeleştir (her N noktadan birini al)
        # Bu, çok fazla nokta olduğunda daha yumuşak eğriler oluşturur
        simplify_factor = max(1, len(control_points) // 20)  # Her 20 noktada bir nokta al
        simplified_points = [control_points[i] for i in range(0, len(control_points), simplify_factor)]
        
        # Başlangıç ve bitiş noktalarını her zaman dahil et
        if simplified_points[0] != control_points[0]:
            simplified_points.insert(0, control_points[0])
        if simplified_points[-1] != control_points[-1]:
            simplified_points.append(control_points[-1])
        
        # Eğer çok az nokta kaldıysa, daha fazla nokta ekle
        if len(simplified_points) < 4:
            simplified_points = control_points
        
        # Noktaları numpy dizisine dönüştür
        points = np.array([[p.x(), p.y()] for p in simplified_points])
        
        # SciPy splprep ile B-spline hesapla
        # s parametresi yumuşatma faktörüdür - daha büyük değerler daha yumuşak eğriler üretir
        # Ancak çok büyük olursa, eğri orijinal noktalardan çok uzaklaşır
        s_factor = len(points) * 2.0  # Daha yüksek yumuşatma faktörü
        
        # k=3 kübik spline için (daha yumuşak eğriler)
        tck, u = interpolate.splprep(points.T, s=s_factor, k=3)
        
        # Eğriyi değerlendirmek için daha fazla nokta oluştur
        # Daha yüksek çözünürlük daha pürüzsüz eğriler oluşturur
        u_new = np.linspace(0, 1, B_SPLINE_RESOLUTION * len(simplified_points))
        x_new, y_new = interpolate.splev(u_new, tck)
        
        # Eğri noktalarını QPointF nesnelerine dönüştür
        spline_points = [QPointF(x_new[i], y_new[i]) for i in range(len(x_new))]
        
        # Eğri noktalarını canvas'a kaydet
        canvas.bezier_control_points = spline_points
        
        # Gerçek kontrol noktalarını da sakla (düzenleme için)
        canvas.spline_control_points = []
        ctrl_points_x, ctrl_points_y = tck[1]
        for i in range(len(ctrl_points_x)):
            canvas.spline_control_points.append(QPointF(ctrl_points_x[i], ctrl_points_y[i]))
        
        # B-spline parametrelerini sakla
        canvas.spline_knots = tck[0]
        canvas.spline_degree = tck[2]
        canvas.spline_u = u
        
    except Exception as e:
        logging.error(f"B-spline hesaplaması sırasında hata: {e}")
        # Hata durumunda basit bezier çizimi kullan
        canvas.bezier_control_points = control_points

def calculate_smoothed_bezier_segment(p0: QPointF, p1: QPointF) -> List[QPointF]:
    """
    İki nokta arasında pürüzsüz görünen bir bezier eğrisi segmenti için 
    kontrol noktalarını hesaplar. Daha belirgin kıvrımlar oluşturur.
    """
    dx = p1.x() - p0.x()
    dy = p1.y() - p0.y()
    distance = math.sqrt(dx * dx + dy * dy)
    
    # Çizginin açısı
    angle = math.atan2(dy, dx)
    
    # Çizgiye dik açı (90 derece)
    perpendicular_angle = angle + math.pi/2
    
    # Kontrol noktalarının çizgiden dışarı çıkma miktarı
    # Daha büyük değer = daha belirgin eğriler
    perpendicular_distance = distance * CONTROL_POINT_PERPENDICULAR_SCALE
    
    # Kontrol noktalarının çizgi boyunca konumu
    # 0.33 ve 0.66 değerleri, kontrol noktalarını çizgi üzerinde 1/3 ve 2/3 mesafelere konumlandırır
    control_distance_along_line = 0.33
    
    # Rotasyon yönü (her zaman aynı yöne eğilsin)
    rotation = 1  # 1 veya -1 olabilir
    
    # Çizgi üzerindeki kontrol noktaları pozisyonları
    c1_line_x = p0.x() + dx * control_distance_along_line
    c1_line_y = p0.y() + dy * control_distance_along_line
    
    c2_line_x = p0.x() + dx * (1 - control_distance_along_line)
    c2_line_y = p0.y() + dy * (1 - control_distance_along_line)
    
    # Kontrol noktalarını çizginin dışına taşı
    c1_x = c1_line_x + rotation * perpendicular_distance * math.cos(perpendicular_angle)
    c1_y = c1_line_y + rotation * perpendicular_distance * math.sin(perpendicular_angle)
    
    c2_x = c2_line_x + rotation * perpendicular_distance * math.cos(perpendicular_angle)
    c2_y = c2_line_y + rotation * perpendicular_distance * math.sin(perpendicular_angle)
    
    return [p0, QPointF(c1_x, c1_y), QPointF(c2_x, c2_y), p1]

def check_if_straight_line(points: List[QPointF], threshold: float = STRAIGHT_LINE_THRESHOLD) -> bool:
    """
    Verilen noktaların yaklaşık olarak düz bir çizgi oluşturup oluşturmadığını kontrol eder.
    Not: Şu an yüksek eşik değeri nedeniyle çoğu çizgi düz olarak kabul edilmeyecek.
    
    Args:
        points: Kontrol edilecek noktalar
        threshold: Doğrusallık eşik değeri (0-1 arası, 0 = tam düz)
        
    Returns:
        Düz çizgi ise True, değilse False
    """
    if len(points) < 3:
        return False  # 2 nokta bile olsa eğri olarak kabul et (daha nazik eğriler için)
    
    # İlk ve son noktayı al
    first_point = points[0]
    last_point = points[-1]
    
    # Referans doğru için vektör
    line_vec_x = last_point.x() - first_point.x()
    line_vec_y = last_point.y() - first_point.y()
    line_length = math.sqrt(line_vec_x * line_vec_x + line_vec_y * line_vec_y)
    
    # Çok kısa çizgiler için False döndür - kısa çizgiler bile eğri olsun
    if line_length < MIN_POINT_DISTANCE * 2:
        return False
    
    # Birim vektör hesapla
    if line_length > 0:
        unit_vec_x = line_vec_x / line_length
        unit_vec_y = line_vec_y / line_length
    else:
        return False  # Çizgi yoksa eğri kabul et
    
    # Her noktanın doğrudan ne kadar saptığını kontrol et
    max_deviation = 0.0
    for i in range(1, len(points) - 1):
        # Orta noktadan doğruya olan uzaklığı hesapla
        point = points[i]
        # Vektör hesaplama
        point_vec_x = point.x() - first_point.x()
        point_vec_y = point.y() - first_point.y()
        
        # Doğru üzerindeki projeksiyonu bul
        projection = point_vec_x * unit_vec_x + point_vec_y * unit_vec_y
        
        # Projeksiyon noktasını hesapla
        proj_x = first_point.x() + projection * unit_vec_x
        proj_y = first_point.y() + projection * unit_vec_y
        
        # Noktanın doğruya olan uzaklığı
        deviation_x = point.x() - proj_x
        deviation_y = point.y() - proj_y
        deviation = math.sqrt(deviation_x * deviation_x + deviation_y * deviation_y)
        
        # Göreceli sapma (çizgi uzunluğuna göre)
        relative_deviation = deviation / line_length
        max_deviation = max(max_deviation, relative_deviation)
    
    # Eşik değerinden düşükse düz çizgi
    return max_deviation <= threshold

def calculate_segment_straightness(segment_points: List[QPointF], all_points: List[QPointF]) -> float:
    """
    Bir segment ve ona yakın noktalar için düzlük derecesini hesaplar.
    0 = tam düz, 1 = tamamen eğimli
    
    Args:
        segment_points: Segmentin başlangıç ve bitiş noktaları
        all_points: Tüm kontrol noktaları
        
    Returns:
        Düzlük derecesi (0-1 arası)
    """
    # Sadece 2 nokta varsa bile eğimli kabul et (yumuşak eğriler için)
    if len(segment_points) != 2 or len(all_points) <= 2:
        return 1.0
    
    p1, p2 = segment_points
    
    # Doğrusal uzunluk hesapla
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    linear_distance = math.sqrt(dx*dx + dy*dy)
    
    # Çok kısa segmentler için bile eğimli kabul et
    if linear_distance < MIN_POINT_DISTANCE:
        return 1.0
    
    # Tüm segmentlerin eğri olmasını sağlamak için her zaman 1.0 döndür
    return 1.0

def create_straight_line_segment(start_point: QPointF, end_point: QPointF) -> List[QPointF]:
    """
    İki nokta arasında hafif eğimli bir çizgi oluşturan bezier segmenti döndürür.
    
    Args:
        start_point: Başlangıç noktası
        end_point: Bitiş noktası
        
    Returns:
        Eğri çizgiyi temsil eden bezier kontrol noktaları
    """
    # İki nokta arasındaki vektörü hesapla
    dx = end_point.x() - start_point.x()
    dy = end_point.y() - start_point.y()
    distance = math.sqrt(dx * dx + dy * dy)
    
    # Çizginin açısı
    angle = math.atan2(dy, dx)
    
    # Çizgiye dik açı
    perpendicular_angle = angle + math.pi/2
    
    # Kontrol noktalarının çizgi boyunca konumu (1/3 ve 2/3 mesafede)
    control_distance_along_line = 0.33
    
    # Düz çizgi için bile hafif bir eğim oluştur
    # Daha küçük değer = daha az eğimli
    perpendicular_distance = distance * 0.5
    
    # Rotasyon yönü
    rotation = 1  # Hep aynı yöne eğilsin
    
    # Çizgi üzerindeki kontrol noktaları
    c1_line_x = start_point.x() + dx * control_distance_along_line
    c1_line_y = start_point.y() + dy * control_distance_along_line
    
    c2_line_x = start_point.x() + dx * (1 - control_distance_along_line)
    c2_line_y = start_point.y() + dy * (1 - control_distance_along_line)
    
    # Kontrol noktalarını çizginin dışına taşı
    c1_x = c1_line_x + rotation * perpendicular_distance * math.cos(perpendicular_angle)
    c1_y = c1_line_y + rotation * perpendicular_distance * math.sin(perpendicular_angle)
    
    c2_x = c2_line_x + rotation * perpendicular_distance * math.cos(perpendicular_angle)
    c2_y = c2_line_y + rotation * perpendicular_distance * math.sin(perpendicular_angle)
    
    return [start_point, QPointF(c1_x, c1_y), QPointF(c2_x, c2_y), end_point]

def calculate_bezier_segment(p0: QPointF, p1: QPointF) -> List[QPointF]:
    """İki nokta arasında kubik bezier eğrisi segmenti için kontrol noktalarını hesaplar."""
    return calculate_smoothed_bezier_segment(p0, p1)

def points_to_bezier_segments(points: List[QPointF]) -> List[QPointF]:
    """
    Eğri noktalarını bezier segmentlerine dönüştürür.
    Bu, B-spline eğrisini mevcut çizim sistemine uyumlu hale getirir.
    """
    if len(points) < 2:
        return points
    
    bezier_segments = []
    bezier_segments.append(points[0])  # İlk nokta
    
    # Her 3 nokta için bir bezier segmenti oluştur 
    # (Her segment 4 nokta içerir: [p0, c1, c2, p3])
    segment_size = 3
    
    for i in range(0, len(points) - 1, segment_size):
        # Segment için noktaları belirle
        start_idx = i
        end_idx = min(i + segment_size, len(points) - 1)
        
        # Segment başlangıç ve bitiş noktaları
        p0 = points[start_idx]
        p3 = points[end_idx]
        
        # Ara noktaları kullanarak kontrol noktalarını belirle
        middle_points = points[start_idx + 1:end_idx]
        
        # Kontrol noktalarını hesapla - özel bir eğri uydurma yöntemi
        if len(middle_points) > 0:
            # İlk kontrol noktası - segment başlangıcından itibaren
            # eğri üzerindeki bir sonraki noktaya doğru
            c1_x = p0.x() + (middle_points[0].x() - p0.x()) * 0.5
            c1_y = p0.y() + (middle_points[0].y() - p0.y()) * 0.5
            
            # İkinci kontrol noktası - segmentin sonundan önceki noktadan
            # segmentin sonuna doğru
            last_middle = middle_points[-1] if middle_points else p0
            c2_x = p3.x() - (p3.x() - last_middle.x()) * 0.5
            c2_y = p3.y() - (p3.y() - last_middle.y()) * 0.5
        else:
            # Eğer ara nokta yoksa, düz bir çizgi yerine hafif bir eğri oluştur
            dx = p3.x() - p0.x()
            dy = p3.y() - p0.y()
            dist = math.sqrt(dx*dx + dy*dy)
            
            # Kontrol noktaları arasındaki mesafeyi belirle
            ctrl_dist = dist / 3.0
            
            # Doğrunun açısını hesapla
            angle = math.atan2(dy, dx)
            
            # Kontrol noktalarını hesapla
            c1_x = p0.x() + ctrl_dist * math.cos(angle)
            c1_y = p0.y() + ctrl_dist * math.sin(angle)
            c2_x = p3.x() - ctrl_dist * math.cos(angle)
            c2_y = p3.y() - ctrl_dist * math.sin(angle)
        
        # B-spline benzeri bir davranış için, segment
        # başlangıç ve bitiş noktalarını tekrarlamaktan kaçın
        if i > 0:
            bezier_segments.pop()  # Son p0'ı (önceki segmentin p3'ü) çıkar
            
        # Bezier kontrol noktalarını ekle
        bezier_segments.extend([
            p0,
            QPointF(c1_x, c1_y),
            QPointF(c2_x, c2_y),
            p3
        ])
    
    return bezier_segments

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
        if len(canvas.current_editable_line_points) >= 3:  # 3 nokta yeterli B-spline için, ama 4 ve üzeri daha iyi
            logging.debug(f"Editable Line Release: Çizim tamamlandı. Nokta sayısı: {len(canvas.current_editable_line_points)}")
            
            # Orijinal noktaları sakla (güvenlik için)
            original_points = canvas.current_editable_line_points.copy()
            original_points_count = len(original_points)
            
            # Ardışık tekrar eden noktaları kaldır
            unique_points = [canvas.current_editable_line_points[0]]
            for i in range(1, len(canvas.current_editable_line_points)):
                if (canvas.current_editable_line_points[i].x() != canvas.current_editable_line_points[i-1].x() or
                    canvas.current_editable_line_points[i].y() != canvas.current_editable_line_points[i-1].y()):
                    unique_points.append(canvas.current_editable_line_points[i])
            
            # Eğer yeterince tekil nokta varsa
            if len(unique_points) >= 3:
                # Douglas-Peucker algoritması ile noktaları çok az sadeleştir (pürüzsüz eğriler için)
                simplified_points = unique_points
                if len(unique_points) > 4:  # 4'ten fazla nokta varsa, basitleştirme uygula
                    simplified_points = douglas_peucker_simplify(
                        unique_points, 
                        SIMPLIFICATION_EPSILON
                    )
                
                # Yeterli nokta kaldığından emin ol
                if len(simplified_points) < 3:
                    simplified_points = unique_points  # Çok az nokta kaldıysa orijinallere geri dön
                
                canvas.current_editable_line_points = simplified_points
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
            else:
                logging.debug(f"Editable Line Release: Yeterli tekil nokta yok ({len(unique_points)}).")
            
            # Çizimden sonra yeni çizim için değişkenleri sıfırla
            canvas.current_editable_line_points = []
            canvas.active_handle_index = -1
            canvas.active_bezier_handle_index = -1
            canvas.is_dragging_bezier_handle = False
            canvas.bezier_control_points = []
            canvas.spline_control_points = []
            canvas.spline_knots = None
            canvas.spline_degree = None
            canvas.spline_u = None
            
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
                        # Ana noktanın indeksi (P0, P3, P6, ...)
                        main_idx = canvas.active_handle_index * 3
                        
                        if main_idx < len(control_points):
                            # Ana noktayı güncelle
                            control_points[main_idx] = pos
                            
                            # Komşu kontrol noktaları (C1, C2) da uygun şekilde güncelle
                            if main_idx > 0:
                                # Önceki kontrol noktası (C2 - ana noktanın öncesindeki)
                                prev_ctrl_idx = main_idx - 1
                                if 0 <= prev_ctrl_idx < len(control_points):
                                    # Önceki kontrol noktasını da ana nokta ile birlikte taşı
                                    # Ancak kontrolün göreceli pozisyonunu koru
                                    prev_shift_x = control_points[main_idx].x() - control_points[prev_ctrl_idx].x()
                                    prev_shift_y = control_points[main_idx].y() - control_points[prev_ctrl_idx].y()
                                    
                                    # Önceki kontrol noktası için aynı göreceli pozisyonu koru
                                    # Taşınan kontrol noktasından aynı vektör farkıyla konumlandır
                                    control_points[prev_ctrl_idx] = QPointF(
                                        pos.x() - prev_shift_x,
                                        pos.y() - prev_shift_y
                                    )
                            
                            if main_idx + 1 < len(control_points):
                                # Sonraki kontrol noktası (C1 - ana noktanın sonrasındaki)
                                next_ctrl_idx = main_idx + 1
                                # Sonraki kontrol noktasını da ana nokta ile birlikte taşı
                                next_shift_x = control_points[next_ctrl_idx].x() - control_points[main_idx].x()
                                next_shift_y = control_points[next_ctrl_idx].y() - control_points[main_idx].y()
                                
                                # Sonraki kontrol noktası için aynı göreceli pozisyonu koru
                                control_points[next_ctrl_idx] = QPointF(
                                    pos.x() + next_shift_x,
                                    pos.y() + next_shift_y
                                )
                            
                            logging.debug(f"Editable Line Editor Move: Ana nokta {canvas.active_handle_index} ve kontrol noktaları güncellendi")
                        else:
                            logging.warning(f"Editable Line Editor Move: Geçersiz ana nokta indeksi: {main_idx}, max: {len(control_points)-1}")
    
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
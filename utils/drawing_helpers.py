import math
# from OpenGL import GL # OpenGL kaldırıldı
from PyQt6.QtCore import QPointF, Qt, QRectF # QRectF eklendi
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath, QBrush # QPainter ve ilgili sınıflar eklendi
from gui.enums import ToolType, TemplateType
from typing import List, Tuple, Any, TYPE_CHECKING
import logging # Logging eklendi
import time # time modülünü import etmeyi unutma! (Dosyanın başında var)

if TYPE_CHECKING:
    from gui.enums import ToolType # Bu zaten vardı, ama yukarıdaki daha genel bir yere taşındı.

# Type hintler (isteğe bağlı)
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]

# Sabitler (DrawingCanvas'tan taşındı)
TEMPLATE_LINE_COLOR = (0.8, 0.8, 0.8)
TEMPLATE_LINE_WIDTH = 1.0
LINED_SPACING = 30
GRID_SPACING = 30

# Helper to convert RGBA float tuple (0-1) to QColor
# Bu DrawingCanvas içindeydi, buraya taşıyabilir veya oradan import edebiliriz.
# Şimdilik buraya taşıyalım:
def rgba_to_qcolor(rgba: tuple) -> QColor:
    if not isinstance(rgba, (list, tuple)) or len(rgba) < 3:
        # return QColor(Qt.GlobalColor.black) # QColor import edilmeli
        return QColor(0, 0, 0) # Varsayılan siyah
    r, g, b = [int(c * 255) for c in rgba[:3]]
    a = int(rgba[3] * 255) if len(rgba) > 3 else 255
    # return QColor(r, g, b, a) # QColor import edilmeli
    return QColor(r, g, b, a)

def draw_template(painter: QPainter, width: int, height: int, template_type: TemplateType, 
                  line_color: tuple, grid_color: tuple, line_spacing_pt: float, grid_spacing_pt: float, pt_to_px: float):
    """Seçili arka plan şablonunu QPainter ile çizer."""
    if template_type == TemplateType.PLAIN:
        return

    painter.save()
    pen = QPen()
    pen.setWidthF(1.0) # İnce çizgiler

    if template_type == TemplateType.LINED:
        spacing_px = line_spacing_pt * pt_to_px
        if spacing_px <= 0: 
            painter.restore()
            return
        pen.setColor(rgba_to_qcolor(line_color))
        painter.setPen(pen)
        y = 0.0
        while y < height:
            painter.drawLine(QPointF(0, y), QPointF(width, y))
            y += spacing_px

    elif template_type == TemplateType.GRID:
        spacing_px = grid_spacing_pt * pt_to_px
        if spacing_px <= 0: 
            painter.restore()
            return
        pen.setColor(rgba_to_qcolor(grid_color))
        painter.setPen(pen)
        # Dikey çizgiler
        x = 0.0
        while x < width:
            painter.drawLine(QPointF(x, 0), QPointF(x, height))
            x += spacing_px
        # Yatay çizgiler
        y = 0.0
        while y < height:
            painter.drawLine(QPointF(0, y), QPointF(width, y))
            y += spacing_px

    painter.restore()

def draw_pen_stroke(painter: QPainter, points: List[QPointF], color: tuple, width: float, line_style: str = 'solid'):
    """Verilen noktaları kullanarak bir kalem çizgisini QPainter ile çizer.
       Yuvarlak uçlar ve birleşimler kullanır.
       line_style: 'solid', 'dashed', 'dotted', 'dashdot', 'double', 'zigzag' olabilir.
    """
    if len(points) < 2:
        return

    def draw_zigzag(painter, points, color, width, amplitude=4, freq=12):
        painter.save()
        pen = QPen(rgba_to_qcolor(color))
        pen.setWidthF(max(1.0, width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i+1]
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = math.hypot(dx, dy)
            if length < 1e-3:
                continue
            steps = max(2, int(length // freq))
            if steps % 2 == 1:
                steps += 1
            zigzag_points = []
            for s in range(steps + 1):
                t = s / steps
                x = p1.x() + dx * t
                y = p1.y() + dy * t
                # Zigzag yönü: her adımda yukarı-aşağı
                if s % 2 == 1:
                    # Normale göre yukarı
                    nx = -dy / length
                    ny = dx / length
                    x += nx * amplitude
                    y += ny * amplitude
                zigzag_points.append(QPointF(x, y))
            for s in range(len(zigzag_points) - 1):
                painter.drawLine(zigzag_points[s], zigzag_points[s+1])
        painter.restore()

    def draw_double(painter, points, color, width, offset=3):
        painter.save()
        pen = QPen(rgba_to_qcolor(color))
        pen.setWidthF(max(1.0, width * 0.7))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        # Orta çizgiye normal vektör ile offset uygula
        for sign in [-1, 1]:
            offset_points = []
            for i in range(len(points)):
                if i == 0:
                    if len(points) > 1:
                        dx = points[1].x() - points[0].x()
                        dy = points[1].y() - points[0].y()
                    else:
                        dx, dy = 0, 0
                else:
                    dx = points[i].x() - points[i-1].x()
                    dy = points[i].y() - points[i-1].y()
                length = math.hypot(dx, dy)
                if length < 1e-3:
                    nx, ny = 0, 0
                else:
                    nx = -dy / length
                    ny = dx / length
                x = points[i].x() + sign * nx * offset
                y = points[i].y() + sign * ny * offset
                offset_points.append(QPointF(x, y))
            path = QPainterPath()
            path.moveTo(offset_points[0])
            for pt in offset_points[1:]:
                path.lineTo(pt)
            painter.drawPath(path)
        painter.restore()

    if line_style == 'zigzag':
        draw_zigzag(painter, points, color, width)
        return
    elif line_style == 'double':
        draw_double(painter, points, color, width)
        return

    path = QPainterPath()
    if len(points) > 1:
        path = QPainterPath()
        first_point = points[0]
        if isinstance(first_point, tuple) and len(first_point) > 0 and isinstance(first_point[0], QPointF):
            path.moveTo(first_point[0])
            for i in range(1, len(points)):
                point_data = points[i]
                if isinstance(point_data, tuple) and len(point_data) > 0 and isinstance(point_data[0], QPointF):
                    path.lineTo(point_data[0])
                else:
                    logging.warning(f"draw_pen_stroke: Beklenmedik nokta formatı (tuple içinde): {point_data}")
        elif isinstance(first_point, QPointF):
            path.moveTo(first_point)
            for i in range(1, len(points)):
                point_data = points[i]
                if isinstance(point_data, QPointF):
                     path.lineTo(point_data)
                else:
                    logging.warning(f"draw_pen_stroke: Beklenmedik nokta formatı (doğrudan): {point_data}")
        else:
            logging.error(f"draw_pen_stroke: Anlaşılamayan nokta listesi formatı. İlk eleman: {first_point}")
            return
        pen = QPen()
        pen.setColor(rgba_to_qcolor(color))
        pen.setWidthF(max(1.0, width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        if line_style == 'dashed':
            pen.setStyle(Qt.PenStyle.DashLine)
        elif line_style == 'dotted':
            pen.setStyle(Qt.PenStyle.DotLine)
        elif line_style == 'dashdot':
            pen.setStyle(Qt.PenStyle.DashDotLine)
        elif line_style == 'dashdotdot':
            pen.setStyle(Qt.PenStyle.DashDotDotLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

def draw_shape(painter: QPainter, shape_data: List[Any], line_style: str = 'solid'):
    logging.debug(f"draw_shape: tool_type={shape_data[0] if len(shape_data)>0 else None}, color={shape_data[1] if len(shape_data)>1 else None}, width={shape_data[2] if len(shape_data)>2 else None}, p1={shape_data[3] if len(shape_data)>3 else None}, p2={shape_data[4] if len(shape_data)>4 else None}, line_style={line_style}, fill_rgba={shape_data[6] if len(shape_data)>6 else None}")
    """Verilen shape_data ile şekil (çizgi, dikdörtgen, daire) çizer. line_style: 'solid', 'dashed', 'dotted', 'dashdot', 'double', 'zigzag' olabilir."""
    
    tool_type_from_data = shape_data[0] if len(shape_data) > 0 else None
    fill_rgba_from_data = shape_data[6] if len(shape_data) >= 7 else None
    # logging.debug(f"draw_shape called. ToolType from data: {tool_type_from_data}, Fill RGBA from data: {fill_rgba_from_data}, Received line_style: {line_style}") # KALDIRILDI

    tool_type, color_tuple, width = shape_data[:3]
    
    # Düzenlenebilir Çizgi için özel durum
    if tool_type == ToolType.EDITABLE_LINE:
        control_points = shape_data[3]  # 4. öğe kontrol noktaları listesidir
        line_style = shape_data[4] if len(shape_data) > 4 else 'solid'
        
        # Kontrol noktaları listesini kullanarak Bezier eğrilerini çiz
        if len(control_points) >= 4:
            painter.save()
            qcolor = rgba_to_qcolor(color_tuple)
            pen = QPen(qcolor, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            
            # Çizgi stilini ayarla
            if line_style == 'dashed':
                pen.setStyle(Qt.PenStyle.DashLine)
            elif line_style == 'dotted':
                pen.setStyle(Qt.PenStyle.DotLine)
            elif line_style == 'dashdot':
                pen.setStyle(Qt.PenStyle.DashDotLine)
            else:
                pen.setStyle(Qt.PenStyle.SolidLine)
                
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            # Bezier eğrisi path'ini oluştur
            path = QPainterPath()
            
            # Eğer kontrol noktaları kübik Bezier eğrileri için ayarlanmışsa
            if len(control_points) >= 4 and (len(control_points) - 1) % 3 == 0:
                # Standart kübik Bezier eğrisi çizimi
                path.moveTo(control_points[0])
                for i in range(0, len(control_points) - 3, 3):
                    if i + 3 < len(control_points):
                        path.cubicTo(
                            control_points[i + 1],  # c1
                            control_points[i + 2],  # c2
                            control_points[i + 3]   # p1
                        )
            else:
                # Düz çizgilerin yumuşatılmış versiyonu: her iki nokta arasına
                # otomatik olarak kübik Bezier eğrisi oluştur
                if len(control_points) >= 2:
                    path.moveTo(control_points[0])
                    
                    # Eğriliği kontrol etmek için yön vektörlerini ve kontrol noktalarını hesapla
                    # Catmull-Rom tipi spline interpolasyon yaklaşımı
                    tension = 0.3  # Düşük değerler daha yumuşak eğriler oluşturur (0-1 arası)
                    control_distance = 0.4  # Kontrol noktalarının ana noktalardan uzaklık faktörü
                    
                    # Her nokta çifti için kontrol noktaları hesapla
                    for i in range(len(control_points) - 1):
                        p0 = control_points[i]      # Mevcut nokta
                        p3 = control_points[i + 1]  # Sonraki nokta
                        
                        # İki nokta arasındaki mesafeyi hesapla
                        dx = p3.x() - p0.x()
                        dy = p3.y() - p0.y()
                        distance = math.sqrt(dx*dx + dy*dy)
                        
                        # Kontrol noktalarının yönlerini hesapla
                        # Önceki ve sonraki noktalardan yön vektörleri elde et
                        if i == 0:  # İlk nokta için
                            if len(control_points) > 2:  # En az 3 nokta varsa
                                # İlk iki segment kullanılarak yön hesapla
                                next_dx = control_points[2].x() - p3.x()
                                next_dy = control_points[2].y() - p3.y()
                                # Ters yönde ortalama eğim
                                tan_x = dx - next_dx * tension * 0.5
                                tan_y = dy - next_dy * tension * 0.5
                                
                                # Sonraki nokta için teğeti ayarla
                                next_tan_x = dx
                                next_tan_y = dy
                                
                                if i + 2 < len(control_points):  # Eğer yeterli nokta varsa
                                    next_tan_x = (dx + next_dx) * 0.5 * tension
                                    next_tan_y = (dy + next_dy) * 0.5 * tension
                            else:
                                # Sadece mevcut segment
                                tan_x = dx
                                tan_y = dy
                                next_tan_x = dx
                                next_tan_y = dy
                        elif i == len(control_points) - 2:  # Son nokta için
                            if len(control_points) > 2:
                                # Son iki segment kullanılarak yön hesapla
                                prev_dx = p0.x() - control_points[i - 1].x()
                                prev_dy = p0.y() - control_points[i - 1].y()
                                # Ortalama eğim
                                tan_x = prev_dx * tension * 0.5 + dx
                                tan_y = prev_dy * tension * 0.5 + dy
                            else:
                                # Sadece mevcut segment
                                tan_x = dx
                                tan_y = dy
                                
                            # Son nokta için sonraki teğeti ayarla (aynı yön)
                            next_tan_x = dx
                            next_tan_y = dy
                        else:
                            # Ara noktalar için önceki ve sonraki segmentlerden ortalama yön hesapla
                            prev_dx = p0.x() - control_points[i - 1].x()
                            prev_dy = p0.y() - control_points[i - 1].y()
                            next_dx = control_points[i + 2].x() - p3.x() if i + 2 < len(control_points) else 0
                            next_dy = control_points[i + 2].y() - p3.y() if i + 2 < len(control_points) else 0
                            
                            # Ortalama teğet yönü
                            tan_x = (prev_dx + dx) * 0.5 * tension
                            tan_y = (prev_dy + dy) * 0.5 * tension
                            
                            # Sonraki teğet için varsayılan değerleri ata
                            next_tan_x = dx
                            next_tan_y = dy
                            
                            # Eğer başka bir nokta daha varsa, gerçek değerleri hesapla
                            if i + 2 < len(control_points):
                                next_tan_x = (dx + next_dx) * 0.5 * tension
                                next_tan_y = (dy + next_dy) * 0.5 * tension
                        
                        # Teğet vektörü normalize et ve kontrol noktası uzaklığını ayarla
                        tan_len = math.sqrt(tan_x*tan_x + tan_y*tan_y)
                        if tan_len > 1e-6:  # Sıfıra bölmeyi önle
                            tan_x = tan_x / tan_len * distance * control_distance
                            tan_y = tan_y / tan_len * distance * control_distance
                        else:
                            tan_x = dx * control_distance
                            tan_y = dy * control_distance
                            
                        if i < len(control_points) - 2:
                            next_tan_len = math.sqrt(next_tan_x*next_tan_x + next_tan_y*next_tan_y)
                            if next_tan_len > 1e-6:
                                next_tan_x = next_tan_x / next_tan_len * distance * control_distance
                                next_tan_y = next_tan_y / next_tan_len * distance * control_distance
                            else:
                                next_tan_x = dx * control_distance
                                next_tan_y = dy * control_distance
                        
                        # Kontrol noktalarını hesapla
                        p1 = QPointF(p0.x() + tan_x, p0.y() + tan_y)
                        if i < len(control_points) - 2:
                            p2 = QPointF(p3.x() - next_tan_x, p3.y() - next_tan_y)
                        else:
                            p2 = QPointF(p3.x() - tan_x, p3.y() - tan_y)
                        
                        # Bezier eğrisi çiz
                        path.cubicTo(p1, p2, p3)
            
            painter.drawPath(path)
            painter.restore()
            return
    
    # Normal şekiller için mevcut kodun devamı
    p1, p2 = None, None
    if len(shape_data) > 4:
        p1, p2 = shape_data[3], shape_data[4]
    
    # line_style parametresi öncelikli, yoksa shape_data[5]'i kullan (serileştirme sonrası için)
    if len(shape_data) >= 6 and line_style == 'solid': # Eğer argüman olarak stil gelmemişse (solid varsayılan)
        line_style = shape_data[5] if shape_data[5] else 'solid' # Verideki stili al
    
    fill_rgba = None
    if len(shape_data) >= 7:
        fill_rgba = shape_data[6]

    def draw_zigzag_line(painter, p1, p2, color, width, amplitude=4, freq=12):
        painter.save()
        pen = QPen(rgba_to_qcolor(color))
        pen.setWidthF(max(1.0, width))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-9: # Çok küçük çizgiler için
            painter.restore()
            return 
        steps = max(2, int(length // freq))
        if steps % 2 == 1:
            steps += 1
        zigzag_points = []
        for s in range(steps + 1):
            t = s / steps
            x = p1.x() + dx * t
            y = p1.y() + dy * t
            if s % 2 == 1:
                nx = -dy / length
                ny = dx / length
                x += nx * amplitude
                y += ny * amplitude
            zigzag_points.append(QPointF(x, y))
        for s in range(len(zigzag_points) - 1):
            painter.drawLine(zigzag_points[s], zigzag_points[s+1])
        painter.restore()

    def draw_double_line(painter, p1, p2, color, width, offset=3):
        painter.save()
        pen = QPen(rgba_to_qcolor(color))
        pen.setWidthF(max(1.0, width * 0.7))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-9: # Çok küçük çizgiler için
            painter.restore()
            return
        nx = -dy / length
        ny = dx / length
        for sign in [-1, 1]:
            off_p1 = QPointF(p1.x() + sign * nx * offset, p1.y() + sign * ny * offset)
            off_p2 = QPointF(p2.x() + sign * nx * offset, p2.y() + sign * ny * offset)
            painter.drawLine(off_p1, off_p2)
        painter.restore()

    painter.save()
    qcolor = rgba_to_qcolor(color_tuple)
    pen = QPen(qcolor, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    # Set line style based on the provided argument or shape_data
    if line_style == 'dashed':
        pen.setStyle(Qt.PenStyle.DashLine)
    elif line_style == 'dotted':
        pen.setStyle(Qt.PenStyle.DotLine)
    elif line_style == 'dashdot':
        pen.setStyle(Qt.PenStyle.DashDotLine)
    else: # solid, double, zigzag ve diğerleri için SolidLine
        pen.setStyle(Qt.PenStyle.SolidLine)
        
    painter.setPen(pen)

    # --- YENİ: Dolgu (Fill) İşlemleri --- #
    if tool_type in [ToolType.RECTANGLE, ToolType.CIRCLE] and fill_rgba and fill_rgba[3] > 0:
        fill_qcolor = rgba_to_qcolor(fill_rgba)
        brush = QBrush(fill_qcolor)
        painter.setBrush(brush)
        # logging.debug(f"    draw_shape: Applying fill for {tool_type.name} with RGBA: {fill_rgba}") # KALDIRILDI
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush) # Dolgu yok
        # logging.debug(f"    draw_shape: NOT applying fill for {tool_type.name}. fill_rgba: {fill_rgba}") # KALDIRILDI
    # --- --- --- --- --- --- --- --- --- -- #

    logging.debug(f"  draw_shape (PRE-DRAW): Pen Color={painter.pen().color().name()}, Width={painter.pen().widthF()}, Style={painter.pen().style()}, Brush Style={painter.brush().style()}, Brush Color={painter.brush().color().name()}")

    if tool_type == ToolType.LINE:
        if line_style == 'double':
            draw_double_line(painter, p1, p2, qcolor, width)
        elif line_style == 'zigzag':
            draw_zigzag_line(painter, p1, p2, qcolor, width)
        else:
            painter.drawLine(p1, p2)
    elif tool_type == ToolType.RECTANGLE:
        rect = QRectF(p1, p2).normalized()
         # YENİ LOG
        logging.debug(f"    draw_shape: RECTANGLE. p1={p1}, p2={p2}, normalized_rect={rect}")
        painter.drawRect(rect)
    elif tool_type == ToolType.CIRCLE:
        rect = QRectF(p1, p2).normalized()
        painter.drawEllipse(rect)

    painter.restore()

def draw_temporary_eraser_path(painter: QPainter, path: List[QPointF], width: float):
    """Silme işlemi sırasında silginin izlediği geçici yolu çizer (QPainter ile)."""
    if len(path) < 2:
        return

    eraser_path = QPainterPath()
    eraser_path.moveTo(path[0])
    for i in range(1, len(path)):
        eraser_path.lineTo(path[i])

    pen = QPen()
    # Yarı saydam gri renk
    pen.setColor(QColor(128, 128, 128, 128))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    painter.save()
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(eraser_path)
    painter.restore()

def draw_temporary_pointer_stroke(painter: QPainter, 
                                points_with_ts: List[Tuple[QPointF, float]], 
                                base_color: tuple, 
                                base_width: float, 
                                duration: float,
                                # --- YENİ: Yapılandırma Parametreleri ---
                                glow_width_factor: float = 2.5, 
                                core_width_factor: float = 0.5, 
                                glow_alpha_factor: float = 0.55, # Artırıldı (0.4 -> 0.55)
                                core_alpha_factor: float = 0.9):
    """Geçici işaretçi çizgisini optimize edilmiş 2 katmanlı efektle çizer.
       Fade-out efekti: Çizgi, ilk noktadan son noktaya doğru yavaşça silinir.
    """
    if not points_with_ts or len(points_with_ts) < 2 or duration <= 0:
        return

    current_time = time.time()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    base_q_color = rgba_to_qcolor(base_color)
    original_alpha = base_q_color.alpha()
    pen = QPen()

    # --- Glow Path (tüm görünür noktalarla, ortalama alpha ile) ---
    visible_points = []
    visible_life_ratios = []
    for i in range(len(points_with_ts)):
        p, ts = points_with_ts[i]
        point_age = current_time - ts
        life_ratio = max(0.0, 1.0 - (point_age / duration))
        if life_ratio > 0.01:
            visible_points.append(p)
            visible_life_ratios.append(life_ratio)
    if len(visible_points) > 1:
        avg_life_ratio = sum(visible_life_ratios) / len(visible_life_ratios)
        # 1. Katman: Çok geniş ve daha yüksek alpha
        wide_glow_width = max(1.0, base_width * avg_life_ratio * glow_width_factor * 3.5)  # Genişlik artırıldı
        wide_glow_alpha = int(original_alpha * avg_life_ratio * glow_alpha_factor * 0.7)   # Alpha artırıldı (0.25 -> 0.7)
        if wide_glow_alpha > 0:
            glow_path = QPainterPath()
            glow_path.moveTo(visible_points[0])
            for p in visible_points[1:]:
                glow_path.lineTo(p)
            glow_color = QColor(base_q_color)
            # Glow rengini biraz daha açık yap (örneğin beyaza yaklaştır)
            glow_color = QColor(
                min(255, glow_color.red() + 60),
                min(255, glow_color.green() + 60),
                min(255, glow_color.blue() + 60),
                wide_glow_alpha
            )
            pen.setColor(glow_color)
            pen.setWidthF(wide_glow_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(glow_path)
        # 2. Katman: Normal glow
        avg_glow_width = max(1.0, base_width * avg_life_ratio * glow_width_factor * 1.5)  # Genişlik artırıldı
        avg_glow_alpha = int(original_alpha * avg_life_ratio * glow_alpha_factor * 0.9)   # Alpha artırıldı
        if avg_glow_alpha > 0:
            glow_path = QPainterPath()
            glow_path.moveTo(visible_points[0])
            for p in visible_points[1:]:
                glow_path.lineTo(p)
            glow_color = QColor(base_q_color)
            glow_color.setAlpha(avg_glow_alpha)
            pen.setColor(glow_color)
            pen.setWidthF(avg_glow_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(glow_path)

    # --- Core Segmentler: Her segment için ayrı alpha (fade-out) ---
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    core_color = QColor(Qt.GlobalColor.white)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for i in range(len(points_with_ts) - 1):
        p1, ts1 = points_with_ts[i]
        p2, ts2 = points_with_ts[i+1]
        point_age = current_time - ts1
        life_ratio = max(0.0, 1.0 - (point_age / duration))
        if life_ratio <= 0.01:
            continue
        core_width = max(1.0, base_width * life_ratio * core_width_factor)
        core_alpha = int(255 * life_ratio * core_alpha_factor)
        if core_alpha > 0:
            core_color.setAlpha(core_alpha)
            pen.setColor(core_color)
            pen.setWidthF(core_width)
            painter.setPen(pen)
            painter.drawLine(p1, p2)

    # --- Feather Glow: Çok katmanlı, yumuşak geçişli glow ---
    if len(visible_points) > 1:
        glow_path = QPainterPath()
        glow_path.moveTo(visible_points[0])
        for p in visible_points[1:]:
            glow_path.lineTo(p)
        for i in range(6, 0, -1):  # 6 katman, dıştan içe
            factor = i / 6.0
            width = base_width * glow_width_factor * (1.0 + factor * 2.5)
            alpha = int(original_alpha * glow_alpha_factor * factor * 0.5)
            if alpha <= 0:
                continue
            glow_color = QColor(base_q_color)
            glow_color.setAlpha(alpha)
            pen.setColor(glow_color)
            pen.setWidthF(width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(glow_path)

    painter.restore()

# draw_eraser_preview canvas içindeki paintEvent'in sonunda doğrudan çiziliyor, burada gerek yok.

# def draw_eraser_preview(canvas: 'DrawingCanvas'): 
#     ... (bu fonksiyon silinecek) ...
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QPen, QMouseEvent, QPainterPath, QTabletEvent
from PyQt6.QtCore import Qt, QPoint, QPointF
from scipy.interpolate import splprep, splev
import numpy as np
import logging # Logging importu eklendi

class DrawingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.strokes = [] # Stores B-spline data ({'control_points', 'knots', 'degree', 'u', 'thickness'})
        self.current_stroke = [] # Stores raw points and pressure for the current stroke [(QPoint, pressure)]
        self.selected_control_point = None # Tuple: (stroke_index, cp_index)
        self.drag_start_cp_pos = None    # Numpy array: Sürüklenen CP'nin başlangıç pozisyonu
        self.setMouseTracking(True) # Enable tracking even when no button is pressed
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, False) # TabletEvent için bunu False yapabiliriz
        self.default_line_thickness = 2 # YENİ: Varsayılan kalınlık
        self.default_stroke_color = (0.0, 0.0, 0.0, 1.0) # YENİ: Varsayılan renk (siyah)
        #logging.debug(f"DrawingWidget initialized. ID: {id(self)}, default_line_thickness: {self.default_line_thickness}") # YENİ LOG

    def setDefaultLineThickness(self, thickness):
        """Sets the default thickness for new strokes."""
        old_thickness = self.default_line_thickness
        self.default_line_thickness = thickness
        #logging.debug(f"DrawingWidget ID: {id(self)}. setDefaultLineThickness called. Old: {old_thickness}, New: {self.default_line_thickness}") # YENİ LOG

    # YENİ METOD: Varsayılan çizgi rengini ayarlar
    def setDefaultStrokeColor(self, color_tuple: tuple):
        """Sets the default color for new strokes."""
        if isinstance(color_tuple, tuple) and len(color_tuple) == 4:
            self.default_stroke_color = color_tuple
            #logging.debug(f"DrawingWidget ID: {id(self)}. setDefaultStrokeColor: {self.default_stroke_color}")
        else:
            #logging.warning(f"DrawingWidget ID: {id(self)}. setDefaultStrokeColor: Geçersiz renk formatı {color_tuple}. Varsayılan siyah kullanılacak.")
            self.default_stroke_color = (0.0, 0.0, 0.0, 1.0)

    # YENİ METOD: Verilen dünya koordinatına en yakın kontrol noktasını bulur.
    def _get_control_point_at(self, world_pos: QPointF, tolerance: float = 10.0) -> tuple[int, int] | None:
        """Verilen dünya koordinatına en yakın B-Spline kontrol noktasını bulur.
           (stroke_index, control_point_index) veya None döndürür.
        """
        # logging.debug(f"DrawingWidget ({id(self)}): _get_control_point_at searching at {world_pos}")
        for stroke_idx, stroke_data in enumerate(self.strokes):
            control_points_np = stroke_data.get('control_points')
            if control_points_np is not None:
                for cp_idx, cp_np in enumerate(control_points_np):
                    # cp_np, [x, y] şeklinde bir numpy array
                    cp_qpointf = QPointF(cp_np[0], cp_np[1])
                    # Basit manhattan uzaklığı veya Öklid mesafesi kullanılabilir
                    if (world_pos - cp_qpointf).manhattanLength() < tolerance:
                        # logging.debug(f"DrawingWidget ({id(self)}): CP found at stroke {stroke_idx}, cp_idx {cp_idx}")
                        return (stroke_idx, cp_idx)
        # logging.debug(f"DrawingWidget ({id(self)}): No CP found at {world_pos}")
        return None

    # YENİ METOD: Kontrol noktasını seçer
    def select_control_point(self, world_pos: QPointF, tolerance: float = 10.0) -> bool:
        """Kontrol noktasını seçer. Seçim başarılıysa True döndürür."""
        cp_info = self._get_control_point_at(world_pos, tolerance)
        if cp_info:
            stroke_idx, cp_idx = cp_info
            self.selected_control_point = cp_info
            # Taşıma başlangıç pozisyonunu sakla (numpy array olarak)
            stroke_data = self.strokes[stroke_idx]
            cp_np = stroke_data['control_points'][cp_idx]
            self.drag_start_cp_pos = cp_np.copy()  # Başlangıç pozisyonunun kopyasını al
            logging.debug(f"DrawingWidget: Control point selected at stroke {stroke_idx}, cp_idx {cp_idx}")
            self.update()
            return True
        else:
            self.selected_control_point = None
            self.drag_start_cp_pos = None
            return False

    # YENİ METOD: Seçili kontrol noktasını taşır
    def move_control_point(self, world_pos: QPointF) -> bool:
        """Seçili kontrol noktasını yeni pozisyona taşır. Başarılıysa True döndürür."""
        if not self.selected_control_point:
            return False
        
        stroke_idx, cp_idx = self.selected_control_point
        if 0 <= stroke_idx < len(self.strokes):
            stroke_data = self.strokes[stroke_idx]
            control_points = stroke_data.get('control_points')
            
            if control_points and 0 <= cp_idx < len(control_points):
                # Kontrol noktasını doğrudan güncelle - orijinal kodda olduğu gibi basit atama
                control_points[cp_idx] = np.array([world_pos.x(), world_pos.y()])
                
                # Eğrinin yeniden çizilmesi için sadece update() çağır
                # tck değişkenleri ve curve_points doğrudan paintEvent'te hesaplanacak
                self.update()
                return True
                
        return False

    # YENİ METOD: Kontrol noktası taşımayı bitirir
    def release_control_point(self) -> tuple:
        """Kontrol noktası taşımayı bitirir ve eski/yeni pozisyon bilgisini döndürür.
        (stroke_idx, cp_idx, old_pos, new_pos) ya da (None, None, None, None) şeklinde tuple döndürür.
        """
        result = (None, None, None, None)  # (stroke_idx, cp_idx, old_pos, new_pos)
        
        if self.selected_control_point and self.drag_start_cp_pos is not None:
            stroke_idx, cp_idx = self.selected_control_point
            if 0 <= stroke_idx < len(self.strokes):
                stroke_data = self.strokes[stroke_idx]
                control_points = stroke_data.get('control_points')
                
                if control_points and 0 <= cp_idx < len(control_points):
                    old_pos = self.drag_start_cp_pos.copy()  # Başlangıç pozisyonu
                    new_pos = control_points[cp_idx].copy()  # Güncel pozisyon
                    result = (stroke_idx, cp_idx, old_pos, new_pos)
        
        # Taşıma durumunu temizle
        self.selected_control_point = None
        self.drag_start_cp_pos = None
        self.update()
        
        return result

    def tabletPressEvent(self, world_pos: QPointF, event: QTabletEvent):
        # Bu metodun çağrıldığı yerdeki (DrawingCanvas) current_tool kontrolü
        # zaten hangi modda olduğumuzu belirlemeli.
        # Eğer DrawingCanvas, NODE_SELECTOR modundaysa burayı direkt çağırmayacak,
        # bunun yerine _get_control_point_at'i kullanacak.
        # Dolayısıyla burada sadece yeni çizgi çizme mantığı kalabilir.

        # Yeni bir stroke başlat
        self.current_stroke = [(world_pos, event.pressure())] 
        self.selected_control_point = None # Yeni çizgi başlarken CP seçimini kaldır
        self.drag_start_cp_pos = None
        #logging.debug(f"DrawingWidget: Starting new stroke at {world_pos}")
        self.update()

    def tabletMoveEvent(self, world_pos: QPointF, event: QTabletEvent):
        # Aynı şekilde, bu metod da sadece yeni çizgi çizilirken çağrılmalı.
        # NODE_SELECTOR modunda DrawingCanvas kendi CP taşıma mantığını işletir.
        if self.current_stroke: # Sadece aktif bir çizim varsa devam et
            self.current_stroke.append((world_pos, event.pressure()))
            self.update()

    def _preprocess_stroke_points(self, stroke_points_with_pressure):
        # Ardışık tekrarlı noktaları kaldır
        if not stroke_points_with_pressure:
            return []
        unique_points_with_pressure = [stroke_points_with_pressure[0]]
        for i in range(1, len(stroke_points_with_pressure)):
            if stroke_points_with_pressure[i][0] != stroke_points_with_pressure[i-1][0]:
                unique_points_with_pressure.append(stroke_points_with_pressure[i])
        return unique_points_with_pressure

    def _downsample_points(self, points_with_pressure, factor=5, min_points=4):
        if len(points_with_pressure) < min_points:
            return points_with_pressure
        downsampled = points_with_pressure[::factor]
        if len(downsampled) < min_points:
            return points_with_pressure
        return downsampled

    def tabletReleaseEvent(self, world_pos: QPointF, event):
        created_stroke_data = None
        if self.current_stroke:
            if len(self.current_stroke) > 1:
                # Ardışık tekrarlı noktaları kaldır
                unique_points_with_pressure = self._preprocess_stroke_points(self.current_stroke)
                # Downsampling uygula
                downsampled_points_with_pressure = self._downsample_points(unique_points_with_pressure, factor=5, min_points=4)
                points_np = np.array([[p.x(), p.y()] for p, pressure in downsampled_points_with_pressure])
                k = 3  # Kübik spline
                if points_np.shape[0] < k + 1:
                    logging.warning(f"DrawingWidget: B-spline oluşturmak için yeterli nokta yok ({points_np.shape[0]} adet). En az {k+1} nokta gerekli. Stroke atlanıyor.")
                    self.current_stroke = []
                    self.update()
                    return None
                try:
                    s_factor = len(points_np) * 3.0  # Dinamik smoothing
                    tck, u = splprep(points_np.T, s=s_factor, k=k)
                    # Kontrol noktalarını (K,2) formatına getir
                    if isinstance(tck[1], list) and len(tck[1]) == 2:
                        control_points_combined_np_array = np.vstack((tck[1][0], tck[1][1])).T
                    elif isinstance(tck[1], np.ndarray) and tck[1].shape[0] == 2:
                        control_points_combined_np_array = tck[1].T
                    elif isinstance(tck[1], np.ndarray) and tck[1].shape[1] == 2:
                        control_points_combined_np_array = tck[1]
                    else:
                        logging.error(f"DrawingWidget: Beklenmeyen tck[1] formatı: {type(tck[1])}, shape: {tck[1].shape if hasattr(tck[1], 'shape') else 'N/A'}")
                        raise ValueError("Beklenmeyen tck[1] formatı splprep'ten")
                    control_points_list_np = [np.array(cp_row) for cp_row in control_points_combined_np_array]
                    x_fine, y_fine = splev(np.linspace(0, u[-1], 2000), tck)
                    curve_points_np = np.column_stack((x_fine, y_fine))
                    created_stroke_data = {
                        'control_points': control_points_list_np,
                        'knots': tck[0],
                        'degree': tck[2],
                        'u': u,
                        'thickness': self.default_line_thickness,
                        'color': self.default_stroke_color,
                        'original_points_with_pressure': downsampled_points_with_pressure,
                        'curve_points': curve_points_np
                    }
                except Exception as e:
                    logging.error(f"DrawingWidget: B-spline oluşturulurken hata: {e}", exc_info=True)
                    created_stroke_data = None
            self.current_stroke = []
        self.update()
        return created_stroke_data

    def set_world_to_screen_func(self, func):
        self._world_to_screen = func

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        world_to_screen = getattr(self, '_world_to_screen', lambda p: p)
        for i, stroke_data in enumerate(self.strokes):
            control_points = stroke_data.get('control_points')
            knots = stroke_data.get('knots')
            degree = stroke_data.get('degree')
            u = stroke_data.get('u')
            if control_points is None or knots is None or degree is None or u is None:
                continue
            stroke_thickness = stroke_data.get('thickness', self.default_line_thickness)
            try:
                if 'curve_points' in stroke_data and stroke_data['curve_points'] is not None:
                    curve_points = stroke_data['curve_points']
                    path = QPainterPath()
                    path.moveTo(world_to_screen(QPointF(curve_points[0][0], curve_points[0][1])))
                    for j in range(1, len(curve_points)):
                        path.lineTo(world_to_screen(QPointF(curve_points[j][0], curve_points[j][1])))
                else:
                    tck = (knots, np.array(control_points).T, degree)
                    x_fine, y_fine = splev(np.linspace(0, u[-1], 2000), tck)
                    path = QPainterPath()
                    path.moveTo(world_to_screen(QPointF(x_fine[0], y_fine[0])))
                    for j in range(1, len(x_fine)):
                        path.lineTo(world_to_screen(QPointF(x_fine[j], y_fine[j])))
                stroke_pen = QPen(Qt.GlobalColor.black, stroke_thickness, Qt.PenStyle.SolidLine, 
                                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                stroke_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(stroke_pen)
                painter.drawPath(path)
            except Exception as e:
                continue
            painter.save()
            if self.selected_control_point and self.selected_control_point[0] == i:
                selected_idx = self.selected_control_point[1]
                for cp_idx, cp in enumerate(control_points):
                    if cp_idx == selected_idx:
                        painter.setPen(QPen(Qt.GlobalColor.cyan, 2, Qt.PenStyle.SolidLine))
                        painter.setBrush(Qt.GlobalColor.red)
                        screen_cp = world_to_screen(QPointF(cp[0], cp[1]))
                        painter.drawRect(screen_cp.x() - 5, screen_cp.y() - 5, 10, 10)
                    else:
                        painter.setPen(QPen(Qt.GlobalColor.red, 5, Qt.PenStyle.SolidLine))
                        screen_cp = world_to_screen(QPointF(cp[0], cp[1]))
                        painter.drawPoint(screen_cp)
            else:
                painter.setPen(QPen(Qt.GlobalColor.red, 5, Qt.PenStyle.SolidLine))
                for cp in control_points:
                    screen_cp = world_to_screen(QPointF(cp[0], cp[1]))
                    painter.drawPoint(screen_cp)
            painter.restore()
        if len(self.current_stroke) > 1:
            painter.save()
            for i in range(len(self.current_stroke) - 1):
                point1, pressure1 = self.current_stroke[i]
                point2, pressure2 = self.current_stroke[i+1]
                pen_width = 1 + pressure1 * 9
                pen = QPen(Qt.GlobalColor.blue, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(world_to_screen(point1), world_to_screen(point2))
            painter.restore()

    def mousePressEvent(self, event: QMouseEvent):
        pass

    def mouseMoveEvent(self, event: QMouseEvent):
        pass

    def mouseReleaseEvent(self, event: QMouseEvent):
        pass 
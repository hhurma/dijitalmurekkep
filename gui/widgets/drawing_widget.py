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

    def tabletReleaseEvent(self, world_pos: QPointF, event: QTabletEvent):
        # Aynı şekilde, bu metod da sadece yeni çizgi biterken çağrılmalı.
        # NODE_SELECTOR modunda komut oluşturma DrawingCanvas'ta.
        created_stroke_data = None # Dönecek değeri başlat
        if self.current_stroke:
            if len(self.current_stroke) > 1:
                # B-spline oluştur ve sakla
                points_np = np.array([[p.x(), p.y()] for p, pressure in self.current_stroke])
                original_points_with_pressure = [(p, pressure) for p, pressure in self.current_stroke]
                
                # YENİ: Minimum nokta sayısı kontrolü
                k = 3 # Kübik spline için derece
                if points_np.shape[0] < k + 1:
                    logging.warning(f"DrawingWidget: B-spline oluşturmak için yeterli nokta yok ({points_np.shape[0]} adet). En az {k+1} nokta gerekli. Stroke atlanıyor.")
                    self.current_stroke = [] # Mevcut stroke'u temizle
                    self.update()
                    return None # Fonksiyondan çık ve None döndür

                try:
                    # smoothing değerini artırarak kontrol noktası sayısını azaltmayı dene
                    # Önceki sabit değer 5.0 idi. Şimdi nokta sayısına orantılı yapalım.
                    smoothing_factor = points_np.shape[0] * 0.75 
                    #logging.debug(f"DrawingWidget: splprep çağrılıyor. Nokta sayısı: {points_np.shape[0]}, Smoothing faktörü: {smoothing_factor:.2f}, Derece: {k}")
                    tck, u = splprep(points_np.T, s=smoothing_factor, k=k)
                    # tck = (knots, control_points_scipy, degree)
                    # control_points_scipy, scipy'den (K, Ndim) şeklinde bir array döner (K kontrol noktası, Ndim=2)
                    
                    # Düzeltilmiş kontrol noktası saklama:
                    # tck[1] muhtemelen [array_x_coords, array_y_coords] listesini veya (2,K) array'ini veriyor.
                    # Bunları birleştirip (K,2) formatına getirelim.
                    if isinstance(tck[1], list) and len(tck[1]) == 2: # Eğer [array_x, array_y] listesi ise
                        control_points_x = tck[1][0]
                        control_points_y = tck[1][1]
                        # Stack them vertically (as columns) then transpose to get (K, 2)
                        control_points_combined_np_array = np.vstack((control_points_x, control_points_y)).T
                    elif isinstance(tck[1], np.ndarray) and tck[1].shape[0] == 2: # Eğer (2,K) ndarray ise
                        control_points_combined_np_array = tck[1].T
                    elif isinstance(tck[1], np.ndarray) and tck[1].shape[1] == 2: # Eğer (K,2) ndarray ise (zaten istediğimiz format)
                        control_points_combined_np_array = tck[1]
                    else:
                        logging.error(f"DrawingWidget: Beklenmeyen tck[1] formatı: {type(tck[1])}, shape: {tck[1].shape if hasattr(tck[1], 'shape') else 'N/A'}")
                        # Hata durumunda boş liste ile devam etmeyi veya hata fırlatmayı seçebiliriz.
                        control_points_list_np = [] # Geçici olarak boş liste
                        raise ValueError("Beklenmeyen tck[1] formatı splprep'ten") # veya raise

                    # Şimdi her bir satırı (yani [x,y] çiftini) alıp ayrı bir np.array olarak listeye ekliyoruz.
                    control_points_list_np = [np.array(cp_row) for cp_row in control_points_combined_np_array]

                    # YENİ LOG: control_points_list_np'nin formatını kontrol et
                    #logging.debug(f"DrawingWidget tabletReleaseEvent: control_points_list_np (len: {len(control_points_list_np) if control_points_list_np is not None else 'None'}):")
                    if control_points_list_np:
                        for idx, cp_arr in enumerate(control_points_list_np):
                            #logging.debug(f"  CP[{idx}]: type={type(cp_arr)}, shape={cp_arr.shape if hasattr(cp_arr, 'shape') else 'N/A'}, content={cp_arr}")
                            pass
                    # YENİ LOG SONU

                    created_stroke_data = { # new_stroke_data -> created_stroke_data
                        'control_points': control_points_list_np, # list of np.array([x,y])
                        'knots': tck[0], # numpy array
                        'degree': tck[2], # int
                        'u': u, # numpy array (parametre değerleri)
                        'thickness': self.default_line_thickness, # YENİ: Kalınlığı kaydet
                        'color': self.default_stroke_color, # YENİ: Rengi kaydet
                        'original_points_with_pressure': original_points_with_pressure # YENİ: Orijinal noktaları sakla
                    }
                    # self.strokes.append(new_stroke_data) # <-- BU SATIR KALDIRILDI
                    #logging.debug(f"DrawingWidget ID: {id(self)}. tabletReleaseEvent: Storing new stroke with thickness: {self.default_line_thickness}")
                    #logging.debug(f"DrawingWidget: New B-spline stroke added to self.strokes. Count: {len(self.strokes)}")
                except Exception as e:
                    #logging.error(f"DrawingWidget: B-spline oluşturulurken hata: {e}", exc_info=True)
                    created_stroke_data = None # Hata durumunda None ata
            self.current_stroke = []
        self.update()
        return created_stroke_data # Oluşturulan stroke verisini veya None döndür

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Default pen for B-splines - This will be set per stroke now
        # pen = QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        # painter.setPen(pen)

        # Draw completed B-splines and control points
        if not self.strokes:
            #logging.debug(f"DrawingWidget ID: {id(self)}. paintEvent: self.strokes is empty. Nothing to draw for B-splines.") # YENİ LOG
            pass
        for i, stroke_data in enumerate(self.strokes): # YENİ: index için enumerate
            #logging.debug(f"DrawingWidget ID: {id(self)}. paintEvent: Processing stroke {i}. Data keys: {list(stroke_data.keys()) if isinstance(stroke_data, dict) else 'Not a dict'}") # YENİ LOG
            pass
            control_points = stroke_data.get('control_points') # .get() ile daha güvenli erişim
            knots = stroke_data.get('knots')
            degree = stroke_data.get('degree')
            u = stroke_data.get('u')
            
            if control_points is None or knots is None or degree is None or u is None:
                #logging.error(f"DrawingWidget ID: {id(self)}. paintEvent: Stroke {i} is missing critical B-spline data. Skipping.")
                continue # Bu stroke'u atla

            # Get original points with pressure (not directly used for B-spline path rendering here)
            # original_points_with_pressure = stroke_data.get('original_points_with_pressure', []) # Yorum satırı yapıldı
            stroke_thickness_from_data = stroke_data.get('thickness') # YENİ: Önce direkt al
            stroke_thickness = stroke_thickness_from_data if stroke_thickness_from_data is not None else self.default_line_thickness # YENİ: Sonra fallback

            # YENİ LOG: Çizim sırasındaki kalınlık ve tipi
            #logging.debug(f"DrawingWidget ID: {id(self)}. paintEvent: Drawing stroke {i} with effective_thickness: {stroke_thickness} (type: {type(stroke_thickness)}). (From stroke: {stroke_thickness_from_data}, Current widget default: {self.default_line_thickness})")

            # Reconstruct tck from stored components
            try:
                # Emin olmak için control_points'in numpy array ve doğru yapıda olduğunu varsayalım
                # veya burada bir kontrol/dönüşüm eklenebilir.
                tck = (knots, np.asarray(control_points).T, degree)
            except Exception as e:
                #logging.error(f"DrawingWidget ID: {id(self)}. paintEvent: Error reconstructing tck for stroke {i}: {e}. Control points: {control_points}")
                continue # Bu stroke'u atla

            # Define pen for this specific stroke
            try:
                # stroke_thickness'ın float olduğundan emin olalım
                pen = QPen(Qt.GlobalColor.black, float(stroke_thickness), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
            except Exception as e:
                #logging.error(f"DrawingWidget ID: {id(self)}. paintEvent: Error creating QPen for stroke {i} with thickness {stroke_thickness}: {e}")
                # Belki varsayılan bir pen ile devam edilebilir veya bu stroke atlanabilir
                default_pen_for_error = QPen(Qt.GlobalColor.magenta, 1) # Hata durumunda farklı renkte çiz
                painter.setPen(default_pen_for_error)

            # Draw the B-spline curve
            try:
                x_fine, y_fine = splev(np.linspace(0, u[-1], 100), tck)
                path = QPainterPath()
                path.moveTo(QPointF(x_fine[0], y_fine[0]))
                for i in range(1, len(x_fine)):
                    path.lineTo(QPointF(x_fine[i], y_fine[i]))
                painter.drawPath(path)
            except Exception as e:
                #logging.error(f"DrawingWidget ID: {id(self)}. paintEvent: Error drawing B-spline for stroke {i}: {e}")
                continue # Bu stroke'u atla

            # Draw control points
            painter.save() # Save painter state
            painter.setPen(QPen(Qt.GlobalColor.red, 5, Qt.PenStyle.SolidLine))
            for cp in control_points:
                painter.drawPoint(QPointF(cp[0], cp[1]))
            painter.restore() # Restore painter state

        # Draw the current raw stroke with pressure sensitivity
        if len(self.current_stroke) > 1:
            painter.save() # Save painter state
            # Draw segments with varying thickness based on pressure
            for i in range(len(self.current_stroke) - 1):
                point1, pressure1 = self.current_stroke[i]
                point2, pressure2 = self.current_stroke[i+1]

                # Map pressure (0.0 to 1.0) to pen width (e.g., 1 to 10)
                pen_width = 1 + pressure1 * 9 # Vary from 1 to 10

                pen = QPen(Qt.GlobalColor.blue, pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(point1, point2)
            painter.restore() # Restore painter state 
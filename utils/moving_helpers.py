# utils/moving_helpers.py
"""Seçili öğeleri taşıma ile ilgili yardımcı fonksiyonlar."""
import logging
from typing import List, Any
from PyQt6.QtCore import QPointF
import numpy as np # YENİ: NumPy importu
from gui.enums import ToolType # ToolType enumunu import et

# Type definitions for clarity
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]
BsplineStrokeDataType = dict # B-Spline stroke verisi için

def move_item(item_data: Any, dx: float, dy: float, item_type: str | None = None):
    """Verilen öğeyi dx, dy kadar taşır.
    item_type belirtilirse, o tipe göre işlem yapar.
    Belirtilmezse, item_data'nın yapısına göre tipini tahmin etmeye çalışır.
    """
    if item_data is None: # None kontrolü eklendi
        #logging.warning("move_item: Boş öğe verisi (None), taşıma yapılamadı.")
        return

    # Eğer item_type dışarıdan belirtilmişse onu kullan
    type_to_process = item_type

    if type_to_process is None:
        # Tip belirtilmemişse, eski tahmin mantığını kullan (çok güvenilir değil)
        is_shape_heuristic = isinstance(item_data, list) and len(item_data) > 0 and isinstance(item_data[0], ToolType) and len(item_data) >= 5 and isinstance(item_data[3], QPointF)
        is_line_heuristic = isinstance(item_data, list) and not is_shape_heuristic and len(item_data) >= 3 and isinstance(item_data[2], list)
        if is_shape_heuristic:
            type_to_process = 'shapes' # Veya item_data[0] (ToolType) daha spesifik olabilir
        elif is_line_heuristic:
            type_to_process = 'lines'
        # B-spline için sezgisel bir tahmin zor, bu yüzden item_type'ın belirtilmesi önemli.

    try:
        delta_np = np.array([dx, dy]) # NumPy array olarak delta
        delta_qpoint = QPointF(dx, dy) # QPointF olarak delta

        if type_to_process == 'lines':
            # item_data: [color, width, points_list, style?]
            if isinstance(item_data, list) and len(item_data) >= 3 and isinstance(item_data[2], list):
                points: List[QPointF] = item_data[2]
                if points: # Boş liste değilse
                    # QPointF listesini NumPy array'ine dönüştür
                    points_np = np.array([[p.x(), p.y()] for p in points])
                    # Vektörel toplama yap
                    moved_points_np = points_np + delta_np
                    # NumPy array'ini tekrar QPointF listesine dönüştür
                    item_data[2] = [QPointF(p[0], p[1]) for p in moved_points_np]
            else:
                #logging.warning(f"move_item: 'lines' tipi için beklenmeyen veri formatı: {item_data}")
                pass

        elif type_to_process == 'shapes':
            # item_data: [ToolType, color, width, p1, p2, style?, fill?]
            if isinstance(item_data, list) and len(item_data) > 0 and isinstance(item_data[0], ToolType):
                tool_type: ToolType = item_data[0]
                if tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE] and len(item_data) >= 5:
                    if isinstance(item_data[3], QPointF) and isinstance(item_data[4], QPointF):
                        item_data[3] += delta_qpoint
                        item_data[4] += delta_qpoint
                # EDITABLE_LINE (eski Bezier) veya PATH için kontrol noktaları item_data[3]'te bir liste
                elif tool_type in [ToolType.EDITABLE_LINE, ToolType.PATH] and len(item_data) >= 4 and isinstance(item_data[3], list):
                    control_points: List[QPointF] = item_data[3]
                    if control_points: # Boş liste değilse
                        # QPointF listesini NumPy array'ine dönüştür
                        points_np = np.array([[p.x(), p.y()] for p in control_points])
                        # Vektörel toplama yap
                        moved_points_np = points_np + delta_np
                        # NumPy array'ini tekrar QPointF listesine dönüştür
                        item_data[3] = [QPointF(p[0], p[1]) for p in moved_points_np]
                else:
                    #logging.warning(f"move_item: Desteklenmeyen veya eksik verili şekil tipi '{tool_type}' için taşıma atlandı.")
                    pass
            else:
                #logging.warning(f"move_item: 'shapes' tipi için beklenmeyen veri formatı: {item_data}")
                pass

        elif type_to_process == 'bspline_strokes':
            # item_data: B-Spline stroke sözlüğü (dict)
            if isinstance(item_data, dict) and 'control_points' in item_data:
                control_points_np = item_data['control_points']
                if isinstance(control_points_np, np.ndarray) and control_points_np.ndim == 2 and control_points_np.shape[1] == 2:
                    # Her bir kontrol noktasını (N,2) array'de kaydır
                    item_data['control_points'] = control_points_np + delta_np
                else:
                    #logging.warning(f"move_item: 'bspline_strokes' için 'control_points' beklenen formatta değil (numpy array N,2). Veri: {control_points_np}")
                    pass
            else:
                #logging.warning(f"move_item: 'bspline_strokes' tipi için beklenmeyen veri formatı veya 'control_points' eksik. Veri: {item_data}")
                pass
        
        elif type_to_process is None:
            #logging.warning(f"move_item: Öğe tipi belirlenemedi, taşıma yapılamadı. Veri: {item_data}")
            pass
        else:
            #logging.warning(f"move_item: Bilinmeyen öğe tipi '{type_to_process}', taşıma yapılamadı.")
            pass

    except IndexError as e:
        #logging.error(f"move_item: Öğe verisi işlenirken Index hatası ({type_to_process=}): {e}. Veri: {item_data}", exc_info=True)
        pass
    except TypeError as e:
        #logging.error(f"move_item: Öğe verisi işlenirken Type hatası ({type_to_process=}, örn. QPointF bekleniyordu): {e}. Veri: {item_data}", exc_info=True)
        pass
    except Exception as e:
        #logging.error(f"move_item: Taşıma sırasında beklenmedik hata ({type_to_process=}): {e}. Veri: {item_data}", exc_info=True) 
        pass
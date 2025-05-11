# utils/moving_helpers.py
"""Seçili öğeleri taşıma ile ilgili yardımcı fonksiyonlar."""
import logging
from typing import List, Any
from PyQt6.QtCore import QPointF
from gui.enums import ToolType # ToolType enumunu import et

# Type definitions for clarity
LineDataType = List[Any] # [color_tuple, width_float, List[QPointF]]
ShapeDataType = List[Any] # [ToolType_enum, color_tuple, width_float, QPointF, QPointF, ...]

def move_item(item_data: List[Any], dx: float, dy: float):
    """Verilen öğeyi (çizgi veya şekil) dx, dy kadar taşır."""
    if not item_data:
        logging.warning("move_item: Boş öğe verisi, taşıma yapılamadı.")
        return

    # Item type detection (basic check, could be more robust)
    # Lines typically have a list of QPointF at index 2
    # Shapes typically have ToolType enum at index 0 and QPointF at 3 and 4
    is_shape = isinstance(item_data[0], ToolType) and len(item_data) >= 5 and isinstance(item_data[3], QPointF)
    is_line = not is_shape and len(item_data) >= 3 and isinstance(item_data[2], list)

    try:
        delta = QPointF(dx, dy)

        if is_line:
            # Move all points in the line
            points: List[QPointF] = item_data[2]
            for i in range(len(points)):
                points[i] += delta
            # logging.debug(f"Line moved by ({dx}, {dy})")

        elif is_shape:
            tool_type: ToolType = item_data[0]
            # Most shapes are defined by p1 and p2
            if tool_type in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
                p1: QPointF = item_data[3]
                p2: QPointF = item_data[4]
                item_data[3] = p1 + delta
                item_data[4] = p2 + delta
                # logging.debug(f"Shape {tool_type.name} moved by ({dx}, {dy})")
            else:
                 logging.warning(f"move_item: Desteklenmeyen şekil tipi {tool_type} için taşıma atlandı.")
        else:
            logging.warning(f"move_item: Tanınmayan öğe formatı, taşıma yapılamadı. Veri: {item_data}")

    except IndexError as e:
        logging.error(f"move_item: Öğe verisi işlenirken Index hatası: {e}. Veri: {item_data}", exc_info=True)
    except TypeError as e:
        logging.error(f"move_item: Öğe verisi işlenirken Type hatası (örn. QPointF bekleniyordu): {e}. Veri: {item_data}", exc_info=True)
    except Exception as e:
        logging.error(f"move_item: Taşıma sırasında beklenmedik hata: {e}. Veri: {item_data}", exc_info=True) 
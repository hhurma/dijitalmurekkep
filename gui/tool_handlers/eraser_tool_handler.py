"""
Silgi (Eraser) aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING, Dict, List, Tuple, Any # EraseChanges için Any, Dict, List, Tuple gerekebilir

from PyQt6.QtCore import QPointF
# QTabletEvent bu dosyada doğrudan kullanılmıyor gibi, event argümanı handle_eraser_press'e gelmiyor.

from utils import erasing_helpers
from utils.commands import EraseCommand

# EraseChanges type alias (erasing_helpers içinde tanımlıysa oradan import edilebilir)
EraseChanges = Dict[str, Dict[int, Any]] 

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas

def handle_eraser_press(canvas: 'DrawingCanvas', pos: QPointF):
    """Silgi aracı için basma olayını yönetir."""
    logging.debug("Eraser Press: Start erasing.")
    canvas.erasing = True
    canvas.last_move_pos = pos 
    canvas.current_eraser_path = [pos] 
    # current_stroke_changes DrawingCanvas'ta bir özellikti, burada yönetilip yönetilmeyeceğine karar verilmeli.
    # Şimdilik EraseCommand tüm değişiklikleri tek seferde aldığı için burada tutmaya gerek yok gibi.
    # canvas.current_stroke_changes: EraseChanges = {'lines': {}, 'shapes': {}} 
    # canvas.update() # Ana handler'da yönetilecek

def handle_eraser_move(canvas: 'DrawingCanvas', pos: QPointF):
    """Silgi aracı için hareket olayını yönetir."""
    if not canvas.erasing:
        return
    canvas.current_eraser_path.append(pos)
    canvas.last_move_pos = pos # Bu silgi için ne kadar gerekli? Çizim önizlemesi için olabilir.
    canvas.update() # Silgi yolunu göstermek için güncelle

def handle_eraser_release(canvas: 'DrawingCanvas', pos: QPointF):
    """Silgi aracı için bırakma olayını yönetir."""
    logging.debug("Eraser Release: Finish erasing.")
    if not canvas.erasing: # Eğer zaten silme modunda değilsek bir şey yapma
        # Bu durum normalde oluşmamalı, press ile erasing True yapılır.
        logging.warning("Eraser Release: Not in erasing mode.")
        return
        
    canvas.erasing = False # Silme modunu bitir
    canvas.current_eraser_path.append(pos) # Son noktayı da yola ekle

    if len(canvas.current_eraser_path) > 1: # Silinecek bir yol varsa
        calculated_changes = erasing_helpers.calculate_erase_changes(
            canvas.lines, canvas.shapes, canvas.current_eraser_path, canvas.eraser_width
        )
        logging.debug(f"Calculated erase changes: {calculated_changes}")

        if calculated_changes['lines'] or calculated_changes['shapes']:
            try:
                command = EraseCommand(canvas, calculated_changes) 
                canvas.undo_manager.execute(command)
                logging.debug(f"EraseCommand created and executed.")
            except Exception as e:
                logging.error(f"EraseCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
        else:
             logging.debug("No effective changes calculated after erase stroke, no command created.")
    else:
        logging.debug("Eraser path too short, no erase command created.")

    canvas.current_eraser_path = [] # Silgi yolunu her zaman temizle
    
    # temporary_drawing_active silgi ile doğrudan ilgili değil, DrawingCanvas'ta genel bir sıfırlamada yapılabilir.
    # Ancak _handle_eraser_release içinde vardı, uyumluluk için eklenebilir veya genel mantıkta çözülebilir.
    # Şimdilik DrawingCanvas'taki genel sıfırlama mantığına bırakalım.
    # canvas.temporary_drawing_active = False 

    canvas.update() # Canvas'ı son durumu yansıtacak şekilde güncelle 
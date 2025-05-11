"""
Geçici İşaretçi (Temporary Pointer) aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING
import copy # copy.deepcopy için
import time # time.time() için

from PyQt6.QtCore import QPointF
# QTabletEvent bu dosyada doğrudan kullanılmıyor.

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas

def handle_temporary_drawing_press(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için basma olayını yönetir."""
    canvas.temporary_drawing_active = True
    canvas.current_temporary_line_points = [(pos, time.time())] 
    logging.debug("Temporary drawing started.")
    # canvas.update() # Ana handler veya DrawingCanvas yönetecek

def handle_temporary_drawing_move(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için hareket olayını yönetir."""
    if canvas.temporary_drawing_active:
        canvas.current_temporary_line_points.append((pos, time.time()))
        canvas.update() # Geçici çizgiyi anlık göstermek için güncelle

def handle_temporary_drawing_release(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için bırakma olayını yönetir."""
    logging.debug(f"[DEBUG] handle_temporary_drawing_release çağrıldı. temporary_drawing_active={canvas.temporary_drawing_active}, current_temporary_line_points={len(canvas.current_temporary_line_points)}")
    if canvas.temporary_drawing_active and len(canvas.current_temporary_line_points) > 0: # Tek nokta bile olsa işlem yapabiliriz (isteğe bağlı)
        # Son noktayı da ekle (eğer hareket varsa zaten eklenmiş olacak ama press-release için)
        if len(canvas.current_temporary_line_points) == 1 and canvas.current_temporary_line_points[0][0] != pos:
             canvas.current_temporary_line_points.append((pos, time.time()))
        elif not canvas.current_temporary_line_points or canvas.current_temporary_line_points[-1][0] != pos:
            canvas.current_temporary_line_points.append((pos, time.time()))

        if len(canvas.current_temporary_line_points) > 1:
            # Ayarlardan renk/kalınlık alınacak
            temp_color_tuple = (canvas.temp_pointer_color.redF(), 
                                canvas.temp_pointer_color.greenF(), 
                                canvas.temp_pointer_color.blueF(), 
                                canvas.temp_pointer_color.alphaF())
            temp_width = canvas.temp_pointer_width
            # Sadece QPointF noktalarını al
            points_only = [p[0] for p in canvas.current_temporary_line_points]
            # DrawLineCommand ile undo/redo sistemine ekle
            try:
                from utils.commands import DrawLineCommand
            except ImportError:
                import sys
                sys.path.append('..')
                from utils.commands import DrawLineCommand
            line_data = [temp_color_tuple, temp_width, points_only, 'solid'] # Çizgi tipi sabit: 'solid'
            command = DrawLineCommand(canvas, line_data)
            logging.debug(f"[DEBUG] Komut oluşturuldu. undo_manager var mı? {hasattr(canvas, 'undo_manager') and canvas.undo_manager is not None}")
            if hasattr(canvas, 'undo_manager') and canvas.undo_manager:
                canvas.undo_manager.execute(command)
                canvas.undo_manager._emit_stack_signals()  # Undo/redo butonlarını güncelle (ilk çizimde de)
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()  # Qt event loop'u işle, buton enable olsun
                logging.debug(f"Temporary path çizimi undo/redo sistemine eklendi. Nokta sayısı: {len(points_only)}")
            else:
                logging.warning("Undo manager bulunamadı, path çizimi komut olarak eklenemedi!")
        else:
            logging.debug("Temporary drawing too short (or just a click), not added as a line.")

    canvas.temporary_drawing_active = False
    canvas.current_temporary_line_points = [] # Her zaman temizle
    canvas.update() # Canvas'ı son durumu yansıtacak şekilde güncelle 

    # --- YENİ: Undo/redo butonlarını güncelle (MainWindow üzerinden) ---
    try:
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.activeWindow()
        if main_window and hasattr(main_window, 'update_actions_state'):
            main_window.update_actions_state()
    except Exception as e:
        logging.warning(f"Undo/redo buton güncellemesi yapılamadı: {e}") 
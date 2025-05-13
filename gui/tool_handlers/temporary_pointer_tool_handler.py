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
    # logging.debug("Temporary drawing started.")
    # canvas.update() # Ana handler veya DrawingCanvas yönetecek

def handle_temporary_drawing_move(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için hareket olayını yönetir."""
    if canvas.temporary_drawing_active:
        canvas.current_temporary_line_points.append((pos, time.time()))
        canvas.update() # Geçici çizgiyi anlık göstermek için güncelle

def handle_temporary_drawing_release(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için bırakma olayını yönetir."""
    if canvas.temporary_drawing_active and len(canvas.current_temporary_line_points) > 1:
        temp_color_tuple = (canvas.temp_pointer_color.redF(), 
                            canvas.temp_pointer_color.greenF(), 
                            canvas.temp_pointer_color.blueF(), 
                            canvas.temp_pointer_color.alphaF())
        temp_width = canvas.temp_pointer_width
        # Kalan noktaları temporary_lines'a ekle (zaman damgaları ile)
        canvas.temporary_lines.append([
            canvas.current_temporary_line_points.copy(),  # Noktalar (QPointF, timestamp)
            temp_color_tuple,    # Renk
            temp_width,          # Kalınlık
            time.time(),         # Çizgi eklenme zamanı
            False                # Animasyon başladı mı
        ])
    canvas.temporary_drawing_active = False
    canvas.current_temporary_line_points = [] # Her zaman temizle
    canvas.update() # Canvas'ı son durumu yansıtacak şekilde güncelle

    # --- Undo/redo butonlarını güncelle (MainWindow üzerinden) ---
    try:
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.activeWindow()
        if main_window and hasattr(main_window, 'update_actions_state'):
            main_window.update_actions_state()
    except Exception as e:
        logging.warning(f"Undo/redo buton güncellemesi yapılamadı: {e}") 
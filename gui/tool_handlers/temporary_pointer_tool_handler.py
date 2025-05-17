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
    current_time = time.time()
    pressure = event.pressure() if hasattr(event, 'pressure') else 0.5 # Basınç yoksa varsayılan
    canvas.current_temporary_line_points = [{
        'point': pos,
        'timestamp': current_time,
        'pressure': pressure,
        'line_end_time': current_time + canvas.temporary_line_duration
    }]
    # canvas.update() # Güncelleme ana tablet_event handler'da veya canvas.add_point ile yapılmalı
    logging.debug(f"Temporary pointer press: {pos}, count: {len(canvas.current_temporary_line_points)}")

def handle_temporary_drawing_move(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için hareket olayını yönetir."""
    if canvas.temporary_drawing_active:
        current_time = time.time()
        pressure = event.pressure() if hasattr(event, 'pressure') else 0.5
        canvas.current_temporary_line_points.append({
            'point': pos,
            'timestamp': current_time,
            'pressure': pressure,
            'line_end_time': current_time + canvas.temporary_line_duration
        })
        canvas.update() # Geçici çizgiyi anlık göstermek için güncelle
        # logging.debug(f"Temporary pointer move: {pos}, count: {len(canvas.current_temporary_line_points)}")

def handle_temporary_drawing_release(canvas: 'DrawingCanvas', pos: QPointF, event):
    """Geçici çizim aracı için bırakma olayını yönetir."""
    # Noktalar zaten current_temporary_line_points içinde ve line_end_time'ları ayarlı.
    # DrawingCanvas._check_temporary_lines ve paintEvent solma ve silme işini yapacak.
    
    # Sadece çizimin aktif olmadığını belirt
    canvas.temporary_drawing_active = False
    
    # current_temporary_line_points listesini TEMİZLEME!
    # canvas.current_temporary_line_points = [] # ESKİ - BU SATIR SORUNA NEDEN OLUYORDU

    # canvas.temporary_lines listesi artık kullanılmıyor.
    # if canvas.temporary_drawing_active and len(canvas.current_temporary_line_points) > 1:
    #     temp_color_tuple = (canvas.temp_pointer_color.redF(), 
    #                         canvas.temp_pointer_color.greenF(), 
    #                         canvas.temp_pointer_color.blueF(), 
    #                         canvas.temp_pointer_color.alphaF())
    #     temp_width = canvas.temp_pointer_width
    #     canvas.temporary_lines.append([\n            canvas.current_temporary_line_points.copy(),\n            temp_color_tuple,\n            temp_width,\n            time.time(),\n            False\n        ])

    logging.debug(f"Temporary pointer release. Points count: {len(canvas.current_temporary_line_points)}. Active: {canvas.temporary_drawing_active}")
    canvas.update() # Canvas'ı son durumu yansıtacak şekilde güncelle (solma başlayacak)

    # Undo/redo butonları için ana pencereyi bulma kısmı şimdilik kalabilir,
    # ancak idealde bu canvas veya mainwindow'un sorumluluğunda olmalı.
    try:
        from PyQt6.QtWidgets import QApplication
        main_window = QApplication.activeWindow()
        if main_window and hasattr(main_window, 'update_actions_state'):
            main_window.update_actions_state()
    except Exception as e:
        logging.warning(f"Undo/redo buton güncellemesi yapılamadı (temp_pointer_release): {e}") 
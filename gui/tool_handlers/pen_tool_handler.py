"""
Kalem aracı için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QTabletEvent # QTabletEvent burada kullanılacak

from utils import erasing_helpers
from utils.commands import DrawLineCommand, EraseCommand

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas # ../drawing_canvas.py olarak düzeltildi

def handle_pen_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """Kalem basma olayını yönetir."""
    # logging.debug(f"handle_pen_press: Tool={canvas.current_tool.name}, WorldPos={pos}, Button={event.button()}")
    right_button_pressed = event.button() == Qt.MouseButton.RightButton

    # --- YENİ: Önceki çizgiyi finalize et --- #
    if not right_button_pressed and canvas.drawing and len(canvas.current_line_points) > 1:
        final_points = [QPointF(p.x(), p.y()) for p in canvas.current_line_points]
        line_data = [
            canvas.current_color,
            canvas.current_pen_width,
            final_points,
            canvas.line_style
        ]
        command = DrawLineCommand(canvas, line_data)
        canvas.undo_manager.execute(command)
        logging.debug(f"Pen Press: Önceki çizgi finalize edildi ve komut olarak eklendi. Nokta sayısı: {len(final_points)}")
        canvas.drawing = False
        canvas.current_line_points = []
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

    if right_button_pressed:
        logging.debug("Pen Press with Stylus Button (Right Click mapped): Starting temporary erase.")
        canvas.temporary_erasing = True
        canvas.erasing = True # Silme işlemini aktif et
        canvas.last_move_pos = pos 
        canvas.current_eraser_path = [pos]
        canvas.drawing = False # Çizim yapmıyoruz
    else:
        logging.debug("Pen Press: Start drawing line.")
        canvas.drawing = True
        canvas.temporary_erasing = False # Geçici silmeyi kapat
        canvas.current_line_points = [pos]
    # canvas.update() # Bu, ana tablet handler'da çağrılmalı veya DrawingCanvas kendi içinde yönetmeli

def handle_pen_move(canvas: 'DrawingCanvas', pos: QPointF):
    """Kalem hareket olayını yönetir."""
    # logging.debug(f"handle_pen_move: Drawing={canvas.drawing}, TempErasing={canvas.temporary_erasing}, WorldPos={pos}")
    if canvas.temporary_erasing: # Eğer geçici silme modundaysak
        if not canvas.erasing: # Bir şekilde erasing kapandıysa (beklenmedik)
             logging.warning("Pen Move: temporary_erasing is True but erasing is False! Forcing erase.")
             canvas.erasing = True # Tekrar aktif et
             # Başlangıç noktasını da ekleyelim, eğer current_eraser_path boşsa
             if not canvas.current_eraser_path and not canvas.last_move_pos.isNull():
                 canvas.current_eraser_path = [canvas.last_move_pos, pos]
             elif not canvas.current_eraser_path and canvas.last_move_pos.isNull():
                  canvas.current_eraser_path = [pos] # Sadece mevcut pozisyon
             else: # current_eraser_path zaten varsa devam et
                 canvas.current_eraser_path.append(pos)
        else:
             canvas.current_eraser_path.append(pos)
        canvas.last_move_pos = pos # Son konumu güncelle
        canvas.update() # Geçici silgi yolunu göstermek için güncelle
    elif canvas.drawing: # Normal çizim modundaysak
        canvas.current_line_points.append(pos)
        # canvas.update() # Çizgiyi anlık olarak göstermek için güncelle

def handle_pen_release(canvas: 'DrawingCanvas', pos: QPointF, event):
    #logging.debug(f"[pen_tool_handler] handle_pen_release çağrıldı. Drawing={canvas.drawing}, TempErasing={canvas.temporary_erasing}, WorldPos={pos}")
    """Kalem bırakma olayını yönetir."""
    # logging.debug(f"handle_pen_release: Drawing={canvas.drawing}, TempErasing={canvas.temporary_erasing}, WorldPos={pos}")
    
    # --- GEÇİCİ SİLME KONTROLÜ (Stylus Butonu ile) --- #
    if canvas.temporary_erasing and canvas.current_eraser_path:
        logging.debug("Pen Release with Stylus Button: Finalizing temporary erase.")
        canvas.temporary_erasing = False # Geçici silmeyi bitir
        canvas.erasing = False # Ana silme modunu da bitir (önemli!)

        if len(canvas.current_eraser_path) > 1: # En az 2 nokta varsa silme işlemi yap
             calculated_changes = erasing_helpers.calculate_erase_changes(
                 canvas.lines, canvas.shapes, canvas.current_eraser_path, canvas.eraser_width
             )
             logging.debug(f"Calculated temporary erase changes: {calculated_changes}")
             if calculated_changes['lines'] or calculated_changes['shapes']:
                 try:
                     # EraseCommand'a canvas referansını doğru şekilde veriyoruz.
                     command = EraseCommand(canvas, calculated_changes)
                     canvas.undo_manager.execute(command)
                     logging.debug(f"Temporary EraseCommand created and executed.")
                     
                     # Sayfayı değiştirilmiş olarak işaretle ve sinyal gönder
                     if canvas._parent_page:
                         canvas._parent_page.mark_as_modified()
                     if hasattr(canvas, 'content_changed'):
                         canvas.content_changed.emit()
                 except Exception as e:
                     logging.error(f"Temporary EraseCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)
             else:
                  logging.debug("No effective changes calculated after temporary erase stroke, no command created.")
        else:
            logging.debug("Temporary erase path too short, no erase command created.")

        canvas.current_eraser_path = [] # Yolu her zaman temizle
        canvas.drawing = False          # Çizim yapmıyorduk, güvenliğe alalım
        canvas.current_line_points = [] # Bunu da temizleyelim
        # canvas.update() # Ana handler veya DrawingCanvas update etmeli

    # --- NORMAL ÇİZİM KONTROLÜ --- #
    elif canvas.drawing and canvas.current_line_points:
        #logging.debug("Pen Release: Finalizing drawing line.")
        if len(canvas.current_line_points) > 1: # En az 2 nokta varsa çizgi oluştur
            final_points = [QPointF(p.x(), p.y()) for p in canvas.current_line_points]
            line_data = [
                canvas.current_color,
                canvas.current_pen_width,
                final_points,
                canvas.line_style  # Stil bilgisini ekle
            ]
            # DrawLineCommand'a canvas referansını doğru şekilde veriyoruz.
            command = DrawLineCommand(canvas, line_data)
            canvas.undo_manager.execute(command)
            #logging.debug(f"Pen Release: DrawLineCommand executed with {len(final_points)} points.")
            
            # Sayfayı değiştirilmiş olarak işaretle ve sinyal gönder
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            if hasattr(canvas, 'content_changed'):
                canvas.content_changed.emit()
        else:
            logging.debug("Pen Release: Line too short, not added to commands.")

        canvas.drawing = False # Çizim bitti
        canvas.current_line_points = [] # Çizim listesini TEMİZLE
        # canvas.update() # Ana handler veya DrawingCanvas update etmeli
    
    # --- Diğer Durumlar (Beklenmedik) --- #
    else:
         if not canvas.temporary_erasing and not canvas.drawing:
              logging.debug("Pen Release: No active drawing or temporary erasing to finalize.")
         elif not canvas.current_line_points and canvas.drawing:
              logging.debug("Pen Release: Drawing was active but no points were recorded.")
         elif not canvas.current_eraser_path and canvas.temporary_erasing: # Bu durum yukarıda handle ediliyor olmalı
              logging.debug("Pen Release: Temporary erasing was active but no path was recorded (should be handled).")
         
         # Her ihtimale karşı durumları sıfırla
         canvas.drawing = False
         canvas.temporary_erasing = False
         canvas.erasing = False # Silmeyi de kapat
         canvas.current_line_points = []
         canvas.current_eraser_path = []
         # canvas.update()

# </rewritten_file> etiketi kaldırılacak. 
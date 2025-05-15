"""
Şekil araçları (Çizgi, Dikdörtgen, Daire) için tablet olaylarını yöneten yardımcı fonksiyonlar.
"""
import logging
from typing import TYPE_CHECKING
import copy

from PyQt6.QtCore import QPointF

from ..enums import ToolType
from utils.commands import DrawShapeCommand
from utils.commands import DrawBsplineCommand

# ToolType, DrawShapeCommand gibi importlar DrawingCanvas'tan veya ilgili modüllerden gelecek.
# Şimdilik TYPE_CHECKING içinde canvas üzerinden erişilecekler gibi varsayalım.
# Eğer doğrudan ihtiyaç olursa, buraya eklenecekler.

if TYPE_CHECKING:
    from ..drawing_canvas import DrawingCanvas
    # from utils.commands import DrawShapeCommand # Yukarı taşındı ve doğrudan import edildi

def handle_shape_press(canvas: 'DrawingCanvas', pos: QPointF):
    """Şekil çizimi için basma olayını yönetir."""
    # --- YENİ: Önceki şekli finalize et --- #
    if canvas.drawing_shape and (canvas.shape_start_point != canvas.shape_end_point):
        if (canvas.shape_end_point - canvas.shape_start_point).manhattanLength() > 2:
            shape_data = [
                canvas.current_tool,
                canvas.current_color,
                canvas.current_pen_width,
                canvas.shape_start_point,
                canvas.shape_end_point,
                canvas.line_style
            ]
            if canvas.current_tool in [ToolType.RECTANGLE, ToolType.CIRCLE]:
                fill_r, fill_g, fill_b, fill_a = canvas.current_fill_rgba
                actual_fill_a = fill_a if canvas.fill_enabled else 0.0
                actual_fill_rgba_tuple = (fill_r, fill_g, fill_b, actual_fill_a)
                shape_data.append(actual_fill_rgba_tuple)
            try:
                tool_type = shape_data[0]
                color = shape_data[1]
                width = shape_data[2]
                p1 = shape_data[3]
                p2 = shape_data[4]
                line_style = shape_data[5]
                fill_rgba = shape_data[6] if len(shape_data) > 6 else None
                command = DrawShapeCommand(canvas, 
                                         tool_type, color, width, 
                                         p1, p2, line_style, 
                                         fill_rgba)
            except Exception as e:
                logging.error(f"shape_tool_handler: Önceki şekil finalize edilirken hata: {e}. Data: {shape_data}", exc_info=True)
                command = None
            if command:
                canvas.undo_manager.execute(command)
                if canvas._parent_page: 
                    canvas._parent_page.mark_as_modified()
        canvas.drawing = False
        canvas.drawing_shape = False
        canvas.shape_start_point = QPointF()
        canvas.shape_end_point = QPointF()
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
    canvas.drawing = True
    canvas.drawing_shape = True
    # --- YENİ: Grid'e snap --- #
    if canvas.current_tool == ToolType.LINE and getattr(canvas, 'snap_lines_to_grid', False):
        canvas.shape_start_point = canvas._snap_point_to_grid(pos)
        canvas.shape_end_point = canvas._snap_point_to_grid(pos)
    else:
        canvas.shape_start_point = pos
        canvas.shape_end_point = pos # Başlangıçta bitişi de aynı yapalım
    # logging.debug(f"Shape Press: Start drawing {canvas.current_tool.name} at {pos}") # KALDIRILDI
    # canvas.update() # Bu, ana tablet handler'da veya DrawingCanvas'ta yönetilmeli

def handle_shape_move(canvas: 'DrawingCanvas', pos: QPointF):
    """Şekil çizimi için hareket olayını yönetir."""
    if canvas.drawing_shape: # Sadece şekil çizimi aktifse güncelle
        # --- YENİ: Grid'e snap --- #
        if canvas.current_tool == ToolType.LINE and getattr(canvas, 'snap_lines_to_grid', False):
            canvas.shape_end_point = canvas._snap_point_to_grid(pos)
        else:
            canvas.shape_end_point = pos
        canvas.update() # Geçici şekli göstermek için canvas'ı güncelle

def handle_shape_release(canvas: 'DrawingCanvas', pos: QPointF):
    logging.debug("handle_shape_release: fonksiyon başı")
    """Şekil çizimi için bırakma olayını yönetir."""
    if canvas.drawing_shape:
        # --- YENİ: Grid'e snap --- #
        if canvas.current_tool == ToolType.LINE and getattr(canvas, 'snap_lines_to_grid', False):
            canvas.shape_end_point = canvas._snap_point_to_grid(pos)
        else:
            canvas.shape_end_point = pos # Son konumu al
        if (canvas.shape_end_point - canvas.shape_start_point).manhattanLength() > 2: 
            shape_data = [
                canvas.current_tool,
                canvas.current_color,
                canvas.current_pen_width,
                canvas.shape_start_point,
                canvas.shape_end_point,
                canvas.line_style
            ]
            if canvas.current_tool in [ToolType.RECTANGLE, ToolType.CIRCLE]:
                fill_r, fill_g, fill_b, fill_a = canvas.current_fill_rgba
                actual_fill_a = fill_a if canvas.fill_enabled else 0.0
                actual_fill_rgba_tuple = (fill_r, fill_g, fill_b, actual_fill_a)
                shape_data.append(actual_fill_rgba_tuple)
            try:
                tool_type = shape_data[0]
                color = shape_data[1]
                width = shape_data[2]
                p1 = shape_data[3]
                p2 = shape_data[4]
                line_style = shape_data[5]
                fill_rgba = shape_data[6] if len(shape_data) > 6 else None
                command = DrawShapeCommand(canvas, 
                                         tool_type, color, width, 
                                         p1, p2, line_style, 
                                         fill_rgba)
            except IndexError as e:
                logging.error(f"shape_tool_handler: Hata - shape_data'dan parametre alınırken IndexError: {e}. Data: {shape_data}", exc_info=True)
                command = None
            except Exception as e:
                logging.error(f"shape_tool_handler: Hata - DrawShapeCommand oluşturulurken bilinmeyen hata: {e}. Data: {shape_data}", exc_info=True)
                command = None
            if command:
                # logging.debug("UndoManager: execute çağrılıyor (DrawShapeCommand).")
                canvas.undo_manager.execute(command)
                logging.debug("UndoManager: execute çağrısı bitti (DrawShapeCommand).")
                if canvas._parent_page: 
                    canvas._parent_page.mark_as_modified()
                # Sayfanın değiştiğini belirten sinyali gönderelim
                if hasattr(canvas, 'content_changed'):
                    canvas.content_changed.emit()
                # logging.debug(f"shape_tool_handler: DrawShapeCommand pushed for {tool_type.name}.") # KALDIRILDI
            else:
                logging.error("shape_tool_handler: DrawShapeCommand oluşturulamadığı için undo yığınına eklenemedi.")
        else:
            # logging.debug("Shape Release: Shape too small or invalid, not added to commands.") # KALDIRILDI
            pass # Küçük şekiller için bir işlem yapılmıyorsa pass eklenebilir
        canvas.drawing = False
        canvas.drawing_shape = False
        canvas.shape_start_point = QPointF()
        canvas.shape_end_point = QPointF()
        canvas.update()
    else:
         # logging.debug("Shape Release: drawing_shape was False. No action taken.") # KALDIRILDI
         pass # drawing_shape False ise bir işlem yapılmıyorsa pass eklenebilir 

    # B-Spline (düzenlenebilir çizgi) ile çizim tamamlandıysa, havuza ekle
    if canvas.current_tool == ToolType.EDITABLE_LINE and hasattr(canvas, 'b_spline_widget'):
        if hasattr(canvas.b_spline_widget, 'strokes') and canvas.b_spline_widget.strokes:
            new_stroke_data = canvas.b_spline_widget.strokes[-1]
            command = DrawBsplineCommand(canvas, new_stroke_data)
            canvas.undo_manager.execute(command)
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            if hasattr(canvas, 'content_changed'):
                canvas.content_changed.emit()
            canvas.drawing = False
            canvas.drawing_shape = False
            canvas.shape_start_point = QPointF()
            canvas.shape_end_point = QPointF()
            canvas.update()
            return 
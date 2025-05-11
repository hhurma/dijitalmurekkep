# handlers/canvas_handler.py
import logging
from typing import TYPE_CHECKING
from PyQt6.QtGui import QColor, QTabletEvent
from gui.enums import ToolType
from PyQt6.QtCore import QPointF
from . import image_handler

if TYPE_CHECKING:
    from gui.arayuz import MainWindow
    from gui.page_manager import PageManager
    from gui.drawing_canvas import DrawingCanvas, TemplateType

def handle_clear_canvas(page_manager: 'PageManager'):
    """Aktif canvas'ı temizleme işlemini tetikler."""
    if not page_manager:
        logging.error("handle_clear_canvas: page_manager None.")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug("Handling clear canvas action...")
            canvas.clear_canvas() # Bu metod zaten command kullanıyor
        else:
            logging.error("handle_clear_canvas: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_clear_canvas: Aktif sayfa bulunamadı.")

def handle_set_template(page_manager: 'PageManager', template_type: 'TemplateType'):
    """Aktif canvas'ın şablonunu ayarlar."""
    if not page_manager:
        logging.error("handle_set_template: page_manager None.")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug(f"Handling set template: {template_type}")
            canvas.set_template(template_type)
        else:
            logging.error("handle_set_template: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_set_template: Aktif sayfa bulunamadı.")

def handle_set_pen_color(page_manager: 'PageManager', color: QColor):
    """Aktif canvas'ın kalem rengini ayarlar."""
    if not page_manager or not color.isValid():
        logging.error(f"handle_set_pen_color: page_manager None veya geçersiz renk: {color}")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug(f"Handling set pen color: {color.name()}")
            canvas.set_color(color) # DrawingCanvas'taki metodu çağır
        else:
            logging.error("handle_set_pen_color: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_set_pen_color: Aktif sayfa bulunamadı.")

def handle_set_pen_width(page_manager: 'PageManager', width: int):
    """Aktif canvas'ın kalem kalınlığını ayarlar."""
    if not page_manager or width <= 0:
        logging.error(f"handle_set_pen_width: page_manager None veya geçersiz kalınlık: {width}")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug(f"Handling set pen width: {width}")
            canvas.set_pen_width(float(width)) # DrawingCanvas float bekliyor
        else:
            logging.error("handle_set_pen_width: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_set_pen_width: Aktif sayfa bulunamadı.")

def handle_set_eraser_width(page_manager: 'PageManager', width: int):
    """Aktif canvas'ın silgi kalınlığını ayarlar."""
    if not page_manager or width <= 0:
        logging.error(f"handle_set_eraser_width: page_manager None veya geçersiz kalınlık: {width}")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug(f"Handling set eraser width: {width}")
            canvas.set_eraser_width(float(width)) # DrawingCanvas float bekliyor
        else:
            logging.error("handle_set_eraser_width: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_set_eraser_width: Aktif sayfa bulunamadı.") 

def handle_canvas_click(main_window: 'MainWindow', page_manager: 'PageManager', world_pos: QPointF, event: QTabletEvent):
    """Canvas'a tıklanıldığında aktif araca göre ilgili işlemi yapar."""
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        logging.warning("handle_canvas_click: Aktif sayfa veya canvas bulunamadı.")
        return
        
    canvas = current_page.drawing_canvas
    current_tool = canvas.current_tool
    
    logging.debug(f"handle_canvas_click: Tool={current_tool.name}, Pos={world_pos}")

    if current_tool == ToolType.IMAGE_SELECTOR:
        image_handler.handle_image_click(main_window, page_manager, world_pos)
    elif current_tool == ToolType.SELECTOR:
        logging.debug("handle_canvas_click: SELECTOR aracı için işlem canvas_tablet_handler'a bırakıldı.")
        pass 
    # Diğer araçların (Pen, Eraser, Shape) tıklama olayları genellikle
    # doğrudan canvas_tablet_handler içindeki handle_tablet_press ile başlar.
    # Bu fonksiyon daha çok seçim modları ve boş alana tıklama için. 
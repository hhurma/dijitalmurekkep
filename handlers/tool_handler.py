# handlers/tool_handler.py
import logging

# Gerekli importlar buraya eklenecek
# from gui.page_manager import PageManager
# from gui.drawing_canvas import ToolType

def handle_set_active_tool(page_manager, tool):
    """Aktif aracı ayarlar."""
    if not page_manager:
        logging.error("handle_set_active_tool: page_manager None.")
        return

    current_page = page_manager.get_current_page()
    if current_page:
        canvas = current_page.get_canvas()
        if canvas:
            logging.debug(f"Handling set active tool: {tool}")
            canvas.set_tool(tool)
        else:
             logging.error("handle_set_active_tool: Aktif sayfanın canvas'ı bulunamadı.")
    else:
        logging.warning("handle_set_active_tool: Aktif sayfa bulunamadı.") 
# handlers/page_handler.py
import logging
from typing import TYPE_CHECKING
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea # Veya başka diyaloglar
from gui.enums import Orientation # Orientation import et

if TYPE_CHECKING:
    from gui.page import Page
    from gui.page_manager import PageManager

# Gerekli importlar buraya eklenecek
# from gui.page_manager import PageManager

def handle_add_page(page_manager):
    """Yeni sayfa ekleme işlemini tetikler."""
    if page_manager:
        logging.debug("Handling add page action...")
        page_manager.add_page()
    else:
        logging.error("handle_add_page çağrıldı ancak page_manager None.")

def handle_remove_current_page(page_manager):
    """Aktif sayfayı silme işlemini tetikler."""
    if page_manager:
        logging.debug("Handling remove current page action...")
        page_manager.remove_current_page()
    else:
        logging.error("handle_remove_current_page çağrıldı ancak page_manager None.")

def handle_next_page(page_manager):
    """Sonraki sayfaya gitme işlemini tetikler."""
    if page_manager:
        logging.debug("Handling next page action...")
        page_manager.go_to_next_page()
    else:
        logging.error("handle_next_page çağrıldı ancak page_manager None.")

def handle_previous_page(page_manager):
    """Önceki sayfaya gitme işlemini tetikler."""
    if page_manager:
        logging.debug("Handling previous page action...")
        page_manager.go_to_previous_page()
    else:
        logging.error("handle_previous_page çağrıldı ancak page_manager None.")

def handle_set_orientation(page_manager, orientation: Orientation):
    """Aktif sayfanın yönünü ayarlar."""
    if page_manager:
        current_page_index = page_manager.currentIndex()
        scroll_area = page_manager.widget(current_page_index)
        current_page = None
        if isinstance(scroll_area, QScrollArea):
            widget_inside = scroll_area.widget()
            # Döngüsel import sorununu önlemek için sınıf adını string olarak kontrol ediyoruz
            if widget_inside.__class__.__name__ == 'Page':
                current_page = widget_inside

        if current_page:
            logging.debug(f"Handling set orientation to {orientation.name} for page {current_page.page_number}")
            current_page.orientation = orientation
            
            canvas = current_page.get_canvas()
            if canvas:
                canvas.load_background_template_image()
            
            main_window = None
            parent = page_manager.parent()
            if parent and hasattr(parent, 'update_orientation_actions_check_state'):
                main_window = parent
                main_window.update_orientation_actions_check_state(orientation)
            else:
                logging.warning("handle_set_orientation: MainWindow referansı alınamadı veya metod yok.")
        else:
            logging.warning(f"Yön ayarlanamadı: Geçerli sayfa bulunamadı veya Page tipinde değil (indeks: {current_page_index})")
    else:
        logging.error("handle_set_orientation çağrıldı ancak page_manager None.")

# if TYPE_CHECKING:
#     # Burada TYPE_CHECKING için gerekli kodları ekleyebilirsiniz 
#     pass # Ya da boş bırak 
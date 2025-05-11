"""
Kes, kopyala ve yapıştır işlemleri için handler fonksiyonları.
Bu fonksiyonlar GUI'den bağımsızdır ve sadece canvas ile çalışır.
"""
import logging
import copy
from typing import Any, Dict, List
from PyQt6.QtCore import QPointF
import uuid
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsPixmapItem
from utils.commands import PasteItemsCommand, DeleteItemsCommand

# Basit bir uygulama içi clipboard (sadece bellek)
_CLIPBOARD: Dict[str, Any] = {
    'items': [],  # Kopyalanan/kesilen öğeler
    'type': None  # 'lines', 'shapes', 'images' veya karışık
}

def handle_copy_selection(canvas) -> bool:
    """Seçili öğeleri kopyalar (clipboard'a alır)."""
    if not hasattr(canvas, 'selected_item_indices') or not canvas.selected_item_indices:
        logging.info("handle_copy_selection: Seçili öğe yok, kopyalama yapılmadı.")
        return False
    global _CLIPBOARD
    _CLIPBOARD['items'] = []
    for item_type, idx in canvas.selected_item_indices:
        if item_type == 'lines' and 0 <= idx < len(canvas.lines):
            _CLIPBOARD['items'].append(('lines', copy.deepcopy(canvas.lines[idx])))
        elif item_type == 'shapes' and 0 <= idx < len(canvas.shapes):
            _CLIPBOARD['items'].append(('shapes', copy.deepcopy(canvas.shapes[idx])))
        elif item_type == 'images' and hasattr(canvas._parent_page, 'images') and 0 <= idx < len(canvas._parent_page.images):
            img = canvas._parent_page.images[idx]
            # Sadece temel alanları kopyala (QPixmap ve pixmap_item hariç)
            img_copy = {
                'path': img.get('path'),
                'rect': img.get('rect'),
                'angle': img.get('angle', 0.0),
                'uuid': img.get('uuid', None)
            }
            _CLIPBOARD['items'].append(('images', img_copy))
    _CLIPBOARD['type'] = 'mixed' if len(_CLIPBOARD['items']) > 1 else (_CLIPBOARD['items'][0][0] if _CLIPBOARD['items'] else None)
    logging.info(f"handle_copy_selection: {_CLIPBOARD['type']} türünde {len(_CLIPBOARD['items'])} öğe kopyalandı.")
    return True

def handle_cut_selection(canvas) -> bool:
    logging.debug(f"handle_cut_selection: BAŞLANGIÇ shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    """Seçili öğeleri keser (clipboard'a alır ve canvas'tan siler, Undo/Redo ile)."""
    if not handle_copy_selection(canvas):
        return False
    logging.debug(f"handle_cut_selection: Komut öncesi shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    if not hasattr(canvas, 'selected_item_indices') or not canvas.selected_item_indices:
        logging.info("handle_cut_selection: Seçili öğe yok, kesme yapılmadı.")
        return False
    command = DeleteItemsCommand(canvas, canvas.selected_item_indices)
    logging.debug(f"handle_cut_selection: DeleteItemsCommand sonrası shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    if hasattr(canvas, 'undo_manager') and canvas.undo_manager:
        canvas.undo_manager.execute(command)
        logging.debug(f"handle_cut_selection: SON shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
        return True
    else:
        logging.warning("handle_cut_selection: Undo manager bulunamadı, doğrudan silme yapılacak.")
        command.execute()
        logging.debug(f"handle_cut_selection: SON (doğrudan silme) shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
        return True

def handle_paste_selection(canvas) -> bool:
    """Clipboard'daki öğeleri canvas'a yapıştırır (Undo/Redo ile)."""
    global _CLIPBOARD
    if not _CLIPBOARD['items']:
        logging.info("handle_paste_selection: Clipboard boş, yapıştırma yapılmadı.")
        return False
    command = PasteItemsCommand(canvas, _CLIPBOARD['items'])
    if hasattr(canvas, 'undo_manager') and canvas.undo_manager:
        canvas.undo_manager.execute(command)
        return True
    else:
        logging.warning("handle_paste_selection: Undo manager bulunamadı, doğrudan ekleme yapılacak.")
        command.execute()
        return True 
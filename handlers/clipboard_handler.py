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
from gui.enums import ToolType

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
            # Şekil tipine göre kontrol yap - düzenlenebilir çizgi için özel işlem
            shape_data = canvas.shapes[idx]
            if len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE:
                # Düzenlenebilir çizgi özel formatı
                editable_line_data = copy.deepcopy(shape_data)
                _CLIPBOARD['items'].append(('shapes', editable_line_data))
                logging.debug(f"handle_copy_selection: Düzenlenebilir çizgi kopyalandı: {editable_line_data}")
            else:
                # Normal şekiller
                _CLIPBOARD['items'].append(('shapes', copy.deepcopy(shape_data)))
        elif item_type == 'bspline_strokes' and hasattr(canvas, 'b_spline_strokes') and 0 <= idx < len(canvas.b_spline_strokes):
            # B-Spline özel işlemi
            bspline_data = copy.deepcopy(canvas.b_spline_strokes[idx])
            _CLIPBOARD['items'].append(('bspline_strokes', bspline_data))
            logging.debug(f"handle_copy_selection: B-Spline kopyalandı: {idx}")
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
    """Seçili öğeleri keser (kopyalar ve siler)."""
    logging.debug(f"handle_cut_selection: BAŞLANGIÇ shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    
    # Önce kopyala
    copied = handle_copy_selection(canvas)
    if not copied:
        return False
    
    # Seçili öğelerin olmadığını kontrol et
    if not hasattr(canvas, 'selected_item_indices') or not canvas.selected_item_indices:
        return False
    
    # Sonra sil (DeleteItemsCommand ile)
    logging.debug(f"handle_cut_selection: Komut öncesi shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    command = DeleteItemsCommand(canvas, canvas.selected_item_indices)
    logging.debug(f"handle_cut_selection: DeleteItemsCommand sonrası shapes id={id(canvas.shapes)}, içerik={canvas.shapes}")
    
    # Undo manager varsa komut ile sil, yoksa doğrudan sil
    if hasattr(canvas, 'undo_manager') and canvas.undo_manager:
        canvas.undo_manager.execute(command)
    else:
        logging.warning("handle_cut_selection: Undo manager bulunamadı, doğrudan silme yapılacak.")
        command.execute()
    
    logging.debug(f"handle_cut_selection: SON shapes id={id(canvas.shapes)}, içerik={canvas.shapes} ")
    return True

def handle_paste_selection(canvas) -> bool:
    """Clipboard'dan öğeleri yapıştırır."""
    global _CLIPBOARD
    if not _CLIPBOARD or 'items' not in _CLIPBOARD or not _CLIPBOARD['items']:
        logging.info("handle_paste_selection: Clipboard boş, yapıştırma yapılmadı.")
        return False
    
    # Yapıştırılacak öğeleri hazırla
    items_to_paste = []
    for item_type, item_data in _CLIPBOARD['items']:
        if item_type == 'lines' or item_type == 'shapes':
            items_to_paste.append((item_type, item_data))
        elif item_type == 'bspline_strokes' and hasattr(canvas, 'b_spline_strokes'):
            # b_spline_stroke için özel işlem
            items_to_paste.append((item_type, item_data))
            logging.debug(f"handle_paste_selection: b_spline_stroke yapıştırmaya hazırlanıyor.")
        elif item_type == 'images':
            # Resim verisi
            items_to_paste.append((item_type, item_data))
    
    if not items_to_paste:
        logging.info("handle_paste_selection: Yapıştırılacak uygun öğe yok.")
        return False
    
    # Yapıştırma komutunu oluştur ve yürüt
    paste_command = PasteItemsCommand(canvas, items_to_paste)
    canvas.undo_manager.execute(paste_command)
    
    # Komutun başarılı olduğunu kontrol et
    if hasattr(paste_command, 'pasted_indices') and paste_command.pasted_indices:
        canvas.selected_item_indices = paste_command.pasted_indices
        canvas.update()
        logging.info(f"handle_paste_selection: {len(paste_command.pasted_indices)} öğe başarıyla yapıştırıldı.")
        return True
    else:
        logging.error("handle_paste_selection: Yapıştırma işlemi başarısız.")
        return False 
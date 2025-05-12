import os
import json
from PyQt6.QtWidgets import QInputDialog, QMessageBox
from PyQt6.QtCore import QDir
from utils.file_io_helpers import _serialize_item, _deserialize_item

SHAPE_POOL_PATH = os.path.join(os.path.dirname(__file__), '../gui/config/shape_pool.json')

# Havuz dosyasını oku (yoksa boş liste döndür)
def _load_shape_pool():
    if not os.path.exists(SHAPE_POOL_PATH):
        return []
    try:
        with open(SHAPE_POOL_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _save_shape_pool(pool):
    os.makedirs(os.path.dirname(SHAPE_POOL_PATH), exist_ok=True)
    with open(SHAPE_POOL_PATH, 'w', encoding='utf-8') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

# Seçili şekilleri havuza ekle (grup desteği)
def handle_store_shape(page_manager, main_window):
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas
    selected_shapes = [i for i in canvas.selected_item_indices if i[0] == 'shapes']
    selected_lines = [i for i in canvas.selected_item_indices if i[0] == 'lines']
    if not (selected_shapes or selected_lines):
        QMessageBox.warning(main_window, "Uyarı", "Lütfen en az bir çizim veya şekil seçin.")
        return
    # Seçili tüm şekil ve çizgileri al
    shape_indices = [i[1] for i in selected_shapes]
    line_indices = [i[1] for i in selected_lines]
    shape_datas = [canvas.shapes[idx] for idx in shape_indices]
    line_datas = [canvas.lines[idx] for idx in line_indices]
    # Başlık sor
    title, ok = QInputDialog.getText(main_window, "Şekli Depola", "Çizim(ler)/Şekil(ler) için bir başlık girin:")
    if not ok or not title.strip():
        return
    # Havuzu yükle, ekle, kaydet
    pool = _load_shape_pool()
    entry = {'title': title.strip()}
    if shape_datas:
        entry['shapes'] = [_serialize_item(sd) for sd in shape_datas]
    if line_datas:
        entry['lines'] = [_serialize_item(ld) for ld in line_datas]
    pool.append(entry)
    _save_shape_pool(pool)
    QMessageBox.information(main_window, "Başarılı", f"'{title}' başlıklı çizim/şekil grubu havuza eklendi.")

# Havuzdan şekil(ler) ekle (grup desteği)
def handle_add_shape_from_pool(page_manager, main_window):
    pool = _load_shape_pool()
    if not pool:
        QMessageBox.information(main_window, "Şekil Havuzu", "Havuzda hiç şekil yok.")
        return
    # Başlıkları listele
    titles = [item['title'] for item in pool]
    title, ok = QInputDialog.getItem(main_window, "Depodan Şekil Ekle", "Bir şekil seçin:", titles, 0, False)
    if not ok or not title:
        return
    # Seçilen şekli bul
    for item in pool:
        if item['title'] == title:
            shape_datas = []
            line_datas = []
            if 'shapes' in item:
                shape_datas = [_deserialize_item(sd) for sd in item['shapes']]
            elif 'shape' in item:
                shape_datas = [_deserialize_item(item['shape'])]
            if 'lines' in item:
                line_datas = [_deserialize_item(ld) for ld in item['lines']]
            elif 'line' in item:
                line_datas = [_deserialize_item(item['line'])]
            break
    else:
        QMessageBox.warning(main_window, "Hata", "Şekil bulunamadı.")
        return
    # Aktif sayfaya ekle
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas
    # Tüm şekil ve çizgileri ekle
    for shape_data in shape_datas:
        if shape_data:
            canvas.shapes.append(shape_data)
    for line_data in line_datas:
        if line_data:
            canvas.lines.append(line_data)
    canvas.update()
    QMessageBox.information(main_window, "Başarılı", f"'{title}' başlıklı çizim/şekil grubu sayfaya eklendi.")

def handle_delete_shape_from_pool(page_manager, main_window):
    pool = _load_shape_pool()
    if not pool:
        QMessageBox.information(main_window, "Şekil Havuzu", "Havuzda hiç şekil yok.")
        return
    # Başlıkları listele
    titles = [item['title'] for item in pool]
    title, ok = QInputDialog.getItem(main_window, "Depodan Şekil Sil", "Silmek istediğiniz şekil grubunu seçin:", titles, 0, False)
    if not ok or not title:
        return
    # Seçilen başlıktaki şekli havuzdan sil
    new_pool = [item for item in pool if item['title'] != title]
    if len(new_pool) == len(pool):
        QMessageBox.warning(main_window, "Hata", "Şekil bulunamadı veya silinemedi.")
        return
    _save_shape_pool(new_pool)
    QMessageBox.information(main_window, "Başarılı", f"'{title}' başlıklı şekil grubu havuzdan silindi.") 
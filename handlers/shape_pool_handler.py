import os
import json
from PyQt6.QtWidgets import QInputDialog, QMessageBox, QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox, QHBoxLayout, QPushButton
from PyQt6.QtCore import QDir
from utils.file_io_helpers import _serialize_item, _deserialize_item
import copy
import logging
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox
from PyQt6.QtGui import QIcon
from typing import Dict, List, Tuple, Any

from gui.enums import ToolType
from utils import file_io_helpers

SHAPE_POOL_PATH = os.path.join(os.path.dirname(__file__), '../gui/config/shape_pool.json')

# Havuz dosyasını oku (yoksa boş sözlük döndür)
def _load_shape_pool():
    if not os.path.exists(SHAPE_POOL_PATH):
        return {"Genel": []}  # Boş bir sözlük döndür, "Genel" kategorisi ile
    try:
        with open(SHAPE_POOL_PATH, 'r', encoding='utf-8') as f:
            pool = json.load(f)
            # Eğer eski format bir liste ise, yeni formata dönüştür
            if isinstance(pool, list):
                return {"Genel": pool}  # Tüm eski şekilleri "Genel" kategorisine koy
            return pool
    except Exception as e:
        logging.error(f"Şekil havuzu yüklenirken hata: {e}")
        return {"Genel": []}

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
    selected_shapes = [i for i in canvas._selected_item_indices if i[0] == 'shapes']
    selected_lines = [i for i in canvas._selected_item_indices if i[0] == 'lines']
    # YENİ: Düzenlenebilir çizgileri de destekle
    selected_editable_lines = [i for i in canvas._selected_item_indices if i[0] == 'editable_lines']
    
    if not (selected_shapes or selected_lines or selected_editable_lines):
        QMessageBox.warning(main_window, "Uyarı", "Lütfen önce bir şekil seçin.")
        return
    
    # Kategori adını kullanıcıdan al
    category, ok = QInputDialog.getText(
        main_window, "Şekil Havuzu", "Kategori adı:", text="Genel"
    )
    if not ok or not category:
        return
    
    pool = _load_shape_pool()
    
    # Yeni kategori oluştur (yoksa)
    if category not in pool:
        pool[category] = []
    
    # Seçili şekilleri havuza ekle
    for shape_idx in selected_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = copy.deepcopy(canvas.shapes[item_idx])
            serialized_shape = file_io_helpers._serialize_item(shape_data)
            if serialized_shape:
                pool[category].append(serialized_shape)
    
    # Seçili çizgileri havuza ekle
    for line_idx in selected_lines:
        item_idx = line_idx[1]
        if 0 <= item_idx < len(canvas.lines):
            line_data = copy.deepcopy(canvas.lines[item_idx])
            serialized_line = file_io_helpers._serialize_item(line_data)
            if serialized_line:
                pool[category].append(serialized_line)
    
    # YENİ: Seçili düzenlenebilir çizgileri havuza ekle
    for editable_line_idx in selected_editable_lines:
        item_idx = editable_line_idx[1]
        if 0 <= item_idx < len(canvas.editable_lines):
            editable_line_data = copy.deepcopy(canvas.editable_lines[item_idx])
            serialized_editable_line = file_io_helpers._serialize_item(editable_line_data)
            if serialized_editable_line:
                pool[category].append(serialized_editable_line)
    
    # Şekil havuzunu kaydet
    _save_shape_pool(pool)
    QMessageBox.information(main_window, "Şekil Havuzu", f"Seçili şekiller '{category}' kategorisine eklendi.")

# Havuzdan şekil yükle (seç ve uygula)
def handle_load_shape(page_manager, main_window):
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas
    
    # Havuzu yükle
    pool = _load_shape_pool()
    if not pool:
        QMessageBox.warning(main_window, "Uyarı", "Şekil havuzu boş veya yüklenemedi.")
        return
    
    # Kategori seçme iletişim kutusu
    categories = sorted(list(pool.keys()))
    if not categories:
        QMessageBox.warning(main_window, "Uyarı", "Şekil havuzunda kategori bulunamadı.")
        return
    
    selected_category, ok = QInputDialog.getItem(
        main_window, "Şekil Havuzu", "Kategori seçin:", 
        categories, 0, False
    )
    if not ok or not selected_category:
        return
    
    # Kategorideki şekilleri göster
    shapes_in_category = pool.get(selected_category, [])
    if not shapes_in_category:
        QMessageBox.warning(main_window, "Uyarı", f"'{selected_category}' kategorisinde şekil bulunamadı.")
        return
    
    # Şekil/çizgi seçim diyaloğu
    dialog = QDialog(main_window)
    dialog.setWindowTitle(f"Şekil Havuzu - {selected_category}")
    dialog.setMinimumWidth(300)
    dialog.setMinimumHeight(400)
    
    layout = QVBoxLayout()
    list_widget = QListWidget()
    
    # Her şekli listeye ekle
    for i, item in enumerate(shapes_in_category):
        if isinstance(item, dict):
            item_type = item.get('type', 'bilinmeyen')
            list_widget.addItem(f"Öğe {i+1} ({item_type})")
    
    layout.addWidget(list_widget)
    
    button_layout = QHBoxLayout()
    load_button = QPushButton("Yükle")
    cancel_button = QPushButton("İptal")
    
    button_layout.addWidget(load_button)
    button_layout.addWidget(cancel_button)
    layout.addLayout(button_layout)
    
    dialog.setLayout(layout)
    
    # Buton fonksiyonları
    selected_index = [-1]  # Liste içinde değişken (kapanış için)
    
    def on_selection_changed():
        selected_index[0] = list_widget.currentRow()
    
    def on_load():
        if selected_index[0] >= 0:
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "Uyarı", "Lütfen bir şekil seçin.")
    
    list_widget.currentRowChanged.connect(on_selection_changed)
    load_button.clicked.connect(on_load)
    cancel_button.clicked.connect(dialog.reject)
    
    # Diyaloğu göster
    if dialog.exec() == QDialog.DialogCode.Accepted and selected_index[0] >= 0:
        idx = selected_index[0]
        if idx < len(shapes_in_category):
            item_data = shapes_in_category[idx]
            
            # Öğenin türüne göre yükleme işlemi
            if 'type' in item_data:
                item_type = item_data.get('type')
                
                if item_type == 'line':
                    # Çizgi verilerini deserialize et
                    deserialized = file_io_helpers._deserialize_item(item_data)
                    if deserialized:
                        # Çizgi stiline göre normal veya düzenlenebilir çizgi olarak ekle
                        if 'editable' in item_data and item_data['editable'] == True:
                            # Düzenlenebilir çizgi olarak ekle
                            canvas.editable_lines.append(deserialized)
                            canvas.update()
                            current_page.mark_as_modified()
                            QMessageBox.information(main_window, "Şekil Havuzu", "Düzenlenebilir çizgi başarıyla eklendi.")
                        else:
                            # Normal çizgi olarak ekle
                            canvas.lines.append(deserialized)
                            canvas.update()
                            current_page.mark_as_modified()
                            QMessageBox.information(main_window, "Şekil Havuzu", "Çizgi başarıyla eklendi.")
                
                elif item_type == 'shape':
                    # Şekil verilerini deserialize et
                    deserialized = file_io_helpers._deserialize_item(item_data)
                    if deserialized:
                        canvas.shapes.append(deserialized)
                        canvas.update()
                        current_page.mark_as_modified()
                        QMessageBox.information(main_window, "Şekil Havuzu", "Şekil başarıyla eklendi.")
                
                elif item_type == 'editable_line':
                    # Düzenlenebilir çizgi verilerini deserialize et
                    deserialized = file_io_helpers._deserialize_item(item_data)
                    if deserialized:
                        canvas.editable_lines.append(deserialized)
                        canvas.update()
                        current_page.mark_as_modified()
                        QMessageBox.information(main_window, "Şekil Havuzu", "Düzenlenebilir çizgi başarıyla eklendi.")
                
                else:
                    QMessageBox.warning(main_window, "Uyarı", f"Bilinmeyen öğe türü: {item_type}")
            else:
                QMessageBox.warning(main_window, "Uyarı", "Geçersiz öğe formatı: tür bilgisi bulunamadı.")
        else:
            QMessageBox.warning(main_window, "Uyarı", "Geçersiz seçim.")
    else:
        # İptal edildi veya geçersiz seçim
        pass

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

# Havuzdan şekil ekleme (diğer fonksiyonun takma adı)
def handle_add_shape_from_pool(page_manager, main_window):
    """Şekil havuzundan seçilen şekli sayfaya ekler (handle_load_shape'in takma adı)"""
    handle_load_shape(page_manager, main_window) 
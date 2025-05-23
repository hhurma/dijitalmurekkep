import os
import sys
import json
from PyQt6.QtWidgets import (QInputDialog, QMessageBox, QDialog, QVBoxLayout, QListWidget, 
                           QListWidgetItem, QDialogButtonBox, QHBoxLayout, QPushButton, 
                           QLabel, QComboBox, QFormLayout, QGroupBox, QLineEdit, QFileDialog)
from PyQt6.QtCore import QDir, Qt, QPointF
from utils.file_io_helpers import _serialize_item, _deserialize_item, _deserialize_bspline
import copy
import logging
from PyQt6.QtGui import QIcon
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

from gui.enums import ToolType
from utils import file_io_helpers

# Kök dizindeki config klasörünü kullan
def get_config_dir():
    if getattr(sys, 'frozen', False):
        # PyInstaller ile exe çalışıyorsa
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    config_dir = os.path.join(base_dir, 'config')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

def get_settings_path():
    return os.path.join(get_config_dir(), 'settings.json')

def get_shape_pool_path():
    settings_path = get_settings_path()
    shape_pool_path = None
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            shape_pool_path = settings.get('shape_pool_path', None)
    except Exception:
        pass
    if shape_pool_path and isinstance(shape_pool_path, str) and shape_pool_path.strip():
        return shape_pool_path
    # Yoksa varsayılan
    return os.path.join(get_config_dir(), 'shape_pool.json')

SHAPE_POOL_PATH = get_shape_pool_path()

# Havuz dosyasını oku (yoksa boş sözlük döndür)
def _load_shape_pool(main_window=None):
    shape_pool_path = get_shape_pool_path()  # Her zaman güncel yolu al
    if not os.path.exists(shape_pool_path):
        # Eğer main_window parametresi verilmişse kullanıcıya yol sor
        if main_window is not None:
            file_dialog = QFileDialog(main_window)
            file_dialog.setWindowTitle("Şekil Havuzu Dosyasını Seç")
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            file_dialog.setNameFilter("JSON Dosyası (*.json)")
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    selected_path = selected_files[0]
                    # settings.json'a kaydet
                    settings_path = get_settings_path()
                    try:
                        try:
                            with open(settings_path, 'r', encoding='utf-8') as f:
                                settings = json.load(f)
                        except Exception:
                            settings = {}
                        settings['shape_pool_path'] = selected_path
                        with open(settings_path, 'w', encoding='utf-8') as f:
                            json.dump(settings, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        if main_window:
                            QMessageBox.warning(main_window, "Uyarı", f"Seçilen dosya yolu ayarlara kaydedilemedi: {e}\nYol: {settings_path}")
                        return {"Genel": {}}
                    # Dosya bulundu, tekrar dene
                    if os.path.exists(selected_path):
                        return _load_shape_pool(main_window)
        # Dosya yine yoksa boş havuz döndür
        return {"Genel": {}}  # Boş bir sözlük döndür, "Genel" kategorisi ile
    try:
        with open(shape_pool_path, 'r', encoding='utf-8') as f:
            pool = json.load(f)
            # Eğer eski format bir liste veya kategori içinde liste ise, yeni formata dönüştür
            if isinstance(pool, list):
                return {"Genel": {"Eski Şekiller": pool}}  # Tüm eski şekilleri "Genel" kategorisine koy
            # Her kategori için liste formatını sözlük formatına dönüştür
            for category, items in pool.items():
                if isinstance(items, list):
                    new_items = {}
                    for i, item in enumerate(items):
                        item_name = f"Şekil {i+1}"
                        new_items[item_name] = [item]  # Her şekil bir liste olarak saklanır (grup olarak)
                    pool[category] = new_items
            return pool
    except Exception as e:
        logging.error(f"Şekil havuzu yüklenirken hata: {e}")
        return {"Genel": {}}

def _save_shape_pool(pool, shape_pool_path=None):
    if shape_pool_path is None:
        shape_pool_path = get_shape_pool_path()
    os.makedirs(os.path.dirname(shape_pool_path), exist_ok=True)
    with open(shape_pool_path, 'w', encoding='utf-8') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

# Seçili şekilleri havuza ekle (grup desteği)
def handle_store_shape(page_manager, main_window):
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas

    # --- Şekil havuzu dosya yolunu ayarlardan dinamik al ---
    shape_pool_path = get_shape_pool_path()
    if not os.path.exists(shape_pool_path):
        # Sadece dosya yoksa kullanıcıya sor
        file_dialog = QFileDialog(main_window)
        file_dialog.setWindowTitle("Şekil Havuzu Dosya Konumu Seç")
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setNameFilter("JSON Dosyası (*.json)")
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.selectFile(shape_pool_path)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                selected_path = selected_files[0]
                os.makedirs(os.path.dirname(selected_path), exist_ok=True)
                # settings.json'a kaydet
                try:
                    settings_path = get_settings_path()
                    try:
                        with open(settings_path, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                    except Exception:
                        settings = {}
                    settings['shape_pool_path'] = selected_path
                    with open(settings_path, 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)
                    shape_pool_path = selected_path
                except Exception as e:
                    QMessageBox.warning(main_window, "Uyarı", f"Seçilen dosya yolu ayarlara kaydedilemedi: {e}\nYol: {settings_path}")
                    return
        else:
            return  # Kullanıcı iptal ettiyse işlemi durdur

    # Seçili öğeleri topla
    selected_shapes = [i for i in canvas._selected_item_indices if i[0] == 'shapes']
    selected_lines = [i for i in canvas._selected_item_indices if i[0] == 'lines']
    selected_bspline_strokes = [i for i in getattr(canvas, '_selected_item_indices', []) if i[0] == 'bspline_strokes']
    editable_lines_in_shapes = []
    for shape_idx in selected_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = canvas.shapes[item_idx]
            if len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE:
                editable_lines_in_shapes.append(shape_idx)
    if not (selected_shapes or selected_lines or selected_bspline_strokes):
        QMessageBox.warning(main_window, "Uyarı", "Lütfen önce bir şekil seçin.")
        return

    # Havuzu yükle ve mevcut kategorileri al
    pool = _load_shape_pool()
    categories = sorted(list(pool.keys()))

    # Kategori ve şekil adı diyalogu
    dialog = QDialog(main_window)
    dialog.setWindowTitle("Şekil Havuzuna Ekle")
    dialog.setMinimumWidth(400)
    dialog.setMinimumHeight(250)
    layout = QVBoxLayout()
    form_layout = QFormLayout()
    category_group = QGroupBox("Kategori Seçimi")
    category_layout = QVBoxLayout()
    category_combo = QComboBox()
    category_combo.setEditable(True)
    category_combo.addItems(categories)
    category_combo.setCurrentText("Genel")
    category_hint = QLabel("Mevcut bir kategori seçin veya yeni bir kategori adı yazın")
    category_hint.setStyleSheet("color: #666; font-size: 10px;")
    category_layout.addWidget(category_combo)
    category_layout.addWidget(category_hint)
    category_group.setLayout(category_layout)

    # --- Şekil adı combobox ---
    shape_name_group = QGroupBox("Şekil Adı")
    shape_name_layout = QVBoxLayout()
    shape_name_combo = QComboBox()
    shape_name_combo.setEditable(True)
    shape_name_combo.addItem("Şekil adı girin...")
    # Kategori değişince şekil adlarını güncelle
    def update_shape_names():
        shape_name_combo.clear()
        shape_name_combo.addItem("Şekil adı girin...")
        selected_category = category_combo.currentText()
        if selected_category in pool and isinstance(pool[selected_category], dict):
            for name in sorted(pool[selected_category].keys()):
                shape_name_combo.addItem(name)
    category_combo.currentIndexChanged.connect(update_shape_names)
    category_combo.editTextChanged.connect(update_shape_names)
    update_shape_names()
    shape_name_hint = QLabel("Var olan bir şekil adını seçerseniz üzerine kaydedilir. Yeni isim yazarsanız yeni şekil eklenir.")
    shape_name_hint.setStyleSheet("color: #666; font-size: 10px;")
    shape_name_layout.addWidget(shape_name_combo)
    shape_name_layout.addWidget(shape_name_hint)
    shape_name_group.setLayout(shape_name_layout)

    info_group = QGroupBox("Seçili Öğeler")
    info_layout = QVBoxLayout()
    normal_shapes_count = sum(1 for idx in selected_shapes if idx not in editable_lines_in_shapes)
    editable_lines_count = len(editable_lines_in_shapes)
    lines_count = len(selected_lines)
    info_text = f"Normal Şekiller: {normal_shapes_count} adet\n"
    info_text += f"Düzenlenebilir Çizgiler: {editable_lines_count} adet\n"
    info_text += f"Çizgiler: {lines_count} adet\n"
    info_text += f"Toplam: {normal_shapes_count + editable_lines_count + lines_count} öğe"
    info_label = QLabel(info_text)
    info_layout.addWidget(info_label)
    info_group.setLayout(info_layout)
    layout.addWidget(category_group)
    layout.addWidget(shape_name_group)
    layout.addWidget(info_group)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    category = category_combo.currentText().strip()
    shape_name = shape_name_combo.currentText().strip()
    if not category or not shape_name or shape_name == "Şekil adı girin...":
        QMessageBox.warning(main_window, "Uyarı", "Kategori ve şekil adı boş olamaz.")
        return
    if category not in pool:
        pool[category] = {}
        logging.info(f"Yeni kategori oluşturuldu: {category}")
    if shape_name in pool[category]:
        confirm = QMessageBox.question(
            main_window, 
            "Onay", 
            f"'{shape_name}' adlı şekil zaten '{category}' kategorisinde var. Üzerine yazmak istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
    serialized_group = []
    for shape_idx in selected_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = copy.deepcopy(canvas.shapes[item_idx])
            if not (len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE):
                serialized_shape = file_io_helpers._serialize_item(shape_data)
                if serialized_shape:
                    serialized_group.append(serialized_shape)
    for shape_idx in editable_lines_in_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = copy.deepcopy(canvas.shapes[item_idx])
            if len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE:
                serialized_shape = file_io_helpers._serialize_item(shape_data)
                if serialized_shape:
                    logging.debug(f"Düzenlenebilir çizgi kaydediliyor: {serialized_shape}")
                    serialized_group.append(serialized_shape)
    for line_idx in selected_lines:
        item_idx = line_idx[1]
        if 0 <= item_idx < len(canvas.lines):
            line_data = copy.deepcopy(canvas.lines[item_idx])
            serialized_line = file_io_helpers._serialize_item(line_data)
            if serialized_line:
                serialized_group.append(serialized_line)
    for bspline_idx in selected_bspline_strokes:
        item_idx = bspline_idx[1]
        if 0 <= item_idx < len(canvas.b_spline_strokes):
            bspline_data = copy.deepcopy(canvas.b_spline_strokes[item_idx])
            serialized_bspline = file_io_helpers._serialize_item(bspline_data)
            if serialized_bspline:
                serialized_group.append(serialized_bspline)
    pool[category][shape_name] = serialized_group
    _save_shape_pool(pool, shape_pool_path)
    QMessageBox.information(main_window, "Başarılı", f"Şekil başarıyla kaydedildi: {category}/{shape_name}")

# Havuzdan şekil yükle (seç ve uygula)
def handle_load_shape(page_manager, main_window):
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas
    
    # Havuzu yükle
    pool = _load_shape_pool(main_window)
    if not pool:
        QMessageBox.warning(main_window, "Uyarı", "Şekil havuzu boş veya yüklenemedi.")
        return
    
    # Boş kategorileri filtrele
    pool = {k: v for k, v in pool.items() if v}
    
    if not pool:
        QMessageBox.warning(main_window, "Uyarı", "Şekil havuzunda hiç öğe yok.")
        return
    
    # Şekil seçme diyaloğu
    dialog = QDialog(main_window)
    dialog.setWindowTitle("Şekil Havuzundan Yükle")
    dialog.setMinimumWidth(500)
    dialog.setMinimumHeight(400)
    
    layout = QVBoxLayout()
    
    # Kategori seçim grubu
    category_group = QGroupBox("Kategori")
    category_layout = QVBoxLayout()
    
    # Kategori seçici ComboBox
    category_label = QLabel("Kategoriyi seçin:")
    category_combo = QComboBox()
    category_combo.setMinimumWidth(200)
    categories = sorted(list(pool.keys()))
    category_combo.addItems(categories)
    
    category_layout.addWidget(category_label)
    category_layout.addWidget(category_combo)
    category_group.setLayout(category_layout)
    
    # Şekil seçim grubu
    shape_group = QGroupBox("Şekil")
    shape_layout = QVBoxLayout()
    
    # Şekil seçici ComboBox
    shape_label = QLabel("Şekli seçin:")
    shape_combo = QComboBox()
    shape_combo.setMinimumWidth(200)
    
    shape_layout.addWidget(shape_label)
    shape_layout.addWidget(shape_combo)
    shape_group.setLayout(shape_layout)
    
    # Şekil detay alanı
    info_group = QGroupBox("Seçili Şekil Detayları")
    info_layout = QVBoxLayout()
    info_label = QLabel("Lütfen bir şekil seçin.")
    info_label.setWordWrap(True)
    info_label.setMinimumHeight(100)
    info_layout.addWidget(info_label)
    info_group.setLayout(info_layout)
    
    # Kategori değiştiğinde şekilleri güncelle
    def update_shapes():
        shape_combo.clear()
        selected_category = category_combo.currentText()
        if selected_category in pool:
            # Hatalı veri varsa atla
            if not isinstance(pool[selected_category], dict):
                return
            shapes_in_category = sorted(list(pool[selected_category].keys()))
            shape_combo.addItems(shapes_in_category)
    
    # Şekil değiştiğinde bilgileri güncelle
    def update_info():
        selected_category = category_combo.currentText()
        selected_shape = shape_combo.currentText()
        
        if not selected_category or not selected_shape:
            info_label.setText("Seçili şekil yok.")
            return
        
        if selected_category in pool and selected_shape in pool[selected_category]:
            items = pool[selected_category][selected_shape]
            info_text = f"<b>Şekil:</b> {selected_shape}<br>"
            info_text += f"<b>Kategori:</b> {selected_category}<br>"
            info_text += f"<b>Parça sayısı:</b> {len(items)}<br><br>"
            
            # İçerik türlerini say
            type_counts = {}
            for item in items:
                item_type = item.get('type', 'bilinmeyen')
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
            
            info_text += "<b>İçerik:</b><br>"
            for item_type, count in type_counts.items():
                # Türleri daha anlaşılır isimlerle göster
                display_name = {
                    'line': 'Çizgi',
                    'shape': 'Şekil',
                    'editable_line': 'Düzenlenebilir Çizgi',
                    'bspline': 'B-spline Çizgi'
                }.get(item_type, item_type)
                
                info_text += f"  - {display_name}: {count} adet<br>"
            
            info_label.setText(info_text)
        else:
            info_label.setText("Seçili şekil bulunamadı.")
    
    # Connect signals
    category_combo.currentIndexChanged.connect(update_shapes)
    shape_combo.currentIndexChanged.connect(update_info)
    
    # Yatay düzen
    panel_layout = QHBoxLayout()
    select_layout = QVBoxLayout()
    
    select_layout.addWidget(category_group)
    select_layout.addWidget(shape_group)
    
    panel_layout.addLayout(select_layout)
    panel_layout.addWidget(info_group)
    
    layout.addLayout(panel_layout)
    
    # Butonlar
    button_layout = QHBoxLayout()
    load_button = QPushButton("Yükle")
    load_button.setIcon(QIcon.fromTheme("document-open"))
    load_button.setMinimumWidth(100)
    
    cancel_button = QPushButton("İptal")
    cancel_button.setIcon(QIcon.fromTheme("dialog-cancel"))
    cancel_button.setMinimumWidth(100)
    
    button_layout.addStretch()
    button_layout.addWidget(load_button)
    button_layout.addWidget(cancel_button)
    layout.addLayout(button_layout)
    
    dialog.setLayout(layout)
    
    # İlk kategoriyi yükle
    update_shapes()
    update_info()
    
    # Buton fonksiyonları
    def on_load():
        selected_category = category_combo.currentText()
        selected_shape = shape_combo.currentText()
        
        if not selected_category or not selected_shape:
            QMessageBox.warning(dialog, "Uyarı", "Lütfen bir kategori ve şekil seçin.")
            return
        
        if selected_category in pool and selected_shape in pool[selected_category]:
            dialog.accept()
        else:
            QMessageBox.warning(dialog, "Uyarı", "Seçilen şekil bulunamadı.")
    
    load_button.clicked.connect(on_load)
    cancel_button.clicked.connect(dialog.reject)
    
    # Diyaloğu göster
    if dialog.exec() == QDialog.DialogCode.Accepted:
        selected_category = category_combo.currentText()
        selected_shape = shape_combo.currentText()
        
        if selected_category in pool and selected_shape in pool[selected_category]:
            items = pool[selected_category][selected_shape]
            
            if not items:
                QMessageBox.warning(main_window, "Uyarı", "Seçili şekil grubunda hiç öğe yok.")
                return
            
            # Tüm şekilleri canvas'a ekle
            added_count = 0
            
            for item_data in items:
                # Öğenin türüne göre yükleme işlemi
                if 'type' in item_data:
                    item_type = item_data.get('type')
                    
                    if item_type == 'line':
                        # Çizgi verilerini deserialize et
                        deserialized = file_io_helpers._deserialize_item(item_data)
                        if deserialized:
                            # Normal çizgi olarak ekle
                            canvas.lines.append(deserialized)
                            added_count += 1
                    
                    elif item_type == 'shape':
                        # Şekil verilerini deserialize et
                        deserialized = file_io_helpers._deserialize_item(item_data)
                        if deserialized:
                            canvas.shapes.append(deserialized)
                            added_count += 1
                    
                    elif item_type == 'editable_line':
                        # Düzenlenebilir çizgi verilerini deserialize et
                        deserialized = file_io_helpers._deserialize_item(item_data)
                        if deserialized:
                            # Düzenlenebilir çizgiler artık shapes listesine ekleniyor
                            canvas.shapes.append(deserialized)
                            logging.debug(f"Düzenlenebilir çizgi yüklendi: {deserialized}")
                            added_count += 1
                    
                    elif item_type == 'bspline':
                        # B-spline'ı deserialize et (file_io_helpers kullanarak)
                        deserialized_bspline = file_io_helpers._deserialize_bspline(item_data)
                        if deserialized_bspline:
                            # B-Spline stroke verisi DrawingCanvas.b_spline_strokes listesine eklenir.
                            # Bu liste DrawingWidget.strokes'a referans olduğu için widget da güncellenir.
                            if not hasattr(canvas, 'b_spline_strokes') or canvas.b_spline_strokes is None:
                                canvas.b_spline_strokes = [] # Eğer yoksa oluştur
                                if hasattr(canvas, 'b_spline_widget') and canvas.b_spline_widget:
                                    canvas.b_spline_widget.strokes = canvas.b_spline_strokes # Referansı tekrar ata

                            canvas.b_spline_strokes.append(deserialized_bspline)
                            logging.debug(f"B-spline (deserialize ile) yüklendi: {deserialized_bspline.get('control_points')}")
                            added_count += 1
                        else:
                            logging.warning(f"B-spline deserialize edilemedi: {item_data}")
                    else:
                        logging.warning(f"Bilinmeyen öğe türü: {item_type}")
            
            if added_count > 0:
                canvas.update()
                if hasattr(canvas, 'invalidate_cache'):
                    canvas.invalidate_cache("Şekil havuzundan şekil eklendi")
                if hasattr(canvas, 'b_spline_widget') and canvas.b_spline_widget: # Widget varsa onu da güncelle
                    logging.debug("Calling canvas.b_spline_widget.update() after loading shapes from pool.")
                    canvas.b_spline_widget.update()
                current_page.mark_as_modified()
                QMessageBox.information(main_window, "Şekil Havuzu", 
                                       f"'{selected_category}/{selected_shape}' şekil grubu başarıyla eklendi. ({added_count} parça)")
            else:
                QMessageBox.warning(main_window, "Uyarı", "Hiçbir şekil eklenemedi.")

def handle_delete_shape_from_pool(page_manager, main_window):
    # Havuzu yükle
    pool = _load_shape_pool()
    shape_pool_path = get_shape_pool_path()
    if not pool:
        QMessageBox.information(main_window, "Şekil Havuzu", "Havuzda hiç şekil yok.")
        return
    
    # Boş kategorileri filtrele
    pool = {k: v for k, v in pool.items() if v}
    
    if not pool:
        QMessageBox.information(main_window, "Şekil Havuzu", "Havuzda hiç şekil yok.")
        return
    
    # Diyalog oluştur
    dialog = QDialog(main_window)
    dialog.setWindowTitle("Şekil Havuzundan Sil")
    dialog.setMinimumWidth(450)
    dialog.setMinimumHeight(300)
    
    layout = QVBoxLayout()
    
    # Kategori seçim grubu
    category_group = QGroupBox("Kategori")
    category_layout = QVBoxLayout()
    
    # Kategori seçici
    category_label = QLabel("Silmek istediğiniz şeklin kategorisini seçin:")
    category_combo = QComboBox()
    category_combo.setMinimumWidth(200)
    categories = sorted(list(pool.keys()))
    category_combo.addItems(categories)
    
    category_layout.addWidget(category_label)
    category_layout.addWidget(category_combo)
    category_group.setLayout(category_layout)
    
    # Şekil seçim grubu
    shape_group = QGroupBox("Şekil")
    shape_layout = QVBoxLayout()
    
    # Şekil seçici
    shape_label = QLabel("Silmek istediğiniz şekli seçin:")
    shape_combo = QComboBox()
    shape_combo.setMinimumWidth(200)
    
    shape_layout.addWidget(shape_label)
    shape_layout.addWidget(shape_combo)
    shape_group.setLayout(shape_layout)
    
    # Önizleme/Bilgi alanı
    info_group = QGroupBox("Şekil Bilgileri")
    info_layout = QVBoxLayout()
    
    info_label = QLabel("Lütfen bir şekil seçin.")
    info_label.setWordWrap(True)
    info_layout.addWidget(info_label)
    
    info_group.setLayout(info_layout)
    
    # Kategori değiştiğinde şekilleri güncelle
    def update_shapes():
        shape_combo.clear()
        selected_category = category_combo.currentText()
        if selected_category in pool:
            shapes_in_category = sorted(list(pool[selected_category].keys()))
            shape_combo.addItems(shapes_in_category)
            update_info()
    
    # Şekil değiştiğinde bilgileri güncelle
    def update_info():
        selected_category = category_combo.currentText()
        selected_shape = shape_combo.currentText()
        
        if not selected_category or not selected_shape:
            info_label.setText("Lütfen bir şekil seçin.")
            return
        
        if selected_category in pool and selected_shape in pool[selected_category]:
            items = pool[selected_category][selected_shape]
            info_text = f"<b>Şekil:</b> {selected_shape}<br>"
            info_text += f"<b>Kategori:</b> {selected_category}<br>"
            info_text += f"<b>Parça sayısı:</b> {len(items)}<br><br>"
            
            # İçerik türlerini say
            type_counts = {}
            for item in items:
                item_type = item.get('type', 'bilinmeyen')
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
            
            info_text += "<b>İçerik:</b><br>"
            for item_type, count in type_counts.items():
                display_name = {
                    'line': 'Çizgi',
                    'shape': 'Şekil', 
                    'editable_line': 'Düzenlenebilir Çizgi',
                    'bspline': 'B-spline Çizgi'
                }.get(item_type, item_type)
                
                info_text += f"  - {display_name}: {count} adet<br>"
            
            info_label.setText(info_text)
        else:
            info_label.setText("Seçili şekil bulunamadı.")
    
    # Connect signals
    category_combo.currentIndexChanged.connect(update_shapes)
    shape_combo.currentIndexChanged.connect(update_info)
    
    # Yatay düzen (sol kategori+şekil seçimi, sağ bilgi)
    content_layout = QHBoxLayout()
    
    select_panel = QVBoxLayout()
    select_panel.addWidget(category_group)
    select_panel.addWidget(shape_group)
    
    content_layout.addLayout(select_panel)
    content_layout.addWidget(info_group)
    
    layout.addLayout(content_layout)
    
    # Butonlar
    button_layout = QHBoxLayout()
    delete_button = QPushButton("Sil")
    delete_button.setIcon(QIcon.fromTheme("edit-delete"))
    delete_button.setStyleSheet("background-color: #f44336; color: white;")
    delete_button.setMinimumWidth(100)
    
    cancel_button = QPushButton("İptal")
    cancel_button.setIcon(QIcon.fromTheme("dialog-cancel"))
    cancel_button.setMinimumWidth(100)
    
    button_layout.addStretch()
    button_layout.addWidget(delete_button)
    button_layout.addWidget(cancel_button)
    layout.addLayout(button_layout)
    
    dialog.setLayout(layout)
    
    # İlk kategoriyi yükle
    update_shapes()
    
    # Buton fonksiyonları
    def on_delete():
        selected_category = category_combo.currentText()
        selected_shape = shape_combo.currentText()
        
        if not selected_category or not selected_shape:
            QMessageBox.warning(dialog, "Uyarı", "Lütfen bir kategori ve şekil seçin.")
            return
        
        # Onay iste
        confirm = QMessageBox.question(
            dialog, 
            "Onay", 
            f"'{selected_category}/{selected_shape}' şeklini silmek istediğinizden emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if confirm != QMessageBox.StandardButton.Yes:
            return
        
        if selected_category in pool and selected_shape in pool[selected_category]:
            # Şekli sil
            del pool[selected_category][selected_shape]
            
            # Eğer kategori boş kaldıysa, kategoriyi de sil
            if not pool[selected_category]:
                del pool[selected_category]
            
            _save_shape_pool(pool, shape_pool_path)
            dialog.accept()
            
            QMessageBox.information(main_window, "Başarılı", f"'{selected_category}/{selected_shape}' şekli başarıyla silindi.")
        else:
            QMessageBox.warning(dialog, "Uyarı", "Seçilen şekil bulunamadı.")
    
    delete_button.clicked.connect(on_delete)
    cancel_button.clicked.connect(dialog.reject)
    
    # Diyaloğu göster
    dialog.exec()

# Havuzdan şekil ekleme (diğer fonksiyonun takma adı)
def handle_add_shape_from_pool(page_manager, main_window):
    """Şekil havuzundan seçilen şekli sayfaya ekler (handle_load_shape'in takma adı)"""
    handle_load_shape(page_manager, main_window)

# Yeni eklenen kod
def handle_store_shape(page_manager, main_window):
    current_page = page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        QMessageBox.warning(main_window, "Uyarı", "Aktif bir sayfa yok.")
        return
    canvas = current_page.drawing_canvas

    # --- Şekil havuzu dosya yolunu ayarlardan dinamik al ---
    shape_pool_path = get_shape_pool_path()
    if not os.path.exists(shape_pool_path):
        # Sadece dosya yoksa kullanıcıya sor
        file_dialog = QFileDialog(main_window)
        file_dialog.setWindowTitle("Şekil Havuzu Dosya Konumu Seç")
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setNameFilter("JSON Dosyası (*.json)")
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.selectFile(shape_pool_path)
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                selected_path = selected_files[0]
                os.makedirs(os.path.dirname(selected_path), exist_ok=True)
                # settings.json'a kaydet
                try:
                    settings_path = get_settings_path()
                    try:
                        with open(settings_path, 'r', encoding='utf-8') as f:
                            settings = json.load(f)
                    except Exception:
                        settings = {}
                    settings['shape_pool_path'] = selected_path
                    with open(settings_path, 'w', encoding='utf-8') as f:
                        json.dump(settings, f, ensure_ascii=False, indent=2)
                    shape_pool_path = selected_path
                except Exception as e:
                    QMessageBox.warning(main_window, "Uyarı", f"Seçilen dosya yolu ayarlara kaydedilemedi: {e}\nYol: {settings_path}")
                    return
        else:
            return  # Kullanıcı iptal ettiyse işlemi durdur

    # Seçili öğeleri topla
    selected_shapes = [i for i in canvas._selected_item_indices if i[0] == 'shapes']
    selected_lines = [i for i in canvas._selected_item_indices if i[0] == 'lines']
    selected_bspline_strokes = [i for i in getattr(canvas, '_selected_item_indices', []) if i[0] == 'bspline_strokes']
    editable_lines_in_shapes = []
    for shape_idx in selected_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = canvas.shapes[item_idx]
            if len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE:
                editable_lines_in_shapes.append(shape_idx)
    if not (selected_shapes or selected_lines or selected_bspline_strokes):
        QMessageBox.warning(main_window, "Uyarı", "Lütfen önce bir şekil seçin.")
        return

    # Havuzu yükle ve mevcut kategorileri al
    pool = _load_shape_pool()
    categories = sorted(list(pool.keys()))

    # Kategori ve şekil adı diyalogu
    dialog = QDialog(main_window)
    dialog.setWindowTitle("Şekil Havuzuna Ekle")
    dialog.setMinimumWidth(400)
    dialog.setMinimumHeight(250)
    layout = QVBoxLayout()
    form_layout = QFormLayout()
    category_group = QGroupBox("Kategori Seçimi")
    category_layout = QVBoxLayout()
    category_combo = QComboBox()
    category_combo.setEditable(True)
    category_combo.addItems(categories)
    category_combo.setCurrentText("Genel")
    category_hint = QLabel("Mevcut bir kategori seçin veya yeni bir kategori adı yazın")
    category_hint.setStyleSheet("color: #666; font-size: 10px;")
    category_layout.addWidget(category_combo)
    category_layout.addWidget(category_hint)
    category_group.setLayout(category_layout)

    # --- Şekil adı combobox ---
    shape_name_group = QGroupBox("Şekil Adı")
    shape_name_layout = QVBoxLayout()
    shape_name_combo = QComboBox()
    shape_name_combo.setEditable(True)
    shape_name_combo.addItem("Şekil adı girin...")
    # Kategori değişince şekil adlarını güncelle
    def update_shape_names():
        shape_name_combo.clear()
        shape_name_combo.addItem("Şekil adı girin...")
        selected_category = category_combo.currentText()
        if selected_category in pool and isinstance(pool[selected_category], dict):
            for name in sorted(pool[selected_category].keys()):
                shape_name_combo.addItem(name)
    category_combo.currentIndexChanged.connect(update_shape_names)
    category_combo.editTextChanged.connect(update_shape_names)
    update_shape_names()
    shape_name_hint = QLabel("Var olan bir şekil adını seçerseniz üzerine kaydedilir. Yeni isim yazarsanız yeni şekil eklenir.")
    shape_name_hint.setStyleSheet("color: #666; font-size: 10px;")
    shape_name_layout.addWidget(shape_name_combo)
    shape_name_layout.addWidget(shape_name_hint)
    shape_name_group.setLayout(shape_name_layout)

    info_group = QGroupBox("Seçili Öğeler")
    info_layout = QVBoxLayout()
    normal_shapes_count = sum(1 for idx in selected_shapes if idx not in editable_lines_in_shapes)
    editable_lines_count = len(editable_lines_in_shapes)
    lines_count = len(selected_lines)
    info_text = f"Normal Şekiller: {normal_shapes_count} adet\n"
    info_text += f"Düzenlenebilir Çizgiler: {editable_lines_count} adet\n"
    info_text += f"Çizgiler: {lines_count} adet\n"
    info_text += f"Toplam: {normal_shapes_count + editable_lines_count + lines_count} öğe"
    info_label = QLabel(info_text)
    info_layout.addWidget(info_label)
    info_group.setLayout(info_layout)
    layout.addWidget(category_group)
    layout.addWidget(shape_name_group)
    layout.addWidget(info_group)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    category = category_combo.currentText().strip()
    shape_name = shape_name_combo.currentText().strip()
    if not category or not shape_name or shape_name == "Şekil adı girin...":
        QMessageBox.warning(main_window, "Uyarı", "Kategori ve şekil adı boş olamaz.")
        return
    if category not in pool:
        pool[category] = {}
        logging.info(f"Yeni kategori oluşturuldu: {category}")
    if shape_name in pool[category]:
        confirm = QMessageBox.question(
            main_window, 
            "Onay", 
            f"'{shape_name}' adlı şekil zaten '{category}' kategorisinde var. Üzerine yazmak istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
    serialized_group = []
    for shape_idx in selected_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = copy.deepcopy(canvas.shapes[item_idx])
            if not (len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE):
                serialized_shape = file_io_helpers._serialize_item(shape_data)
                if serialized_shape:
                    serialized_group.append(serialized_shape)
    for shape_idx in editable_lines_in_shapes:
        item_idx = shape_idx[1]
        if 0 <= item_idx < len(canvas.shapes):
            shape_data = copy.deepcopy(canvas.shapes[item_idx])
            if len(shape_data) > 0 and shape_data[0] == ToolType.EDITABLE_LINE:
                serialized_shape = file_io_helpers._serialize_item(shape_data)
                if serialized_shape:
                    logging.debug(f"Düzenlenebilir çizgi kaydediliyor: {serialized_shape}")
                    serialized_group.append(serialized_shape)
    for line_idx in selected_lines:
        item_idx = line_idx[1]
        if 0 <= item_idx < len(canvas.lines):
            line_data = copy.deepcopy(canvas.lines[item_idx])
            serialized_line = file_io_helpers._serialize_item(line_data)
            if serialized_line:
                serialized_group.append(serialized_line)
    for bspline_idx in selected_bspline_strokes:
        item_idx = bspline_idx[1]
        if 0 <= item_idx < len(canvas.b_spline_strokes):
            bspline_data = copy.deepcopy(canvas.b_spline_strokes[item_idx])
            serialized_bspline = file_io_helpers._serialize_item(bspline_data)
            if serialized_bspline:
                serialized_group.append(serialized_bspline)
    pool[category][shape_name] = serialized_group
    _save_shape_pool(pool, shape_pool_path)
    QMessageBox.information(main_window, "Başarılı", f"Şekil başarıyla kaydedildi: {category}/{shape_name}") 
# utils/file_io_helpers.py
"""Not defterini kaydetme ve yükleme ile ilgili yardımcı fonksiyonlar."""

import json
import logging
from typing import List, Dict, Any, Tuple
from PyQt6.QtCore import QPointF, QRectF
from gui.enums import ToolType, Orientation # Orientation eklendi

# --- Veri Dönüştürme Yardımcıları ---

def _point_to_list(p: QPointF) -> List[float]:
    """QPointF'i [x, y] listesine dönüştürür."""
    return [p.x(), p.y()]

def _list_to_point(p_list: List[float]) -> QPointF:
    """[x, y] listesini QPointF'e dönüştürür."""
    return QPointF(p_list[0], p_list[1])

# --- YENİ: Rect ve Image Serialize/Deserialize ---
def _rect_to_list(r: QRectF) -> List[float]:
    """QRectF'i [left, top, width, height] listesine dönüştürür."""
    return [r.left(), r.top(), r.width(), r.height()]

def _list_to_rect(r_list: List[float]) -> QRectF:
    """[left, top, width, height] listesini QRectF'e dönüştürür."""
    return QRectF(r_list[0], r_list[1], r_list[2], r_list[3])

def _serialize_image(image_data: Dict[str, Any]) -> Dict[str, Any]:
    """Tek bir resim verisini (pixmap hariç) JSON uyumlu sözlüğe dönüştürür."""
    serialized = {}
    for key, value in image_data.items():
        if key == 'pixmap':
            continue # Pixmap'ı kaydetme
        elif key == 'rect' and isinstance(value, QRectF):
            serialized['rect'] = _rect_to_list(value)
        elif key == 'angle':
            serialized['angle'] = value
        elif key == 'path': # Mutlak yolu kaydet
            serialized['path'] = value
        elif key == 'uuid': # UUID'yi de alalım
             serialized['uuid'] = value
        # Gelecekte eklenebilecek diğer anahtarlar buraya eklenebilir
    # Path'in mutlaka eklendiğinden emin olalım (eski format uyumu için?)
    if 'path' not in serialized:
         serialized['path'] = image_data.get('path', None) # Path yoksa None
         if serialized['path'] is None:
             logging.warning(f"Kaydedilecek resim verisinde 'path' bulunamadı: UUID {image_data.get('uuid')}")

    serialized['type'] = 'image' # Türünü belirtelim
    return serialized

def _deserialize_image(image_dict: Dict[str, Any]) -> Dict[str, Any] | None:
    """JSON uyumlu sözlükten resim verisi sözlüğünü oluşturur (pixmap YÜKLEMEZ)."""
    if image_dict.get('type') != 'image':
        logging.warning(f"Deserialize image: Geçersiz tip: {image_dict.get('type')}")
        return None
    try:
        deserialized = {
            'uuid': image_dict.get('uuid'),
            'path': image_dict.get('path'), # Mutlak yol
            'angle': image_dict.get('angle', 0.0),
            'rect': _list_to_rect(image_dict['rect']) if 'rect' in image_dict else QRectF(),
            'pixmap': None # Pixmap burada yüklenmeyecek
        }
        if not deserialized['path']:
             logging.warning(f"Deserialize image: Resim yolu eksik: UUID {deserialized['uuid']}")
             # Belki burada hata vermek yerine None döndürmek daha iyi? Şimdilik devam edelim.
        return deserialized
    except Exception as e:
        logging.error(f"Resim deserialize edilirken hata ({image_dict}): {e}", exc_info=True)
        return None
# --- --- --- --- --- --- --- --- --- --- --- --- ---

def _serialize_item(item_data: List[Any]) -> Dict[str, Any]:
    """Tek bir çizgi veya şekil verisini JSON uyumlu sözlüğe dönüştürür."""
    item_type = 'line' if not isinstance(item_data[0], ToolType) else 'shape'
    
    if item_type == 'line':
        # Line: [color_tuple, width_float, List[QPointF], Optional[line_style_str]]
        if len(item_data) >= 3:
            serialized = {
                'type': 'line',
                'color': list(item_data[0]),
                'width': item_data[1],
                'points': [_point_to_list(p) for p in item_data[2]]
            }
            # YENİ: Çizgi stilini ekle (varsa)
            if len(item_data) >= 4 and item_data[3] is not None:
                serialized['line_style'] = item_data[3]
            return serialized
        else:
             logging.warning(f"Geçersiz çizgi verisi formatı: {item_data}")
             return {} # Boş sözlük döndür
    elif item_type == 'shape':
        # Shape: [ToolType_enum, color_tuple, width, p1, p2, Optional[line_style_str], Optional[fill_rgba_tuple]]
        if len(item_data) >= 5:
             serialized = {
                 'type': 'shape',
                 'tool': item_data[0].name,
                 'color': list(item_data[1]),
                 'width': item_data[2],
                 'p1': _point_to_list(item_data[3]),
                 'p2': _point_to_list(item_data[4]),
             }
             # YENİ: Çizgi stilini ekle (varsa)
             if len(item_data) >= 6 and item_data[5] is not None:
                 serialized['line_style'] = item_data[5]
             # YENİ: Dolgu rengini ekle (varsa)
             if len(item_data) >= 7 and item_data[6] is not None:
                 serialized['fill_rgba'] = list(item_data[6]) # Tuple'ı listeye çevir
             return serialized
        else:
            logging.warning(f"Geçersiz şekil verisi formatı: {item_data}")
            return {}
    else:
         logging.warning(f"Bilinmeyen öğe tipi: {item_data}")
         return {}

def _deserialize_item(item_dict: Dict[str, Any]) -> List[Any] | None:
    """JSON uyumlu sözlükten çizgi veya şekil verisi listesini oluşturur."""
    item_type = item_dict.get('type')
    
    try:
        if item_type == 'line':
            points = [_list_to_point(p_list) for p_list in item_dict.get('points', [])]
            deserialized = [
                tuple(item_dict['color']),
                item_dict['width'],
                points
            ]
            # YENİ: Çizgi stilini ekle (varsa)
            line_style = item_dict.get('line_style')
            if line_style:
                deserialized.append(line_style)
            return deserialized
        elif item_type == 'shape':
            tool_name = item_dict.get('tool')
            if not tool_name: return None
            try:
                tool_enum = ToolType[tool_name]
            except KeyError:
                logging.warning(f"Bilinmeyen araç tipi adı: {tool_name}")
                return None
                
            deserialized = [
                tool_enum,
                tuple(item_dict['color']),
                item_dict['width'],
                _list_to_point(item_dict['p1']),
                _list_to_point(item_dict['p2'])
            ]
            # YENİ: Çizgi stilini ekle (varsa)
            line_style = item_dict.get('line_style')
            if line_style:
                deserialized.append(line_style)
            else: # Stil yoksa da listeyi tamamlamak için None ekleyebiliriz
                if len(deserialized) == 5: # Eğer sadece ilk 5 eleman varsa
                    deserialized.append('solid') # Varsayılan stil
            
            # YENİ: Dolgu rengini ekle (varsa)
            fill_rgba_list = item_dict.get('fill_rgba')
            if fill_rgba_list:
                # Eğer line_style yoksa, önce onu ekle
                if len(deserialized) == 5:
                     deserialized.append('solid') # Varsayılan stil
                deserialized.append(tuple(fill_rgba_list)) # Listeyi tuple'a çevir
            # Eğer dolgu yoksa ve stil varsa (len 6), None eklemeye gerek yok, draw_shape None kabul eder.
            # Eğer dolgu yoksa ve stil de yoksa (len 5), yukarıda stil eklendi, yine None eklemeye gerek yok.
            
            return deserialized
        else:
            logging.warning(f"Sözlükten öğe oluşturulurken bilinmeyen tip: {item_type}")
            return None
    except Exception as e:
        logging.error(f"Öğe deserialize edilirken hata ({item_dict}): {e}", exc_info=True)
        return None

# --- Ana Kaydet/Yükle Fonksiyonları ---

def save_notebook(filepath: str, pages: List['Page']):
    """Verilen sayfa listesini belirtilen dosyaya JSON formatında kaydeder.
    
    Args:
        filepath: Kaydedilecek dosyanın yolu.
        pages: Kaydedilecek Page nesnelerinin listesi.
    """
    try:
        notebook_to_save = []
        for page in pages:
            # Canvas yerine doğrudan Page'den alalım (veriler Page'de tutuluyordu)
            orientation = page.orientation # Yönü al
            canvas = page.get_canvas() # Çizimler için canvas yine de lazım

            # --- YENİ: images listesini de al ---
            images_to_serialize = []
            if hasattr(page, 'images') and isinstance(page.images, list):
                 for img_data in page.images:
                      serialized_img = _serialize_image(img_data)
                      if serialized_img: # Başarılı serialize olduysa ekle
                           images_to_serialize.append(serialized_img)
            else:
                 logging.warning(f"Sayfa {page.page_number}: 'images' özelliği bulunamadı veya liste değil.")
            # --- --- --- --- --- --- --- --- ---

            # YENİ: PDF arka plan yolunu al
            pdf_bg_path = None
            if canvas and hasattr(canvas, '_pdf_background_source_path'):
                pdf_bg_path = canvas._pdf_background_source_path

            serialized_page = {
                'lines': [_serialize_item(line) for line in canvas.lines if line],
                'shapes': [_serialize_item(shape) for shape in canvas.shapes if shape],
                'images': images_to_serialize, # Serileştirilmiş resimleri ekle
                'orientation': orientation.name, # Yön ismini kaydet
                'pdf_background_source_path': pdf_bg_path # YENİ: PDF arka plan yolunu kaydet
            }
            notebook_to_save.append(serialized_page)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(notebook_to_save, f, ensure_ascii=False, indent=4)
        logging.info(f"Not defteri başarıyla kaydedildi: {filepath}")
        return True
    except Exception as e:
        logging.error(f"Not defteri kaydedilirken hata oluştu: {e}", exc_info=True)
        return False

def load_notebook(filepath: str) -> List[Dict[str, Any]] | None:
    """Belirtilen JSON dosyasından not defteri verilerini yükler.

    Args:
        filepath: Yüklenecek dosyanın yolu.

    Returns:
        Her biri {'lines': [...], 'shapes': [...], 'orientation': 'PORTRAIT'|'LANDSCAPE'} 
        içeren sözlüklerden oluşan liste veya hata durumunda None.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            loaded_notebook = json.load(f)
        
        pages_data = []
        if not isinstance(loaded_notebook, list):
             logging.error(f"Yüklenen dosya formatı geçersiz (liste değil): {filepath}")
             return None

        for page_dict in loaded_notebook:
            if not isinstance(page_dict, dict):
                logging.warning(f"Sayfa verisi sözlük değil, atlanıyor: {page_dict}")
                continue

            # --- YENİ: images listesini de deserialize et ---
            deserialized_images = []
            for image_dict in page_dict.get('images', []):
                 deserialized_img = _deserialize_image(image_dict)
                 if deserialized_img:
                      deserialized_images.append(deserialized_img)
            # --- --- --- --- --- --- --- --- --- --- --- ---

            # --- YENİ: orientation'ı tuple yerine string olarak sakla ---
            deserialized_page = {
                'lines': [],
                'shapes': [],
                'images': deserialized_images, # Deserialize edilmiş resimleri ekle
                'orientation': page_dict.get('orientation', Orientation.PORTRAIT.name), # String olarak al
                'pdf_background_source_path': page_dict.get('pdf_background_source_path') # YENİ: PDF arka plan yolunu oku
            }
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

            for item_dict in page_dict.get('lines', []):
                item = _deserialize_item(item_dict)
                if item: deserialized_page['lines'].append(item)

            for item_dict in page_dict.get('shapes', []):
                item = _deserialize_item(item_dict)
                if item: deserialized_page['shapes'].append(item)

            pages_data.append(deserialized_page)

        logging.info(f"Not defteri başarıyla yüklendi: {filepath} ({len(pages_data)} sayfa)")
        return pages_data
        
    except FileNotFoundError:
        logging.error(f"Yüklenecek dosya bulunamadı: {filepath}")
        return None
    except json.JSONDecodeError as e:
        logging.error(f"Dosya yüklenirken JSON hatası: {filepath} - {e}", exc_info=True)
        return None
    except Exception as e:
        logging.error(f"Not defteri yüklenirken genel hata oluştu: {filepath} - {e}", exc_info=True)
        return None 
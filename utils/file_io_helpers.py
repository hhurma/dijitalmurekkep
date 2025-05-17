# utils/file_io_helpers.py
"""Not defterini kaydetme ve yükleme ile ilgili yardımcı fonksiyonlar."""

import json
import logging
from typing import List, Dict, Any, Tuple
import numpy as np  # NumPy dizileri için gerekli
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
    if not item_data or len(item_data) < 3:
        logging.warning(f"Serileştirme için eksik veri: {item_data}")
        return None
    
    item_type = 'line' if not isinstance(item_data[0], ToolType) else 'shape'
    
    if item_type == 'line':
        # Line: [color_tuple, width_float, List[QPointF], Optional[line_style_str]]
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
        # Shape: [ToolType, color_tuple, width_float, p1, p2, ...]
        tool_type = item_data[0]
        
        # YENİ: Düzenlenebilir çizgileri özel olarak işle
        if tool_type == ToolType.EDITABLE_LINE:
            # Düzenlenebilir çizgiler için özel format kullan
            serialized = {
                'type': 'editable_line',
                'color': list(item_data[1]),
                'width': item_data[2],
                'points': [_point_to_list(p) for p in item_data[3]]
            }
            # Çizgi stilini ekle (varsa)
            if len(item_data) >= 5 and item_data[4] is not None:
                serialized['line_style'] = item_data[4]
            return serialized
        # YENİ: PATH için özel serialize
        elif tool_type == ToolType.PATH:
            # PATH şekilleri için 3. indekste points listesi var
            if len(item_data) <= 3 or not isinstance(item_data[3], list):
                logging.warning(f"PATH serileştirmesi için geçersiz/eksik veri. Points listesi bulunamadı: {item_data}")
                return None
                
            serialized = {
                'type': 'shape',
                'tool_type': tool_type.name,
                'color': list(item_data[1]),
                'width': item_data[2],
                'points': [_point_to_list(p) for p in item_data[3]],
                'line_style': item_data[4] if len(item_data) > 4 else 'solid'
            }
            logging.debug(f"PATH serileştirildi: {len(serialized['points'])} nokta")
            return serialized
        else:
            # Standart şekiller için
            serialized = {
                'type': 'shape',
                'tool_type': tool_type.name,
                'color': list(item_data[1]),
                'width': item_data[2],
                'p1': _point_to_list(item_data[3]),
                'p2': _point_to_list(item_data[4])
            }
            
            # İsteğe bağlı ekstra parametreler
            if len(item_data) >= 6 and item_data[5] is not None:
                serialized['line_style'] = item_data[5]
                
            if len(item_data) >= 7 and item_data[6] is not None:
                serialized['fill_rgba'] = list(item_data[6]) if item_data[6] else None
                
            return serialized

def _deserialize_item(item_dict: Dict[str, Any]) -> List[Any] | None:
    """JSON uyumlu sözlüğü çizgi veya şekil verisine dönüştürür."""
    if not item_dict:
        return None

    item_type = item_dict.get('type')
    if item_type == 'line':
        # Renk, genişlik ve noktaları çıkar
        color = item_dict.get('color')
        width = item_dict.get('width')
        points_list = item_dict.get('points')
        
        if color is None or width is None or points_list is None:
            logging.warning(f"Çizgi verisinde zorunlu alanlar eksik: {item_dict}")
            return None
        
        # Çizgi stilini al (varsa, yoksa None)
        line_style = item_dict.get('line_style')
            
        # Noktaları QPointF'e dönüştür
        points = [_list_to_point(p) for p in points_list]
        
        # Çizgi listesi döndür: [color_tuple, width_float, List[QPointF], Optional[line_style_str]]
        result = [tuple(color), width, points]
        if line_style is not None:
            result.append(line_style)
        
        return result
    
    elif item_type == 'shape':
        # Şekil verilerini çıkar
        tool_type_str = item_dict.get('tool_type')
        color = item_dict.get('color')
        width = item_dict.get('width')

        # PATH için özel kontrol
        if tool_type_str == 'PATH':
            points_list = item_dict.get('points')
            if not points_list:
                logging.warning(f"PATH deserialize: 'points' listesi bulunamadı: {item_dict}")
                return None
                
            line_style = item_dict.get('line_style', 'solid')
            
            if color is None or width is None:
                logging.warning(f"PATH verisinde zorunlu alanlar eksik: {item_dict}")
                return None
                
            try:
                tool_type = ToolType[tool_type_str]
            except (KeyError, ValueError):
                logging.warning(f"Geçersiz ToolType: {tool_type_str}")
                return None
                
            # Noktaları QPointF'e dönüştür 
            points = [_list_to_point(p) for p in points_list]
            logging.debug(f"PATH deserialize edildi: {len(points)} nokta")
            
            # [ToolType.PATH, color_tuple, width_float, List[QPointF], line_style]
            return [tool_type, tuple(color), width, points, line_style]
        # Standart şekiller
        else:
            p1_list = item_dict.get('p1')
            p2_list = item_dict.get('p2')
            
            if not all([tool_type_str, color, width, p1_list, p2_list]):
                logging.warning(f"Şekil verisinde zorunlu alanlar eksik: {item_dict}")
                return None
            
            # ToolType'a dönüştür
            try:
                tool_type = ToolType[tool_type_str]
            except (KeyError, ValueError):
                logging.warning(f"Geçersiz ToolType: {tool_type_str}")
                return None
            
            # QPointF'e dönüştür
            p1 = _list_to_point(p1_list)
            p2 = _list_to_point(p2_list)
            
            # İsteğe bağlı parametreler
            line_style = item_dict.get('line_style')
            fill_rgba = item_dict.get('fill_rgba')
            
            # Şekil listesi: [ToolType, color_tuple, width_float, p1, p2, Optional[line_style_str], Optional[fill_rgba_tuple]]
            result = [tool_type, tuple(color), width, p1, p2]
            
            if line_style is not None:
                result.append(line_style)
            elif fill_rgba is not None or 'fill_rgba' in item_dict:
                result.append(None)  # line_style yok ama fill_rgba var
                
            if fill_rgba is not None:
                result.append(tuple(fill_rgba))
                
            return result
    
    elif item_type == 'editable_line':
        # Düzenlenebilir çizgiyi deserialize et
        color = item_dict.get('color')
        width = item_dict.get('width')
        points_list = item_dict.get('points')
        
        if color is None or width is None or points_list is None:
            logging.warning(f"Düzenlenebilir çizgi verisinde zorunlu alanlar eksik: {item_dict}")
            return None
        
        # Çizgi stilini al (varsa, yoksa 'solid')
        line_style = item_dict.get('line_style', 'solid')
            
        # Noktaları QPointF'e dönüştür
        points = [_list_to_point(p) for p in points_list]
        
        # Düzenlenebilir çizgi formatı döndür: [ToolType.EDITABLE_LINE, color_tuple, width_float, List[QPointF], line_style_str]
        return [ToolType.EDITABLE_LINE, tuple(color), width, points, line_style]
    
    else:
        logging.warning(f"Bilinmeyen öğe türü: {item_type}")
        return None

# --- YENİ: B-Spline Serialize/Deserialize ---
def _serialize_bspline(stroke_data: Dict[str, Any]) -> Dict[str, Any]:
    """B-Spline stroke verisini JSON uyumlu sözlüğe dönüştürür."""
    try:
        serialized = {
            'type': 'bspline',
            'degree': stroke_data.get('degree', 3)
        }
        
        control_points_data = stroke_data.get('control_points')

        if isinstance(control_points_data, list) and all(isinstance(cp, np.ndarray) and cp.shape == (2,) for cp in control_points_data):
            # Durum 1: List[np.array([x,y])] -> List[List[float, float]]
            serialized['control_points'] = [cp.tolist() for cp in control_points_data]
        elif isinstance(control_points_data, np.ndarray) and control_points_data.ndim == 2 and control_points_data.shape[1] == 2:
            # Durum 2: np.array([[x1,y1], [x2,y2], ...]) -> List[List[float, float]]
            serialized['control_points'] = control_points_data.tolist()
        elif isinstance(control_points_data, list) and all(isinstance(cp, list) and len(cp) == 2 for cp in control_points_data):
            # Durum 3: Zaten List[List[float, float]] (veya QPointF'ten dönüştürülmüş olabilir)
            # Her bir iç listeyi float'a dönüştürdüğümüzden emin olalım
            serialized['control_points'] = [[float(coord) for coord in cp] for cp in control_points_data]
        else:
            logging.warning(f"B-Spline serialize: 'control_points' beklenmeyen formatta veya eksik. Format: {type(control_points_data)}. Veri: {control_points_data}")
            return None # Veya boş liste serialized['control_points'] = []
            
        # knots ve u parametreleri zaten NumPy array olmalı ve tolist() ile serileştirilmeli
        if 'knots' in stroke_data and isinstance(stroke_data['knots'], np.ndarray):
            serialized['knots'] = stroke_data['knots'].tolist()
        else:
            logging.warning(f"B-Spline serialize: knots eksik veya NumPy dizisi değil. Veri: {stroke_data.get('knots')}")
            # knots olmadan B-Spline çizilemez, bu yüzden None dönmek mantıklı olabilir.
            # Ancak bazen spline'lar sadece kontrol noktaları ile de ifade edilebilir (örneğin bezier).
            # Şimdilik devam edelim, ama bu bir potansiyel sorun noktası.
            serialized['knots'] = [] # Veya None ve yüklerken kontrol et

            
        if 'u' in stroke_data and isinstance(stroke_data['u'], np.ndarray):
            serialized['u'] = stroke_data['u'].tolist()
        else:
            # u parametresi scipy.interpolate.splev için gerekli.
            logging.warning(f"B-Spline serialize: u parametresi eksik veya NumPy dizisi değil. Veri: {stroke_data.get('u')}")
            serialized['u'] = [] # Veya None

            
        # Ek olarak renk, çizgi stili ve kalınlık bilgilerini de ekleyelim
        serialized['color'] = stroke_data.get('color', [0.0, 0.0, 0.0, 1.0]) # Renk zaten list of float olmalı
        serialized['width'] = float(stroke_data.get('width', 2.0))
        serialized['line_style'] = stroke_data.get('line_style', 'solid')

        # Orijinal noktaları da kaydet (varsa)
        if 'original_points_with_pressure' in stroke_data:
            original_points = stroke_data['original_points_with_pressure']
            # Format: [ (QPointF(x,y), pressure), ... ] veya [ (np.array([x,y]), pressure), ... ]
            # Hedef: [ [[x,y], pressure], ... ]
            serialized_orig_points = []
            for p_obj, pressure_val in original_points:
                if isinstance(p_obj, QPointF):
                    serialized_orig_points.append([ [p_obj.x(), p_obj.y()], float(pressure_val) ])
                elif isinstance(p_obj, np.ndarray) and p_obj.shape == (2,):
                    serialized_orig_points.append([ p_obj.tolist(), float(pressure_val) ])
                elif isinstance(p_obj, list) and len(p_obj) == 2: # Belki [[x,y], pressure] formatında geliyordur
                    serialized_orig_points.append([ [float(p_obj[0]), float(p_obj[1])], float(pressure_val) ])
                else:
                    logging.warning(f"B-Spline serialize: original_points_with_pressure içindeki nokta beklenmedik formatta: {type(p_obj)}")
            serialized['original_points_with_pressure'] = serialized_orig_points
        
        return serialized
    except Exception as e:
        logging.error(f"B-Spline serialize edilirken hata: {e}", exc_info=True)
        return None

def _deserialize_bspline(stroke_dict: Dict[str, Any]) -> Dict[str, Any]:
    """JSON uyumlu sözlükten B-Spline stroke verisi oluşturur."""
    if stroke_dict.get('type') != 'bspline':
        logging.warning(f"Deserialize bspline: Geçersiz tip: {stroke_dict.get('type')}")
        return None
        
    try:
        # Python listelerini NumPy dizilerine dönüştür
        control_points_list_of_lists = stroke_dict.get('control_points')
        
        # YENİ: control_points'i List[np.array([x,y])] formatına çevir
        if isinstance(control_points_list_of_lists, list) and all(isinstance(cp, list) and len(cp) == 2 for cp in control_points_list_of_lists):
            control_points = [np.array(cp_row, dtype=float) for cp_row in control_points_list_of_lists]
        else:
            # Eğer format beklenmedikse, eski davranışa (2D array) geri dön veya hata logla
            logging.warning(f"B-Spline deserialize: 'control_points' beklenen formatta değil (List[List[float, float]]). 2D NumPy array olarak yükleniyor: {control_points_list_of_lists}")
            control_points = np.array(control_points_list_of_lists) # Eski davranış (2D array)

        knots = np.array(stroke_dict.get('knots'))
        u_params = np.array(stroke_dict.get('u'))
        
        deserialized = {
            'control_points': control_points,
            'knots': knots,
            'u': u_params,
            'degree': stroke_dict.get('degree', 3),
            'color': stroke_dict.get('color', [0.0, 0.0, 0.0, 1.0]),
            'width': stroke_dict.get('width', 2.0),
            'line_style': stroke_dict.get('line_style', 'solid')
        }
        
        # Orijinal noktaları da yükle (varsa)
        if 'original_points_with_pressure' in stroke_dict:
            original_points_list = stroke_dict['original_points_with_pressure']
            # Format: [ [[x,y], pressure], ... ] 
            # Hedef: [ (QPointF(x,y), pressure), ... ]
            deserialized_orig_points = []
            for item in original_points_list:
                if isinstance(item, list) and len(item) == 2 and isinstance(item[0], list) and len(item[0]) == 2:
                    try:
                        point = QPointF(float(item[0][0]), float(item[0][1]))
                        pressure = float(item[1])
                        deserialized_orig_points.append((point, pressure))
                    except (ValueError, TypeError) as e_conv:
                        logging.warning(f"B-Spline deserialize: original_points_with_pressure öğesi dönüştürülemedi: {item}, hata: {e_conv}")
                else:
                    logging.warning(f"B-Spline deserialize: original_points_with_pressure öğesi beklenmeyen formatta: {item}")
            deserialized['original_points_with_pressure'] = deserialized_orig_points
            
        return deserialized
    except Exception as e:
        logging.error(f"B-Spline deserialize edilirken hata: {e}", exc_info=True)
        return None
# --- --- --- --- --- --- --- --- --- --- --- ---

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
                
            # YENİ: B-Spline strokes verilerini al
            bspline_strokes_to_serialize = []
            if canvas and hasattr(canvas, 'b_spline_strokes') and canvas.b_spline_strokes:
                for stroke_data in canvas.b_spline_strokes:
                    serialized_stroke = _serialize_bspline(stroke_data)
                    if serialized_stroke:
                        bspline_strokes_to_serialize.append(serialized_stroke)

            serialized_page = {
                'lines': [_serialize_item(line) for line in canvas.lines if line],
                'shapes': [_serialize_item(shape) for shape in canvas.shapes if shape],
                'images': images_to_serialize, # Serileştirilmiş resimleri ekle
                'orientation': orientation.name, # Yön ismini kaydet
                'pdf_background_source_path': pdf_bg_path, # YENİ: PDF arka plan yolunu kaydet
                'bspline_strokes': bspline_strokes_to_serialize # YENİ: B-Spline verilerini ekle
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

            # --- YENİ: B-Spline stroke verilerini deserialize et ---
            deserialized_bsplines = []
            for bspline_dict in page_dict.get('bspline_strokes', []):
                deserialized_bspline = _deserialize_bspline(bspline_dict)
                if deserialized_bspline:
                    deserialized_bsplines.append(deserialized_bspline)
            # --- --- --- --- --- --- --- --- --- --- --- ---

            # --- YENİ: orientation'ı tuple yerine string olarak sakla ---
            deserialized_page = {
                'lines': [],
                'shapes': [],
                'images': deserialized_images, # Deserialize edilmiş resimleri ekle
                'orientation': page_dict.get('orientation', Orientation.PORTRAIT.name), # String olarak al
                'pdf_background_source_path': page_dict.get('pdf_background_source_path'), # YENİ: PDF arka plan yolunu oku
                'bspline_strokes': deserialized_bsplines # YENİ: B-Spline verilerini ekle
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
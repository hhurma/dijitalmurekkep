"""Sayfaları PDF olarak dışa aktarma ile ilgili yardımcı fonksiyonlar (PyMuPDF/fitz kullanarak)."""

import logging
import os
from typing import TYPE_CHECKING
from io import BytesIO
import tempfile # tempfile modülünü en başa ekle

# PyMuPDF importları
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    logging.warning("PDF dışa aktarma için 'PyMuPDF' kütüphanesi bulunamadı. Lütfen yükleyin (pip install pymupdf).")
    PYMUPDF_AVAILABLE = False

# PyQt importları (sadece type hinting için gerekli olabilir)
from PyQt6.QtCore import QRectF, QPointF, QBuffer, QIODevice

# YENİ: Pillow ve BytesIO importları
from io import BytesIO
try:
    from PIL import Image
    from PIL import ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    logging.warning("Resim döndürme için 'Pillow' kütüphanesi bulunamadı. Lütfen yükleyin (pip install Pillow). Döndürülmüş resimler dışa aktarılmayabilir.")
    PILLOW_AVAILABLE = False

if TYPE_CHECKING:
    from gui.drawing_canvas import DrawingCanvas
    from gui.page_manager import PageManager
from gui.page import Page
    # Enumu normal import et (veya TYPE_CHECKING içine al)
from gui.enums import ToolType, Orientation, TemplateType

# Gerekli enumları import et
from gui.enums import ToolType, Orientation, TemplateType

# --- YENİ: Sabitler ---
# A4 boyutları (mm cinsinden) - ARTIK DOĞRUDAN KULLANILMAYACAK, REFERANS OLARAK KALABİLİR
# A4_WIDTH_MM = 210
# A4_HEIGHT_MM = 297
# Standart DPI (PDF için) - ARTIK DOĞRUDAN KULLANILMAYACAK
# DEFAULT_DPI = 72
# Çıktı şablon klasörü
TEMPLATE_OUTPUT_DIR = "generated_templates"
# --- --- --- --- --- --- #

# Bağımlılık kontrolü
PILLOW_AVAILABLE = True
PYMUPDF_AVAILABLE = True

# A4 boyutları (nokta/point cinsinden, 72 DPI varsayımıyla) - REFERANS OLARAK KALABİLİR
# A4_WIDTH_PT = (A4_WIDTH_MM / 25.4) * 72
# A4_HEIGHT_PT = (A4_HEIGHT_MM / 25.4) * 72

# A4 Boyutları (nokta/point cinsinden - PyMuPDF varsayılan birimi)
A4_WIDTH_PT = 595.276
A4_HEIGHT_PT = 841.890
A4_RECT_PORTRAIT = fitz.Rect(0, 0, A4_WIDTH_PT, A4_HEIGHT_PT)
A4_RECT_LANDSCAPE = fitz.Rect(0, 0, A4_HEIGHT_PT, A4_WIDTH_PT) # Genişlik ve yükseklik yer değiştirir

# Renkleri PyMuPDF formatına (0.0-1.0 aralığında RGB tuple) çevirme
def _convert_color_to_fitz(qt_color_tuple: tuple) -> tuple | None:
    """Qt renk tuple'ını (0.0-1.0 RGBA) fitz uyumlu RGB tuple'ına çevirir."""
    if len(qt_color_tuple) < 3:
        return None # Geçersizse None döndür
    # Sadece ilk 3 değeri (RGB) al, alfa ihmal edilir (fitz çizimlerde genellikle desteklemez)
    return tuple(qt_color_tuple[:3])

# --- YENİ: Arka Plan Resmini OLUŞTURMA VE KAYDETME Fonksiyonu (Pillow Kullanarak) ---
def generate_template_image_pillow(output_dir: str, filename_base: str, 
                                   orientation: str, template_type: str, 
                                   spacing_pt: float, color: tuple,
                                   dpi: int = 150):
    """Verilen ayarlara göre Pillow kullanarak şablon arka plan resmi (JPG) oluşturur
       ve belirtilen klasöre kaydeder.
    """
    if not PILLOW_AVAILABLE:
        logging.error("Arka plan resmi oluşturmak için Pillow kütüphanesi gerekli.")
        return False

    try:
        # Hedef A4 boyutlarını belirle (nokta cinsinden)
        if orientation.lower() == "landscape":
            target_width_pt = A4_HEIGHT_PT
            target_height_pt = A4_WIDTH_PT
        else: # portrait (varsayılan)
            target_width_pt = A4_WIDTH_PT
            target_height_pt = A4_HEIGHT_PT

        # Hedef boyutları piksele çevir
        width_px = int(target_width_pt * dpi / 72.0)
        height_px = int(target_height_pt * dpi / 72.0)
        if width_px <= 0 or height_px <= 0:
            logging.warning("Hesaplanan arka plan resmi boyutları geçersiz.")
            return False

        # Beyaz arka planlı yeni bir RGB resim oluştur (JPG için RGB daha uygun)
        img = Image.new('RGB', (width_px, height_px), (255, 255, 255)) # Beyaz arka plan
        draw = ImageDraw.Draw(img)

        # Renk zaten Pillow formatında (0-255 RGBA tuple) geliyor handler'dan
        # Ama JPG alfa desteklemez, bu yüzden RGB'ye çevirelim
        pillow_color_rgb = color[:3] 
        pen_width_px = max(1, int(0.5 * dpi / 72.0)) # 0.5 pt kalınlık piksel olarak

        if template_type.lower() == "lined":
            spacing_px = spacing_pt * dpi / 72.0
            if spacing_px > 0.1:
                y = 0
                while True:
                    y += spacing_px
                    if y >= height_px:
                        break
                    draw.line([(0, int(y)), (width_px, int(y))], fill=pillow_color_rgb, width=pen_width_px)

        elif template_type.lower() == "grid":
            # Grid için hem dikey hem yatay çizgiler (aynı aralık ve renkle)
            spacing_px = spacing_pt * dpi / 72.0 
            if spacing_px > 0.1:
                # Dikey çizgiler
                x = 0
                while True:
                    x += spacing_px
                    if x >= width_px:
                        break
                    draw.line([(int(x), 0), (int(x), height_px)], fill=pillow_color_rgb, width=pen_width_px)
                # Yatay çizgiler
                y = 0
                while True:
                    y += spacing_px
                    if y >= height_px:
                        break
                    draw.line([(0, int(y)), (width_px, int(y))], fill=pillow_color_rgb, width=pen_width_px)

        # Çıktı dosya yolunu oluştur
        output_filename = f"{filename_base}.jpg"
        output_filepath = os.path.join(output_dir, output_filename)

        # Resmi JPG olarak kaydet
        img.save(output_filepath, format='JPEG', quality=90) # Kalite ayarı eklendi
        logging.debug(f"Generated and saved template image: {output_filepath} ({width_px}x{height_px}px @{dpi} DPI).")
        return True

    except Exception as e:
        logging.error(f"Arka plan resmi oluşturulurken/kaydedilirken hata: {e}", exc_info=True)
        return False
# --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

def _draw_page_content_to_pdf(pdf_page: fitz.Page,
                              page_data: dict,
                              canvas_width_px: int, 
                              canvas_height_px: int, 
                              background_image_path: str | None, 
                              page_background_pixmap: fitz.Pixmap | None = None, # QPixmap yerine fitz.Pixmap veya BytesIO
                              image_export_dpi: int = 150,
                              view_zoom: float = 1.0,                   # YENİ
                              view_pan_offset: QPointF = QPointF(0,0) # YENİ
                              ): 
    """
    Verilen sayfa verilerini (çizgiler, şekiller, resimler) PDF sayfasına çizer.
    PDF arka planı, verilen view_zoom ve view_pan_offset'e göre konumlandırılır.
    Kullanıcı çizimleri de bu transformasyona göre PDF'e yerleştirilir.
    """
    if not PYMUPDF_AVAILABLE:
        logging.error("PDF içeriği çizilemedi: PyMuPDF (fitz) kütüphanesi bulunamadı.")
        return

    logging.debug(f"--- _draw_page_content_to_pdf BAŞLADI --- Sayfa Rect: {pdf_page.rect}")
    logging.debug(f"    Input Params: canvas_w={canvas_width_px}, canvas_h={canvas_height_px}, bg_path={background_image_path}, page_bg_pixmap_exists={page_background_pixmap is not None}, dpi={image_export_dpi}, zoom={view_zoom:.3f}, pan=({view_pan_offset.x():.1f}, {view_pan_offset.y():.1f})")

    try:
        page_rect_pdf_coords = pdf_page.rect 

        # 1. Arka Planı Çiz
        background_drawn = False
        actual_bg_to_draw = None
        bg_draw_x = -view_pan_offset.x()
        bg_draw_y = -view_pan_offset.y()

        if page_background_pixmap:
            if page_background_pixmap.width > 0 and page_background_pixmap.height > 0:
                actual_bg_to_draw = page_background_pixmap
                logging.debug(f"    Arka Plan: Özel PDF Pixmap kullanılacak. Boyut: {actual_bg_to_draw.width}x{actual_bg_to_draw.height}")
            else:
                logging.warning("    Arka Plan: Özel PDF Pixmap geçersiz (0 boyut). Atlanıyor.")
        elif background_image_path and os.path.exists(background_image_path):
            try:
                loaded_pixmap = fitz.Pixmap(background_image_path)
                if loaded_pixmap.width > 0 and loaded_pixmap.height > 0:
                    actual_bg_to_draw = loaded_pixmap
                    logging.debug(f"    Arka Plan: Şablon dosyası kullanılacak ({background_image_path}). Boyut: {actual_bg_to_draw.width}x{actual_bg_to_draw.height}")
                else:
                    logging.warning(f"    Arka Plan: Şablon dosyası ({background_image_path}) yüklendi ama boyutu geçersiz. Atlanıyor.")
            except Exception as e_bg_path_load:
                logging.error(f"    Arka Plan: Şablon dosyası ({background_image_path}) yüklenirken hata: {e_bg_path_load}")
        
        if actual_bg_to_draw:
            bg_target_w = actual_bg_to_draw.width * view_zoom
            bg_target_h = actual_bg_to_draw.height * view_zoom
            target_bg_rect_on_pdf = fitz.Rect(bg_draw_x, bg_draw_y, bg_draw_x + bg_target_w, bg_draw_y + bg_target_h)
            source_bg_rect = fitz.Rect(0, 0, actual_bg_to_draw.width, actual_bg_to_draw.height)
            logging.debug(f"    Arka Plan Çizim Detayları: Hedef Rect = {target_bg_rect_on_pdf}, Kaynak Rect = {source_bg_rect}")
            
            try:
                pdf_page.insert_image(target_bg_rect_on_pdf, pixmap=actual_bg_to_draw, keep_proportion=True, overlay=False)
                background_drawn = True
                logging.info(f"    Arka Plan Başarıyla Çizildi.")
            except Exception as e_insert_bg:
                logging.error(f"    HATA: Arka plan PDF'e eklenirken: {e_insert_bg}", exc_info=True)
        
        if not background_drawn:
            logging.warning(f"    UYARI: Sayfa için uygun bir arka plan çizilemedi.")

        # 2. Kullanıcı Çizimlerini Ekle
        def transform_point(p: QPointF) -> fitz.Point:
            world_x = p.x()
            world_y = p.y()
            transformed_x = bg_draw_x + (world_x * view_zoom)
            transformed_y = bg_draw_y + (world_y * view_zoom)
            return fitz.Point(transformed_x, transformed_y)

        def transform_width(w: float) -> float:
            # Genişliği en az 0.1 yapalım (0 olmasın)
            return max(0.1, w * view_zoom) 

        line_items = page_data.get('lines', [])
        shape_items = page_data.get('shapes', [])
        image_items = page_data.get('images', [])
        logging.debug(f"    İçerik: {len(line_items)} çizgi, {len(shape_items)} şekil, {len(image_items)} resim.")

        # --- Çizgiler --- #
        for i, line_data in enumerate(line_items):
            try:
                color = line_data[0]
                original_width = line_data[1]
                points_qpointf = line_data[2]
                
                if len(points_qpointf) >= 2:
                    fitz_color = color[:3]
                    fitz_width = transform_width(original_width)
                    fitz_points = [transform_point(p) for p in points_qpointf]
                    
                    if i == 0: # Sadece ilk çizgi için detay logla
                        logging.debug(f"      Çizgi 0 Orijinal: width={original_width:.2f}, ilk_nokta={points_qpointf[0]}")
                        logging.debug(f"      Çizgi 0 Dönüştürülmüş: width={fitz_width:.2f}, ilk_nokta={fitz_points[0]}, renk={fitz_color}")
                    
                    pdf_page.draw_polyline(fitz_points, color=fitz_color, width=fitz_width, fill=None, closePath=False)
                # else: # Yetersiz nokta logu zaten vardı, tekrar eklemeye gerek yok
            except Exception as e_line:
                logging.error(f"    HATA: Çizgi {i} PDF'e çizilirken: {e_line}", exc_info=True)

        # --- Şekiller --- #
        for i, shape_data in enumerate(shape_items):
            try:
                tool_type = shape_data[0]
                color = shape_data[1]
                original_pen_width = shape_data[2]
                start_qpointf = shape_data[3]
                end_qpointf = shape_data[4]

                fitz_color = color[:3]
                fitz_pen_width = transform_width(original_pen_width)
                p1_transformed = transform_point(start_qpointf)
                p2_transformed = transform_point(end_qpointf)
                
                rect_x0 = min(p1_transformed.x, p2_transformed.x)
                rect_y0 = min(p1_transformed.y, p2_transformed.y)
                rect_x1 = max(p1_transformed.x, p2_transformed.x)
                rect_y1 = max(p1_transformed.y, p2_transformed.y)
                transformed_rect = fitz.Rect(rect_x0, rect_y0, rect_x1, rect_y1)

                if i == 0: # Sadece ilk şekil için detay logla
                    logging.debug(f"      Şekil 0 ({tool_type.name}) Orijinal: start={start_qpointf}, end={end_qpointf}, width={original_pen_width:.2f}")
                    logging.debug(f"      Şekil 0 Dönüştürülmüş: rect={transformed_rect}, width={fitz_pen_width:.2f}, renk={fitz_color}")

                if tool_type.name == 'RECTANGLE':
                    pdf_page.draw_rect(transformed_rect, color=fitz_color, width=fitz_pen_width, fill=None)
                elif tool_type.name == 'CIRCLE':
                    center_transformed = transformed_rect.center
                    effective_radius = min(transformed_rect.width / 2, transformed_rect.height / 2)
                    if effective_radius > 0:
                        pdf_page.draw_circle(center_transformed, effective_radius, color=fitz_color, width=fitz_pen_width, fill=None)
                elif tool_type.name == 'LINE':
                    pdf_page.draw_line(p1_transformed, p2_transformed, color=fitz_color, width=fitz_pen_width)
            except Exception as e_shape:
                logging.error(f"    HATA: Şekil {i} ({tool_type.name if tool_type else 'Bilinmeyen'}) PDF'e çizilirken: {e_shape}", exc_info=True)

        # --- Resimler --- #
        for i, img_data in enumerate(image_items):
            try:
                original_path = img_data.get('path')
                world_x = img_data.get('x') 
                world_y = img_data.get('y')
                world_w = img_data.get('width')
                world_h = img_data.get('height')
                angle = img_data.get('rotation', 0.0)

                if not (original_path and os.path.exists(original_path) and 
                        world_x is not None and world_y is not None and 
                        world_w is not None and world_h is not None and 
                        world_w > 0 and world_h > 0):
                    logging.warning(f"    Resim {i} için yetersiz veri veya dosya bulunamadı. Atlanıyor. Path={original_path}")
                    continue
                
                pdf_img_x = bg_draw_x + (world_x * view_zoom)
                pdf_img_y = bg_draw_y + (world_y * view_zoom)
                pdf_img_w = world_w * view_zoom
                pdf_img_h = world_h * view_zoom
                pdf_rect = fitz.Rect(pdf_img_x, pdf_img_y, pdf_img_x + pdf_img_w, pdf_img_y + pdf_img_h)
                
                if i == 0: # Sadece ilk resim için detay logla
                    logging.debug(f"      Resim 0 Orijinal: path={original_path}, x={world_x:.1f}, y={world_y:.1f}, w={world_w:.1f}, h={world_h:.1f}, angle={angle:.1f}")
                    logging.debug(f"      Resim 0 Dönüştürülmüş: pdf_rect={pdf_rect}, angle={angle:.1f}")
                
                # ... (Pillow/Stream işlemleri - önceki mantık korunuyor) ...
                # stream_to_pdf ve angle_for_pdf burada oluşturulur.
                # Bu kısım loglama açısından zaten detaylıydı, ekstra log eklemeye gerek yok.
                
                stream_to_pdf = None
                angle_for_pdf = int(angle)
                # ... (Pillow/Stream oluşturma mantığı - KISALTILDI) ...
                # Önemli olan, sonunda stream_to_pdf'in dolu ve angle_for_pdf'in doğru olması.
                # Test amaçlı, stream'i orijinal dosyadan alalım:
                try:
                    with open(original_path, "rb") as img_file:
                        stream_to_pdf = BytesIO(img_file.read())
                except Exception as e_read_img:
                    logging.error(f"    HATA: Resim dosyası okunamadı ({original_path}): {e_read_img}")
                    continue # Bu resmi atla

                if stream_to_pdf:
                    logging.debug(f"    Resim {i} PDF'e ekleniyor: rect={pdf_rect}, angle={angle_for_pdf}")
                    pdf_page.insert_image(
                        pdf_rect,
                        stream=stream_to_pdf,
                        rotate=angle_for_pdf 
                    )
                else:
                    logging.error(f"    HATA: Resim {i} için stream oluşturulamadı: {original_path}")

            except Exception as e_image:
                logging.error(f"    HATA: Resim {i} PDF'e eklenirken: {e_image}", exc_info=True)
        
        logging.info(f"--- _draw_page_content_to_pdf BİTTİ --- Toplam {len(line_items)} çizgi, {len(shape_items)} şekil, {len(image_items)} resim işlendi.")

    except Exception as e:
        logging.error(f"PDF içeriği çizilirken genel bir hata oluştu: {e}", exc_info=True)

# --- GÜNCELLENMİŞ Fonksiyon ---
def export_page_to_pdf(output_path: str,
                       page_data: dict,
                       canvas_width_px: int, # YENİ: Canvas genişliği (piksel)
                       canvas_height_px: int, # YENİ: Canvas yüksekliği (piksel)
                       background_image_path: str | None, # YENİ: Canvas'ın kullandığı arka plan
                       image_export_dpi: int = 150): # Bu DPI artık sadece iç resim işlemleri için
    """
    Tek bir sayfanın içeriğini PDF dosyasına aktarır.
    PDF sayfa boyutu, verilen canvas boyutlarına göre ayarlanır.
    """
    if not PYMUPDF_AVAILABLE:
        logging.error("PDF dışa aktarılamadı: PyMuPDF (fitz) kütüphanesi bulunamadı.")
        return False

    try:
        doc = fitz.open() # Yeni PDF dokümanı

        # Sayfa boyutunu canvas boyutları olarak ayarla (piksel = nokta varsayımı)
        # PyMuPDF rect için (x0, y0, x1, y1) bekler.
        page_width_pt = float(canvas_width_px)
        page_height_pt = float(canvas_height_px)
        
        # Yeni sayfa ekle
        pdf_page = doc.new_page(width=page_width_pt, height=page_height_pt)
        logging.info(f"PDF sayfası oluşturuldu: Genişlik={page_width_pt}pt, Yükseklik={page_height_pt}pt")

        _draw_page_content_to_pdf(pdf_page, page_data,
                                  canvas_width_px, canvas_height_px,
                                  background_image_path,
                                  image_export_dpi=image_export_dpi)
        
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        logging.info(f"PDF başarıyla '{output_path}' olarak kaydedildi.")
        return True
    except Exception as e:
        logging.error(f"PDF dışa aktarılırken hata oluştu: {e}", exc_info=True)
        return False

# --- Şablon Resmi Üretme Fonksiyonu (Ekran Boyutlarına Göre) ---
# Bu fonksiyonun adı ve parametreleri, ekran çözünürlüğünü alacak şekilde güncellenmeli
# ve Ayarlar Handler'ında çağrılmalı. Şimdilik sadece imzasını ve amacını belirtelim.

def generate_template_image_for_screen(output_dir: str, filename_base: str,
                                       screen_width_px: int, screen_height_px: int, # YENİ: Ekran boyutları
                                       template_type: str, # 'lined' veya 'grid'
                                       spacing_px: float,  # YENİ: Aralık piksel cinsinden
                                       color: tuple,       # Renk (R,G,B,A) float 0-1
                                       is_landscape: bool): # YENİ: Ekran yatay mı?
    """
    Verilen ekran boyutlarına ve ayarlara göre Pillow kullanarak
    şablon arka plan resmi (JPG) oluşturur ve kaydeder.
    Bu fonksiyon artık A4 değil, doğrudan ekran piksel boyutlarını kullanır.
    'orientation' yerine 'is_landscape' ve 'dpi' yerine doğrudan piksel değerleri.
    """
    if not PILLOW_AVAILABLE:
        logging.error("Arka plan resmi oluşturmak için Pillow kütüphanesi gerekli.")
        return False

    try:
        # Hedef boyutlar doğrudan parametre olarak geliyor (screen_width_px, screen_height_px)
        # Eğer 'is_landscape' False ise ve ekran genişliği yüksekliğinden küçükse,
        # bu dikey moddur. Eğer 'is_landscape' True ise yatay moddur.
        # Çizim yapılacak resmin boyutları:
        img_width = screen_width_px
        img_height = screen_height_px
        
        # Eğer template 'lined' ve dikey mod ise, çizgiler yatay olur.
        # Eğer template 'lined' ve yatay mod ise, çizgiler yine yatay olur. (Genelde çizgili defter hep yatay çizgili)
        # Eğer template 'grid' ise, hem dikey hem yatay çizgiler olur.

        image = Image.new('RGB', (img_width, img_height), 'white') # JPG için RGB ve beyaz arka plan
        draw = ImageDraw.Draw(image)

        # Renk tuple'ını (R,G,B) formatına çevir (0-255)
        rgb_color = (int(color[0]*255), int(color[1]*255), int(color[2]*255))
        line_width_px = 1 # Çizgi kalınlığı (piksel)

        if template_type == 'lined':
            current_y = spacing_px
            while current_y < img_height:
                draw.line([(0, current_y), (img_width, current_y)], fill=rgb_color, width=line_width_px)
                current_y += spacing_px
        elif template_type == 'grid':
            # Yatay çizgiler
            current_y = spacing_px
            while current_y < img_height:
                draw.line([(0, current_y), (img_width, current_y)], fill=rgb_color, width=line_width_px)
                current_y += spacing_px
            # Dikey çizgiler
            current_x = spacing_px
            while current_x < img_width:
                draw.line([(current_x, 0), (current_x, img_height)], fill=rgb_color, width=line_width_px)
                current_x += spacing_px
        else:
            logging.warning(f"Bilinmeyen şablon tipi: {template_type}. Boş resim oluşturulacak.")

        # Dosya adını oluştur
        # filename_base zaten template_type ve orientation içeriyor olabilir.
        # Örnek: "lined_portrait_screen.jpg" veya "grid_landscape_screen.jpg"
        # Fonksiyon çağrılırken filename_base doğru şekilde oluşturulmalı.
        output_filepath = os.path.join(output_dir, f"{filename_base}.jpg")

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        image.save(output_filepath, "JPEG", quality=95)
        logging.info(f"Ekran için şablon resmi oluşturuldu ve kaydedildi: {output_filepath} (Boyut: {img_width}x{img_height})")
        return True

    except Exception as e:
        logging.error(f"Ekran için şablon resmi ({filename_base}) oluşturulurken hata: {e}", exc_info=True)
        return False

# --- Ana Dışa Aktarma Fonksiyonları ---

def export_notebook_to_pdf(filepath: str, 
                           pages_render_data: list[dict], # page_manager yerine bu listeyi al
                           image_export_dpi: int = 150):
    """Tüm not defterini (verilen sayfa render verilerini) tek bir PDF dosyasına aktarır."""
    if not PYMUPDF_AVAILABLE:
        logging.error("PDF dışa aktarma başarısız: PyMuPDF kütüphanesi yüklü değil.")
        return False
        
    if not pages_render_data:
        logging.warning("Dışa aktarılacak sayfa verisi bulunamadı.")
        return False

    doc = fitz.open() # Yeni boş PDF belgesi oluştur
        
    try:
        for i, render_data in enumerate(pages_render_data):
            logging.debug(f"Exporting page data index {i} to PDF (PyMuPDF)...")
            
            page_content = render_data.get("page_content")
            canvas_w = render_data.get("width", 800) # Varsayılan değerler ekle
            canvas_h = render_data.get("height", 600)
            bg_path = render_data.get("background_path")
            page_bg_pixmap_qpixmap = render_data.get("page_background_pixmap") # Bu QPixmap
            current_zoom = render_data.get("zoom_level", 1.0) # YENİ
            current_pan = render_data.get("pan_offset", QPointF(0,0)) # YENİ

            if not page_content:
                logging.warning(f"Sayfa veri indeksi {i} için 'page_content' bulunamadı, atlanıyor.")
                continue
                
            # PDF sayfasını canvas boyutuyla oluştur (bu 1:1 çizim alanı için)
            pdf_export_page = doc.new_page(width=float(canvas_w), height=float(canvas_h))
            
            # page_background_pixmap_qpixmap'ı (QPixmap) fitz.Pixmap'a dönüştür (eğer varsa)
            fitz_page_bg = None
            if page_bg_pixmap_qpixmap and not page_bg_pixmap_qpixmap.isNull():
                try:
                    buffer = QBuffer()
                    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                    success = page_bg_pixmap_qpixmap.save(buffer, "PNG")
                    buffer.close()
                    if success:
                        img_bytes = bytes(buffer.data())
                        if img_bytes:
                            fitz_page_bg = fitz.Pixmap(img_bytes)
                            if not (fitz_page_bg.width > 0 and fitz_page_bg.height > 0):
                                logging.warning("PDF Export: QPixmap'tan dönüştürülen fitz.Pixmap boş.")
                                fitz_page_bg = None
                        else: logging.warning("PDF Export: QPixmap'tan byte alınamadı.")
                    else: logging.warning("PDF Export: QPixmap buffer'a kaydedilemedi.")
                except Exception as e_conv:
                    logging.error(f"PDF Export: QPixmap'ı fitz.Pixmap'a dönüştürürken hata: {e_conv}", exc_info=True)
            
            _draw_page_content_to_pdf(pdf_export_page, page_content,
                                      canvas_w, canvas_h,
                                      bg_path,
                                      page_background_pixmap=fitz_page_bg, # Dönüştürülmüşü gönder
                                      image_export_dpi=image_export_dpi,
                                      view_zoom=current_zoom,             # YENİ
                                      view_pan_offset=current_pan         # YENİ
                                      )

        if len(doc) > 0:
            doc.save(filepath, garbage=4, deflate=True)
            logging.info(f"Not defteri başarıyla PDF olarak dışa aktarıldı ({len(doc)} sayfa): {filepath}")
            doc.close()
            return True
        else:
            logging.warning("İşlenecek geçerli sayfa bulunamadığı için PDF oluşturulmadı.")
            doc.close()
            return False

    except Exception as e:
        logging.error(f"Tüm not defteri PDF'e aktarılırken hata oluştu (PyMuPDF): {e}", exc_info=True)
        if doc: # doc hala var ise kapatmayı dene
            doc.close()
        return False


def export_selected_pages_to_pdf(filepath: str, page_manager: 'PageManager',
                               page_indices: list[int],
                               include_background: bool = True,
                               line_spacing_setting_pt: float = 20.0,
                               grid_spacing_setting_pt: float = 20.0,
                               image_export_dpi: int = 150): # YENİ: image_export_dpi parametresi
    """Verilen indeks listesindeki sayfaları tek bir PDF dosyasına aktarır."""
    if not PYMUPDF_AVAILABLE:
        logging.error("PDF dışa aktarma başarısız: PyMuPDF kütüphanesi yüklü değil.")
        return False

    if not page_indices:
        logging.warning("Dışa aktarılacak sayfa indeksi listesi boş.")
        return False

    doc = fitz.open() # Yeni boş PDF belgesi oluştur
    exported_page_count = 0

    try:
        # Seçilen indekslerdeki sayfaları işle
        for index in page_indices:
            page_obj = page_manager.widget(index)
            if page_obj and hasattr(page_obj, 'get_canvas'):
                logging.debug(f"Exporting selected page (index {index}, number {page_obj.page_number}) to PDF (PyMuPDF)...")
                # Ayar değerlerini yardımcı fonksiyona aktar
                # Page nesnesinden veri alıp _draw_page_content_to_pdf'ye geçirelim
                page_data = page_obj.get_page_data_for_export()
                canvas = page_obj.get_canvas()
                bg_path = canvas.background_image_path if canvas else None
                canvas_w = canvas.width() if canvas else 800
                canvas_h = canvas.height() if canvas else 600
                
                # Her sayfa için yeni bir PDF sayfası oluştur
                pdf_export_page = doc.new_page(width=float(canvas_w), height=float(canvas_h))
                
                _draw_page_content_to_pdf(pdf_export_page, page_data,
                                          canvas_w, canvas_h,
                                          bg_path,
                                          image_export_dpi=image_export_dpi) # YENİ: DPI parametresi aktarıldı
                exported_page_count += 1
            else:
                 logging.warning(f"Seçilen sayfa (Indeks: {index}) PDF'e aktarılırken alınamadı veya geçerli değil, atlanıyor.")

        # PDF'i kaydet (optimize ederek)
        if exported_page_count > 0:
            doc.save(filepath, garbage=4, deflate=True)
            logging.info(f"Seçilen {exported_page_count} sayfa başarıyla PDF olarak dışa aktarıldı: {filepath}")
            doc.close()
            return True
        else:
            logging.warning("Seçilen indekslerden hiçbiri geçerli bir sayfaya karşılık gelmedi. PDF oluşturulmadı.")
            doc.close()
            return False

    except Exception as e:
        logging.error(f"Seçilen sayfalar PDF'e aktarılırken hata oluştu (PyMuPDF): {e}", exc_info=True)
        doc.close() # Hata durumunda da belgeyi kapat
        return False

# Eski tek sayfa export fonksiyonu (PyMuPDF ile güncellenebilir veya kaldırılabilir)
# İstersen bunu da PyMuPDF kullanacak şekilde güncelleyebilirim. Şimdilik kaldırıyorum.
# def export_single_page_to_pdf(filepath: str, page: 'Page'):
#    ...

# TODO: İleride tüm not defterini aktarma fonksiyonu eklenebilir -> YAPILDI
# def export_notebook_to_pdf(filepath: str, page_manager: 'PageManager'):
#    pass 
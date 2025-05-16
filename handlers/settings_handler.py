import logging
import os
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QColorDialog, QScrollArea
from PyQt6.QtGui import QGuiApplication

# Dialogları import et
from gui.settings_dialog import TemplateSettingsDialog, PointerSettingsDialog
# Yardımcı fonksiyonlar için import
from utils.pdf_export_helpers import generate_template_image_for_screen, TEMPLATE_OUTPUT_DIR
# Enums
from gui.enums import TemplateType, Orientation

# Type checking importları
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gui.arayuz import MainWindow
    from gui.drawing_canvas import DrawingCanvas
    from gui.page import Page

PT_TO_PX = 96 / 72.0 # Varsayılan 96 DPI için punto -> piksel çevrimi

# --- YENİ: A4 Boyutları (96 DPI) --- #
A4_WIDTH_96DPI = 794
A4_HEIGHT_96DPI = 1123
# --- --- --- --- --- --- --- --- --- -- #

def handle_open_template_settings(main_window: 'MainWindow'):
    """Sayfa şablonu ayarları dialogunu açar ve sonuçları işler."""
    logging.debug("Sayfa ayarları dialogu açılıyor...")
    
    current_settings = main_window.settings.get('template_settings', {}).copy()
    dialog = TemplateSettingsDialog(current_settings, parent=main_window)
    
    # --- Anlık Güncelleme Bağlantıları ---
    active_page = main_window.page_manager.get_current_page()
    active_canvas = active_page.get_canvas() if active_page else None
    
    # Anlık değişiklikleri uygulamak için küçük bir yardımcı fonksiyon
    def _handle_apply_request(settings: dict):
        if active_canvas:
            try:
                logging.debug(f"Applying temporary settings to active canvas: {settings}")
                active_canvas.apply_template_settings(settings)
            except Exception as e:
                logging.error(f"Error applying temporary settings: {e}")
                
    if active_canvas:
        try:
            # Sinyalleri aktif canvas'ın metodlarına bağla
            dialog.line_spacing_changed.connect(active_canvas.update_line_spacing)
            dialog.grid_spacing_changed.connect(active_canvas.update_grid_spacing)
            # Yeni renk sinyallerini bağla
            dialog.line_color_changed.connect(active_canvas.update_line_color)
            dialog.grid_color_changed.connect(active_canvas.update_grid_color)
            # Yeni apply sinyalini bağla
            dialog.apply_settings_requested.connect(_handle_apply_request)
            
            logging.debug("Dialog sinyalleri aktif canvas'a bağlandı.")
        except AttributeError as e:
             logging.error(f"Canvas'ta güncelleme metodu bulunamadı: {e}")
        except Exception as e:
             logging.error(f"Dialog sinyallerini bağlarken hata: {e}")
    else:
        logging.warning("Ayarları anlık güncellemek için aktif canvas bulunamadı.")
    # --- --- ---

    # --- YENİ: Şablon Oluşturma Sinyal Bağlantıları --- #
    try:
        # --- DÜZELTME: Lambda ile main_window'u geçir --- #
        dialog.generate_templates_requested.connect(lambda settings_dict: handle_generate_template_images(main_window))
        # dialog.generate_templates_requested.connect(main_window._handle_templates_generated) # Bu bağlantı kaldırıldı
        logging.debug("Şablon oluşturma sinyali bağlandı.")
    except Exception as e:
        logging.error(f"Şablon oluşturma sinyali bağlanırken hata: {e}")
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    if dialog.exec():
        new_settings = dialog.get_settings()
        logging.info("Sayfa ayarları dialogu kabul edildi.")
        
        # --- YENİ: MainWindow'daki ayarları güncelle --- #
        # Sadece template ile ilgili kısmı güncellemek daha güvenli
        main_window.settings['template_settings'] = new_settings
        # --- --- --- --- --- --- --- --- --- --- --- --- #

        # Ayarları aktif canvas'a uygula
        canvas = main_window.page_manager.get_current_page().get_canvas() if main_window.page_manager.get_current_page() else None
        if canvas:
            canvas.apply_template_settings(new_settings)
        
        # --- DÜZELTME: settings argümanını gönder --- #    
        main_window._save_settings(main_window.settings) # Ayarları JSON'a kaydet
        # --- --- --- --- --- --- --- --- --- --- --- -- #

        # 3. Tüm mevcut canvasları yeni ayarlarla güncelle
        logging.debug("Mevcut tüm canvaslar güncelleniyor...")
        for i in range(main_window.page_manager.count()):
            # --- DEĞİŞİKLİK: ScrollArea'dan Page'i al --- #
            scroll_area = main_window.page_manager.widget(i)
            page = None
            if isinstance(scroll_area, QScrollArea):
                widget_inside = scroll_area.widget()
                if widget_inside.__class__.__name__ == 'Page':
                    page = widget_inside
            # --- --- --- --- --- --- --- --- --- --- -- #

            if page and hasattr(page, 'get_canvas'):
                canvas = page.get_canvas()
                if canvas:
                    try:
                         canvas.apply_template_settings(new_settings) # Bu metodu Canvas'a ekleyeceğiz
                         logging.debug(f"Canvas {i} güncellendi.")
                    except Exception as e:
                         logging.error(f"Canvas {i} güncellenirken hata: {e}")
                         
        logging.info("Sayfa ayarları başarıyla güncellendi ve kaydedildi.")
    else:
        logging.info("Sayfa ayarları dialogu iptal edildi.")
        # İptal durumunda anlık değişiklikleri geri al? 
        # Şimdilik sadece kaydetmiyoruz. Anlık renk değişimi yapmadığımız için sorun yok.
        # Aralıkları eski haline getirmek için orijinal ayarları saklayıp burada geri yükleyebiliriz.
        if active_canvas: 
             try:
                 # Orijinal ayarlarla canvas'ı eski haline getir
                 active_canvas.apply_template_settings(current_settings) 
                 logging.debug("İptal edildi, aktif canvas eski ayarlara döndürüldü.")
             except Exception as e:
                  logging.error(f"İptal sonrası canvas eski haline getirilirken hata: {e}")

    # --- Bağlantıları Kes (Bellek sızıntısını önlemek için) ---
    if active_canvas:
        try:
             dialog.line_spacing_changed.disconnect(active_canvas.update_line_spacing)
             dialog.grid_spacing_changed.disconnect(active_canvas.update_grid_spacing)
             # Yeni renk ve apply bağlantılarını kes
             dialog.line_color_changed.disconnect(active_canvas.update_line_color)
             dialog.grid_color_changed.disconnect(active_canvas.update_grid_color)
             dialog.apply_settings_requested.disconnect(_handle_apply_request)
             logging.debug("Dialog sinyal bağlantıları aktif canvas'tan kesildi.")
        except TypeError: # Zaten bağlı değilse hata vermez
             pass 
        except Exception as e:
             logging.error(f"Dialog sinyal bağlantılarını keserken hata: {e}")
    # --- YENİ: Şablon Oluşturma Sinyal Bağlantısını Kes --- #
    try:
        # --- DÜZELTME: Bağlantıyı kes --- #
        dialog.generate_templates_requested.disconnect()
        # dialog.generate_templates_requested.disconnect(main_window._handle_templates_generated) # Bu bağlantı kaldırıldı
        logging.debug("Şablon oluşturma sinyal bağlantısı kesildi.")
    except TypeError: # Zaten bağlı değilse
        pass
    except Exception as e:
        logging.error(f"Şablon oluşturma sinyal bağlantısı kesilirken hata: {e}")
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

# --- YENİ: İşaretçi Ayarları Handler --- #
def handle_open_pointer_settings(main_window: 'MainWindow'):
    """İşaretçi ayarları penceresini açar ve ayarları yönetir."""
    from gui.pointer_settings_dialog import PointerSettingsDialog # Sadece burada import et
    
    # --- DEĞİŞİKLİK: Yeni faktörleri de settings'ten oku --- #
    current_pointer_settings = {
        # Eski ayarlar
        'laser_pointer_color': main_window.settings.get('laser_pointer_color', '#FF0000'),
        'laser_pointer_size': main_window.settings.get('laser_pointer_size', 10),
        'temp_pointer_color': main_window.settings.get('temp_pointer_color', '#FFA500'),
        'temp_pointer_width': main_window.settings.get('temp_pointer_width', 3.0),
        'temp_pointer_duration': main_window.settings.get('temp_pointer_duration', 5.0),
        # Yeni görünüm faktörleri
        'temp_glow_width_factor': main_window.settings.get('temp_glow_width_factor', 2.5),
        'temp_core_width_factor': main_window.settings.get('temp_core_width_factor', 0.5),
        'temp_glow_alpha_factor': main_window.settings.get('temp_glow_alpha_factor', 0.55),
        'temp_core_alpha_factor': main_window.settings.get('temp_core_alpha_factor', 0.9) 
    }
    # --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    dialog = PointerSettingsDialog(current_pointer_settings, parent=main_window)
    
    # --- YENİ: Diyalog açılmadan önce mevcut ayarları logla ---
    logging.debug(f"PointerSettingsDialog açılıyor. Başlangıç ayarları: {current_pointer_settings}")
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    if dialog.exec():
        new_settings = dialog.get_settings()
        # --- YENİ: Diyalogdan dönen ayarları logla ---
        logging.debug(f"PointerSettingsDialog kabul edildi. Alınan yeni ayarlar: {new_settings}")
        # --- --- --- --- --- --- --- --- --- --- --- ---
        
        # Ayarları MainWindow'daki ana settings sözlüğüne güncelle
        main_window.settings.update(new_settings) 
        # --- YENİ: Güncellenen ana ayarları logla ---
        logging.debug(f"MainWindow.settings güncellendi: {main_window.settings}")
        # --- --- --- --- --- --- --- --- --- --- --- ---

        # Güncellenmiş ayarları JSON'a kaydet
        logging.debug(f"_save_settings çağrılıyor...") # Kaydetme öncesi log
        main_window._save_settings(main_window.settings)
        
        # Ayarları aktif canvas'a uygula 
        main_window.apply_pointer_settings_to_canvas(new_settings) 
    else:
        logging.info("İşaretçi ayarları penceresi iptal edildi.")
# --- --- --- --- --- --- --- --- --- --- # 

# --- İMZA GÜNCELLENDİ: Tekrar MainWindow alır --- #
def handle_generate_template_images(main_window: 'MainWindow'):
    """Mevcut CANVAS boyutlarına ve KAYDEDİLMİŞ ayarlara göre 
       HEM DİKEY HEM YATAY şablon arka plan resimlerini (JPG) oluşturur.
    """
    logging.info("Mevcut Canvas boyutuna özel DİKEY ve YATAY şablon arka plan resimleri oluşturuluyor...")
    
    # Aktif canvas'ı al
    current_page = main_window.page_manager.get_current_page()
    if not current_page or not current_page.drawing_canvas:
        logging.error("Şablon oluşturmak için aktif canvas bulunamadı.")
        QMessageBox.warning(main_window, "Hata", "Şablonları oluşturmak için geçerli bir çizim alanı bulunamadı.")
        return
    canvas = current_page.drawing_canvas
    canvas_width = canvas.width()
    canvas_height = canvas.height()
    
    if canvas_width <= 0 or canvas_height <= 0:
        logging.error(f"Geçersiz canvas boyutları: {canvas_width}x{canvas_height}")
        QMessageBox.warning(main_window, "Hata", "Çizim alanının boyutları geçerli değil.")
        return
        
    logging.info(f"Kullanılacak Canvas boyutları: {canvas_width}x{canvas_height}")

    try:
        # 1. Gerekli Ayarları Al (Kaydedilmiş ayarlardan)
        settings = main_window.settings
        template_settings = settings.get('template_settings', {}) 
        line_color_rgba = template_settings.get("line_color", (0.8, 0.8, 1.0, 0.7))
        grid_color_rgba = template_settings.get("grid_color", (0.9, 0.9, 0.9, 0.8))
        line_spacing_pt = template_settings.get("line_spacing_pt", 28)
        grid_spacing_pt = template_settings.get("grid_spacing_pt", 14)

        # 2. Punto aralıklarını piksele çevir
        line_spacing_px = line_spacing_pt * PT_TO_PX
        grid_spacing_px = grid_spacing_pt * PT_TO_PX
        logging.debug(f"Hesaplanan aralıklar (px): Çizgi={line_spacing_px:.2f}, Izgara={grid_spacing_px:.2f}")

        # --- YENİ: Karışık Boyut Hesaplama --- #
        landscape_template_width = canvas_width # Canvas Genişliği
        landscape_template_height = A4_HEIGHT_96DPI # A4 Yüksekliği
        portrait_template_width = A4_WIDTH_96DPI # A4 Genişliği
        portrait_template_height = A4_HEIGHT_96DPI # DEĞİŞİKLİK: canvas_height -> A4_HEIGHT_96DPI
        logging.info(f"Oluşturulacak Şablon Boyutları: Yatay={landscape_template_width}x{landscape_template_height}, Dikey={portrait_template_width}x{portrait_template_height}")
        # --- --- --- --- --- --- --- --- --- --- #

        # 3. Şablonları Üret (Lined ve Grid, Hem Dikey hem Yatay - KARIŞIK BOYUTLARA GÖRE)
        output_dir = TEMPLATE_OUTPUT_DIR
        results = []

        # --- Lined - Dikey (A4 Genişlik x Canvas Yükseklik) --- #
        filename_base_lined_p = "lined_portrait_screen"
        results.append(generate_template_image_for_screen(
            output_dir=output_dir, filename_base=filename_base_lined_p,
            screen_width_px=portrait_template_width, 
            screen_height_px=portrait_template_height, 
            template_type='lined', spacing_px=line_spacing_px, color=line_color_rgba,
            is_landscape=False
        ))
        # --- Lined - Yatay (Canvas Genişlik x A4 Yükseklik) --- #
        filename_base_lined_l = "lined_landscape_screen"
        results.append(generate_template_image_for_screen(
            output_dir=output_dir, filename_base=filename_base_lined_l,
            screen_width_px=landscape_template_width, 
            screen_height_px=landscape_template_height, 
            template_type='lined', spacing_px=line_spacing_px, color=line_color_rgba,
            is_landscape=True
        ))
        # --- Grid - Dikey (A4 Genişlik x Canvas Yükseklik) --- #
        filename_base_grid_p = "grid_portrait_screen"
        results.append(generate_template_image_for_screen(
            output_dir=output_dir, filename_base=filename_base_grid_p,
            screen_width_px=portrait_template_width, 
            screen_height_px=portrait_template_height, 
            template_type='grid', spacing_px=grid_spacing_px, color=grid_color_rgba,
            is_landscape=False 
        ))
        # --- Grid - Yatay (Canvas Genişlik x A4 Yükseklik) --- #
        filename_base_grid_l = "grid_landscape_screen"
        results.append(generate_template_image_for_screen(
            output_dir=output_dir, filename_base=filename_base_grid_l,
            screen_width_px=landscape_template_width, 
            screen_height_px=landscape_template_height, 
            template_type='grid', spacing_px=grid_spacing_px, color=grid_color_rgba,
            is_landscape=True
        ))
        
        # 4. Sonuçları Kontrol Et ve Bildir
        if all(results):
            logging.info("Canvas/A4 karışık boyutlu tüm şablonlar başarıyla oluşturuldu.")
            QMessageBox.information(main_window, "Başarılı", 
                                    f"Canvas/A4 karışık boyutlu şablon arka planları başarıyla oluşturuldu ve '{output_dir}' klasörüne kaydedildi.")
            # --- YENİ: Canvas güncellemesini buraya taşıdık --- #
            canvas.load_background_template_image()
        else:
            logging.error("Canvas/A4 karışık boyutlu şablonlar oluşturulurken bir veya daha fazla hata oluştu.")
            QMessageBox.warning(main_window, "Hata", "Canvas/A4 şablonları oluşturulurken bazı hatalar oluştu. Lütfen logları kontrol edin.")

    except Exception as e:
        logging.error(f"Canvas/A4 karışık boyutlu şablonlar oluşturulurken genel hata: {e}", exc_info=True)
        QMessageBox.critical(main_window, "Kritik Hata", f"Canvas/A4 şablonları oluşturulurken beklenmedik bir hata oluştu:\n{e}")

# --- İşaretçi Ayarları --- #
def handle_show_pointer_settings(main_window: 'MainWindow'):
    # Mevcut ayarları al
    # ... (eski kodun ilgili kısmı buraya gelecek veya pass olacak)
    pass # Linter hatasını gidermek için geçici

def handle_apply_pointer_settings(dialog: PointerSettingsDialog, main_window: 'MainWindow'):
    # Dialogdan yeni ayarları al ve uygula
    # ... (eski kodun ilgili kısmı buraya gelecek veya pass olacak)
    pass # Linter hatasını gidermek için geçici

# --- --- --- --- --- --- --- --- --- --- # 
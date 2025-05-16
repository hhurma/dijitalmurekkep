# handlers/file_handler.py
"""Dosya işlemleri (Kaydet, Yükle, PDF Aktar) için handler fonksiyonları."""

import logging
from typing import TYPE_CHECKING, List
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication, QInputDialog, QScrollArea
from PyQt6.QtCore import QRectF, QPointF # QRectF ve QPointF importları eksik
import re # Sayfa aralığı ayrıştırma için eklendi
import os # Dosya işlemleri için eklendi
import time # Zaman işlemleri için eklendi

# Helperları import etfrom utils import file_io_helpers, pdf_export_helpers# from utils.pdf_export_helpers import REPORTLAB_AVAILABLE # Kaldırıldıfrom utils.pdf_export_helpers import PYMUPDF_AVAILABLE, export_notebook_to_pdf, export_selected_pages_to_pdf, export_page_to_pdf # PYMUPDF bayrağı ve fonksiyonlarfrom gui.enums import Orientation # Orientation enum'unu import et# from gui.drawing_canvas import DrawingCanvas # DrawingCanvas import edildi - Döngüsel import sorunu yaratabilir# from gui.arayuz import MAX_RECENT_FILES # Sabiti import et - KALDIRILDIif TYPE_CHECKING:    from gui.arayuz import MainWindow    from gui.page_manager import PageManager    from gui.page import Page  # Type hinting için Page sınıfını buraya taşıdık    from gui.drawing_canvas import DrawingCanvas  # Type hinting için buraya taşıdık

# Dosya uzantıları ve filtreler
NOTEBOOK_EXTENSION = ".dnd" # Digital Notes Data
NOTEBOOK_FILTER = f"Not Defteri (*{NOTEBOOK_EXTENSION})"
PDF_EXTENSION = ".pdf"
PDF_FILTER = "PDF Dosyası (*.pdf)"

def handle_save_notebook(main_window: 'MainWindow', page_manager: 'PageManager', save_as: bool = False) -> bool:
    """Mevcut not defterini bir dosyaya kaydeder.
    Eğer save_as True ise veya daha önce kaydedilmemişse dosya adı sorar.
    Başarı durumunu bool olarak döndürür.
    """
    if page_manager.count() == 0:
        QMessageBox.information(main_window, "Kaydetme", "Kaydedilecek sayfa bulunmuyor.")
        return False # Kaydedilecek bir şey yok

    filepath = main_window.current_notebook_path
    
    # Dosya yolu yoksa veya 'Farklı Kaydet' ise, kullanıcıdan yol iste
    if save_as or not filepath:
        selected_filepath, _ = QFileDialog.getSaveFileName(
            main_window, 
            "Farklı Kaydet" if save_as else "Not Defterini Kaydet", 
            filepath or "", # Mevcut yolu veya boş string'i öner
            NOTEBOOK_FILTER
        )
        
        if not selected_filepath:
            return False # Kullanıcı iptal etti
        filepath = selected_filepath
        
        # Dosya uzantısını kontrol et/ekle
        if not filepath.endswith(NOTEBOOK_EXTENSION):
            filepath += NOTEBOOK_EXTENSION
    
    # Gerekli kontrollerden sonra filepath'in geçerli olduğundan emin olmalıyız
    if not filepath:
         logging.error("Kaydetme işlemi için geçerli bir dosya yolu belirlenemedi.")
         QMessageBox.critical(main_window, "Kaydetme Hatası", "Geçerli bir dosya yolu belirlenemedi.")
         return False

    logging.info(f"Not defteri kaydediliyor: {filepath}")
    main_window.statusBar().showMessage(f"Not defteri kaydediliyor: {filepath}...", 3000)

    # Sayfa verilerini topla (Page nesneleri olarak)
    pages_to_save = []  # Type hinting için import'u Type_CHECKING içine taşıdık
    for i in range(page_manager.count()):
        # --- DEĞİŞİKLİK: ScrollArea'dan Page'i al --- #
        scroll_area = page_manager.widget(i)
        page = None
        if isinstance(scroll_area, QScrollArea):
            widget_inside = scroll_area.widget()
            # Tip kontrolü için doğrudan sınıf ismini kontrol etmek daha güvenli olabilir
            # Döngüsel importu önlemek için isinstance yerine sınıf adını kontrol ediyoruz
            if widget_inside.__class__.__name__ == 'Page':
                page = widget_inside
        # --- --- --- --- --- --- --- --- --- --- -- #

        if page: # Sadece geçerli Page nesnelerini ekle
            pages_to_save.append(page)
        else:
             logging.warning(f"Kaydederken {i}. sekmedeki widget alınamadı veya Page değil.")

    # Yardımcı fonksiyon ile kaydet
    success = file_io_helpers.save_notebook(filepath, pages_to_save)

    if success:
        # Kayıt başarılıysa, geçerli yolu ve pencere başlığını güncelle
        main_window.set_current_notebook_path(filepath)
        main_window.statusBar().showMessage(f"Not defteri başarıyla kaydedildi: {filepath}", 5000)
        # YENİ: Başarılı kayıttan sonra tüm sayfaları 'kaydedildi' olarak işaretle
        page_manager.mark_all_pages_as_saved()
        # Başarı durumunu döndür
        return True
    else:
        main_window.statusBar().showMessage(f"Not defteri kaydedilemedi!", 5000)
        QMessageBox.critical(main_window, "Kaydetme Hatası", f"Not defteri kaydedilirken bir hata oluştu.\nDosya: {filepath}")
        # Başarısızlık durumunu döndür
        return False

def handle_save_notebook_as(main_window: 'MainWindow', page_manager: 'PageManager') -> bool:
    """Not defterini her zaman yeni bir dosya adı sorarak kaydeder.
       Başarı durumunu bool olarak döndürür.
    """
    # handle_save_notebook zaten bool döndürüyor
    return handle_save_notebook(main_window, page_manager, save_as=True)

def handle_load_notebook(main_window: 'MainWindow', page_manager: 'PageManager'):
    """Bir not defteri dosyasını yükler."""
    # --- YENİ: Yüklemeden önce kaydetmeyi sor --- #
    if not main_window._prompt_save_before_action(lambda: handle_load_notebook(main_window, page_manager)):
         return # Kullanıcı iptal etti veya kaydetme başarısız oldu
    # ------------------------------------------ #

    # Mevcut sayfalar varsa kullanıcıyı uyar? (Bu kontrol _prompt_save_before_action içinde yapıldı, kaldırılabilir)
    # if page_manager.count() > 0:
    #     reply = QMessageBox.question(main_window,
    #                                  "Yükle",
    #                                  "Mevcut not defteri kapatılacak. Emin misiniz?",
    #                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    #                                  QMessageBox.StandardButton.No)
    #     if reply == QMessageBox.StandardButton.No:
    #         return

    # Yüklenecek dosyayı seçtir
    filepath, _ = QFileDialog.getOpenFileName(
        main_window, 
        "Not Defterini Aç", 
        "", 
        NOTEBOOK_FILTER
    )

    if not filepath:
        return

    logging.info(f"Not defteri yükleniyor: {filepath}")
    main_window.statusBar().showMessage(f"Not defteri yükleniyor: {filepath}...", 3000)
    
    # Yardımcı fonksiyon ile yükle
    loaded_data = file_io_helpers.load_notebook(filepath)

    if loaded_data is None:
        main_window.statusBar().showMessage(f"Not defteri yüklenemedi!", 5000)
        QMessageBox.critical(main_window, "Yükleme Hatası", f"Not defteri yüklenirken bir hata oluştu veya dosya geçersiz.\nDosya: {filepath}")
        # Yükleme başarısızsa mevcut yolu temizle
        main_window.set_current_notebook_path(None) 
        return

    # Başarılı yükleme -> Mevcut sayfaları temizle ve yenilerini ekle
    page_manager.clear_all_pages() # Doğru metodu çağır
    
    # Yüklenen dosya yolunu ayarla ve pencere başlığını güncelle
    main_window.set_current_notebook_path(filepath)
    # Başarılı yüklemeden sonra sayfaları 'kaydedildi' olarak işaretle
    page_manager.mark_all_pages_as_saved() 

    # --- YENİ: Son açılanlar listesini güncelle --- #
    if filepath:
        recent_files = main_window.settings.get('recent_files', [])
        max_files = main_window.settings.get('max_recent_files', 5) # Ayarlardan oku
        # Varsa kaldır
        if filepath in recent_files:
            recent_files.remove(filepath)
        # Başa ekle
        recent_files.insert(0, filepath)
        # Limiti uygula
        main_window.settings['recent_files'] = recent_files[:max_files] # Ayarlardan okunan limiti kullan
        # --- DÜZELTME: Ayarları argüman olarak gönder --- #
        main_window._save_settings(main_window.settings) # Ayarları kaydet
        # --- --- --- --- --- --- --- --- --- --- --- --- -- #
        if hasattr(main_window, '_update_recent_files_menu'):
             main_window._update_recent_files_menu()
    # --- --- --- --- --- --- --- --- --- --- ---

    if not loaded_data: # Dosya boşsa
         page_manager.add_page() # Yeni boş bir sayfa ekle
         logging.info("Yüklenen dosya boştu, yeni bir boş sayfa eklendi.")
    else:
        for page_content in loaded_data:
            # Yeni sayfa ve canvas oluştur
            new_page = page_manager.add_page(create_new=True) # Yeni, boş sayfa ekletelim
            if not new_page: # Ekleme başarısızsa atla
                 logging.error(f"Yeni sayfa yükleme sırasında oluşturulamadı.")
                 continue

            # Yüklenen veriyi canvas'a ata
            new_page.get_canvas().lines = page_content.get('lines', [])
            new_page.get_canvas().shapes = page_content.get('shapes', [])

            # --- YENİ: Resim verisini Page nesnesine ata --- #
            loaded_images_data = page_content.get('images', [])
            if loaded_images_data:
                # Pixmap'ları None olarak başlatmamız gerekiyor.
                # _ensure_pixmaps_loaded daha sonra bunları yükleyecek.
                new_page.images = [] # Önce temizle
                for img_data_loaded in loaded_images_data:
                    # Gerekli alanları kontrol et (path, rect, angle, uuid)
                    if all(k in img_data_loaded for k in ('path', 'rect', 'angle', 'uuid')):
                        img_data_for_page = {
                            'uuid': img_data_loaded['uuid'],
                            'path': img_data_loaded['path'],
                            'rect': QRectF(*img_data_loaded['rect']) if isinstance(img_data_loaded['rect'], list) else img_data_loaded['rect'], # rect list ise QRectF yap
                            'angle': img_data_loaded['angle'],
                            'pixmap': None, # Başlangıçta pixmap None
                            'pixmap_item': None # Başlangıçta None
                        }
                        new_page.images.append(img_data_for_page)
                        logging.debug(f"Loaded image data for page {new_page.page_number}: uuid={img_data_for_page['uuid']}")
                    else:
                        logging.warning(f"Skipping loaded image data due to missing keys: {img_data_loaded}")
            else:
                 new_page.images = [] # Resim yoksa boş liste
            # --- --- --- --- --- --- --- --- --- --- --- -- #

            # YENİ: Sayfa yönünü yükle
            loaded_orientation_name = page_content.get('orientation', Orientation.PORTRAIT.name) # String olarak al
            try:
                loaded_orientation = Orientation[loaded_orientation_name] # String'den Enum'a çevir
            except KeyError:
                logging.warning(f"Geçersiz orientation değeri '{loaded_orientation_name}' bulundu, varsayılan (PORTRAIT) kullanılıyor.")
                loaded_orientation = Orientation.PORTRAIT
            # --- DÜZELTME: set_orientation yerine property kullan ---\
            new_page.orientation = loaded_orientation
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

            # YENİ: PDF'ten gelen özel arka planı yükle
            pdf_bg_path = page_content.get('pdf_background_source_path')
            if pdf_bg_path and os.path.exists(pdf_bg_path):
                logging.info(f"Sayfa {new_page.page_number} için PDF arka planı yükleniyor: {pdf_bg_path}")
                new_page.set_background_image(pdf_bg_path)
            elif pdf_bg_path:
                logging.warning(f"Sayfa {new_page.page_number} için kayıtlı PDF arka plan yolu ({pdf_bg_path}) bulunamadı.")

            # Sayfayı manager'a ekle -> add_page zaten ekledi
            # page_manager.add_page(page=new_page)

    # Mevcut sayfaları temizledikten sonra, widget'ları hemen silmek QStackedWidget için sorun yaratabilir.
    # Belki clear_pages sonrası bir processEvents çağrısı gerekir?
    # Şimdilik böyle deneyelim.
    QApplication.processEvents() # Olay döngüsünü işletelim

    # --- YENİ: Yükleme sonrası aktif canvas'ı güncelle (Resimlerin görünmesi için) ---\
    if page_manager.count() > 0:
        # setCurrentIndex zaten yukarıda çağrılmış olabilir ama burada aktif sayfayı almak için tekrar kullanalım.
        # Eğer setCurrentIndex(0) henüz bir paint event tetiklemediyse, get_canvas() bunu yapabilir.
        active_page_widget = page_manager.get_current_page() # DEĞİŞİKLİK: current_page_widget -> get_current_page
        if active_page_widget and hasattr(active_page_widget, 'get_canvas'):
            canvas = active_page_widget.get_canvas() # Bu, _ensure_pixmaps_loaded ve _load_qgraphics_pixmap_items_from_page'i tetikler
            if canvas:
                logging.debug("Dosya yükleme sonrası aktif canvas için update() çağrılıyor.")
                canvas.update()
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---

    main_window.statusBar().showMessage(f"Not defteri başarıyla yüklendi: {filepath}", 5000)
    # İlk sayfayı göster
    if page_manager.count() > 0:
         page_manager.setCurrentIndex(0)

    """ # Mevcut çizimi ve ayarları kaydet
    main_window.page_manager.save_to_file(filepath)
    main_window.set_window_title(os.path.basename(filepath))
    main_window.add_recent_file(filepath)
    main_window.last_save_load_directory = os.path.dirname(filepath) # Son kullanılan dizini güncelle

    logging.info(f"Dosya başarıyla kaydedildi: {filepath}")
    QMessageBox.information(
        main_window,
        "Başarılı",
        f"Dosya başarıyla kaydedildi: {filepath}"
    ) """ 

def handle_export_pdf(main_window: 'MainWindow'):
    # --- YENİ: Çift Çağrı Kontrol Logu (Fonksiyon Başı) --- #
    call_timestamp = time.time()
    if hasattr(main_window, '_last_export_pdf_call') and call_timestamp - main_window._last_export_pdf_call < 1.0:
        logging.warning("handle_export_pdf: Fonksiyon 1 saniye içinde tekrar çağrıldı! Çift tıklama veya sinyal sorunu olabilir.")
        # return # İsteğe bağlı: Çift çağrıyı engellemek için buradan çıkılabilir
    else:
        logging.debug(f"handle_export_pdf çağrıldı. (Timestamp: {call_timestamp})")
    main_window._last_export_pdf_call = call_timestamp
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    # --- YENİ: PDF Resim Çözünürlüğü Ayarını Al --- #
    try:
        export_dpi = main_window.settings.get('template_settings', {}).get('pdf_export_image_dpi', 150)
        logging.debug(f"PDF dışa aktarma için kullanılacak DPI: {export_dpi}")
    except Exception as e:
        logging.error(f"Ayarlardan DPI okunurken hata: {e}. Varsayılan 150 DPI kullanılacak.")
        export_dpi = 150
    # --- --- --- --- --- --- --- --- --- --- --- -- #

    logging.debug("handle_export_pdf fonksiyonuna girildi.")
    if not PYMUPDF_AVAILABLE:
        QMessageBox.warning(main_window, "PDF Dışa Aktarma Hatası",
                              "PDF dışa aktarma için gerekli PyMuPDF kütüphanesi bulunamadı.")
        return

    page_manager = main_window.page_manager
    if page_manager.count() == 0:
        QMessageBox.warning(main_window, "Sayfa Yok", "Dışa aktarılacak sayfa bulunmuyor.")
        return

    # Kaydetme diyaloğunu göster
    filepath, _ = QFileDialog.getSaveFileName(
        main_window,
        "Not Defterini PDF Olarak Dışa Aktar", # Başlık güncellendi
        main_window.last_save_load_directory, 
        PDF_FILTER
    )

    if not filepath:
        return # Kullanıcı iptal etti

    if not filepath.lower().endswith(PDF_EXTENSION):
        filepath += PDF_EXTENSION

    main_window.last_save_load_directory = os.path.dirname(filepath)
    logging.info(f"Tüm not defteri PDF olarak dışa aktarılıyor: {filepath}")

    all_pages_render_data = []
    for i in range(page_manager.count()):
        scroll_area = page_manager.widget(i)
        page_widget: Page | None = None
        canvas: DrawingCanvas | None = None

        if isinstance(scroll_area, QScrollArea):
            widget_inside = scroll_area.widget()
            if isinstance(widget_inside, Page):
                page_widget = widget_inside
                if hasattr(page_widget, 'get_canvas'):
                    canvas = page_widget.get_canvas()
        
        if not page_widget or not canvas:
            logging.error(f"PDF Export: {i}. sayfa veya canvas alınamadı. Bu sayfa atlanacak.")
            QMessageBox.warning(main_window, "Sayfa Atlama", f"{i+1}. sayfa işlenemediği için PDF export işleminde atlanacaktır.")
            continue

        # Sayfa içeriğini (çizgiler, şekiller, resimler) al
        # Page nesnesinden export için veri al (artık Page sınıfında bu metod var varsayalım)
        page_content = page_widget.get_page_data_for_export()
        
        # Canvas boyutlarını al (render_data içinde yoksa varsayılan kullanıldı)
        canvas_width = canvas.width() if canvas else 800
        canvas_height = canvas.height() if canvas else 600
        background_path = canvas._current_background_image_path if canvas else None
        # Özel PDF arka planını al (QPixmap olarak)
        page_background_pixmap = canvas._page_background_pixmap if canvas and canvas._has_page_background else None

        logging.debug(f"  PDF Export için {i+1}. sayfa verisi toplandı. Arka plan: {background_path if background_path else 'Özel PDF Arka Planı' if page_background_pixmap else 'Yok'}")

        all_pages_render_data.append({
            "page_content": page_content,
            "width": canvas_width,
            "height": canvas_height,
            "background_path": background_path,
            "page_background_pixmap": page_background_pixmap,
            "zoom_level": page_widget.zoom_level,  # YENİ
            "pan_offset": page_widget.pan_offset   # YENİ
        })

    if not all_pages_render_data:
        QMessageBox.information(main_window, "Sayfa Yok", "Dışa aktarılacak geçerli sayfa verisi bulunamadı.")
        return

    # Güncellenmiş dışa aktarma fonksiyonunu çağır
    success = export_notebook_to_pdf(
        filepath,
        all_pages_render_data, # Toplanan tüm sayfa verileri
        image_export_dpi=export_dpi
    )

    if success:
        QMessageBox.information(main_window, "Başarılı", f"Not defteri başarıyla PDF olarak dışa aktarıldı:\n{filepath}")
    else:
        QMessageBox.critical(main_window, "PDF Dışa Aktarma Hatası", "Not defteri PDF olarak dışa aktarılırken bir hata oluştu. Lütfen logları kontrol edin.")

# --- Yeni Sayfa Seçimi Ayrıştırıcı ---
def _parse_page_selection(selection_str: str, max_page_index: int) -> list[int] | None:
    """
    Virgülle ayrılmış sayfa numaralarını ve aralıklarını (örn: "1, 3, 5-7")
    ayrıştırır ve sıralı, benzersiz, 0 tabanlı sayfa indekslerinin bir listesini döndürür.
    Giriş geçersizse veya sayfa numaraları aralık dışındaysa None döndürür.
    """
    indices = set()
    parts = selection_str.split(',')
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Aralık kontrolü (örn: "5-7")
        if '-' in part:
            match = re.fullmatch(r'(\d+)\s*-\s*(\d+)', part)
            if not match:
                logging.error(f"Geçersiz sayfa aralığı formatı: '{part}'")
                return None
            start_page = int(match.group(1))
            end_page = int(match.group(2))
            
            if start_page <= 0 or end_page <= 0 or start_page > end_page:
                logging.error(f"Geçersiz sayfa aralığı: {start_page}-{end_page}")
                return None
                
            start_index = start_page - 1
            end_index = end_page - 1
            
            if end_index > max_page_index:
                logging.error(f"Sayfa numarası ({end_page}) toplam sayfa sayısını ({max_page_index + 1}) aşıyor.")
                # QMessageBox.warning(QApplication.activeWindow(), "Hata", f"Sayfa numarası ({end_page}) toplam sayfa sayısını ({max_page_index + 1}) aşıyor.")
                return None 
                
            for i in range(start_index, end_index + 1):
                indices.add(i)
                
        # Tek sayfa numarası kontrolü
        else:
            try:
                page_num = int(part)
                if page_num <= 0:
                    logging.error(f"Geçersiz sayfa numarası (0 veya negatif): {page_num}")
                    return None
                
                index = page_num - 1
                if index > max_page_index:
                    logging.error(f"Sayfa numarası ({page_num}) toplam sayfa sayısını ({max_page_index + 1}) aşıyor.")
                    # QMessageBox.warning(QApplication.activeWindow(), "Hata", f"Sayfa numarası ({page_num}) toplam sayfa sayısını ({max_page_index + 1}) aşıyor.")
                    return None
                    
                indices.add(index)
            except ValueError:
                logging.error(f"Geçersiz sayfa numarası formatı: '{part}'")
                return None

    if not indices:
        logging.warning("Seçilen sayfa bulunamadı veya giriş boş.")
        return None
        
    return sorted(list(indices)) 

def handle_open_recent_file(main_window: 'MainWindow', page_manager: 'PageManager', filepath: str):
    """Verilen yoldaki not defteri dosyasını açar.
       Açmadan önce kaydedilmemiş değişiklikleri sorar.
    """
    logging.info(f"Son açılan dosya açılıyor: {filepath}")
    
    # --- YENİ: Açmadan önce kaydetmeyi sor --- #
    if not main_window._prompt_save_before_action(lambda: handle_open_recent_file(main_window, page_manager, filepath)):
         return # Kullanıcı iptal etti veya kaydetme başarısız oldu
    # ------------------------------------------ #
    
    # Dosya var mı kontrolü (isteğe bağlı ama önerilir)
    if not os.path.exists(filepath):
        logging.error(f"Son açılan dosya bulunamadı: {filepath}")
        QMessageBox.critical(main_window, "Hata", f"Dosya bulunamadı:\n{filepath}")
        # TODO: Kullanıcıya listeden kaldırma seçeneği sunulabilir?
        # Şimdilik sadece hata gösterelim.
        # Belki listeden otomatik kaldırabiliriz? Ayarları güncelleyip menüyü yenilemek gerekir.
        # main_window.settings['recent_files'].remove(filepath)
        # main_window._save_settings()
        # main_window._update_recent_files_menu()
        return

    main_window.statusBar().showMessage(f"Son açılan dosya yükleniyor: {filepath}...", 3000)
    
    # Yardımcı fonksiyon ile yükle
    loaded_data = file_io_helpers.load_notebook(filepath)

    if loaded_data is None:
        main_window.statusBar().showMessage(f"Dosya yüklenemedi: {filepath}", 5000)
        QMessageBox.critical(main_window, "Yükleme Hatası", f"Dosya yüklenirken bir hata oluştu veya dosya geçersiz.\nDosya: {filepath}")
        main_window.set_current_notebook_path(None) 
        return

    # Başarılı yükleme -> Mevcut sayfaları temizle ve yenilerini ekle
    page_manager.clear_all_pages()
    main_window.set_current_notebook_path(filepath)
    page_manager.mark_all_pages_as_saved()

    # --- Son açılanlar listesini güncelle (handle_load_notebook'taki mantıkla aynı) --- #
    recent_files = main_window.settings.get('recent_files', [])
    max_files = main_window.settings.get('max_recent_files', 5) # Ayarlardan oku
    if filepath in recent_files:
        recent_files.remove(filepath)
    recent_files.insert(0, filepath)
    main_window.settings['recent_files'] = recent_files[:max_files] # Ayarlardan okunan limiti kullan
    # --- DÜZELTME: Ayarları argüman olarak gönder --- #
    main_window._save_settings(main_window.settings) # Ayarları kaydet
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #
    if hasattr(main_window, '_update_recent_files_menu'):
        main_window._update_recent_files_menu()
    # --- --- --- --- --- --- --- --- --- --- ---

    if not loaded_data: # Dosya boşsa
        page_manager.add_page()
        logging.info("Yüklenen dosya boştu, yeni bir boş sayfa eklendi.")
    else:
        for page_content in loaded_data:
            new_page = page_manager.add_page(create_new=True)
            if not new_page:
                logging.error(f"Yeni sayfa yükleme sırasında oluşturulamadı.")
                continue
            canvas = new_page.get_canvas()
            canvas.lines = page_content.get('lines', [])
            canvas.shapes = page_content.get('shapes', [])

            # --- YENİ: Resim verisini Page nesnesine ata --- #
            loaded_images_data = page_content.get('images', [])
            if loaded_images_data:
                # Pixmap'ları None olarak başlatmamız gerekiyor.
                # _ensure_pixmaps_loaded daha sonra bunları yükleyecek.
                new_page.images = [] # Önce temizle
                for img_data_loaded in loaded_images_data:
                    # Gerekli alanları kontrol et (path, rect, angle, uuid)
                    if all(k in img_data_loaded for k in ('path', 'rect', 'angle', 'uuid')):
                        img_data_for_page = {
                            'uuid': img_data_loaded['uuid'],
                            'path': img_data_loaded['path'],
                            'rect': QRectF(*img_data_loaded['rect']) if isinstance(img_data_loaded['rect'], list) else img_data_loaded['rect'], # rect list ise QRectF yap
                            'angle': img_data_loaded['angle'],
                            'pixmap': None, # Başlangıçta pixmap None
                            'pixmap_item': None # Başlangıçta None
                        }
                        new_page.images.append(img_data_for_page)
                        logging.debug(f"Loaded image data for page {new_page.page_number}: uuid={img_data_for_page['uuid']}")
                    else:
                        logging.warning(f"Skipping loaded image data due to missing keys: {img_data_loaded}")
            else:
                 new_page.images = [] # Resim yoksa boş liste
            # --- --- --- --- --- --- --- --- --- --- --- -- #

            # YENİ: Sayfa yönünü yükle
            loaded_orientation_name = page_content.get('orientation', Orientation.PORTRAIT.name)
            try:
                loaded_orientation = Orientation[loaded_orientation_name]
            except KeyError:
                logging.warning(f"Geçersiz orientation değeri '{loaded_orientation_name}' bulundu, varsayılan (PORTRAIT) kullanılıyor.")
                loaded_orientation = Orientation.PORTRAIT
            # --- DÜZELTME: set_orientation yerine property kullan ---\
            new_page.orientation = loaded_orientation
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- #

            # YENİ: PDF'ten gelen özel arka planı yükle
            pdf_bg_path = page_content.get('pdf_background_source_path')
            if pdf_bg_path and os.path.exists(pdf_bg_path):
                logging.info(f"Sayfa {new_page.page_number} için PDF arka planı yükleniyor: {pdf_bg_path}")
                new_page.set_background_image(pdf_bg_path)
            elif pdf_bg_path:
                logging.warning(f"Sayfa {new_page.page_number} için kayıtlı PDF arka plan yolu ({pdf_bg_path}) bulunamadı.")

            # Sayfayı manager'a ekle -> add_page zaten ekledi
            # page_manager.add_page(page=new_page)

    QApplication.processEvents()
    # --- YENİ: Yükleme sonrası aktif canvas'ı güncelle (Resimlerin görünmesi için) ---\
    if page_manager.count() > 0:
        active_page_widget = page_manager.get_current_page() # DEĞİŞİKLİK: current_page_widget -> get_current_page
        if active_page_widget and hasattr(active_page_widget, 'get_canvas'):
            canvas = active_page_widget.get_canvas()
            if canvas:
                logging.debug("Son kullanılan dosya yükleme sonrası aktif canvas için update() çağrılıyor.")
                canvas.update()
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
    main_window.statusBar().showMessage(f"Dosya başarıyla yüklendi (Son Açılanlardan): {filepath}", 5000)
    if page_manager.count() > 0:
        page_manager.setCurrentIndex(0) 

    # Mevcut çizimi ve ayarları kaydet - BU BLOK HATALI VE GEREKSİZ
    # main_window.page_manager.save_to_file(filepath) # HATALI SATIR - YORUMA ALINDI
    # main_window.set_window_title(os.path.basename(filepath)) # Bu zaten set_current_notebook_path içinde yapılıyor
    # main_window.add_recent_file(filepath) # Bu zaten yukarıda yapılıyor
    # main_window.last_save_load_directory = os.path.dirname(filepath) # Bu zaten set_current_notebook_path içinde yapılıyor

    logging.info(f"Dosya başarıyla yüklendi (Son Açılanlardan): {filepath}")
    # Yükleme sonrası bilgilendirme mesajı göstermeye gerek yok, zaten açıldı.
    # QMessageBox.information(...)
    
# ... (Dosyanın geri kalanı)

    logging.info(f"Dosya başarıyla kaydedildi: {filepath}")
    QMessageBox.information(
        main_window,
        "Başarılı",
        f"Dosya başarıyla kaydedildi: {filepath}"
    ) 
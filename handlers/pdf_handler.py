# handlers/pdf_handler.py
import logging
import os # os modülü eklendi
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QStandardPaths, QPointF # Geçici dosya konumu için

from helpers import pdf_helper
import fitz # PyMuPDF'i doğrudan kullanacağız

# Geçici PDF sayfaları için bir alt klasör adı
TEMP_PDF_IMAGE_DIR = "temp_pdf_pages"

def _ensure_temp_dir_exists():
    """Geçici PDF resimlerinin saklanacağı dizinin var olduğundan emin olur."""
    # Kullanıcının uygulama veri dizininde bir yer bulmaya çalışalım
    app_data_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not app_data_path: # Eğer alamazsak, çalışma dizinine fallback yap
        app_data_path = "." 
    
    temp_dir = os.path.join(app_data_path, TEMP_PDF_IMAGE_DIR)
    
    if not os.path.exists(temp_dir):
        try:
            os.makedirs(temp_dir)
            logging.info(f"Geçici PDF resim klasörü oluşturuldu: {temp_dir}")
        except OSError as e:
            logging.error(f"Geçici PDF resim klasörü oluşturulamadı ({temp_dir}): {e}")
            # Klasör oluşturulamazsa, çalışma dizinini kullanmayı deneyebiliriz
            # veya hata verip işlemi durdurabiliriz. Şimdilik çalışma dizinine fallback.
            temp_dir = TEMP_PDF_IMAGE_DIR 
            if not os.path.exists(temp_dir):
                try:
                    os.makedirs(temp_dir)
                except OSError: # Hala olmuyorsa, null dönebiliriz ya da hata fırlatabiliriz.
                    logging.error(f"Çalışma dizininde de geçici klasör oluşturulamadı: {temp_dir}")
                    return None
    return temp_dir

def handle_import_pdf(parent_window=None, page_manager=None): # page_manager eklendi
    """
    Kullanıcının bir PDF dosyası seçmesini sağlar, dosyayı açar, sayfalarını
    resim olarak kaydeder ve PageManager'a ekler.

    Args:
        parent_window (QWidget, optional): QFileDialog için ebeveyn pencere.
        page_manager (PageManager, optional): Resimlerin ekleneceği PageManager nesnesi.
    """
    if not page_manager:
        logging.error("PageManager sağlanmadı, PDF içe aktarılamıyor.")
        if parent_window:
            QMessageBox.critical(parent_window, "Hata", "PageManager bulunamadı. PDF içe aktarma işlemi yapılamaz.")
        return

    filepath, _ = QFileDialog.getOpenFileName(
        parent_window,
        "PDF Dosyası Seçin",
        "",
        "PDF Dosyaları (*.pdf);;Tüm Dosyalar (*.*)"
    )

    if not filepath:
        logging.info("PDF içe aktarma işlemi kullanıcı tarafından iptal edildi.")
        return

    logging.info(f"Seçilen PDF dosyası: {filepath}")
    
    pdf_document = pdf_helper.import_pdf_document(filepath)

    if pdf_document:
        temp_image_folder = _ensure_temp_dir_exists()
        if not temp_image_folder:
            logging.error("Geçici resimler için klasör oluşturulamadı/erişilemedi. PDF içe aktarma iptal edildi.")
            if parent_window:
                QMessageBox.critical(parent_window, "Hata", "Geçici resimler için klasör hazırlanamadı.")
            pdf_document.close()
            return

        logging.info(f"PDF başarıyla açıldı: {filepath}, Sayfa Sayısı: {len(pdf_document)}")
        
        # PDF'den sayfa sayısını kontrol et
        if len(pdf_document) == 0:
            logging.warning("PDF dosyasında içe aktarılacak sayfa bulunamadı.")
            if parent_window:
                QMessageBox.warning(parent_window, "PDF İçe Aktarma", f"'{os.path.basename(filepath)}' dosyasında içe aktarılacak sayfa bulunamadı.")
            pdf_document.close()
            return
            
        # Mevcut sayfaları temizle - eğer hiç sayfa yoksa bu işlem atlanır
        if page_manager.count() > 0:
            page_manager.clear_all_pages()
        
        imported_page_count = 0
        first_page_index = 0  # İlk eklenen sayfanın indeksini sakla
        
        try:
            for i, page_fitz in enumerate(pdf_document):
                try:
                    # Sayfayı pixmap olarak al (DPI ayarı çözünürlüğü etkiler)
                    pix = page_fitz.get_pixmap(dpi=150) # DPI değeri 300'den 150'ye düşürüldü
                    
                    # Dosya adını oluştur (orijinal dosya adı + sayfa no)
                    base_pdf_name = os.path.splitext(os.path.basename(filepath))[0]
                    image_filename = f"{base_pdf_name}_page_{i+1}.png"
                    image_path = os.path.join(temp_image_folder, image_filename)
                    
                    pix.save(image_path)
                    logging.info(f"  Sayfa {i+1} şuraya kaydedildi: {image_path}")

                    # PageManager'a bu resmi yeni bir sayfa olarak ekle.
                    if hasattr(page_manager, 'add_page_from_image'):
                        newly_added_page = page_manager.add_page_from_image(image_path)
                        if newly_added_page:
                            if imported_page_count == 0:
                                first_page_index = page_manager.currentIndex()  # İlk sayfanın indeksini kaydet
                            
                            imported_page_count += 1
                            logging.info(f"PageManager'a eklendi: {image_path}")
                            
                            # --- YENİ: Zoom Seviyesini Ayarla ---
                            try:
                                # PDF'ten oluşturulan pixmap'in genişliği
                                pdf_pixmap_width = pix.width
                                
                                # Hedef canvas genişliğini al (Sayfanın mevcut canvas'ından)
                                # Bu, sayfanın yönelimine göre değişen şablon genişliği olmalı.
                                target_canvas = newly_added_page.get_canvas()
                                if target_canvas:
                                    # Canvas'ın o anki gerçek genişliğini veya sizeHint'ini kullanabiliriz.
                                    # Veya daha iyisi, canvas'ın kullandığı _background_pixmap (şablon) genişliğini.
                                    canvas_target_width = 0
                                    if target_canvas._background_pixmap and not target_canvas._background_pixmap.isNull():
                                        canvas_target_width = target_canvas._background_pixmap.width()
                                        logging.debug(f"  Hedef canvas şablon genişliği: {canvas_target_width}")
                                    elif target_canvas.width() > 0: # Fallback olarak canvas'ın o anki genişliği
                                        canvas_target_width = target_canvas.width()
                                        logging.debug(f"  Hedef canvas mevcut genişliği: {canvas_target_width}")
                                    else: # Varsayılan bir değere fallback
                                        canvas_target_width = 800 # Makul bir varsayılan
                                        logging.warning(f"  Hedef canvas genişliği alınamadı, varsayılan {canvas_target_width} kullanılıyor.")

                                    if pdf_pixmap_width > 0 and canvas_target_width > 0:
                                        required_zoom = canvas_target_width / pdf_pixmap_width
                                        # Çok fazla küçültmeyi veya büyütmeyi engellemek için sınır koyabiliriz
                                        required_zoom = max(0.1, min(required_zoom, 3.0)) 
                                        newly_added_page.set_zoom(required_zoom)
                                        newly_added_page.set_pan(QPointF(0,0)) # Pan'ı sıfırla
                                        logging.info(f"  Sayfa {newly_added_page.page_number} için otomatik zoom ayarlandı: {required_zoom:.2f} (PDF genişliği: {pdf_pixmap_width}, Hedef Genişlik: {canvas_target_width})")
                                else:
                                    logging.warning("  Otomatik zoom ayarlanamadı: PDF veya hedef genişlik sıfır.")
                            except Exception as e_zoom:
                                logging.error(f"  Sayfa için otomatik zoom ayarlanırken hata: {e_zoom}", exc_info=True)
                            # --- --- --- --- --- --- --- --- ---
                        else:
                            logging.error(f"PageManager.add_page_from_image çağrıldı ancak sayfa eklenemedi: {image_path}")
                    else:
                        logging.warning(f"PageManager'da `add_page_from_image` metodu bulunamadı. Sayfa {i+1} ({image_path}) eklenemedi.")
                    
                except Exception as e_page:
                    logging.error(f"PDF sayfası {i+1} işlenirken hata: {e_page}", exc_info=True)
                    if parent_window:
                        QMessageBox.warning(parent_window, "Sayfa Hatası", f"{os.path.basename(filepath)} dosyasının {i+1}. sayfası işlenirken bir sorun oluştu.")
            
            # PDF içe aktarma tamamlandığında ilk sayfaya git
            if imported_page_count > 0:
                page_manager.setCurrentIndex(first_page_index)  # İlk sayfaya dön
                logging.info(f"PDF içe aktarma tamamlandı. İlk sayfa gösteriliyor (index: {first_page_index})")
                
                # Başarılı içe aktarma mesajı
                if parent_window:
                    QMessageBox.information(parent_window, 
                                           "PDF İçe Aktarıldı", 
                                           f"'{os.path.basename(filepath)}' dosyasından {imported_page_count} sayfa başarıyla yeni sayfa olarak eklendi.")
            elif len(pdf_document) > 0 and imported_page_count == 0 : # Sayfa var ama eklenemedi
                if parent_window:
                    QMessageBox.warning(parent_window, 
                                            "PDF İçe Aktarma", 
                                            f"'{os.path.basename(filepath)}' dosyasındaki sayfalar okundu ancak uygulamaya eklenemedi (PageManager entegrasyonu bekleniyor).")
            else: # Hiç sayfa yoksa veya 0 sayfa işlendiyse
                if parent_window:
                    QMessageBox.information(parent_window, "PDF İçe Aktarma", f"'{os.path.basename(filepath)}' dosyasında işlenecek sayfa bulunamadı veya bir sorun oluştu.")

        finally:
            # Açılan belgeyi kapat
            pdf_document.close()
    else:
        logging.error(f"PDF dosyası ({filepath}) açılamadı veya yüklenemedi.")
        if parent_window:
            QMessageBox.critical(parent_window, 
                                 "Hata", 
                                 f"PDF dosyası ({filepath}) yüklenirken bir sorun oluştu.")

def handle_annotate_pdf(pdf_document, annotation_data):
    """
    Verilen PDF belgesine belirtilen işaretlemeyi ekler.

    Args:
        pdf_document: İşaretlenecek PDF belgesi (henüz formatı belirsiz).
        annotation_data: İşaretleme bilgileri (örneğin, sayfa, konum, metin, renk).
    """
    logging.info(f"PDF işaretleme isteği alındı. Belge: {pdf_document}, İşaretleme: {annotation_data}")
    # Burada pdf_helper.add_annotation_to_pdf(pdf_document, annotation_data) çağrılabilir.
    # Şimdilik sadece logluyoruz.
    print(f"PDF işaretleme mantığı eklenecek. Belge: {pdf_document}, İşaretleme: {annotation_data}")

if __name__ == '__main__':
    # Bu dosya doğrudan çalıştırıldığında test amaçlı kullanılabilir.
    # logging.basicConfig(level=logging.DEBUG)
    # handle_import_pdf() # Test için parent_window ve page_manager gerekebilir
    pass 
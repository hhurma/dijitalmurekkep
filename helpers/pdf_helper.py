import logging

# PDF işleme için PyMuPDF (fitz) veya reportlab gibi kütüphaneler kullanılabilir.
# Örnek olarak PyMuPDF (fitz) kullanalım. Kurulum: pip install PyMuPDF
import fitz  # PyMuPDF import edildi

def import_pdf_document(filepath: str):
    """
    Belirtilen yoldaki PDF dosyasını PyMuPDF (fitz) kullanarak açar.

    Args:
        filepath (str): PDF dosyasının yolu.

    Returns:
        fitz.Document | None: PyMuPDF belge nesnesi veya hata durumunda None.
    """
    try:
        doc = fitz.open(filepath)
        logging.info(f"PDF dosyası başarıyla açıldı: {filepath}, Sayfa Sayısı: {len(doc)}")
        return doc
    except Exception as e:
        logging.error(f"PDF dosyası ({filepath}) açılırken PyMuPDF hatası: {e}", exc_info=True)
        return None

def add_annotation_to_pdf(doc: fitz.Document, page_number: int, rect_coords: tuple, text: str, author: str = "AI Assistant", output_filepath: str | None = None) -> bool:
    """
    Verilen PyMuPDF belge nesnesinin belirtilen sayfasına bir metin notu (annotation) ekler.

    Args:
        doc (fitz.Document): Üzerinde çalışılacak PyMuPDF belge nesnesi.
        page_number (int): İşaretlemenin ekleneceği sayfa numarası (0 tabanlı).
        rect_coords (tuple): İşaretlemenin yerleştirileceği dikdörtgen koordinatları (x0, y0, x1, y1).
                         fitz.Rect nesnesi olarak da verilebilir.
        text (str): Eklenecek not metni.
        author (str): Notu ekleyenin adı.
        output_filepath (str, optional): Değişikliklerin kaydedileceği dosya yolu.
                                      None ise orijinal dosyanın üzerine yazılır (incremental save).

    Returns:
        bool: İşlem başarılıysa True, değilse False.
    """
    if not doc:
        logging.error("PDF'e işaretleme eklenemedi: Geçersiz belge nesnesi.")
        return False

    try:
        if not (0 <= page_number < len(doc)):
            logging.error(f"Geçersiz sayfa numarası: {page_number}. Belge sayfa sayısı: {len(doc)}")
            return False
        
        page = doc.load_page(page_number)
        
        # rect_coords tuple ise fitz.Rect'e çevir
        if isinstance(rect_coords, tuple):
            rect = fitz.Rect(rect_coords)
        elif isinstance(rect_coords, fitz.Rect):
            rect = rect_coords
        else:
            logging.error("Geçersiz rect_coords tipi. tuple veya fitz.Rect olmalı.")
            return False

        # Metin notu ekle (Text annotation)
        # page.add_freetext_annot(rect, text, fontsize=11, fontname="helv", text_color=0, fill_color=1, rotate=0)
        # Daha basit bir Text (sticky note benzeri) annotation için:
        annot = page.add_text_annot(rect.tl, text, author=author) # rect.tl sol üst köşe
        # İsteğe bağlı: İşaretlemenin görünümünü ayarla
        annot.set_colors(stroke=(0, 0, 1), fill=(0.7, 0.7, 1)) # Mavi tonları örnek
        annot.update(opacity=0.7)

        # Değişiklikleri kaydet
        if output_filepath:
            doc.save(output_filepath)
            logging.info(f"İşaretlenmiş PDF yeni dosyaya kaydedildi: {output_filepath}")
        else:
            # Orijinal dosyanın üzerine artımlı olarak kaydet
            doc.save(doc.name, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            logging.info(f"PDF belgesine ({doc.name}, Sayfa: {page_number}) işaretleme eklendi ve kaydedildi.")
        
        return True
    except Exception as e:
        logging.error(f"PDF'e işaretleme eklenirken PyMuPDF hatası: {e}", exc_info=True)
        return False

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # ----- import_pdf_document Testi -----
    # Lütfen buraya test etmek istediğiniz bir PDF dosyasının yolunu girin.
    # Örneğin: sample_pdf_path = "C:/Users/kullanici/Desktop/ornek.pdf"
    sample_pdf_path = "test.pdf" # Geçerli bir PDF dosyası olduğundan emin olun.

    # Basit bir test PDF dosyası oluştur (eğer test.pdf yoksa)
    if not fitz.utils.check_file_readable(sample_pdf_path):
        try:
            temp_doc = fitz.open() # Boş döküman
            page = temp_doc.new_page()
            page.insert_text((50, 72), "Bu bir test PDF sayfasıdır.")
            temp_doc.save(sample_pdf_path)
            logging.info(f"'{sample_pdf_path}' adında basit bir test PDF'i oluşturuldu.")
            temp_doc.close()
        except Exception as e:
            logging.error(f"Test PDF'i oluşturulurken hata: {e}")

    if fitz.utils.check_file_readable(sample_pdf_path):
        logging.info(f"'{sample_pdf_path}' test ediliyor...")
        document = import_pdf_document(sample_pdf_path)

        if document:
            logging.info(f"Test PDF'i başarıyla yüklendi: {document.name}, {len(document)} sayfa.")
            
            # ----- add_annotation_to_pdf Testi -----
            # İlk sayfaya bir işaretleme ekleyelim
            page_to_annotate = 0
            # Koordinatlar: (sol_x, ust_y, sag_x, alt_y)
            # Sayfanın sol üstüne yakın bir yere not ekleyelim.
            # PyMuPDF koordinatları genellikle sol üstten başlar (0,0).
            annotation_rect = (50, 50, 200, 100) 
            annotation_text = "Bu PyMuPDF ile eklenmiş bir test notudur!"
            
            # Değişikliklerin kaydedileceği yeni dosya adı
            annotated_pdf_path = "test_annotated.pdf"

            success = add_annotation_to_pdf(document, 
                                            page_to_annotate, 
                                            annotation_rect, 
                                            annotation_text, 
                                            author="Test Kullanıcısı",
                                            output_filepath=annotated_pdf_path)
            if success:
                logging.info(f"İşaretleme testi başarılı. Sonuç: {annotated_pdf_path}")
            else:
                logging.error("İşaretleme testi başarısız.")
            
            # Belgeyi kapatmayı unutmayın
            document.close()
        else:
            logging.error(f"Test PDF'i ('{sample_pdf_path}') yüklenemedi.")
    else:
        logging.warning(f"Test PDF dosyası '{sample_pdf_path}' bulunamadı veya okunamıyor. Lütfen geçerli bir dosya yolu sağlayın.") 
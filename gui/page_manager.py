from PyQt6.QtWidgets import QStackedWidget, QWidget, QMessageBox, QApplication, QTabWidget, QMainWindow, QScrollArea
from PyQt6.QtCore import pyqtSignal, pyqtSlot
import logging

from .page import Page # Page sınıfını import et

class PageManager(QTabWidget):
    """Birden fazla not sayfasını (Page) yönetir."""

    # Sinyaller
    current_page_changed = pyqtSignal(Page) # Aktif sayfa değiştiğinde Page nesnesini gönderir
    page_count_changed = pyqtSignal(int, int) # Sayfa sayısı değiştiğinde (yeni_sayfa_sayısı, aktif_indeks)

    def __init__(self, parent=None, template_settings: dict | None = None):
        super().__init__(parent)
        self.pages: list[Page] = []
        self.template_settings = template_settings if template_settings is not None else {} # Ayarları sakla
        # --- YENİ: MainWindow referansını sakla --- #
        self.main_window = parent # PageManager'ın parent'ı MainWindow olmalı
        if not isinstance(self.main_window, QMainWindow):
            # Bu durum beklenmiyor, ama bir uyarı verelim
            logging.warning("PageManager başlatılırken parent MainWindow değil!")
            self.main_window = None # Referansı sıfırla
        # --- --- --- --- --- --- --- --- --- --- --- #
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.remove_page)
        self.currentChanged.connect(self._on_current_changed)
        logging.info("PageManager başlatıldı.")

    def page_count(self) -> int:
        """Toplam sayfa sayısını döndürür."""
        # return len(self.pages) # veya QStackedWidget'in count'u
        return self.count()

    def current_index(self) -> int:
        """Aktif sayfanın indeksini döndürür."""
        return self.currentIndex()

    def get_current_page(self) -> Page | None:
        """Aktif sayfayı (Page nesnesi) döndürür."""
        # --- DEĞİŞİKLİK: ScrollArea'dan widget'ı al --- #
        scroll_area = self.currentWidget()
        if isinstance(scroll_area, QScrollArea):
            page_widget = scroll_area.widget()
            if isinstance(page_widget, Page):
                return page_widget
        # --- --- --- --- --- --- --- --- --- --- --- -- #
        return None

    def add_page(self, page: Page | None = None, create_new: bool = True):
        """Yeni bir sayfa ekler veya var olanı ekler.
           create_new=True ise yeni boş bir Page oluşturulur.
           Aksi takdirde verilen page nesnesi kullanılır.
        """
        new_page = None # Başa alalım
        if create_new:
            new_page_number = self.count() + 1 # Mevcut tab sayısına göre
            # --- YENİ: Ayarlardan varsayılan sayfa yönünü al --- #
            default_orientation = "portrait" # Varsayılan
            if self.main_window and hasattr(self.main_window, 'settings'):
                template_settings_from_main = self.main_window.settings.get('template_settings', {})
                default_orientation = template_settings_from_main.get('default_page_orientation', "portrait")
                logging.debug(f"Yeni sayfa için varsayılan yön ayarlandı: {default_orientation}")
            else:
                logging.warning("PageManager: MainWindow veya settings alınamadı, varsayılan sayfa yönü 'portrait' kullanılacak.")
            # --- --- --- --- --- --- --- --- --- --- --- --- -- #
            
            new_page = Page(page_number=new_page_number, 
                            template_settings=self.template_settings, 
                            main_window=self.main_window,
                            default_orientation_str=default_orientation) # YENİ: Yön parametresi
            logging.debug(f"Yeni sayfa oluşturuldu: {new_page_number} (Yön: {default_orientation}, Ayarlarla)")
        elif page:
            new_page = page # Verilen sayfayı kullan
            new_page_number = page.page_number # Sayfa numarasını al
            logging.debug(f"Varolan sayfa eklendi: {new_page_number}")
        else:
             logging.error("add_page: Ne yeni sayfa oluşturulacak ne de var olan sayfa verildi.")
             return None

        # --- YENİ: Sayfayı ScrollArea içine koy --- #
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True) # İçerik boyutuna uyum sağla
        scroll_area.setWidget(new_page)      # Page'i scroll area'nın widget'ı yap
        # --- --- --- --- --- --- --- --- --- --- -- #

        # YENİ: Event Filter Kurulumu (DrawingCanvas için)
        if hasattr(new_page, 'drawing_canvas') and new_page.drawing_canvas:
            scroll_area.viewport().installEventFilter(new_page.drawing_canvas)
            logging.debug(f"Event filter installed on ScrollArea viewport for Page {new_page_number}")
        else:
            logging.warning(f"Event filter KURULAMADI: Page {new_page_number} için drawing_canvas bulunamadı.")

        # Sekme başlığını oluştur
        tab_title = f"Sayfa {new_page_number}"

        # Sekmeyi ekle (ScrollArea'yı ekle)
        index = self.addTab(scroll_area, tab_title)
        self.setCurrentIndex(index) # Yeni eklenen sekmeyi aktif yap

        self.page_count_changed.emit(self.count(), self.currentIndex())
        logging.info(f"Sayfa eklendi. Toplam sayfa: {self.count()}")
        return new_page # Eklenen Page nesnesini döndür

    def remove_page(self, index: int):
        """Belirtilen indeksteki sayfayı siler."""
        if not (0 <= index < self.page_count()):
            logging.warning(f"Geçersiz sayfa indeksi silinemedi: {index}")
            return

        if self.page_count() <= 1:
            logging.warning("Son sayfa silinemez.")
            return

        # --- DEĞİŞİKLİK: ScrollArea'yı al ve içindeki Page'e eriş --- #
        scroll_area_to_remove = self.widget(index)
        if isinstance(scroll_area_to_remove, QScrollArea):
            page_to_remove = scroll_area_to_remove.widget()
            if isinstance(page_to_remove, Page):
                page_number = page_to_remove.page_number
                self.removeTab(index) # Sekmeyi (ScrollArea içeren) kaldır
                # Page widget'ının bellekten silinmesini planla
                page_to_remove.deleteLater()
                # ScrollArea'nın da silinmesini planlayabiliriz, QTabWidget otomatik yapmıyorsa
                scroll_area_to_remove.deleteLater()
                # self.pages listesini kullanmıyoruz artık
                # if page_to_remove in self.pages:
                #      self.pages.remove(page_to_remove)

                logging.info(f"Sayfa {page_number} (Indeks: {index}) silindi.")
                self.page_count_changed.emit(self.page_count(), self.current_index())
            else:
                logging.error(f"Silinmeye çalışılan ScrollArea içindeki widget bir Page değil: Indeks {index}")
                self.removeTab(index) # Sorunlu sekmeyi yine de kaldır
                scroll_area_to_remove.deleteLater()
        else:
            logging.error(f"Silinmeye çalışılan widget bir QScrollArea değil: Indeks {index}")
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    def remove_current_page(self):
        """Aktif olan sayfayı siler."""
        self.remove_page(self.current_index())

    def go_to_next_page(self):
        """Bir sonraki sayfaya geçer."""
        next_index = (self.current_index() + 1) % self.page_count()
        self.setCurrentIndex(next_index)

    def go_to_previous_page(self):
        """Bir önceki sayfaya geçer."""
        prev_index = (self.current_index() - 1 + self.page_count()) % self.page_count()
        self.setCurrentIndex(prev_index)

    def clear_all_pages(self):
        """Tüm not sayfalarını widget'tan ve listeden kaldırır."""
        logging.info("Tüm sayfalar temizleniyor...")
        for i in range(self.count() - 1, -1, -1):
            # --- DEĞİŞİKLİK: ScrollArea ve içindeki Page'i sil --- #
            scroll_area = self.widget(i)
            self.removeTab(i)
            if isinstance(scroll_area, QScrollArea):
                page_widget = scroll_area.widget()
                if isinstance(page_widget, Page):
                    page_widget.deleteLater()
                scroll_area.deleteLater() # ScrollArea'yı da sil
            else:
                 logging.warning(f"clear_all_pages: QScrollArea olmayan bir widget bulundu ve kaldırıldı: {scroll_area}")
            # --- --- --- --- --- --- --- --- --- --- --- --- --- #
                
        logging.info(f"Tüm sayfalar temizlendi. Kalan sayfa: {self.count()}")
        self.page_count_changed.emit(0, -1)

    def has_unsaved_changes(self) -> bool:
        """Yönetilen sayfalardan herhangi birinde kaydedilmemiş değişiklik olup olmadığını kontrol eder."""
        for i in range(self.count()):
            # --- DEĞİŞİKLİK: ScrollArea içindeki Page'i kontrol et --- #
            scroll_area = self.widget(i)
            if isinstance(scroll_area, QScrollArea):
                page_widget = scroll_area.widget()
                if isinstance(page_widget, Page) and page_widget.is_modified:
                    return True
            # --- --- --- --- --- --- --- --- --- --- --- --- --- -- #
        return False

    def mark_all_pages_as_saved(self):
        """Yönetilen tüm sayfaları 'kaydedildi' olarak işaretler."""
        logging.debug("Tüm sayfalar kaydedildi olarak işaretleniyor...")
        for i in range(self.count()):
            # --- DEĞİŞİKLİK: ScrollArea içindeki Page'i işaretle --- #
            scroll_area = self.widget(i)
            if isinstance(scroll_area, QScrollArea):
                page_widget = scroll_area.widget()
                if isinstance(page_widget, Page):
                    page_widget.mark_as_saved()
            # --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    @pyqtSlot(int)
    def _on_current_changed(self, index: int):
        """QTabWidget'in currentChanged sinyaline bağlı slot."""
        # --- DEĞİŞİKLİK: ScrollArea içindeki Page'i al ve sinyali gönder --- #
        scroll_area = self.widget(index)
        if isinstance(scroll_area, QScrollArea):
            current_page = scroll_area.widget()
            if isinstance(current_page, Page):
                logging.debug(f"Aktif sayfa değişti: Indeks {index}, Sayfa No {current_page.page_number}")
                self.current_page_changed.emit(current_page)
            else:
                 logging.warning(f"Aktif widget bir QScrollArea ama içindeki Page değil: Indeks {index}")
        elif scroll_area is not None: # Eğer None değilse ama ScrollArea da değilse, bu bir sorun
            logging.error(f"Aktif widget bir QScrollArea değil: Indeks {index}, Tip: {type(scroll_area)}")
        # index == -1 durumu (hiç tab kalmayınca) olabilir, bu durumda current_page None olur.
        # current_page_changed(None) sinyali göndermeli miyiz? MainWindow bunu handle etmeli.
        # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- # 

    def add_page_from_image(self, image_path: str):
        """Verilen yoldaki resmi arka plan olarak kullanan yeni bir sayfa ekler."""
        # Yeni sayfa numarası, mevcut sayfa sayısına göre belirlenir
        new_page_number = self.count() + 1
        default_orientation = "portrait" # Varsayılan, ayarlanabilir
        if self.main_window and hasattr(self.main_window, 'settings'):
            template_settings_from_main = self.main_window.settings.get('template_settings', {})
            default_orientation = template_settings_from_main.get('default_page_orientation', "portrait")
        
        # Yeni sayfa oluştur
        new_page = Page(page_number=new_page_number,
                        template_settings=self.template_settings,
                        main_window=self.main_window,
                        default_orientation_str=default_orientation)
        
        # Arka plan resmini ayarla
        success = False
        if hasattr(new_page, 'set_background_image'):
            success = new_page.set_background_image(image_path)
            logging.info(f"Sayfa {new_page_number} için arka plan resmi ayarlandı: {image_path}")
        elif hasattr(new_page.get_canvas(), 'set_background_image'):
            success = new_page.get_canvas().set_background_image(image_path)
            logging.info(f"Sayfa {new_page_number} canvas'ı için arka plan resmi ayarlandı: {image_path}")
        else:
            logging.warning(f"Page veya Canvas üzerinde `set_background_image` metodu bulunamadı. Arka plan ayarlanamadı: {image_path}")
            # Arka plan ayarlanamazsa bile sayfayı ekleyebiliriz veya hata verebiliriz.
            # Şimdilik devam edelim.
        
        # Sayfayı ScrollArea içine yerleştirip ekle
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(new_page)

        # Event Filter Kurulumu (DrawingCanvas için)
        if hasattr(new_page, 'drawing_canvas') and new_page.drawing_canvas:
            scroll_area.viewport().installEventFilter(new_page.drawing_canvas)
            logging.debug(f"Event filter (from image) installed on ScrollArea viewport for Page {new_page_number}")
        else:
            logging.warning(f"Event filter (from image) KURULAMADI: Page {new_page_number} için drawing_canvas bulunamadı.")

        # Sayfa başlığını ayarla ve sekmeyi ekle
        tab_title = f"Sayfa {new_page_number}"
        index = self.addTab(scroll_area, tab_title)
        self.setCurrentIndex(index)  # Yeni eklenen sayfayı aktif yap
        
        # Sayfa sayısı değişikliği bildirimi
        self.page_count_changed.emit(self.count(), index)
        logging.info(f"Resimli sayfa eklendi: {new_page_number} (Indeks: {index})")
        
        return new_page

    # --- YENİ: Tüm Canvas'lara Grid Ayarlarını Uygula ---
    def apply_grid_settings_to_all_canvases(self, settings_dict: dict):
        """Tüm sayfalardaki DrawingCanvas nesnelerine verilen grid ayarlarını uygular."""
        logging.debug(f"apply_grid_settings_to_all_canvases çağrıldı: {settings_dict}")
        for i in range(self.count()):
            scroll_area = self.widget(i)
            if isinstance(scroll_area, QScrollArea):
                page_widget = scroll_area.widget()
                if isinstance(page_widget, Page) and hasattr(page_widget, 'drawing_canvas') and page_widget.drawing_canvas:
                    if hasattr(page_widget.drawing_canvas, 'apply_grid_settings'):
                        page_widget.drawing_canvas.apply_grid_settings(settings_dict)
                        # logging.debug(f"  Ayarlar Sayfa {page_widget.page_number} canvas'ına uygulandı.")
                    else:
                        logging.warning(f"  Sayfa {page_widget.page_number} canvas'ında 'apply_grid_settings' metodu bulunamadı.")
                # else:
                #     logging.debug(f"  Sekme {i} bir Page veya drawing_canvas içermiyor.")
            # else:
            #     logging.debug(f"  Sekme {i} bir QScrollArea değil.")
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
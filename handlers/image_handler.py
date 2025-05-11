import logging
import os
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import QRectF, QPointF, QSize, QSizeF, Qt
import uuid
from utils.commands import AddImageCommand

# Gerekli tipler için
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from gui.arayuz import MainWindow
    from gui.page_manager import PageManager
    from gui.page import Page
    
def handle_add_image(main_window: 'MainWindow', page_manager: 'PageManager'):
    '''Kullanıcının bir resim seçip aktif sayfaya eklemesini sağlar.
       Büyük resimleri otomatik olarak ölçeklendirir.
    '''
    current_page: 'Page' | None = page_manager.get_current_page()
    if not current_page:
        logging.warning("Resim eklenecek aktif sayfa bulunamadı.")
        return

    canvas = current_page.get_canvas() # Canvas'ı al
    if not canvas:
        logging.error("Resim eklenecek canvas bulunamadı.")
        return

    # Dosya seçme diyalogu
    # Desteklenen formatları belirtelim
    supported_formats = " *.png *.jpg *.jpeg *.bmp *.gif *.svg"
    filepath, _ = QFileDialog.getOpenFileName(
        main_window, 
        "Resim Dosyası Seçin", 
        "", # Başlangıç dizini (boş bırakılabilir)
        f"Resim Dosyaları ({supported_formats});;Tüm Dosyalar (*)"
    )

    if not filepath:
        logging.debug("Kullanıcı resim seçimi iptal etti.")
        return

    # Resmi QPixmap olarak yüklemeyi dene
    pixmap = QPixmap(filepath)
    if pixmap.isNull():
        logging.error(f"Resim dosyası yüklenemedi veya geçersiz: {filepath}")
        # Kullanıcıya hata mesajı gösterilebilir
        # QMessageBox.critical(main_window, "Hata", f"Resim dosyası yüklenemedi: {os.path.basename(filepath)}")
        return

    img_size = pixmap.size()
    img_width = img_size.width()
    img_height = img_size.height()
    
    # Canvas boyutuna göre hedef boyutları belirle (ekran pikseli)
    view_width = canvas.width() 
    view_height = canvas.height()
    max_target_width_view = view_width * 0.8 
    max_target_height_view = view_height * 0.8 

    scale = 1.0
    if img_width > max_target_width_view or img_height > max_target_height_view:
        scale_w = max_target_width_view / img_width if img_width > 0 else 1.0
        scale_h = max_target_height_view / img_height if img_height > 0 else 1.0
        scale = min(scale_w, scale_h)
        # logging.debug(...) # KALDIRILDI

    # --- YENİ: Hedef dünya boyutlarını hesapla --- 
    target_world_width = img_width * scale / current_page.zoom_level # Zoom'u hesaba kat
    target_world_height = img_height * scale / current_page.zoom_level # Zoom'u hesaba kat
    target_world_size = QSizeF(target_world_width, target_world_height)
    
    # Pixmap'i ölçeklendirirken ekran boyutlarını kullanabiliriz (görsel kalite için)
    target_pixmap_width = int(img_width * scale)
    target_pixmap_height = int(img_height * scale)
    scaled_pixmap = pixmap.scaled(target_pixmap_width, target_pixmap_height, 
                                  Qt.AspectRatioMode.KeepAspectRatio, 
                                  Qt.TransformationMode.SmoothTransformation)
    if scaled_pixmap.isNull():
        logging.error(f"Resim ölçeklendirme başarısız: {filepath}")
        return
    # --- --- --- --- --- --- --- -- #
    
    # --- YENİ: Başlangıç konumunu görünür alanın merkezine ayarla --- # DEĞİŞTİRİLDİ!
    # Görünür alanın ekran koordinatlarındaki merkezi
    # view_center_screen = QPointF(view_width / 2.0, view_height / 2.0)
    # Dünya koordinatlarına çevir
    # view_center_world = canvas.screen_to_world(view_center_screen)
    
    # Resmin sol üst köşesini hesapla (merkez view_center_world olacak şekilde)
    # initial_pos_world = QPointF(
    #     view_center_world.x() - target_world_width / 2.0,
    #     view_center_world.y() - target_world_height / 2.0
    # )
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- #
    
    # --- TEST: Başlangıç pozisyonunu (0,0) yapalım --- #
    initial_pos_world = QPointF(0, 0) 
    # --- --- --- --- --- --- --- --- --- --- --- --- -- #

    # --- DÜZELTME: Dünya koordinatları ve boyutunu kullan --- #
    initial_rect_world = QRectF(initial_pos_world, target_world_size)
    # --- --- --- --- --- --- --- --- --- --- --- --- --- --- -- #

    # --- YENİ LOG: Oluşturulan rect'i logla ---
    logging.debug(f"handle_add_image: Calculated initial_rect_world: {initial_rect_world}")
    # --- --- --- --- --- --- --- --- --- --- -- #

    image_id = str(uuid.uuid4())
    image_data = {
        'uuid': image_id,
        'path': filepath, 
        'pixmap': scaled_pixmap, # Ölçeklenmiş pixmap (gösterim için)
        'rect': initial_rect_world, # DÜNYA KOORDİNATLARI (Artık 0,0'dan başlıyor)
        'angle': 0.0
    }

    try:
        command = AddImageCommand(current_page, image_data)
        page_undo_manager = current_page.get_undo_manager()
        if page_undo_manager:
            page_undo_manager.execute(command)
            logging.info(f"AddImageCommand oluşturuldu ve {current_page.page_number}. sayfanın yöneticisi ile yürütüldü: {filepath} (UUID: {image_id})")
        else:
            logging.error(f"AddImageCommand: {current_page.page_number}. sayfanın undo manager'ı alınamadı!")
    except Exception as e:
        logging.error(f"AddImageCommand oluşturulurken/çalıştırılırken hata: {e}", exc_info=True)

def handle_image_click(main_window: 'MainWindow', page_manager: 'PageManager', world_pos: QPointF):
    """Verilen dünya koordinatındaki tıklamaya göre resim seçimini yönetir.
       Şimdilik sadece tekli seçimi destekler.
    """
    logging.debug(f"--- handle_image_click CALLED with world_pos: {world_pos} ---") # YENİ LOG
    current_page: 'Page' | None = page_manager.get_current_page()
    if not current_page:
        logging.warning("handle_image_click: Aktif sayfa bulunamadı.")
        return

    canvas = current_page.get_canvas()
    if not canvas:
        logging.error("handle_image_click: Aktif canvas bulunamadı.")
        return
        
    clicked_image_index = -1
    # Sayfadaki resimleri kontrol et (varsa)
    if hasattr(current_page, 'images') and current_page.images:
        logging.debug(f"handle_image_click: Checking {len(current_page.images)} image(s) on the current page.") # YENİ LOG
        # Sondan başa doğru kontrol et, üstteki resim öncelikli olsun
        for i in range(len(current_page.images) - 1, -1, -1):
            img_data = current_page.images[i]
            
            if 'rect' not in img_data or not isinstance(img_data['rect'], QRectF) or \
               'angle' not in img_data or 'pixmap' not in img_data: # pixmap de gerekli
                logging.warning(f"handle_image_click: images[{i}] içinde gerekli 'rect', 'angle' veya 'pixmap' bulunamadı.")
                continue

            world_rect = img_data['rect'] # Resmin dünya koordinatlarındaki QRectF'i
            angle = img_data['angle']     # Resmin açısı
            
            # Resmin kendi merkezi etrafında döndüğünü varsayıyoruz.
            # QGraphicsPixmapItem.transformOriginPoint() genellikle pixmap'in merkezidir.
            # Burada da pixmap'in merkezini kullanacağız.
            # ÖNEMLİ: img_data['pixmap'] ölçeklenmiş pixmap. 
            # Dönüşüm merkezi, bu ölçeklenmiş pixmap'in yerel merkezidir.
            # Ancak dünya koordinatlarına çevrilmiş tıklama ile karşılaştıracağımız için,
            # dünya koordinatlarındaki rect'in merkezini kullanalım.
            center_world = world_rect.center()

            # Tıklanan dünya noktasını (world_pos) resmin yerel koordinatlarına dönüştür
            transform = QTransform()
            transform.translate(center_world.x(), center_world.y()) # 3. Dönüşüm merkezine geri taşı
            transform.rotate(angle)                                  # 2. Döndür
            transform.translate(-center_world.x(), -center_world.y())# 1. Dönüşüm merkezini orijine taşı
            
            # İnverse transformu al ve dünya noktasını map et
            inverted_transform, invertible = transform.inverted()

            if not invertible:
                logging.warning(f"handle_image_click: Resim {i} için dönüşüm ters çevrilemedi.")
                continue
            
            local_click_pos = inverted_transform.map(world_pos)

            # Şimdi local_click_pos'un, resmin DÖNDÜRÜLMEMİŞ sınırlayıcı kutusu içinde olup olmadığını kontrol et.
            # Bu sınırlayıcı kutu, dünya koordinatlarındaki world_rect ile aynı konumda olmalı.
            # Dolayısıyla, local_click_pos'u doğrudan world_rect ile karşılaştırabiliriz.
            # Alternatif olarak, local_click_pos'un (0,0) merkezli ve world_rect.size() boyutlu bir
            # yerel kutuda olup olmadığını kontrol edebiliriz, EĞER dönüşümümüz noktayı
            # resmin sol-üst köşesi (0,0) olacak şekilde bir yerel sisteme taşıyorsa.
            # Mevcut transformasyon, noktayı dünya merkezli dönen bir sisteme taşıyor.
            # Bu nedenle, dönüştürülmüş noktanın HALA world_rect içinde olup olmadığını kontrol etmek doğru.

            # Basit bir kontrol: world_rect, resmin döndürülmemiş sınırlayıcı kutusudur.
            # Eğer tıklama bu kutunun içindeyse VE dönüşüm sonrası yerel kontrol de geçerliyse seç.
            # Daha doğru bir yöntem: Tıklama noktasını, resmin kendi yerel koordinatlarına (sol üstü 0,0 olan)
            # dönüştürüp, sonra bu yerel noktanın resmin orijinal boyutları içinde olup olmadığını kontrol etmek.

            # Yeni Yaklaşım:
            # 1. Tıklama noktasını resmin döndürülmüş çerçevesinin içine almak için QTransform oluştur.
            #    Bu transform, dünya koordinatlarından, resmin sol üst köşesi (0,0) ve orijinal
            #    boyutlarında olduğu bir yerel sisteme haritalama yapmalı.
            
            # Resmin QGraphicsPixmapItem'daki gibi bir dönüşüm orijin noktası olmalı.
            # Genellikle bu, pixmap'in yerel merkezidir: QPointF(pixmap.width()/2, pixmap.height()/2)
            # `image_data` içinde `pixmap` anahtarı ölçeklenmiş QPixmap'ı tutuyor.
            # `rect` ise dünya koordinatlarındaki QRectF'i.
            
            pixmap = img_data.get('pixmap') # Bu ölçeklenmiş pixmap
            if not pixmap or pixmap.isNull():
                logging.warning(f"handle_image_click: Resim {i} için pixmap bulunamadı veya geçersiz.")
                continue

            # Dönüşüm için kullanılacak yerel orijin (pixmap'in merkezi)
            local_origin = QPointF(pixmap.width() / 2.0, pixmap.height() / 2.0)
            
            # Tıklanan dünya noktasını (world_pos) resmin yerel koordinatlarına dönüştürmek için:
            # 1. Resmin pozisyonunu (world_rect.topLeft()) çıkar (orijine taşımak için).
            # 2. Sonra, resmin yerel orijini etrafında ters açıyla döndür.
            
            transform_to_local = QTransform()
            # Adım 1: Önce resmin sol üst köşesini (world_rect.topLeft()) dünyanın orijinine taşı.
            transform_to_local.translate(-world_rect.topLeft().x(), -world_rect.topLeft().y())
            
            # Adım 2: Şimdi bu ötelenmiş sistemi, resmin yerel orijini (local_origin) etrafında
            #          ters açı (-angle) ile döndür.
            #          Döndürmeden önce local_origin'e translate et, döndür, sonra ters translate et.
            temp_transform = QTransform()
            temp_transform.translate(local_origin.x(), local_origin.y())
            temp_transform.rotate(-angle) # Ters açı
            temp_transform.translate(-local_origin.x(), -local_origin.y())
            
            # İki dönüşümü birleştir. world_pos'a önce translate, sonra rotate uygulanacak.
            final_transform_to_local = temp_transform * transform_to_local
            
            local_point = final_transform_to_local.map(world_pos)
            
            # Yerel sınırlayıcı kutu (sol üst 0,0, boyutlar pixmap'in boyutları)
            local_bounding_rect = QRectF(QPointF(0,0), QSizeF(pixmap.size()))

            if local_bounding_rect.contains(local_point):
                clicked_image_index = i
                logging.debug(f"Resim tıklandı (yeni yöntem): index={i}, uuid={img_data.get('uuid')}, local_point={local_point}, world_pos={world_pos}")
                break
            # Eski yöntem:
            # if img_data['rect'].contains(world_pos):
            #     clicked_image_index = i
            #     logging.debug(f"Resim tıklandı: index={i}, uuid={img_data.get('uuid')}")
            #     break # İlk bulunan (en üstteki) yeterli
            else:
                # logging.debug(f"Resim {i} tıklanmadı. local_point={local_point} vs local_bbox={local_bounding_rect}, world_pos={world_pos} vs world_rect={world_rect}")
                pass
        #else bloğu gereksiz, döngü dışına çıktı
            # logging.warning(f"handle_image_click: images[{i}] içinde geçerli 'rect' bulunamadı.") # Bu else artık geçerli değil

    # Seçimi güncelle
    new_selection = []
    if clicked_image_index != -1:
        # TODO: Shift ile çoklu seçim eklenecek
        new_selection = [('images', clicked_image_index)] # Sadece tıklanan resmi seç
        logging.debug(f"Yeni seçim ayarlandı: {new_selection}")
    else:
        logging.debug("Boş alana tıklandı, seçim temizlendi.")
        # Boş alana tıklandıysa seçimi temizle
        pass # new_selection zaten boş liste

    # Canvas'ın seçim listesini güncelle (doğrudan erişim yerine bir metod daha iyi olabilir)
    # Şimdilik doğrudan erişelim
    if hasattr(canvas, 'selected_item_indices'):
        # Sadece farklıysa güncelle ve ekranı yenile
        if canvas.selected_item_indices != new_selection:
            canvas.selected_item_indices = new_selection
            canvas.update() # Seçim çerçevesini göstermek/gizlemek için güncelle
        else:
            logging.debug("Seçim değişmedi, canvas güncellenmiyor.")
    else:
        logging.error("handle_image_click: Canvas'ta 'selected_item_indices' bulunamadı.")

# Gelecekte eklenecek fonksiyonlar:
# def handle_select_image(...) # Belki handle_image_click yeterli?
# def handle_move_image(...) 
# def handle_resize_image(...)
# def handle_delete_image(...) 
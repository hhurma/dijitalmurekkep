"""
Tablet basma olayını yönetmek için yardımcı fonksiyon.
"""
import logging
from typing import TYPE_CHECKING
import copy # Moved import
import math

from PyQt6.QtGui import QTabletEvent, QTransform, QPixmap, QVector2D, QPolygonF
from PyQt6.QtCore import Qt, QPointF, QRectF, QSizeF
from PyQt6.QtWidgets import QApplication, QGraphicsPixmapItem

from utils import selection_helpers
from gui.enums import ToolType
from utils.commands import MoveItemsCommand, ResizeItemsCommand, RotateItemsCommand # Moved import
from .tool_handlers import pen_tool_handler # YENİ: Pen tool handler importu
from .tool_handlers import shape_tool_handler # YENİ: Shape tool handler importu
from .tool_handlers import selector_tool_handler # YENİ: Selector tool handler importu
from .tool_handlers import eraser_tool_handler # YENİ: Eraser tool handler importu
from .tool_handlers import temporary_pointer_tool_handler # YENİ: Temporary Pointer tool handler importu
from utils.selection_helpers import adjust_corner_for_aspect_ratio

if TYPE_CHECKING:
    from .drawing_canvas import DrawingCanvas # Dairesel bağımlılığı önlemek için
    # from .page import Page # Page şu an doğrudan kullanılmıyor gibi, canvas._parent_page üzerinden erişiliyor

# --- TÜM RESİM SEÇME, TAŞIMA, DÖNDÜRME, BOYUTLANDIRMA KODLARI SİLİNDİ --- #
# (handle_tablet_press, handle_tablet_move, handle_tablet_release ve ilgili yardımcı fonksiyonlar kaldırıldı)
# ... diğer araç handler'ları ve yardımcı fonksiyonlar kalabilir ...

def handle_canvas_click(canvas: 'DrawingCanvas', world_pos: QPointF, event: QTabletEvent):
    """
    DrawingCanvas üzerinde bir tıklama olayını yönetir.
    Seçim aracındayken öğe seçimi veya seçim dışı bırakma için kullanılır.
    """
    logging.debug(f"handle_canvas_click: Tool={canvas.current_tool.name}, Pos={world_pos}")
    
    # Canvas içeriğini güncelleyebileceğinden, önce sayfadaki resimleri QGraphicsItem olarak yükle/güncelle
    if canvas._parent_page and hasattr(canvas._parent_page, 'ensure_pixmaps_loaded'):
        canvas._parent_page.ensure_pixmaps_loaded() 
    if hasattr(canvas, '_load_qgraphics_pixmap_items_from_page'):
        canvas._load_qgraphics_pixmap_items_from_page()

    item_at_click = canvas._get_item_at(world_pos)
    
    ctrl_pressed = event.modifiers() & Qt.KeyboardModifier.ControlModifier
    # shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier # Şimdilik kullanılmıyor

    new_selection = []
    selection_changed = False

    if item_at_click:
        item_type, item_index = item_at_click
        clicked_item_tuple = (item_type, item_index)
        
        if ctrl_pressed: # Ctrl basılıysa, mevcut seçime ekle/çıkar
            if clicked_item_tuple in canvas.selected_item_indices:
                # Zaten seçiliyse, seçimden çıkar
                new_selection = [item for item in canvas.selected_item_indices if item != clicked_item_tuple]
                logging.debug(f"  Ctrl+Click: Item {clicked_item_tuple} deselected.")
            else:
                # Seçili değilse, seçime ekle
                new_selection = canvas.selected_item_indices + [clicked_item_tuple]
                logging.debug(f"  Ctrl+Click: Item {clicked_item_tuple} added to selection.")
            selection_changed = True
        else: # Ctrl basılı değilse, sadece tıklanan öğeyi seç
            if clicked_item_tuple not in canvas.selected_item_indices or len(canvas.selected_item_indices) > 1:
                new_selection = [clicked_item_tuple]
                logging.debug(f"  Click: Item {clicked_item_tuple} selected (new selection).")
                selection_changed = True
            # else: tıklanan öğe zaten tek başına seçiliyse bir şey yapma, seçim değişmedi.
            
    else: # Boş alana tıklandı
        if canvas.selected_item_indices: # Eğer bir seçim varsa
            new_selection = [] # Seçimi temizle
            logging.debug("Boş alana tıklandı, seçim temizlendi.")
            selection_changed = True

    if selection_changed:
        canvas.selected_item_indices = new_selection
        canvas.current_handles.clear() # Yeni seçim için tutamaçları temizle (bir sonraki update'te hesaplanacak)
        # Orijinal durumları da temizle, çünkü seçim değişti
        canvas.original_resize_states.clear()
        canvas.move_original_states.clear()
        
        # Eğer yeni bir seçim yapıldıysa (ve tek bir resimse), orijinal durumları al
        if len(canvas.selected_item_indices) == 1:
            # --- YENİ: _get_current_selection_states'e _parent_page ver ---
            states = canvas._get_current_selection_states(canvas._parent_page)
            # --- --- --- --- --- --- --- --- --- --- --- --- --- --- --- ---
            if states and states[0] is not None: # None kontrolü
                canvas.original_resize_states = states # Boyutlandırma ve döndürme için
                canvas.move_original_states = states # Taşıma için
                
                # canvas.resize_original_bbox'ı da ayarla (eğer resimse)
                item_type, index = canvas.selected_item_indices[0]
                if item_type == 'images' and canvas._parent_page and 0 <= index < len(canvas._parent_page.images):
                    img_data = canvas._parent_page.images[index]
                    canvas.resize_original_bbox = QRectF(img_data.get('rect', QRectF()))
                else:
                    canvas.resize_original_bbox = QRectF() # Diğerleri için boşalt
            else:
                logging.warning("handle_canvas_click: _get_current_selection_states None veya boş state döndürdü.")
                canvas.resize_original_bbox = QRectF()
        else:
            canvas.resize_original_bbox = QRectF() # Çoklu seçim veya seçim yoksa boşalt

        canvas.update()
    # canvas.content_changed.emit() # Bu sinyal daha çok kalıcı değişikliklerde (çizim, silme vb.)
    
    # Seçim sonrası bazı durumları sıfırla (örn. bir önceki hareketten kalanlar)
    canvas.moving_selection = False
    canvas.resizing_selection = False
    canvas.rotating_selection = False
    canvas.resize_threshold_passed = False


# handle_tablet_release fonksiyonu, handle_canvas_click'i doğrudan çağırmaz,
# kendi mantığı içinde seçimle ilgili durumları yönetir.
# handle_tablet_press içindeki Selector aracı da kendi seçim mantığını çalıştırır.
# Bu handle_canvas_click daha çok genel bir "tıklandı ve seçim değişti" olayı gibidir.
# Şimdilik Image Selector press/release içinde bu çağrılmıyor, kendi özel mantıkları var.
# Bu daha çok, diğer araçlardayken bir tıklama olursa veya boş bir alana tıklanırsa diye düşünülebilir.
# Ancak IMAGE_SELECTOR modunda boş alana tıklama da buraya gelmeli.

def calculate_rotated_bbox_aspect_locked(
    original_rect: QRectF,
    original_angle: float,
    mouse_world: QPointF,
    handle_type: str,
    min_size: float = 10.0
) -> QRectF:
    """
    Döndürülmüş bir resmin köşe tutamacı ile, en-boy oranı kilitli şekilde yeni bbox'unu hesaplar.
    BASİTLEŞTİRİLMİŞ YAKLAŞIM: Vektörü yerel eksene çevir, boyutu hesapla, sonra merkezi koruyarak dünyaya döndür.
    """
    if original_rect.isNull() or not original_rect.isValid():
        return original_rect

    center = original_rect.center()
    width = original_rect.width()
    height = original_rect.height()
    aspect = width / height if height > 1e-6 else 1.0

    handle_map = {
        'top-left': (0, 2), 'top-right': (1, 3),
        'bottom-right': (2, 0), 'bottom-left': (3, 1)
    }
    if handle_type not in handle_map:
        return original_rect

    # Sabit köşeyi dünya koordinatlarında bul
    corners_world = [
        original_rect.topLeft(), original_rect.topRight(),
        original_rect.bottomRight(), original_rect.bottomLeft()
    ]
    # Dikkat: Köşeler QRectF'ten alınmalı, ancak QRectF döndürülmüş değil.
    # Önce köşeleri döndürmemiz lazım.
    transform_world = QTransform()
    transform_world.translate(center.x(), center.y())
    transform_world.rotate(original_angle)
    transform_world.translate(-center.x(), -center.y()) # Merkezi referans alarak döndür
    rotated_corners = [
        transform_world.map(original_rect.topLeft()),
        transform_world.map(original_rect.topRight()),
        transform_world.map(original_rect.bottomRight()),
        transform_world.map(original_rect.bottomLeft())
    ]
    if len(rotated_corners) < 4: return original_rect # Hata durumu

    moving_idx, fixed_idx = handle_map[handle_type]
    fixed_corner_world = rotated_corners[fixed_idx]

    # Sabit köşeden mouse'a olan dünya vektörü
    delta_world = mouse_world - fixed_corner_world

    # Bu vektörü resmin yerel (döndürülmemiş) eksenlerine çevir
    transform_vec_to_local = QTransform()
    transform_vec_to_local.rotate(-original_angle)
    delta_local = transform_vec_to_local.map(delta_world)

    # Yeni yerel genişlik/yüksekliği hesapla
    new_local_width = 0.0
    new_local_height = 0.0

    # Hangi boyutun değişeceğine karar ver (aspect'i koruyarak)
    # Baskın yöne göre değil, sabit köşeye göre karar verelim:
    # Örneğin, top-left tutamacıysa, mouse_local'in x ve y'sine göre boyut belirlenir.
    # Hangi boyutun sabit kalacağına handle_type karar verir.
    # BU KISIM HALA KARMAŞIK VE HATAYA AÇIK.

    # DAHA BASİT YAKLAŞIM: İstenen yeni yerel bbox'un köşegen vektörünü (fixed_local -> mouse_local) bul.
    # Ancak fixed_local'ı doğrudan kullanamayız, orijinal yerel bbox'a göre olmalı.
    
    # YENİ YÖNTEM: İstenen yeni boyutu mouse pozisyonundan türet.
    # Mouse'un, resmin DÖNDÜRÜLMÜŞ eksenlerindeki projeksiyonuna bakalım.
    mouse_relative_to_center = mouse_world - center
    # Mouse'un yerel koordinatını bul (merkeze göre, döndürülmüş)
    transform_center_to_local = QTransform().rotate(-original_angle)
    mouse_local_from_center = transform_center_to_local.map(mouse_relative_to_center)

    # Handle tipine göre hangi boyutun mouse tarafından belirlendiğini bul
    target_width = width
    target_height = height

    if handle_type in ['top-left', 'bottom-right']:
        target_width = abs(mouse_local_from_center.x() * 2)
        target_height = abs(mouse_local_from_center.y() * 2)
    elif handle_type in ['top-right', 'bottom-left']:
        target_width = abs(mouse_local_from_center.x() * 2)
        target_height = abs(mouse_local_from_center.y() * 2)
    # Köşe tutamaçlarında, hem en hem boy mouse'a göre belirlenir, sonra aspect ratio uygulanır.
    # Bu nedenle yukarıdaki ayrım gereksiz.
    
    # Mouse'un merkezden uzaklığına göre boyut belirle
    dist_x = abs(mouse_local_from_center.x())
    dist_y = abs(mouse_local_from_center.y())
    
    # En-boy oranını koru
    if (dist_x / aspect) > dist_y:
        new_local_width = dist_x * 2
        new_local_height = new_local_width / aspect
    else:
        new_local_height = dist_y * 2
        new_local_width = new_local_height * aspect

    # Minimum boyut kontrolü
    if new_local_width < min_size:
        new_local_width = min_size
        new_local_height = new_local_width / aspect
    if new_local_height < min_size:
        new_local_height = min_size
        new_local_width = new_local_height * aspect
        
    # Yeni dünya bbox'unu oluştur (merkezi orijinal merkezde)
    half_w = new_local_width / 2.0
    half_h = new_local_height / 2.0
    new_bbox_world = QRectF(center.x() - half_w, center.y() - half_h, new_local_width, new_local_height)

    # Son geçerlilik kontrolü
    if new_bbox_world.isNull() or not new_bbox_world.isValid() or \
       new_bbox_world.width() < min_size / 2 or new_bbox_world.height() < min_size / 2:
        return original_rect

    return new_bbox_world

def calculate_rotated_bbox_from_handle(
    original_rect: QRectF,
    original_angle: float,
    mouse_world: QPointF,
    handle_type: str,
    aspect_ratio_locked: bool,
    min_size: float = 10.0
) -> QRectF:
    """
    Döndürülmüş bir resmin herhangi bir tutamacı ile yeni bbox'unu hesaplar.
    Köşe tutamaçlarında aspect_ratio_locked ise calculate_rotated_bbox_aspect_locked fonksiyonunu çağırır.
    Kenar (middle-*) tutamaçlarında ilgili kenarı mouse ile değiştirir, diğer kenarları sabit tutar.
    """
    # Köşe tutamaçları için aspect_ratio_locked ise özel fonksiyonu çağır
    if handle_type in ['top-left', 'top-right', 'bottom-right', 'bottom-left'] and aspect_ratio_locked:
        return calculate_rotated_bbox_aspect_locked(
            original_rect, original_angle, mouse_world, handle_type, min_size
        )

    center = original_rect.center()
    corners = [
        original_rect.topLeft(),
        original_rect.topRight(),
        original_rect.bottomRight(),
        original_rect.bottomLeft()
    ]
    # Dünya -> yerel (döndürülmemiş, merkezli)
    transform = QTransform()
    transform.translate(-center.x(), -center.y())
    transform.rotate(-original_angle)
    mouse_local = transform.map(mouse_world)
    # Orijinal bbox'u da yerel koordinata çevir (merkezi 0,0 olacak şekilde)
    local_bbox = QRectF(
        -original_rect.width() / 2,
        -original_rect.height() / 2,
        original_rect.width(),
        original_rect.height()
    )
    # Kenar tutamaçları için
    new_bbox_local = QRectF(local_bbox)
    if handle_type == 'middle-left':
        new_left = mouse_local.x()
        if new_left > new_bbox_local.right() - min_size:
            new_left = new_bbox_local.right() - min_size
        new_bbox_local.setLeft(new_left)
    elif handle_type == 'middle-right':
        new_right = mouse_local.x()
        if new_right < new_bbox_local.left() + min_size:
            new_right = new_bbox_local.left() + min_size
        new_bbox_local.setRight(new_right)
    elif handle_type == 'middle-top':
        new_top = mouse_local.y()
        if new_top > new_bbox_local.bottom() - min_size:
            new_top = new_bbox_local.bottom() - min_size
        new_bbox_local.setTop(new_top)
    elif handle_type == 'middle-bottom':
        new_bottom = mouse_local.y()
        if new_bottom < new_bbox_local.top() + min_size:
            new_bottom = new_bbox_local.top() + min_size
        new_bbox_local.setBottom(new_bottom)
    # Yerel (0,0 merkezli) -> Dünya koordinatına dönüştür
    transform_to_world = QTransform()
    transform_to_world.rotate(original_angle)
    transform_to_world.translate(center.x(), center.y())
    poly = QPolygonF()
    poly.append(new_bbox_local.topLeft())
    poly.append(new_bbox_local.topRight())
    poly.append(new_bbox_local.bottomRight())
    poly.append(new_bbox_local.bottomLeft())
    mapped_poly = transform_to_world.map(poly)
    new_bbox_world = mapped_poly.boundingRect()
    # Son kontrol: bbox geçerli mi?
    if new_bbox_world.isNull() or not new_bbox_world.isValid() or new_bbox_world.width() < min_size or new_bbox_world.height() < min_size:
        return original_rect
    return new_bbox_world

def handle_tablet_press(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """
    DrawingCanvas._handle_tablet_press metodunun taşınmış halidir.
    Tablet basma olayını yönetir.
    """
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_press --- Tool: {canvas.current_tool}, World Pos: {pos}") # Log eklendi

    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        if not canvas._parent_page or not canvas._parent_page.main_window:
            logging.error("IMAGE_SELECTOR Press: MainWindow referansı alınamadı.")
            return

        canvas.grabbed_handle_type = None
        clicked_item_info = canvas._get_item_at(pos) # Güncellenmiş _get_item_at kullanımı
        
        # --- Seçili bir öğe var mı ve bu öğe bir resim mi kontrol et ---
        single_selected_image_index = -1
        current_selected_rect = QRectF()
        current_selected_angle = 0.0

        if len(canvas.selected_item_indices) == 1 and canvas.selected_item_indices[0][0] == 'images':
            single_selected_image_index = canvas.selected_item_indices[0][1]
            if 0 <= single_selected_image_index < len(canvas._parent_page.images):
                img_data = canvas._parent_page.images[single_selected_image_index]
                current_selected_rect = QRectF(img_data.get('rect', QRectF()))
                current_selected_angle = img_data.get('angle', 0.0)
                # Orijinal state'leri SADECE işlem başladığında kaydetmek için hazırlık
                canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
            else:
                single_selected_image_index = -1 # Geçersiz index
                canvas.original_resize_states = []
        else:
            canvas.original_resize_states = []

        # --- Tutamaç Kontrolü (SADECE TEK BİR RESİM SEÇİLİYSE) ---
        if single_selected_image_index != -1 and not current_selected_rect.isNull():
            screen_pos = canvas.world_to_screen(pos) # Tutamaçlar ekran koordinatında
            zoom = canvas._parent_page.zoom_level
            # get_handle_at_rotated_point dünya koordinatları ile çalışıyorsa screen_pos yerine pos gönderilmeli
            # Eğer get_handle_at_rotated_point ekran koordinatları bekliyorsa, world_to_screen dönüşümü doğru.
            # Mevcut selection_helpers.get_handle_at_rotated_point ekran koordinatları bekliyor.
            canvas.grabbed_handle_type = selection_helpers.get_handle_at_rotated_point(
                screen_pos,
                current_selected_rect, # Dünya koordinatındaki rect
                current_selected_angle,
                zoom,
                canvas.world_to_screen # Bu fonksiyonun kendisi değil, bir map fonksiyonu gibi kullanılmamalı.
                                      # Bunun yerine canvas.world_to_screen(point) şeklinde kullanılmalı.
                                      # Ancak get_handle_at_rotated_point bunu zaten içermeli.
                                      # Şimdilik bu parametreyi kaldırıyorum, helper kendi içinde yapsın.
            )
            # logging.debug(f"  Handle check on selected image {single_selected_image_index}: rect={current_selected_rect}, angle={current_selected_angle}, screen_pos={screen_pos}, zoom={zoom} -> handle_type={canvas.grabbed_handle_type}") # Log eklendi

        # --- Eylemi Belirle ---
        if canvas.grabbed_handle_type == 'rotate':
            if not canvas.original_resize_states: # State alınmamışsa işlem yapma
                logging.warning("Döndürme başlatılamadı: original_resize_states eksik.")
                return
            logging.debug("Döndürme tutamacı yakalandı. Döndürme başlıyor.")
            canvas.rotating_selection = True
            canvas.resizing_selection = False
            canvas.moving_selection = False
            canvas.selecting = False
            canvas.resize_threshold_passed = False
            
            # original_resize_states zaten press başında alındı.
            # Buradaki state'in 'rect' ve 'angle' içerdiğinden emin olmalıyız.
            img_state_for_rotation = canvas.original_resize_states[0]
            canvas.rotation_center_world = QRectF(img_state_for_rotation.get('rect')).center() # Press anındaki merkez
            # original_angle_at_press original_resize_states içinde zaten var.
            canvas.rotation_start_pos_world = pos # Mouse'un dünya konumu
            QApplication.setOverrideCursor(selection_helpers.get_resize_cursor('rotate'))
            canvas.update()
            return

        elif canvas.grabbed_handle_type: # Boyutlandırma tutamacı
            if not canvas.original_resize_states:
                logging.warning("Boyutlandırma başlatılamadı: original_resize_states eksik.")
                return
            logging.debug(f"Boyutlandırma tutamacı yakalandı: {canvas.grabbed_handle_type}. Boyutlandırma başlıyor.")
            canvas.resizing_selection = True
            canvas.rotating_selection = False
            canvas.moving_selection = False
            canvas.selecting = False
            canvas.resize_threshold_passed = False
            
            # original_resize_states zaten press başında alındı.
            # Buradaki state'in 'rect' ve 'angle' içerdiğinden emin olmalıyız.
            img_state_for_resize = canvas.original_resize_states[0]
            canvas.resize_original_bbox = QRectF(img_state_for_resize.get('rect')) # Press anındaki rect
            # original_angle_for_resize original_resize_states içinde zaten var.
            canvas.resize_start_pos = pos # Mouse'un dünya konumu
            QApplication.setOverrideCursor(selection_helpers.get_resize_cursor(canvas.grabbed_handle_type))
            canvas.update()
            return

        # --- Tutamaç Yoksa, Resim Üzerine Tıklama veya Boş Alana Tıklama ---
        is_clicked_item_selected = (clicked_item_info is not None and
                                    len(canvas.selected_item_indices) == 1 and
                                    clicked_item_info == canvas.selected_item_indices[0])

        if clicked_item_info and is_clicked_item_selected: # Seçili olan resme tekrar tıklandı (taşıma)
            item_type, item_idx = clicked_item_info
            if item_type == 'images': # Sadece resimler taşınabilir
                if not canvas.original_resize_states: # State alınmamışsa (seçim yeni yapıldıysa vs)
                    canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)

                if not canvas.original_resize_states: # Hala state yoksa işlem yapma
                     logging.warning("Taşıma başlatılamadı: original_resize_states alınamadı.")
                     return

                # logging.debug(f"Seçili resme ({clicked_item_info}) tıklandı. Taşıma başlıyor.")
                canvas.moving_selection = True
                canvas.resizing_selection = False
                canvas.rotating_selection = False
                canvas.selecting = False
                canvas.resize_threshold_passed = False
                
                img_state_for_move = canvas.original_resize_states[0] # Tek resim seçili varsayımı
                canvas.move_start_rect = QRectF(img_state_for_move.get('rect'))
                canvas.move_start_pos = pos
                canvas.move_original_states = canvas.original_resize_states # Taşıma komutu için de bu state'i kullanalım
                QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
                canvas.update()
                return
        
        elif clicked_item_info: # Yeni bir resme tıklandı veya seçim yoktu bir resme tıklandı
            item_type, item_idx = clicked_item_info
            if item_type == 'images':
                logging.debug(f"Yeni/farklı bir resme ({clicked_item_info}) tıklandı. Seçim güncelleniyor.")
                canvas.selected_item_indices = [(item_type, item_idx)]
                # Yeni seçilen resim için state'leri al
                canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
                # Taşıma için de hazırlık yapabiliriz, kullanıcı sürüklerse diye
                if canvas.original_resize_states:
                    img_state_for_potential_move = canvas.original_resize_states[0]
                    canvas.move_start_rect = QRectF(img_state_for_potential_move.get('rect'))
                    canvas.move_start_pos = pos
                    # moving_selection henüz True değil, kullanıcı sürüklerse True olacak (move event'inde)
                canvas.update()
                # Burada handle_canvas_click çağırmaya gerek yok, seçimi doğrudan yaptık.
                return 
            else: # Tıklanan öğe resim değil (çizgi, şekil vs)
                # Bu durumu ana canvas_handler.handle_canvas_click yönlendirebilir veya burada yönetebiliriz.
                # Şimdilik resim dışı tıklamaları ana handler'a bırakalım (varsa).
                # Ancak IMAGE_SELECTOR modunda olduğumuz için, resim dışı bir öğeye tıklama
                # genellikle seçimi temizlemeli veya hiçbir şey yapmamalı.
                logging.debug(f"Resim olmayan bir öğeye tıklandı: {clicked_item_info}. Seçim temizleniyor.")
                if canvas.selected_item_indices: # Eğer bir resim seçiliyse
                    canvas.selected_item_indices = []
                    canvas.original_resize_states = []
                    canvas.update()
                return


        else: # Boş alana tıklandı
            logging.debug("Boş alana tıklandı. Mevcut resim seçimi kaldırılıyor.")
            if canvas.selected_item_indices: # Eğer bir resim seçiliyse
                canvas.selected_item_indices = []
                canvas.original_resize_states = []
                canvas.update()
            return
            
    elif canvas.current_tool == ToolType.SELECTOR:
        # --- SEÇİCİ (SELECTOR) için seçim başlatma --- #
        selector_tool_handler.handle_selector_press(canvas, pos, event)
        return

    # Diğer araçlar için press eventleri (PEN, SHAPE, SELECTOR vb.)
    elif canvas.current_tool == ToolType.PEN:
        logging.debug("[canvas_tablet_handler] PEN aracı için handle_pen_press çağrılıyor.")
        pen_tool_handler.handle_pen_press(canvas, pos, event)
    elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
        from gui.tool_handlers import shape_tool_handler
        shape_tool_handler.handle_shape_press(canvas, pos)
    elif canvas.current_tool == ToolType.ERASER:
        eraser_tool_handler.handle_eraser_press(canvas, pos)
        return
    elif canvas.current_tool == ToolType.LASER_POINTER:
        # Lazer işaretçi: sadece pozisyonu güncelle ve update et
        canvas.laser_pointer_active = True
        canvas.last_cursor_pos_screen = canvas.world_to_screen(pos)  # Ekran koordinatına çevir
        canvas.update()
        return
    elif canvas.current_tool == ToolType.TEMPORARY_POINTER:
        temporary_pointer_tool_handler.handle_temporary_drawing_press(canvas, pos, event)
        canvas.update()
        return

# handle_tablet_move ve handle_tablet_release fonksiyonları da benzer şekilde güncellenmeli.
# Bu örnek sadece handle_tablet_press'e odaklandı.

def handle_tablet_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    """
    DrawingCanvas._handle_tablet_move metodunun taşınmış halidir.
    Tablet hareket olayını yönetir.
    """
    updated = False
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_move --- Tool: {canvas.current_tool}, World Pos: {pos}, Resizing: {canvas.resizing_selection}, Moving: {canvas.moving_selection}, Rotating: {canvas.rotating_selection}") # Log eklendi

    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        # --- Eşik Kontrolü (Taşıma, Boyutlandırma, Döndürme için ortak) ---
        if not canvas.resize_threshold_passed:
            start_action_pos = QPointF()
            if canvas.moving_selection and not canvas.move_start_pos.isNull():
                start_action_pos = canvas.move_start_pos
            elif canvas.resizing_selection and not canvas.resize_start_pos.isNull():
                start_action_pos = canvas.resize_start_pos
            elif canvas.rotating_selection and not canvas.rotation_start_pos_world.isNull():
                start_action_pos = canvas.rotation_start_pos_world
            
            if not start_action_pos.isNull():
                if (pos - start_action_pos).manhattanLength() > canvas.RESIZE_MOVE_THRESHOLD:
                    canvas.resize_threshold_passed = True
                    # logging.debug(f"    Threshold PASSED for action starting at {start_action_pos}.") # Log eklendi
            else:
                # Başlangıç pozisyonu yoksa (hata durumu), eşik geçilemez.
                # logging.debug("    Threshold check SKIPPED: No valid start_action_pos.") # Log eklendi
                pass # Bir şey yapma, threshold geçilmemiş sayılır

        if not canvas.resize_threshold_passed:
            # logging.debug("    Movement below threshold, returning.") # Log eklendi
            return # Eşik geçilmediyse hiçbir işlem yapma

        # --- Taşıma --- #
        if canvas.moving_selection:
            if hasattr(canvas, 'move_start_rect') and not canvas.move_start_rect.isNull() and \
               hasattr(canvas, 'move_start_pos') and not canvas.move_start_pos.isNull() and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1 and \
               canvas.selected_item_indices[0][0] == 'images':
                img_index = canvas.selected_item_indices[0][1]
                if canvas._parent_page and 0 <= img_index < len(canvas._parent_page.images):
                    img_data_ref = canvas._parent_page.images[img_index]
                    dosya_yolu = img_data_ref.get('path', None)
                    if dosya_yolu:
                        # Yeni konumu hesapla (taşıma başlangıcına göre)
                        dx = pos.x() - canvas.move_start_pos.x()
                        dy = pos.y() - canvas.move_start_pos.y()
                        yeni_x = int(canvas.move_start_rect.x() + dx)
                        yeni_y = int(canvas.move_start_rect.y() + dy)
                        try:
                            from handlers import resim_islem_handler
                            sonuc = resim_islem_handler.handle_move_image(dosya_yolu, yeni_x, yeni_y)
                            # Sadece handler'dan dönen yeni konumu uygula
                            img_data_ref['rect'].moveTo(yeni_x, yeni_y)
                            updated = True
                        except Exception as e:
                            logging.error(f"Resim handler'a taşıma aktarılırken hata: {e}")
            else:
                pass  # ... mevcut kod ...

        # --- Boyutlandırma --- #
        elif canvas.resizing_selection:
            if canvas.grabbed_handle_type and \
               hasattr(canvas, 'resize_original_bbox') and not canvas.resize_original_bbox.isNull() and \
               canvas.original_resize_states and len(canvas.original_resize_states) == 1 and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1 and \
               canvas.selected_item_indices[0][0] == 'images':
                img_index = canvas.selected_item_indices[0][1]
                original_state = canvas.original_resize_states[0]
                original_angle = original_state.get('angle', 0.0)
                aspect_ratio_locked_for_this_op = not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
                min_dimension = 10.0
                new_bbox_world = QRectF()
                if canvas.grabbed_handle_type in ['top-left', 'top-right', 'bottom-right', 'bottom-left'] and aspect_ratio_locked_for_this_op:
                    new_bbox_world = calculate_rotated_bbox_aspect_locked(
                        canvas.resize_original_bbox,
                        original_angle,
                        pos,
                        canvas.grabbed_handle_type,
                        min_dimension
                    )
                else:
                    new_bbox_world = calculate_rotated_bbox_from_handle(
                        canvas.resize_original_bbox,
                        original_angle,
                        pos,
                        canvas.grabbed_handle_type,
                        aspect_ratio_locked_for_this_op,
                        min_dimension
                    )
                if canvas._parent_page and 0 <= img_index < len(canvas._parent_page.images):
                    img_data_ref = canvas._parent_page.images[img_index]
                    if not new_bbox_world.isNull() and new_bbox_world.isValid():
                        dosya_yolu = img_data_ref.get('path')
                        yeni_genislik = int(new_bbox_world.width())
                        yeni_yukseklik = int(new_bbox_world.height())
                        yeni_x = int(new_bbox_world.x())
                        yeni_y = int(new_bbox_world.y())
                        from handlers import resim_islem_handler
                        sonuc = resim_islem_handler.handle_resize_image(dosya_yolu, yeni_genislik, yeni_yukseklik)
                        img_data_ref['rect'].setRect(yeni_x, yeni_y, sonuc['yeni_genislik'], sonuc['yeni_yukseklik'])
                        # --- YENİ: Pixmap'i yeniden ölçekle ---
                        if 'original_pixmap_for_scaling' in img_data_ref:
                            new_pixmap = img_data_ref['original_pixmap_for_scaling'].scaled(
                                sonuc['yeni_genislik'], sonuc['yeni_yukseklik'],
                                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                            )
                            img_data_ref['pixmap'] = new_pixmap
                            if 'pixmap_item' in img_data_ref and img_data_ref['pixmap_item']:
                                img_data_ref['pixmap_item'].setPixmap(new_pixmap)
                                img_data_ref['pixmap_item'].setPos(QPointF(yeni_x, yeni_y))
                        updated = True
                    else:
                        pass
            else:
                pass

        # --- Döndürme --- #
        elif canvas.rotating_selection:
            if hasattr(canvas, 'rotation_center_world') and not canvas.rotation_center_world.isNull() and \
               hasattr(canvas, 'rotation_start_pos_world') and not canvas.rotation_start_pos_world.isNull() and \
               canvas.original_resize_states and len(canvas.original_resize_states) == 1 and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1 and \
               canvas.selected_item_indices[0][0] == 'images':

                img_index = canvas.selected_item_indices[0][1]
                original_state_for_rotation = canvas.original_resize_states[0]
                original_angle_at_press = original_state_for_rotation.get('angle', 0.0)

                vec_start = canvas.rotation_start_pos_world - canvas.rotation_center_world
                vec_current = pos - canvas.rotation_center_world
                angle_start_rad = math.atan2(vec_start.y(), vec_start.x())
                angle_current_rad = math.atan2(vec_current.y(), vec_current.x())
                delta_angle_rad = angle_current_rad - angle_start_rad
                delta_angle_deg = math.degrees(delta_angle_rad)
                new_angle = original_angle_at_press + delta_angle_deg
                if canvas._parent_page and 0 <= img_index < len(canvas._parent_page.images):
                    img_data_ref = canvas._parent_page.images[img_index]
                    dosya_yolu = img_data_ref.get('path')
                    from handlers import resim_islem_handler
                    sonuc = resim_islem_handler.handle_rotate_image(dosya_yolu, new_angle)
                    img_data_ref['angle'] = sonuc['aci']
                    if 'pixmap_item' in img_data_ref and img_data_ref['pixmap_item']:
                        img_data_ref['pixmap_item'].setRotation(sonuc['aci'])
                    updated = True
            else:
                pass

        if updated:
            canvas.update()
        return # IMAGE_SELECTOR modundaysa diğer modlara geçme
            
    elif canvas.current_tool == ToolType.SELECTOR:
        # --- SEÇİCİ (SELECTOR) için seçim ve sürükleme --- #
        if canvas.selecting:
            selector_tool_handler.handle_selector_rect_select_move(canvas, pos, event)
            return
        elif canvas.moving_selection:
            selector_tool_handler.handle_selector_move_selection(canvas, pos, event)
            return
        elif canvas.resizing_selection:
            selector_tool_handler.handle_selector_resize_move(canvas, pos, event)
            return

    # --- KALEM, ŞEKİL, SEÇİCİ, SİLGİ, GEÇİCİ İŞARETÇİ için olay yönlendirme --- #
    # (Bu kısım değişmedi, aynı kalabilir)
    elif canvas.drawing:
        if canvas.current_tool == ToolType.PEN:
            pen_tool_handler.handle_pen_move(canvas, pos)
            updated = True
        elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
            shape_tool_handler.handle_shape_move(canvas, pos)
            updated = True
    elif canvas.current_tool == ToolType.ERASER:
        eraser_tool_handler.handle_eraser_move(canvas, pos)
        return

    if updated:
        canvas.update()
    # --- LAZER POINTER GERÇEK ZAMANLI GÜNCELLEME ---
    if canvas.current_tool == ToolType.LASER_POINTER:
        canvas.laser_pointer_active = True
        canvas.last_cursor_pos_screen = canvas.world_to_screen(pos)
        canvas.update()
        return

    # --- GEÇİCİ POINTER GERÇEK ZAMANLI GÜNCELLEME ---
    if canvas.current_tool == ToolType.TEMPORARY_POINTER:
        temporary_pointer_tool_handler.handle_temporary_drawing_move(canvas, pos, event)
        canvas.update()
        return

def handle_tablet_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    # logging.debug(f"[canvas_tablet_handler] handle_tablet_release çağrıldı. Tool={canvas.current_tool}")
    """
    DrawingCanvas._handle_tablet_release metodunun taşınmış halidir.
    Tablet bırakma olayını yönetir.
    """
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_release --- Tool: {canvas.current_tool}, World Pos: {pos}") # Log eklendi

    action_performed = False

    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        # --- Taşıma Bitişi --- #
        if canvas.moving_selection:
            # logging.debug("  Finalizing Move Operation.") # Log eklendi
            if canvas.resize_threshold_passed and canvas.move_original_states and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
                item_type, item_idx = canvas.selected_item_indices[0]
                if item_type == 'images' and canvas._parent_page and 0 <= item_idx < len(canvas._parent_page.images):
                    final_img_data = canvas._parent_page.images[item_idx]
                    dosya_yolu = final_img_data.get('path', None)
                    if dosya_yolu:
                        yeni_x = int(final_img_data['rect'].x())
                        yeni_y = int(final_img_data['rect'].y())
                        try:
                            from handlers import resim_islem_handler
                            sonuc = resim_islem_handler.handle_move_image(dosya_yolu, yeni_x, yeni_y)
                            # Sadece handler'dan dönen yeni konumu uygula
                            final_img_data['rect'].moveTo(yeni_x, yeni_y)
                            action_performed = True
                        except Exception as e:
                            logging.error(f"Resim handler'a taşıma aktarılırken hata: {e}")
                    # Eski MoveItemsCommand ve state güncellemeleri images için çalışmayacak
                else:
                    # Eski kod: sadece images dışı için çalışsın
                    # (MoveItemsCommand ve state güncellemeleri burada kalabilir)
                    pass
            canvas.moving_selection = False
            canvas.move_original_states.clear()
            if hasattr(canvas, 'move_start_rect'): canvas.move_start_rect = QRectF()
            if hasattr(canvas, 'move_start_pos'): canvas.move_start_pos = QPointF()

        # --- Boyutlandırma Bitişi --- #
        elif canvas.resizing_selection:
            if canvas.resize_threshold_passed and canvas.grabbed_handle_type and \
               canvas.original_resize_states and len(canvas.original_resize_states) == 1 and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:
                item_type, item_idx = canvas.selected_item_indices[0]
                if item_type == 'images' and canvas._parent_page and 0 <= item_idx < len(canvas._parent_page.images):
                    final_img_data = canvas._parent_page.images[item_idx]
                    dosya_yolu = final_img_data.get('path')
                    yeni_genislik = int(final_img_data['rect'].width())
                    yeni_yukseklik = int(final_img_data['rect'].height())
                    yeni_x = int(final_img_data['rect'].x())
                    yeni_y = int(final_img_data['rect'].y())
                    from handlers import resim_islem_handler
                    sonuc = resim_islem_handler.handle_resize_image(dosya_yolu, yeni_genislik, yeni_yukseklik)
                    final_img_data['rect'].setRect(yeni_x, yeni_y, sonuc['yeni_genislik'], sonuc['yeni_yukseklik'])
                    # --- YENİ: Pixmap'i yeniden ölçekle ---
                    if 'original_pixmap_for_scaling' in final_img_data:
                        new_pixmap = final_img_data['original_pixmap_for_scaling'].scaled(
                            sonuc['yeni_genislik'], sonuc['yeni_yukseklik'],
                            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                        final_img_data['pixmap'] = new_pixmap
                        if 'pixmap_item' in final_img_data and final_img_data['pixmap_item']:
                            final_img_data['pixmap_item'].setPixmap(new_pixmap)
                            final_img_data['pixmap_item'].setPos(QPointF(yeni_x, yeni_y))
                    action_performed = True
                # Eski ResizeItemsCommand ve state güncellemeleri images için çalışmayacak
            canvas.resizing_selection = False
            canvas.grabbed_handle_type = None
            canvas.original_resize_states.clear()
            if hasattr(canvas, 'resize_original_bbox'): canvas.resize_original_bbox = QRectF()
            if hasattr(canvas, 'resize_start_pos'): canvas.resize_start_pos = QPointF()

        # --- Döndürme Bitişi --- #
        elif canvas.rotating_selection:
            if canvas.resize_threshold_passed and \
               canvas.original_resize_states and len(canvas.original_resize_states) == 1 and \
               canvas.selected_item_indices and len(canvas.selected_item_indices) == 1:

                item_type, item_idx = canvas.selected_item_indices[0]
                if item_type == 'images' and canvas._parent_page and 0 <= item_idx < len(canvas._parent_page.images):
                    final_img_data = canvas._parent_page.images[item_idx]
                    dosya_yolu = final_img_data.get('path')
                    final_angle = final_img_data.get('angle', 0.0)
                    from handlers import resim_islem_handler
                    sonuc = resim_islem_handler.handle_rotate_image(dosya_yolu, final_angle)
                    final_img_data['angle'] = sonuc['aci']
                    if 'pixmap_item' in final_img_data and final_img_data['pixmap_item']:
                        final_img_data['pixmap_item'].setRotation(sonuc['aci'])
                    action_performed = True
            canvas.rotating_selection = False
            canvas.original_resize_states.clear()
            if hasattr(canvas, 'rotation_center_world'): canvas.rotation_center_world = QPointF()
            if hasattr(canvas, 'rotation_start_pos_world'): canvas.rotation_start_pos_world = QPointF()

        # Ortak sıfırlamalar
        canvas.resize_threshold_passed = False
        QApplication.restoreOverrideCursor()
        if action_performed or canvas.current_tool == ToolType.IMAGE_SELECTOR: # Bir işlem yapıldıysa veya hala resim modundaysa update et
            canvas.update()
        return # IMAGE_SELECTOR modundaysa diğer modlara geçme

    elif canvas.current_tool == ToolType.SELECTOR:
        # --- SEÇİCİ (SELECTOR) için bırakma --- #
        if canvas.selecting:
            selector_tool_handler.handle_selector_select_release(canvas, pos, event)
            return
        elif canvas.moving_selection:
            selector_tool_handler.handle_selector_move_selection_release(canvas, pos, event)
            return
        elif canvas.resizing_selection:
            selector_tool_handler.handle_selector_resize_release(canvas, pos, event)
            return
    elif canvas.current_tool == ToolType.ERASER:
        eraser_tool_handler.handle_eraser_release(canvas, pos)
        return
    elif canvas.current_tool == ToolType.LASER_POINTER:
        # Lazer işaretçi: bırakınca pozisyonu sıfırla ve update et
        canvas.laser_pointer_active = False
        canvas.last_cursor_pos_screen = QPointF()
        canvas.update()
        return
    elif canvas.current_tool == ToolType.TEMPORARY_POINTER:
        temporary_pointer_tool_handler.handle_temporary_drawing_release(canvas, pos, event)
        return
    # --- KALEM, ŞEKİL, SEÇİCİ, SİLGİ için olay yönlendirme --- #
    # (Bu kısım değişmedi, aynı kalabilir)
    active_operation = canvas.drawing or canvas.erasing or \
                       (canvas.moving_selection and canvas.current_tool == ToolType.SELECTOR) or \
                       (canvas.resizing_selection and canvas.current_tool == ToolType.SELECTOR) or \
                       canvas.selecting
    # ... (Diğer tool handler çağrıları ve genel durum sıfırlama)

    if canvas.current_tool == ToolType.PEN:
        logging.debug("[canvas_tablet_handler] PEN aracı için handle_pen_release çağrılıyor.")
        pen_tool_handler.handle_pen_release(canvas, pos, event)
        return

    elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
        from gui.tool_handlers import shape_tool_handler
        shape_tool_handler.handle_shape_release(canvas, pos)
        return

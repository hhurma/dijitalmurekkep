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
from handlers import resim_islem_handler  # YENİ: Resim işlem handler'ını ekle
from .tool_handlers import pen_tool_handler # YENİ: Pen tool handler importu
from .tool_handlers import shape_tool_handler # YENİ: Shape tool handler importu
from .tool_handlers import selector_tool_handler # YENİ: Selector tool handler importu
from .tool_handlers import eraser_tool_handler # YENİ: Eraser tool handler importu
from .tool_handlers import temporary_pointer_tool_handler # YENİ: Temporary Pointer tool handler importu
from .tool_handlers import editable_line_tool_handler # YENİ: Editable Line tool handler importu
from .tool_handlers import editable_line_node_selector_handler # YENİ: Kontrol Noktası Seçici importu
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
    logging.debug(f"handle_canvas_click: Tool={canvas.current_tool}, Pos={world_pos}")
    
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
    #print(f"[DEBUG] TOOL (PRESS): {canvas.current_tool}")
    #logging.info(f"TOOL (PRESS): {canvas.current_tool}")
    """
    DrawingCanvas._handle_tablet_press metodunun taşınmış halidir.
    Tablet basma olayını yönetir.
    """
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_press --- Tool: {canvas.current_tool}, World Pos: {pos}") # Log eklendi
    action_performed = False

    # --- RESİM SEÇME ARACI İÇİN BASKI --- #
    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        # Önce tutamaç kontrolü yap
        screen_pos = event.position()
        canvas.grabbed_handle_type = canvas._get_handle_at(screen_pos, tolerance=10.0)
        
        if canvas.grabbed_handle_type:
            # Tutamaç yakalandı - boyutlandırma veya döndürmeye başla
            logging.debug(f"IMAGE_SELECTOR: Tutamaç yakalandı: {canvas.grabbed_handle_type}")
            
            # Döndürme tutamacı mı kontrol et
            if canvas.grabbed_handle_type == 'rotation':
                canvas.rotating_selection = True
                canvas.rotation_start_point = pos
            else:
                # Boyutlandırma tutamacı
                canvas.resizing_selection = True
                canvas.resize_start_pos = pos

            # Her durumda orijinal durumları ve bbox'u al
            if canvas.selected_item_indices:
                canvas.original_resize_states = canvas._get_current_selection_states(canvas._parent_page)
                # Seçilen resmin orijinal bbox'ını al
                item_type, index = canvas.selected_item_indices[0]
                if item_type == 'images' and canvas._parent_page and index < len(canvas._parent_page.images):
                    img_data = canvas._parent_page.images[index]
                    canvas.resize_original_bbox = QRectF(img_data.get('rect', QRectF()))
                    canvas.original_angle = img_data.get('angle', 0.0)  # Orijinal açıyı kaydet
            
            # Uygun imleci ayarla
            if canvas.grabbed_handle_type == 'rotation':
                QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
            else:
                QApplication.setOverrideCursor(selection_helpers.get_resize_cursor(canvas.grabbed_handle_type))
                
            canvas.update()
            
            action_performed = True
        else:
            # Tutamaç yakalanmadı, taşıma işlemi için devam et (mevcut kod)
            item_at_click = canvas._get_item_at(pos)
            if item_at_click:
                item_type, index = item_at_click
                if item_type == 'images':
                    # Resmi seç
                    canvas.selected_item_indices = [(item_type, index)]
                    canvas.move_start_point = pos
                    canvas.last_move_pos = pos
                    canvas.selection_changed.emit()
                    canvas.moving_selection = True
                    canvas.move_original_states = canvas._get_current_selection_states(canvas._parent_page)
                    QApplication.setOverrideCursor(Qt.CursorShape.SizeAllCursor)
                    
                    action_performed = True
    
    # --- KALEM ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.PEN:
        pen_tool_handler.handle_pen_press(canvas, pos, event)
        action_performed = True
    
    # --- ŞEKİL ARAÇLARI İÇİN BASKI --- #
    elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
        shape_tool_handler.handle_shape_press(canvas, pos)
        action_performed = True
    
    # --- SEÇİM ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.SELECTOR:
        selector_tool_handler.handle_selector_press(canvas, pos, event)
        action_performed = True

    # --- SİLGİ ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.ERASER:
        # Silgi işlemini başlat
        canvas.erasing = True
        canvas.drawing = False
        canvas.current_eraser_path = [pos]
        canvas.erased_this_stroke = []  # Bu silgi vuruşuyla silinen öğeler
        
        # Tablet kaleminin yan düğmesi basılı mı kontrol et (geçici silme modu)
        stylus_button_pressed = event.buttons() & (Qt.MouseButton.MiddleButton | Qt.MouseButton.RightButton)
        canvas.temporary_erasing = stylus_button_pressed
        # logging.debug(f"Silgi basma: TemporaryErasing={canvas.temporary_erasing}")
        
        action_performed = True
    # --- LAZER İŞARETÇİ ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.LASER_POINTER:
        canvas.laser_pointer_active = True
        canvas.last_cursor_pos_screen = event.position()
        action_performed = True
    # --- GEÇİCİ İŞARETÇİ ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.TEMPORARY_POINTER:
        logging.info(f"TEMPORARY_POINTER PRESS: temporary_drawing_active={canvas.temporary_drawing_active}")
        canvas.temporary_drawing_active = True
        canvas.current_temporary_line_points = [(pos, 0.0)]  # İlk nokta, zaman değeri için placeholder
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE:
        editable_line_tool_handler.handle_editable_line_press(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ DÜZENLEME ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_EDITOR:
        editable_line_tool_handler.handle_editable_line_editor_press(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ KONTROL NOKTASI SEÇİCİ ARACI İÇİN BASKI --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
        editable_line_node_selector_handler.handle_node_selector_press(canvas, pos, event)
        action_performed = True
    elif canvas.current_tool == ToolType.PATH:
        print("[DEBUG] PATH PRESS: Başlatıldı")
        logging.info("PATH PRESS: Başlatıldı")
        
        # PATH çizimine başla
        canvas.drawing = True
        canvas.drawing_shape = True
        # current_path_points oluştur ve ilk noktayı ekle
        canvas.current_path_points = [pos]
        
        action_performed = True
        
    if not action_performed:
        logging.warning(f"handle_tablet_press: İşlem gerçekleştirilmedi! Araç: {canvas.current_tool}")
        event.ignore()
    else:
        # Eğer IMAGE_SELECTOR aracıyla işlem gerçekleştildiyse, tutamaçları güncelle
        if canvas.current_tool == ToolType.IMAGE_SELECTOR:
            canvas.update_current_handles()
            
        canvas.update()  # Çizimi güncelle
        event.accept()

def handle_tablet_move(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    #print(f"[DEBUG] TOOL (MOVE): {canvas.current_tool}")
    #logging.info(f"TOOL (MOVE): {canvas.current_tool}")
    """
    DrawingCanvas._handle_tablet_move metodunun taşınmış halidir.
    Tablet hareket olayını yönetir.
    """
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_move --- Tool: {canvas.current_tool}, World Pos: {pos}")
    action_performed = False

    # --- RESİM SEÇME ARACI İÇİN HAREKET --- #
    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        if canvas.resizing_selection and canvas.grabbed_handle_type and canvas._parent_page and canvas.selected_item_indices:
            # Boyutlandırma işlemi
            item_type, index = canvas.selected_item_indices[0]
            if item_type == 'images' and index < len(canvas._parent_page.images):
                # Yeni boyutu hesapla
                if not canvas.resize_original_bbox.isNull():
                    # Aspect ratio'yu koru
                    aspect_ratio = canvas.resize_original_bbox.width() / canvas.resize_original_bbox.height() if canvas.resize_original_bbox.height() > 0 else 1.0
                    
                    new_bbox = selection_helpers.calculate_rotated_bbox_from_handle(
                        canvas.resize_original_bbox, 
                        canvas.original_angle or 0.0,
                        pos, 
                        canvas.grabbed_handle_type, 
                        True,  # aspect_ratio_locked
                        10.0   # min_size
                    )
                    
                    if not new_bbox.isNull():
                        canvas._parent_page.images[index]['rect'] = new_bbox
                        
                        # YENİ: resim_islem_handler'ı kullan
                        if 'filepath' in canvas._parent_page.images[index]:
                            img_path = canvas._parent_page.images[index]['filepath']
                            resim_islem_handler.handle_resize_image(
                                img_path, 
                                int(new_bbox.width()), 
                                int(new_bbox.height())
                            )
                        
                        canvas.invalidate_cache(reason="Resim boyutlandırma hareketi")
                        canvas.update()
                        action_performed = True
                        
        elif canvas.rotating_selection and canvas.grabbed_handle_type == 'rotation' and canvas._parent_page and canvas.selected_item_indices:
            # Döndürme işlemi
            item_type, index = canvas.selected_item_indices[0]
            if item_type == 'images' and index < len(canvas._parent_page.images):
                img_data = canvas._parent_page.images[index]
                rect = img_data.get('rect')
                
                if rect and not rect.isNull():
                    # Resim merkezini al
                    center = rect.center()
                    
                    # Orijinal açıyı al (veya 0 derece)
                    original_angle = canvas.original_angle or 0.0
                    
                    # Başlangıç ve şu anki açıları hesapla
                    start_angle = math.degrees(math.atan2(canvas.rotation_start_point.y() - center.y(), 
                                                          canvas.rotation_start_point.x() - center.x()))
                    current_angle = math.degrees(math.atan2(pos.y() - center.y(), 
                                                           pos.x() - center.x()))
                    
                    # Açı farkını hesapla (başlangıçtan itibaren kaç derece döndü)
                    angle_delta = current_angle - start_angle
                    
                    # Yeni açıyı hesapla ve uygula
                    new_angle = original_angle + angle_delta
                    img_data['angle'] = new_angle
                    
                    # YENİ: resim_islem_handler'ı kullan
                    if 'filepath' in img_data:
                        img_path = img_data['filepath']
                        resim_islem_handler.handle_rotate_image(img_path, new_angle)
                    
                    canvas.invalidate_cache(reason="Resim döndürme hareketi")
                    canvas.update()
                    action_performed = True
                    
        elif canvas.moving_selection:
            # Mevcut taşıma kodunu koru (değişiklik yok)
            if canvas._parent_page and canvas.selected_item_indices:
                # Kaydırma miktarını hesapla
                dx = pos.x() - canvas.last_move_pos.x()
                dy = pos.y() - canvas.last_move_pos.y()
                
                for item_type, index in canvas.selected_item_indices:
                    if item_type == 'images' and index < len(canvas._parent_page.images):
                        # Resmi kaydır
                        rect = canvas._parent_page.images[index]['rect']
                        rect.translate(dx, dy)
                        
                        # YENİ: resim_islem_handler'ı kullan
                        if 'filepath' in canvas._parent_page.images[index]:
                            img_path = canvas._parent_page.images[index]['filepath']
                            img_x = int(rect.x())
                            img_y = int(rect.y())
                            resim_islem_handler.handle_move_image(img_path, img_x, img_y)
                        canvas.invalidate_cache(reason="Resim taşıma hareketi")
                
                canvas.last_move_pos = pos
                action_performed = True
    
    # --- KALEM ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.PEN:
        pen_tool_handler.handle_pen_move(canvas, pos)
        action_performed = True
    
    # --- ŞEKİL ARAÇLARI İÇİN HAREKET --- #
    elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
        shape_tool_handler.handle_shape_move(canvas, pos)
        action_performed = True

    # --- SEÇİM ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.SELECTOR:
        # Farklı seçici durumlarına göre ilgili handler çağrılır
        if canvas.selecting: # Dikdörtgenle seçim yapılıyorsa
            selector_tool_handler.handle_selector_rect_select_move(canvas, pos, event)
            action_performed = True
        elif canvas.moving_selection: # Seçili öğeler taşınıyorsa
            selector_tool_handler.handle_selector_move_selection(canvas, pos, event)
            action_performed = True 
        elif canvas.resizing_selection: # Seçili öğeler boyutlandırılıyorsa
            selector_tool_handler.handle_selector_resize_move(canvas, pos, event)
            action_performed = True
        # Diğer selector durumları (örn. döndürme) buraya eklenebilir
        
        # Selector aracıyla bir işlem yapıldıysa (veya yapılmadıysa bile durumu yansıtmak için)
        # canvas güncellenmeli.
        canvas.update() # <--- TÜM SELECTOR DURUMLARINDAN SONRA GENEL UPDATE
        # action_performed yukarıdaki bloklarda ayarlandığı için burada ayrıca True yapmaya gerek yok,
        # eğer hiçbir koşul karşılanmazsa False kalır.
        if not action_performed and (canvas.selecting or canvas.moving_selection or canvas.resizing_selection):
            # Bu durum, bir işlem modunda olduğumuzu ama ilgili handler'ın çağrılmadığını gösterir.
            # Genellikle bu olmamalı, ama güvenlik için action_performed True yapılabilir.
            action_performed = True 
            
    # --- SİLGİ ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.ERASER and canvas.erasing:
        # Silgi yoluna yeni nokta ekle
        canvas.current_eraser_path.append(pos)
        canvas.pressure = event.pressure()  # Baskı değerini güncelle
        canvas.update()  # Sadece önizleme için güncelle
        action_performed = True

    # --- LAZER İŞARETÇİ ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.LASER_POINTER:
        canvas.last_cursor_pos_screen = event.position()
        action_performed = True

    # --- GEÇİCİ İŞARETÇİ ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.TEMPORARY_POINTER and canvas.temporary_drawing_active:
        # Geçici işaretçi çizgisine yeni nokta ekle
        import time
        current_time = time.time()
        logging.info(f"TEMPORARY_POINTER MOVE: Adding point at {pos}, time={current_time}")
        canvas.current_temporary_line_points.append((pos, current_time))
        action_performed = True
    
    # --- DÜZENLENEBİLİR ÇİZGİ ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE:
        editable_line_tool_handler.handle_editable_line_move(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ DÜZENLEME ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_EDITOR:
        editable_line_tool_handler.handle_editable_line_editor_move(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ KONTROL NOKTASI SEÇİCİ ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
        editable_line_node_selector_handler.handle_node_selector_move(canvas, pos, event)
        action_performed = True
    # --- PATH ARACI İÇİN HAREKET --- #
    elif canvas.current_tool == ToolType.PATH and canvas.drawing and hasattr(canvas, 'current_path_points'):
        print(f"[DEBUG] PATH MOVE: Nokta eklendi, yeni nokta: {pos}")
        logging.info(f"PATH MOVE: Nokta eklendi, yeni nokta: {pos}")
        
        # PATH çizimine yeni nokta ekle
        canvas.current_path_points.append(pos)
        action_performed = True
    
    if not action_performed:
        # logging.debug(f"handle_tablet_move: İşlem gerçekleştirilmedi! Araç: {canvas.current_tool}")
        event.ignore()
    else:
        canvas.update()  # Çizimi güncelle
        event.accept()

def handle_tablet_release(canvas: 'DrawingCanvas', pos: QPointF, event: QTabletEvent):
    #print(f"[DEBUG] TOOL (RELEASE): {canvas.current_tool}")
    #logging.info(f"TOOL (RELEASE): {canvas.current_tool}")
    """
    DrawingCanvas._handle_tablet_release metodunun taşınmış halidir.
    Tablet bırakma olayını yönetir.
    """
    # logging.debug(f"--- CanvasTabletHandler.handle_tablet_release --- Tool: {canvas.current_tool}, World Pos: {pos}") # Log eklendi

    action_performed = False

    if canvas.current_tool == ToolType.IMAGE_SELECTOR:
        # --- Taşıma, boyutlandırma veya döndürme logicini tamamla ---
        if canvas.moving_selection:
            # --- YENİ: Undo/Redo için MoveItemsCommand ekle (sadece resim için) --- #
            if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1 and canvas.selected_item_indices[0][0] == 'images' and canvas._parent_page:
                import copy
                from utils.commands import MoveItemsCommand
                indices_copy = copy.deepcopy(canvas.selected_item_indices)
                original_states = getattr(canvas, 'move_original_states', [])
                final_states = canvas._get_current_selection_states(canvas._parent_page)
                logging.info(f"[DEBUG] MoveItemsCommand kontrol: original_states={original_states}, final_states={final_states}")
                if original_states and final_states and original_states != final_states:
                    command = MoveItemsCommand(canvas, indices_copy, original_states, final_states)
                    canvas._parent_page.get_undo_manager().execute(command)
                    # --- YENİ: scaled_pixmap cache'ini sıfırla --- #
                    img_idx = indices_copy[0][1]
                    if 0 <= img_idx < len(canvas._parent_page.images):
                        canvas._parent_page.images[img_idx]['_scaled_pixmap'] = None
                        canvas._parent_page.images[img_idx]['_scaled_pixmap_cache_key'] = None
                    if hasattr(canvas, '_load_qgraphics_pixmap_items_from_page'):
                        canvas._load_qgraphics_pixmap_items_from_page()
            # Seçim taşımasını bitir
            canvas.moving_selection = False
            QApplication.restoreOverrideCursor()
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            action_performed = True
        elif canvas.resizing_selection:
            # --- YENİ: Undo/Redo için ResizeItemsCommand ekle (sadece resim için) --- #
            if canvas.selected_item_indices and len(canvas.selected_item_indices) == 1 and canvas.selected_item_indices[0][0] == 'images' and canvas._parent_page:
                import copy
                from utils.commands import ResizeItemsCommand
                indices_copy = copy.deepcopy(canvas.selected_item_indices)
                original_states = getattr(canvas, 'original_resize_states', [])
                final_states = canvas._get_current_selection_states(canvas._parent_page)
                logging.info(f"[DEBUG] ResizeItemsCommand kontrol: original_states={original_states}, final_states={final_states}")
                if original_states and final_states and original_states != final_states:
                    command = ResizeItemsCommand(canvas, indices_copy, original_states, final_states)
                    canvas._parent_page.get_undo_manager().execute(command)
                    # --- YENİ: scaled_pixmap cache'ini sıfırla --- #
                    img_idx = indices_copy[0][1]
                    if 0 <= img_idx < len(canvas._parent_page.images):
                        canvas._parent_page.images[img_idx]['_scaled_pixmap'] = None
                        canvas._parent_page.images[img_idx]['_scaled_pixmap_cache_key'] = None
                    if hasattr(canvas, '_load_qgraphics_pixmap_items_from_page'):
                        canvas._load_qgraphics_pixmap_items_from_page()
            # Boyutlandırmayı bitir
            canvas.resizing_selection = False
            canvas.grabbed_handle_type = None
            QApplication.restoreOverrideCursor()
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            
            # Handle'ları güncelle - tutamaçların ekran koordinatlarını güncelle
            canvas.update_current_handles()
            
            action_performed = True
        elif canvas.rotating_selection:
            # Döndürmeyi bitir
            canvas.rotating_selection = False
            canvas.grabbed_handle_type = None
            QApplication.restoreOverrideCursor()
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            
            # Handle'ları güncelle - tutamaçların ekran koordinatlarını güncelle
            canvas.update_current_handles()
            
            action_performed = True
    
    # --- KALEM ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.PEN:
        pen_tool_handler.handle_pen_release(canvas, pos, event)
        action_performed = True
    
    # --- ŞEKİL ARAÇLARI İÇİN BIRAKMA --- #
    elif canvas.current_tool in [ToolType.LINE, ToolType.RECTANGLE, ToolType.CIRCLE]:
        shape_tool_handler.handle_shape_release(canvas, pos)
        action_performed = True
    
    # --- SEÇİM ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.SELECTOR:
        if canvas.selecting:
            # Dikdörtgen seçimini bitir
            selector_tool_handler.handle_selector_select_release(canvas, pos, event)
            action_performed = True
        elif canvas.moving_selection:
            # Seçim taşımayı bitir
            selector_tool_handler.handle_selector_move_selection_release(canvas, pos, event)
            action_performed = True
        elif canvas.resizing_selection:
            # Seçili öğelerin boyutunu değiştirmeyi bitir
            selector_tool_handler.handle_selector_resize_release(canvas, pos, event)
            action_performed = True
        elif canvas.rotating_selection:
            # Seçili öğeleri döndürmeyi bitir
            pass
            # Bu özellik için rotation bitirme logicini implement et

    # --- SİLGİ ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.ERASER and canvas.erasing:
        if len(canvas.current_eraser_path) > 1:
            from utils import erasing_helpers
            erasing_helpers.erase_at_position(canvas, canvas.current_eraser_path, canvas.eraser_width)
        canvas.erasing = False
        canvas.current_eraser_path = []
        action_performed = True
    
    # --- LAZER İŞARETÇİ ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.LASER_POINTER:
        canvas.laser_pointer_active = False
        action_performed = True

    # --- GEÇİCİ İŞARETÇİ ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.TEMPORARY_POINTER and canvas.temporary_drawing_active:
        # --- YENİ: Pointer Çizgisini Finalize Et --- #
        import time
        current_time = time.time()
        canvas.current_temporary_line_points.append((pos, current_time))
        
        # Geçici çizgiyi tamamla ve temporary_lines listesine ekle (süresi dolunca silinecek)
        if len(canvas.current_temporary_line_points) > 1:
            logging.info(f"TEMPORARY_POINTER RELEASE: Finalizing with {len(canvas.current_temporary_line_points)} points")
            # Noktaları ve renk/kalınlık bilgisini sakla
            points_copy = canvas.current_temporary_line_points.copy()
            color_tuple = (canvas.temp_pointer_color.redF(), canvas.temp_pointer_color.greenF(), 
                          canvas.temp_pointer_color.blueF(), canvas.temp_pointer_color.alphaF())
            start_time = current_time
            
            # Son kaydedilen geçici çizgiyi sil
            if hasattr(canvas, 'temporary_lines'):
                canvas.temporary_lines.append([points_copy, color_tuple, canvas.temp_pointer_width, start_time, False])
            
            canvas.current_temporary_line_points = []
        
        canvas.temporary_drawing_active = False
        action_performed = True
    
    # --- DÜZENLENEBİLİR ÇİZGİ ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE:
        editable_line_tool_handler.handle_editable_line_release(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ DÜZENLEME ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_EDITOR:
        editable_line_tool_handler.handle_editable_line_editor_release(canvas, pos, event)
        action_performed = True
    # --- DÜZENLENEBİLİR ÇİZGİ KONTROL NOKTASI SEÇİCİ ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.EDITABLE_LINE_NODE_SELECTOR:
        editable_line_node_selector_handler.handle_node_selector_release(canvas, pos, event)
        action_performed = True
    
    # --- PATH ARACI İÇİN BIRAKMA --- #
    elif canvas.current_tool == ToolType.PATH:
        # PATH çizimi tamamlandıysa, noktaları shapes'e ekle
        if hasattr(canvas, 'current_path_points') and len(canvas.current_path_points) > 1:
            print(f"[DEBUG] PATH EKLEME ÖNCESİ: shapes len={len(canvas.shapes)}, içerik={canvas.shapes}")
            logging.info(f"PATH EKLEME ÖNCESİ: shapes len={len(canvas.shapes)}, içerik={canvas.shapes}")
            path_points = [QPointF(p.x(), p.y()) for p in canvas.current_path_points]
            path_shape = [
                ToolType.PATH,
                canvas.current_color,
                canvas.current_pen_width,
                path_points,
                canvas.line_style
            ]
            canvas.shapes.append(path_shape)
            print(f"[DEBUG] PATH SHAPE EKLENDİ: {path_shape}")
            logging.info(f"PATH SHAPE EKLENDİ: {path_shape}")
            print(f"[DEBUG] PATH EKLEME SONRASI: shapes len={len(canvas.shapes)}, içerik={canvas.shapes}")
            logging.info(f"PATH EKLEME SONRASI: shapes len={len(canvas.shapes)}, içerik={canvas.shapes}")
            if canvas._parent_page:
                canvas._parent_page.mark_as_modified()
            if hasattr(canvas, 'content_changed'):
                canvas.content_changed.emit()
            canvas.current_path_points = []
            canvas.drawing = False
            canvas.drawing_shape = False
            canvas.update()
        else:
            print("[DEBUG] PATH aracı ile çizim için yeterli nokta yok, shapes'e eklenmedi.")
        action_performed = True
    
    if not action_performed:
        # logging.debug(f"handle_tablet_release: İşlem gerçekleştirilmedi! Araç: {canvas.current_tool}")
        event.ignore()
    else:
        canvas.update()  # Çizimi güncelle
        event.accept()

# YARDIMCI FONKSİYON: Basit yol eğrisi oluşturur
def create_path_from_points(points):
    """Basit bir QPainterPath oluşturur (Kalem aracı için)."""
    from PyQt6.QtGui import QPainterPath
    
    if not points or len(points) < 2:
        return None

    path = QPainterPath()
    path.moveTo(points[0])
    
    for p in points[1:]:
        path.lineTo(p)
    
    return path

# --- Canvas Util Fonksiyonları --- #

def get_pen_pressure(event: QTabletEvent, min_width: float, max_width: float) -> float:
    """Tablet baskısına göre kalem genişliğini hesaplar."""
    pressure = event.pressure()
    if pressure < 0.01:  # Çok küçük değerleri filtrele
        pressure = 0.01
    return min_width + pressure * (max_width - min_width)

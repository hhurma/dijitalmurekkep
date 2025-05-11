# utils/deleting_helpers.py
"""Çizim nesnelerini silme ile ilgili yardımcı fonksiyonlar."""
import logging

# Gerekli importlar ve fonksiyonlar buraya eklenecek

def delete_item_at(point, items_list):
    """Belirtilen noktadaki çizim öğesini bulur ve silmek üzere işaretler/döndürür (Nesne bazlı silme)."""
    logging.warning("delete_item_at henüz implemente edilmedi.")
    # TODO: items_list (lines + shapes) içinde point koordinatını içeren
    #       nesneyi bul (bounding box veya daha hassas kontrol ile)
    return None # Silinecek nesne bulunamadıysa

def delete_pixels_in_area(area, canvas_data):
    """Belirli bir alandaki pikselleri siler (Piksel bazlı silme)."""
    logging.warning("delete_pixels_in_area henüz implemente edilmedi.")
    # TODO: Bu daha karmaşık. OpenGL framebuffer veya doku üzerinde işlem gerektirebilir.
    #       Ya da çizgileri/şekilleri silgi alanına göre kırpmak gerekebilir.
    pass 
"""Yakınlaştırma ve Kaydırma işlemleri için yardımcı fonksiyonlar."""

from PyQt6.QtCore import QPointF
from OpenGL import GL
import logging

def set_projection(width: int, height: int, zoom: float, pan_offset: QPointF):
    """Verilen zoom ve pan değerlerine göre OpenGL projeksiyon matrisini ayarlar.
       (0,0) dünya koordinatını sol üst köşe varsayar.
       pan_offset: Görünümün sol üst köşesinde olması istenen dünya koordinatı.
    """
    if width <= 0 or height <= 0 or zoom <= 1e-6: # zoom sıfır olamaz
        logging.warning(f"set_projection çağrısında geçersiz değerler: w={width}, h={height}, zoom={zoom}")
        # Geçersiz durumda standart bir projeksiyon ayarla (örn. 0,w,h,0)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        GL.glOrtho(0.0, float(width), float(height), 0.0, -1.0, 1.0)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        return

    # Görünür alanın dünya koordinatlarındaki boyutları
    visible_width_world = width / zoom
    visible_height_world = height / zoom

    # Görünür alanın dünya koordinatlarındaki sınırları
    left = pan_offset.x()
    right = pan_offset.x() + visible_width_world
    top = pan_offset.y()
    bottom = pan_offset.y() + visible_height_world

    GL.glMatrixMode(GL.GL_PROJECTION)
    GL.glLoadIdentity()
    # glOrtho(left, right, bottom, top, near, far) - Y aşağı doğru artar
    GL.glOrtho(left, right, bottom, top, -1.0, 1.0)
    GL.glMatrixMode(GL.GL_MODELVIEW)
    GL.glLoadIdentity()
    # logging.debug(f"Projection set: L={left:.1f}, R={right:.1f}, T={top:.1f}, B={bottom:.1f}, Zoom={zoom:.2f}, Pan=({pan_offset.x():.1f},{pan_offset.y():.1f})")

def screen_to_world(screen_pos: QPointF, widget_width: int, widget_height: int, zoom: float, pan_offset: QPointF) -> QPointF:
    """Ekran koordinatlarını (widget üzeri, sol üst 0,0) dünya koordinatlarına çevirir.
       Yeni projeksiyon mantığına göre güncellendi.
    """
    if widget_width <= 0 or widget_height <= 0 or zoom <= 1e-6:
        return QPointF()

    world_x = pan_offset.x() + screen_pos.x() / zoom
    world_y = pan_offset.y() + screen_pos.y() / zoom
    
    # logging.debug(f"ScreenToWorld: Screen({screen_pos.x():.1f},{screen_pos.y():.1f}) -> World({world_x:.1f},{world_y:.1f})")
    return QPointF(world_x, world_y)

def world_to_screen(world_pos: QPointF, widget_width: int, widget_height: int, zoom: float, pan_offset: QPointF) -> QPointF:
    """Dünya koordinatlarını ekran koordinatlarına (widget üzeri, sol üst 0,0) çevirir.
       Yeni projeksiyon mantığına göre güncellendi.
    """
    if widget_width <= 0 or widget_height <= 0 or zoom <= 1e-6:
        return QPointF()

    screen_x = (world_pos.x() - pan_offset.x()) * zoom
    screen_y = (world_pos.y() - pan_offset.y()) * zoom

    # logging.debug(f"WorldToScreen: World({world_pos.x():.1f},{world_pos.y():.1f}) -> Screen({screen_x:.1f},{screen_y:.1f})")
    return QPointF(screen_x, screen_y)

# Yakınlaştırma/Uzaklaştırma için yardımcılar (isteğe bağlı)
ZOOM_FACTOR = 1.2 # Her adımda ne kadar yakınlaşılacak/uzaklaşılacak

def get_zoom_in_level(current_zoom: float) -> float:
    """Mevcut zoom seviyesinden bir adım yakınlaştırılmış seviyeyi döndürür."""
    return current_zoom * ZOOM_FACTOR

def get_zoom_out_level(current_zoom: float) -> float:
    """Mevcut zoom seviyesinden bir adım uzaklaştırılmış seviyeyi döndürür."""
    # Çok fazla uzaklaşmayı engellemek için bir sınır konabilir (örn. 0.1)
    new_zoom = current_zoom / ZOOM_FACTOR
    return max(0.1, new_zoom) # Minimum zoom sınırı 
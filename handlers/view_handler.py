"""Görünüm (Yakınlaştırma, Kaydırma) işlemleri için handler fonksiyonları."""

import logging
from typing import TYPE_CHECKING

# Yardımcı fonksiyonları import et
from utils import view_helpers

if TYPE_CHECKING:
    from gui.page_manager import PageManager

def handle_zoom_in(page_manager: 'PageManager'):
    """Aktif sayfanın görünümünü bir adım yakınlaştırır."""
    if not page_manager:
        logging.error("handle_zoom_in: page_manager None.")
        return
        
    current_page = page_manager.get_current_page()
    if current_page:
        new_zoom = view_helpers.get_zoom_in_level(current_page.zoom_level)
        logging.debug(f"Zoom In requested. Current: {current_page.zoom_level:.2f}, New: {new_zoom:.2f}")
        current_page.set_zoom(new_zoom)
    else:
        logging.warning("handle_zoom_in: Aktif sayfa bulunamadı.")

def handle_zoom_out(page_manager: 'PageManager'):
    """Aktif sayfanın görünümünü bir adım uzaklaştırır."""
    if not page_manager:
        logging.error("handle_zoom_out: page_manager None.")
        return
        
    current_page = page_manager.get_current_page()
    if current_page:
        new_zoom = view_helpers.get_zoom_out_level(current_page.zoom_level)
        logging.debug(f"Zoom Out requested. Current: {current_page.zoom_level:.2f}, New: {new_zoom:.2f}")
        current_page.set_zoom(new_zoom)
    else:
        logging.warning("handle_zoom_out: Aktif sayfa bulunamadı.")

def handle_reset_view(page_manager: 'PageManager'):
    """Aktif sayfanın görünümünü (zoom ve pan) sıfırlar."""
    if not page_manager:
        logging.error("handle_reset_view: page_manager None.")
        return
        
    current_page = page_manager.get_current_page()
    if current_page:
        logging.debug("Reset View requested.")
        current_page.reset_view()
    else:
        logging.warning("handle_reset_view: Aktif sayfa bulunamadı.")

# TODO: handle_pan(page_manager, dx, dy) eklenebilir (orta tuş veya pan aracı için) 
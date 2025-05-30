# rotation_helpers.py
# Kısa açıklama: Döndürme işlemleri için yardımcı fonksiyonlar
import math

def rotate_point(point, center, angle_rad):
    """Bir noktayı verilen merkez etrafında belirli bir radyan açı kadar döndür."""
    x, y = point
    cx, cy = center
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    dx = x - cx
    dy = y - cy
    rx = cos_a * dx - sin_a * dy + cx
    ry = sin_a * dx + cos_a * dy + cy
    return rx, ry


def rotate_shape(points, center, angle_rad):
    """Birden fazla noktadan oluşan şekli verilen merkez etrafında döndür."""
    return [rotate_point(p, center, angle_rad) for p in points]

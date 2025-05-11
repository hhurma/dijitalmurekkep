import os
import logging

# Resimlerin bilgilerini tutan basit bir veri yapısı (modül düzeyinde)
resim_veritabani = {}

def handle_select_image(dosya_yolu: str) -> str:
    """
    Verilen dosya yolunu kontrol eder ve seçilen resmin yolunu döndürür.
    Bu fonksiyon sadece resim seçme işlemini yönetir.
    """
    # Resim ilk kez seçiliyorsa varsayılan değerlerle ekle
    if dosya_yolu not in resim_veritabani:
        resim_veritabani[dosya_yolu] = {
            "x": 0,
            "y": 0,
            "aci": 0.0,
            "genislik": 100,
            "yukseklik": 100
        }
    return dosya_yolu

def handle_move_image(resim_yolu: str, yeni_x: int, yeni_y: int) -> dict:
    """
    Verilen resmin konumunu günceller.
    """
    if resim_yolu in resim_veritabani:
        resim_veritabani[resim_yolu]["x"] = yeni_x
        resim_veritabani[resim_yolu]["y"] = yeni_y
    return {"resim_yolu": resim_yolu, "yeni_x": yeni_x, "yeni_y": yeni_y}

def handle_rotate_image(resim_yolu: str, aci: float) -> dict:
    """
    Verilen resmin açısını günceller.
    """
    if resim_yolu in resim_veritabani:
        resim_veritabani[resim_yolu]["aci"] = aci
    return {"resim_yolu": resim_yolu, "aci": aci}

def handle_resize_image(resim_yolu: str, yeni_genislik: int, yeni_yukseklik: int) -> dict:
    """
    Verilen resmin boyutunu günceller.
    """
    if resim_yolu in resim_veritabani:
        resim_veritabani[resim_yolu]["genislik"] = yeni_genislik
        resim_veritabani[resim_yolu]["yukseklik"] = yeni_yukseklik
    return {"resim_yolu": resim_yolu, "yeni_genislik": yeni_genislik, "yeni_yukseklik": yeni_yukseklik}


def handle_delete_image(image_path: str):
    """
    Verilen dosya yolundaki resmi siler.
    """
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
            logging.info(f"Resim dosyası silindi: {image_path}")
        else:
            logging.warning(f"Silinmek istenen resim dosyası bulunamadı: {image_path}")
    except Exception as e:
        logging.error(f"Resim silinirken hata oluştu: {e}")
        
if __name__ == "__main__":
    # Basit birim testler
    print("Test: handle_select_image")
    assert handle_select_image("/tmp/resim.png") == "/tmp/resim.png"
    assert resim_veritabani["/tmp/resim.png"]["x"] == 0

    print("Test: handle_move_image")
    sonuc = handle_move_image("/tmp/resim.png", 100, 200)
    assert sonuc == {"resim_yolu": "/tmp/resim.png", "yeni_x": 100, "yeni_y": 200}
    assert resim_veritabani["/tmp/resim.png"]["x"] == 100
    assert resim_veritabani["/tmp/resim.png"]["y"] == 200

    print("Test: handle_rotate_image")
    sonuc = handle_rotate_image("/tmp/resim.png", 45.0)
    assert sonuc == {"resim_yolu": "/tmp/resim.png", "aci": 45.0}
    assert resim_veritabani["/tmp/resim.png"]["aci"] == 45.0

    print("Test: handle_resize_image")
    sonuc = handle_resize_image("/tmp/resim.png", 300, 400)
    assert sonuc == {"resim_yolu": "/tmp/resim.png", "yeni_genislik": 300, "yeni_yukseklik": 400}
    assert resim_veritabani["/tmp/resim.png"]["genislik"] == 300
    assert resim_veritabani["/tmp/resim.png"]["yukseklik"] == 400

    print("Tüm testler başarıyla geçti.") 
# Dijital Mürekkep

PyQt6 ve OpenGL tabanlı, kalem destekli dijital not alma uygulaması.

## Özellikler
- Çoklu sayfa yönetimi
- Çizgili, kareli ve düz şablon seçenekleri
- Kalem, çizgi, dikdörtgen, daire, silgi ve seçim araçları
- Resim ekleme, taşıma ve boyutlandırma
- PDF içe/dışa aktarma
- Gelişmiş geri al/ileri al (undo/redo)
- Grid (ızgara) desteği ve çizgi snap özelliği
- Hızlı renk seçimi ve özelleştirilebilir araç çubuğu
- Ayarların ve son açılan dosyaların otomatik kaydı
- Sürükle-bırak ile sayfa sıralama
- Kapsamlı klavye kısayolları

## Klasör Yapısı

```
proje/
├── main.py
├── gui/
│   └── arayuz.py
├── handlers/
│   ├── genel_handler.py
│   └── dosya_handler.py
├── utils/
│   └── logger.py
├── config/
│   └── settings.json
├── build_info.py
└── README.md
```

## Kurulum

```bash
pip install -r requirements.txt
```

## Çalıştırma

```bash
python main.py
```

## Sürüm ve Derleme Bilgisi

Sürüm: v1.0.0  
Derleme tarihi: `build_info.py` içindeki `BUILD_TIMESTAMP` sabiti kullanılır.

## Katkı ve Lisans

Katkıda bulunmak için pull request gönderebilirsiniz.  
Lisans: MIT 

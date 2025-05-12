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
- **Şekil Havuzu (Depo) Özelliği:**
  - Seçili bir veya birden fazla şekil ve/veya serbest çizim (kalemle path) birlikte "havuz"a (depo) kaydedilebilir.
  - Havuzdan istenen grup, başlığı ile seçilerek aktif sayfaya eklenebilir.
  - Hem şekiller (dikdörtgen, daire, çizgi vb.) hem de serbest çizimler (lines) aynı anda depolanabilir ve geri çağrılabilir.
  - Havuzdan şekil/çizim grubu silinebilir.
  - Tüm işlemler Edit menüsünden kolayca erişilebilir.

## Klasör Yapısı

```
proje/
├── main.py
├── gui/
│   └── arayuz.py
│   └── config/
│       └── shape_pool.json   # Şekil havuzu verisi
├── handlers/
│   ├── shape_pool_handler.py # Şekil havuzu işlemleri
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

Sürüm: v1.1.0  
Derleme tarihi: `build_info.py` içindeki `BUILD_TIMESTAMP` sabiti kullanılır.

## Katkı ve Lisans

Katkıda bulunmak için pull request gönderebilirsiniz.  
Lisans: MIT 

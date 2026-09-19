# YEDAŞ Planlı Kesinti & GSM Saha İzleme Sistemi

Streamlit tabanlı, YEDAŞ planlı kesintileri ile ~1300 GSM baz istasyonunu
karşılaştıran, haritada gösteren, sürüş mesafesi hesaplayan, arıza
kayıtlarını mum grafiği ile sunan ve admin yönetimi barındıran uygulama.

## Kurulum

```bash
pip install -r requirements.txt
streamlit run app.py
```

Uygulama ilk açıldığında veritabanı boşsa, sistemi uçtan uca test
edebilmeniz için otomatik olarak ~1300 örnek GSM sahası ve ilçe merkezi
verisi oluşturulur (`sample_data.py`). Gerçek saha listenizi Admin
panelinden (`admin5555`) yükleyerek bu örnek veriyi güncelleyebilirsiniz
(Excel Diff senkronizasyonu otomatik olarak eski/yeni farkını uygular).

## Proje Yapısı

```
app.py                      # Ana giriş noktası, veritabanı init, seed
database.py                 # SQLite şeması ve tüm CRUD işlemleri
yedas_client.py              # YEDAŞ API istemcisi (cache_data ttl=300)
osrm_client.py                # OSRM rota/mesafe istemcisi (SQLite cache)
geo_utils.py                 # GeoPandas spatial join (point-in-polygon)
report_utils.py              # Pillow ile JPG rapor üretimi
sample_data.py                # Test/offline mock veri üreticisi
pages/
  1_📡_Ana_Ekran.py            # Canlı kesintiler haritası
  2_📊_Detay_ve_Analiz.py      # Top-5 KPI + mum grafik
  3_🗺️_Sahalar_ve_Mesafe.py    # Saha <-> ilçe merkezi mesafe/rota
  4_🚨_Ariza_Takip.py           # Mains/Backup/Outage Gantt/mum grafik
  5_🔐_Admin_Paneli.py          # Şifreli admin, Excel sync, merkez yönetimi
```

## Canlı Ortama Alırken Yapılması Gerekenler

Bu geliştirme sandbox'ının ağ erişimi kısıtlı olduğundan (YEDAŞ ve OSRM
uç noktalarına ulaşılamıyor), varsayılan olarak **mock/örnek veri**
kullanılacak şekilde yapılandırılmıştır. Gerçek sunucuya dağıtırken:

1. **`yedas_client.py`** içinde `USE_MOCK_DATA_DEFAULT = False` yapın.
   Gerçek API yanıtını bir kez örnekleyip `FIELD_MAP_CANDIDATES`
   sözlüğündeki alan adlarını (`il`, `ilce`, `baslangic`, `bitis`,
   `aciklama`, `ref`) gerçek JSON alan adlarıyla eşleştirin.

2. **`osrm_client.py`** içinde `OSRM_BASE_URL`'i kendi barındırdığınız
   OSRM sunucunuzun adresiyle değiştirin (halka açık demo sunucu
   rate-limit uygulayabilir, üretim için önerilmez).

3. **Admin şifresi**: `pages/5_🔐_Admin_Paneli.py` içindeki
   `ADMIN_PASSWORD = "admin5555"` değişkenini üretimde ortam
   değişkeninden veya `st.secrets`'tan okuyacak şekilde güncelleyin.

4. **Gerçek saha listesi**: Admin panelinden şirketinizin güncel
   `.xlsx` dosyasını yükleyin; sistem otomatik olarak diff uygulayıp
   yeni/silinen sahaları raporlayacaktır.

## Notlar

- Spatial join, GeoPandas'ın R-Tree indeksli `sjoin` fonksiyonunu
  kullanır; 1300 nokta x onlarca poligon karşılaştırması milisaniyeler
  içinde tamamlanır.
- OSRM sonuçları SQLite'da (`osrm_cache` tablosu) saklanır; aynı
  saha-merkez çifti için tekrar API çağrısı yapılmaz.
- Admin oturumu `st.session_state` üzerinde tutulur; bu nedenle sadece
  giriş yapan kullanıcının tarayıcı sekmesi/oturumu için geçerlidir,
  sayfa yenilenince veya sekme kapanınca sıfırlanır.

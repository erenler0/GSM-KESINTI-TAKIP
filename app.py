"""
app.py
------
YEDAŞ Kesinti & GSM Saha İzleme Sistemi - Ana Giriş Noktası

Çalıştırma:
    streamlit run app.py

Sayfalar `pages/` klasöründe otomatik olarak Streamlit'in
multipage yapısıyla sol menüde listelenir.
"""

import streamlit as st
import database as db
import pandas as pd

st.set_page_config(
    page_title="YEDAŞ Kesinti & GSM Saha İzleme",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Veritabanını başlat
db.init_db()

# NOT: Demo/Örnek verilerin veritabanı boşken otomatik yüklenmesini engellemek için
# seed_demo_data_if_empty() çağrısı devreden çıkarılmıştır.
# Kendi verilerinizi doğrudan Admin Paneli üzerinden yükleyebilirsiniz.

st.title("⚡ YEDAŞ Planlı Kesinti & GSM Saha İzleme Sistemi")

st.markdown("""
Bu sistem, **YEDAŞ planlı kesinti** verilerini **~1300 GSM baz istasyonu**
koordinatlarıyla karşılaştırarak etkilenen sahaları anlık olarak tespit eder,
haritada gösterir, sürüş mesafelerini hesaplar ve arıza geçmişini analiz eder.

### 📋 Sol menüden bir ekran seçin:
- **📡 Ana Ekran** — Canlı YEDAŞ kesintileri ve etkilenen sahalar
- **📊 Detay ve Analiz** — Top-5 istatistikler, mum grafik, arama/filtre
- **🗺️ Sahalar & Mesafe** — Saha ↔ İlçe merkezi rota/mesafe hesaplama
- **🚨 Arıza Takip** — Mains/Backup/Outage kayıt girişi ve Gantt/mum grafik
- **🔐 Admin Paneli** — Excel yükleme, senkronizasyon, ilçe merkezi yönetimi
""")

col1, col2, col3, col4 = st.columns(4)
sahalar = db.get_all_sahalar()
merkezler = db.get_all_ilce_merkezleri()

with col1:
    st.metric("📡 Aktif GSM Sahası", len(sahalar))
with col2:
    st.metric("🏙️ Tanımlı İlçe Merkezi", len(merkezler))
with col3:
    kesintiler = db.get_kesintiler(gun_sayisi=7)
    st.metric("⚡ Son 7 Gün Kesinti", len(kesintiler))
with col4:
    admin_status = "🟢 Aktif" if st.session_state.get("is_admin") else "🔴 Pasif"
    st.metric("🔐 Admin Oturumu", admin_status)

# Mavi st.info() not kutusu buradan kaldırılmıştır.

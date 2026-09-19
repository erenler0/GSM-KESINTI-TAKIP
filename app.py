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

db.init_db()


def seed_demo_data_if_empty():
    """
    Veritabanı tamamen boşsa (ilk kurulum), uygulamanın demo modunda
    uçtan uca test edilebilmesi için örnek saha / ilçe merkezi verisi
    yükler. Gerçek ortamda admin panelinden gerçek Excel dosyası
    yüklendiğinde bu veri Excel Diff senkronizasyonu ile güncellenir.
    """
    existing = db.get_all_sahalar(only_active=False)
    if not existing.empty:
        return

    from sample_data import generate_mock_sahalar, generate_ilce_merkezleri_df

    with st.spinner("İlk kurulum: örnek saha verisi ve ilçe merkezleri yükleniyor (~1300 saha)..."):
        df_merkez = generate_ilce_merkezleri_df()
        for _, row in df_merkez.iterrows():
            db.add_ilce_merkezi(row["isim"], row["il"], row["latitude"], row["longitude"])

        df_saha = generate_mock_sahalar(1300)
        db.upsert_sahalar_from_df(df_saha)

        # İl/ilçe bilgisini ve varsayılan en yakın merkez atamasını yap
        from geo_utils import find_nearest_ilce_merkezi
        sahalar = db.get_all_sahalar()
        merkezler = db.get_all_ilce_merkezleri()

        with db.get_conn() as conn:
            c = conn.cursor()
            for _, saha in sahalar.iterrows():
                nearest, _ = find_nearest_ilce_merkezi(saha["latitude"], saha["longitude"], merkezler)
                if nearest is not None:
                    c.execute(
                        "UPDATE sahalar SET il=?, ilce=?, ilce_merkezi_id=? WHERE id=?",
                        (nearest["il"], nearest["isim"], int(nearest["id"]), int(saha["id"]))
                    )
            conn.commit()


seed_demo_data_if_empty()

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

st.info(
    "ℹ️ **Not:** Bu ortamda YEDAŞ API'si ve OSRM sunucusuna doğrudan ağ erişimi "
    "kısıtlı olabilir; bu durumda sistem otomatik olarak gerçekçi **örnek veri** "
    "ile çalışır. Canlı sunucuya dağıtıldığında `yedas_client.py` ve `osrm_client.py` "
    "içindeki `use_mock` bayrakları `False` yapılarak gerçek API'lere bağlanılır."
)

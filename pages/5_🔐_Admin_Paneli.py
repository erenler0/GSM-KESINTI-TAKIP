"""
Ekran 5: 🔐 Admin Paneli & Yetkilendirme
- Şifre: admin5555
- Session-based auth: sadece bu tarayıcı sekmesi/oturumu için geçerli
- Excel Diff senkronizasyonu (eklenen/silinen saha tespiti)
- İlçe merkezleri yönetimi
- Saha - İlçe merkezi manuel atama (override)
"""

import streamlit as st
import pandas as pd
import database as db
import report_utils

st.set_page_config(page_title="Admin Paneli", page_icon="🔐", layout="wide")
st.title("🔐 Admin Paneli & Yetkilendirme")

ADMIN_PASSWORD = "admin5555"

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ---------------------------------------------------------------------------
# Oturum Yönetimi (Session-Based Auth)
# ---------------------------------------------------------------------------
if not st.session_state.is_admin:
    st.warning("Bu ekrana erişmek için admin girişi yapmanız gerekiyor.")
    pw = st.text_input("Admin Şifresi", type="password")
    if st.button("Giriş Yap"):
        if pw == ADMIN_PASSWORD:
            st.session_state.is_admin = True
            st.success("✅ Giriş başarılı. Bu oturum için admin yetkisi aktif.")
            st.rerun()
        else:
            st.error("❌ Hatalı şifre.")
    st.stop()

st.success("🟢 Admin oturumu aktif (yalnızca bu tarayıcı sekmesi için geçerlidir).")
if st.button("🚪 Oturumu Kapat"):
    st.session_state.is_admin = False
    st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Akıllı Excel Senkronizasyonu (Diff)
# ---------------------------------------------------------------------------
st.header("📥 Saha Excel Senkronizasyonu")
st.caption("Beklenen sütunlar: Placemark Adı, Latitude, Longitude, KML Dosyası, Açıklama, Altitude, Koordinat (Ham)")

uploaded = st.file_uploader("Yeni Saha Listesi Excel Dosyası (.xlsx)", type=["xlsx"])

if uploaded is not None:
    try:
        df_new = pd.read_excel(uploaded)
        required_cols = {"Placemark Adı", "Latitude", "Longitude"}
        missing = required_cols - set(df_new.columns)
        if missing:
            st.error(f"Eksik sütunlar: {', '.join(missing)}")
        else:
            st.write(f"📄 Yüklenen dosyada **{len(df_new)}** saha kaydı bulundu.")
            st.dataframe(df_new.head(10), use_container_width=True)

            if st.button("🔄 Senkronizasyonu Başlat (Diff Uygula)"):
                with st.spinner("Karşılaştırma yapılıyor..."):
                    eklenen, silinen = db.diff_and_sync_sahalar(df_new)

                    # Yeni eklenen sahalar için il/ilçe ve en yakın merkez ataması
                    from geo_utils import find_nearest_ilce_merkezi
                    merkezler = db.get_all_ilce_merkezleri()
                    if not merkezler.empty and eklenen:
                        with db.get_conn() as conn:
                            c = conn.cursor()
                            for name in eklenen:
                                row = c.execute("SELECT id, latitude, longitude FROM sahalar WHERE placemark_adi=?", (name,)).fetchone()
                                if row:
                                    nearest, _ = find_nearest_ilce_merkezi(row["latitude"], row["longitude"], merkezler)
                                    if nearest is not None:
                                        c.execute("UPDATE sahalar SET il=?, ilce=?, ilce_merkezi_id=? WHERE id=?",
                                                  (nearest["il"], nearest["isim"], int(nearest["id"]), row["id"]))
                            conn.commit()

                st.success(f"✅ Senkronizasyon tamamlandı: {len(eklenen)} saha eklendi, {len(silinen)} saha kaldırıldı (pasif işaretlendi).")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**➕ Eklenen Sahalar**")
                    st.dataframe(pd.DataFrame({"Saha Adı": eklenen}) if eklenen else pd.DataFrame({"Saha Adı": []}), hide_index=True, use_container_width=True)
                with c2:
                    st.markdown("**➖ Silinen (Pasif) Sahalar**")
                    st.dataframe(pd.DataFrame({"Saha Adı": silinen}) if silinen else pd.DataFrame({"Saha Adı": []}), hide_index=True, use_container_width=True)

                img = report_utils.excel_diff_jpg(eklenen, silinen)
                st.image(img, caption="Fark Raporu Önizleme")
                st.download_button("⬇️ Fark Raporu (JPG) İndir", data=report_utils.image_to_bytes(img),
                                    file_name="excel_fark_raporu.jpg", mime="image/jpeg")
    except Exception as e:
        st.error(f"Dosya okunurken hata oluştu: {e}")

st.divider()

# ---------------------------------------------------------------------------
# İlçe Merkezleri Yönetimi
# ---------------------------------------------------------------------------
st.header("🏙️ İlçe Merkezleri Yönetimi")

merkezler = db.get_all_ilce_merkezleri()

c1, c2 = st.columns([1, 1])
with c1:
    st.subheader("➕ Yeni İlçe Merkezi Ekle")
    with st.form("yeni_merkez_form", clear_on_submit=True):
        isim = st.text_input("İlçe / Merkez Adı")
        il = st.selectbox("İl", options=["Samsun", "Sinop", "Ordu", "Amasya", "Tokat", "Çorum"])
        lat = st.number_input("Latitude", format="%.6f", value=40.0)
        lon = st.number_input("Longitude", format="%.6f", value=36.0)
        if st.form_submit_button("Ekle"):
            if isim:
                db.add_ilce_merkezi(isim, il, lat, lon)
                st.success(f"✅ {isim} ({il}) eklendi.")
                st.rerun()
            else:
                st.error("İsim boş olamaz.")

with c2:
    st.subheader("🔎 Ara / Sil")
    arama = st.text_input("Merkez Ara", key="merkez_ara")
    filtered_merkez = merkezler[merkezler["isim"].str.contains(arama, case=False, na=False)] if arama else merkezler
    for _, row in filtered_merkez.iterrows():
        cc1, cc2 = st.columns([4, 1])
        cc1.write(f"📍 **{row['isim']}** ({row['il']}) — {row['latitude']:.4f}, {row['longitude']:.4f}")
        if cc2.button("🗑️", key=f"del_merkez_{row['id']}"):
            db.delete_ilce_merkezi(row["id"])
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Saha - İlçe Merkezi Manuel Atama (Override)
# ---------------------------------------------------------------------------
st.header("🔗 Saha — İlçe Merkezi Manuel Atama (Override)")
st.caption("Bir saha, coğrafi olarak en yakın merkeze bakılmaksızın operasyonel olarak farklı bir merkeze bağlanabilir.")

sahalar = db.get_all_sahalar()
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    saha_secim = st.selectbox("Saha Seç", options=sorted(sahalar["placemark_adi"].tolist()) if not sahalar.empty else [])
with c2:
    merkez_secim = st.selectbox(
        "Yeni İlçe Merkezi",
        options=merkezler.apply(lambda r: f"{r['isim']} ({r['il']}) [id:{r['id']}]", axis=1).tolist() if not merkezler.empty else []
    )
with c3:
    st.write("")
    st.write("")
    if st.button("✅ Ata"):
        if saha_secim and merkez_secim:
            saha_row = db.get_saha_by_name(saha_secim)
            merkez_id = int(merkez_secim.split("[id:")[1].rstrip("]"))
            db.set_saha_ilce_merkezi(saha_row["id"], merkez_id, manuel=True)
            st.success(f"✅ {saha_secim} → {merkez_secim} olarak manuel atandı.")

# Mevcut atamaları göster
if not sahalar.empty:
    merkez_lookup = merkezler.set_index("id")["isim"].to_dict() if not merkezler.empty else {}
    sahalar_show = sahalar.copy()
    sahalar_show["Atanan Merkez"] = sahalar_show["ilce_merkezi_id"].map(merkez_lookup)
    sahalar_show["Atama Tipi"] = sahalar_show["manuel_atama"].map({1: "Manuel", 0: "Otomatik (En Yakın)"})
    st.dataframe(
        sahalar_show[["placemark_adi", "il", "ilce", "Atanan Merkez", "Atama Tipi"]].rename(
            columns={"placemark_adi": "Saha Adı", "il": "İl", "ilce": "İlçe"}
        ),
        use_container_width=True, hide_index=True, height=350,
    )

st.divider()

# ---------------------------------------------------------------------------
# Sistem Bilgisi
# ---------------------------------------------------------------------------
st.header("ℹ️ Sistem Durumu")
c1, c2, c3 = st.columns(3)
c1.metric("Toplam Aktif Saha", len(db.get_all_sahalar()))
c2.metric("Toplam İlçe Merkezi", len(db.get_all_ilce_merkezleri()))
with db.get_conn() as conn:
    sync_log = pd.read_sql_query("SELECT * FROM excel_sync_log ORDER BY created_at DESC LIMIT 5", conn)
c3.metric("Son Senkronizasyon Sayısı", len(sync_log))

if not sync_log.empty:
    st.subheader("📜 Senkronizasyon Geçmişi (Son 5)")
    st.dataframe(sync_log[["created_at", "eklenen_sayisi", "silinen_sayisi"]].rename(
        columns={"created_at": "Tarih", "eklenen_sayisi": "Eklenen", "silinen_sayisi": "Silinen"}
    ), hide_index=True, use_container_width=True)

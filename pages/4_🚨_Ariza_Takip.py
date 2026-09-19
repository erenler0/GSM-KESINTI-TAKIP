"""
Ekran 4: 🚨 Arıza Takip & Şebeke/Kesinti Analizi
Yeşil mum: Mains alarm -> Saha Down (Backup/akü süresi)
Kırmızı mum: Saha Down -> Enerji geldi (Outage süresi)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import database as db
import report_utils

st.set_page_config(page_title="Arıza Takip", page_icon="🚨", layout="wide")
st.title("🚨 Arıza Takip & Şebeke/Kesinti Analizi")

sahalar = db.get_all_sahalar()

# ---------------------------------------------------------------------------
# Veri Giriş Formu
# ---------------------------------------------------------------------------
with st.expander("➕ Yeni Arıza Kaydı Girişi", expanded=False):
    with st.form("ariza_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            saha_adi = st.selectbox("Saha Ara / Seç", options=sorted(sahalar["placemark_adi"].tolist()))
            mains_tarih = st.date_input("Mains Tarihi (Elektrik Kesilme)", value=datetime.now())
            mains_saat = st.time_input("Mains Saati", value=datetime.now().time())
        with f2:
            kesinti_tarih = st.date_input("Kesinti Tarihi (Saha Down)", value=datetime.now())
            kesinti_saat = st.time_input("Kesinti Saati (Saha Down)", value=datetime.now().time())
            enerji_saat_input = st.time_input("Enerji Geliş Saati (opsiyonel)", value=None)

        yorum = st.text_area("Yorum")
        submitted = st.form_submit_button("💾 Kaydet")

        if submitted:
            saha_row = db.get_saha_by_name(saha_adi)
            mains_dt = datetime.combine(mains_tarih, mains_saat)
            kesinti_dt = datetime.combine(kesinti_tarih, kesinti_saat)
            backup_dk = (kesinti_dt - mains_dt).total_seconds() / 60

            if enerji_saat_input:
                enerji_dt = datetime.combine(kesinti_tarih, enerji_saat_input)
                if enerji_dt < kesinti_dt:
                    enerji_dt += timedelta(days=1)
                kesinti_suresi_dk = (enerji_dt - kesinti_dt).total_seconds() / 60
                enerji_dt_str = enerji_dt.strftime("%Y-%m-%d %H:%M")
            else:
                enerji_dt_str = None
                kesinti_suresi_dk = None

            if backup_dk < 0:
                st.error("Kesinti saati, Mains saatinden önce olamaz.")
            else:
                db.insert_ariza_kaydi(
                    saha_id=saha_row["id"],
                    mains_saati=mains_dt.strftime("%Y-%m-%d %H:%M"),
                    kesinti_saati=kesinti_dt.strftime("%Y-%m-%d %H:%M"),
                    enerji_gelis_saati=enerji_dt_str,
                    backup_suresi_dk=round(backup_dk, 1),
                    kesinti_suresi_dk=round(kesinti_suresi_dk, 1) if kesinti_suresi_dk is not None else None,
                    yorum=yorum,
                )
                st.success(f"✅ {saha_adi} için arıza kaydı eklendi.")
                st.rerun()

    if st.button("🎲 Örnek Arıza Kayıtları Oluştur (Test için)"):
        from sample_data import generate_mock_ariza_kayitlari
        mock_df = generate_mock_ariza_kayitlari(sahalar, n=150)
        for _, row in mock_df.iterrows():
            db.insert_ariza_kaydi(
                saha_id=row["saha_id"], mains_saati=row["mains_saati"], kesinti_saati=row["kesinti_saati"],
                enerji_gelis_saati=row["enerji_gelis_saati"], backup_suresi_dk=row["backup_suresi_dk"],
                kesinti_suresi_dk=row["kesinti_suresi_dk"], yorum=row["yorum"],
            )
        st.success(f"{len(mock_df)} örnek kayıt eklendi.")
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Filtre & Grafik
# ---------------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
with c1:
    saha_secim = st.selectbox("Saha Filtresi", options=["(Tümü)"] + sorted(sahalar["placemark_adi"].tolist()), key="ariza_saha")
with c2:
    d_start = st.date_input("Başlangıç", value=datetime.now() - timedelta(days=30), key="ariza_start")
with c3:
    d_end = st.date_input("Bitiş", value=datetime.now(), key="ariza_end")

saha_filtre = None if saha_secim == "(Tümü)" else saha_secim
df_ariza = db.get_ariza_kayitlari(saha_filtre, str(d_start), str(d_end))

if df_ariza.empty:
    st.info("Seçilen filtreler için arıza kaydı bulunamadı. Yukarıdan 'Örnek Arıza Kayıtları Oluştur' ile test verisi ekleyebilirsiniz.")
else:
    df_ariza = df_ariza.copy()
    df_ariza["mains_dt"] = pd.to_datetime(df_ariza["mains_saati"])
    df_ariza["kesinti_dt"] = pd.to_datetime(df_ariza["kesinti_saati"])
    df_ariza["enerji_dt"] = pd.to_datetime(df_ariza["enerji_gelis_saati"], errors="coerce")
    df_ariza["gun"] = df_ariza["mains_dt"].dt.date.astype(str)

    def to_hour_frac(dt):
        return dt.hour + dt.minute / 60 + dt.second / 3600

    fig = go.Figure()

    # Yeşil mum: Mains -> Down (Backup/akü süresi)
    for _, r in df_ariza.iterrows():
        y0 = to_hour_frac(r["mains_dt"])
        y1 = to_hour_frac(r["kesinti_dt"])
        fig.add_trace(go.Scatter(
            x=[r["gun"], r["gun"]], y=[y0, y1], mode="lines",
            line=dict(color="rgb(39,174,96)", width=8),
            name="Backup (Akü) Süresi", showlegend=False,
            hovertext=f"{r['placemark_adi']}<br>Mains: {r['mains_saati']}<br>Down: {r['kesinti_saati']}<br>Backup: {r['backup_suresi_dk']} dk",
            hoverinfo="text",
        ))
        if pd.notna(r["enerji_dt"]):
            y2 = to_hour_frac(r["enerji_dt"])
            fig.add_trace(go.Scatter(
                x=[r["gun"], r["gun"]], y=[y1, y2], mode="lines",
                line=dict(color="rgb(192,57,43)", width=8),
                name="Outage (Kesinti) Süresi", showlegend=False,
                hovertext=f"{r['placemark_adi']}<br>Down: {r['kesinti_saati']}<br>Enerji: {r['enerji_gelis_saati']}<br>Kesinti: {r['kesinti_suresi_dk']} dk",
                hoverinfo="text",
            ))

    fig.update_layout(
        title="Arıza / Şebeke Zaman Çizelgesi (Yeşil: Backup | Kırmızı: Outage)",
        yaxis=dict(title="Saat (00:00 - 24:00)", range=[0, 24], dtick=2),
        xaxis=dict(title="Tarih"),
        height=550,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Metrikler
    metrikler = db.get_ariza_ozet_metrikleri(saha_filtre, str(d_start), str(d_end))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ortalama Backup Süresi", f"{metrikler['ortalama_backup_dk']} dk")
    m2.metric("Ortalama Kesik Kalma Süresi", f"{metrikler['ortalama_kesinti_dk']} dk")
    m3.metric("Toplam Kesinti Saati", f"{metrikler['toplam_kesinti_saat']} saat")
    m4.metric("Kayıt Sayısı", metrikler["kayit_sayisi"])

    st.dataframe(
        df_ariza[["placemark_adi", "il", "ilce", "mains_saati", "kesinti_saati", "enerji_gelis_saati", "backup_suresi_dk", "kesinti_suresi_dk", "yorum"]].rename(
            columns={"placemark_adi": "Saha", "il": "İl", "ilce": "İlçe", "mains_saati": "Mains Saati",
                     "kesinti_saati": "Kesinti Saati", "enerji_gelis_saati": "Enerji Geliş", "backup_suresi_dk": "Backup (dk)",
                     "kesinti_suresi_dk": "Kesinti (dk)", "yorum": "Yorum"}
        ), use_container_width=True, hide_index=True,
    )

    dl1, dl2 = st.columns(2)
    with dl1:
        buf = pd.io.common.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_ariza.to_excel(writer, index=False, sheet_name="Ariza Kayitlari")
        st.download_button("⬇️ Excel İndir", data=buf.getvalue(), file_name="ariza_kayitlari.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with dl2:
        img = report_utils.ariza_ozet_jpg(metrikler, saha_adi=saha_filtre)
        st.download_button("⬇️ Özet Raporu JPG İndir", data=report_utils.image_to_bytes(img), file_name="ariza_ozet.jpg", mime="image/jpeg")

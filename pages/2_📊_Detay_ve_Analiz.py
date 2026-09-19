"""
Ekran 2: 📊 Detay ve Analiz Ekranı
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import database as db
import report_utils

st.set_page_config(page_title="Detay ve Analiz", page_icon="📊", layout="wide")
st.title("📊 Detay ve Analiz Ekranı")

# ---------------------------------------------------------------------------
# Hızlı Özet (Top 5)
# ---------------------------------------------------------------------------
st.subheader("⭐ Hızlı Özet")

c1, c2 = st.columns(2)
with c1:
    baslangic_tarih = st.date_input("Başlangıç Tarihi", value=datetime.now() - timedelta(days=30), key="ozet_start")
with c2:
    bitis_tarih = st.date_input("Bitiş Tarihi", value=datetime.now(), key="ozet_end")

top_saha, top_il, top_ilce = db.get_top_n_stats(5, str(baslangic_tarih), str(bitis_tarih))

k1, k2, k3 = st.columns(3)
with k1:
    st.markdown("**🏭 Top 5 Saha**")
    if top_saha.empty:
        st.caption("Veri bulunmuyor")
    else:
        st.dataframe(top_saha.rename(columns={"placemark_adi": "Saha", "kesinti_sayisi": "Kesinti"}), hide_index=True, use_container_width=True)
with k2:
    st.markdown("**🏙️ Top 5 İl**")
    if top_il.empty:
        st.caption("Veri bulunmuyor")
    else:
        st.dataframe(top_il.rename(columns={"il": "İl", "kesinti_sayisi": "Kesinti"}), hide_index=True, use_container_width=True)
with k3:
    st.markdown("**📍 Top 5 İlçe**")
    if top_ilce.empty:
        st.caption("Veri bulunmuyor")
    else:
        st.dataframe(top_ilce.rename(columns={"ilce": "İlçe", "kesinti_sayisi": "Kesinti"}), hide_index=True, use_container_width=True)

if st.button("🖼️ Özet Raporu JPG Olarak İndir"):
    img = report_utils.analiz_ozet_jpg(top_saha, top_il, top_ilce)
    st.image(img)
    st.download_button("⬇️ İndir", data=report_utils.image_to_bytes(img), file_name="analiz_ozeti.jpg", mime="image/jpeg")

st.divider()

# ---------------------------------------------------------------------------
# Arama ve Zaman Filtresi + Mum Grafik
# ---------------------------------------------------------------------------
st.subheader("🔍 Saha Arama ve Kesinti Geçmişi (Mum Grafik)")

sahalar = db.get_all_sahalar()
saha_secim = st.selectbox("Saha Seçin", options=["(Tümü)"] + sorted(sahalar["placemark_adi"].tolist()))

c1, c2 = st.columns(2)
with c1:
    d_start = st.date_input("Tarih Aralığı Başlangıç", value=datetime.now() - timedelta(days=60), key="mum_start")
with c2:
    d_end = st.date_input("Tarih Aralığı Bitiş", value=datetime.now() + timedelta(days=7), key="mum_end")

if saha_secim != "(Tümü)":
    df_hist = db.get_kesinti_history_for_saha(saha_secim, str(d_start), str(d_end))
else:
    df_hist = db.get_kesintiler(gun_sayisi=(d_end - d_start).days if (d_end - d_start).days > 0 else 1)

if df_hist.empty:
    st.info("Bu filtreler için kesinti geçmişi bulunamadı. (Örnek veride sınırlı sayıda kayıt olabilir.)")
else:
    df_hist = df_hist.copy()
    df_hist["baslangic_dt"] = pd.to_datetime(df_hist["baslangic"], errors="coerce")
    df_hist["bitis_dt"] = pd.to_datetime(df_hist["bitis"], errors="coerce")
    df_hist = df_hist.dropna(subset=["baslangic_dt", "bitis_dt"]).sort_values("baslangic_dt")

    # Plotly Candlestick: open=baslangic saati, close=bitis saati, high/low aynı gün içi aralık
    # Kesinti süresini "mum gövdesi" olarak temsil ediyoruz (open < close ise yeşil, aksi kırmızı gösterilecek şekilde)
    df_hist["sure_saat"] = (df_hist["bitis_dt"] - df_hist["baslangic_dt"]).dt.total_seconds() / 3600
    df_hist["open_saat"] = df_hist["baslangic_dt"].dt.hour + df_hist["baslangic_dt"].dt.minute / 60
    df_hist["close_saat"] = df_hist["open_saat"] + df_hist["sure_saat"]
    df_hist["gun"] = df_hist["baslangic_dt"].dt.date.astype(str)

    fig = go.Figure(data=[go.Candlestick(
        x=df_hist["gun"],
        open=df_hist["open_saat"],
        high=df_hist["close_saat"] + 0.3,
        low=df_hist["open_saat"] - 0.3,
        close=df_hist["close_saat"],
        increasing_line_color="rgb(230,126,34)",
        decreasing_line_color="rgb(230,126,34)",
        name="Kesinti Süresi",
    )])
    fig.update_layout(
        title=f"Kesinti Zaman Dilimleri — {saha_secim}",
        yaxis_title="Saat (0-24)", xaxis_title="Tarih",
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        df_hist[["gun", "il", "ilce", "baslangic", "bitis", "is_aciklamasi"]].rename(
            columns={"gun": "Tarih", "il": "İl", "ilce": "İlçe", "baslangic": "Başlangıç", "bitis": "Bitiş", "is_aciklamasi": "Açıklama"}
        ),
        use_container_width=True, hide_index=True,
    )

    cdl1, cdl2 = st.columns(2)
    with cdl1:
        excel_buf = pd.io.common.BytesIO()
        with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
            df_hist.to_excel(writer, index=False, sheet_name="Kesinti Geçmişi")
        st.download_button("⬇️ Excel İndir", data=excel_buf.getvalue(), file_name="kesinti_gecmisi.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with cdl2:
        img = report_utils.tablo_jpg(
            df_hist.rename(columns={"gun": "Tarih", "il": "İl", "ilce": "İlçe", "baslangic": "Başlangıç", "bitis": "Bitiş"}),
            title=f"Kesinti Geçmişi — {saha_secim}",
            columns=["Tarih", "İl", "İlçe", "Başlangıç", "Bitiş"],
        )
        st.download_button("⬇️ JPG İndir", data=report_utils.image_to_bytes(img), file_name="kesinti_gecmisi.jpg", mime="image/jpeg")

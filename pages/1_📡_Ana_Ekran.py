"""
Ekran 1: 📡 Ana Ekran - YEDAŞ Canlı Kesintiler & Anlık Takip
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import database as db
import yedas_client
import geo_utils
import report_utils

st.set_page_config(page_title="Ana Ekran", page_icon="📡", layout="wide")
st.title("📡 YEDAŞ Canlı Kesintiler & Anlık Takip")

# ---------------------------------------------------------------------------
# Filtreler
# ---------------------------------------------------------------------------
c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
with c1:
    daily = st.button("📅 Daily (Günlük)", use_container_width=True)
with c2:
    three_day = st.button("📅 3 Günlük", use_container_width=True)
with c3:
    seven_day = st.button("📅 7 Günlük", use_container_width=True)
with c4:
    if st.button("🔄 Şimdi Yenile (Cache Temizle)"):
        yedas_client.fetch_yedas_outages.clear()
        st.rerun()

if "gun_filtresi" not in st.session_state:
    st.session_state.gun_filtresi = 1
if daily:
    st.session_state.gun_filtresi = 1
if three_day:
    st.session_state.gun_filtresi = 3
if seven_day:
    st.session_state.gun_filtresi = 7

gun = st.session_state.gun_filtresi
st.caption(f"Görüntülenen aralık: **{gun} gün** | Veri 5 dakikada bir otomatik güncellenir (`st.cache_data ttl=300`)")

# ---------------------------------------------------------------------------
# Veri çekme + spatial join
# ---------------------------------------------------------------------------
with st.spinner("YEDAŞ kesinti verisi çekiliyor..."):
    df_outages_raw = yedas_client.fetch_yedas_outages(use_mock=yedas_client.USE_MOCK_DATA_DEFAULT)

df_outages = yedas_client.filter_by_range(df_outages_raw, gun)
df_sahalar = db.get_all_sahalar()

if df_outages.empty:
    st.success("✅ Seçilen aralıkta planlı kesinti bulunmuyor.")
    st.stop()

with st.spinner("GeoPandas R-Tree spatial join ile etkilenen sahalar hesaplanıyor..."):
    matched = geo_utils.match_sahalar_with_outages(df_sahalar, df_outages)

etkilenen_sayisi = matched["placemark_adi"].nunique() if not matched.empty else 0

m1, m2, m3 = st.columns(3)
m1.metric("⚡ Kesinti Sayısı", len(df_outages))
m2.metric("📡 Etkilenen Saha", etkilenen_sayisi)
m3.metric("🕐 Toplam Saha", len(df_sahalar))

# ---------------------------------------------------------------------------
# Harita
# ---------------------------------------------------------------------------
st.subheader("🗺️ Harita — Turuncu: Kesinti Alanları | Mavi: GSM Sahaları")

fig = go.Figure()

# Kesinti poligonları (turuncu)
from shapely import wkt as shapely_wkt
for _, row in df_outages.iterrows():
    try:
        poly = shapely_wkt.loads(row["polygon_wkt"])
        xs, ys = poly.exterior.xy
        fig.add_trace(go.Scattermapbox(
            lon=list(xs), lat=list(ys), mode="lines", fill="toself",
            fillcolor="rgba(230,126,34,0.35)", line=dict(color="rgb(230,126,34)", width=2),
            name=f"{row['il']}/{row['ilce']}",
            hovertext=f"{row['il']}/{row['ilce']}<br>{row['baslangic']} - {row['bitis']}<br>{row['aciklama']}",
            hoverinfo="text", showlegend=False,
        ))
    except Exception:
        continue

# Tüm sahalar (açık mavi, küçük)
fig.add_trace(go.Scattermapbox(
    lon=df_sahalar["longitude"], lat=df_sahalar["latitude"], mode="markers",
    marker=dict(size=5, color="rgba(52,152,219,0.35)"),
    name="Tüm Sahalar", hovertext=df_sahalar["placemark_adi"], hoverinfo="text",
))

# Etkilenen sahalar (koyu mavi, büyük)
if not matched.empty:
    fig.add_trace(go.Scattermapbox(
        lon=matched["longitude"], lat=matched["latitude"], mode="markers",
        marker=dict(size=11, color="rgb(21,67,96)"),
        name="Etkilenen Sahalar",
        hovertext=matched["placemark_adi"] + " | " + matched["kesinti_il"].astype(str) + "/" + matched["kesinti_ilce"].astype(str),
        hoverinfo="text",
    ))

center_lat = df_sahalar["latitude"].mean()
center_lon = df_sahalar["longitude"].mean()
fig.update_layout(
    mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=7),
    margin=dict(l=0, r=0, t=0, b=0), height=550,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Liste & Detay
# ---------------------------------------------------------------------------
st.subheader("📋 Kesinti Listesi ve Etkilenen Sahalar")

for idx, outage in df_outages.reset_index(drop=True).iterrows():
    saha_list = matched[matched["kesinti_yedas_ref"] == outage.get("yedas_ref")]["placemark_adi"].tolist() if not matched.empty and "kesinti_yedas_ref" in matched.columns else []
    with st.expander(f"⚡ {outage['il']} / {outage['ilce']} — {outage['baslangic']} → {outage['bitis']}  ({len(saha_list)} saha etkileniyor)"):
        cc1, cc2 = st.columns([2, 1])
        with cc1:
            st.write(f"**İş Açıklaması:** {outage.get('aciklama', '-')}")
            st.write(f"**Referans:** {outage.get('yedas_ref', '-')}")
            if saha_list:
                st.write("**Etkilenen Sahalar:**")
                st.dataframe(pd.DataFrame({"Saha Adı": saha_list}), use_container_width=True, hide_index=True)
            else:
                st.caption("Bu kesinti alanında GSM sahası bulunmuyor.")
        with cc2:
            if st.button("🖼️ Görsel Kart Oluştur (JPG)", key=f"jpg_{idx}"):
                saha_adi_str = ", ".join(saha_list[:3]) + (f" +{len(saha_list)-3} daha" if len(saha_list) > 3 else "") if saha_list else "Etkilenen saha yok"
                img = report_utils.kesinti_karti_jpg(
                    saha_adi=saha_adi_str, il=outage["il"], ilce=outage["ilce"],
                    baslangic=outage["baslangic"], bitis=outage["bitis"], aciklama=outage.get("aciklama", "")
                )
                st.image(img, caption="Önizleme")
                st.download_button(
                    "⬇️ JPG İndir", data=report_utils.image_to_bytes(img),
                    file_name=f"kesinti_{outage['il']}_{outage['ilce']}.jpg", mime="image/jpeg", key=f"dl_{idx}"
                )

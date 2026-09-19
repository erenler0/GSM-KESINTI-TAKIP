"""
Ekran 3: 🗺️ Sahalar & İlçe Merkezleri (Mesafe & Rota)
Kapsam: Samsun, Sinop, Ordu, Amasya, Tokat, Çorum
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import database as db
import geo_utils
import osrm_client
import report_utils

st.set_page_config(page_title="Sahalar & Mesafe", page_icon="🗺️", layout="wide")
st.title("🗺️ Sahalar & İlçe Merkezleri — Mesafe & Rota")

KAPSAM_ILLER = ["Samsun", "Sinop", "Ordu", "Amasya", "Tokat", "Çorum"]

sahalar = db.get_all_sahalar()
merkezler = db.get_all_ilce_merkezleri()
sahalar = sahalar[sahalar["il"].isin(KAPSAM_ILLER)] if "il" in sahalar.columns else sahalar

# ---------------------------------------------------------------------------
# Filtreler
# ---------------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
with c1:
    il_filtre = st.multiselect("İl Filtresi", options=KAPSAM_ILLER, default=KAPSAM_ILLER)
with c2:
    ilce_secenekleri = sorted(sahalar[sahalar["il"].isin(il_filtre)]["ilce"].dropna().unique().tolist()) if not sahalar.empty else []
    ilce_filtre = st.multiselect("İlçe Filtresi", options=ilce_secenekleri, default=[])
with c3:
    arama = st.text_input("🔎 Saha Adı Ara")

df_f = sahalar[sahalar["il"].isin(il_filtre)]
if ilce_filtre:
    df_f = df_f[df_f["ilce"].isin(ilce_filtre)]
if arama:
    df_f = df_f[df_f["placemark_adi"].str.contains(arama, case=False, na=False)]

st.caption(f"{len(df_f)} saha listeleniyor (toplam kapsam: {len(sahalar)} saha)")

# ---------------------------------------------------------------------------
# Mesafe/Süre hesabı (cache-first, OSRM)
# ---------------------------------------------------------------------------
if st.button("📏 Görüntülenen Sahalar için Mesafe/Süre Hesapla (OSRM)"):
    progress = st.progress(0, text="Hesaplanıyor...")

    def cb(i, total):
        progress.progress(i / total, text=f"{i}/{total} saha işlendi")

    result_df = osrm_client.bulk_compute_routes(df_f, merkezler, progress_callback=cb)
    progress.empty()
    st.session_state["mesafe_sonuc"] = result_df
    st.success(f"{len(result_df)} saha için mesafe/süre hesaplandı ve cache'e kaydedildi.")

# ---------------------------------------------------------------------------
# Harita
# ---------------------------------------------------------------------------
st.subheader("🗺️ Harita — Mavi: GSM Sahaları | Kırmızı: İlçe Merkezleri")

fig = go.Figure()
fig.add_trace(go.Scattermapbox(
    lon=df_f["longitude"], lat=df_f["latitude"], mode="markers",
    marker=dict(size=8, color="rgb(41,128,185)"),
    name="GSM Sahaları",
    hovertext=df_f.apply(lambda r: f"{r['placemark_adi']}<br>{r.get('il','-')} / {r.get('ilce','-')}", axis=1),
    hoverinfo="text",
))
fig.add_trace(go.Scattermapbox(
    lon=merkezler["longitude"], lat=merkezler["latitude"], mode="markers",
    marker=dict(size=13, color="rgb(192,57,43)", symbol="circle"),
    name="İlçe Merkezleri",
    hovertext=merkezler["isim"] + " (" + merkezler["il"] + ")",
    hoverinfo="text",
))

# Rota çizgileri (eğer hesaplanmışsa)
if "mesafe_sonuc" in st.session_state and not st.session_state["mesafe_sonuc"].empty:
    res = st.session_state["mesafe_sonuc"]
    merkez_lookup = merkezler.set_index("id")
    for _, r in res.iterrows():
        saha_row = df_f[df_f["id"] == r["saha_id"]]
        if saha_row.empty or r["ilce_merkezi_id"] not in merkez_lookup.index:
            continue
        s = saha_row.iloc[0]
        mk = merkez_lookup.loc[r["ilce_merkezi_id"]]
        fig.add_trace(go.Scattermapbox(
            lon=[s["longitude"], mk["longitude"]], lat=[s["latitude"], mk["latitude"]],
            mode="lines", line=dict(width=1, color="rgba(100,100,100,0.4)"),
            showlegend=False, hoverinfo="skip",
        ))

if not df_f.empty:
    center_lat, center_lon = df_f["latitude"].mean(), df_f["longitude"].mean()
else:
    center_lat, center_lon = 40.9, 36.3

fig.update_layout(
    mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=7),
    margin=dict(l=0, r=0, t=0, b=0), height=550,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Tekil Atama Override (Admin dışı kullanıcı için sadece görüntüleme)
# ---------------------------------------------------------------------------
st.subheader("📋 Saha Listesi (Alfabetik)")

if "mesafe_sonuc" in st.session_state and not st.session_state["mesafe_sonuc"].empty:
    tablo = st.session_state["mesafe_sonuc"].copy()
    tablo = tablo[tablo["saha_id"].isin(df_f["id"])].sort_values("placemark_adi")
    tablo_show = tablo.rename(columns={
        "placemark_adi": "Saha Adı", "ilce_merkezi_isim": "Merkez",
        "mesafe_km": "Mesafe (km)", "sure_dk": "Süre (dk)",
    })[["Saha Adı", "Merkez", "Mesafe (km)", "Süre (dk)"]]
    st.dataframe(tablo_show, use_container_width=True, hide_index=True)

    dl1, dl2 = st.columns(2)
    with dl1:
        buf = pd.io.common.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            tablo_show.to_excel(writer, index=False, sheet_name="Mesafe Listesi")
        st.download_button("⬇️ Excel İndir", data=buf.getvalue(), file_name="saha_mesafe_listesi.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with dl2:
        img = report_utils.tablo_jpg(tablo_show, title="Saha - İlçe Merkezi Mesafe Listesi",
                                      columns=["Saha Adı", "Merkez", "Mesafe (km)", "Süre (dk)"])
        st.download_button("⬇️ JPG İndir", data=report_utils.image_to_bytes(img), file_name="saha_mesafe_listesi.jpg", mime="image/jpeg")
else:
    basit_liste = df_f[["placemark_adi", "il", "ilce"]].sort_values("placemark_adi").rename(
        columns={"placemark_adi": "Saha Adı", "il": "İl", "ilce": "İlçe"}
    )
    st.dataframe(basit_liste, use_container_width=True, hide_index=True)
    st.caption("Mesafe/süre bilgisi için yukarıdaki '📏 Mesafe/Süre Hesapla' butonunu kullanın.")

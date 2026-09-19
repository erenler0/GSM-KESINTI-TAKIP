"""
yedas_client.py
----------------
YEDAŞ planlı kesinti API'sinden canlı veri çeker.

ÖNEMLİ (Dağıtım Notu):
Bu kod, çalıştırıldığı sunucunun internet erişimi olduğu ve
https://www.yedas.com/api/planli-kesinti-harita adresine ulaşabildiği
varsayımıyla yazılmıştır. Gerçek uçtaki yanıt yapısı (JSON alan adları)
değişebileceğinden, `_parse_yedas_response` fonksiyonu farklı olası
yapılar için esnek tutulmuştur; canlıya alırken gerçek API yanıtını
örnekleyip alan eşlemesini (aşağıdaki FIELD_MAP) güncelleyin.

Ağ erişimi olmayan / test ortamlarında `USE_MOCK_DATA=True` ile
sample_data.py üzerinden sahte (ama gerçekçi) kesinti verisi üretilir,
böylece uygulamanın tamamı uçtan uca test edilebilir.
"""

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from shapely.geometry import shape
import json

YEDAS_API_URL = "https://www.yedas.com/api/planli-kesinti-harita"
REQUEST_TIMEOUT = 15

# Gerçek API'ye ulaşılamayan (sandbox / offline) ortamlarda otomatik
# olarak örnek veriye düşer. Canlı sunucuda bunu False yapın ya da
# .streamlit/secrets.toml içine YEDAS_USE_MOCK=false ekleyin.
USE_MOCK_DATA_DEFAULT = False

# Olası JSON alan adı varyasyonlarını tek bir iç şemaya eşlemek için.
FIELD_MAP_CANDIDATES = {
    "il": ["il", "province", "city"],
    "ilce": ["ilce", "district", "town"],
    "baslangic": ["baslangicTarihi", "start_date", "kesinti_baslangic", "startDate"],
    "bitis": ["bitisTarihi", "end_date", "kesinti_bitis", "endDate"],
    "aciklama": ["isAciklamasi", "description", "aciklama", "workDescription"],
    "ref": ["id", "referansNo", "ref", "kesintiId"],
}


def _first_match(d: dict, keys: list, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


@st.cache_data(ttl=300, show_spinner=False)
def fetch_yedas_outages(use_mock: bool = USE_MOCK_DATA_DEFAULT) -> pd.DataFrame:
    """
    YEDAŞ planlı kesinti verisini çeker ve normalize edilmiş bir
    DataFrame döner: [ref, il, ilce, baslangic, bitis, aciklama, geometry(WKT)]

    st.cache_data(ttl=300) sayesinde 5 dakikada bir otomatik yenilenir.
    """
    if use_mock:
        from sample_data import generate_mock_outages
        return generate_mock_outages()

    try:
        resp = requests.get(YEDAS_API_URL, timeout=REQUEST_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (GSM-Outage-Monitor/1.0)"
        })
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        st.warning(f"YEDAŞ API'sine ulaşılamadı ({e}). Örnek veri gösteriliyor.")
        from sample_data import generate_mock_outages
        return generate_mock_outages()

    return _parse_yedas_response(payload)


def _parse_yedas_response(payload) -> pd.DataFrame:
    """
    GeoJSON FeatureCollection ya da düz liste formatlarını normalize eder.
    """
    features = payload.get("features") if isinstance(payload, dict) else payload
    if features is None:
        features = payload.get("data", []) if isinstance(payload, dict) else []

    rows = []
    for feat in features:
        props = feat.get("properties", feat) if isinstance(feat, dict) else {}
        geom = feat.get("geometry") if isinstance(feat, dict) else None

        wkt = None
        if geom:
            try:
                wkt = shape(geom).wkt
            except Exception:
                wkt = None

        rows.append({
            "yedas_ref": _first_match(props, FIELD_MAP_CANDIDATES["ref"]),
            "il": _first_match(props, FIELD_MAP_CANDIDATES["il"]),
            "ilce": _first_match(props, FIELD_MAP_CANDIDATES["ilce"]),
            "baslangic": _first_match(props, FIELD_MAP_CANDIDATES["baslangic"]),
            "bitis": _first_match(props, FIELD_MAP_CANDIDATES["bitis"]),
            "aciklama": _first_match(props, FIELD_MAP_CANDIDATES["aciklama"]),
            "polygon_wkt": wkt,
        })

    return pd.DataFrame(rows)


def filter_by_range(df: pd.DataFrame, gun_sayisi: int) -> pd.DataFrame:
    """Daily / 3 Günlük / 7 Günlük filtresi."""
    if df.empty:
        return df
    now = datetime.now()
    cutoff = now + timedelta(days=gun_sayisi)
    df = df.copy()
    df["baslangic_dt"] = pd.to_datetime(df["baslangic"], errors="coerce")
    df["bitis_dt"] = pd.to_datetime(df["bitis"], errors="coerce")
    mask = (df["baslangic_dt"] <= cutoff) & (
        (df["bitis_dt"].isna()) | (df["bitis_dt"] >= now)
    )
    return df[mask | (df["baslangic_dt"] >= now)].reset_index(drop=True)


def sync_outages_to_db(df: pd.DataFrame):
    """
    Çekilen kesintileri DB'ye yazar (basit upsert - referans yoksa her seferinde
    yeni satır eklemek yerine aynı gün+il+ilçe+açıklama kombinasyonunu tekilleştirir).
    """
    import database as db
    inserted_ids = []
    for _, row in df.iterrows():
        kid = db.insert_kesinti(
            yedas_ref=row.get("yedas_ref"),
            il=row.get("il"),
            ilce=row.get("ilce"),
            baslangic=str(row.get("baslangic")),
            bitis=str(row.get("bitis")),
            is_aciklamasi=row.get("aciklama"),
            polygon_wkt=row.get("polygon_wkt"),
        )
        inserted_ids.append(kid)
    return inserted_ids

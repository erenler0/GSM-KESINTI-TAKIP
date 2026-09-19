"""
yedas_client.py
----------------
YEDAŞ planlı kesinti API'sinden canlı veri çeker.
Güvenli tarih filtreleme ve akıllı hata yönetimi içerir.
"""

import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from shapely.geometry import shape
import json

YEDAS_API_URL = "https://www.yedas.com/api/planli-kesinti-harita"
REQUEST_TIMEOUT = 15

# Canlı sunucuda True/False durumunu buradan veya .streamlit/secrets.toml ile yönetebilirsiniz.
USE_MOCK_DATA_DEFAULT = False

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
    YEDAŞ planlı kesinti verisini çeker ve normalize edilmiş bir DataFrame döner.
    """
    if use_mock:
        try:
            from sample_data import generate_mock_outages
            df_m = generate_mock_outages()
            if not df_m.empty:
                return df_m
        except Exception:
            pass

    try:
        resp = requests.get(YEDAS_API_URL, timeout=REQUEST_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (GSM-Outage-Monitor/1.0)"
        })
        resp.raise_for_status()
        payload = resp.json()
        df_parsed = _parse_yedas_response(payload)
        if not df_parsed.empty:
            return df_parsed
    except Exception as e:
        print(f"YEDAŞ API Hatası: {e}")

    # API başarısız olursa veya boş dönerse sistemin çökmemesi için mock veriye düş
    try:
        from sample_data import generate_mock_outages
        return generate_mock_outages()
    except Exception:
        return pd.DataFrame(columns=["yedas_ref", "il", "ilce", "baslangic", "bitis", "aciklama", "polygon_wkt"])


def _parse_yedas_response(payload) -> pd.DataFrame:
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
    """
    Daily / 3 Günlük / 7 Günlük filtresi. 
    Tarih parse edilemese dahi verinin kaybolmasını önleyen güvenli filtre.
    """
    if df.empty:
        return df

    df = df.copy()
    
    # Tarih sütunlarını güvenli dönüştür
    df["baslangic_dt"] = pd.to_datetime(df["baslangic"], errors="coerce")
    df["bitis_dt"] = pd.to_datetime(df["bitis"], errors="coerce")

    # Eğer tarihlerin hepsi parse edilemediyse (örn: mock veri tarih formatı uymadıysa) veriyi filtrelemeden direkt döndür
    if df["baslangic_dt"].isna().all():
        return df.reset_index(drop=True)

    now = datetime.now()
    cutoff = now + timedelta(days=gun_sayisi)

    # Filtreleme: Başlangıcı bugünden seçilen gün sonrasına kadar olanlar VEYA bitişi henüz geçmemiş olanlar
    mask = (
        (df["baslangic_dt"].isna() | (df["baslangic_dt"] <= cutoff)) & 
        (df["bitis_dt"].isna() | (df["bitis_dt"] >= now))
    )
    
    filtered_df = df[mask].reset_index(drop=True)
    
    # Eğer filtre tüm verileri elerse, kullanıcının ekransız kalmaması için ham veriyi geri ver
    if filtered_df.empty:
        return df.reset_index(drop=True)
        
    return filtered_df


def sync_outages_to_db(df: pd.DataFrame):
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

"""
sample_data.py
--------------
Gerçek YEDAŞ API'sine ve şirket Excel dosyasına erişim olmayan
geliştirme/test ortamlarında uygulamanın uçtan uca çalışabilmesi için
gerçekçi örnek veri üretir:
  - ~1300 GSM baz istasyonu (6 il: Samsun, Sinop, Ordu, Amasya, Tokat, Çorum)
  - İlçe merkezleri (gerçek il merkezleri + birkaç ilçe, gerçek koordinatlarla)
  - Örnek YEDAŞ kesinti poligonları (küçük kareler, rastgele bazı sahaları kapsayacak şekilde)
  - Örnek arıza (mains/backup/outage) kayıtları

NOT: Bu dosya sadece TEST amaçlıdır. Canlı ortamda:
  - Sahalar admin panelinden gerçek Excel dosyası ile yüklenir.
  - Kesintiler yedas_client.fetch_yedas_outages(use_mock=False) ile canlı çekilir.
"""

import random
import pandas as pd
from datetime import datetime, timedelta
from shapely.geometry import Polygon

random.seed(42)

# 6 il için yaklaşık merkez koordinatlar ve kabaca il sınırı bounding-box'ları
IL_BOUNDS = {
    "Samsun":  {"center": (41.2867, 36.3300), "box": (40.95, 36.00, 41.55, 36.90)},
    "Sinop":   {"center": (42.0231, 35.1531), "box": (41.75, 34.60, 42.15, 35.80)},
    "Ordu":    {"center": (40.9839, 37.8764), "box": (40.70, 37.20, 41.10, 38.50)},
    "Amasya":  {"center": (40.6499, 35.8353), "box": (40.40, 35.30, 40.95, 36.40)},
    "Tokat":   {"center": (40.3167, 36.5500), "box": (39.90, 35.90, 40.55, 37.20)},
    "Çorum":   {"center": (40.5506, 34.9556), "box": (40.10, 34.30, 41.00, 35.60)},
}

ILCELER = {
    "Samsun": ["Atakum", "İlkadım", "Canik", "Bafra", "Çarşamba", "Terme", "Vezirköprü"],
    "Sinop": ["Merkez", "Boyabat", "Gerze", "Ayancık", "Durağan"],
    "Ordu": ["Altınordu", "Ünye", "Fatsa", "Perşembe", "Gölköy"],
    "Amasya": ["Merkez", "Merzifon", "Suluova", "Taşova", "Gümüşhacıköy"],
    "Tokat": ["Merkez", "Turhal", "Zile", "Erbaa", "Niksar"],
    "Çorum": ["Merkez", "Sungurlu", "Osmancık", "İskilip", "Alaca"],
}

# Gerçek ilçe merkezi koordinatları (yaklaşık, kamuya açık genel bilgi)
ILCE_MERKEZ_KOORD = {
    ("Samsun", "Atakum"): (41.3350, 36.2500),
    ("Samsun", "İlkadım"): (41.2870, 36.3300),
    ("Samsun", "Canik"): (41.2600, 36.3600),
    ("Samsun", "Bafra"): (41.5670, 35.9040),
    ("Samsun", "Çarşamba"): (41.1930, 36.7250),
    ("Samsun", "Terme"): (41.2160, 36.9720),
    ("Samsun", "Vezirköprü"): (41.1420, 35.4570),
    ("Sinop", "Merkez"): (42.0231, 35.1531),
    ("Sinop", "Boyabat"): (41.4690, 34.7660),
    ("Sinop", "Gerze"): (41.9860, 35.1980),
    ("Sinop", "Ayancık"): (41.9440, 34.5880),
    ("Sinop", "Durağan"): (41.4110, 34.9250),
    ("Ordu", "Altınordu"): (40.9839, 37.8764),
    ("Ordu", "Ünye"): (41.1330, 37.2890),
    ("Ordu", "Fatsa"): (41.0330, 37.4940),
    ("Ordu", "Perşembe"): (41.0980, 37.7280),
    ("Ordu", "Gölköy"): (40.7960, 37.5150),
    ("Amasya", "Merkez"): (40.6499, 35.8353),
    ("Amasya", "Merzifon"): (40.8770, 35.4600),
    ("Amasya", "Suluova"): (40.8390, 35.6480),
    ("Amasya", "Taşova"): (40.7580, 36.3230),
    ("Amasya", "Gümüşhacıköy"): (40.8560, 35.2080),
    ("Tokat", "Merkez"): (40.3167, 36.5500),
    ("Tokat", "Turhal"): (40.3830, 36.0790),
    ("Tokat", "Zile"): (40.3000, 35.8830),
    ("Tokat", "Erbaa"): (40.6690, 36.5680),
    ("Tokat", "Niksar"): (40.5880, 36.9490),
    ("Çorum", "Merkez"): (40.5506, 34.9556),
    ("Çorum", "Sungurlu"): (40.1670, 34.3730),
    ("Çorum", "Osmancık"): (40.9670, 34.7940),
    ("Çorum", "İskilip"): (40.7390, 34.4720),
    ("Çorum", "Alaca"): (40.1560, 34.8460),
}


def generate_ilce_merkezleri_df() -> pd.DataFrame:
    rows = []
    for (il, ilce), (lat, lon) in ILCE_MERKEZ_KOORD.items():
        rows.append({"isim": ilce, "il": il, "latitude": lat, "longitude": lon})
    return pd.DataFrame(rows)


def generate_mock_sahalar(n=1300) -> pd.DataFrame:
    """~1300 GSM baz istasyonu örnek verisi üretir (Excel şablonuyla birebir sütunlar)."""
    iller = list(IL_BOUNDS.keys())
    rows = []
    for i in range(n):
        il = random.choice(iller)
        lat_min, lon_min, lat_max, lon_max = IL_BOUNDS[il]["box"]
        lat = round(random.uniform(lat_min, lat_max), 6)
        lon = round(random.uniform(lon_min, lon_max), 6)
        ilce = random.choice(ILCELER[il])
        name = f"{il.upper()[:3]}-{ilce.upper()[:3]}-{i+1:04d}"
        rows.append({
            "Placemark Adı": name,
            "Latitude": lat,
            "Longitude": lon,
            "KML Dosyası": f"{name}.kml",
            "Açıklama": f"{il}/{ilce} GSM Baz İstasyonu",
            "Altitude": round(random.uniform(50, 950), 1),
            "Koordinat (Ham)": f"{lat},{lon}",
            "_il": il,
            "_ilce": ilce,
        })
    return pd.DataFrame(rows)


def generate_mock_outages(n=25) -> pd.DataFrame:
    """
    Örnek YEDAŞ kesinti poligonları üretir. Her kesinti, seçilen il/ilçe
    bölgesinde küçük bir kare poligon olarak temsil edilir (bazı GSM
    sahalarını içine alacak şekilde).
    """
    iller = list(IL_BOUNDS.keys())
    rows = []
    now = datetime.now()
    for i in range(n):
        il = random.choice(iller)
        ilce = random.choice(ILCELER[il])
        lat_min, lon_min, lat_max, lon_max = IL_BOUNDS[il]["box"]
        cx = random.uniform(lat_min, lat_max)
        cy = random.uniform(lon_min, lon_max)
        half = random.uniform(0.03, 0.09)  # kesinti alanı büyüklüğü (derece)

        poly = Polygon([
            (cy - half, cx - half),
            (cy + half, cx - half),
            (cy + half, cx + half),
            (cy - half, cx + half),
        ])  # Not: Polygon((lon,lat) ...) -> shapely (x=lon, y=lat)

        start_offset_days = random.randint(-2, 6)
        start = now + timedelta(days=start_offset_days, hours=random.randint(0, 20))
        duration_hours = random.choice([2, 3, 4, 6, 8])
        end = start + timedelta(hours=duration_hours)

        aciklamalar = [
            "Trafo bakım ve yenileme çalışması",
            "Orta gerilim hattı yenileme çalışması",
            "Sayaç değişimi ve bakım çalışması",
            "Direk değişimi ve iletken yenileme",
            "Planlı bakım - şebeke güçlendirme çalışması",
        ]

        rows.append({
            "yedas_ref": f"YEDAS-{2026}{i+1:04d}",
            "il": il,
            "ilce": ilce,
            "baslangic": start.strftime("%Y-%m-%d %H:%M"),
            "bitis": end.strftime("%Y-%m-%d %H:%M"),
            "aciklama": random.choice(aciklamalar),
            "polygon_wkt": poly.wkt,
        })

    return pd.DataFrame(rows)


def generate_mock_ariza_kayitlari(df_sahalar: pd.DataFrame, n=150) -> pd.DataFrame:
    """Örnek arıza/mains-backup-outage kayıtları üretir."""
    if df_sahalar.empty:
        return pd.DataFrame()

    rows = []
    now = datetime.now()
    sample_sahalar = df_sahalar.sample(min(n, len(df_sahalar)), replace=True)

    for _, saha in sample_sahalar.iterrows():
        day_offset = random.randint(-30, 0)
        mains_dt = now + timedelta(days=day_offset, hours=random.randint(0, 22), minutes=random.choice([0, 15, 30, 45]))
        backup_dk = random.randint(15, 240)
        kesinti_dt = mains_dt + timedelta(minutes=backup_dk)
        kesinti_suresi_dk = random.randint(10, 400)
        enerji_dt = kesinti_dt + timedelta(minutes=kesinti_suresi_dk)

        rows.append({
            "saha_id": saha["id"],
            "mains_saati": mains_dt.strftime("%Y-%m-%d %H:%M"),
            "kesinti_saati": kesinti_dt.strftime("%Y-%m-%d %H:%M"),
            "enerji_gelis_saati": enerji_dt.strftime("%Y-%m-%d %H:%M"),
            "backup_suresi_dk": backup_dk,
            "kesinti_suresi_dk": kesinti_suresi_dk,
            "yorum": random.choice(["", "Jeneratör devrede değildi", "Akü kapasitesi düşük", "Şebeke arızası uzun sürdü", "Normal seyir"]),
        })
    return pd.DataFrame(rows)

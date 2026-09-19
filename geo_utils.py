"""
geo_utils.py
------------
GeoPandas / Shapely tabanlı mekansal (spatial) işlemler:
  - 1300 GSM sahasının, YEDAŞ kesinti poligonlarının İÇİNDE olup
    olmadığının R-Tree indeksli spatial join ile milisaniyeler
    içinde bulunması.
  - Sahadan en yakın ilçe merkezinin bulunması (nearest-neighbor).

GeoPandas'ın `sjoin` fonksiyonu, altyapıda Shapely/RTree spatial index
kullanır; bu sayede 1300 nokta x N poligon karşılaştırması,
naive O(n*m) döngüye göre çok daha hızlı çalışır.
"""

import geopandas as gpd
import pandas as pd
from shapely import wkt as shapely_wkt
from shapely.geometry import Point


def sahalar_to_geodataframe(df_sahalar: pd.DataFrame) -> gpd.GeoDataFrame:
    """Sahalar DataFrame'ini (latitude/longitude) GeoDataFrame'e çevirir."""
    geometry = [Point(xy) for xy in zip(df_sahalar["longitude"], df_sahalar["latitude"])]
    gdf = gpd.GeoDataFrame(df_sahalar.copy(), geometry=geometry, crs="EPSG:4326")
    return gdf


def kesintiler_to_geodataframe(df_kesinti: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Kesinti DataFrame'ini (polygon_wkt sütunu) GeoDataFrame'e çevirir.
    Geçersiz / boş WKT olan satırlar atlanır.
    """
    geoms = []
    valid_idx = []
    for idx, row in df_kesinti.iterrows():
        w = row.get("polygon_wkt")
        if not w or pd.isna(w):
            continue
        try:
            geoms.append(shapely_wkt.loads(w))
            valid_idx.append(idx)
        except Exception:
            continue
    if not geoms:
        return gpd.GeoDataFrame(columns=list(df_kesinti.columns) + ["geometry"], geometry="geometry", crs="EPSG:4326")
    sub = df_kesinti.loc[valid_idx].copy()
    return gpd.GeoDataFrame(sub, geometry=geoms, crs="EPSG:4326")


def match_sahalar_with_outages(df_sahalar: pd.DataFrame, df_kesinti: pd.DataFrame) -> pd.DataFrame:
    """
    Point-in-Polygon + R-Tree spatial join:
    Her kesinti poligonunun içinde kalan sahaları bulur.

    Dönüş: sahalar sütunları + kesinti sütunları (prefix: kesinti_) birleşik DataFrame.
    Eşleşme yoksa boş DataFrame döner.
    """
    if df_sahalar.empty or df_kesinti.empty:
        return pd.DataFrame()

    gdf_sahalar = sahalar_to_geodataframe(df_sahalar)
    gdf_kesinti = kesintiler_to_geodataframe(df_kesinti)

    if gdf_kesinti.empty:
        return pd.DataFrame()

    # predicate="within": saha noktası poligonun içinde mi? (R-Tree index ile hızlandırılmış)
    joined = gpd.sjoin(gdf_sahalar, gdf_kesinti, how="inner", predicate="within")

    # index_right -> kesinti tablosundaki orijinal index; kesinti sütunlarını prefix'le
    kesinti_cols = [c for c in df_kesinti.columns if c != "geometry"]
    rename_map = {c: f"kesinti_{c}" for c in kesinti_cols if c in joined.columns}
    joined = joined.rename(columns=rename_map)

    return joined.drop(columns=["geometry"], errors="ignore").reset_index(drop=True)


def find_nearest_ilce_merkezi(saha_lat, saha_lon, df_merkezler: pd.DataFrame):
    """
    Haversine mesafesine göre (kuş uçuşu, ön-seçim amaçlı) en yakın
    ilçe merkezini bulur. Gerçek yol mesafesi için osrm_client kullanılır;
    bu fonksiyon sadece "varsayılan atama" için hızlı bir ön belirleme yapar.
    """
    if df_merkezler.empty:
        return None

    from math import radians, sin, cos, sqrt, atan2

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 2 * R * atan2(sqrt(a), sqrt(1 - a))

    best_row = None
    best_dist = float("inf")
    for _, row in df_merkezler.iterrows():
        d = haversine(saha_lat, saha_lon, row["latitude"], row["longitude"])
        if d < best_dist:
            best_dist = d
            best_row = row

    return best_row, best_dist

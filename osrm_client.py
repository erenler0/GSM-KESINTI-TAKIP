"""
osrm_client.py
--------------
OSRM (Open Source Routing Machine) API üzerinden saha -> ilçe merkezi
gerçek araba yolu mesafesi (km) ve tahmini sürüş süresi (dk) hesaplar.

Varsayılan olarak halka açık demo sunucu kullanılır:
    http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}
Üretimde kendi barındırdığınız bir OSRM sunucusu (Türkiye .osm.pbf ile)
kullanmanız şiddetle önerilir; demo sunucu rate-limit uygulayabilir.

Sonuçlar SQLite (osrm_cache tablosu) üzerinde saklanır, böylece 1300 saha
için tekrar tekrar API çağrısı yapılmaz — sadece yeni eklenen sahalar veya
cache'i olmayan saha/merkez çiftleri için istek atılır.
"""

import requests
import pandas as pd
import database as db

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
REQUEST_TIMEOUT = 10


def get_route(saha_id, saha_lat, saha_lon, ilce_merkezi_id, ilce_lat, ilce_lon, force_refresh=False):
    """
    Cache-first: önce SQLite'a bakar, yoksa OSRM'e sorar ve cache'ler.
    Dönüş: dict {mesafe_km, sure_dk, route_geojson}
    """
    if not force_refresh:
        cached = db.get_osrm_cache(saha_id, ilce_merkezi_id)
        if cached and cached.get("mesafe_km") is not None:
            return cached

    url = f"{OSRM_BASE_URL}/{saha_lon},{saha_lat};{ilce_lon},{ilce_lat}"
    params = {"overview": "full", "geometries": "geojson"}

    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError(f"OSRM yanıtı geçersiz: {data.get('code')}")

        route = data["routes"][0]
        mesafe_km = round(route["distance"] / 1000.0, 2)
        sure_dk = round(route["duration"] / 60.0, 1)
        route_geojson = str(route["geometry"])

        db.set_osrm_cache(saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson)
        return {"mesafe_km": mesafe_km, "sure_dk": sure_dk, "route_geojson": route_geojson}

    except Exception as e:
        # OSRM'e ulaşılamıyorsa (offline sandbox dahil) kuş uçuşu mesafeden
        # kaba bir tahmin üretir, böylece uygulama akışı bozulmaz.
        from geo_utils import find_nearest_ilce_merkezi
        import pandas as pd
        fallback_df = pd.DataFrame([{"latitude": ilce_lat, "longitude": ilce_lon}])
        _, haversine_km = find_nearest_ilce_merkezi(saha_lat, saha_lon, fallback_df)
        # Karayolu genelde kuş uçuşundan ~%25-40 daha uzundur; kaba katsayı uygula
        est_km = round(haversine_km * 1.3, 2)
        est_dk = round(est_km / 45 * 60, 1)  # ortalama 45 km/s varsayımı
        db.set_osrm_cache(saha_id, ilce_merkezi_id, est_km, est_dk, None)
        return {"mesafe_km": est_km, "sure_dk": est_dk, "route_geojson": None, "estimated": True, "error": str(e)}


def bulk_compute_routes(df_sahalar, df_merkezler, progress_callback=None):
    """
    Atanmış (ilce_merkezi_id dolu) tüm sahalar için mesafe/süre hesaplar.
    Streamlit progress bar için progress_callback(i, total) çağrılabilir.
    """
    results = []
    total = len(df_sahalar)
    merkez_lookup = df_merkezler.set_index("id").to_dict("index")

    for i, (_, saha) in enumerate(df_sahalar.iterrows()):
        merkez_id = saha.get("ilce_merkezi_id")
        if merkez_id is None or pd.isna(merkez_id):
            continue
        merkez = merkez_lookup.get(int(merkez_id))
        if not merkez:
            continue

        r = get_route(
            saha["id"], saha["latitude"], saha["longitude"],
            int(merkez_id), merkez["latitude"], merkez["longitude"]
        )
        results.append({
            "saha_id": saha["id"],
            "placemark_adi": saha["placemark_adi"],
            "ilce_merkezi_id": int(merkez_id),
            "ilce_merkezi_isim": merkez["isim"],
            **r
        })
        if progress_callback:
            progress_callback(i + 1, total)

    return pd.DataFrame(results)

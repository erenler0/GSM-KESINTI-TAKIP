"""
database.py
-----------
Tüm SQLite veritabanı işlemleri burada toplanmıştır: şema oluşturma,
sahalar, ilçe merkezleri, kesinti kayıtları, arıza kayıtları ve
OSRM mesafe/süre cache tablosu.

Tek bir SQLite dosyası kullanılır: data/yedas_app.db
"""

import sqlite3
import os
import json
import urllib.request
import pandas as pd
from datetime import datetime
from contextlib import contextmanager

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "yedas_app.db")

os.makedirs(DB_DIR, exist_ok=True)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Uygulama ilk açıldığında tüm tabloları oluşturur (varsa dokunmaz)."""
    with get_conn() as conn:
        c = conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS sahalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placemark_adi TEXT NOT NULL UNIQUE,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            kml_dosyasi TEXT,
            aciklama TEXT,
            altitude REAL,
            koordinat_ham TEXT,
            il TEXT,
            ilce TEXT,
            ilce_merkezi_id INTEGER,
            manuel_atama INTEGER DEFAULT 0,
            aktif INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ilce_merkezi_id) REFERENCES ilce_merkezleri(id) ON DELETE SET NULL
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ilce_merkezleri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isim TEXT NOT NULL,
            il TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(isim, il)
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS osrm_cache (
            saha_id INTEGER NOT NULL,
            ilce_merkezi_id INTEGER NOT NULL,
            mesafe_km REAL,
            sure_dk REAL,
            route_geojson TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (saha_id, ilce_merkezi_id),
            FOREIGN KEY (saha_id) REFERENCES sahalar(id) ON DELETE CASCADE,
            FOREIGN KEY (ilce_merkezi_id) REFERENCES ilce_merkezleri(id) ON DELETE CASCADE
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS kesintiler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            yedas_ref TEXT,
            il TEXT,
            ilce TEXT,
            baslangic TEXT,
            bitis TEXT,
            is_aciklamasi TEXT,
            polygon_wkt TEXT,
            kaynak TEXT DEFAULT 'YEDAS_API',
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS kesinti_saha_eslesme (
            kesinti_id INTEGER NOT NULL,
            saha_id INTEGER NOT NULL,
            PRIMARY KEY (kesinti_id, saha_id),
            FOREIGN KEY (kesinti_id) REFERENCES kesintiler(id) ON DELETE CASCADE,
            FOREIGN KEY (saha_id) REFERENCES sahalar(id) ON DELETE CASCADE
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS ariza_kayitlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saha_id INTEGER NOT NULL,
            mains_saati TEXT NOT NULL,
            kesinti_saati TEXT NOT NULL,
            enerji_gelis_saati TEXT,
            backup_suresi_dk REAL,
            kesinti_suresi_dk REAL,
            yorum TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (saha_id) REFERENCES sahalar(id) ON DELETE CASCADE
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS excel_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dosya_adi TEXT,
            eklenen_sayisi INTEGER,
            silinen_sayisi INTEGER,
            eklenen_isimler TEXT,
            silinen_isimler TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)

        conn.commit()

# Modül yüklendiğinde veritabanı tablolarının varlığını garantiye al
init_db()


def reset_database():
    """Tüm demo ve mevcut verileri temizleyerek sıfır veritabanı oluşturur."""
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM kesinti_saha_eslesme;")
        c.execute("DELETE FROM ariza_kayitlari;")
        c.execute("DELETE FROM osrm_cache;")
        c.execute("DELETE FROM kesintiler;")
        c.execute("DELETE FROM sahalar;")
        c.execute("DELETE FROM ilce_merkezleri;")
        c.execute("DELETE FROM excel_sync_log;")
        c.execute("DELETE FROM sqlite_sequence;")
        conn.commit()


# ---------------------------------------------------------------------------
# YARDIMCI: KOORDİNAT -> İL / İLÇE TESPİTİ (SADECE EXCEL YÜKLERKEN ÇALIŞIR)
# ---------------------------------------------------------------------------

def reverse_geocode(lat: float, lon: float):
    """
    Excel'de İl/İlçe sütunu olmadığında koordinattan otomatik il ve ilçe bulur.
    Yalnızca Excel aktarımı sırasında 1 kez çağrılır ve DB'ye kaydedilir.
    """
    # 1. OpenStreetMap (Nominatim) API Çözümleme
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=10&accept-language=tr"
        req = urllib.request.Request(url, headers={'User-Agent': 'yedas_gsm_tracker_app'})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            if "address" in data:
                addr = data["address"]
                il = addr.get("province") or addr.get("state") or addr.get("admin_level_4")
                ilce = addr.get("town") or addr.get("district") or addr.get("county") or addr.get("suburb") or addr.get("city_district")
                
                il_str = str(il).strip() if il else None
                ilce_str = str(ilce).strip() if ilce else None
                
                if il_str:
                    return il_str, ilce_str
    except Exception as e:
        print(f"API Reverse Geocode atlandı ({lat}, {lon}): {e}")

    # 2. Bölgesel Bounding Box Çevrimdışı Koruması (Ağ kısıtı veya API zaman aşımı durumu için)
    if 40.8 <= lat <= 41.7 and 35.2 <= lon <= 37.2:
        return "Samsun", "Merkez"
    elif 40.5 <= lat <= 41.2 and 36.8 <= lon <= 38.2:
        return "Ordu", "Merkez"
    elif 41.2 <= lat <= 42.1 and 34.2 <= lon <= 35.4:
        return "Sinop", "Merkez"
    elif 40.3 <= lat <= 40.9 and 35.0 <= lon <= 36.5:
        return "Amasya", "Merkez"
    elif 40.0 <= lat <= 40.7 and 35.8 <= lon <= 37.5:
        return "Tokat", "Merkez"
    elif 40.0 <= lat <= 41.3 and 34.0 <= lon <= 35.6:
        return "Çorum", "Merkez"

    return "Samsun", "Merkez"


# ---------------------------------------------------------------------------
# SAHALAR (GSM Sites)
# ---------------------------------------------------------------------------

def get_all_sahalar(only_active=True) -> pd.DataFrame:
    try:
        with get_conn() as conn:
            q = "SELECT * FROM sahalar"
            if only_active:
                q += " WHERE aktif = 1"
            return pd.read_sql_query(q, conn)
    except Exception as e:
        print(f"get_all_sahalar hatası: {e}")
        return pd.DataFrame()


def get_saha_by_name(name: str):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sahalar WHERE placemark_adi = ?", (name,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"get_saha_by_name hatası: {e}")
        return None


def upsert_sahalar_from_df(df: pd.DataFrame):
    """
    Excel'den okunan DataFrame'i sahalar tablosuna ekler / günceller.
    Excel'de İl/İlçe olmasa dahi koordinat üzerinden otomatik İl/İlçe atar ve DB'ye yazar.
    """
    if df is None or df.empty:
        return

    df_clean = df.copy()

    col_map = {}
    for col in df_clean.columns:
        c_str = str(col).strip().lower()
        c_clean = c_str.replace("ı", "i").replace("ğ", "g").replace("ü", "u").replace("ş", "s").replace("ö", "o").replace("ç", "c").replace("_", "").replace(" ", "")

        if c_clean in ["placemarkadi", "placemark", "sahaadi", "siteid", "sitename", "saha_adi", "saha"]:
            col_map[col] = "placemark_adi"
        elif c_clean in ["latitude", "enlem", "lat", "y"]:
            col_map[col] = "latitude"
        elif c_clean in ["longitude", "boylam", "lon", "lng", "long", "x"]:
            col_map[col] = "longitude"
        elif c_clean in ["kmldosyası", "kmldosyasi", "kml"]:
            col_map[col] = "kml_dosyasi"
        elif c_clean in ["açıklama", "aciklama", "description"]:
            col_map[col] = "aciklama"
        elif c_clean in ["altitude", "yukseklik"]:
            col_map[col] = "altitude"
        elif c_clean in ["koordinatham", "koordinat"]:
            col_map[col] = "koordinat_ham"
        elif c_clean in ["il", "city", "şehir", "sehir"]:
            col_map[col] = "il"
        elif c_clean in ["ilce", "ilçe", "town", "district"]:
            col_map[col] = "ilce"

    df_clean = df_clean.rename(columns=col_map)

    if "placemark_adi" not in df_clean.columns or "latitude" not in df_clean.columns or "longitude" not in df_clean.columns:
        print("⚠️ Excel'de Saha Adı, Latitude veya Longitude sütunları bulunamadı.")
        return

    # Sayısal veri ve virgül-nokta dönüşümü
    df_clean["latitude"] = pd.to_numeric(df_clean["latitude"].astype(str).str.replace(",", "."), errors="coerce")
    df_clean["longitude"] = pd.to_numeric(df_clean["longitude"].astype(str).str.replace(",", "."), errors="coerce")
    df_clean = df_clean.dropna(subset=["placemark_adi", "latitude", "longitude"])

    with get_conn() as conn:
        c = conn.cursor()
        for _, row in df_clean.iterrows():
            name = str(row.get("placemark_adi", "")).strip()
            if not name:
                continue

            lat = float(row.get("latitude"))
            lon = float(row.get("longitude"))

            kml = str(row.get("kml_dosyasi")).strip() if pd.notna(row.get("kml_dosyasi")) else None
            aciklama = str(row.get("aciklama")).strip() if pd.notna(row.get("aciklama")) else None
            alt = float(row.get("altitude")) if pd.notna(row.get("altitude")) else None
            koord_ham = str(row.get("koordinat_ham")).strip() if pd.notna(row.get("koordinat_ham")) else None
            
            il_val = str(row.get("il")).strip() if pd.notna(row.get("il")) and str(row.get("il")).strip() != "" else None
            ilce_val = str(row.get("ilce")).strip() if pd.notna(row.get("ilce")) and str(row.get("ilce")).strip() != "" else None

            # Veritabanındaki mevcut durumu kontrol et
            existing = c.execute(
                "SELECT id, il, ilce FROM sahalar WHERE placemark_adi = ?", (name,)
            ).fetchone()

            # Eğer Excel'de il/ilçe yoksa ve DB'de önceden kayıtlı değilse, koordinattan otomatik tespit et
            if not il_val or not ilce_val:
                if existing and existing["il"] and existing["ilce"]:
                    il_val = il_val or existing["il"]
                    ilce_val = ilce_val or existing["ilce"]
                else:
                    geo_il, geo_ilce = reverse_geocode(lat, lon)
                    il_val = il_val or geo_il
                    ilce_val = ilce_val or geo_ilce

            if existing:
                c.execute("""
                    UPDATE sahalar SET latitude=?, longitude=?, kml_dosyasi=?, aciklama=?,
                        altitude=?, koordinat_ham=?, il=?, ilce=?, aktif=1, updated_at=datetime('now')
                    WHERE placemark_adi=?
                """, (lat, lon, kml, aciklama, alt, koord_ham, il_val, ilce_val, name))
            else:
                c.execute("""
                    INSERT INTO sahalar
                        (placemark_adi, latitude, longitude, kml_dosyasi, aciklama, altitude, koordinat_ham, il, ilce, aktif)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (name, lat, lon, kml, aciklama, alt, koord_ham, il_val, ilce_val))
        conn.commit()


def diff_and_sync_sahalar(df_new: pd.DataFrame):
    if df_new is None or df_new.empty:
        return [], []

    name_col = None
    for c in df_new.columns:
        if str(c).strip().lower().replace("_", "").replace(" ", "") in ["placemarkadi", "placemark", "sahaadi", "siteid"]:
            name_col = c
            break

    if not name_col:
        name_col = df_new.columns[0]

    new_names = set(df_new[name_col].astype(str).str.strip())

    with get_conn() as conn:
        c = conn.cursor()
        existing_rows = c.execute("SELECT placemark_adi FROM sahalar WHERE aktif = 1").fetchall()
        existing_names = set(r["placemark_adi"] for r in existing_rows)

        eklenen = sorted(new_names - existing_names)
        silinen = sorted(existing_names - new_names)

        upsert_sahalar_from_df(df_new)

        for name in silinen:
            c.execute("UPDATE sahalar SET aktif = 0, updated_at=datetime('now') WHERE placemark_adi = ?", (name,))
        conn.commit()

    log_excel_sync(eklenen, silinen)
    return eklenen, silinen


def log_excel_sync(eklenen, silinen, dosya_adi="upload.xlsx"):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO excel_sync_log (dosya_adi, eklenen_sayisi, silinen_sayisi, eklenen_isimler, silinen_isimler)
                VALUES (?, ?, ?, ?, ?)
            """, (dosya_adi, len(eklenen), len(silinen), ", ".join(eklenen), ", ".join(silinen)))
            conn.commit()
    except Exception as e:
        print(f"log_excel_sync hatası: {e}")


def set_saha_ilce_merkezi(saha_id: int, ilce_merkezi_id: int, manuel: bool = True):
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE sahalar SET ilce_merkezi_id = ?, manuel_atama = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (ilce_merkezi_id, 1 if manuel else 0, saha_id))
            conn.commit()
    except Exception as e:
        print(f"set_saha_ilce_merkezi hatası: {e}")


# ---------------------------------------------------------------------------
# İLÇE MERKEZLERİ
# ---------------------------------------------------------------------------

def get_all_ilce_merkezleri() -> pd.DataFrame:
    try:
        with get_conn() as conn:
            return pd.read_sql_query("SELECT * FROM ilce_merkezleri ORDER BY il, isim", conn)
    except Exception as e:
        print(f"get_all_ilce_merkezleri hatası: {e}")
        return pd.DataFrame()


def add_ilce_merkezi(isim, il, lat, lon):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO ilce_merkezleri (isim, il, latitude, longitude) VALUES (?, ?, ?, ?)
            """, (isim, il, lat, lon))
            conn.commit()
    except Exception as e:
        print(f"add_ilce_merkezi hatası: {e}")


def delete_ilce_merkezi(ilce_id):
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM ilce_merkezleri WHERE id = ?", (ilce_id,))
            conn.commit()
    except Exception as e:
        print(f"delete_ilce_merkezi hatası: {e}")


# ---------------------------------------------------------------------------
# OSRM CACHE
# ---------------------------------------------------------------------------

def get_osrm_cache(saha_id, ilce_merkezi_id):
    try:
        with get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM osrm_cache WHERE saha_id = ? AND ilce_merkezi_id = ?
            """, (saha_id, ilce_merkezi_id)).fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"get_osrm_cache hatası: {e}")
        return None


def set_osrm_cache(saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson=None):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO osrm_cache (saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(saha_id, ilce_merkezi_id) DO UPDATE SET
                    mesafe_km=excluded.mesafe_km, sure_dk=excluded.sure_dk,
                    route_geojson=excluded.route_geojson, updated_at=datetime('now')
            """, (saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson))
            conn.commit()
    except Exception as e:
        print(f"set_osrm_cache hatası: {e}")


# ---------------------------------------------------------------------------
# KESİNTİLER (YEDAŞ outages)
# ---------------------------------------------------------------------------

def insert_kesinti(yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak="YEDAS_API"):
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO kesintiler (yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        print(f"insert_kesinti hatası: {e}")
        return None


def link_kesinti_saha(kesinti_id, saha_id):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO kesinti_saha_eslesme (kesinti_id, saha_id) VALUES (?, ?)
            """, (kesinti_id, saha_id))
            conn.commit()
    except Exception as e:
        print(f"link_kesinti_saha hatası: {e}")


def get_kesintiler(gun_sayisi=30) -> pd.DataFrame:
    try:
        with get_conn() as conn:
            q = f"""
                SELECT * FROM kesintiler
                WHERE baslangic >= datetime('now', '-{int(gun_sayisi)} days')
                   OR bitis >= datetime('now', '-1 days')
                   OR baslangic IS NULL
                ORDER BY id DESC
            """
            df = pd.read_sql_query(q, conn)
            if df.empty:
                df = pd.read_sql_query("SELECT * FROM kesintiler ORDER BY id DESC", conn)
            return df
    except Exception as e:
        print(f"get_kesintiler hatası: {e}")
        return pd.DataFrame()


def get_etkilenen_sahalar(kesinti_id) -> pd.DataFrame:
    try:
        with get_conn() as conn:
            return pd.read_sql_query("""
                SELECT s.* FROM sahalar s
                JOIN kesinti_saha_eslesme k ON k.saha_id = s.id
                WHERE k.kesinti_id = ?
            """, conn, params=(kesinti_id,))
    except Exception as e:
        print(f"get_etkilenen_sahalar hatası: {e}")
        return pd.DataFrame()


def get_kesinti_history_for_saha(saha_adi, start_date=None, end_date=None) -> pd.DataFrame:
    try:
        q = """
            SELECT k.* FROM kesintiler k
            JOIN kesinti_saha_eslesme e ON e.kesinti_id = k.id
            JOIN sahalar s ON s.id = e.saha_id
            WHERE s.placemark_adi = ?
        """
        params = [saha_adi]
        if start_date:
            q += " AND k.baslangic >= ?"
            params.append(str(start_date))
        if end_date:
            q += " AND k.baslangic <= ?"
            params.append(str(end_date))
        with get_conn() as conn:
            return pd.read_sql_query(q, conn, params=params)
    except Exception as e:
        print(f"get_kesinti_history_for_saha hatası: {e}")
        return pd.DataFrame()


def get_top_n_stats(n=5, start_date=None, end_date=None):
    try:
        q = "SELECT k.*, s.placemark_adi FROM kesintiler k LEFT JOIN kesinti_saha_eslesme e ON e.kesinti_id = k.id LEFT JOIN sahalar s ON s.id = e.saha_id WHERE 1=1"
        params = []
        if start_date:
            q += " AND k.baslangic >= ?"
            params.append(str(start_date))
        if end_date:
            q += " AND k.baslangic <= ?"
            params.append(str(end_date))
        with get_conn() as conn:
            df = pd.read_sql_query(q, conn, params=params)
        if df.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        top_saha = df.dropna(subset=["placemark_adi"]).groupby("placemark_adi").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
        top_il = df.dropna(subset=["il"]).groupby("il").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
        top_ilce = df.dropna(subset=["ilce"]).groupby("ilce").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
        return top_saha, top_il, top_ilce
    except Exception as e:
        print(f"get_top_n_stats hatası: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


# ---------------------------------------------------------------------------
# ARIZA KAYITLARI (Mains / Backup / Outage tracking)
# ---------------------------------------------------------------------------

def insert_ariza_kaydi(saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum):
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO ariza_kayitlari
                    (saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum))
            conn.commit()
    except Exception as e:
        print(f"insert_ariza_kaydi hatası: {e}")


def get_ariza_kayitlari(saha_adi=None, start_date=None, end_date=None) -> pd.DataFrame:
    try:
        q = """
            SELECT a.*, s.placemark_adi, s.il, s.ilce FROM ariza_kayitlari a
            JOIN sahalar s ON s.id = a.saha_id
            WHERE 1=1
        """
        params = []
        if saha_adi:
            q += " AND s.placemark_adi = ?"
            params.append(saha_adi)
        if start_date:
            q += " AND a.mains_saati >= ?"
            params.append(str(start_date))
        if end_date:
            q += " AND a.mains_saati <= ?"
            params.append(str(end_date))
        q += " ORDER BY a.mains_saati DESC"
        with get_conn() as conn:
            return pd.read_sql_query(q, conn, params=params)
    except Exception as e:
        print(f"get_ariza_kayitlari hatası: {e}")
        return pd.DataFrame()


def get_ariza_ozet_metrikleri(saha_adi=None, start_date=None, end_date=None):
    df = get_ariza_kayitlari(saha_adi, start_date, end_date)
    if df.empty:
        return {"ortalama_backup_dk": 0, "ortalama_kesinti_dk": 0, "toplam_kesinti_saat": 0, "kayit_sayisi": 0}
    return {
        "ortalama_backup_dk": round(df["backup_suresi_dk"].mean(), 1) if "backup_suresi_dk" in df else 0,
        "ortalama_kesinti_dk": round(df["kesinti_suresi_dk"].mean(), 1) if "kesinti_suresi_dk" in df else 0,
        "toplam_kesinti_saat": round(df["kesinti_suresi_dk"].sum() / 60, 1) if "kesinti_suresi_dk" in df else 0,
        "kayit_sayisi": len(df),
    }

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


# ---------------------------------------------------------------------------
# SAHALAR (GSM Sites)
# ---------------------------------------------------------------------------

def get_all_sahalar(only_active=True) -> pd.DataFrame:
    with get_conn() as conn:
        q = "SELECT * FROM sahalar"
        if only_active:
            q += " WHERE aktif = 1"
        return pd.read_sql_query(q, conn)


def get_saha_by_name(name: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sahalar WHERE placemark_adi = ?", (name,)
        ).fetchone()
        return dict(row) if row else None


def upsert_sahalar_from_df(df: pd.DataFrame):
    """
    Excel'den okunan DataFrame'i sahalar tablosuna ekler / günceller.
    Beklenen sütunlar: Placemark Adı, Latitude, Longitude, KML Dosyası,
    Açıklama, Altitude, Koordinat (Ham)
    """
    with get_conn() as conn:
        c = conn.cursor()
        for _, row in df.iterrows():
            name = str(row.get("Placemark Adı", "")).strip()
            if not name:
                continue
            existing = c.execute(
                "SELECT id FROM sahalar WHERE placemark_adi = ?", (name,)
            ).fetchone()
            vals = (
                float(row.get("Latitude")) if pd.notna(row.get("Latitude")) else None,
                float(row.get("Longitude")) if pd.notna(row.get("Longitude")) else None,
                str(row.get("KML Dosyası", "")) if pd.notna(row.get("KML Dosyası", None)) else None,
                str(row.get("Açıklama", "")) if pd.notna(row.get("Açıklama", None)) else None,
                float(row.get("Altitude")) if pd.notna(row.get("Altitude", None)) else None,
                str(row.get("Koordinat (Ham)", "")) if pd.notna(row.get("Koordinat (Ham)", None)) else None,
            )
            if existing:
                c.execute("""
                    UPDATE sahalar SET latitude=?, longitude=?, kml_dosyasi=?, aciklama=?,
                        altitude=?, koordinat_ham=?, aktif=1, updated_at=datetime('now')
                    WHERE placemark_adi=?
                """, (*vals, name))
            else:
                c.execute("""
                    INSERT INTO sahalar
                        (placemark_adi, latitude, longitude, kml_dosyasi, aciklama, altitude, koordinat_ham, aktif)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (name, *vals))
        conn.commit()


def diff_and_sync_sahalar(df_new: pd.DataFrame):
    """
    Excel Diff senkronizasyonu:
    - Yeni listede olup DB'de olmayan sahalar eklenir (aktif=1)
    - DB'de olup yeni listede olmayan sahalar 'pasif' işaretlenir (silinmiş sayılır)
    Dönüş: (eklenen_isimler: list, silinen_isimler: list)
    """
    new_names = set(df_new["Placemark Adı"].astype(str).str.strip())
    with get_conn() as conn:
        c = conn.cursor()
        existing_rows = c.execute("SELECT placemark_adi FROM sahalar WHERE aktif = 1").fetchall()
        existing_names = set(r["placemark_adi"] for r in existing_rows)

        eklenen = sorted(new_names - existing_names)
        silinen = sorted(existing_names - new_names)

        # Ekle / güncelle (yeni olanlar dahil hepsini upsert et)
        upsert_sahalar_from_df(df_new[df_new["Placemark Adı"].astype(str).str.strip().isin(new_names)])

        # Silinenleri pasif yap (gerçek silme yapmıyoruz, veri kaybını önlemek için)
        for name in silinen:
            c.execute("UPDATE sahalar SET aktif = 0, updated_at=datetime('now') WHERE placemark_adi = ?", (name,))
        conn.commit()

    log_excel_sync(eklenen, silinen)
    return eklenen, silinen


def log_excel_sync(eklenen, silinen, dosya_adi="upload.xlsx"):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO excel_sync_log (dosya_adi, eklenen_sayisi, silinen_sayisi, eklenen_isimler, silinen_isimler)
            VALUES (?, ?, ?, ?, ?)
        """, (dosya_adi, len(eklenen), len(silinen), ", ".join(eklenen), ", ".join(silinen)))
        conn.commit()


def set_saha_ilce_merkezi(saha_id: int, ilce_merkezi_id: int, manuel: bool = True):
    with get_conn() as conn:
        conn.execute("""
            UPDATE sahalar SET ilce_merkezi_id = ?, manuel_atama = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (ilce_merkezi_id, 1 if manuel else 0, saha_id))
        conn.commit()


# ---------------------------------------------------------------------------
# İLÇE MERKEZLERİ
# ---------------------------------------------------------------------------

def get_all_ilce_merkezleri() -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("SELECT * FROM ilce_merkezleri ORDER BY il, isim", conn)


def add_ilce_merkezi(isim, il, lat, lon):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO ilce_merkezleri (isim, il, latitude, longitude) VALUES (?, ?, ?, ?)
        """, (isim, il, lat, lon))
        conn.commit()


def delete_ilce_merkezi(ilce_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM ilce_merkezleri WHERE id = ?", (ilce_id,))
        conn.commit()


# ---------------------------------------------------------------------------
# OSRM CACHE
# ---------------------------------------------------------------------------

def get_osrm_cache(saha_id, ilce_merkezi_id):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT * FROM osrm_cache WHERE saha_id = ? AND ilce_merkezi_id = ?
        """, (saha_id, ilce_merkezi_id)).fetchone()
        return dict(row) if row else None


def set_osrm_cache(saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson=None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO osrm_cache (saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(saha_id, ilce_merkezi_id) DO UPDATE SET
                mesafe_km=excluded.mesafe_km, sure_dk=excluded.sure_dk,
                route_geojson=excluded.route_geojson, updated_at=datetime('now')
        """, (saha_id, ilce_merkezi_id, mesafe_km, sure_dk, route_geojson))
        conn.commit()


# ---------------------------------------------------------------------------
# KESİNTİLER (YEDAŞ outages)
# ---------------------------------------------------------------------------

def insert_kesinti(yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak="YEDAS_API"):
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO kesintiler (yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (yedas_ref, il, ilce, baslangic, bitis, is_aciklamasi, polygon_wkt, kaynak))
        conn.commit()
        return cur.lastrowid


def link_kesinti_saha(kesinti_id, saha_id):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO kesinti_saha_eslesme (kesinti_id, saha_id) VALUES (?, ?)
        """, (kesinti_id, saha_id))
        conn.commit()


def get_kesintiler(gun_sayisi=1) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query(f"""
            SELECT * FROM kesintiler
            WHERE date(baslangic) >= date('now', '-{int(gun_sayisi)} days')
               OR date(bitis) >= date('now')
            ORDER BY baslangic DESC
        """, conn)


def get_etkilenen_sahalar(kesinti_id) -> pd.DataFrame:
    with get_conn() as conn:
        return pd.read_sql_query("""
            SELECT s.* FROM sahalar s
            JOIN kesinti_saha_eslesme k ON k.saha_id = s.id
            WHERE k.kesinti_id = ?
        """, conn, params=(kesinti_id,))


def get_kesinti_history_for_saha(saha_adi, start_date=None, end_date=None) -> pd.DataFrame:
    q = """
        SELECT k.* FROM kesintiler k
        JOIN kesinti_saha_eslesme e ON e.kesinti_id = k.id
        JOIN sahalar s ON s.id = e.saha_id
        WHERE s.placemark_adi = ?
    """
    params = [saha_adi]
    if start_date:
        q += " AND date(k.baslangic) >= date(?)"
        params.append(start_date)
    if end_date:
        q += " AND date(k.baslangic) <= date(?)"
        params.append(end_date)
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)


def get_top_n_stats(n=5, start_date=None, end_date=None):
    """Top-N Saha / İl / İlçe kesinti sayıları."""
    q = "SELECT k.*, s.placemark_adi FROM kesintiler k LEFT JOIN kesinti_saha_eslesme e ON e.kesinti_id = k.id LEFT JOIN sahalar s ON s.id = e.saha_id WHERE 1=1"
    params = []
    if start_date:
        q += " AND date(k.baslangic) >= date(?)"
        params.append(start_date)
    if end_date:
        q += " AND date(k.baslangic) <= date(?)"
        params.append(end_date)
    with get_conn() as conn:
        df = pd.read_sql_query(q, conn, params=params)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    top_saha = df.dropna(subset=["placemark_adi"]).groupby("placemark_adi").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
    top_il = df.groupby("il").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
    top_ilce = df.groupby("ilce").size().reset_index(name="kesinti_sayisi").sort_values("kesinti_sayisi", ascending=False).head(n)
    return top_saha, top_il, top_ilce


# ---------------------------------------------------------------------------
# ARIZA KAYITLARI (Mains / Backup / Outage tracking)
# ---------------------------------------------------------------------------

def insert_ariza_kaydi(saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO ariza_kayitlari
                (saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (saha_id, mains_saati, kesinti_saati, enerji_gelis_saati, backup_suresi_dk, kesinti_suresi_dk, yorum))
        conn.commit()


def get_ariza_kayitlari(saha_adi=None, start_date=None, end_date=None) -> pd.DataFrame:
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
        q += " AND date(a.mains_saati) >= date(?)"
        params.append(start_date)
    if end_date:
        q += " AND date(a.mains_saati) <= date(?)"
        params.append(end_date)
    q += " ORDER BY a.mains_saati DESC"
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)


def get_ariza_ozet_metrikleri(saha_adi=None, start_date=None, end_date=None):
    df = get_ariza_kayitlari(saha_adi, start_date, end_date)
    if df.empty:
        return {"ortalama_backup_dk": 0, "ortalama_kesinti_dk": 0, "toplam_kesinti_saat": 0, "kayit_sayisi": 0}
    return {
        "ortalama_backup_dk": round(df["backup_suresi_dk"].mean(), 1),
        "ortalama_kesinti_dk": round(df["kesinti_suresi_dk"].mean(), 1),
        "toplam_kesinti_saat": round(df["kesinti_suresi_dk"].sum() / 60, 1),
        "kayit_sayisi": len(df),
    }

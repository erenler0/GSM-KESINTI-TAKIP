"""
geo_utils.py
------------
Metin tabanlı (İl-İlçe-Mahalle) eşleştirme işlemleri ve 
saha-ilçe merkezi arası koordinat (Haversine) mesafe hesaplamaları.

Not: YEDAŞ poligonlarının kararsızlığı nedeniyle GeoPandas (sjoin) 
iptal edilmiş, yerine standartlaştırılmış Pandas metin eşleştirmesi 
(pd.merge) entegre edilmiştir.
"""

import pandas as pd
import re
from math import radians, sin, cos, sqrt, atan2

def standardize_text(text):
    """
    Metinleri eşleştirme için standart hale getirir:
    - Küçük harfe çevirir ve Türkçe karakterleri tolere eder.
    - 'mah.', 'mahallesi', 'koy' gibi takıları siler.
    - Noktalama işaretlerini temizler.
    """
    if not isinstance(text, str) or pd.isna(text):
        return ""
    
    text = text.lower()
    text = text.replace("i̇", "i").replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    
    # Mahalle/Köy takılarını temizle
    text = re.sub(r'\b(mah|mahallesi|mah\.|koy|koyu|koy\.)\b', '', text)
    
    # Sadece harfler ve rakamlar kalsın (noktalama işaretlerini boşluğa çevir)
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    
    # Fazla boşlukları temizle
    return " ".join(text.split())

def match_sahalar_with_text(df_sahalar: pd.DataFrame, df_kesinti: pd.DataFrame) -> pd.DataFrame:
    """
    Standartlaştırılmış İl, İlçe ve Mahalle metinlerine göre 
    sahalar ile kesintileri eşleştirir (Pandas Inner Merge).
    """
    if df_sahalar is None or df_sahalar.empty or df_kesinti is None or df_kesinti.empty:
        return pd.DataFrame()
        
    # Her iki dataframe için arama (match) sütunları oluştur
    # df_sahalar tarafında 'il', 'ilce', 'mahalle' sütunlarının DB'den gelmesi gerekir
    df_sahalar_copy = df_sahalar.copy()
    df_sahalar_copy['match_il'] = df_sahalar_copy.get('il', '').apply(standardize_text)
    df_sahalar_copy['match_ilce'] = df_sahalar_copy.get('ilce', '').apply(standardize_text)
    df_sahalar_copy['match_mahalle'] = df_sahalar_copy.get('mahalle', '').apply(standardize_text)
    
    df_kesinti_copy = df_kesinti.copy()
    df_kesinti_copy['match_il'] = df_kesinti_copy.get('il', '').apply(standardize_text)
    df_kesinti_copy['match_ilce'] = df_kesinti_copy.get('ilce', '').apply(standardize_text)
    df_kesinti_copy['match_mahalle'] = df_kesinti_copy.get('mahalle', '').apply(standardize_text)
    
    # İl, İlçe ve Mahalle üzerinden eşleştir
    matched = pd.merge(
        df_sahalar_copy, 
        df_kesinti_copy, 
        on=['match_il', 'match_ilce', 'match_mahalle'], 
        how='inner',
        suffixes=('', '_kesinti')
    )
    
    # Merge sonrası oluşan mükerrer sütun isimlerini temizle/düzenle
    for col in matched.columns:
        if col.endswith('_kesinti'):
            base_col = col.replace('_kesinti', '')
            rename_col = f"kesinti_{base_col}"
            matched.rename(columns={col: rename_col}, inplace=True)
            
    return matched.reset_index(drop=True)

def find_nearest_ilce_merkezi(saha_lat, saha_lon, df_merkezler: pd.DataFrame):
    """
    Kuş uçuşu (Haversine) mesafesine göre en yakın ilçe merkezini bulur.
    (Ekran 3 - OSRM rotalama öncesi ön eleme için kullanılır)
    """
    if df_merkezler.empty:
        return None, float("inf")

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

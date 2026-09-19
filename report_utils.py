"""
report_utils.py
----------------
Pillow ile estetik JPG kartlar/raporlar üretir:
  - Tekil kesinti kartı (Ekran 1)
  - Saha/İl/İlçe analiz özet raporu (Ekran 2)
  - Sahalar & mesafe tablo raporu (Ekran 3)
  - Arıza/backup özet raporu (Ekran 4)
  - Excel Diff senkronizasyon raporu (Ekran 5)

Tüm fonksiyonlar bir PIL.Image döner; çağıran taraf bunu
`st.download_button` ile indirtebilir veya `st.image` ile gösterebilir.
"""

from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
from datetime import datetime

# Renk paleti
COLOR_BG = (255, 255, 255)
COLOR_HEADER_BG = (0, 82, 155)       # YEDAŞ mavi tonu
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_TEXT = (30, 30, 30)
COLOR_MUTED = (110, 110, 110)
COLOR_ACCENT = (230, 126, 34)        # kesinti turuncusu
COLOR_LINE = (225, 225, 225)
COLOR_GREEN = (39, 174, 96)
COLOR_RED = (192, 57, 43)


def _font(size, bold=False):
    """Sistem fontlarını dener, bulunamazsa PIL varsayılan fontuna düşer."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_header(draw, width, title, subtitle=None, height=90):
    draw.rectangle([0, 0, width, height], fill=COLOR_HEADER_BG)
    draw.text((30, 20), title, font=_font(28, bold=True), fill=COLOR_HEADER_TEXT)
    if subtitle:
        draw.text((30, 58), subtitle, font=_font(14), fill=(220, 230, 240))
    return height


def _wrapped_text(draw, xy, text, font, fill, max_width_chars=70, line_height=22):
    x, y = xy
    for line in textwrap.wrap(text or "", width=max_width_chars):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def kesinti_karti_jpg(saha_adi, il, ilce, baslangic, bitis, aciklama, width=800, height=500) -> Image.Image:
    """Ekran 1: Seçilen kesinti için tekil görsel kart."""
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    y = _draw_header(draw, width, "⚡ YEDAŞ Planlı Kesinti Bildirimi", subtitle=f"Rapor Tarihi: {datetime.now():%d.%m.%Y %H:%M}")

    y += 30
    draw.text((30, y), "Saha Adı", font=_font(14), fill=COLOR_MUTED); y += 20
    draw.text((30, y), saha_adi or "-", font=_font(22, bold=True), fill=COLOR_TEXT); y += 45

    col2_x = width // 2 + 20
    y_start = y
    draw.text((30, y), "İl", font=_font(14), fill=COLOR_MUTED)
    draw.text((col2_x, y), "İlçe", font=_font(14), fill=COLOR_MUTED)
    y += 20
    draw.text((30, y), il or "-", font=_font(18, bold=True), fill=COLOR_TEXT)
    draw.text((col2_x, y), ilce or "-", font=_font(18, bold=True), fill=COLOR_TEXT)
    y += 45

    draw.line([(30, y), (width - 30, y)], fill=COLOR_LINE, width=1)
    y += 20

    draw.text((30, y), "Çalışma Başlangıç", font=_font(14), fill=COLOR_MUTED)
    draw.text((col2_x, y), "Çalışma Bitiş", font=_font(14), fill=COLOR_MUTED)
    y += 20
    draw.text((30, y), str(baslangic) or "-", font=_font(16, bold=True), fill=COLOR_ACCENT)
    draw.text((col2_x, y), str(bitis) or "-", font=_font(16, bold=True), fill=COLOR_ACCENT)
    y += 45

    draw.line([(30, y), (width - 30, y)], fill=COLOR_LINE, width=1)
    y += 20
    draw.text((30, y), "İş Açıklaması", font=_font(14), fill=COLOR_MUTED)
    y += 22
    _wrapped_text(draw, (30, y), aciklama or "Açıklama belirtilmemiş.", _font(15), COLOR_TEXT, max_width_chars=75)

    draw.rectangle([0, height - 6, width, height], fill=COLOR_ACCENT)
    return img


def analiz_ozet_jpg(top_saha_df, top_il_df, top_ilce_df, width=900, height=650) -> Image.Image:
    """Ekran 2: Top-5 Saha / İl / İlçe özet raporu."""
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)
    y = _draw_header(draw, width, "📊 Kesinti Analiz Özeti", subtitle=f"Rapor Tarihi: {datetime.now():%d.%m.%Y %H:%M}")

    col_w = width // 3
    sections = [("En Çok Kesinti Alan Sahalar", top_saha_df, "placemark_adi"),
                ("En Çok Kesinti Alan İller", top_il_df, "il"),
                ("En Çok Kesinti Alan İlçeler", top_ilce_df, "ilce")]

    for i, (title, df, key) in enumerate(sections):
        x0 = i * col_w + 20
        yy = y + 30
        draw.text((x0, yy), title, font=_font(16, bold=True), fill=COLOR_HEADER_BG)
        yy += 35
        if df is None or df.empty:
            draw.text((x0, yy), "Veri yok", font=_font(13), fill=COLOR_MUTED)
            continue
        for rank, (_, row) in enumerate(df.iterrows(), start=1):
            label = str(row.get(key, "-"))[:22]
            count = row.get("kesinti_sayisi", 0)
            draw.text((x0, yy), f"{rank}. {label}", font=_font(14), fill=COLOR_TEXT)
            draw.text((x0 + col_w - 60, yy), str(count), font=_font(14, bold=True), fill=COLOR_ACCENT)
            yy += 26

    draw.rectangle([0, height - 6, width, height], fill=COLOR_HEADER_BG)
    return img


def tablo_jpg(df, title, columns=None, width=1000, row_height=28, max_rows=40) -> Image.Image:
    """
    Ekran 3 & 4: Genel amaçlı tablo -> JPG dönüştürücü.
    (Sahalar & mesafe listesi, arıza kayıtları vb.)
    """
    if columns is None:
        columns = list(df.columns)
    df = df[columns].head(max_rows)

    height = 110 + row_height * (len(df) + 1)
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)
    y = _draw_header(draw, width, title, subtitle=f"Rapor Tarihi: {datetime.now():%d.%m.%Y %H:%M} | {len(df)} kayıt")

    col_w = (width - 40) // max(len(columns), 1)
    x0 = 20
    y0 = y + 20

    # Başlık satırı
    draw.rectangle([x0, y0, width - 20, y0 + row_height], fill=(240, 244, 248))
    for i, col in enumerate(columns):
        draw.text((x0 + i * col_w + 6, y0 + 6), str(col)[:18], font=_font(13, bold=True), fill=COLOR_HEADER_BG)

    y0 += row_height
    for r, (_, row) in enumerate(df.iterrows()):
        if r % 2 == 0:
            draw.rectangle([x0, y0, width - 20, y0 + row_height], fill=(250, 250, 250))
        for i, col in enumerate(columns):
            val = row[col]
            text = f"{val:.1f}" if isinstance(val, float) else str(val)
            draw.text((x0 + i * col_w + 6, y0 + 6), text[:20], font=_font(12), fill=COLOR_TEXT)
        y0 += row_height
        draw.line([(x0, y0), (width - 20, y0)], fill=COLOR_LINE, width=1)

    return img


def ariza_ozet_jpg(metrikler: dict, saha_adi=None, width=800, height=380) -> Image.Image:
    """Ekran 4: Ortalama backup/kesinti süresi ve toplam kesinti saat raporu."""
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)
    subtitle = f"Saha: {saha_adi}" if saha_adi else "Tüm Sahalar"
    y = _draw_header(draw, width, "🚨 Arıza & Şebeke Analiz Raporu", subtitle=subtitle)

    cards = [
        ("Ortalama Backup Süresi", f"{metrikler['ortalama_backup_dk']} dk", COLOR_GREEN),
        ("Ortalama Kesik Kalma Süresi", f"{metrikler['ortalama_kesinti_dk']} dk", COLOR_RED),
        ("Toplam Kesinti Saati", f"{metrikler['toplam_kesinti_saat']} saat", COLOR_HEADER_BG),
    ]
    card_w = (width - 80) // 3
    x = 30
    y0 = y + 40
    for label, value, color in cards:
        draw.rounded_rectangle([x, y0, x + card_w, y0 + 160], radius=12, outline=color, width=3)
        draw.text((x + 15, y0 + 20), label, font=_font(13), fill=COLOR_MUTED)
        draw.text((x + 15, y0 + 60), value, font=_font(24, bold=True), fill=color)
        x += card_w + 20

    draw.text((30, y0 + 190), f"Toplam Kayıt Sayısı: {metrikler['kayit_sayisi']}", font=_font(14), fill=COLOR_TEXT)
    return img


def excel_diff_jpg(eklenen: list, silinen: list, width=800, height=None) -> Image.Image:
    """Ekran 5: Admin Excel senkronizasyon fark raporu."""
    n_lines = max(len(eklenen), len(silinen), 1)
    height = height or (160 + min(n_lines, 20) * 22)
    img = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(img)
    y = _draw_header(draw, width, "🔐 Excel Senkronizasyon Fark Raporu",
                      subtitle=f"Rapor Tarihi: {datetime.now():%d.%m.%Y %H:%M}")

    col2_x = width // 2 + 10
    y0 = y + 25
    draw.text((30, y0), f"➕ Eklenen Sahalar ({len(eklenen)})", font=_font(15, bold=True), fill=COLOR_GREEN)
    draw.text((col2_x, y0), f"➖ Silinen Sahalar ({len(silinen)})", font=_font(15, bold=True), fill=COLOR_RED)
    y0 += 30

    for i in range(min(20, n_lines)):
        if i < len(eklenen):
            draw.text((30, y0), f"• {eklenen[i][:35]}", font=_font(13), fill=COLOR_TEXT)
        if i < len(silinen):
            draw.text((col2_x, y0), f"• {silinen[i][:35]}", font=_font(13), fill=COLOR_TEXT)
        y0 += 22

    if n_lines > 20:
        draw.text((30, y0 + 5), f"... ve {n_lines - 20} kayıt daha (detaylar için Excel çıktısına bakınız)", font=_font(12), fill=COLOR_MUTED)

    return img


def image_to_bytes(img: Image.Image, quality=92) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()

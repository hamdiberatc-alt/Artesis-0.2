#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ARTE TERAPİ — Klinik Yönetim Sistemi v3.13.0
"""
import sqlite3, json, os, sys, webbrowser, threading, urllib.parse, calendar, socket, shutil
from datetime import datetime, date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def get_app_dir():
    if os.name == 'nt':
        base = os.getenv('APPDATA') or os.path.expanduser('~')
        app_dir = os.path.join(base, 'ArteTerapi')
    else:
        app_dir = os.path.join(os.path.expanduser('~'), '.arteterapi')
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

CLOUD_MODE = os.getenv('ARTE_CLOUD', '') == '1' or os.getenv('VERCEL', '') == '1'

def resolve_db_path():
    if CLOUD_MODE:
        return 'cloud://arteterapi'
    env_path = os.getenv('ARTE_DB_PATH', '').strip()
    if env_path:
        custom = os.path.abspath(env_path)
        os.makedirs(os.path.dirname(custom), exist_ok=True)
        return custom

    new_path = os.path.join(get_app_dir(), 'arteterapi.db')
    legacy_candidates = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    legacy_candidates.append(os.path.join(script_dir, 'arteterapi.db'))
    cwd = os.path.abspath(os.getcwd())
    if cwd != script_dir:
        legacy_candidates.append(os.path.join(cwd, 'arteterapi.db'))

    # Yeni sabit konum varsa onu kullan
    if os.path.exists(new_path):
        return new_path

    # Eski konumda db varsa otomatik taşı/kopyala
    for cand in legacy_candidates:
        if os.path.exists(cand) and os.path.getsize(cand) > 0:
            try:
                source = sqlite3.connect(cand)
                target = sqlite3.connect(new_path)
                try:
                    source.backup(target)
                finally:
                    target.close(); source.close()
                return new_path
            except Exception:
                return cand

    return new_path

DB_PATH = resolve_db_path()
PORT = 5679
APP_VERSION = '3.5.2'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def q(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def parse_iso_date(value, fallback=None):
    fallback = fallback or date.today()
    if not value:
        return fallback
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return fallback
    text = text[:10]
    try:
        return datetime.strptime(text, '%Y-%m-%d').date()
    except Exception:
        return fallback

WEEKDAY_NAMES = ['Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar']
WEEKDAY_SHORT = ['Pzt','Sal','Çar','Per','Cum','Cmt','Paz']

def haftalik_meta(week_start=None):
    base = parse_iso_date(week_start, date.today())
    monday = base - timedelta(days=base.weekday())
    sunday = monday + timedelta(days=6)
    days = []
    for i in range(7):
        dt = monday + timedelta(days=i)
        days.append({'index': i, 'date': dt.isoformat(), 'label': dt.strftime('%d.%m'), 'day_name': WEEKDAY_SHORT[i], 'full_name': WEEKDAY_NAMES[i]})
    hours = [f"{h:02d}:00" for h in range(8, 21)]
    return monday, sunday, days, hours

def init_db():
    conn = get_db(); c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS terapistler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        renk TEXT DEFAULT '#f5b800',
        uzmanlik TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS hizmet_alanlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        terapist_id INTEGER NOT NULL,
        alan_adi TEXT NOT NULL,
        kategori TEXT DEFAULT 'ftr',
        seans_ucreti REAL DEFAULT 0,
        paket_mi INTEGER DEFAULT 0,
        paket_seans INTEGER DEFAULT 8,
        paket_hafta INTEGER DEFAULT 6,
        bireysel_fiyat REAL DEFAULT 0,
        grup2_fiyat REAL DEFAULT 0,
        grup3_fiyat REAL DEFAULT 0,
        terapist_prim_orani REAL DEFAULT 0,
        aktif INTEGER DEFAULT 1,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
    CREATE TABLE IF NOT EXISTS danisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        terapist_id INTEGER NOT NULL,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        telefon TEXT DEFAULT '',
        dogum_tarihi TEXT DEFAULT '',
        tckn TEXT DEFAULT '',
        cinsiyet TEXT DEFAULT '',
        meslek TEXT DEFAULT '',
        tani TEXT DEFAULT '',
        sikayet TEXT DEFAULT '',
        hedefler TEXT DEFAULT '',
        notlar TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        kayit_tarihi TEXT DEFAULT (date('now','localtime')),
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
    CREATE TABLE IF NOT EXISTS seanslar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        tarih TEXT NOT NULL,
        tip TEXT DEFAULT 'normal',
        grup_turu TEXT DEFAULT 'bireysel',
        ucret REAL DEFAULT 0,
        terapist_payi REAL DEFAULT 0,
        isletme_payi REAL DEFAULT 0,
        indirimli INTEGER DEFAULT 0,
        ucret_alindi INTEGER DEFAULT 0,
        tahsilat_tarihi TEXT DEFAULT '',
        soap_s TEXT DEFAULT '',
        soap_o TEXT DEFAULT '',
        soap_a TEXT DEFAULT '',
        soap_p TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id),
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
    CREATE TABLE IF NOT EXISTS gelisim_notlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        tur TEXT DEFAULT 'genel',
        metin TEXT NOT NULL,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id)
    );
    CREATE TABLE IF NOT EXISTS danisan_raporlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        baslik TEXT NOT NULL,
        icerik TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id)
    );
    CREATE TABLE IF NOT EXISTS odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        tutar REAL NOT NULL,
        yontem TEXT DEFAULT 'nakit',
        notlar TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS giderler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        kategori TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS kasa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        tur TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT DEFAULT '',
        kaynak TEXT DEFAULT 'manuel'
    );
    CREATE TABLE IF NOT EXISTS randevular (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        tarih TEXT NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        durum TEXT DEFAULT 'bekliyor',
        notlar TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id),
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
    CREATE TABLE IF NOT EXISTS haftalik_program_sablonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        gun_index INTEGER NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        oda_id INTEGER,
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE CASCADE,
        FOREIGN KEY(hizmet_id) REFERENCES hizmet_alanlari(id),
        FOREIGN KEY(oda_id) REFERENCES odalar(id)
    );
    CREATE TABLE IF NOT EXISTS odalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL UNIQUE,
        renk TEXT DEFAULT '#64748b',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS danisan_terapistler (
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        rol TEXT DEFAULT 'ek',
        PRIMARY KEY (danisan_id, terapist_id),
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS mesaj_sablonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kod TEXT UNIQUE,
        ad TEXT NOT NULL,
        kanal TEXT DEFAULT 'whatsapp',
        konu TEXT DEFAULT '',
        metin TEXT NOT NULL,
        sistem INTEGER DEFAULT 0,
        aktif INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS mesaj_kayitlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        kanal TEXT NOT NULL,
        hedef_turu TEXT DEFAULT '',
        hedef_id INTEGER,
        hedef_ad TEXT DEFAULT '',
        hedef_iletisim TEXT DEFAULT '',
        konu TEXT DEFAULT '',
        metin TEXT DEFAULT '',
        durum TEXT DEFAULT 'hazirlandi',
        meta_json TEXT DEFAULT ''
    );
    """)
    # Şema güncellemeleri
    mevcut_cols = [r['name'] for r in q(conn, "PRAGMA table_info(seanslar)")]
    if 'saat' not in mevcut_cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN saat TEXT DEFAULT ''")
    if 'sure_dk' not in mevcut_cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN sure_dk INTEGER DEFAULT 45")
    if 'oda_id' not in mevcut_cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN oda_id INTEGER")
    if 'ucret_alindi' not in mevcut_cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN ucret_alindi INTEGER DEFAULT 0")
    if 'tahsilat_tarihi' not in mevcut_cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN tahsilat_tarihi TEXT DEFAULT ''")
    mevcut_cols_r = [r['name'] for r in q(conn, "PRAGMA table_info(randevular)")]
    if 'oda_id' not in mevcut_cols_r:
        c.execute("ALTER TABLE randevular ADD COLUMN oda_id INTEGER")
    mevcut_cols_h = [r['name'] for r in q(conn, "PRAGMA table_info(hizmet_alanlari)")]
    if 'takvim_rengi' not in mevcut_cols_h:
        c.execute("ALTER TABLE hizmet_alanlari ADD COLUMN takvim_rengi TEXT DEFAULT '#3b82f6'")
    mevcut_cols_d = [r['name'] for r in q(conn, "PRAGMA table_info(danisanlar)")]
    if 'pilates_baslangic_tarihi' not in mevcut_cols_d:
        c.execute("ALTER TABLE danisanlar ADD COLUMN pilates_baslangic_tarihi TEXT DEFAULT ''")
    if 'pilates_paket_odendi' not in mevcut_cols_d:
        c.execute("ALTER TABLE danisanlar ADD COLUMN pilates_paket_odendi INTEGER DEFAULT 0")
    if 'pilates_paket_odeme_tarihi' not in mevcut_cols_d:
        c.execute("ALTER TABLE danisanlar ADD COLUMN pilates_paket_odeme_tarihi TEXT DEFAULT ''")
    if 'email' not in mevcut_cols_d:
        c.execute("ALTER TABLE danisanlar ADD COLUMN email TEXT DEFAULT ''")
    # Varsayılan ayarlar
    c.execute("INSERT OR IGNORE INTO ayarlar(anahtar,deger) VALUES('tema','sari')")
    c.execute("INSERT OR IGNORE INTO ayarlar(anahtar,deger) VALUES('klinik_adi','Arte Terapi')")
    c.execute("INSERT OR IGNORE INTO ayarlar(anahtar,deger) VALUES('ozel_renk','#f5b800')")
    c.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES('app_version',?)", (APP_VERSION,))
    c.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES('db_path',?)", (DB_PATH,))

    c.execute("SELECT COUNT(*) FROM mesaj_sablonlari")
    if c.fetchone()[0] == 0:
        varsayilan_sablonlar = [
            ('randevu_wp', 'Randevu Hatırlatma', 'whatsapp', '', 'Merhaba {ad}, {tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır. Uygun değilseniz lütfen bize haber verin. {klinik}', 1),
            ('randevu_mail', 'Randevu Hatırlatma', 'email', 'Randevu Hatırlatma | {klinik}', 'Merhaba {ad},\n\n{tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır.\n{oda_satiri}\nUygun değilseniz lütfen bize dönüş yapın.\n\n{klinik}', 1),
            ('pilates_wp', 'Pilates Paket Uyarısı', 'whatsapp', '', 'Merhaba {ad}, pilates paketinizde {kalan_seans} seans ve {kalan_gun} gün kaldı. Paket bitiş tarihiniz: {bitis_tarihi}. Uygun gününüzü planlamak için bize yazabilirsiniz. {klinik}', 1),
            ('toplu_duyuru_mail', 'Toplu Bilgilendirme', 'email', '{klinik} Bilgilendirme', 'Merhaba {ad},\n\n{icerik}\n\n{klinik}', 1),
        ]
        c.executemany("INSERT INTO mesaj_sablonlari(kod,ad,kanal,konu,metin,sistem) VALUES(?,?,?,?,?,?)", varsayilan_sablonlar)

    # Varsayılan odalar
    c.execute("SELECT COUNT(*) FROM odalar")
    if c.fetchone()[0] == 0:
        for ad, renk in [('Oda 1','#3b82f6'),('Oda 2','#10b981'),('Pilates Stüdyosu','#8b5cf6')]:
            c.execute("INSERT INTO odalar(ad,renk) VALUES(?,?)", (ad, renk))

    # Varsayılan terapistler
    c.execute("SELECT COUNT(*) FROM terapistler")
    if c.fetchone()[0] == 0:
        terapistler_data = [
            ("Terapist 1", "#e67e22", "Bobath, HEP, Duyu Bütünleme"),
            ("Terapist 2",  "#2980b9", "Nöroloji, Ortopedi, Masaj, Pediatri"),
            ("Terapist 3",  "#8e44ad", "Nöroloji, Ortopedi, Masaj, Pilates"),
        ]
        for ad, renk, uzm in terapistler_data:
            c.execute("INSERT INTO terapistler(ad,renk,uzmanlik) VALUES(?,?,?)", (ad, renk, uzm))
        conn.commit()

        c.execute("SELECT id,ad FROM terapistler ORDER BY id")
        tlist = c.fetchall()
        sid_id = tlist[0][0]  # Terapist 1
        ber_id = tlist[1][0]  # Terapist 2
        sim_id = tlist[2][0]  # Terapist 3

        hizmetler_data = [
            # Terapist 1
            (sid_id, "Bobath Seansı",        "ftr",     0, 1, 1, 3000, 0, 0, 0.0),
            (sid_id, "HEP Seansı",           "ftr",     0, 1, 1, 3000, 0, 0, 0.0),
            (sid_id, "Duyu Bütünleme",       "ftr",     0, 1, 1, 3000, 0, 0, 0.0),
            # Terapist 2
            (ber_id, "Nöroloji Seansı",      "ftr",     0, 1, 1, 2000, 1500, 0, 0.0),
            (ber_id, "Ortopedi Seansı",      "ftr",     0, 1, 1, 2000, 1500, 0, 0.0),
            (ber_id, "Masaj Seansı",         "masaj",   0, 1, 1, 2000, 1500, 0, 0.0),
            (ber_id, "Pediatri Seansı",      "ftr",     0, 1, 1, 2000, 1500, 0, 0.0),
            # Terapist 3
            (sim_id, "Nöroloji FTR",         "ftr",     0, 1, 1, 2000, 0, 0, 0.5),
            (sim_id, "Ortopedi FTR",         "ftr",     0, 1, 1, 2000, 0, 0, 0.5),
            (sim_id, "Masaj Seansı",         "masaj",   0, 1, 1, 2000, 0, 0, 0.5),
            (sim_id, "Pilates (Bireysel)",   "pilates", 1, 8, 6, 6400, 0, 0, 0.4),
            (sim_id, "Pilates (2 Kişi)",     "pilates", 1, 8, 6, 0, 4000, 0, 0.4),
            (sim_id, "Pilates (3 Kişi)",     "pilates", 1, 8, 6, 0, 0, 3200, 0.4),
        ]
        for h in hizmetler_data:
            c.execute("""INSERT INTO hizmet_alanlari
                (terapist_id,alan_adi,kategori,paket_mi,paket_seans,paket_hafta,
                 seans_ucreti,grup2_fiyat,grup3_fiyat,terapist_prim_orani)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", h)
    conn.commit(); conn.close()

# ── AYARLAR ──────────────────────────────────────────────────────────────────────
def ayar_al(anahtar, varsayilan=''):
    conn = get_db()
    r = q(conn, "SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,))
    conn.close()
    return r[0]['deger'] if r else varsayilan

def ayar_kaydet(anahtar, deger):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES(?,?)", (anahtar, deger))
    conn.commit(); conn.close()

def tum_ayarlar():
    conn = get_db()
    r = {row['anahtar']: row['deger'] for row in conn.execute("SELECT * FROM ayarlar").fetchall()}
    conn.close(); return r

def erisim_bilgisi():
    hosts = get_local_ips()
    return {
        'port': PORT,
        'hosts': hosts,
        'urls': [f"http://{ip}:{PORT}" for ip in hosts],
        'db_path': DB_PATH
    }

def _turkiye_tel_normalize(tel):
    digits = ''.join(ch for ch in str(tel or '') if ch.isdigit())
    if not digits:
        return ''
    if digits.startswith('90') and len(digits) >= 12:
        return digits
    if digits.startswith('0') and len(digits) >= 11:
        return '90' + digits[1:]
    if len(digits) == 10:
        return '90' + digits
    return digits

def mesaj_sablonlari_listesi(kanal=None):
    conn = get_db()
    sql = "SELECT * FROM mesaj_sablonlari WHERE aktif=1"
    p = []
    if kanal:
        sql += " AND kanal=?"
        p.append(kanal)
    rows = q(conn, sql + " ORDER BY sistem DESC, ad", p)
    conn.close()
    return rows

def mesaj_sablon_kaydet(d):
    conn = get_db(); c = conn.cursor()
    if d.get('id'):
        c.execute("UPDATE mesaj_sablonlari SET ad=?, kanal=?, konu=?, metin=?, aktif=? WHERE id=?",
                  (d.get('ad',''), d.get('kanal','whatsapp'), d.get('konu',''), d.get('metin',''), d.get('aktif',1), d['id']))
        lid = d['id']
    else:
        kod = d.get('kod') or ('user_' + datetime.now().strftime('%Y%m%d%H%M%S%f'))
        c.execute("INSERT INTO mesaj_sablonlari(kod,ad,kanal,konu,metin,sistem,aktif) VALUES(?,?,?,?,?,?,?)",
                  (kod, d.get('ad','Yeni Şablon'), d.get('kanal','whatsapp'), d.get('konu',''), d.get('metin',''), 0, d.get('aktif',1)))
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid

def mesaj_loglari_listesi(limit=120):
    conn = get_db()
    rows = q(conn, "SELECT * FROM mesaj_kayitlari ORDER BY datetime(tarih) DESC, id DESC LIMIT ?", (limit,))
    conn.close()
    return rows

def mesaj_log_ekle(data):
    kayitlar = data.get('kayitlar') if isinstance(data, dict) else None
    if not kayitlar:
        kayitlar = [data]
    conn = get_db(); c = conn.cursor(); sayi = 0
    for item in kayitlar:
        c.execute("""INSERT INTO mesaj_kayitlari
            (tarih,kanal,hedef_turu,hedef_id,hedef_ad,hedef_iletisim,konu,metin,durum,meta_json)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (item.get('tarih') or datetime.now().isoformat(timespec='seconds'),
             item.get('kanal','whatsapp'), item.get('hedef_turu',''), item.get('hedef_id'),
             item.get('hedef_ad',''), item.get('hedef_iletisim',''), item.get('konu',''),
             item.get('metin',''), item.get('durum','hazirlandi'), json.dumps(item.get('meta',{}), ensure_ascii=False)))
        sayi += 1
    conn.commit(); conn.close(); return sayi

def planli_program_tarih_araligi(start_date, end_date, terapist_id=None):
    conn = get_db()
    sql = """SELECT ws.id as plan_id, ws.gun_index, ws.saat, ws.sure_dk, ws.notlar,
        d.id as danisan_id, d.ad, d.soyad, d.telefon, COALESCE(d.email,'') as email,
        t.id as terapist_id, t.ad as terapist_adi,
        h.alan_adi as hizmet_adi, COALESCE(h.takvim_rengi,'#3b82f6') as hizmet_renk,
        o.ad as oda_adi
        FROM haftalik_program_sablonlari ws
        JOIN danisanlar d ON d.id=ws.danisan_id
        JOIN terapistler t ON t.id=ws.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=ws.hizmet_id
        LEFT JOIN odalar o ON o.id=ws.oda_id
        WHERE ws.aktif=1"""
    p = []
    if terapist_id:
        sql += " AND ws.terapist_id=?"
        p.append(terapist_id)
    rows = q(conn, sql, p)
    conn.close()
    gun_map = {}
    for r in rows:
        gun_map.setdefault(int(r.get('gun_index') or 0), []).append(r)
    start_dt = parse_iso_date(start_date)
    end_dt = parse_iso_date(end_date, start_dt)
    items = []
    cur = start_dt
    while cur <= end_dt:
        for r in gun_map.get(cur.weekday(), []):
            x = dict(r)
            x['tarih'] = cur.isoformat()
            x['danisan_adi'] = ((r.get('ad') or '') + ' ' + (r.get('soyad') or '')).strip()
            items.append(x)
        cur += timedelta(days=1)
    items.sort(key=lambda x: (x.get('tarih',''), x.get('saat',''), x.get('danisan_adi','')))
    return items

def mesaj_hedefleri_listesi(tip='yarin_randevu', terapist_id=None, tarih=None, week_start=None):
    conn = get_db()
    klinik = ayar_al('klinik_adi', 'Arte Terapi')
    ref = parse_iso_date(tarih, date.today())
    if tip == 'yarin_randevu':
        bas = ref + timedelta(days=1); bit = bas
    elif tip == 'bugun_randevu':
        bas = ref; bit = ref
    elif tip == 'hafta_randevu':
        bas, son, _, _ = haftalik_meta(week_start or ref.isoformat()); bit = son
    elif tip == 'bugun_planli':
        bas = ref; bit = ref
    elif tip == 'hafta_planli':
        bas, son, _, _ = haftalik_meta(week_start or ref.isoformat()); bit = son
    else:
        bas = ref; bit = ref

    items = []
    if tip in ('bugun_randevu','yarin_randevu','hafta_randevu'):
        sql = """SELECT r.id as kaynak_id, 'randevu' as kaynak, r.tarih, r.saat, r.notlar,
            d.id as danisan_id, d.ad, d.soyad, d.telefon, COALESCE(d.email,'') as email,
            t.id as terapist_id, t.ad as terapist_adi,
            h.alan_adi as hizmet_adi, o.ad as oda_adi
            FROM randevular r
            JOIN danisanlar d ON d.id=r.danisan_id
            JOIN terapistler t ON t.id=r.terapist_id
            LEFT JOIN hizmet_alanlari h ON h.id=r.hizmet_id
            LEFT JOIN odalar o ON o.id=r.oda_id
            WHERE date(r.tarih) BETWEEN date(?) AND date(?)"""
        p = [bas.isoformat(), bit.isoformat()]
        if terapist_id:
            sql += " AND r.terapist_id=?"
            p.append(terapist_id)
        rows = q(conn, sql + " ORDER BY date(r.tarih), COALESCE(r.saat,'')", p)
        for r in rows:
            x = dict(r)
            x['danisan_adi'] = ((r.get('ad') or '') + ' ' + (r.get('soyad') or '')).strip()
            x['telefon_norm'] = _turkiye_tel_normalize(r.get('telefon'))
            x['klinik'] = klinik
            x['oda_satiri'] = f"Oda: {r.get('oda_adi')}" if r.get('oda_adi') else ''
            items.append(x)
    elif tip in ('bugun_planli','hafta_planli'):
        for r in planli_program_tarih_araligi(bas.isoformat(), bit.isoformat(), terapist_id):
            x = dict(r)
            x['kaynak'] = 'planli'
            x['kaynak_id'] = r.get('plan_id')
            x['telefon_norm'] = _turkiye_tel_normalize(r.get('telefon'))
            x['klinik'] = klinik
            x['oda_satiri'] = f"Oda: {r.get('oda_adi')}" if r.get('oda_adi') else ''
            items.append(x)
    elif tip == 'pilates_uyari':
        conn.close()
        rows = pilates_ozet()
        for r in rows:
            if int(r.get('kalan_seans') or 0) <= 0:
                continue
            if int(r.get('kalan_gun') or 0) > 7 and int(r.get('kalan_seans') or 0) > 2:
                continue
            x = {
                'kaynak':'pilates', 'kaynak_id':r.get('danisan_id'), 'tarih':r.get('bitis_tarihi',''), 'saat':'',
                'danisan_id':r.get('danisan_id'), 'danisan_adi':r.get('danisan_adi'), 'telefon':r.get('telefon',''),
                'email':r.get('email',''), 'telefon_norm':_turkiye_tel_normalize(r.get('telefon')), 'terapist_adi':r.get('terapist_adi',''),
                'hizmet_adi':'Pilates Paketi', 'oda_adi':'', 'klinik':klinik, 'oda_satiri':'',
                'kalan_seans':r.get('kalan_seans'), 'kalan_gun':r.get('kalan_gun'), 'bitis_tarihi':r.get('bitis_tarihi')
            }
            items.append(x)
        return {'tip': tip, 'items': items, 'count': len(items)}

    conn.close()
    return {'tip': tip, 'items': items, 'count': len(items)}

# ── TERAPİST ─────────────────────────────────────────────────────────────────────
def terapistler_listesi():
    conn = get_db()
    rows = q(conn, "SELECT * FROM terapistler WHERE aktif=1 ORDER BY ad")
    conn.close(); return rows

def terapist_ekle(d):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO terapistler(ad,soyad,renk,uzmanlik,notlar) VALUES(?,?,?,?,?)",
              (d['ad'], d.get('soyad',''), d.get('renk','#f5b800'), d.get('uzmanlik',''), d.get('notlar','')))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def terapist_guncelle(d):
    conn = get_db()
    conn.execute("UPDATE terapistler SET ad=?,soyad=?,renk=?,uzmanlik=?,notlar=?,aktif=? WHERE id=?",
                 (d['ad'], d.get('soyad',''), d.get('renk','#f5b800'), d.get('uzmanlik',''),
                  d.get('notlar',''), d.get('aktif',1), d['id']))
    conn.commit(); conn.close()

def odalar_listesi():
    conn = get_db()
    rows = q(conn, "SELECT * FROM odalar WHERE aktif=1 ORDER BY ad")
    conn.close(); return rows

def _danisan_terapistleri_yaz(conn, danisan_id, primary_terapist_id, terapist_ids=None):
    ids = set()
    if primary_terapist_id:
        ids.add(int(primary_terapist_id))
    for tid in (terapist_ids or []):
        if tid not in (None, '', 0, '0'):
            ids.add(int(tid))
    conn.execute("DELETE FROM danisan_terapistler WHERE danisan_id=?", (danisan_id,))
    for tid in ids:
        rol = 'primary' if int(tid) == int(primary_terapist_id) else 'ek'
        conn.execute("INSERT OR IGNORE INTO danisan_terapistler(danisan_id,terapist_id,rol) VALUES(?,?,?)", (danisan_id, tid, rol))

# ── HİZMET ALANLARI ──────────────────────────────────────────────────────────────
def hizmetler_listesi(terapist_id=None):
    conn = get_db()
    sql = """SELECT h.*, t.ad as terapist_adi FROM hizmet_alanlari h
             LEFT JOIN terapistler t ON t.id=h.terapist_id WHERE h.aktif=1"""
    p = []
    if terapist_id:
        sql += " AND h.terapist_id=?"; p.append(terapist_id)
    rows = q(conn, sql + " ORDER BY h.terapist_id, h.alan_adi", p)
    conn.close(); return rows

def hizmet_ekle(d):
    conn = get_db(); c = conn.cursor()
    seans_ucreti = d.get('seans_ucreti', d.get('bireysel_fiyat', 0) or 0)
    c.execute("""INSERT INTO hizmet_alanlari
        (terapist_id,alan_adi,kategori,paket_mi,paket_seans,paket_hafta,
         seans_ucreti,bireysel_fiyat,grup2_fiyat,grup3_fiyat,terapist_prim_orani,takvim_rengi,aktif)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d['terapist_id'], d['alan_adi'], d.get('kategori','ftr'), d.get('paket_mi',0),
         d.get('paket_seans',1), d.get('paket_hafta',1), seans_ucreti, seans_ucreti,
         d.get('grup2_fiyat',0), d.get('grup3_fiyat',0), d.get('terapist_prim_orani',0),
         d.get('takvim_rengi','#3b82f6'), d.get('aktif',1)))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def hizmet_guncelle(d):
    conn = get_db()
    seans_ucreti = d.get('seans_ucreti', d.get('bireysel_fiyat', 0) or 0)
    conn.execute("""UPDATE hizmet_alanlari SET terapist_id=?, alan_adi=?,kategori=?,paket_mi=?,paket_seans=?,
        paket_hafta=?,seans_ucreti=?,bireysel_fiyat=?,grup2_fiyat=?,grup3_fiyat=?,terapist_prim_orani=?,takvim_rengi=?,aktif=?
        WHERE id=?""",
        (d.get('terapist_id'), d['alan_adi'], d.get('kategori','ftr'), d.get('paket_mi',0), d.get('paket_seans',1),
         d.get('paket_hafta',1), seans_ucreti, seans_ucreti, d.get('grup2_fiyat',0),
         d.get('grup3_fiyat',0), d.get('terapist_prim_orani',0), d.get('takvim_rengi','#3b82f6'),
         d.get('aktif',1), d['id']))
    conn.commit(); conn.close()

# ── DANIŞAN ───────────────────────────────────────────────────────────────────────
def danisanlar_listesi(terapist_id=None, arama=''):
    conn = get_db()
    sql = """SELECT d.*,
        (SELECT COUNT(*) FROM seanslar WHERE danisan_id=d.id) as toplam_seans,
        (SELECT COUNT(*) FROM seanslar WHERE danisan_id=d.id
         AND strftime('%Y-%m',tarih)=strftime('%Y-%m','now','localtime')) as bu_ay_seans,
        (SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE danisan_id=d.id) as toplam_odeme,
        t.ad as terapist_adi, t.renk as terapist_renk,
        (SELECT GROUP_CONCAT(tt.ad, ', ') FROM danisan_terapistler dt
         JOIN terapistler tt ON tt.id=dt.terapist_id
         WHERE dt.danisan_id=d.id) as terapistler
        FROM danisanlar d LEFT JOIN terapistler t ON t.id=d.terapist_id
        WHERE d.aktif=1"""
    p = []
    if terapist_id:
        sql += " AND (d.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=d.id AND dt.terapist_id=?))"
        p.extend([terapist_id, terapist_id])
    if arama:
        sql += " AND (d.ad||' '||d.soyad LIKE ? OR d.telefon LIKE ? OR d.tckn LIKE ?)"
        p += [f'%{arama}%', f'%{arama}%', f'%{arama}%']
    rows = q(conn, sql + " ORDER BY d.ad, d.soyad", p)
    conn.close(); return rows

def danisan_detay(did):
    conn = get_db()
    d = q(conn, "SELECT d.*, t.ad as terapist_adi FROM danisanlar d LEFT JOIN terapistler t ON t.id=d.terapist_id WHERE d.id=?", (did,))
    if not d:
        conn.close(); return None
    d = d[0]
    d['terapistler'] = q(conn, """SELECT t.id, t.ad, t.soyad, t.renk, dt.rol
        FROM danisan_terapistler dt JOIN terapistler t ON t.id=dt.terapist_id
        WHERE dt.danisan_id=? ORDER BY CASE WHEN dt.rol='primary' THEN 0 ELSE 1 END, t.ad""", (did,))
    d['seanslar'] = q(conn, """SELECT s.*, h.alan_adi as hizmet_adi
        FROM seanslar s LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        WHERE s.danisan_id=? ORDER BY s.tarih DESC LIMIT 60""", (did,))
    d['gelisim_notlari'] = q(conn, "SELECT * FROM gelisim_notlari WHERE danisan_id=? ORDER BY tarih DESC", (did,))
    d['raporlar'] = q(conn, "SELECT * FROM danisan_raporlar WHERE danisan_id=? ORDER BY tarih DESC", (did,))
    d['odemeler'] = q(conn, "SELECT * FROM odemeler WHERE danisan_id=? ORDER BY tarih DESC", (did,))
    conn.close(); return d

def danisan_ekle(d):
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO danisanlar
        (terapist_id,ad,soyad,telefon,email,dogum_tarihi,tckn,cinsiyet,meslek,tani,sikayet,hedefler,notlar,pilates_baslangic_tarihi,pilates_paket_odendi,pilates_paket_odeme_tarihi)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (d['terapist_id'], d['ad'], d.get('soyad',''), d.get('telefon',''), d.get('email',''), d.get('dogum_tarihi',''),
         d.get('tckn',''), d.get('cinsiyet',''), d.get('meslek',''), d.get('tani',''),
         d.get('sikayet',''), d.get('hedefler',''), d.get('notlar',''), d.get('pilates_baslangic_tarihi',''),
         d.get('pilates_paket_odendi',0), d.get('pilates_paket_odeme_tarihi','')))
    conn.commit(); lid = c.lastrowid
    _danisan_terapistleri_yaz(conn, lid, d['terapist_id'], d.get('terapist_ids') or [])
    conn.commit(); conn.close(); return lid

def danisan_guncelle(d):
    conn = get_db()
    conn.execute("""UPDATE danisanlar SET terapist_id=?,ad=?,soyad=?,telefon=?,email=?,dogum_tarihi=?,
        tckn=?,cinsiyet=?,meslek=?,tani=?,sikayet=?,hedefler=?,notlar=?,aktif=?,pilates_baslangic_tarihi=? WHERE id=?""",
        (d.get('terapist_id'), d['ad'], d.get('soyad',''), d.get('telefon',''), d.get('email',''), d.get('dogum_tarihi',''),
         d.get('tckn',''), d.get('cinsiyet',''), d.get('meslek',''), d.get('tani',''),
         d.get('sikayet',''), d.get('hedefler',''), d.get('notlar',''), d.get('aktif',1), d.get('pilates_baslangic_tarihi',''), d['id']))
    _danisan_terapistleri_yaz(conn, d['id'], d.get('terapist_id'), d.get('terapist_ids') or [])
    conn.commit(); conn.close()

def danisan_sil(did):
    conn = get_db()
    odeme_ids = [r['id'] for r in q(conn, "SELECT id FROM odemeler WHERE danisan_id=?", (did,))]
    conn.close()
    for oid in odeme_ids:
        odeme_sil(oid)
    conn = get_db()
    for t in ['randevular','seanslar','gelisim_notlari','danisan_raporlar']:
        conn.execute(f"DELETE FROM {t} WHERE danisan_id=?", (did,))
    conn.execute("DELETE FROM danisanlar WHERE id=?", (did,))
    conn.commit(); conn.close()

# ── SEANS ─────────────────────────────────────────────────────────────────────────
def _ucret_hesapla(hizmet, grup_turu, indirimli):
    if not hizmet: return 0.0, 0.0, 0.0
    if hizmet.get('paket_mi'):
        fiyat_map = {'bireysel': hizmet['seans_ucreti'] or hizmet['bireysel_fiyat'],
                     'grup2': hizmet['grup2_fiyat'], 'grup3': hizmet['grup3_fiyat']}
        toplam = fiyat_map.get(grup_turu, hizmet['seans_ucreti'] or 0)
        ucret = round(toplam / (hizmet['paket_seans'] or 1), 2)
    else:
        if indirimli and hizmet.get('grup2_fiyat', 0) > 0:
            ucret = hizmet['grup2_fiyat']
        else:
            ucret = hizmet['seans_ucreti'] or hizmet.get('bireysel_fiyat', 0) or 0
    t_pay = round(float(ucret) * float(hizmet.get('terapist_prim_orani', 0) or 0), 2)
    i_pay = round(float(ucret) - t_pay, 2)
    return float(ucret), t_pay, i_pay

def seans_ekle(danisan_id, terapist_id, hizmet_id, tarih, tip='normal',
               grup_turu='bireysel', indirimli=0, soap=None, saat='', sure_dk=45, oda_id=None,
               ucret_alindi=0, tahsilat_tarihi=''):
    conn = get_db(); c = conn.cursor()
    h_list = q(conn, "SELECT * FROM hizmet_alanlari WHERE id=?", (hizmet_id,)) if hizmet_id else []
    h = h_list[0] if h_list else None
    ucret, t_pay, i_pay = _ucret_hesapla(h, grup_turu, indirimli)
    if soap is None:
        soap = {}
    elif isinstance(soap, str):
        # Geriye dönük uyumluluk: bazı akışlar SOAP alanını düz metin gönderiyor.
        soap = {'s': soap, 'o': '', 'a': '', 'p': ''}
    elif not isinstance(soap, dict):
        soap = dict(soap) if hasattr(soap, 'items') else {'s': str(soap), 'o': '', 'a': '', 'p': ''}
    ucret_alindi = 1 if str(ucret_alindi) in ('1', 'True', 'true', 'on') or ucret_alindi is True else 0
    tahsilat_tarihi = (tahsilat_tarihi or '').strip()
    if ucret_alindi and not tahsilat_tarihi:
        tahsilat_tarihi = tarih
    if not ucret_alindi:
        tahsilat_tarihi = ''
    c.execute("SELECT id FROM seanslar WHERE danisan_id=? AND terapist_id=? AND tarih=? AND COALESCE(saat,'')=COALESCE(?, '')",
              (danisan_id, terapist_id, tarih, saat))
    mevcut = c.fetchone()
    if mevcut:
        c.execute("""UPDATE seanslar SET hizmet_id=?,tip=?,grup_turu=?,ucret=?,
            terapist_payi=?,isletme_payi=?,indirimli=?,ucret_alindi=?,tahsilat_tarihi=?,
            soap_s=?,soap_o=?,soap_a=?,soap_p=?, saat=?, sure_dk=?, oda_id=? WHERE id=?""",
            (hizmet_id, tip, grup_turu, ucret, t_pay, i_pay, indirimli, ucret_alindi, tahsilat_tarihi,
             soap.get('s',''), soap.get('o',''), soap.get('a',''), soap.get('p',''),
             saat, sure_dk, oda_id, mevcut['id']))
        lid = mevcut['id']
    else:
        c.execute("""INSERT INTO seanslar
            (danisan_id,terapist_id,hizmet_id,tarih,tip,grup_turu,ucret,
             terapist_payi,isletme_payi,indirimli,ucret_alindi,tahsilat_tarihi,
             soap_s,soap_o,soap_a,soap_p,saat,sure_dk,oda_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (danisan_id, terapist_id, hizmet_id, tarih, tip, grup_turu, ucret,
             t_pay, i_pay, indirimli, ucret_alindi, tahsilat_tarihi,
             soap.get('s',''), soap.get('o',''), soap.get('a',''), soap.get('p',''),
             saat, sure_dk, oda_id))
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid

def seans_sil(seans_id):
    conn = get_db()
    conn.execute("DELETE FROM seanslar WHERE id=?", (seans_id,))
    conn.commit(); conn.close()

def seans_detay(seans_id):
    conn = get_db()
    r = q(conn, """SELECT s.*,
        d.ad||' '||d.soyad as danisan_adi,
        t.ad||CASE WHEN COALESCE(t.soyad,'')<>'' THEN ' '||t.soyad ELSE '' END as terapist_adi,
        h.alan_adi as hizmet_adi,
        h.takvim_rengi
        FROM seanslar s
        LEFT JOIN danisanlar d ON d.id=s.danisan_id
        LEFT JOIN terapistler t ON t.id=s.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        WHERE s.id=?""", (seans_id,))
    conn.close(); return r[0] if r else None

def seans_odeme_durum_guncelle(seans_id, ucret_alindi, tahsilat_tarihi=''):
    conn = get_db()
    row = q(conn, "SELECT tarih FROM seanslar WHERE id=?", (seans_id,))
    if not row:
        conn.close()
        raise ValueError('Seans bulunamadı')
    alindi = 1 if str(ucret_alindi) in ('1','True','true','on') or ucret_alindi is True else 0
    tahsilat_tarihi = (tahsilat_tarihi or '').strip()
    if alindi and not tahsilat_tarihi:
        tahsilat_tarihi = row[0]['tarih']
    if not alindi:
        tahsilat_tarihi = ''
    conn.execute("UPDATE seanslar SET ucret_alindi=?, tahsilat_tarihi=? WHERE id=?", (alindi, tahsilat_tarihi, seans_id))
    conn.commit(); conn.close()
    return {'ok': True}

def aylik_grid(yil, ay, terapist_id):
    conn = get_db()
    terapist_id = str(terapist_id or '')
    ay_str = f"{int(yil):04d}-{int(ay):02d}"
    gun_sayisi = calendar.monthrange(int(yil), int(ay))[1]
    dans = q(conn, """SELECT d.id, d.ad||' '||d.soyad as tam_adi
        FROM danisanlar d
        WHERE d.aktif=1 AND (d.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=d.id AND dt.terapist_id=?))
        ORDER BY d.ad, d.soyad""", (terapist_id, terapist_id))
    seanslar = q(conn, """SELECT s.*, h.takvim_rengi FROM seanslar s
        LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        WHERE s.terapist_id=? AND strftime('%Y-%m',s.tarih)=? ORDER BY s.tarih, COALESCE(s.saat,'')""", (terapist_id, ay_str))
    programlar = haftalik_program_sablonlari_listesi(terapist_id)
    grid = {str(g): {} for g in range(1, gun_sayisi+1)}
    danisan_toplam = {}
    gunluk_toplam = {}
    gunluk_planli = {}

    def ensure_total(did):
        if did not in danisan_toplam:
            danisan_toplam[did] = {'normal':0,'degerlendirme':0,'telafi':0,'planli':0,'toplam':0,'ucret':0.0}

    for s in seanslar:
        gun = str(int(str(s['tarih']).split('-')[2]))
        did = str(s['danisan_id'])
        ensure_total(did)
        grid[gun][did] = {'tip': s['tip'], 'ucret': s['ucret'], 'id': s['id'],
                          'terapist_payi': s['terapist_payi'], 'isletme_payi': s['isletme_payi'],
                          'hizmet_id': s['hizmet_id'], 'grup_turu': s['grup_turu'],
                          'ucret_alindi': s.get('ucret_alindi', 0), 'takvim_rengi': s.get('takvim_rengi') or '',
                          'saat': s.get('saat') or '', 'sure_dk': s.get('sure_dk') or 45,
                          'oda_id': s.get('oda_id')}
        danisan_toplam[did][s['tip']] = danisan_toplam[did].get(s['tip'],0) + 1
        danisan_toplam[did]['toplam'] += 1
        danisan_toplam[did]['ucret'] += float(s['ucret'] or 0)
        gunluk_toplam[gun] = gunluk_toplam.get(gun,0) + 1

    for gun_num in range(1, gun_sayisi+1):
        dt = date(int(yil), int(ay), gun_num)
        day_idx = dt.weekday()
        for pr in programlar:
            if int(pr.get('gun_index') or 0) != day_idx:
                continue
            did = str(pr['danisan_id'])
            gun = str(gun_num)
            ensure_total(did)
            if did in grid[gun]:
                continue
            grid[gun][did] = {
                'tip': 'planli',
                'ucret': 0,
                'id': '',
                'program_id': pr['id'],
                'hizmet_id': pr.get('hizmet_id'),
                'grup_turu': 'bireysel',
                'ucret_alindi': 0,
                'takvim_rengi': pr.get('takvim_rengi') or '',
                'saat': pr.get('saat') or '',
                'sure_dk': pr.get('sure_dk') or 45,
                'oda_id': pr.get('oda_id'),
                'oda_adi': pr.get('oda_adi') or ''
            }
            danisan_toplam[did]['planli'] += 1
            gunluk_planli[gun] = gunluk_planli.get(gun,0) + 1
    conn.close()
    return {'danisanlar': dans, 'grid': grid, 'danisan_toplam': danisan_toplam,
            'gunluk_toplam': gunluk_toplam, 'gunluk_planli': gunluk_planli, 'gun_sayisi': gun_sayisi}


# ── GELİŞİM / RAPOR ──────────────────────────────────────────────────────────────
def gelisim_not_ekle(d):
    conn = get_db(); c = conn.cursor()
    metin = d.get('metin', d.get('icerik', ''))
    c.execute("INSERT INTO gelisim_notlari(danisan_id,terapist_id,tarih,tur,metin) VALUES(?,?,?,?,?)",
              (d['danisan_id'], d.get('terapist_id'), d['tarih'], d.get('tur','genel'), metin))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def gelisim_not_sil(nid):
    conn = get_db(); conn.execute("DELETE FROM gelisim_notlari WHERE id=?", (nid,)); conn.commit(); conn.close()

def rapor_ekle(d):
    conn = get_db(); c = conn.cursor()
    baslik = d.get('baslik', d.get('tur', 'Rapor'))
    icerik = d.get('icerik', d.get('metin', ''))
    c.execute("INSERT INTO danisan_raporlar(danisan_id,terapist_id,tarih,baslik,icerik) VALUES(?,?,?,?,?)",
              (d['danisan_id'], d.get('terapist_id'), d['tarih'], baslik, icerik))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def rapor_sil(rid):
    conn = get_db(); conn.execute("DELETE FROM danisan_raporlar WHERE id=?", (rid,)); conn.commit(); conn.close()

# ── ÖDEME / GİDER / KASA ─────────────────────────────────────────────────────────
def odeme_ekle(d):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO odemeler(danisan_id,terapist_id,tarih,tutar,yontem,notlar) VALUES(?,?,?,?,?,?)",
              (d['danisan_id'], d.get('terapist_id'), d['tarih'], d['tutar'], d.get('yontem','nakit'), d.get('notlar','')))
    lid = c.lastrowid
    dan = q(conn, "SELECT ad||' '||soyad as n FROM danisanlar WHERE id=?", (d['danisan_id'],))
    c.execute("INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak) VALUES(?,?,?,?,?)",
              (d['tarih'], 'giris', d['tutar'], f"Ödeme: {dan[0]['n'] if dan else ''}", 'odeme'))
    conn.commit(); conn.close(); return lid

def odeme_sil(oid):
    conn = get_db()
    o = q(conn, "SELECT * FROM odemeler WHERE id=?", (oid,))
    if o:
        kasa = q(conn, "SELECT id FROM kasa WHERE kaynak='odeme' AND tutar=? AND tarih=? ORDER BY id DESC LIMIT 1", (o[0]['tutar'], o[0]['tarih']))
        if kasa:
            conn.execute("DELETE FROM kasa WHERE id=?", (kasa[0]['id'],))
    conn.execute("DELETE FROM odemeler WHERE id=?", (oid,))
    conn.commit(); conn.close()

def odemeler_listesi(ay=None, terapist_id=None, danisan_id=None):
    conn = get_db()
    sql = "SELECT o.*,d.ad||' '||d.soyad as danisan_adi FROM odemeler o JOIN danisanlar d ON d.id=o.danisan_id WHERE 1=1"
    p = []
    if ay: sql += " AND strftime('%Y-%m',o.tarih)=?"; p.append(ay)
    if terapist_id: sql += " AND o.terapist_id=?"; p.append(terapist_id)
    if danisan_id: sql += " AND o.danisan_id=?"; p.append(danisan_id)
    rows = q(conn, sql+" ORDER BY o.tarih DESC", p); conn.close(); return rows

def gider_ekle(d):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO giderler(tarih,kategori,tutar,aciklama) VALUES(?,?,?,?)",
              (d['tarih'], d['kategori'], d['tutar'], d.get('aciklama','')))
    lid = c.lastrowid
    c.execute("INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak) VALUES(?,?,?,?,?)",
              (d['tarih'], 'cikis', d['tutar'], d.get('aciklama', d['kategori']), 'gider'))
    conn.commit(); conn.close(); return lid

def gider_sil(gid):
    conn = get_db()
    g = q(conn, "SELECT * FROM giderler WHERE id=?", (gid,))
    if g:
        kasa = q(conn, "SELECT id FROM kasa WHERE kaynak='gider' AND tutar=? AND tarih=? ORDER BY id DESC LIMIT 1", (g[0]['tutar'], g[0]['tarih']))
        if kasa:
            conn.execute("DELETE FROM kasa WHERE id=?", (kasa[0]['id'],))
    conn.execute("DELETE FROM giderler WHERE id=?", (gid,)); conn.commit(); conn.close()

def giderler_listesi(ay=None):
    conn = get_db()
    sql = "SELECT * FROM giderler WHERE 1=1"; p = []
    if ay: sql += " AND strftime('%Y-%m',tarih)=?"; p.append(ay)
    rows = q(conn, sql+" ORDER BY tarih DESC", p); conn.close(); return rows

def kasa_listesi(ay=None):
    conn = get_db()
    sql = "SELECT * FROM kasa WHERE 1=1"; p = []
    if ay: sql += " AND strftime('%Y-%m',tarih)=?"; p.append(ay)
    rows = q(conn, sql+" ORDER BY tarih DESC", p); conn.close(); return rows

def kasa_ekle(d):
    conn = get_db(); c = conn.cursor()
    tur = d.get('tur', d.get('tip'))
    if not tur:
        raise ValueError('Kasa türü zorunludur')
    c.execute("INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak) VALUES(?,?,?,?,?)",
              (d['tarih'], tur, d['tutar'], d.get('aciklama',''), 'manuel'))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def kasa_sil(kid):
    conn = get_db(); conn.execute("DELETE FROM kasa WHERE id=?", (kid,)); conn.commit(); conn.close()

# ── RAPORLAR ──────────────────────────────────────────────────────────────────────
def gelir_ozet(ay=None, terapist_id=None):
    conn = get_db()
    s_filtre = ""; p_s = []
    if ay: s_filtre += " AND strftime('%Y-%m',tarih)=?"; p_s.append(ay)
    if terapist_id: s_filtre += " AND terapist_id=?"; p_s.append(terapist_id)
    o_filtre = ""; p_o = []
    if ay: o_filtre += " AND strftime('%Y-%m',tarih)=?"; p_o.append(ay)
    if terapist_id: o_filtre += " AND terapist_id=?"; p_o.append(terapist_id)

    terapist_detay = q(conn, f"""SELECT t.id,t.ad,t.renk,
        COUNT(s.id) as seans, COALESCE(SUM(s.terapist_payi),0) as t_pay,
        COALESCE(SUM(s.isletme_payi),0) as i_pay, COALESCE(SUM(s.ucret),0) as toplam
        FROM terapistler t LEFT JOIN seanslar s ON s.terapist_id=t.id {s_filtre.replace('AND','WHERE',1) if s_filtre and 'WHERE' not in s_filtre else s_filtre}
        GROUP BY t.id ORDER BY t.ad""", p_s)

    seans_ozet = q(conn, f"SELECT COALESCE(SUM(ucret),0) as g, COALESCE(SUM(terapist_payi),0) as t, COALESCE(SUM(isletme_payi),0) as i, COUNT(*) as sayi FROM seanslar WHERE 1=1{s_filtre}", p_s)[0]
    odeme_toplam = q(conn, f"SELECT COALESCE(SUM(tutar),0) as t FROM odemeler WHERE 1=1{o_filtre}", p_o)[0]['t']
    gider_toplam = q(conn, "SELECT COALESCE(SUM(tutar),0) as t FROM giderler" + (" WHERE strftime('%Y-%m',tarih)=?" if ay else ""), [ay] if ay else [])[0]['t']
    kasa_bakiye_r = q(conn, "SELECT COALESCE(SUM(CASE WHEN tur='giris' THEN tutar ELSE -tutar END),0) as b FROM kasa")[0]
    aylik = q(conn, "SELECT strftime('%Y-%m',tarih) as ay, COUNT(*) as seans, COALESCE(SUM(ucret),0) as gelir FROM seanslar GROUP BY ay ORDER BY ay DESC LIMIT 12")
    conn.close()
    return {'terapist_detay': terapist_detay, 'seans_ozet': seans_ozet,
            'odeme_toplam': odeme_toplam, 'gider_toplam': gider_toplam,
            'net_kar': float(odeme_toplam) - float(gider_toplam),
            'kasa_bakiye': float(kasa_bakiye_r['b']), 'aylik': aylik}
# ── RANDEVU ──────────────────────────────────────────────────────────────────────
def randevular_listesi(tarih=None, ay=None, terapist_id=None):
    conn = get_db()
    sql = """SELECT r.*, d.ad||' '||d.soyad as danisan_adi,
        t.ad as terapist_adi, t.renk as terapist_renk,
        h.alan_adi as hizmet_adi, o.ad as oda_adi, o.renk as oda_renk
        FROM randevular r
        JOIN danisanlar d ON d.id=r.danisan_id
        JOIN terapistler t ON t.id=r.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=r.hizmet_id
        LEFT JOIN odalar o ON o.id=r.oda_id
        WHERE 1=1"""
    p = []
    if tarih: sql += " AND r.tarih=?"; p.append(tarih)
    if ay: sql += " AND strftime('%Y-%m',r.tarih)=?"; p.append(ay)
    if terapist_id:
        sql += " AND (r.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=r.danisan_id AND dt.terapist_id=?))"
        p.extend([terapist_id, terapist_id])
    rows = q(conn, sql+" ORDER BY r.tarih, r.saat", p)
    conn.close(); return rows

def randevu_ekle(d):
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO randevular(danisan_id,terapist_id,hizmet_id,tarih,saat,sure_dk,durum,notlar,oda_id)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
              (d['danisan_id'], d['terapist_id'], d.get('hizmet_id'),
               d['tarih'], d['saat'], d.get('sure_dk',45), d.get('durum','bekliyor'), d.get('notlar',''), d.get('oda_id')))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid

def randevu_guncelle(d):
    conn = get_db()
    conn.execute("""UPDATE randevular SET danisan_id=?, terapist_id=?, hizmet_id=?, tarih=?, saat=?,
        sure_dk=?, durum=?, notlar=?, oda_id=? WHERE id=?""",
        (d['danisan_id'], d['terapist_id'], d.get('hizmet_id'), d['tarih'], d['saat'],
         d.get('sure_dk',45), d.get('durum','bekliyor'), d.get('notlar',''), d.get('oda_id'), d['id']))
    conn.commit(); conn.close()

def randevu_sil(rid):
    conn = get_db(); conn.execute("DELETE FROM randevular WHERE id=?", (rid,)); conn.commit(); conn.close()


def _saat_dakika(saat):
    try:
        hh, mm = (saat or '00:00')[:5].split(':')
        return int(hh) * 60 + int(mm)
    except Exception:
        return 0


def _aralik_cakisiyor(saat1, sure1, saat2, sure2):
    bas1 = _saat_dakika(saat1)
    bas2 = _saat_dakika(saat2)
    bit1 = bas1 + int(sure1 or 45)
    bit2 = bas2 + int(sure2 or 45)
    return bas1 < bit2 and bas2 < bit1


def _konflikt_kart(row):
    return {
        'id': row.get('id'),
        'danisan_id': row.get('danisan_id'),
        'danisan_adi': row.get('danisan_adi') or '',
        'terapist_id': row.get('terapist_id'),
        'terapist_adi': row.get('terapist_adi') or row.get('randevu_terapist_adi') or '',
        'oda_id': row.get('oda_id'),
        'oda_adi': row.get('oda_adi') or '',
        'gun_index': int(row.get('gun_index') or row.get('day_index') or 0),
        'saat': (row.get('saat') or '')[:5],
        'sure_dk': int(row.get('sure_dk') or 45),
        'hizmet_adi': row.get('hizmet_adi') or ''
    }


def haftalik_program_cakisma_analizi(d):
    aday = {
        'id': str(d.get('id') or ''),
        'danisan_id': str(d.get('danisan_id') or ''),
        'terapist_id': str(d.get('terapist_id') or ''),
        'oda_id': str(d.get('oda_id') or ''),
        'gun_index': int(d.get('gun_index', 0) or 0),
        'saat': (d.get('saat') or '')[:5],
        'sure_dk': int(d.get('sure_dk', 45) or 45)
    }
    if not aday['terapist_id'] or not aday['danisan_id'] or not aday['saat']:
        return {'has_conflict': False, 'terapist': [], 'oda': [], 'danisan': []}
    conn = get_db()
    rows = q(conn, """SELECT ws.*,
        d.ad||' '||d.soyad as danisan_adi,
        t.ad as terapist_adi,
        h.alan_adi as hizmet_adi,
        o.ad as oda_adi
        FROM haftalik_program_sablonlari ws
        JOIN danisanlar d ON d.id=ws.danisan_id
        LEFT JOIN terapistler t ON t.id=ws.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=ws.hizmet_id
        LEFT JOIN odalar o ON o.id=ws.oda_id
        WHERE COALESCE(ws.aktif,1)=1 AND ws.gun_index=?
    """, (aday['gun_index'],))
    conn.close()
    terapist_conflicts, oda_conflicts, danisan_conflicts = [], [], []
    for row in rows:
        if aday['id'] and str(row.get('id')) == aday['id']:
            continue
        if not _aralik_cakisiyor(aday['saat'], aday['sure_dk'], row.get('saat'), row.get('sure_dk')):
            continue
        kart = _konflikt_kart(row)
        if str(row.get('terapist_id') or '') == aday['terapist_id']:
            terapist_conflicts.append(kart)
        if aday['oda_id'] and str(row.get('oda_id') or '') == aday['oda_id']:
            oda_conflicts.append(kart)
        if str(row.get('danisan_id') or '') == aday['danisan_id']:
            danisan_conflicts.append(kart)
    return {
        'has_conflict': bool(terapist_conflicts or oda_conflicts or danisan_conflicts),
        'terapist': terapist_conflicts,
        'oda': oda_conflicts,
        'danisan': danisan_conflicts
    }


def haftalik_program_cakisma_haritasi(rows):
    harita = {}
    normalized = []
    for row in rows or []:
        current = dict(row)
        current['_gun'] = int(current.get('gun_index') or current.get('day_index') or 0)
        current['_saat'] = (current.get('saat') or '')[:5]
        current['_sure'] = int(current.get('sure_dk') or 45)
        normalized.append(current)
        harita[str(current.get('id'))] = {'terapist': [], 'oda': [], 'danisan': []}
    for i, a in enumerate(normalized):
        for b in normalized[i+1:]:
            if a['_gun'] != b['_gun']:
                continue
            if not _aralik_cakisiyor(a['_saat'], a['_sure'], b['_saat'], b['_sure']):
                continue
            if str(a.get('terapist_id') or '') == str(b.get('terapist_id') or ''):
                harita[str(a.get('id'))]['terapist'].append(_konflikt_kart(b))
                harita[str(b.get('id'))]['terapist'].append(_konflikt_kart(a))
            if a.get('oda_id') and str(a.get('oda_id')) == str(b.get('oda_id')):
                harita[str(a.get('id'))]['oda'].append(_konflikt_kart(b))
                harita[str(b.get('id'))]['oda'].append(_konflikt_kart(a))
            if str(a.get('danisan_id') or '') == str(b.get('danisan_id') or ''):
                harita[str(a.get('id'))]['danisan'].append(_konflikt_kart(b))
                harita[str(b.get('id'))]['danisan'].append(_konflikt_kart(a))
    return harita


def haftalik_program_kaydet(d):
    conn = get_db(); c = conn.cursor()
    gun_index = int(d.get('gun_index', 0) or 0)
    gun_index = max(0, min(6, gun_index))
    saat = (d.get('saat') or '').strip()[:5]
    if not saat:
        raise ValueError('Saat zorunludur')
    sure_dk = int(d.get('sure_dk', 45) or 45)
    payload = (
        d['danisan_id'],
        d['terapist_id'],
        d.get('hizmet_id') or None,
        gun_index,
        saat,
        sure_dk,
        d.get('oda_id') or None,
        1 if str(d.get('aktif', 1)) not in ('0', 'false', 'False') else 0,
        d.get('notlar', '')
    )
    if d.get('id'):
        c.execute("""UPDATE haftalik_program_sablonlari
            SET danisan_id=?, terapist_id=?, hizmet_id=?, gun_index=?, saat=?, sure_dk=?, oda_id=?, aktif=?, notlar=?
            WHERE id=?""", payload + (d['id'],))
        pid = int(d['id'])
    else:
        c.execute("""INSERT INTO haftalik_program_sablonlari
            (danisan_id, terapist_id, hizmet_id, gun_index, saat, sure_dk, oda_id, aktif, notlar)
            VALUES(?,?,?,?,?,?,?,?,?)""", payload)
        pid = c.lastrowid
    conn.commit(); conn.close(); return pid

def haftalik_program_sil(pid):
    conn = get_db()
    conn.execute("DELETE FROM haftalik_program_sablonlari WHERE id=?", (pid,))
    conn.commit(); conn.close()

def haftalik_program_sablonlari_listesi(terapist_id=None):
    conn = get_db()
    sql = """SELECT ws.*,
        d.ad||' '||d.soyad as danisan_adi,
        t.ad as randevu_terapist_adi,
        h.alan_adi as hizmet_adi,
        h.takvim_rengi as takvim_rengi,
        o.ad as oda_adi
        FROM haftalik_program_sablonlari ws
        JOIN danisanlar d ON d.id=ws.danisan_id
        LEFT JOIN terapistler t ON t.id=ws.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=ws.hizmet_id
        LEFT JOIN odalar o ON o.id=ws.oda_id
        WHERE COALESCE(ws.aktif,1)=1"""
    p = []
    if terapist_id:
        sql += " AND (ws.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=ws.danisan_id AND dt.terapist_id=?))"
        p.extend([terapist_id, terapist_id])
    rows = q(conn, sql + " ORDER BY ws.gun_index, COALESCE(ws.saat,''), d.ad, d.soyad", p)
    conn.close()
    return rows

def haftalik_program_terapist_programi(week_start=None, terapist_id=None):
    if terapist_id in (None, '', 0, '0'):
        terapistler = terapistler_listesi()
        terapist_id = terapistler[0]['id'] if terapistler else None
    monday, sunday, days, hours = haftalik_meta(week_start)
    if not terapist_id:
        return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'items': [], 'hours': hours}
    conflict_map = haftalik_program_cakisma_haritasi(haftalik_program_sablonlari_listesi(None))
    raw_items = haftalik_program_sablonlari_listesi(terapist_id)
    items = []
    for item in raw_items:
        day_idx = int(item.get('gun_index') or 0)
        item_date = monday + timedelta(days=day_idx)
        row = dict(item)
        row['tarih'] = item_date.isoformat()
        row['day_index'] = day_idx
        row['ana_terapist_mi'] = 1 if str(item.get('terapist_id')) == str(terapist_id) else 0
        row['conflicts'] = conflict_map.get(str(item.get('id')), {'terapist': [], 'oda': [], 'danisan': []})
        items.append(row)
    return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'items': items, 'hours': hours}

def haftalik_terapist_programi(week_start=None, terapist_id=None):
    return haftalik_program_terapist_programi(week_start, terapist_id)


def haftalik_oda_programi(week_start=None, oda_id=None):
    conn = get_db()
    monday, sunday, days, hours = haftalik_meta(week_start)
    odalar = odalar_listesi()
    if oda_id in (None, '', 0, '0'):
        oda_id = odalar[0]['id'] if odalar else None
    conflict_map = haftalik_program_cakisma_haritasi(haftalik_program_sablonlari_listesi(None))
    items = []
    if oda_id:
        rows = q(conn, """SELECT ws.*,
            d.ad||' '||d.soyad as danisan_adi,
            t.ad as terapist_adi, t.renk as terapist_renk,
            h.alan_adi as hizmet_adi, h.takvim_rengi as takvim_rengi,
            o.ad as oda_adi, o.renk as oda_renk
            FROM haftalik_program_sablonlari ws
            JOIN danisanlar d ON d.id=ws.danisan_id
            LEFT JOIN terapistler t ON t.id=ws.terapist_id
            LEFT JOIN hizmet_alanlari h ON h.id=ws.hizmet_id
            LEFT JOIN odalar o ON o.id=ws.oda_id
            WHERE COALESCE(ws.aktif,1)=1 AND ws.oda_id=?
            ORDER BY ws.gun_index, COALESCE(ws.saat,''), d.ad, d.soyad""", (oda_id,))
        for item in rows:
            day_idx = int(item.get('gun_index') or 0)
            item_date = monday + timedelta(days=day_idx)
            row = dict(item)
            row['tarih'] = item_date.isoformat()
            row['day_index'] = day_idx
            row['conflicts'] = conflict_map.get(str(item.get('id')), {'terapist': [], 'oda': [], 'danisan': []})
            items.append(row)
    conn.close()
    return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'items': items, 'hours': hours, 'odalar': odalar, 'oda_id': oda_id}


def seans_haftalik_programi(week_start=None, terapist_id=None):
    conn = get_db()
    if terapist_id in (None, '', 0, '0'):
        terapistler = terapistler_listesi()
        terapist_id = terapistler[0]['id'] if terapistler else None
    monday, sunday, days, hours = haftalik_meta(week_start)
    if not terapist_id:
        conn.close()
        return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'items': [], 'hours': hours}
    actual = q(conn, """SELECT s.*,
        d.ad||' '||d.soyad as danisan_adi,
        t.ad as terapist_adi, t.renk as terapist_renk,
        h.alan_adi as hizmet_adi, h.takvim_rengi as takvim_rengi,
        o.ad as oda_adi, o.renk as oda_renk
        FROM seanslar s
        JOIN danisanlar d ON d.id=s.danisan_id
        LEFT JOIN terapistler t ON t.id=s.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        LEFT JOIN odalar o ON o.id=s.oda_id
        WHERE s.tarih BETWEEN ? AND ?
          AND (s.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=s.danisan_id AND dt.terapist_id=?))
        ORDER BY s.tarih, COALESCE(s.saat,''), d.ad, d.soyad""", (monday.isoformat(), sunday.isoformat(), terapist_id, terapist_id))
    planned = haftalik_program_sablonlari_listesi(terapist_id)
    actual_keys = set()
    items = []
    for row in actual:
        dt = parse_iso_date(row['tarih'], monday)
        item = dict(row)
        item['day_index'] = dt.weekday()
        item['kaynak'] = 'gerceklesen'
        items.append(item)
        actual_keys.add((row['tarih'], str(row['danisan_id']), (row.get('saat') or '')[:5]))
    for pr in planned:
        day_idx = int(pr.get('gun_index') or 0)
        item_date = monday + timedelta(days=day_idx)
        key = (item_date.isoformat(), str(pr['danisan_id']), (pr.get('saat') or '')[:5])
        if key in actual_keys:
            continue
        row = dict(pr)
        row['tarih'] = item_date.isoformat()
        row['day_index'] = day_idx
        row['kaynak'] = 'planli'
        row['tip'] = 'planli'
        items.append(row)
    conn.close()
    items.sort(key=lambda x: (x.get('tarih') or '', x.get('saat') or '', x.get('danisan_adi') or ''))
    return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'items': items, 'hours': hours}


# ── AYLIK KARŞILAŞTIRMA ──────────────────────────────────────────────────────────
def aylik_karsilastirma(terapist_id=None):
    conn = get_db()
    p = [terapist_id]*3 if terapist_id else []
    t_filtre = " AND s.terapist_id=?" if terapist_id else ""
    o_filtre = " AND terapist_id=?" if terapist_id else ""
    g_filtre = ""
    aylik = q(conn, f"""
        SELECT
            strftime('%Y-%m', s.tarih) as ay,
            COUNT(s.id) as seans_sayisi,
            COALESCE(SUM(s.ucret),0) as seans_gelir,
            COALESCE(SUM(s.terapist_payi),0) as terapist_pay,
            COALESCE(SUM(s.isletme_payi),0) as isletme_pay
        FROM seanslar s WHERE 1=1{t_filtre}
        GROUP BY ay ORDER BY ay DESC LIMIT 18""", p[:1] if terapist_id else [])
    # Her ay için ödeme ve gider de ekle
    sonuc = []
    for row in aylik:
        p2 = [row['ay']]
        if terapist_id: p2.append(terapist_id)
        odeme = q(conn, f"SELECT COALESCE(SUM(tutar),0) as t FROM odemeler WHERE strftime('%Y-%m',tarih)=?{o_filtre}", p2)[0]['t']
        gider = q(conn, "SELECT COALESCE(SUM(tutar),0) as t FROM giderler WHERE strftime('%Y-%m',tarih)=?", [row['ay']])[0]['t']
        r = dict(row)
        r['odeme'] = float(odeme)
        r['gider'] = float(gider)
        r['net_kar'] = float(odeme) - float(gider)
        sonuc.append(r)
    # Terapist bazlı aylık
    terapist_aylik = q(conn, f"""
        SELECT t.id, t.ad, t.renk,
            strftime('%Y-%m',s.tarih) as ay,
            COUNT(s.id) as seans,
            COALESCE(SUM(s.terapist_payi),0) as t_pay,
            COALESCE(SUM(s.isletme_payi),0) as i_pay,
            COALESCE(SUM(s.ucret),0) as toplam
        FROM terapistler t LEFT JOIN seanslar s ON s.terapist_id=t.id
        WHERE s.tarih IS NOT NULL
        GROUP BY t.id, ay ORDER BY ay DESC, t.ad LIMIT 60""", [])
    conn.close()
    return {'aylik': sonuc, 'terapist_aylik': terapist_aylik}

# ── TÜM SEANSLAR ──────────────────────────────────────────────────────────────────
def tum_seanslar(ay=None, terapist_id=None):
    conn = get_db()
    sql = """SELECT s.*,
        d.ad||' '||d.soyad as danisan_adi,
        t.ad as terapist_adi, t.renk as terapist_renk,
        h.alan_adi as hizmet_adi
        FROM seanslar s
        JOIN danisanlar d ON d.id=s.danisan_id
        JOIN terapistler t ON t.id=s.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        WHERE 1=1"""
    p = []
    if ay: sql += " AND strftime('%Y-%m',s.tarih)=?"; p.append(ay)
    if terapist_id: sql += " AND s.terapist_id=?"; p.append(terapist_id)
    rows = q(conn, sql+" ORDER BY s.tarih DESC, t.ad", p)
    conn.close(); return rows

# ── ÖDEME ÖZET (Terapist 3 kazancı dahil) ────────────────────────────────────────────
def odeme_ozet(ay=None, terapist_id=None):
    conn = get_db()
    s_p = []; s_f = " WHERE 1=1"
    if ay: s_f += " AND strftime('%Y-%m',tarih)=?"; s_p.append(ay)
    if terapist_id: s_f += " AND terapist_id=?"; s_p.append(terapist_id)
    # Tahsil edilen ödemeler
    odemeler = q(conn, f"SELECT COALESCE(SUM(tutar),0) as t FROM odemeler{s_f}", s_p)[0]['t']
    # Seans bazlı hesaplanan gelir (terapist payları dahil)
    terapist_kazanc = q(conn, f"""
        SELECT t.id, t.ad, t.renk,
            COUNT(s.id) as seans_sayisi,
            COALESCE(SUM(s.ucret),0) as brut_gelir,
            COALESCE(SUM(s.terapist_payi),0) as terapist_kazanc,
            COALESCE(SUM(s.isletme_payi),0) as artesis_kazanc
        FROM terapistler t
        LEFT JOIN seanslar s ON s.terapist_id=t.id{s_f.replace('WHERE 1=1','WHERE 1=1').replace('tarih','s.tarih').replace('terapist_id','s.terapist_id')}
        GROUP BY t.id ORDER BY t.ad""", s_p)
    conn.close()
    return {
        'tahsil_edilen': float(odemeler),
        'terapist_kazanc': terapist_kazanc
    }



def terapist_pay_ozet(ay=None, terapist_id=None):
    conn = get_db()
    filt = " WHERE 1=1"; p=[]
    if ay:
        filt += " AND strftime('%Y-%m', s.tarih)=?"; p.append(ay)
    if terapist_id:
        filt += " AND s.terapist_id=?"; p.append(terapist_id)
    ozet = q(conn, f"""SELECT t.id, t.ad, t.renk,
        COUNT(s.id) as seans_sayisi,
        COALESCE(SUM(s.ucret),0) as brut_gelir,
        COALESCE(SUM(s.terapist_payi),0) as terapist_payi,
        COALESCE(SUM(s.isletme_payi),0) as isletme_payi
        FROM terapistler t LEFT JOIN seanslar s ON s.terapist_id=t.id
        {filt.replace('s.tarih','tarih').replace('s.terapist_id','terapist_id')}
        GROUP BY t.id ORDER BY t.ad""", p)
    conn.close()
    return ozet

def pilates_ozet():
    conn = get_db()
    today = date.today()
    paket_seans_sayisi = 8
    paket_sure_gun = 42

    rows = q(conn, """SELECT d.id as danisan_id,
        d.ad||' '||d.soyad as danisan_adi,
        d.kayit_tarihi,
        d.pilates_baslangic_tarihi,
        COALESCE(d.pilates_paket_odendi,0) as pilates_paket_odendi,
        COALESCE(d.pilates_paket_odeme_tarihi,'') as pilates_paket_odeme_tarihi,
        (SELECT MIN(s.tarih)
           FROM seanslar s
           JOIN hizmet_alanlari h ON h.id=s.hizmet_id
          WHERE s.danisan_id=d.id AND h.kategori='pilates') as ilk_pilates_tarihi,
        (SELECT MIN(r.tarih)
           FROM randevular r
           JOIN hizmet_alanlari h ON h.id=r.hizmet_id
          WHERE r.danisan_id=d.id AND h.kategori='pilates') as ilk_pilates_randevu_tarihi
        FROM danisanlar d
        WHERE d.aktif=1 AND (
            COALESCE(NULLIF(d.pilates_baslangic_tarihi,''),'')<>'' OR
            EXISTS(SELECT 1 FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=d.id AND h.kategori='pilates') OR
            EXISTS(SELECT 1 FROM randevular r JOIN hizmet_alanlari h ON h.id=r.hizmet_id WHERE r.danisan_id=d.id AND h.kategori='pilates')
        )
        ORDER BY COALESCE(NULLIF(d.pilates_baslangic_tarihi,''),
                 (SELECT MIN(s.tarih) FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=d.id AND h.kategori='pilates'),
                 (SELECT MIN(r.tarih) FROM randevular r JOIN hizmet_alanlari h ON h.id=r.hizmet_id WHERE r.danisan_id=d.id AND h.kategori='pilates'),
                 d.kayit_tarihi) DESC""")

    detaylar = []
    for r in rows:
        start_dt = parse_iso_date(
            r.get('pilates_baslangic_tarihi') or r.get('ilk_pilates_tarihi') or r.get('ilk_pilates_randevu_tarihi') or r.get('kayit_tarihi'),
            today
        )
        end_dt = start_dt + timedelta(days=paket_sure_gun - 1)

        seanslar = q(conn, """SELECT s.id, s.tarih, s.saat, s.ucret, s.terapist_payi, s.isletme_payi,
            h.alan_adi as hizmet_adi, t.ad as terapist_adi
            FROM seanslar s
            LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
            LEFT JOIN terapistler t ON t.id=s.terapist_id
            WHERE s.danisan_id=?
              AND h.kategori='pilates'
              AND date(COALESCE(NULLIF(s.tarih,''), ?)) BETWEEN date(?) AND date(?)
            ORDER BY date(s.tarih), COALESCE(s.saat,'')""", (r['danisan_id'], start_dt.isoformat(), start_dt.isoformat(), end_dt.isoformat()))

        tamamlanan_seans = len(seanslar)
        toplam_ucret = sum(float(s.get('ucret') or 0) for s in seanslar)
        toplam_simge_payi = sum(float(s.get('terapist_payi') or 0) for s in seanslar)
        toplam_isletme_payi = sum(float(s.get('isletme_payi') or 0) for s in seanslar)
        terapistler = [s.get('terapist_adi') for s in seanslar if s.get('terapist_adi')]
        terapist_adi = ', '.join(dict.fromkeys(terapistler)) if terapistler else '-'

        if today < start_dt:
            gecen_gun = 0
            kalan_gun = paket_sure_gun
            sure_durumu = 'planli'
        else:
            gecen_gun = min((today - start_dt).days + 1, paket_sure_gun)
            kalan_gun = max((end_dt - today).days + 1, 0)
            if tamamlanan_seans >= paket_seans_sayisi:
                sure_durumu = 'tamamlandi'
            elif kalan_gun == 0:
                sure_durumu = 'suresi_doldu'
            else:
                sure_durumu = 'aktif'

        kalan_seans = max(paket_seans_sayisi - tamamlanan_seans, 0)
        seans_ilerleme = round(min(tamamlanan_seans / paket_seans_sayisi, 1) * 100, 1)
        gun_ilerleme = round(min(gecen_gun / paket_sure_gun, 1) * 100, 1) if today >= start_dt else 0

        detay = dict(r)
        detay['baslangic_tarihi'] = start_dt.isoformat()
        detay['bitis_tarihi'] = end_dt.isoformat()
        detay['tamamlanan_seans'] = tamamlanan_seans
        detay['toplam_ucret'] = toplam_ucret
        detay['toplam_simge_payi'] = toplam_simge_payi
        detay['toplam_isletme_payi'] = toplam_isletme_payi
        detay['terapist_adi'] = terapist_adi
        detay['kalan_seans'] = kalan_seans
        detay['gecen_gun'] = gecen_gun
        detay['kalan_gun'] = kalan_gun
        detay['kalan_hafta'] = round(kalan_gun / 7, 1)
        detay['paket_toplam_gun'] = paket_sure_gun
        detay['paket_toplam_seans'] = paket_seans_sayisi
        detay['seans_ilerleme_yuzde'] = seans_ilerleme
        detay['gun_ilerleme_yuzde'] = gun_ilerleme
        detay['sure_durumu'] = sure_durumu
        detay['paket_odendi'] = int(r.get('pilates_paket_odendi') or 0)
        detay['paket_odeme_tarihi'] = r.get('pilates_paket_odeme_tarihi') or ''
        detay['seanslar'] = seanslar
        detaylar.append(detay)

    conn.close()
    return detaylar


def pilates_baslangic_guncelle(data):
    conn = get_db()
    reset_paket = int(data.get('paket_sifirla', 0) or 0)
    odendi = 0 if reset_paket else int(data.get('pilates_paket_odendi', data.get('paket_odendi', 0)) or 0)
    odeme_tarih = '' if reset_paket else (data.get('pilates_paket_odeme_tarihi', data.get('paket_odeme_tarihi', '')) or '')
    conn.execute("UPDATE danisanlar SET pilates_baslangic_tarihi=?, pilates_paket_odendi=?, pilates_paket_odeme_tarihi=? WHERE id=?", (
        data.get('pilates_baslangic_tarihi',''), odendi, odeme_tarih, data['danisan_id']
    ))
    conn.commit()
    conn.close()

def pilates_paket_odeme_guncelle(data):
    conn = get_db()
    odendi = int(data.get('paket_odendi', 0) or 0)
    odeme_tarihi = (data.get('paket_odeme_tarihi') or '').strip()
    if odendi and not odeme_tarihi:
        odeme_tarihi = date.today().isoformat()
    if not odendi:
        odeme_tarihi = ''
    conn.execute("UPDATE danisanlar SET pilates_paket_odendi=?, pilates_paket_odeme_tarihi=? WHERE id=?", (odendi, odeme_tarihi, data['danisan_id']))
    conn.commit()
    conn.close()
    return {'ok': True, 'paket_odendi': odendi, 'paket_odeme_tarihi': odeme_tarihi}

def oda_doluluk(tarih=None):
    conn = get_db()
    tarih = tarih or date.today().isoformat()
    odalar = odalar_listesi()
    randevular = q(conn, """SELECT r.*, d.ad||' '||d.soyad as danisan_adi, t.ad as terapist_adi,
        h.alan_adi as hizmet_adi, o.ad as oda_adi, o.renk as oda_renk
        FROM randevular r
        JOIN danisanlar d ON d.id=r.danisan_id
        JOIN terapistler t ON t.id=r.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=r.hizmet_id
        LEFT JOIN odalar o ON o.id=r.oda_id
        WHERE r.tarih=? ORDER BY r.saat""", (tarih,))
    seanslar = q(conn, """SELECT s.*, d.ad||' '||d.soyad as danisan_adi, t.ad as terapist_adi,
        h.alan_adi as hizmet_adi, o.ad as oda_adi, o.renk as oda_renk
        FROM seanslar s
        JOIN danisanlar d ON d.id=s.danisan_id
        JOIN terapistler t ON t.id=s.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        LEFT JOIN odalar o ON o.id=s.oda_id
        WHERE s.tarih=? AND COALESCE(s.saat,'')<>'' ORDER BY s.saat""", (tarih,))
    conn.close()
    return {'tarih': tarih, 'odalar': odalar, 'randevular': randevular, 'seanslar': seanslar}

# ── HTTP HANDLER ──────────────────────────────────────────────────────────────────

TEMA_RENKLERI = {
    'sari':   {'primary':'#f5b800','primary2':'#d4a017','bg':'#fffdf0','card':'#ffffff','sidebar':'#1a1a2e','text':'#1a1a1a','accent':'#f5b800'},
    'mavi':   {'primary':'#2563eb','primary2':'#1d4ed8','bg':'#f0f4ff','card':'#ffffff','sidebar':'#0f172a','text':'#0f172a','accent':'#2563eb'},
    'yesil':  {'primary':'#059669','primary2':'#047857','bg':'#f0fdf4','card':'#ffffff','sidebar':'#052e16','text':'#052e16','accent':'#059669'},
    'mor':    {'primary':'#7c3aed','primary2':'#6d28d9','bg':'#f5f3ff','card':'#ffffff','sidebar':'#1e1b4b','text':'#1e1b4b','accent':'#7c3aed'},
    'lacivert':{'primary':'#0e7490','primary2':'#0c5b72','bg':'#f0fdff','card':'#ffffff','sidebar':'#0c2a31','text':'#0c2a31','accent':'#0e7490'},
    'ozel':   {'primary':'#f5b800','primary2':'#d4a017','bg':'#fffdf0','card':'#ffffff','sidebar':'#1a1a2e','text':'#1a1a1a','accent':'#f5b800'},
}



# ── v3.5.0 EK MODÜLLERİ ────────────────────────────────────────────────────────────
import secrets

_legacy_init_db_v350 = init_db

def init_db():
    _legacy_init_db_v350()
    conn = get_db(); c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS kaynaklar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        tur TEXT DEFAULT 'ekipman',
        renk TEXT DEFAULT '#0ea5e9',
        kapasite INTEGER DEFAULT 1,
        bagli_oda_id INTEGER,
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS kaynak_rezervasyonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kaynak_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        baslik TEXT NOT NULL,
        tip TEXT DEFAULT 'manuel',
        danisan_id INTEGER,
        terapist_id INTEGER,
        meta_json TEXT DEFAULT '',
        FOREIGN KEY(kaynak_id) REFERENCES kaynaklar(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS stok_kalemleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        kategori TEXT DEFAULT 'Sarf',
        birim TEXT DEFAULT 'adet',
        mevcut_stok REAL DEFAULT 0,
        min_stok REAL DEFAULT 0,
        birim_maliyet REAL DEFAULT 0,
        barkod TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS stok_hareketleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kalem_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        tur TEXT NOT NULL,
        miktar REAL NOT NULL,
        birim_fiyat REAL DEFAULT 0,
        aciklama TEXT DEFAULT '',
        FOREIGN KEY(kalem_id) REFERENCES stok_kalemleri(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS otomasyon_kurallari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kod TEXT UNIQUE,
        ad TEXT NOT NULL,
        tur TEXT NOT NULL,
        kanal TEXT DEFAULT 'whatsapp',
        sablon_kod TEXT DEFAULT '',
        ayar_json TEXT DEFAULT '{}',
        aktif INTEGER DEFAULT 1,
        son_calisma TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS portal_erisimleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        aktif INTEGER DEFAULT 1,
        olusturma_tarihi TEXT NOT NULL,
        son_gecerlilik TEXT DEFAULT '',
        son_giris TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS online_talepler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        telefon TEXT DEFAULT '',
        email TEXT DEFAULT '',
        hizmet_adi TEXT DEFAULT '',
        tercih_tarih TEXT DEFAULT '',
        tercih_saat TEXT DEFAULT '',
        notlar TEXT DEFAULT '',
        durum TEXT DEFAULT 'yeni',
        token TEXT DEFAULT '',
        olusturma_tarihi TEXT DEFAULT (datetime('now','localtime'))
    );
    """)
    cols = [r['name'] for r in q(conn, "PRAGMA table_info(kaynaklar)")]
    if 'bagli_oda_id' not in cols:
        c.execute("ALTER TABLE kaynaklar ADD COLUMN bagli_oda_id INTEGER")
    for oda in q(conn, "SELECT * FROM odalar WHERE aktif=1"):
        var = q(conn, "SELECT id FROM kaynaklar WHERE bagli_oda_id=? OR (tur='oda' AND ad=?)", (oda['id'], oda['ad']))
        if not var:
            c.execute("INSERT INTO kaynaklar(ad,tur,renk,kapasite,bagli_oda_id,aktif,notlar) VALUES(?,?,?,?,?,?,?)",
                      (oda['ad'], 'oda', oda.get('renk') or '#64748b', 1, oda['id'], 1, 'Oda kaynağı'))
        else:
            c.execute("UPDATE kaynaklar SET ad=?, renk=?, aktif=1, tur='oda', bagli_oda_id=? WHERE id=?",
                      (oda['ad'], oda.get('renk') or '#64748b', oda['id'], var[0]['id']))
    c.execute("SELECT COUNT(*) FROM stok_kalemleri")
    if c.fetchone()[0] == 0:
        vars = [
            ('Dezenfektan', 'Sarf', 'adet', 4, 2, 120),
            ('Kağıt Havlu', 'Sarf', 'paket', 8, 3, 65),
            ('Lateks Eldiven', 'Sarf', 'kutu', 5, 2, 180),
            ('Pilates Bandı', 'Ekipman', 'adet', 6, 2, 250),
        ]
        c.executemany("INSERT INTO stok_kalemleri(ad,kategori,birim,mevcut_stok,min_stok,birim_maliyet) VALUES(?,?,?,?,?,?)", vars)
    c.execute("SELECT COUNT(*) FROM otomasyon_kurallari")
    if c.fetchone()[0] == 0:
        kurallar = [
            ('randevu_yarin', 'Yarın randevu hatırlatma', 'randevu_hatirlatma', 'whatsapp', 'randevu_wp', json.dumps({'tip':'yarin_randevu'}), 1),
            ('odeme_3gun', '3 gün geçmiş tahsilat uyarısı', 'odeme_hatirlatma', 'whatsapp', 'odeme_wp', json.dumps({'gun_esik':3}), 1),
            ('recall_21', '21 gün pasif danışan recall', 'recall', 'whatsapp', 'recall_wp', json.dumps({'gun_esik':21}), 0),
        ]
        c.executemany("INSERT INTO otomasyon_kurallari(kod,ad,tur,kanal,sablon_kod,ayar_json,aktif) VALUES(?,?,?,?,?,?,?)", kurallar)
    mevcut_tpl = {r['kod'] for r in q(conn, "SELECT kod FROM mesaj_sablonlari")}
    tpller = [
        ('odeme_wp', 'Ödeme Hatırlatma', 'whatsapp', '', 'Merhaba {ad}, {klinik} kayıtlarına göre tahsil edilmemiş {borc_tutar} tutarında seans/paket bakiyeniz görünüyor. Uygun olduğunuzda ödeme planı için bize dönüş yapabilirsiniz.', 1),
        ('recall_wp', 'Recall Hatırlatma', 'whatsapp', '', 'Merhaba {ad}, sizi bir süredir klinikte göremedik. Son seansınızın üzerinden {gecen_gun} gün geçti. Uygun olduğunuzda devam planınızı birlikte netleştirebiliriz. {klinik}', 1),
    ]
    for kod, ad, kanal, konu, metin, sistem in tpller:
        if kod not in mevcut_tpl:
            c.execute("INSERT INTO mesaj_sablonlari(kod,ad,kanal,konu,metin,sistem) VALUES(?,?,?,?,?,?)", (kod, ad, kanal, konu, metin, sistem))
    c.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES('app_version',?)", (APP_VERSION,))
    conn.commit(); conn.close()


def _parse_json_text(txt, default=None):
    if default is None:
        default = {}
    if not txt:
        return default
    try:
        return json.loads(txt)
    except Exception:
        return default


def kaynaklar_listesi(tur=None):
    init_db()
    conn = get_db()
    sql = "SELECT * FROM kaynaklar WHERE aktif=1"
    p = []
    if tur:
        sql += " AND tur=?"; p.append(tur)
    rows = q(conn, sql + " ORDER BY CASE WHEN tur='oda' THEN 0 ELSE 1 END, ad", p)
    conn.close(); return rows


def kaynak_kaydet(d):
    init_db()
    conn = get_db(); c = conn.cursor()
    vals = (d.get('ad','').strip(), d.get('tur','ekipman'), d.get('renk','#0ea5e9'), d.get('kapasite',1), d.get('bagli_oda_id') or None, d.get('aktif',1), d.get('notlar',''))
    if d.get('id'):
        c.execute("UPDATE kaynaklar SET ad=?,tur=?,renk=?,kapasite=?,bagli_oda_id=?,aktif=?,notlar=? WHERE id=?", vals + (d['id'],))
        lid = d['id']
    else:
        c.execute("INSERT INTO kaynaklar(ad,tur,renk,kapasite,bagli_oda_id,aktif,notlar) VALUES(?,?,?,?,?,?,?)", vals)
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def kaynak_sil(kid):
    conn = get_db(); conn.execute("DELETE FROM kaynaklar WHERE id=?", (kid,)); conn.commit(); conn.close()


def kaynak_rezervasyon_kaydet(d):
    conn = get_db(); c = conn.cursor()
    vals = (d['kaynak_id'], d['tarih'], d['saat'], d.get('sure_dk',45), d.get('baslik','Blok'), d.get('tip','manuel'), d.get('danisan_id'), d.get('terapist_id'), json.dumps(d.get('meta',{}), ensure_ascii=False))
    if d.get('id'):
        c.execute("UPDATE kaynak_rezervasyonlari SET kaynak_id=?,tarih=?,saat=?,sure_dk=?,baslik=?,tip=?,danisan_id=?,terapist_id=?,meta_json=? WHERE id=?", vals + (d['id'],))
        lid = d['id']
    else:
        c.execute("INSERT INTO kaynak_rezervasyonlari(kaynak_id,tarih,saat,sure_dk,baslik,tip,danisan_id,terapist_id,meta_json) VALUES(?,?,?,?,?,?,?,?,?)", vals)
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def kaynak_rezervasyon_sil(rid):
    conn = get_db(); conn.execute("DELETE FROM kaynak_rezervasyonlari WHERE id=?", (rid,)); conn.commit(); conn.close()


def kaynak_haftalik_programi(week_start=None, kaynak_id=None, tur=None):
    init_db()
    monday, sunday, days, hours = haftalik_meta(week_start)
    conn = get_db()
    kaynaklar = kaynaklar_listesi(tur)
    if kaynak_id:
        kaynaklar = [k for k in kaynaklar if str(k['id']) == str(kaynak_id)]
    bagli = {k['bagli_oda_id']: k for k in kaynaklar if k.get('bagli_oda_id')}
    items = []
    sql = "SELECT kr.*, k.ad as kaynak_adi, k.renk as kaynak_renk FROM kaynak_rezervasyonlari kr JOIN kaynaklar k ON k.id=kr.kaynak_id WHERE date(kr.tarih) BETWEEN date(?) AND date(?)"
    p = [monday.isoformat(), sunday.isoformat()]
    if kaynak_id:
        sql += " AND kr.kaynak_id=?"; p.append(kaynak_id)
    for r in q(conn, sql, p):
        items.append({'id':r['id'],'kaynak_id':r['kaynak_id'],'tarih':r['tarih'],'saat':r['saat'],'sure_dk':r.get('sure_dk') or 45,'baslik':r['baslik'],'renk':r.get('kaynak_renk') or '#0ea5e9','tip':r.get('tip') or 'manuel'})
    if bagli:
        for r in q(conn, """SELECT ws.id, ws.oda_id, ws.saat, ws.sure_dk, ws.gun_index, d.ad||' '||d.soyad as danisan_adi, t.ad as terapist_adi
            FROM haftalik_program_sablonlari ws
            JOIN danisanlar d ON d.id=ws.danisan_id JOIN terapistler t ON t.id=ws.terapist_id
            WHERE ws.aktif=1 AND ws.oda_id IS NOT NULL"""):
            base = monday + timedelta(days=int(r['gun_index'] or 0))
            k = bagli.get(r['oda_id'])
            if not k or (kaynak_id and str(k['id']) != str(kaynak_id)): continue
            items.append({'id':'planli_'+str(r['id']),'kaynak_id':k['id'],'tarih':base.isoformat(),'saat':r['saat'],'sure_dk':r.get('sure_dk') or 45,'baslik':f"{r['danisan_adi']} • {r['terapist_adi']}",'renk':k.get('renk') or '#64748b','tip':'planli'})
    for table, tip in [('randevular','randevu'),('seanslar','seans')]:
        if not bagli: break
        extra = "r.sure_dk" if table == 'randevular' else "COALESCE(r.sure_dk,45)"
        for r in q(conn, f"""SELECT r.id, r.oda_id, r.tarih, COALESCE(r.saat,'') as saat, {extra} as sure_dk,
            d.ad||' '||d.soyad as danisan_adi, t.ad as terapist_adi
            FROM {table} r JOIN danisanlar d ON d.id=r.danisan_id JOIN terapistler t ON t.id=r.terapist_id
            WHERE r.oda_id IS NOT NULL AND date(r.tarih) BETWEEN date(?) AND date(?)""", (monday.isoformat(), sunday.isoformat())):
            k = bagli.get(r['oda_id'])
            if not k or (kaynak_id and str(k['id']) != str(kaynak_id)): continue
            items.append({'id':f"{tip}_{r['id']}",'kaynak_id':k['id'],'tarih':r['tarih'],'saat':r['saat'] or '','sure_dk':r.get('sure_dk') or 45,'baslik':f"{r['danisan_adi']} • {r['terapist_adi']}",'renk':k.get('renk') or '#64748b','tip':tip})
    conn.close()
    items.sort(key=lambda x:(x.get('tarih',''), x.get('saat',''), str(x.get('baslik',''))))
    return {'week_start': monday.isoformat(), 'week_end': sunday.isoformat(), 'days': days, 'hours': hours, 'resources': kaynaklar, 'items': items}


def stok_kalemleri_listesi():
    init_db()
    conn = get_db()
    items = q(conn, "SELECT *, CASE WHEN mevcut_stok<=min_stok THEN 1 ELSE 0 END as kritik FROM stok_kalemleri WHERE aktif=1 ORDER BY kritik DESC, kategori, ad")
    hareketler = q(conn, "SELECT sh.*, sk.ad as kalem_adi FROM stok_hareketleri sh JOIN stok_kalemleri sk ON sk.id=sh.kalem_id ORDER BY datetime(sh.tarih) DESC, sh.id DESC LIMIT 100")
    conn.close(); return {'items': items, 'hareketler': hareketler, 'kritik_sayi': sum(1 for x in items if x.get('kritik'))}


def stok_kalem_kaydet(d):
    conn = get_db(); c = conn.cursor()
    vals = (d.get('ad','').strip(), d.get('kategori','Sarf'), d.get('birim','adet'), float(d.get('mevcut_stok',0) or 0), float(d.get('min_stok',0) or 0), float(d.get('birim_maliyet',0) or 0), d.get('barkod',''), d.get('aktif',1), d.get('notlar',''))
    if d.get('id'):
        c.execute("UPDATE stok_kalemleri SET ad=?,kategori=?,birim=?,mevcut_stok=?,min_stok=?,birim_maliyet=?,barkod=?,aktif=?,notlar=? WHERE id=?", vals + (d['id'],))
        lid = d['id']
    else:
        c.execute("INSERT INTO stok_kalemleri(ad,kategori,birim,mevcut_stok,min_stok,birim_maliyet,barkod,aktif,notlar) VALUES(?,?,?,?,?,?,?,?,?)", vals)
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def stok_hareket_ekle(d):
    conn = get_db(); c = conn.cursor()
    kalem = q(conn, "SELECT * FROM stok_kalemleri WHERE id=?", (d['kalem_id'],))
    if not kalem:
        conn.close(); raise ValueError('Stok kalemi bulunamadı')
    kalem = kalem[0]
    miktar = float(d.get('miktar',0) or 0)
    tur = d.get('tur','giris')
    mevcut = float(kalem.get('mevcut_stok') or 0)
    if tur == 'giris': yeni = mevcut + miktar
    elif tur == 'cikis': yeni = mevcut - miktar
    else: yeni = miktar
    c.execute("INSERT INTO stok_hareketleri(kalem_id,tarih,tur,miktar,birim_fiyat,aciklama) VALUES(?,?,?,?,?,?)", (d['kalem_id'], d.get('tarih') or date.today().isoformat(), tur, miktar, float(d.get('birim_fiyat',0) or 0), d.get('aciklama','')))
    c.execute("UPDATE stok_kalemleri SET mevcut_stok=?, birim_maliyet=COALESCE(NULLIF(?,0), birim_maliyet) WHERE id=?", (yeni, float(d.get('birim_fiyat',0) or 0), d['kalem_id']))
    conn.commit(); conn.close(); return {'ok': True, 'mevcut_stok': yeni}


def recall_hedefleri(gun_esik=21, terapist_id=None):
    conn = get_db(); klinik = ayar_al('klinik_adi', 'Arte Terapi')
    sql = """SELECT d.id as danisan_id, d.ad, d.soyad, d.telefon, COALESCE(d.email,'') as email, t.ad as terapist_adi,
        MAX(date(s.tarih)) as son_seans
        FROM danisanlar d
        LEFT JOIN seanslar s ON s.danisan_id=d.id
        LEFT JOIN terapistler t ON t.id=d.terapist_id
        WHERE d.aktif=1"""
    p = []
    if terapist_id:
        sql += " AND d.terapist_id=?"; p.append(terapist_id)
    sql += " GROUP BY d.id HAVING son_seans IS NOT NULL AND julianday(date('now','localtime')) - julianday(date(son_seans)) >= ? ORDER BY son_seans"
    p.append(int(gun_esik or 21))
    rows = q(conn, sql, p); conn.close(); items = []
    for r in rows:
        gecen = int((date.today() - parse_iso_date(r.get('son_seans'))).days)
        items.append({'kaynak':'recall','kaynak_id':r['danisan_id'],'danisan_id':r['danisan_id'],'ad':r['ad'],'soyad':r.get('soyad',''),'danisan_adi':((r['ad'] or '')+' '+(r.get('soyad') or '')).strip(),'telefon':r.get('telefon',''),'email':r.get('email',''),'telefon_norm':_turkiye_tel_normalize(r.get('telefon')),'terapist_adi':r.get('terapist_adi',''),'gecen_gun':gecen,'klinik':klinik})
    return items


def odeme_hatirlatma_hedefleri(gun_esik=3, terapist_id=None):
    conn = get_db(); klinik = ayar_al('klinik_adi', 'Arte Terapi')
    sql = """SELECT d.id as danisan_id, d.ad, d.soyad, d.telefon, COALESCE(d.email,'') as email, t.ad as terapist_adi,
        SUM(CASE WHEN s.ucret_alindi=0 THEN COALESCE(s.ucret,0) ELSE 0 END) as borc_tutar,
        MIN(CASE WHEN s.ucret_alindi=0 THEN s.tarih END) as ilk_borc_tarihi,
        COALESCE(d.pilates_paket_odendi,0) as pilates_paket_odendi
        FROM danisanlar d LEFT JOIN seanslar s ON s.danisan_id=d.id LEFT JOIN terapistler t ON t.id=d.terapist_id
        WHERE d.aktif=1"""
    p = []
    if terapist_id: sql += " AND d.terapist_id=?"; p.append(terapist_id)
    sql += " GROUP BY d.id ORDER BY borc_tutar DESC"
    rows = q(conn, sql, p); conn.close(); items=[]
    for r in rows:
        borc=float(r.get('borc_tutar') or 0)
        if borc <= 0 and int(r.get('pilates_paket_odendi') or 0) == 1: continue
        tarih = r.get('ilk_borc_tarihi') or date.today().isoformat()
        if borc > 0:
            gecen = (date.today() - parse_iso_date(tarih)).days
            if gecen < int(gun_esik or 3): continue
        items.append({'kaynak':'odeme','kaynak_id':r['danisan_id'],'danisan_id':r['danisan_id'],'ad':r['ad'],'soyad':r.get('soyad',''),'danisan_adi':((r['ad'] or '')+' '+(r.get('soyad') or '')).strip(),'telefon':r.get('telefon',''),'email':r.get('email',''),'telefon_norm':_turkiye_tel_normalize(r.get('telefon')),'terapist_adi':r.get('terapist_adi',''),'borc_tutar':f"₺{borc:,.0f}".replace(',', '.'),'klinik':klinik,'tarih':tarih})
    return items


_mesaj_hedefleri_listesi_v340 = mesaj_hedefleri_listesi

def mesaj_hedefleri_listesi(tip='yarin_randevu', terapist_id=None, tarih=None, week_start=None):
    if tip == 'recall':
        items = recall_hedefleri(21, terapist_id)
        return {'tip': tip, 'items': items, 'count': len(items)}
    if tip == 'odeme_hatirlatma':
        items = odeme_hatirlatma_hedefleri(3, terapist_id)
        return {'tip': tip, 'items': items, 'count': len(items)}
    return _mesaj_hedefleri_listesi_v340(tip, terapist_id, tarih, week_start)


def otomasyon_kurallari_listesi():
    init_db(); conn = get_db(); rows = q(conn, "SELECT * FROM otomasyon_kurallari ORDER BY aktif DESC, ad"); conn.close(); return rows


def otomasyon_kural_kaydet(d):
    conn = get_db(); c = conn.cursor()
    ayar_json = d.get('ayar_json') if isinstance(d.get('ayar_json'), str) else json.dumps(d.get('ayar_json', {}), ensure_ascii=False)
    if d.get('id'):
        c.execute("UPDATE otomasyon_kurallari SET ad=?,tur=?,kanal=?,sablon_kod=?,ayar_json=?,aktif=? WHERE id=?", (d.get('ad','Kural'), d.get('tur','randevu_hatirlatma'), d.get('kanal','whatsapp'), d.get('sablon_kod',''), ayar_json, d.get('aktif',1), d['id']))
        lid = d['id']
    else:
        kod = d.get('kod') or ('rule_'+datetime.now().strftime('%Y%m%d%H%M%S'))
        c.execute("INSERT INTO otomasyon_kurallari(kod,ad,tur,kanal,sablon_kod,ayar_json,aktif) VALUES(?,?,?,?,?,?,?)", (kod, d.get('ad','Kural'), d.get('tur','randevu_hatirlatma'), d.get('kanal','whatsapp'), d.get('sablon_kod',''), ayar_json, d.get('aktif',1)))
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def weekStartMondayPy(value=None):
    return haftalik_meta(value)[0].isoformat()


def _targets_for_rule(rule):
    ayar = _parse_json_text(rule.get('ayar_json'), {})
    tur = rule.get('tur')
    if tur == 'randevu_hatirlatma':
        return mesaj_hedefleri_listesi(ayar.get('tip','yarin_randevu'), None, date.today().isoformat(), weekStartMondayPy())['items']
    if tur == 'odeme_hatirlatma':
        return odeme_hatirlatma_hedefleri(int(ayar.get('gun_esik',3) or 3))
    if tur == 'recall':
        return recall_hedefleri(int(ayar.get('gun_esik',21) or 21))
    return []


def otomasyon_onizleme():
    rules = otomasyon_kurallari_listesi(); out = []
    for rule in rules:
        hedefler = _targets_for_rule(rule)
        out.append({'kural': rule, 'adet': len(hedefler), 'ornekler': hedefler[:5]})
    return out


def otomasyon_calistir():
    rules = [r for r in otomasyon_kurallari_listesi() if int(r.get('aktif') or 0) == 1]
    tpl_map = {r['kod']: r for r in mesaj_sablonlari_listesi()}
    kayitlar=[]; now = datetime.now().isoformat(timespec='seconds')
    for rule in rules:
        tpl = tpl_map.get(rule.get('sablon_kod'))
        if not tpl: continue
        for x in _targets_for_rule(rule):
            kayitlar.append({'tarih': now, 'kanal': rule.get('kanal','whatsapp'), 'hedef_turu': rule.get('tur',''), 'hedef_id': x.get('danisan_id') or x.get('kaynak_id'), 'hedef_ad': x.get('danisan_adi') or x.get('ad',''), 'hedef_iletisim': x.get('email') if rule.get('kanal')=='email' else x.get('telefon',''), 'konu': tpl.get('konu',''), 'metin': tpl.get('metin',''), 'durum':'otomatik_hazirlandi', 'meta': x})
        conn = get_db(); conn.execute("UPDATE otomasyon_kurallari SET son_calisma=? WHERE id=?", (now, rule['id'])); conn.commit(); conn.close()
    if kayitlar: mesaj_log_ekle({'kayitlar': kayitlar})
    ayar_kaydet('otomasyon_son_calisma', now)
    return {'ok': True, 'adet': len(kayitlar)}


def portal_token_olustur(danisan_id, gecerlilik_gun=180):
    conn = get_db(); c = conn.cursor(); token = secrets.token_urlsafe(18)
    son = (date.today() + timedelta(days=int(gecerlilik_gun or 180))).isoformat()
    c.execute("INSERT INTO portal_erisimleri(danisan_id,token,aktif,olusturma_tarihi,son_gecerlilik) VALUES(?,?,?,?,?)", (danisan_id, token, 1, datetime.now().isoformat(timespec='seconds'), son))
    conn.commit(); conn.close(); return token


def portal_linkleri_listesi():
    init_db(); conn = get_db(); host = get_local_ips()[0] if get_local_ips() else '127.0.0.1'
    base = f"http://{host}:{PORT}"
    data = q(conn, "SELECT p.*, d.ad||' '||d.soyad as danisan_adi, d.telefon, d.email FROM portal_erisimleri p JOIN danisanlar d ON d.id=p.danisan_id WHERE p.aktif=1 ORDER BY p.id DESC")
    for r in data: r['portal_url'] = f"{base}/portal?token={r['token']}"
    talepler = q(conn, "SELECT * FROM online_talepler ORDER BY datetime(olusturma_tarihi) DESC, id DESC LIMIT 100")
    conn.close(); return {'portallar': data, 'talepler': talepler, 'booking_url': f"{base}/rezervasyon"}


def online_talep_ekle(d):
    conn = get_db(); c = conn.cursor(); token = secrets.token_urlsafe(10)
    c.execute("INSERT INTO online_talepler(ad,soyad,telefon,email,hizmet_adi,tercih_tarih,tercih_saat,notlar,durum,token) VALUES(?,?,?,?,?,?,?,?,?,?)", (d.get('ad',''), d.get('soyad',''), d.get('telefon',''), d.get('email',''), d.get('hizmet_adi',''), d.get('tercih_tarih',''), d.get('tercih_saat',''), d.get('notlar',''), d.get('durum','yeni'), token))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid


def online_talep_guncelle(d):
    conn = get_db(); conn.execute("UPDATE online_talepler SET durum=?, notlar=? WHERE id=?", (d.get('durum','yeni'), d.get('notlar',''), d['id'])); conn.commit(); conn.close()


def portal_veri(token):
    conn = get_db()
    rows = q(conn, "SELECT p.*, d.*, t.ad as terapist_adi FROM portal_erisimleri p JOIN danisanlar d ON d.id=p.danisan_id LEFT JOIN terapistler t ON t.id=d.terapist_id WHERE p.token=? AND p.aktif=1", (token,))
    if not rows: conn.close(); return None
    r = rows[0]
    conn.execute("UPDATE portal_erisimleri SET son_giris=? WHERE token=?", (datetime.now().isoformat(timespec='seconds'), token))
    rv = q(conn, "SELECT tarih,saat,durum FROM randevular WHERE danisan_id=? AND date(tarih)>=date('now','localtime') ORDER BY date(tarih), saat LIMIT 10", (r['danisan_id'],))
    ss = q(conn, "SELECT tarih, saat, ucret, ucret_alindi FROM seanslar WHERE danisan_id=? ORDER BY date(tarih) DESC, saat DESC LIMIT 10", (r['danisan_id'],))
    conn.commit(); conn.close(); return {'danisan': r, 'randevular': rv, 'seanslar': ss}


def public_booking_html():
    klinik = ayar_al('klinik_adi', 'Arte Terapi')
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{klinik} Online Talep</title><style>body{{font-family:system-ui;background:#f8fafc;padding:24px;color:#0f172a}}.card{{max-width:720px;margin:auto;background:white;border:1px solid #e2e8f0;border-radius:16px;padding:24px;box-shadow:0 10px 24px rgba(15,23,42,.06)}}input,textarea,button{{width:100%;padding:12px;border-radius:12px;border:1px solid #cbd5e1;margin-top:6px;margin-bottom:12px;box-sizing:border-box}}button{{background:#f5b800;border:0;font-weight:700;cursor:pointer}}</style></head><body><div class='card'><h2>{klinik} • Online Randevu Talebi</h2><p>Bu form istek bırakır; otomatik onaylı randevu oluşturmaz.</p><form onsubmit='return sendForm(event)'><label>Ad</label><input id='ad' required><label>Soyad</label><input id='soyad'><label>Telefon</label><input id='telefon' required><label>E-posta</label><input id='email'><label>İstenen hizmet</label><input id='hizmet_adi'><label>Tercih edilen tarih</label><input id='tercih_tarih' type='date'><label>Saat</label><input id='tercih_saat' type='time'><label>Notlar</label><textarea id='notlar'></textarea><button>Talep Gönder</button></form><div id='sonuc'></div></div><script>async function sendForm(e){{e.preventDefault();const body={{ad:ad.value,soyad:soyad.value,telefon:telefon.value,email:email.value,hizmet_adi:hizmet_adi.value,tercih_tarih:tercih_tarih.value,tercih_saat:tercih_saat.value,notlar:notlar.value}};const r=await fetch('/api/public/booking',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});const j=await r.json();document.getElementById('sonuc').innerHTML=j.ok?'Talebiniz alındı. En kısa sürede dönüş yapacağız.':'Hata: '+(j.error||'Bilinmiyor');}}</script></body></html>"""


def public_portal_html(token):
    klinik = ayar_al('klinik_adi', 'Arte Terapi')
    veri = portal_veri(token)
    if not veri: return "<html><body><h3>Geçersiz portal bağlantısı</h3></body></html>"
    d = veri['danisan']
    upcoming = ''.join([f"<li>{x['tarih']} {x.get('saat','')}</li>" for x in veri['randevular']]) or '<li>Yaklaşan randevu yok</li>'
    recent = ''.join([f"<li>{x['tarih']} {x.get('saat','')} • {'ödendi' if int(x.get('ucret_alindi') or 0) else 'ödeme bekliyor'}</li>" for x in veri['seanslar']]) or '<li>Kayıtlı seans yok</li>'
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{klinik} Portal</title><style>body{{font-family:system-ui;background:#f8fafc;padding:24px;color:#0f172a}}.card{{max-width:760px;margin:auto;background:white;border:1px solid #e2e8f0;border-radius:16px;padding:24px;box-shadow:0 10px 24px rgba(15,23,42,.06)}}ul{{line-height:1.8}}</style></head><body><div class='card'><h2>{klinik} • Danışan Portalı</h2><p><b>{d.get('ad','')} {d.get('soyad','')}</b></p><p>Birincil terapist: {d.get('terapist_adi','')}</p><h3>Yaklaşan randevular</h3><ul>{upcoming}</ul><h3>Son seanslar</h3><ul>{recent}</ul></div></body></html>"""









# ── BAŞLATMA ──────────────────────────────────────────────────────────────────────
def get_local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith('127.'):
            ips.append(ip)
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        ips.append('127.0.0.1')
    return ips

class ArteServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ── v3.6.0 Sadeleştirme + WhatsApp 24s Otomasyon ───────────────────────────────
APP_VERSION = '3.6.0'

_prev_init_db_v360 = init_db

def init_db():
    _prev_init_db_v360()
    try:
        ayar_kaydet('app_version', APP_VERSION)
    except Exception:
        pass
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) as n FROM mesaj_sablonlari WHERE kod='24saat_wp'")
    row = c.fetchone()
    if not row or int(row[0]) == 0:
        c.execute(
            "INSERT INTO mesaj_sablonlari(kod,ad,kanal,konu,metin,sistem,aktif) VALUES(?,?,?,?,?,?,?)",
            (
                '24saat_wp',
                '24 Saat Kala WhatsApp',
                'whatsapp',
                '',
                'Merhaba {ad}, yarın {tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır. Uygun değilseniz lütfen bize bilgi verin. {oda_satiri} {klinik}',
                1,
                1,
            )
        )
    conn.commit(); conn.close()

_prev_gelir_ozet_v360 = gelir_ozet

def gelir_ozet(ay=None, terapist_id=None):
    data = _prev_gelir_ozet_v360(ay, terapist_id)
    conn = get_db()
    sql = """SELECT COALESCE(o.ad,'Atanmamış') as oda_adi,
                    COUNT(s.id) as seans,
                    COALESCE(MAX(o.renk),'#94a3b8') as oda_renk
             FROM seanslar s
             LEFT JOIN odalar o ON o.id=s.oda_id
             WHERE 1=1"""
    params = []
    if ay:
        sql += " AND strftime('%Y-%m',s.tarih)=?"
        params.append(ay)
    if terapist_id:
        sql += " AND (s.terapist_id=? OR EXISTS (SELECT 1 FROM danisan_terapistler dt WHERE dt.danisan_id=s.danisan_id AND dt.terapist_id=?))"
        params.extend([terapist_id, terapist_id])
    sql += " GROUP BY COALESCE(o.ad,'Atanmamış') ORDER BY seans DESC, oda_adi"
    data['oda_ozet'] = q(conn, sql, params)
    conn.close()
    return data

_prev_mesaj_hedefleri_v360 = mesaj_hedefleri_listesi

def mesaj_hedefleri_listesi(tip='yarin_randevu', terapist_id=None, tarih=None, week_start=None):
    if tip not in ('24saat_kala', '24saat_whatsapp'):
        return _prev_mesaj_hedefleri_v360(tip, terapist_id, tarih, week_start)

    conn = get_db()
    klinik = ayar_al('klinik_adi', 'Arte Terapi')
    ref = parse_iso_date(tarih, date.today())
    hedef = ref + timedelta(days=1)
    items = []

    sql = """SELECT r.id as kaynak_id, 'randevu' as kaynak, r.tarih, r.saat, r.notlar,
        d.id as danisan_id, d.ad, d.soyad, d.telefon, COALESCE(d.email,'') as email,
        t.id as terapist_id, t.ad as terapist_adi,
        h.alan_adi as hizmet_adi, o.ad as oda_adi
        FROM randevular r
        JOIN danisanlar d ON d.id=r.danisan_id
        JOIN terapistler t ON t.id=r.terapist_id
        LEFT JOIN hizmet_alanlari h ON h.id=r.hizmet_id
        LEFT JOIN odalar o ON o.id=r.oda_id
        WHERE date(r.tarih)=date(?)"""
    params = [hedef.isoformat()]
    if terapist_id:
        sql += " AND r.terapist_id=?"
        params.append(terapist_id)
    rows = q(conn, sql + " ORDER BY COALESCE(r.saat,''), d.ad, d.soyad", params)
    mevcut = set()
    for r in rows:
        x = dict(r)
        x['danisan_adi'] = ((r.get('ad') or '') + ' ' + (r.get('soyad') or '')).strip()
        x['telefon_norm'] = _turkiye_tel_normalize(r.get('telefon'))
        x['klinik'] = klinik
        x['oda_satiri'] = f"Oda: {r.get('oda_adi')}" if r.get('oda_adi') else ''
        x['hedef_turu'] = '24saat_kala'
        items.append(x)
        mevcut.add((str(r.get('danisan_id')), str(r.get('terapist_id')), (r.get('saat') or '')[:5]))

    for r in planli_program_tarih_araligi(hedef.isoformat(), hedef.isoformat(), terapist_id):
        key = (str(r.get('danisan_id')), str(r.get('terapist_id')), (r.get('saat') or '')[:5])
        if key in mevcut:
            continue
        x = dict(r)
        x['kaynak'] = 'planli'
        x['kaynak_id'] = r.get('plan_id')
        x['tarih'] = hedef.isoformat()
        x['danisan_adi'] = ((r.get('ad') or '') + ' ' + (r.get('soyad') or '')).strip()
        x['telefon_norm'] = _turkiye_tel_normalize(r.get('telefon'))
        x['klinik'] = klinik
        x['oda_satiri'] = f"Oda: {r.get('oda_adi')}" if r.get('oda_adi') else ''
        x['hedef_turu'] = '24saat_kala'
        items.append(x)

    items.sort(key=lambda x: ((x.get('tarih') or ''), (x.get('saat') or ''), (x.get('danisan_adi') or '')))
    conn.close()
    return {'items': items, 'tip': '24saat_kala'}





# ── v3.7.0 Mobil + Oda Ayarları + Pay Detayı + Mesaj Merkezi ───────────────────
import io

APP_VERSION = '3.7.0'

_prev_init_db_v370 = init_db

def init_db():
    _prev_init_db_v370()
    conn = get_db(); c = conn.cursor()
    cols = [r[1] for r in c.execute("PRAGMA table_info(odalar)").fetchall()]
    if 'kategori' not in cols:
        c.execute("ALTER TABLE odalar ADD COLUMN kategori TEXT DEFAULT 'uygulama'")
    if 'kapasite' not in cols:
        c.execute("ALTER TABLE odalar ADD COLUMN kapasite INTEGER DEFAULT 1")
    if 'ozellikler' not in cols:
        c.execute("ALTER TABLE odalar ADD COLUMN ozellikler TEXT DEFAULT ''")

    migrated = c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_370_initialized'").fetchone() or ('kategori' in cols and 'kapasite' in cols)
    renames = {} if migrated else {
        'Oda 1': 'Uygulama odası 1 (pediatri)',
        'Oda 2': 'Uygulama odası 2 (FTR)',
    }
    for old, new in renames.items():
        old_row = c.execute("SELECT id FROM odalar WHERE ad=?", (old,)).fetchone()
        new_row = c.execute("SELECT id FROM odalar WHERE ad=?", (new,)).fetchone()
        if old_row and not new_row:
            c.execute("UPDATE odalar SET ad=? WHERE ad=?", (new, old))

    defaults = [
        ('Uygulama odası 1 (pediatri)', '#3b82f6', 'uygulama', 1, 'Pediatri değerlendirme ve duyu bütünleme seansları'),
        ('Uygulama odası 2 (FTR)', '#10b981', 'uygulama', 1, 'FTR ve bireysel terapi seansları'),
        ('Pilates Stüdyosu', '#8b5cf6', 'pilates', 6, 'Reformer / pilates grup ve bireysel seansları'),
    ]
    for ad, renk, kategori, kapasite, ozellikler in ([] if migrated else defaults):
        row = c.execute("SELECT id FROM odalar WHERE ad=?", (ad,)).fetchone()
        if row:
            pass  # Preserve existing room settings.
        else:
            c.execute("INSERT INTO odalar(ad,renk,aktif,notlar,kategori,kapasite,ozellikler) VALUES(?,?,?,?,?,?,?)", (ad, renk, 1, '', kategori, kapasite, ozellikler))

    c.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES('app_version',?)", (APP_VERSION,))
    c.execute("INSERT OR IGNORE INTO ayarlar VALUES('schema_370_initialized','1')")
    conn.commit(); conn.close()


def odalar_listesi():
    init_db()
    conn = get_db()
    rows = q(conn, """SELECT id, ad, renk, aktif, COALESCE(notlar,'') as notlar,
                      COALESCE(kategori,'uygulama') as kategori,
                      COALESCE(kapasite,1) as kapasite,
                      COALESCE(ozellikler,'') as ozellikler
                      FROM odalar ORDER BY aktif DESC, ad""")
    conn.close()
    return rows


def oda_kaydet(d):
    init_db()
    conn = get_db(); c = conn.cursor()
    payload = (
        (d.get('ad') or '').strip(),
        d.get('renk') or '#64748b',
        int(d.get('aktif', 1) or 0),
        d.get('notlar') or '',
        d.get('kategori') or 'uygulama',
        int(d.get('kapasite', 1) or 1),
        d.get('ozellikler') or ''
    )
    if not payload[0]:
        raise ValueError('Oda adı zorunludur')
    if d.get('id'):
        c.execute("""UPDATE odalar SET ad=?, renk=?, aktif=?, notlar=?, kategori=?, kapasite=?, ozellikler=?
                     WHERE id=?""", payload + (int(d['id']),))
        lid = int(d['id'])
    else:
        c.execute("""INSERT INTO odalar(ad,renk,aktif,notlar,kategori,kapasite,ozellikler)
                     VALUES(?,?,?,?,?,?,?)""", payload)
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def terapist_pay_detay(ay=None, terapist_id=None):
    conn = get_db()
    filt = " WHERE 1=1 "
    p = []
    if ay:
        filt += " AND strftime('%Y-%m', s.tarih)=?"
        p.append(ay)
    if terapist_id:
        filt += " AND s.terapist_id=?"
        p.append(terapist_id)
    rows = q(conn, f"""SELECT s.id, s.tarih, COALESCE(s.saat,'') as saat, COALESCE(s.tip,'normal') as tip,
                 COALESCE(s.ucret,0) as ucret, COALESCE(s.terapist_payi,0) as terapist_payi,
                 COALESCE(s.isletme_payi,0) as isletme_payi,
                 d.ad||' '||COALESCE(d.soyad,'') as danisan_adi,
                 t.ad as terapist_adi,
                 COALESCE(h.alan_adi,'') as hizmet_adi,
                 COALESCE(o.ad,'') as oda_adi
              FROM seanslar s
              LEFT JOIN danisanlar d ON d.id=s.danisan_id
              LEFT JOIN terapistler t ON t.id=s.terapist_id
              LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
              LEFT JOIN odalar o ON o.id=s.oda_id
              {filt}
              ORDER BY date(s.tarih) DESC, COALESCE(s.saat,'') DESC, s.id DESC""", p)
    conn.close()
    return rows











# ── v3.8.0 Pilates pay fix + Gelmedi + Danışan içgörüleri + PDF rapor + Mesaj Merkezi ──
import io, base64, re

APP_VERSION = '3.8.0'

_prev_init_db_v380 = init_db

def get_reports_dir():
    p = os.path.join(get_app_dir(), 'rapor_pdfler')
    os.makedirs(p, exist_ok=True)
    return p


def init_db():
    _prev_init_db_v380()
    conn = get_db(); c = conn.cursor()
    cols = [r[1] for r in c.execute("PRAGMA table_info(seanslar)").fetchall()]
    if 'gelmedi' not in cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN gelmedi INTEGER DEFAULT 0")
    if 'gelmedi_nedeni' not in cols:
        c.execute("ALTER TABLE seanslar ADD COLUMN gelmedi_nedeni TEXT DEFAULT ''")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS danisan_rapor_dosyalari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        dosya_adi TEXT NOT NULL,
        dosya_yolu TEXT NOT NULL,
        mime_tur TEXT DEFAULT 'application/pdf',
        boyut INTEGER DEFAULT 0,
        eklenme_ts TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE SET NULL
    );
    """)
    c.execute("INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES('app_version',?)", (APP_VERSION,))
    conn.commit(); conn.close()


def _coerce_float(v, default=0.0):
    try:
        return float(v or 0)
    except Exception:
        return default


def _ucret_hesapla(hizmet, grup_turu, indirimli):
    if not hizmet:
        return 0.0, 0.0, 0.0
    paket_mi = int(hizmet.get('paket_mi') or 0) == 1
    grup_turu = (grup_turu or 'bireysel').strip()
    if paket_mi:
        fiyat_map = {
            'bireysel': _coerce_float(hizmet.get('seans_ucreti') or hizmet.get('bireysel_fiyat')),
            'grup2': _coerce_float(hizmet.get('grup2_fiyat') or hizmet.get('seans_ucreti') or hizmet.get('bireysel_fiyat')),
            'grup3': _coerce_float(hizmet.get('grup3_fiyat') or hizmet.get('grup2_fiyat') or hizmet.get('seans_ucreti') or hizmet.get('bireysel_fiyat')),
        }
        toplam = fiyat_map.get(grup_turu, fiyat_map['bireysel'])
        paket_seans = int(hizmet.get('paket_seans') or 1) or 1
        ucret = round(toplam / paket_seans, 2)
    else:
        if grup_turu == 'grup2' and _coerce_float(hizmet.get('grup2_fiyat')) > 0:
            ucret = _coerce_float(hizmet.get('grup2_fiyat'))
        elif grup_turu == 'grup3' and _coerce_float(hizmet.get('grup3_fiyat')) > 0:
            ucret = _coerce_float(hizmet.get('grup3_fiyat'))
        elif indirimli and _coerce_float(hizmet.get('grup2_fiyat')) > 0:
            ucret = _coerce_float(hizmet.get('grup2_fiyat'))
        else:
            ucret = _coerce_float(hizmet.get('seans_ucreti') or hizmet.get('bireysel_fiyat'))
    terapist_oran = _coerce_float(hizmet.get('terapist_prim_orani'))
    t_pay = round(ucret * terapist_oran, 2)
    i_pay = round(ucret - t_pay, 2)
    return float(ucret), t_pay, i_pay


def seans_ekle(danisan_id, terapist_id, hizmet_id, tarih, tip='normal',
               grup_turu='bireysel', indirimli=0, soap=None, saat='', sure_dk=45, oda_id=None,
               ucret_alindi=0, tahsilat_tarihi='', gelmedi=0, gelmedi_nedeni=''):
    conn = get_db(); c = conn.cursor()
    h_list = q(conn, "SELECT * FROM hizmet_alanlari WHERE id=?", (hizmet_id,)) if hizmet_id else []
    h = h_list[0] if h_list else None
    ucret, t_pay, i_pay = _ucret_hesapla(h, grup_turu, indirimli)
    if soap is None:
        soap = {}
    elif isinstance(soap, str):
        soap = {'s': soap, 'o': '', 'a': '', 'p': ''}
    elif not isinstance(soap, dict):
        soap = dict(soap) if hasattr(soap, 'items') else {'s': str(soap), 'o': '', 'a': '', 'p': ''}
    ucret_alindi = 1 if str(ucret_alindi) in ('1', 'True', 'true', 'on') or ucret_alindi is True else 0
    gelmedi = 1 if str(gelmedi) in ('1', 'True', 'true', 'on') or gelmedi is True else 0
    gelmedi_nedeni = (gelmedi_nedeni or '').strip()
    tahsilat_tarihi = (tahsilat_tarihi or '').strip()
    if gelmedi:
        ucret = 0.0
        t_pay = 0.0
        i_pay = 0.0
        ucret_alindi = 0
        tahsilat_tarihi = ''
    else:
        if ucret_alindi and not tahsilat_tarihi:
            tahsilat_tarihi = tarih
        if not ucret_alindi:
            tahsilat_tarihi = ''
    c.execute("SELECT id FROM seanslar WHERE danisan_id=? AND terapist_id=? AND tarih=? AND COALESCE(saat,'')=COALESCE(?, '')",
              (danisan_id, terapist_id, tarih, saat))
    mevcut = c.fetchone()
    if mevcut:
        c.execute("""UPDATE seanslar SET hizmet_id=?,tip=?,grup_turu=?,ucret=?,
            terapist_payi=?,isletme_payi=?,indirimli=?,ucret_alindi=?,tahsilat_tarihi=?,
            soap_s=?,soap_o=?,soap_a=?,soap_p=?, saat=?, sure_dk=?, oda_id=?, gelmedi=?, gelmedi_nedeni=? WHERE id=?""",
            (hizmet_id, tip, grup_turu, ucret, t_pay, i_pay, indirimli, ucret_alindi, tahsilat_tarihi,
             soap.get('s',''), soap.get('o',''), soap.get('a',''), soap.get('p',''),
             saat, sure_dk, oda_id, gelmedi, gelmedi_nedeni, mevcut['id']))
        lid = mevcut['id']
    else:
        c.execute("""INSERT INTO seanslar
            (danisan_id,terapist_id,hizmet_id,tarih,tip,grup_turu,ucret,
             terapist_payi,isletme_payi,indirimli,ucret_alindi,tahsilat_tarihi,
             soap_s,soap_o,soap_a,soap_p,saat,sure_dk,oda_id,gelmedi,gelmedi_nedeni)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (danisan_id, terapist_id, hizmet_id, tarih, tip, grup_turu, ucret,
             t_pay, i_pay, indirimli, ucret_alindi, tahsilat_tarihi,
             soap.get('s',''), soap.get('o',''), soap.get('a',''), soap.get('p',''),
             saat, sure_dk, oda_id, gelmedi, gelmedi_nedeni))
        lid = c.lastrowid
    conn.commit(); conn.close(); return lid


def seans_durum_guncelle(seans_id, gelmedi=0, gelmedi_nedeni=''):
    conn = get_db()
    row = q(conn, "SELECT id, hizmet_id, grup_turu, indirimli FROM seanslar WHERE id=?", (seans_id,))
    if not row:
        conn.close(); raise ValueError('Seans bulunamadı')
    gelmedi = 1 if str(gelmedi) in ('1', 'True', 'true', 'on') or gelmedi is True else 0
    gelmedi_nedeni = (gelmedi_nedeni or '').strip()
    if gelmedi:
        conn.execute("UPDATE seanslar SET gelmedi=1, gelmedi_nedeni=?, ucret=0, terapist_payi=0, isletme_payi=0, ucret_alindi=0, tahsilat_tarihi='' WHERE id=?", (gelmedi_nedeni, seans_id))
    else:
        s = row[0]
        h_list = q(conn, "SELECT * FROM hizmet_alanlari WHERE id=?", (s['hizmet_id'],)) if s.get('hizmet_id') else []
        h = h_list[0] if h_list else None
        ucret, t_pay, i_pay = _ucret_hesapla(h, s.get('grup_turu') or 'bireysel', s.get('indirimli') or 0)
        conn.execute("UPDATE seanslar SET gelmedi=0, gelmedi_nedeni='', ucret=?, terapist_payi=?, isletme_payi=? WHERE id=?", (ucret, t_pay, i_pay, seans_id))
    conn.commit(); conn.close(); return {'ok': True}


_prev_danisan_detay_v380 = danisan_detay

def danisan_detay(did):
    d = _prev_danisan_detay_v380(did)
    if not d:
        return d
    conn = get_db()
    d['seans_gecmisi'] = q(conn, """SELECT s.id as id, s.tarih as tarih, COALESCE(s.saat,'') as saat, COALESCE(s.gelmedi,0) as gelmedi,
        COALESCE(s.gelmedi_nedeni,'') as gelmedi_nedeni, COALESCE(s.ucret,0) as ucret,
        COALESCE(h.alan_adi,'') as hizmet_adi, COALESCE(h.takvim_rengi,'') as takvim_rengi
        FROM seanslar s LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
        WHERE s.danisan_id=? ORDER BY date(s.tarih) DESC, COALESCE(s.saat,'') DESC, s.id DESC LIMIT 120""", (did,))
    pdfler = q(conn, "SELECT * FROM danisan_rapor_dosyalari WHERE danisan_id=? ORDER BY date(tarih) DESC, id DESC", (did,))
    for r in pdfler:
        r['url'] = f"/rapor_pdf?id={r['id']}"
    d['rapor_pdfler'] = pdfler
    d['son_rapor_pdf'] = pdfler[0] if pdfler else None
    rows = q(conn, """SELECT strftime('%Y-%W', tarih) as hafta, MIN(tarih) as ilk_tarih,
               SUM(CASE WHEN COALESCE(gelmedi,0)=0 THEN 1 ELSE 0 END) as gelen,
               SUM(CASE WHEN COALESCE(gelmedi,0)=1 THEN 1 ELSE 0 END) as gelmedi_sayisi
               FROM seanslar WHERE danisan_id=? GROUP BY strftime('%Y-%W', tarih)
               ORDER BY hafta DESC LIMIT 12""", (did,))
    rows = list(reversed(rows))
    d['siklik_grafik'] = {
        'labels': [r['ilk_tarih'] for r in rows],
        'gelen': [int(r.get('gelen') or 0) for r in rows],
        'gelmedi': [int(r.get('gelmedi_sayisi') or 0) for r in rows],
    }
    d['gelen_tarihleri'] = [x['tarih'] + (f" {str(x.get('saat') or '')[:5]}" if (x.get('saat') or '') else '') for x in d['seans_gecmisi'] if int(x.get('gelmedi') or 0) == 0][:60]
    conn.close()
    return d


def _safe_pdf_name(name):
    name = re.sub(r'[^\w\-. ]+', '_', str(name or 'rapor.pdf')).strip() or 'rapor.pdf'
    if not name.lower().endswith('.pdf'):
        name += '.pdf'
    return name


def rapor_pdf_kaydet(d):
    danisan_id = int(d['danisan_id'])
    terapist_id = int(d['terapist_id']) if str(d.get('terapist_id') or '').strip() else None
    tarih = (d.get('tarih') or date.today().isoformat())[:10]
    dosya_adi = _safe_pdf_name(d.get('dosya_adi') or 'rapor.pdf')
    raw = d.get('base64') or ''
    if raw.startswith('data:'):
        raw = raw.split(',', 1)[1] if ',' in raw else ''
    blob = base64.b64decode(raw or b'', validate=False)
    if not blob or not blob.startswith(b'%PDF'):
        raise ValueError('Yalnızca PDF dosyası yüklenebilir')
    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    save_name = f"danisan_{danisan_id}_{ts}_{dosya_adi}"
    save_path = os.path.join(get_reports_dir(), save_name)
    with open(save_path, 'wb') as f:
        f.write(blob)
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO danisan_rapor_dosyalari(danisan_id, terapist_id, tarih, dosya_adi, dosya_yolu, mime_tur, boyut)
                 VALUES(?,?,?,?,?,?,?)""", (danisan_id, terapist_id, tarih, dosya_adi, save_path, 'application/pdf', len(blob)))
    conn.commit(); lid = c.lastrowid; conn.close(); return lid


def rapor_pdf_sil(rid):
    conn = get_db()
    row = q(conn, "SELECT dosya_yolu FROM danisan_rapor_dosyalari WHERE id=?", (rid,))
    if row:
        try:
            if os.path.exists(row[0]['dosya_yolu']):
                os.remove(row[0]['dosya_yolu'])
        except Exception:
            pass
    conn.execute("DELETE FROM danisan_rapor_dosyalari WHERE id=?", (rid,))
    conn.commit(); conn.close(); return {'ok': True}


def _serve_pdf_file(handler, rid):
    conn = get_db()
    rows = q(conn, "SELECT * FROM danisan_rapor_dosyalari WHERE id=?", (rid,))
    conn.close()
    if not rows:
        handler.send_response(404); handler.end_headers(); return
    row = rows[0]
    path = row.get('dosya_yolu') or ''
    if not path or not os.path.exists(path):
        handler.send_response(404); handler.end_headers(); return
    with open(path, 'rb') as f:
        b = f.read()
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/pdf')
    handler.send_header('Content-Length', str(len(b)))
    handler.send_header('Content-Disposition', f'inline; filename="{_safe_pdf_name(row.get("dosya_adi") or "rapor.pdf")}"')
    handler.end_headers()
    handler.wfile.write(b)










# ── v3.9.0: consistent records, packages, reporting and authenticated HTTP ──
import hashlib, hmac, math, time, zipfile, tempfile, html as html_lib
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from http.cookies import SimpleCookie
from functools import wraps

APP_VERSION = '3.9.0'
_SCHEMA_INIT = init_db
_INIT_LOCK = threading.RLock()
_WRITE_LOCK = threading.RLock()
_INITIALIZED_PATHS = set()

def money(value):
    try:
        n = Decimal(str(value or 0))
        if not n.is_finite() or n < 0 or n > Decimal('1000000000'):
            raise ValueError()
        return float(n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    except Exception:
        raise ValueError('Tutar 0 ile 1 milyar arasında geçerli bir sayı olmalıdır.')

def integer(value, low=0, high=100000):
    try:
        n = int(str(value))
        if not low <= n <= high: raise ValueError()
        return n
    except Exception: raise ValueError(f'Tam sayı {low}–{high} aralığında olmalıdır.')

def flag(value): return 1 if str(value).lower() in ('1','true','on') else 0

def valid_date(value):
    try: return date.fromisoformat(str(value)).isoformat()
    except Exception: raise ValueError('Tarih YYYY-AA-GG biçiminde olmalıdır.')

def valid_time(value):
    try:
        text = str(value)
        if len(text) != 5: raise ValueError()
        datetime.strptime(text, '%H:%M')
        return text
    except Exception: raise ValueError('Saat SS:DD biçiminde olmalıdır.')

def required(value, label='Alan'):
    value = str(value or '').strip()
    if not value: raise ValueError(label + ' zorunludur.')
    if len(value)>20000: raise ValueError(label + ' çok uzun.')
    return value

def get_db():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=20000')
    return c

@contextmanager
def transaction():
    with _WRITE_LOCK:
        c = get_db()
        try:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback(); raise
        finally: c.close()

def exists(c, table, ident, label='Kayıt'):
    if not ident: raise ValueError(label + ' seçiniz.')
    row = c.execute('SELECT * FROM '+table+' WHERE id=?', (ident,)).fetchone()
    if not row: raise ValueError(label + ' bulunamadı.')
    return dict(row)

def backup_bytes():
    buf=io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        dest=os.path.join(tmp,'arteterapi.db')
        a=get_db(); b=sqlite3.connect(dest)
        try: a.backup(b)
        finally: a.close(); b.close()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(dest,'arteterapi.db')
            conn=get_db()
            try:
                tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                files=q(conn,'SELECT id,dosya_yolu FROM danisan_rapor_dosyalari') if 'danisan_rapor_dosyalari' in tables else []
            finally: conn.close()
            for r in files:
                if os.path.isfile(r['dosya_yolu']): z.write(r['dosya_yolu'],'rapor_pdfler/'+str(r['id'])+'.pdf')
            z.writestr('OKU.txt','Veritabanı ve PDF dosyaları birlikte yedeklendi. Geri yüklerken uygulama kapalı olmalıdır. DB dosyasını veri klasörüne, rapor_pdfler klasörünü aynı dizine koyun. Uygulama açılışta rapor yollarını yeniden eşler.')
    return buf.getvalue()

def init_db():
    with _INIT_LOCK:
        key=os.path.abspath(DB_PATH)
        if key in _INITIALIZED_PATHS: return
        if os.path.isfile(DB_PATH) and os.path.getsize(DB_PATH):
            c=get_db()
            try:
                try: done=c.execute("SELECT deger FROM ayarlar WHERE anahtar='schema_390'").fetchone()
                except sqlite3.Error: done=None
            finally:c.close()
            if not done:
                folder=os.path.join(os.path.dirname(DB_PATH),'yedekler');os.makedirs(folder,exist_ok=True)
                with open(os.path.join(folder,'v390_oncesi_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'wb') as f:f.write(backup_bytes())
        _SCHEMA_INIT()
        with transaction() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS pilates_paketleri(
                id INTEGER PRIMARY KEY AUTOINCREMENT, danisan_id INTEGER NOT NULL,
                ad TEXT NOT NULL, fiyat REAL NOT NULL DEFAULT 0,
                seans_sayisi INTEGER NOT NULL DEFAULT 8, hediye_seans INTEGER NOT NULL DEFAULT 0,
                baslangic TEXT NOT NULL, bitis TEXT NOT NULL, grup_turu TEXT NOT NULL DEFAULT 'bireysel',
                aktif INTEGER NOT NULL DEFAULT 1, legacy INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS automation_runs(rule_id INTEGER, target_key TEXT, run_date TEXT,
                PRIMARY KEY(rule_id,target_key,run_date));
            ''')
            for table,fields in {
                'seanslar':{'paket_id':'INTEGER REFERENCES pilates_paketleri(id)','hediye':'INTEGER DEFAULT 0','hak_dustu':'INTEGER DEFAULT 1','prim_orani':'REAL DEFAULT 0','anlasilan_ucret':'REAL DEFAULT 0'},
                'odemeler':{'seans_id':'INTEGER REFERENCES seanslar(id) ON DELETE CASCADE','paket_id':'INTEGER REFERENCES pilates_paketleri(id) ON DELETE CASCADE'},
                'kasa':{'kaynak_id':'INTEGER'},
                'hizmet_alanlari':{'hediye_seans':'INTEGER DEFAULT 0'},
                'haftalik_program_sablonlari':{'grup_turu':"TEXT DEFAULT 'bireysel'"}
            }.items():
                cols={r['name'] for r in q(c,'PRAGMA table_info('+table+')')}
                for col,typ in fields.items():
                    if col not in cols:c.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
            first=not c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_390'").fetchone()
            if first:
                c.execute('UPDATE seanslar SET anlasilan_ucret=ucret')
                c.execute('UPDATE seanslar SET prim_orani=CASE WHEN ucret>0 THEN terapist_payi/ucret ELSE COALESCE((SELECT terapist_prim_orani FROM hizmet_alanlari WHERE id=seanslar.hizmet_id),0) END')
                c.execute('UPDATE seanslar SET hak_dustu=CASE WHEN gelmedi=1 THEN 0 ELSE 1 END')
                # Only unambiguous historic ledger links are migrated; never guess a payment identity.
                for table,source,desc in [('odemeler','odeme',''),('giderler','gider','')]:
                    for r in q(c,'SELECT * FROM '+table+' ORDER BY id'):
                        candidates=q(c,'SELECT * FROM kasa WHERE kaynak=? AND tarih=? AND tutar=? AND kaynak_id IS NULL',(source,r['tarih'],r['tutar']))
                        if table=='odemeler':
                            d=c.execute('SELECT ad,soyad FROM danisanlar WHERE id=?',(r['danisan_id'],)).fetchone()
                            exact=[x for x in candidates if d and x['aciklama']=='Ödeme: '+d['ad']+' '+(d['soyad'] or '')]
                        else:exact=[x for x in candidates if x['aciklama']==(r['aciklama'] or r['kategori'])]
                        if len(exact)==1:c.execute('UPDATE kasa SET kaynak_id=? WHERE id=?',(r['id'],exact[0]['id']))
                # Preserve historic prices and payment rows; the user confirms legacy package terms.
                for d in q(c,"SELECT * FROM danisanlar d WHERE pilates_baslangic_tarihi<>'' OR EXISTS(SELECT 1 FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=d.id AND h.kategori='pilates')"):
                    try:
                        inferred=c.execute("SELECT MIN(s.tarih) FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=? AND h.kategori='pilates'",(d['id'],)).fetchone()[0]
                        start=valid_date(d['pilates_baslangic_tarihi'] or inferred)
                    except ValueError:continue
                    sample=c.execute("SELECT s.*,h.paket_seans,h.paket_hafta,h.seans_ucreti,h.grup2_fiyat,h.grup3_fiyat FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=? AND h.kategori='pilates' ORDER BY s.tarih DESC LIMIT 1",(d['id'],)).fetchone()
                    group=(sample['grup_turu'] if sample else 'bireysel') or 'bireysel';num=(sample['paket_seans'] if sample else 8) or 8;weeks=(sample['paket_hafta'] if sample else 6) or 6
                    price=(sample[{'bireysel':'seans_ucreti','grup2':'grup2_fiyat','grup3':'grup3_fiyat'}.get(group,'seans_ucreti')] if sample else 0) or 0
                    end=(date.fromisoformat(start)+timedelta(days=int(weeks)*7-1)).isoformat()
                    pid=c.execute('INSERT INTO pilates_paketleri(danisan_id,ad,fiyat,seans_sayisi,baslangic,bitis,grup_turu,legacy) VALUES(?,?,?,?,?,?,?,1)',(d['id'],'Eski paket — kontrol ediniz',price,max(1,num),start,end,group)).lastrowid
                    c.execute("UPDATE seanslar SET paket_id=? WHERE danisan_id=? AND tarih BETWEEN ? AND ? AND hizmet_id IN(SELECT id FROM hizmet_alanlari WHERE kategori='pilates')",(pid,d['id'],start,end))
            for r in q(c,'SELECT id,dosya_yolu FROM danisan_rapor_dosyalari'):
                if not os.path.isfile(r['dosya_yolu']):
                    restored=os.path.join(os.path.dirname(DB_PATH),'rapor_pdfler',str(r['id'])+'.pdf')
                    if os.path.isfile(restored):c.execute('UPDATE danisan_rapor_dosyalari SET dosya_yolu=? WHERE id=?',(restored,r['id']))
            c.execute("INSERT OR REPLACE INTO ayarlar VALUES('schema_390','1')")
            c.execute("INSERT OR REPLACE INTO ayarlar VALUES('app_version',?)",(APP_VERSION,))
        _INITIALIZED_PATHS.add(key)

def terapistler_listesi(include_inactive=False):
    c=get_db()
    try:return q(c,'SELECT * FROM terapistler'+('' if include_inactive else ' WHERE aktif=1')+' ORDER BY ad')
    finally:c.close()

def odalar_listesi():
    c=get_db()
    try:return q(c,'SELECT * FROM odalar ORDER BY aktif DESC,ad')
    finally:c.close()

def hizmetler_listesi(terapist_id=None,include_inactive=False):
    c=get_db()
    try:return q(c,'SELECT h.*,t.ad as terapist_adi FROM hizmet_alanlari h JOIN terapistler t ON t.id=h.terapist_id WHERE 1=1'+('' if include_inactive else ' AND h.aktif=1')+(' AND h.terapist_id=?' if terapist_id else '')+' ORDER BY h.alan_adi',([terapist_id] if terapist_id else []))
    finally:c.close()

def danisan_ekle(d):
    with transaction() as c:
        fields=['terapist_id','ad','soyad','telefon','email','dogum_tarihi','tckn','cinsiyet','meslek','tani','sikayet','hedefler','notlar']
        exists(c,'terapistler',d.get('terapist_id'),'Terapist');d=dict(d);d['ad']=required(d.get('ad'),'Ad')
        if d.get('dogum_tarihi'):valid_date(d['dogum_tarihi'])
        did=c.execute('INSERT INTO danisanlar('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[d.get(f,'') for f in fields]).lastrowid
        _danisan_terapistleri_yaz(c,did,d['terapist_id'],d.get('terapist_ids') or [])
        return did

def danisan_guncelle(d):
    with transaction() as c:
        old=exists(c,'danisanlar',d.get('id'),'Danışan');v={**old,**d}
        exists(c,'terapistler',v['terapist_id'],'Terapist');v['ad']=required(v['ad'],'Ad')
        if v.get('dogum_tarihi'):valid_date(v['dogum_tarihi'])
        fields=['terapist_id','ad','soyad','telefon','email','dogum_tarihi','tckn','cinsiyet','meslek','tani','sikayet','hedefler','notlar','aktif']
        c.execute('UPDATE danisanlar SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',[v[f] for f in fields]+[d['id']])
        ids=d.get('terapist_ids')
        if ids is None:ids=[r['terapist_id'] for r in q(c,'SELECT terapist_id FROM danisan_terapistler WHERE danisan_id=?',(d['id'],))]
        _danisan_terapistleri_yaz(c,d['id'],v['terapist_id'],ids)

def danisan_sil(did):
    # Archive: clinical history and financial audit trails stay intact.
    with transaction() as c:
        exists(c,'danisanlar',did,'Danışan')
        c.execute('UPDATE danisanlar SET aktif=0 WHERE id=?',(did,))
        c.execute('UPDATE haftalik_program_sablonlari SET aktif=0 WHERE danisan_id=?',(did,))
        c.execute('UPDATE portal_erisimleri SET aktif=0 WHERE danisan_id=?',(did,))

_DETAIL_BASE=danisan_detay

def danisan_detay(did):
    d=_DETAIL_BASE(did)
    if not d:return None
    c=get_db()
    try:
        d['toplam_seans']=c.execute('SELECT COUNT(*) FROM seanslar WHERE danisan_id=? AND gelmedi=0',(did,)).fetchone()[0]
        d['seanslar']=q(c,'''SELECT s.*,h.alan_adi hizmet_adi,t.ad terapist_adi FROM seanslar s LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id LEFT JOIN terapistler t ON t.id=s.terapist_id WHERE s.danisan_id=? ORDER BY tarih DESC,saat DESC,id DESC''',(did,))
        for r in d['rapor_pdfler']:r.pop('dosya_yolu',None)
        if d.get('son_rapor_pdf'):d['son_rapor_pdf'].pop('dosya_yolu',None)
        return d
    finally:c.close()

def _ucret_hesapla(hizmet,grup_turu,indirimli):
    if not hizmet:raise ValueError('Hizmet seçiniz.')
    if grup_turu not in ('bireysel','grup2','grup3'):raise ValueError('Geçersiz grup türü.')
    field={'bireysel':'seans_ucreti','grup2':'grup2_fiyat','grup3':'grup3_fiyat'}[grup_turu]
    price=money(hizmet.get(field) or (hizmet.get('bireysel_fiyat',0) if grup_turu=='bireysel' else 0))
    if not flag(hizmet.get('paket_mi')) and indirimli and hizmet.get('grup2_fiyat'):price=money(hizmet['grup2_fiyat'])
    if flag(hizmet.get('paket_mi')):price=money(Decimal(str(price))/integer(hizmet.get('paket_seans',1),1))
    rate=float(hizmet.get('terapist_prim_orani') or 0)
    if not math.isfinite(rate) or not 0<=rate<=1:raise ValueError('Terapist payı 0–1 aralığında olmalıdır.')
    tp=money(Decimal(str(price))*Decimal(str(rate)))
    return price,tp,round(price-tp,2)

def paketler_listesi(danisan_id=None):
    c=get_db()
    try:
        rows=q(c,'''SELECT p.*,d.ad||' '||d.soyad danisan_adi,d.pilates_paket_odendi eski_odendi,
          (SELECT COUNT(*) FROM seanslar s WHERE s.paket_id=p.id AND s.hak_dustu=1 AND s.hediye=0) kullanilan,
          (SELECT COUNT(*) FROM seanslar s WHERE s.paket_id=p.id AND s.hak_dustu=1 AND s.hediye=1) hediye_kullanilan,
          (SELECT COALESCE(SUM(o.tutar),0) FROM odemeler o WHERE o.paket_id=p.id) tahsilat,
          (SELECT COALESCE(SUM(s.ucret),0) FROM seanslar s WHERE s.paket_id=p.id) kazanilan
          FROM pilates_paketleri p JOIN danisanlar d ON d.id=p.danisan_id'''+(' WHERE p.danisan_id=?' if danisan_id else '')+' ORDER BY p.baslangic DESC,p.id DESC',([danisan_id] if danisan_id else []))
        for r in rows:
            r['kalan']=max(0,r['seans_sayisi']-r['kullanilan'])+max(0,r['hediye_seans']-r['hediye_kullanilan'])
            r['bakiye']=round(max(0,r['fiyat']-r['tahsilat']),2)
        return rows
    finally:c.close()

def paket_kaydet(d):
    with transaction() as c:
        old=exists(c,'pilates_paketleri',d['id'],'Paket') if d.get('id') else {}
        v={**old,**d};did=integer(v.get('danisan_id'),1);exists(c,'danisanlar',did,'Danışan')
        if old and did!=old['danisan_id']:raise ValueError('Paket başka danışana taşınamaz.')
        start=valid_date(v.get('baslangic'));end=valid_date(v.get('bitis'))
        if end<start:raise ValueError('Bitiş başlangıçtan önce olamaz.')
        n=integer(v.get('seans_sayisi',8),1);gift=integer(v.get('hediye_seans',0));price=money(v.get('fiyat'))
        group=v.get('grup_turu','bireysel')
        if group not in ('bireysel','grup2','grup3'):raise ValueError('Grup seçimi geçersiz.')
        if old:
            used=c.execute('SELECT COUNT(*),SUM(CASE WHEN hediye=1 THEN 1 ELSE 0 END),COALESCE(SUM(ucret),0) FROM seanslar WHERE paket_id=? AND hak_dustu=1',(old['id'],)).fetchone()
            gu=used[1] or 0
            if n<used[0]-gu or gift<gu:raise ValueError('Seans hakkı kullanılmış sayının altına indirilemez.')
            if price<float(used[2]):raise ValueError('Paket fiyatı kaydedilmiş seans kazancından düşük olamaz.')
            if n==used[0]-gu and abs(price-float(used[2]))>.005:raise ValueError('Tüm ücretli haklar kullanıldı; tutarı artırmak için ücretli seans da ekleyin.')
            if c.execute('SELECT 1 FROM seanslar WHERE paket_id=? AND (tarih<? OR tarih>?)',(old['id'],start,end)).fetchone():raise ValueError('Yeni tarihler mevcut paket seanslarını dışarıda bırakamaz.')
            paid=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE paket_id=?',(old['id'],)).fetchone()[0]
            if price<paid:raise ValueError('Önce fazla tahsilatı düzeltin; fiyat tahsilatın altına inemez.')
        vals=(did,required(v.get('ad','Pilates Paketi'),'Paket adı'),price,n,gift,start,end,group,flag(v.get('aktif',1)))
        if old:
            c.execute('UPDATE pilates_paketleri SET danisan_id=?,ad=?,fiyat=?,seans_sayisi=?,hediye_seans=?,baslangic=?,bitis=?,grup_turu=?,aktif=?,legacy=0 WHERE id=?',vals+(old['id'],));return old['id']
        return c.execute('INSERT INTO pilates_paketleri(danisan_id,ad,fiyat,seans_sayisi,hediye_seans,baslangic,bitis,grup_turu,aktif) VALUES(?,?,?,?,?,?,?,?,?)',vals).lastrowid

def _payment_write(c,d):
    did=integer(d.get('danisan_id'),1);exists(c,'danisanlar',did,'Danışan')
    sid=d.get('seans_id') or None;pid=d.get('paket_id') or None;tid=d.get('terapist_id') or None
    amount=money(d.get('tutar'))
    if amount<=0:raise ValueError('Ödeme sıfırdan büyük olmalıdır.')
    if sid and pid:raise ValueError('Ödeme için seans veya paket seçiniz.')
    if sid:
        s=exists(c,'seanslar',sid,'Seans')
        if s['danisan_id']!=did:raise ValueError('Seans danışanı farklı.')
        if s['paket_id']:raise ValueError('Bu seansın ödemesini paket üzerinden girin.')
        paid=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE seans_id=?',(sid,)).fetchone()[0]
        if amount>round(s['ucret']-paid,2):raise ValueError('Ödeme kalan seans borcunu aşıyor.')
        tid=s['terapist_id']
    if pid:
        p=exists(c,'pilates_paketleri',pid,'Paket')
        if p['danisan_id']!=did:raise ValueError('Paket danışanı farklı.')
        paid=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE paket_id=?',(pid,)).fetchone()[0]
        if amount>round(p['fiyat']-paid,2):raise ValueError('Ödeme paket bakiyesini aşıyor.')
        tid=None # A shared package belongs to the clinic; session earnings belong to each provider.
    if tid:exists(c,'terapistler',tid,'Terapist')
    dt=valid_date(d.get('tarih'));method=d.get('yontem','nakit')
    if method not in ('nakit','kart','havale'):raise ValueError('Ödeme yöntemi geçersiz.')
    oid=c.execute('INSERT INTO odemeler(danisan_id,terapist_id,tarih,tutar,yontem,notlar,seans_id,paket_id) VALUES(?,?,?,?,?,?,?,?)',(did,tid,dt,amount,method,d.get('notlar',''),sid,pid)).lastrowid
    c.execute('INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak,kaynak_id) VALUES(?,?,?,?,?,?)',(dt,'giris',amount,'Tahsilat #'+str(oid),'odeme',oid))
    if sid:_sync_paid(c,sid)
    return oid

def _sync_paid(c,sid):
    s=exists(c,'seanslar',sid,'Seans');p=c.execute('SELECT COALESCE(SUM(tutar),0),MAX(tarih) FROM odemeler WHERE seans_id=?',(sid,)).fetchone()
    full=s['ucret']>0 and p[0]>=s['ucret']-.005
    c.execute('UPDATE seanslar SET ucret_alindi=?,tahsilat_tarihi=? WHERE id=?',(int(full),p[1] if full else '',sid))

def odeme_ekle(d):
    with transaction() as c:return _payment_write(c,d)

def odeme_sil(oid):
    with transaction() as c:
        o=exists(c,'odemeler',oid,'Ödeme')
        if not c.execute("SELECT 1 FROM kasa WHERE kaynak='odeme' AND kaynak_id=?",(oid,)).fetchone():raise ValueError('Eski ödeme kasa kaydıyla eşleşmiyor. Önce Kasa ekranından bu ödemeye eşleştirin.')
        c.execute("DELETE FROM kasa WHERE kaynak='odeme' AND kaynak_id=?",(oid,));c.execute('DELETE FROM odemeler WHERE id=?',(oid,))
        if o.get('seans_id'):_sync_paid(c,o['seans_id'])

def seans_kaydet(d):
    with transaction() as c:
        old=exists(c,'seanslar',d['id'],'Seans') if d.get('id') else {}
        v={**old,**d};did=integer(v.get('danisan_id'),1);tid=integer(v.get('terapist_id'),1)
        client=exists(c,'danisanlar',did,'Danışan');therapist=exists(c,'terapistler',tid,'Terapist');h=exists(c,'hizmet_alanlari',v.get('hizmet_id'),'Hizmet')
        if not client['aktif'] or not therapist['aktif'] or not h['aktif']:raise ValueError('Danışan, terapist ve hizmet aktif olmalıdır.')
        if not service_allows(c,h['id'],tid) and not (old and old['terapist_id']==tid and old['hizmet_id']==h['id']):raise ValueError('Seçilen terapist bu hizmete atanmamış.')
        dt=valid_date(v.get('tarih'))
        if not old and dt>date.today().isoformat():raise ValueError('Gelecek seansları haftalık programa ekleyin; katılımı seans gününde kaydedin.')
        st=valid_time(v.get('saat'));duration=integer(v.get('sure_dk',45),5,480)
        if _saat_dakika(st)+duration>1440:raise ValueError('Seans gece yarısını aşamaz.')
        room=v.get('oda_id') or None
        if room and not exists(c,'odalar',room,'Oda')['aktif']:raise ValueError('Oda pasif.')
        typ=v.get('tip','normal')
        if typ not in ('normal','degerlendirme','telafi'):raise ValueError('Seans türü geçersiz.')
        no=flag(v.get('gelmedi',0));consumed=1 if not no else flag(v.get('hak_dustu',0));gift=flag(v.get('hediye',0));pid=v.get('paket_id') or None
        if not old and h['kategori']=='pilates' and not pid:raise ValueError('Pilates seansı için üyenin satın aldığı paketi seçin.')
        group=v.get('grup_turu','bireysel');ind=flag(v.get('indirimli',0))
        if old and old.get('paket_id') and str(old['paket_id'])!=str(pid):raise ValueError('Kayıtlı paket bağlantısını değiştirmek için önce seansı silip yeniden kaydedin.')
        conflict=c.execute("SELECT id FROM seanslar WHERE danisan_id=? AND terapist_id=? AND tarih=? AND saat=? AND id<>?",(did,tid,dt,st,old.get('id',0))).fetchone()
        if conflict:raise ValueError('Aynı danışan/terapist/saat için seans var. Mevcut kaydı düzenleyin.')
        rate=float(old.get('prim_orani') if old else h.get('terapist_prim_orani',0))
        if not 0<=rate<=1:raise ValueError('Prim oranını hizmet ayarlarından düzeltin.')
        same_price=bool(old and str(old.get('hizmet_id'))==str(h['id']) and group==old['grup_turu'] and ind==old['indirimli'] and gift==old['hediye'] and consumed==old['hak_dustu'])
        if pid:
            p=exists(c,'pilates_paketleri',pid,'Paket')
            if p['danisan_id']!=did or h['kategori']!='pilates':raise ValueError('Paket/danışan/hizmet eşleşmiyor.')
            if not p['baslangic']<=dt<=p['bitis']:raise ValueError('Seans paket tarih aralığı dışında.')
            if not p['aktif'] and not old:raise ValueError('Paket pasif.')
            group=p['grup_turu']
            rows=q(c,'SELECT hediye,ucret FROM seanslar WHERE paket_id=? AND hak_dustu=1 AND id<>?',(pid,old.get('id',0)))
            paidused=sum(not x['hediye'] for x in rows);giftused=sum(bool(x['hediye']) for x in rows)
            if consumed and not gift and paidused>=p['seans_sayisi']:gift=1
            if consumed and ((gift and giftused>=p['hediye_seans']) or (not gift and paidused>=p['seans_sayisi'])):raise ValueError('Paketin seçilen seans hakkı bitti.')
            if gift or not consumed:price=0.0
            elif old and old['hak_dustu'] and not old['hediye']:price=float(old['ucret'])
            else:
                remaining=Decimal(str(p['fiyat']))-sum((Decimal(str(x['ucret'])) for x in rows),Decimal(0))
                if remaining<0:raise ValueError('Eski paket tutarı kazanılan gelirden düşük; paket tutarını kontrol edin.')
                price=money(remaining/(p['seans_sayisi']-paidused))
        else:
            if h['kategori']=='pilates' and h['paket_mi'] and not old:raise ValueError('Pilates paket hizmeti için paket seçiniz.')
            keep_snapshot=bool(old and str(old.get('hizmet_id'))==str(h['id']) and group==old['grup_turu'] and ind==old['indirimli'])
            price=float(old.get('anlasilan_ucret') or old['ucret']) if keep_snapshot else _ucret_hesapla(h,group,ind)[0]
            agreed=price
            if gift or not consumed:price=0.0
        agreed=price if pid else agreed
        tp=money(Decimal(str(price))*Decimal(str(rate)));ip=round(price-tp,2)
        linked=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE seans_id=?',(old.get('id',0),)).fetchone()[0]
        if linked>price+.005:raise ValueError('Seansın tahsilatı yeni ücretinden yüksek. Önce ödeme kaydını düzeltin.')
        soap=d.get('soap')
        if soap is None:soap={k:old.get('soap_'+k,'') for k in 'soap'}
        if not isinstance(soap,dict):raise ValueError('SOAP alanı geçersiz.')
        fields=['danisan_id','terapist_id','hizmet_id','tarih','saat','sure_dk','oda_id','tip','grup_turu','indirimli','gelmedi','gelmedi_nedeni','hak_dustu','hediye','paket_id','ucret','terapist_payi','isletme_payi','prim_orani','anlasilan_ucret','soap_s','soap_o','soap_a','soap_p']
        values=[did,tid,h['id'],dt,st,duration,room,typ,group,ind,no,str(v.get('gelmedi_nedeni','')) if no else '',consumed,gift,pid,price,tp,ip,rate,agreed]+[str(soap.get(k,'')) for k in 'soap']
        if old:c.execute('UPDATE seanslar SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',values+[old['id']]);sid=old['id']
        else:sid=c.execute('INSERT INTO seanslar('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',values).lastrowid
        origin_day=v.get('plan_tarihi') or '';origin_time=v.get('planlanan_saat') or '';origin_program=str(v.get('program_id') or '')
        if origin_day:valid_date(origin_day)
        if origin_time:valid_time(origin_time)
        c.execute('UPDATE seanslar SET program_id=?,planlanan_saat=?,plan_tarihi=? WHERE id=?',(origin_program,origin_time,origin_day,sid))
        c.execute("INSERT OR IGNORE INTO danisan_terapistler(danisan_id,terapist_id,rol) VALUES(?,?,'ek')",(did,tid))
        legacy_paid=bool(old and old.get('ucret_alindi') and not linked)
        if flag(d.get('ucret_alindi')) and not pid and price>linked and not legacy_paid:
            _payment_write(c,{'danisan_id':did,'seans_id':sid,'terapist_id':tid,'tutar':round(price-linked,2),'tarih':d.get('tahsilat_tarihi') or dt,'yontem':d.get('yontem','nakit')})
        if (not old or linked or 'ucret_alindi' in d) and not legacy_paid:_sync_paid(c,sid)
        return sid

def seans_ekle(danisan_id,terapist_id,hizmet_id,tarih,tip='normal',grup_turu='bireysel',indirimli=0,soap=None,saat='',sure_dk=45,oda_id=None,ucret_alindi=0,tahsilat_tarihi='',gelmedi=0,gelmedi_nedeni='',**extra):
    d=locals().copy();d.pop('extra');d.update(extra);return seans_kaydet(d)

def seans_durum_guncelle(seans_id,gelmedi=0,gelmedi_nedeni='',hak_dustu=0):
    return {'ok':True,'id':seans_kaydet({'id':seans_id,'gelmedi':gelmedi,'gelmedi_nedeni':gelmedi_nedeni,'hak_dustu':hak_dustu})}

def seans_sil(sid):
    with transaction() as c:
        exists(c,'seanslar',sid,'Seans')
        if c.execute('SELECT 1 FROM odemeler WHERE seans_id=?',(sid,)).fetchone():raise ValueError('Seansı silmeden önce bağlı tahsilatı silin.')
        c.execute('DELETE FROM seanslar WHERE id=?',(sid,))

def seans_odeme_durum_guncelle(sid,ucret_alindi,tahsilat_tarihi=''):
    if not flag(ucret_alindi):raise ValueError('Tahsilatı geri almak için Ödemeler ekranındaki ilgili işlemi silin.')
    return {'ok':True,'id':seans_kaydet({'id':sid,'ucret_alindi':1,'tahsilat_tarihi':tahsilat_tarihi})}

def odemeler_listesi(ay=None,terapist_id=None,danisan_id=None):
    c=get_db();sql='''SELECT o.*,d.ad||' '||d.soyad danisan_adi,COALESCE(t.ad,'Klinik / ortak paket') terapist_adi FROM odemeler o LEFT JOIN danisanlar d ON d.id=o.danisan_id LEFT JOIN terapistler t ON t.id=o.terapist_id WHERE 1=1''';params=[]
    for val,clause in [(ay," AND substr(o.tarih,1,7)=?"),(terapist_id,' AND o.terapist_id=?'),(danisan_id,' AND o.danisan_id=?')]:
        if val:sql+=clause;params.append(val)
    try:return q(c,sql+' ORDER BY o.tarih DESC,o.id DESC',params)
    finally:c.close()

def gelir_raporu(start=None,end=None,terapist_id=None):
    start=valid_date(start or date.today().replace(day=1).isoformat());end=valid_date(end or date.today().isoformat())
    if end<start:raise ValueError('Tarih aralığı geçersiz.')
    if (date.fromisoformat(end)-date.fromisoformat(start)).days>3660:raise ValueError('En çok 10 yıllık aralık seçiniz.')
    c=get_db()
    try:
        sessions=q(c,'''SELECT s.*,d.ad||' '||d.soyad danisan_adi,t.ad terapist_adi,h.alan_adi hizmet_adi FROM seanslar s LEFT JOIN danisanlar d ON d.id=s.danisan_id LEFT JOIN terapistler t ON t.id=s.terapist_id LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.tarih BETWEEN ? AND ?'''+(' AND s.terapist_id=?' if terapist_id else '')+' ORDER BY s.tarih,s.saat,s.id',[start,end]+([terapist_id] if terapist_id else []))
        def blank(key):return {'donem':key,'seans':0,'gelen':0,'gelmedi':0,'hediye':0,'brut':0,'terapist_payi':0,'isletme_payi':0}
        weeks={};months={};therapists={};total=blank('Toplam')
        day=date.fromisoformat(start)
        while day<=date.fromisoformat(end):
            wk=(day-timedelta(days=day.weekday())).isoformat();weeks.setdefault(wk,blank(wk));mo=day.strftime('%Y-%m');months.setdefault(mo,blank(mo));day+=timedelta(days=1)
        clean=[];data_issues=0
        for s in sessions:
            try:date.fromisoformat(s['tarih'])
            except ValueError:data_issues+=1;continue
            clean.append(s)
        sessions=clean
        for s in sessions:
            dt=date.fromisoformat(s['tarih']);wk=(dt-timedelta(days=dt.weekday())).isoformat();mo=dt.strftime('%Y-%m')
            th=therapists.setdefault(str(s['terapist_id']),{**blank(s['terapist_adi'] or 'Bilinmeyen'),'terapist_id':s['terapist_id']})
            for r in [total,weeks[wk],months[mo],th]:
                r['seans']+=1;r['gelen']+=int(not s['gelmedi']);r['gelmedi']+=int(bool(s['gelmedi']));r['hediye']+=int(bool(s['hediye'] and s['hak_dustu']))
                for target,field in [('brut','ucret'),('terapist_payi','terapist_payi'),('isletme_payi','isletme_payi')]:r[target]=round(r[target]+float(s[field] or 0),2)
        receipts=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE tarih BETWEEN ? AND ?'+(' AND terapist_id=?' if terapist_id else ''),[start,end]+([terapist_id] if terapist_id else [])).fetchone()[0]
        cost=c.execute('SELECT COALESCE(SUM(tutar),0) FROM giderler WHERE tarih BETWEEN ? AND ?',(start,end)).fetchone()[0]
        return {'data_issues':data_issues,'baslangic':start,'bitis':end,'toplam':total,'haftalik':list(weeks.values()),'aylik':list(months.values()),'terapistler':list(therapists.values()),'seanslar':sessions,'tahsilat':receipts,'gider':cost if not terapist_id else None,'nakit_farki':round(receipts-cost,2) if not terapist_id else None}
    finally:c.close()

def gelir_ozet(ay=None,terapist_id=None):
    if ay:
        start=valid_date(ay+'-01');dt=date.fromisoformat(start);end=date(dt.year,dt.month,calendar.monthrange(dt.year,dt.month)[1]).isoformat()
    else:start='2000-01-01';end=date.today().isoformat()
    # Compatibility projection for older read callers.
    if not ay:start=(date.today()-timedelta(days=3650)).isoformat()
    r=gelir_raporu(start,end,terapist_id);t=r['toplam']
    return {'seans_ozet':{'g':t['brut'],'t':t['terapist_payi'],'i':t['isletme_payi'],'sayi':t['seans']},'odeme_toplam':r['tahsilat'],'gider_toplam':r['gider'],'net_kar':r['nakit_farki'],'terapist_detay':r['terapistler'],'aylik':r['aylik']}

def haftalik_meta(week_start=None):
    dt=date.fromisoformat(valid_date(week_start or date.today().isoformat()));monday=dt-timedelta(days=dt.weekday());sunday=monday+timedelta(days=6)
    days=[{'index':i,'date':(monday+timedelta(days=i)).isoformat(),'label':(monday+timedelta(days=i)).strftime('%d.%m'),'day_name':WEEKDAY_SHORT[i],'full_name':WEEKDAY_NAMES[i]} for i in range(7)]
    return monday,sunday,days,[f'{h:02d}:{minute:02d}' for h in range(8,21) for minute in [0,15,30,45]]

def seans_haftalik_programi(week_start=None,terapist_id=None):
    mon,sun,days,hours=haftalik_meta(week_start);c=get_db()
    try:
        rows=q(c,'''SELECT s.*,d.ad||' '||d.soyad danisan_adi,t.ad terapist_adi,h.alan_adi hizmet_adi FROM seanslar s JOIN danisanlar d ON d.id=s.danisan_id JOIN terapistler t ON t.id=s.terapist_id LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE (s.tarih BETWEEN ? AND ? OR s.plan_tarihi BETWEEN ? AND ?)'''+(' AND s.terapist_id=?' if terapist_id else ''),[mon.isoformat(),sun.isoformat(),mon.isoformat(),sun.isoformat()]+([terapist_id] if terapist_id else []))
        keys={(r['tarih'],r['danisan_id'],r['terapist_id'],r['saat']) for r in rows}
        for r in rows:
            if r.get('plan_tarihi') and r.get('planlanan_saat'):keys.add((r['plan_tarihi'],r['danisan_id'],r['terapist_id'],r['planlanan_saat']))
        for r in q(c,"SELECT * FROM randevular WHERE durum='iptal' AND tarih BETWEEN ? AND ?",(mon.isoformat(),sun.isoformat())):keys.add((r['tarih'],r['danisan_id'],r['terapist_id'],r['saat']))
        rows=[r for r in rows if mon.isoformat()<=r['tarih']<=sun.isoformat()]
        for r in rows:r['kaynak']='gerceklesen'
        plans=haftalik_program_sablonlari_listesi(terapist_id)
        for p in plans:
            dt=(mon+timedelta(days=p['gun_index'])).isoformat()
            if (not p.get('baslangic') or dt>=p['baslangic']) and (not p.get('bitis') or dt<=p['bitis']) and (dt,p['danisan_id'],p['terapist_id'],p['saat']) not in keys:rows.append({**p,'tarih':dt,'kaynak':'planli','tip':'normal'})
        rows.sort(key=lambda x:(x['tarih'],x.get('saat') or ''))
        return {'week_start':mon.isoformat(),'week_end':sun.isoformat(),'days':days,'items':rows,'hours':hours}
    finally:c.close()

def haftalik_program_sablonlari_listesi(terapist_id=None):
    c=get_db()
    try:return q(c,'''SELECT p.*,d.ad||' '||d.soyad danisan_adi,d.pilates_paket_odendi eski_odendi,t.ad terapist_adi,h.alan_adi hizmet_adi,o.ad oda_adi FROM haftalik_program_sablonlari p JOIN danisanlar d ON d.id=p.danisan_id JOIN terapistler t ON t.id=p.terapist_id LEFT JOIN hizmet_alanlari h ON h.id=p.hizmet_id LEFT JOIN odalar o ON o.id=p.oda_id WHERE p.aktif=1 AND d.aktif=1'''+(' AND p.terapist_id=?' if terapist_id else '')+' ORDER BY p.gun_index,p.saat',[terapist_id] if terapist_id else [])
    finally:c.close()

_PLAN_SAVE=haftalik_program_kaydet

def haftalik_program_kaydet(d):
    d=dict(d);d['saat']=valid_time(d.get('saat'));d['gun_index']=integer(d.get('gun_index'),0,6);d['sure_dk']=integer(d.get('sure_dk',45),5,480)
    with transaction() as c:
        exists(c,'danisanlar',d.get('danisan_id'),'Danışan');exists(c,'terapistler',d.get('terapist_id'),'Terapist')
        h=exists(c,'hizmet_alanlari',d.get('hizmet_id'),'Hizmet')
        if not service_allows(c,h['id'],d['terapist_id']):raise ValueError('Seçilen terapist bu hizmete atanmamış.')
        if d.get('oda_id') and not exists(c,'odalar',d['oda_id'],'Oda')['aktif']:raise ValueError('Oda pasif.')
    pid=_PLAN_SAVE(d)
    with transaction() as c:
        c.execute('UPDATE haftalik_program_sablonlari SET grup_turu=? WHERE id=?',(d.get('grup_turu','bireysel'),pid))
        c.execute("INSERT OR IGNORE INTO danisan_terapistler VALUES(?,?,'ek')",(d['danisan_id'],d['terapist_id']))
    return pid

def gider_ekle(d):
    with transaction() as c:
        dt=valid_date(d.get('tarih'));amount=money(d.get('tutar'));cat=required(d.get('kategori'),'Kategori')
        if amount<=0:raise ValueError('Tutar sıfırdan büyük olmalıdır.')
        gid=c.execute('INSERT INTO giderler(tarih,kategori,tutar,aciklama) VALUES(?,?,?,?)',(dt,cat,amount,d.get('aciklama',''))).lastrowid
        c.execute("INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak,kaynak_id) VALUES(?,'cikis',?,?,'gider',?)",(dt,amount,d.get('aciklama',cat),gid));return gid

def gider_sil(gid):
    with transaction() as c:
        exists(c,'giderler',gid,'Gider')
        if not c.execute("SELECT 1 FROM kasa WHERE kaynak='gider' AND kaynak_id=?",(gid,)).fetchone():raise ValueError('Önce eski gideri Kasa ekranından eşleştirin.')
        c.execute("DELETE FROM kasa WHERE kaynak='gider' AND kaynak_id=?",(gid,));c.execute('DELETE FROM giderler WHERE id=?',(gid,))

def kasa_ekle(d):
    with transaction() as c:
        if d.get('tur') not in ('giris','cikis'):raise ValueError('Kasa türü geçersiz.')
        dt=valid_date(d.get('tarih'));amount=money(d.get('tutar'))
        if amount<=0:raise ValueError('Tutar sıfırdan büyük olmalıdır.')
        return c.execute("INSERT INTO kasa(tarih,tur,tutar,aciklama,kaynak) VALUES(?,?,?,?,'manuel')",(dt,d['tur'],amount,d.get('aciklama',''))).lastrowid

def kasa_sil(kid):
    with transaction() as c:
        r=exists(c,'kasa',kid,'Kasa')
        if r['kaynak']!='manuel':raise ValueError('Bağlı işlemi Ödeme/Gider ekranından silin.')
        c.execute('DELETE FROM kasa WHERE id=?',(kid,))

def kasa_eslestir(d):
    with transaction() as c:
        r=exists(c,'kasa',d.get('id'),'Kasa');source=r['kaynak']
        if r.get('kaynak_id') or source not in ('odeme','gider'):raise ValueError('Bu satır eşleştirmeye uygun değil.')
        o=exists(c,'odemeler' if source=='odeme' else 'giderler',d.get('kaynak_id'),'Kaynak')
        if o['tarih']!=r['tarih'] or float(o['tutar'])!=float(r['tutar']):raise ValueError('Tarih ve tutar aynı olmalı.')
        if c.execute('SELECT 1 FROM kasa WHERE kaynak=? AND kaynak_id=?',(source,o['id'])).fetchone():raise ValueError('Kaynak zaten eşleştirilmiş.')
        c.execute('UPDATE kasa SET kaynak_id=? WHERE id=?',(o['id'],r['id']))

def stok_hareket_ekle(d):
    with transaction() as c:
        row=exists(c,'stok_kalemleri',d.get('kalem_id'),'Stok');typ=d.get('tur');amount=money(d.get('miktar'));dt=valid_date(d.get('tarih') or date.today().isoformat())
        if typ not in ('giris','cikis','sayim'):raise ValueError('Stok hareket türü geçersiz.')
        if amount<=0 and typ!='sayim':raise ValueError('Miktar pozitif olmalıdır.')
        new=amount if typ=='sayim' else row['mevcut_stok']+(amount if typ=='giris' else -amount)
        if new<0:raise ValueError('Stok yeterli değil.')
        price=money(d.get('birim_fiyat'))
        c.execute('INSERT INTO stok_hareketleri(kalem_id,tarih,tur,miktar,birim_fiyat,aciklama) VALUES(?,?,?,?,?,?)',(row['id'],dt,typ,amount,price,d.get('aciklama','')))
        c.execute('UPDATE stok_kalemleri SET mevcut_stok=?,birim_maliyet=CASE WHEN ?>0 THEN ? ELSE birim_maliyet END WHERE id=?',(new,price,price,row['id']));return {'ok':True,'mevcut_stok':new}

def get_reports_dir():
    p=os.path.join(os.path.dirname(DB_PATH),'rapor_pdfler');os.makedirs(p,exist_ok=True);return p

def rapor_pdf_kaydet(d):
    raw=str(d.get('base64',''));raw=raw.split(',',1)[1] if raw.startswith('data:') and ',' in raw else raw
    try:blob=base64.b64decode(raw,validate=True)
    except Exception:raise ValueError('PDF verisi geçersiz.')
    if not blob.startswith(b'%PDF-') or len(blob)>10*1024*1024:raise ValueError('En fazla 10 MB PDF yükleyiniz.')
    saved=None
    try:
        with transaction() as c:
            did=integer(d.get('danisan_id'),1);exists(c,'danisanlar',did,'Danışan');tid=d.get('terapist_id') or None
            if tid:exists(c,'terapistler',tid,'Terapist')
            name=_safe_pdf_name(d.get('dosya_adi','rapor.pdf'))[:180];dt=valid_date(d.get('tarih') or date.today().isoformat())
            saved=os.path.join(get_reports_dir(),secrets.token_hex(18)+'.pdf')
            with open(saved,'xb') as f:f.write(blob)
            return c.execute('INSERT INTO danisan_rapor_dosyalari(danisan_id,terapist_id,tarih,dosya_adi,dosya_yolu,boyut) VALUES(?,?,?,?,?,?)',(did,tid,dt,name,saved,len(blob))).lastrowid
    except Exception:
        if saved and os.path.exists(saved):os.remove(saved)
        raise

def rapor_pdf_sil(rid):
    with transaction() as c:
        row=exists(c,'danisan_rapor_dosyalari',rid,'PDF')
        if os.path.isfile(row['dosya_yolu']):os.remove(row['dosya_yolu'])
        c.execute('DELETE FROM danisan_rapor_dosyalari WHERE id=?',(rid,))
    return {'ok':True}

def portal_veri(token):
    c=get_db()
    try:
        r=c.execute('''SELECT p.danisan_id FROM portal_erisimleri p JOIN danisanlar d ON d.id=p.danisan_id WHERE p.token=? AND p.aktif=1 AND d.aktif=1 AND p.son_gecerlilik>=?''',(token,date.today().isoformat())).fetchone()
        if not r:return None
        did=r['danisan_id'];d=c.execute('SELECT ad,soyad FROM danisanlar WHERE id=?',(did,)).fetchone()
        return {'danisan':dict(d),'randevular':q(c,"SELECT tarih,saat FROM randevular WHERE danisan_id=? AND tarih>=? AND durum NOT IN('iptal','tamamlandi') ORDER BY tarih,saat LIMIT 30",(did,date.today().isoformat())),'seanslar':q(c,'SELECT tarih,saat,gelmedi FROM seanslar WHERE danisan_id=? ORDER BY tarih DESC,saat DESC LIMIT 30',(did,))}
    finally:c.close()

def public_portal_html(token):
    data=portal_veri(token)
    if not data:return '<meta charset="utf-8"><p>Bağlantı geçersiz veya süresi dolmuş.</p>'
    esc=html_lib.escape
    return '<meta charset="utf-8"><title>Danışan Portalı</title><h2>'+esc(data['danisan']['ad']+' '+data['danisan']['soyad'])+'</h2><h3>Yaklaşan randevular</h3><ul>'+''.join('<li>'+esc(r['tarih']+' '+r['saat'])+'</li>' for r in data['randevular'])+'</ul>'

def mesaj_hedefleri_listesi(tip='yarin_randevu',terapist_id=None,tarih=None,week_start=None):
    ref=date.fromisoformat(valid_date(tarih or date.today().isoformat()));c=get_db();items=[]
    try:
        if tip in ('odeme_hatirlatma','recall','pilates_uyari'):
            if tip=='odeme_hatirlatma':return {'items':odeme_hatirlatma_hedefleri(3,terapist_id)}
            if tip=='recall':return {'items':recall_hedefleri(21,terapist_id)}
            for p in paketler_listesi():
                if p['aktif'] and p['kalan']>0 and ((date.fromisoformat(p['bitis'])-ref).days<=7 or p['kalan']<=2):
                    d=exists(c,'danisanlar',p['danisan_id'])
                    if terapist_id and not c.execute('SELECT 1 FROM danisan_terapistler WHERE danisan_id=? AND terapist_id=?',(d['id'],terapist_id)).fetchone():continue
                    items.append({**d,'danisan_id':d['id'],'kaynak':'pilates','kaynak_id':p['id'],'danisan_adi':d['ad']+' '+d['soyad'],'kalan_seans':p['kalan'],'bitis_tarihi':p['bitis'],'kalan_gun':max(0,(date.fromisoformat(p['bitis'])-ref).days)})
        else:
            if tip in ('24saat_kala','24saat_whatsapp','yarin_randevu'):start=end=(ref+timedelta(days=1)).isoformat()
            elif tip in ('hafta_randevu','hafta_planli'):mon,sun,_,_=haftalik_meta(week_start or ref.isoformat());start,end=mon.isoformat(),sun.isoformat()
            else:start=end=ref.isoformat()
            rows=q(c,'''SELECT r.*,d.ad,d.soyad,d.telefon,d.email,t.ad terapist_adi,h.alan_adi hizmet_adi,o.ad oda_adi FROM randevular r JOIN danisanlar d ON d.id=r.danisan_id JOIN terapistler t ON t.id=r.terapist_id LEFT JOIN hizmet_alanlari h ON h.id=r.hizmet_id LEFT JOIN odalar o ON o.id=r.oda_id WHERE d.aktif=1 AND r.tarih BETWEEN ? AND ?'''+(' AND r.terapist_id=?' if terapist_id else ''),[start,end]+([terapist_id] if terapist_id else []))
            suppressed={(x['danisan_id'],x['terapist_id'],x['tarih'],x['saat']) for x in rows if x['durum'] in ('iptal','tamamlandi')}
            for x in rows:
                if x['durum'] not in ('iptal','tamamlandi'):items.append({**x,'kaynak':'randevu','kaynak_id':x['id'],'danisan_adi':x['ad']+' '+x['soyad']})
            seen={(x['danisan_id'],x['terapist_id'],x['tarih'],x['saat']) for x in items}|suppressed
            if tip in ('24saat_kala','24saat_whatsapp','yarin_randevu','bugun_planli','hafta_planli'):
                for x in planli_program_tarih_araligi(start,end,terapist_id):
                    key=(x['danisan_id'],x['terapist_id'],x['tarih'],x['saat'])
                    if key in seen:continue
                    if not c.execute('SELECT 1 FROM danisanlar WHERE id=? AND aktif=1',(x['danisan_id'],)).fetchone():continue
                    items.append({**x,'kaynak':'planli','kaynak_id':x['plan_id']});seen.add(key)
        for x in items:
            x['telefon_norm']=_turkiye_tel_normalize(x.get('telefon'));x['klinik']=ayar_al('klinik_adi','Arte Terapi');x['terapist']=x.get('terapist_adi','');x['hizmet']=x.get('hizmet_adi','');x['oda_satiri']=('Oda: '+x['oda_adi']) if x.get('oda_adi') else ''
        return {'tip':tip,'items':items,'count':len(items)}
    finally:c.close()

def odeme_hatirlatma_hedefleri(gun_esik=3,terapist_id=None):
    c=get_db();out=[];cut=(date.today()-timedelta(days=int(gun_esik))).isoformat()
    try:
        for d in danisanlar_listesi(terapist_id):
            if c.execute('SELECT 1 FROM odemeler WHERE danisan_id=? AND seans_id IS NULL AND paket_id IS NULL',(d['id'],)).fetchone():continue
            debt=c.execute('''SELECT COALESCE(SUM(MAX(0,s.ucret-(SELECT COALESCE(SUM(o.tutar),0) FROM odemeler o WHERE o.seans_id=s.id))),0) FROM seanslar s WHERE s.danisan_id=? AND s.paket_id IS NULL AND s.ucret_alindi=0 AND s.tarih<=?''',(d['id'],cut)).fetchone()[0]
            debt+=sum(p['bakiye'] for p in paketler_listesi(d['id']) if p['baslangic']<=cut and not (p['legacy'] and p.get('eski_odendi')))
            if debt>0:out.append({**d,'danisan_id':d['id'],'danisan_adi':d['ad']+' '+d['soyad'],'borc_tutar':f'{debt:.2f} TL','telefon_norm':_turkiye_tel_normalize(d.get('telefon')),'klinik':ayar_al('klinik_adi','Arte Terapi'),'kaynak':'odeme','kaynak_id':d['id']})
        return out
    finally:c.close()

def recall_hedefleri(gun_esik=21,terapist_id=None):
    c=get_db();out=[]
    try:
        for d in danisanlar_listesi(terapist_id):
            r=c.execute('SELECT MAX(tarih) FROM seanslar WHERE danisan_id=? AND gelmedi=0 AND tarih<=?',(d['id'],date.today().isoformat())).fetchone()[0]
            if r and (date.today()-date.fromisoformat(r)).days>=int(gun_esik):out.append({**d,'danisan_id':d['id'],'danisan_adi':d['ad']+' '+d['soyad'],'gecen_gun':(date.today()-date.fromisoformat(r)).days,'kaynak':'recall','kaynak_id':d['id'],'klinik':ayar_al('klinik_adi','Arte Terapi')})
        return out
    finally:c.close()

def _render_message(text,ctx):
    def sub(m):
        k=m.group(1)
        if k not in ctx:raise ValueError('Şablonda bilinmeyen alan: '+k)
        return str(ctx[k] or '')
    return re.sub(r'\{(\w+)\}',sub,str(text or ''))

def otomasyon_calistir():
    count=0;today=date.today().isoformat()
    templates={x['kod']:x for x in mesaj_sablonlari_listesi()}
    for rule in otomasyon_kurallari_listesi():
        if not rule['aktif']:continue
        template=templates.get(rule['sablon_kod'])
        if not template:continue
        for target in _targets_for_rule(rule):
            key='|'.join(str(target.get(k,'')) for k in ('danisan_id','kaynak','kaynak_id','tarih','saat'))
            text=_render_message(template['metin'],target);subject=_render_message(template.get('konu',''),target)
            with transaction() as c:
                if not c.execute('INSERT OR IGNORE INTO automation_runs VALUES(?,?,?)',(rule['id'],key,today)).rowcount:continue
                c.execute('INSERT INTO mesaj_kayitlari(tarih,kanal,hedef_turu,hedef_id,hedef_ad,hedef_iletisim,konu,metin,durum,meta_json) VALUES(?,?,?,?,?,?,?,?,?,?)',(datetime.now().isoformat(timespec='seconds'),rule['kanal'],rule['tur'],target['danisan_id'],target['danisan_adi'],target.get('email') if rule['kanal']=='email' else target.get('telefon',''),subject,text,'hazirlandi',json.dumps(target,ensure_ascii=False)))
                c.execute('UPDATE otomasyon_kurallari SET son_calisma=? WHERE id=?',(today,rule['id']));count+=1
    return {'ok':True,'adet':count}

def _save_record(kind,d):
    tables={
      'terapistler':('terapistler',['ad','soyad','renk','uzmanlik','aktif','notlar']),
      'hizmetler':('hizmet_alanlari',['terapist_id','alan_adi','kategori','seans_ucreti','bireysel_fiyat','grup2_fiyat','grup3_fiyat','paket_mi','paket_seans','paket_hafta','hediye_seans','terapist_prim_orani','takvim_rengi','aktif']),
      'odalar':('odalar',['ad','renk','aktif','notlar','kategori','kapasite','ozellikler']),
      'randevular':('randevular',['danisan_id','terapist_id','hizmet_id','tarih','saat','sure_dk','durum','notlar','oda_id']),
      'kaynaklar':('kaynaklar',['ad','tur','renk','kapasite','bagli_oda_id','aktif','notlar']),
      'rezervasyonlar':('kaynak_rezervasyonlari',['kaynak_id','tarih','saat','sure_dk','baslik','tip','danisan_id','terapist_id']),
      'stok':('stok_kalemleri',['ad','kategori','birim','mevcut_stok','min_stok','birim_maliyet','barkod','aktif','notlar']),
      'notlar':('gelisim_notlari',['danisan_id','terapist_id','tarih','tur','metin']),
      'raporlar':('danisan_raporlar',['danisan_id','terapist_id','tarih','baslik','icerik']),
      'sablonlar':('mesaj_sablonlari',['kod','ad','kanal','konu','metin','aktif']),
      'kurallar':('otomasyon_kurallari',['kod','ad','tur','kanal','sablon_kod','ayar_json','aktif'])}
    if kind not in tables:raise ValueError('İşlem türü geçersiz.')
    table,allowed=tables[kind]
    with transaction() as c:
        old=exists(c,table,d['id']) if d.get('id') else {}
        v={**old,**{k:val for k,val in d.items() if k in allowed}}
        for f in ['ad'] if 'ad' in allowed else []:v[f]=required(v.get(f),'Ad')
        for f in ['tarih'] if 'tarih' in allowed else []:v[f]=valid_date(v.get(f))
        for f,t in [('danisan_id','danisanlar'),('terapist_id','terapistler'),('hizmet_id','hizmet_alanlari'),('oda_id','odalar'),('kaynak_id','kaynaklar'),('bagli_oda_id','odalar')]:
            if f in v:
                if v[f]:exists(c,t,v[f]);v[f]=int(v[f])
                else:v[f]=None
        if kind in ('notlar','raporlar','randevular') and not v.get('danisan_id'):raise ValueError('Danışan seçiniz.')
        if kind=='randevular':
            if not v.get('terapist_id'):raise ValueError('Terapist seçiniz.')
            if v.get('durum','bekliyor') not in ('bekliyor','tamamlandi','iptal'):raise ValueError('Randevu durumu geçersiz.')
        if kind=='rezervasyonlar' and not v.get('kaynak_id'):raise ValueError('Kaynak seçiniz.')
        if 'saat' in allowed:
            v['saat']=valid_time(v.get('saat'));v['sure_dk']=integer(v.get('sure_dk',45),5,480)
            if _saat_dakika(v['saat'])+v['sure_dk']>1440:raise ValueError('Süre gece yarısını aşamaz.')
        if kind=='hizmetler':
            if not v.get('terapist_id'):raise ValueError('Terapist seçiniz.')
            v['alan_adi']=required(v.get('alan_adi'),'Hizmet adı')
            for f in ['seans_ucreti','grup2_fiyat','grup3_fiyat']:v[f]=money(v.get(f))
            v['bireysel_fiyat']=v['seans_ucreti'];v['paket_seans']=integer(v.get('paket_seans',8),1);v['paket_hafta']=integer(v.get('paket_hafta',6),1,520);v['hediye_seans']=integer(v.get('hediye_seans',0))
            v['terapist_prim_orani']=float(v.get('terapist_prim_orani') or 0)
            if not math.isfinite(v['terapist_prim_orani']) or not 0<=v['terapist_prim_orani']<=1:raise ValueError('Prim oranı 0–1 arasında olmalı; %40 için 0.4.')
        if kind=='stok':
            for f in ['mevcut_stok','min_stok','birim_maliyet']:v[f]=money(v.get(f))
            if old and v['mevcut_stok']!=old['mevcut_stok']:raise ValueError('Mevcut stoğu hareket/sayım kaydıyla değiştirin.')
        if 'kapasite' in allowed:v['kapasite']=integer(v.get('kapasite',1),1,1000)
        if 'aktif' in allowed:v['aktif']=flag(v.get('aktif',1))
        if 'paket_mi' in allowed:v['paket_mi']=flag(v.get('paket_mi',0))
        if kind in ('sablonlar','kurallar') and not old:v.setdefault('kod',secrets.token_hex(10))
        if kind in ('sablonlar','kurallar'):
            if v.get('kanal','whatsapp') not in ('whatsapp','email'):raise ValueError('Kanal geçersiz.')
        if kind=='kurallar':
            cfg=v.get('ayar_json','{}')
            try:parsed=json.loads(cfg) if isinstance(cfg,str) else cfg
            except Exception:raise ValueError('Kural ayarı geçerli JSON olmalı.')
            if not isinstance(parsed,dict):raise ValueError('Kural ayarı nesne olmalı.')
            v['ayar_json']=json.dumps(parsed,ensure_ascii=False)
        for f in ['metin','baslik']:
            if f in allowed:v[f]=required(v.get(f),f)
        fields=[f for f in allowed if f in v]
        if old:
            c.execute('UPDATE '+table+' SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',[v[f] for f in fields]+[old['id']]);return old['id']
        return c.execute('INSERT INTO '+table+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',[v[f] for f in fields]).lastrowid

def _delete_record(kind,ident):
    funcs={'danisanlar':danisan_sil,'seanslar':seans_sil,'odemeler':odeme_sil,'giderler':gider_sil,'kasa':kasa_sil,'pdf':rapor_pdf_sil}
    if kind in funcs:return funcs[kind](ident)
    tables={'planlar':'haftalik_program_sablonlari','randevular':'randevular','notlar':'gelisim_notlari','raporlar':'danisan_raporlar','rezervasyonlar':'kaynak_rezervasyonlari','paketler':'pilates_paketleri','sablonlar':'mesaj_sablonlari','kurallar':'otomasyon_kurallari','portal':'portal_erisimleri','kaynaklar':'kaynaklar'}
    table=tables.get(kind)
    if not table:raise ValueError('Silme işlemi desteklenmiyor.')
    with transaction() as c:
        exists(c,table,ident)
        if kind in ('paketler','sablonlar','kurallar','portal','kaynaklar'):c.execute('UPDATE '+table+' SET aktif=0 WHERE id=?',(ident,))
        else:c.execute('DELETE FROM '+table+' WHERE id=?',(ident,))

def odeme_bagla(d):
    with transaction() as c:
        o=exists(c,'odemeler',d.get('id'),'Ödeme')
        if o['seans_id'] or o['paket_id']:raise ValueError('Ödeme zaten bağlı.')
        sid=d.get('seans_id') or None;pid=d.get('paket_id') or None
        if bool(sid)==bool(pid):raise ValueError('Bir seans veya paket seçiniz.')
        r=exists(c,'seanslar' if sid else 'pilates_paketleri',sid or pid)
        if r['danisan_id']!=o['danisan_id']:raise ValueError('Danışan eşleşmiyor.')
        if sid and r.get('paket_id'):raise ValueError('Ödemeyi seansın paketine bağlayınız.')
        field='seans_id' if sid else 'paket_id';paid=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE '+field+'=?',(sid or pid,)).fetchone()[0]
        if paid+o['tutar']>(r['ucret'] if sid else r['fiyat'])+.005:raise ValueError('Bu ödeme kalan bakiyeyi aşıyor; gerekirse ödeme kaydını bölerek yeniden girin.')
        c.execute('UPDATE odemeler SET seans_id=?,paket_id=?,terapist_id=? WHERE id=?',(sid,pid,r['terapist_id'] if sid else None,o['id']))
        if sid:_sync_paid(c,sid)

# All active mutations use the validated implementations.
def hizmet_ekle(d):return _save_record('hizmetler',d)
def hizmet_guncelle(d):return _save_record('hizmetler',d)
def terapist_ekle(d):return _save_record('terapistler',d)
def terapist_guncelle(d):return _save_record('terapistler',d)
def oda_kaydet(d):return _save_record('odalar',d)
def randevu_ekle(d):return _save_record('randevular',d)
def randevu_guncelle(d):return _save_record('randevular',d)
def stok_kalem_kaydet(d):return _save_record('stok',d)
def kaynak_kaydet(d):return _save_record('kaynaklar',d)
def kaynak_rezervasyon_kaydet(d):return _save_record('rezervasyonlar',d)
def gelisim_not_ekle(d):return _save_record('notlar',d)
def rapor_ekle(d):return _save_record('raporlar',d)
def mesaj_sablon_kaydet(d):return _save_record('sablonlar',d)
def otomasyon_kural_kaydet(d):return _save_record('kurallar',d)

def _list_kind(kind,qs):
    funcs={'danisanlar':lambda:danisanlar_listesi(qs.get('terapist_id'),qs.get('arama','')),'terapistler':lambda:terapistler_listesi(True),'hizmetler':lambda:hizmetler_listesi(include_inactive=True),'odalar':odalar_listesi,'paketler':lambda:paketler_listesi(qs.get('danisan_id')),'seanslar':lambda:tum_seanslar(qs.get('ay'),qs.get('terapist_id')),'odemeler':lambda:odemeler_listesi(qs.get('ay'),qs.get('terapist_id'),qs.get('danisan_id')),'giderler':lambda:giderler_listesi(qs.get('ay')),'kasa':lambda:kasa_listesi(qs.get('ay')),'planlar':lambda:haftalik_program_sablonlari_listesi(qs.get('terapist_id')),'randevular':lambda:randevular_listesi(None,qs.get('ay'),qs.get('terapist_id')),'stok':stok_kalemleri_listesi,'kaynaklar':kaynaklar_listesi,'sablonlar':mesaj_sablonlari_listesi,'kurallar':otomasyon_kurallari_listesi,'mesajlog':mesaj_loglari_listesi,'portal':portal_linkleri_listesi}
    if kind=='rezervasyonlar':
        c=get_db()
        try:return q(c,'SELECT r.*,k.ad kaynak_adi FROM kaynak_rezervasyonlari r JOIN kaynaklar k ON k.id=r.kaynak_id ORDER BY tarih DESC,saat')
        finally:c.close()
    if kind not in funcs:raise ValueError('Liste türü geçersiz.')
    return funcs[kind]()

def _save_kind(kind,d):
    funcs={'danisanlar':lambda:danisan_guncelle(d) if d.get('id') else danisan_ekle(d),'seanslar':lambda:seans_kaydet(d),'paketler':lambda:paket_kaydet(d),'odemeler':lambda:odeme_ekle(d),'giderler':lambda:gider_ekle(d),'kasa':lambda:kasa_ekle(d),'planlar':lambda:haftalik_program_kaydet(d),'stokhareket':lambda:stok_hareket_ekle(d),'pdf':lambda:rapor_pdf_kaydet(d),'eslestir':lambda:kasa_eslestir(d),'odemebagla':lambda:odeme_bagla(d)}
    if kind in ('seanslar','randevular','planlar','rezervasyonlar'):
        conflicts=schedule_conflicts(kind,d)
        if conflicts['has_conflict'] and not flag(d.get('conflict_override')):raise ValueError('Zaman/oda/kaynak çakışması var. Formdan inceleyip onaylayın.')
    return funcs[kind]() if kind in funcs else _save_record(kind,d)

def _password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),240000).hex()

_LOGIN_LIMIT={};_SESS_LOCK=threading.RLock()

class Handler(BaseHTTPRequestHandler):
    server_version='ArteTerapi/3.11'
    def setup(self):
        super().setup();self.connection.settimeout(20)
    def log_message(self,*args):pass
    def _send(self,body,status=200,ctype='application/json; charset=utf-8',headers=None):
        if not isinstance(body,bytes):body=(json.dumps(body,ensure_ascii=False,allow_nan=False,default=str) if ctype.startswith('application/json') else str(body)).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def _auth(self):
        try:cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));token=cookie['arte_session'].value
        except Exception:return None
        c=get_db()
        try:
            row=c.execute('SELECT * FROM auth_sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None
        finally:c.close()
    def do_OPTIONS(self):self._send({'error':'Çapraz site erişimi kapalı.'},403)
    def do_GET(self):
        p=urllib.parse.urlparse(self.path);qs=dict(urllib.parse.parse_qsl(p.query));path=p.path
        try:
            if path=='/':return self._send(build_html(),ctype='text/html; charset=utf-8')
            if path=='/api/session':
                auth=self._auth();return self._send({'authenticated':bool(auth),'csrf':auth['csrf'] if auth else '', 'setup':not bool(ayar_al('admin_password_hash')),'setup_allowed':self.client_address[0] in ('127.0.0.1','::1'),'version':APP_VERSION})
            if path=='/portal':return self._send(public_portal_html(qs.get('token','')),ctype='text/html; charset=utf-8')
            if path=='/rezervasyon':return self._send(public_booking_html(),ctype='text/html; charset=utf-8')
            if path=='/portal-pdf':
                scope=portal_scope(qs.get('token',''))
                if not scope or not scope.get('paylas_rapor'):return self._send({'error':'Bağlantı geçersiz.'},403)
                c=get_db()
                try:r=exists(c,'danisan_rapor_dosyalari',qs.get('id'),'PDF')
                finally:c.close()
                if r['danisan_id']!=scope['danisan_id'] or r['tarih']>(scope.get('dokum_bitis') or date.today().isoformat()):return self._send({'error':'Bu ek paylaşım kapsamında değil.'},403)
                blob=read_report_blob(r)
                if blob is None:return self._send({'error':'PDF bulunamadı.'},404)
                return self._send(blob,ctype='application/pdf',headers={'Content-Disposition':"inline; filename=rapor.pdf; filename*=UTF-8''"+urllib.parse.quote(_safe_pdf_name(r['dosya_adi']),safe='')})
            if not self._auth():return self._send({'error':'Oturum açınız.'},401)
            if path in ('/danisan-dokumu','/api/statement'):
                d=client_statement(integer(qs.get('id'),1),qs.get('start'),qs.get('end'),qs.get('future_end'),flag(qs.get('reports')),flag(qs.get('measurements')))
                return self._send(statement_html(d),ctype='text/html; charset=utf-8') if path=='/danisan-dokumu' else self._send(d)
            if path=='/api/mobile':return self._send(mobile_connection_info(self.server))
            if path=='/api/bootstrap':return self._send({'terapistler':terapistler_listesi(True),'hizmetler':hizmetler_listesi(include_inactive=True),'odalar':odalar_listesi(),'danisanlar':danisanlar_listesi(),'paketler':paketler_listesi(),'klinik':ayar_al('klinik_adi','Arte Terapi'),'version':APP_VERSION})
            if path=='/api/list':return self._send(_list_kind(qs.get('kind'),qs))
            if path=='/api/client':
                d=danisan_detay(qs.get('id'));return self._send(d if d else {'error':'Danışan bulunamadı.'},200 if d else 404)
            if path=='/api/report':return self._send(gelir_raporu(qs.get('start'),qs.get('end'),qs.get('terapist_id')))
            if path=='/api/week':return self._send(seans_haftalik_programi(qs.get('start'),qs.get('terapist_id')))
            if path=='/api/targets':return self._send(mesaj_hedefleri_listesi(qs.get('tip','24saat_kala'),qs.get('terapist_id'),qs.get('tarih'),qs.get('week_start')))
            if path=='/api/backup':return self._send(backup_bytes(),ctype='application/zip',headers={'Content-Disposition':'attachment; filename="ArteTerapi_yedek.zip"'})
            if path=='/rapor_pdf':
                c=get_db()
                try:r=exists(c,'danisan_rapor_dosyalari',qs.get('id'),'PDF')
                finally:c.close()
                blob=read_report_blob(r)
                if blob is None:return self._send({'error':'PDF bulunamadı.'},404)
                disposition="inline; filename=\"rapor.pdf\"; filename*=UTF-8''"+urllib.parse.quote(_safe_pdf_name(r['dosya_adi']),safe='')
                return self._send(blob,ctype='application/pdf',headers={'Content-Disposition':disposition})
            self._send({'error':'Yol bulunamadı.'},404)
        except ValueError as e:self._send({'error':str(e)},400)
        except Exception as e:
            print('GET error:',type(e).__name__,str(e),file=sys.stderr);self._send({'error':'İşlem tamamlanamadı. Veritabanı ve dosya erişimini kontrol edin.'},500)
    def do_POST(self):
        try:
            path=urllib.parse.urlparse(self.path).path
            origin=self.headers.get('Origin','');host=self.headers.get('Host','')
            if self.headers.get('Sec-Fetch-Site')=='cross-site' or (origin and urllib.parse.urlparse(origin).netloc!=host):return self._send({'error':'İstek kaynağı geçersiz.'},403)
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=15*1024*1024:return self._send({'error':'İstek boyutu geçersiz (en çok 15 MB).'},413)
            if not self.headers.get('Content-Type','').lower().startswith('application/json'):return self._send({'error':'JSON içerik gerekli.'},415)
            try:d=json.loads(self.rfile.read(length).decode('utf-8'))
            except Exception:return self._send({'error':'Geçersiz JSON.'},400)
            if not isinstance(d,dict):raise ValueError('İstek nesne olmalıdır.')
            if path in ('/api/login','/api/setup'):
                ip=self.client_address[0];now=time.time()
                with _SESS_LOCK:
                    recent=[t for t in _LOGIN_LIMIT.get(ip,[]) if now-t<300];_LOGIN_LIMIT[ip]=recent
                    if len(recent)>=10:return self._send({'error':'Çok fazla deneme. 5 dakika sonra tekrar deneyin.'},429)
                    password=required(d.get('password'),'Parola');stored=ayar_al('admin_password_hash')
                    if path=='/api/setup':
                        if stored:return self._send({'error':'İlk kurulum zaten tamamlandı.'},409)
                        if ip not in ('127.0.0.1','::1'):return self._send({'error':'İlk parolayı uygulamanın çalıştığı bilgisayardan belirleyin.'},403)
                        if len(password)<8:raise ValueError('Parola en az 8 karakter olmalı.')
                        stored=_password_hash(password);ayar_kaydet('admin_password_hash',stored)
                    elif not stored or not hmac.compare_digest(_password_hash(password,stored.split(':')[0]),stored):
                        recent.append(now);return self._send({'error':'Parola hatalı.'},401)
                    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
                    with transaction() as c:
                        c.execute('DELETE FROM auth_sessions WHERE expires<?',(now,))
                        c.execute('INSERT INTO auth_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,now+12*3600))
                    return self._send({'ok':True,'csrf':csrf},headers={'Set-Cookie':'arte_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
            if path=='/api/public/booking':
                ip='booking:'+self.client_address[0];now=time.time()
                with _SESS_LOCK:
                    recent=[t for t in _LOGIN_LIMIT.get(ip,[]) if now-t<3600]
                    if len(recent)>=10:return self._send({'error':'Talep sınırına ulaşıldı.'},429)
                    recent.append(now);_LOGIN_LIMIT[ip]=recent
                d['ad']=required(d.get('ad'),'Ad');d['telefon']=required(d.get('telefon'),'Telefon');d['durum']='yeni'
                if d.get('tercih_tarih'):valid_date(d['tercih_tarih'])
                if d.get('tercih_saat'):valid_time(d['tercih_saat'])
                return self._send({'ok':True,'id':online_talep_ekle(d)})
            auth=self._auth()
            if not auth:return self._send({'error':'Oturum açınız.'},401)
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),auth['csrf']):return self._send({'error':'Güvenlik anahtarı geçersiz. Sayfayı yenileyin.'},403)
            if path=='/api/logout':
                with transaction() as c:c.execute('DELETE FROM auth_sessions WHERE token_hash=?',(auth['token_hash'],))
                return self._send({'ok':True},headers={'Set-Cookie':'arte_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/'})
            if path=='/api/save':return self._send({'ok':True,'id':_save_kind(d.get('kind'),d.get('data') or {})})
            if path=='/api/delete':_delete_record(d.get('kind'),str(d.get('id') or '') if d.get('kind')=='programlar' else integer(d.get('id'),1));return self._send({'ok':True})
            if path=='/api/conflict':return self._send(schedule_conflicts(d.get('kind','planlar'),d.get('data',d)))
            if path=='/api/automation':return self._send(otomasyon_calistir())
            if path=='/api/portal-token':return self._send({'ok':True,'token':portal_token_olustur(integer(d.get('danisan_id'),1),integer(d.get('gun',180),1,365))})
            if path=='/api/booking-status':online_talep_guncelle(d);return self._send({'ok':True})
            if path=='/api/settings':
                if 'klinik_adi' in d:ayar_kaydet('klinik_adi',required(d['klinik_adi'],'Klinik adı'))
                if d.get('new_password'):
                    stored=ayar_al('admin_password_hash')
                    if not hmac.compare_digest(_password_hash(str(d.get('old_password','')),stored.split(':')[0]),stored):raise ValueError('Mevcut parola hatalı.')
                    if len(d['new_password'])<8:raise ValueError('Yeni parola en az 8 karakter olmalı.')
                    ayar_kaydet('admin_password_hash',_password_hash(d['new_password']))
                    with transaction() as c:c.execute('DELETE FROM auth_sessions WHERE token_hash<>?',(auth['token_hash'],))
                return self._send({'ok':True})
            self._send({'error':'Yol bulunamadı.'},404)
        except (ValueError,KeyError,TypeError,sqlite3.IntegrityError) as e:self._send({'error':str(e)},400)
        except Exception as e:
            print('POST error:',type(e).__name__,str(e),file=sys.stderr);self._send({'error':'İşlem tamamlanamadı. Kaydı yenileyip tekrar deneyin.'},500)


def _run_app():
    init_db()
    bind=os.getenv('ARTE_BIND','127.0.0.1');port=int(os.getenv('ARTE_PORT',str(PORT)))
    server=ArteServer((bind,port),Handler)
    print(f'Arte Terapi v{APP_VERSION} — http://127.0.0.1:{port}')
    print('İlk açılışta tarayıcıdan yönetici parolanızı belirleyin. Veriler: '+DB_PATH)
    if bind!='127.0.0.1':print('Ağ erişimi açık. Yalnız güvenilir ağda kullanın; internet erişimi için HTTPS gereklidir.')
    threading.Timer(1,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

def schedule_conflicts(kind,d):
    if kind not in ('seanslar','randevular','planlar','rezervasyonlar'):return {'has_conflict':False,'items':[]}
    c=get_db();out=[]
    try:
        tables={'seanslar':'seanslar','randevular':'randevular','planlar':'haftalik_program_sablonlari','rezervasyonlar':'kaynak_rezervasyonlari'}
        if d.get('id'):d={**exists(c,tables[kind],d['id']),**d}
        start=valid_time(d.get('saat'));duration=integer(d.get('sure_dk',45),5,480)
        if kind=='planlar':weekday=integer(d.get('gun_index'),0,6);dt=None
        else:dt=valid_date(d.get('tarih'));weekday=date.fromisoformat(dt).weekday()
        if kind=='seanslar' and flag(d.get('gelmedi')):return {'has_conflict':False,'items':[]}
        def equal(a,b):return a not in (None,'') and str(a)==str(b)
        candidates=[]
        for category,table in tables.items():
            if category=='planlar':rows=q(c,'SELECT * FROM '+table+' WHERE aktif=1 AND gun_index=?',(weekday,))
            elif kind=='planlar':rows=q(c,"SELECT * FROM "+table+" WHERE tarih>=? AND ((CAST(strftime('%w',tarih) AS INTEGER)+6)%7)=?",(date.today().isoformat(),weekday))
            else:rows=q(c,'SELECT * FROM '+table+' WHERE tarih=?',(dt,))
            for r in rows:
                if category==kind and equal(r['id'],d.get('id')):continue
                if category=='planlar' and d.get('program_id') and r.get('program_id')==d['program_id']:continue
                astart=d.get('baslangic') or (dt if kind!='planlar' else '0001-01-01');aend=d.get('bitis') or (dt if kind!='planlar' else '9999-12-31')
                bstart=r.get('baslangic') or (r.get('tarih') if category!='planlar' else '0001-01-01');bend=r.get('bitis') or (r.get('tarih') if category!='planlar' else '9999-12-31')
                if aend<bstart or bend<astart:continue
                if r.get('durum')=='iptal' or r.get('gelmedi'):continue
                if not _aralik_cakisiyor(start,duration,r.get('saat'),r.get('sure_dk')):continue
                sameclient=equal(d.get('danisan_id'),r.get('danisan_id'));sametherapist=equal(d.get('terapist_id'),r.get('terapist_id'));sameroom=equal(d.get('oda_id'),r.get('oda_id'));sameres=equal(d.get('kaynak_id'),r.get('kaynak_id'))
                if category!=kind and sameclient and sametherapist and start==r.get('saat') and equal(d.get('hizmet_id'),r.get('hizmet_id')):continue # planned/actual occurrence of the same session
                if kind=='rezervasyonlar' and d.get('kaynak_id'):
                    resource=exists(c,'kaynaklar',d['kaynak_id']);sameroom=sameroom or equal(resource.get('bagli_oda_id'),r.get('oda_id'))
                if category=='rezervasyonlar' and r.get('kaynak_id'):
                    resource=exists(c,'kaynaklar',r['kaynak_id']);sameroom=sameroom or equal(resource.get('bagli_oda_id'),d.get('oda_id'))
                if sameclient or sametherapist or sameroom or sameres:candidates.append((category,r,sameclient,sametherapist,sameroom,sameres))
        # Group concurrency is intentional only in the same slot; capacity remains visible as a warning.
        group=d.get('grup_turu','bireysel');capacity=int(group[-1]) if group in ('grup2','grup3') else 1
        if d.get('paket_id'):
            p=exists(c,'pilates_paketleri',d['paket_id']);group=p['grup_turu'];capacity=int(group[-1]) if group in ('grup2','grup3') else 1
        for category,r,client,therapist,room,res in candidates:
            isgroup=capacity>1 and group==r.get('grup_turu','bireysel') and not client and not res and start==r.get('saat') and sameduration(duration,r.get('sure_dk')) and therapist and room
            if isgroup:
                same_people={str(x[1].get('danisan_id')) for x in candidates if x[1].get('saat')==start and x[3] and x[4]}
                roomcap=exists(c,'odalar',d['oda_id'])['kapasite'] if d.get('oda_id') else capacity
                if len(same_people)+1<=min(capacity,roomcap or 1):continue
            labels=[label for yes,label in [(client,'Danışan'),(therapist,'Terapist'),(room,'Oda'),(res,'Kaynak')] if yes]
            out.append({'id':r['id'],'kaynak':category,'aciklama':', '.join(labels)+' '+str(r.get('tarih') or 'haftalık')+' '+str(r.get('saat'))})
        return {'has_conflict':bool(out),'items':out}
    finally:c.close()

def sameduration(a,b):return int(a or 45)==int(b or 45)

def public_booking_html():
    clinic=html_lib.escape(ayar_al('klinik_adi','Arte Terapi'))
    return '<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Randevu Talebi</title><style>body{max-width:650px;margin:30px auto;padding:20px;font-family:system-ui}label{display:block;margin:14px 0}input,textarea,button{display:block;width:100%;padding:10px;box-sizing:border-box}p{line-height:1.6}</style><h1>'+clinic+'</h1><p>Bu form randevu talebi oluşturur. Klinik onayı olmadan randevu kesinleşmez.</p><form id="booking"><label>Ad<input name="ad" required></label><label>Soyad<input name="soyad"></label><label>Telefon<input name="telefon" required></label><label>E-posta<input name="email" type="email"></label><label>Hizmet<input name="hizmet_adi"></label><label>Tercih edilen tarih<input type="date" name="tercih_tarih"></label><label>Saat<input type="time" name="tercih_saat"></label><label>Not<textarea name="notlar"></textarea></label><button>Talep gönder</button></form><p id="result" role="status"></p><script>document.getElementById("booking").addEventListener("submit",async e=>{e.preventDefault();const b=e.target.querySelector("button");b.disabled=true;try{const r=await fetch("/api/public/booking",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});const d=await r.json();if(!r.ok)throw Error(d.error);document.getElementById("result").textContent="Talebiniz alındı.";e.target.reset()}catch(x){document.getElementById("result").textContent=x.message}finally{b.disabled=false}});</script></html>'


# v3.10: member workspace, per-person package catalogue and reusable weekly programs.
APP_VERSION = '3.10.0'
_INIT_390 = init_db

def init_db():
    _INIT_390()
    with _INIT_LOCK:
        check=get_db()
        try:done=check.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_3100'").fetchone()
        finally:check.close()
        if done:return
        folder=os.path.join(os.path.dirname(DB_PATH),'yedekler');os.makedirs(folder,exist_ok=True)
        with open(os.path.join(folder,'v3100_oncesi_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'wb') as f:f.write(backup_bytes())
        with transaction() as c:
            if c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_3100'").fetchone():return
            c.execute('CREATE TABLE IF NOT EXISTS pilates_uyeleri(danisan_id INTEGER PRIMARY KEY REFERENCES danisanlar(id), kayit_tarihi TEXT NOT NULL)')
            c.execute('''CREATE TABLE IF NOT EXISTS pilates_tarifeleri(id INTEGER PRIMARY KEY AUTOINCREMENT,
              ad TEXT NOT NULL, seans_sayisi INTEGER NOT NULL, hediye_seans INTEGER NOT NULL DEFAULT 0,
              hafta INTEGER NOT NULL, bireysel REAL NOT NULL, grup2 REAL NOT NULL, grup3 REAL NOT NULL, aktif INTEGER NOT NULL DEFAULT 1)''')
            cols={r['name'] for r in c.execute('PRAGMA table_info(haftalik_program_sablonlari)')}
            for col,typ in [('program_id','TEXT'),('paket_id','INTEGER'),('baslangic',"TEXT DEFAULT ''"),('bitis',"TEXT DEFAULT ''")]:
                if col not in cols:c.execute('ALTER TABLE haftalik_program_sablonlari ADD COLUMN '+col+' '+typ)
            c.execute("INSERT OR IGNORE INTO pilates_uyeleri SELECT DISTINCT danisan_id,? FROM pilates_paketleri",(date.today().isoformat(),))
            c.execute("INSERT OR IGNORE INTO pilates_uyeleri SELECT DISTINCT s.danisan_id,? FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE h.kategori='pilates'",(date.today().isoformat(),))
            c.execute("INSERT INTO pilates_tarifeleri(ad,seans_sayisi,hediye_seans,hafta,bireysel,grup2,grup3) SELECT DISTINCT alan_adi,MAX(1,COALESCE(paket_seans,8)),COALESCE(hediye_seans,0),MAX(1,COALESCE(paket_hafta,6)),COALESCE(seans_ucreti,0),COALESCE(grup2_fiyat,0),COALESCE(grup3_fiyat,0) FROM hizmet_alanlari WHERE kategori='pilates' AND paket_mi=1 AND aktif=1")
            c.execute("INSERT INTO ayarlar(anahtar,deger) VALUES('schema_3100','1')")

def pilates_tarife_kaydet(d):
    with transaction() as c:
        old=exists(c,'pilates_tarifeleri',d['id']) if d.get('id') else {};v={**old,**d}
        values=(required(v.get('ad'),'Tarife adı'),integer(v.get('seans_sayisi'),1,1000),integer(v.get('hediye_seans',0),0,1000),integer(v.get('hafta'),1,520),money(v.get('bireysel')),money(v.get('grup2')),money(v.get('grup3')),flag(v.get('aktif',1)))
        if old:
            c.execute('UPDATE pilates_tarifeleri SET ad=?,seans_sayisi=?,hediye_seans=?,hafta=?,bireysel=?,grup2=?,grup3=?,aktif=? WHERE id=?',values+(old['id'],));return old['id']
        return c.execute('INSERT INTO pilates_tarifeleri(ad,seans_sayisi,hediye_seans,hafta,bireysel,grup2,grup3,aktif) VALUES(?,?,?,?,?,?,?,?)',values).lastrowid

def pilates_uye_kaydet(d):
    with transaction() as c:
        did=integer(d.get('danisan_id'),1)
        if not exists(c,'danisanlar',did)['aktif']:raise ValueError('Önce danışanı aktif hale getirin.')
        c.execute('INSERT OR IGNORE INTO pilates_uyeleri VALUES(?,?)',(did,date.today().isoformat()));return did

def pilates_veri():
    c=get_db()
    try:
        members=q(c,"SELECT d.*,u.kayit_tarihi FROM danisanlar d JOIN pilates_uyeleri u ON u.danisan_id=d.id WHERE d.aktif=1 ORDER BY d.ad,d.soyad")
        # Package owners are automatically members, including packages created through the general screen.
        allclients={r['id']:r for r in danisanlar_listesi()};seen={r['id'] for r in members}
        packages=paketler_listesi()
        for p in packages:
            if p['danisan_id'] in allclients and p['danisan_id'] not in seen:
                members.append(allclients[p['danisan_id']]);seen.add(p['danisan_id'])
        return {'uyeler':members,'paketler':packages,'tarifeler':q(c,'SELECT * FROM pilates_tarifeleri ORDER BY aktif DESC,seans_sayisi,id'),'planlar':haftalik_program_sablonlari_listesi()}
    finally:c.close()

def program_kaydet(d):
    slots=d.get('slots')
    if not isinstance(slots,list) or not 1<=len(slots)<=21:raise ValueError('1–21 gün/saat seçin.')
    did=integer(d.get('danisan_id'),1);tid=integer(d.get('terapist_id'),1);hid=integer(d.get('hizmet_id'),1)
    duration=integer(d.get('sure_dk',45),5,480);start=valid_date(d.get('baslangic'));end=valid_date(d.get('bitis'))
    if end<start:raise ValueError('Bitiş başlangıçtan önce olamaz.')
    pid=integer(d['paket_id'],1) if d.get('paket_id') else None
    source_id=integer(d['source_plan_id'],1) if d.get('source_plan_id') else None
    program=str(d.get('program_id') or secrets.token_hex(16));room=integer(d['oda_id'],1) if d.get('oda_id') else None
    with _WRITE_LOCK:
        c=get_db()
        try:
            for table,ident in [('danisanlar',did),('terapistler',tid),('hizmet_alanlari',hid)]:
                if not exists(c,table,ident)['aktif']:raise ValueError('Üye, terapist ve hizmet aktif olmalıdır.')
            h=exists(c,'hizmet_alanlari',hid)
            if not service_allows(c,h['id'],tid):raise ValueError('Seçilen terapist bu hizmete atanmamış.')
            group=d.get('grup_turu','bireysel')
            if group not in ('bireysel','grup2','grup3'):raise ValueError('Grup seçimi geçersiz.')
            if h['kategori']=='pilates' and not pid:raise ValueError('Pilates programı için üyenin paketini seçin.')
            if pid:
                p=exists(c,'pilates_paketleri',pid)
                if h['kategori']!='pilates' or p['danisan_id']!=did or not p['aktif']:raise ValueError('Aktif üye paketi ve Pilates hizmeti seçin.')
                if start<p['baslangic'] or end>p['bitis']:raise ValueError('Program tarihleri paket geçerliliği içinde olmalı.')
                group=p['grup_turu']
            if room and not exists(c,'odalar',room)['aktif']:raise ValueError('Oda pasif.')
            if source_id:
                source=exists(c,'haftalik_program_sablonlari',source_id)
                if source['danisan_id']!=did or source.get('program_id'):raise ValueError('Kaynak program değişti; ekranı yenileyin.')
            prior=q(c,'SELECT * FROM haftalik_program_sablonlari WHERE program_id=?',(program,))
            if d.get('program_id') and not prior:raise ValueError('Program bulunamadı; ekranı yenileyin.')
            if prior and any(r['danisan_id']!=did for r in prior):raise ValueError('Program başka üyeye taşınamaz.')
        finally:c.close()
        cleaned=[];warnings=[]
        for slot in slots:
            day=integer(slot.get('gun_index'),0,6);time=valid_time(slot.get('saat'))
            if _saat_dakika(time)+duration>1440:raise ValueError('Seans gece yarısını aşamaz.')
            if any(s['gun_index']==day and _aralik_cakisiyor(time,duration,s['saat'],duration) for s in cleaned):raise ValueError('Seçtiğiniz gün/saatler birbirleriyle çakışıyor.')
            candidate=dict(d,gun_index=day,saat=time,grup_turu=group,program_id=program);candidate.pop('id',None)
            if source_id:candidate['id']=source_id
            warnings.extend(schedule_conflicts('planlar',candidate)['items']);cleaned.append({'gun_index':day,'saat':time})
        if warnings and not flag(d.get('conflict_override')):return {'saved':False,'conflicts':warnings}
        with transaction() as c:
            c.execute('DELETE FROM haftalik_program_sablonlari WHERE program_id=?',(program,))
            if source_id:c.execute('DELETE FROM haftalik_program_sablonlari WHERE id=?',(source_id,))
            for s in cleaned:
                c.execute('''INSERT INTO haftalik_program_sablonlari(danisan_id,terapist_id,hizmet_id,gun_index,saat,sure_dk,oda_id,aktif,notlar,grup_turu,program_id,paket_id,baslangic,bitis) VALUES(?,?,?,?,?,?,?,1,?,?,?,?,?,?)''',(did,tid,hid,s['gun_index'],s['saat'],duration,room,str(d.get('notlar') or ''),group,program,pid,start,end))
            c.execute("INSERT OR IGNORE INTO danisan_terapistler VALUES(?,?,'ek')",(did,tid))
            if pid:c.execute('INSERT OR IGNORE INTO pilates_uyeleri VALUES(?,?)',(did,date.today().isoformat()))
        return {'saved':True,'program_id':program,'slots':len(cleaned)}

_LIST_390=_list_kind
_SAVE_390=_save_kind
_DELETE_390=_delete_record

def _list_kind(kind,qs):
    if kind=='pilates':return pilates_veri()
    if kind=='tarifeler':return pilates_veri()['tarifeler']
    return _LIST_390(kind,qs)

def _save_kind(kind,d):
    if kind=='programlar':return program_kaydet(d)
    if kind=='tarifeler':return pilates_tarife_kaydet(d)
    if kind=='pilatesuye':return pilates_uye_kaydet(d)
    return _SAVE_390(kind,d)

def _delete_record(kind,ident):
    if kind=='programlar':
        with transaction() as c:c.execute('UPDATE haftalik_program_sablonlari SET aktif=0 WHERE program_id=?',(str(ident),))
        return True
    return _DELETE_390(kind,ident)


# v3.11: atomic registration, scoped client statements, measurement milestones.
APP_VERSION='3.11.0'
MEASURE_FIELDS=[('boy','Boy (cm)'),('kilo','Kilo (kg)'),('omuz','Omuz'),('gogus','Göğüs'),('bel','Bel'),('karin','Karın'),('kalca','Kalça'),('basen','Basen'),('sag_kol','Sağ Kol'),('sol_kol','Sol Kol'),('sag_ust_bacak','Sağ Üst Bacak'),('sol_ust_bacak','Sol Üst Bacak'),('sag_diz_ustu','Sağ Diz Üstü'),('sol_diz_ustu','Sol Diz Üstü'),('sag_baldir','Sağ Baldır'),('sol_baldir','Sol Baldır')]
_INIT_310=init_db

def init_db():
    _INIT_310()
    with _INIT_LOCK:
        c=get_db()
        try:done=c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_3110'").fetchone()
        finally:c.close()
        if done:return
        folder=os.path.join(os.path.dirname(DB_PATH),'yedekler');os.makedirs(folder,exist_ok=True)
        with open(os.path.join(folder,'v3110_oncesi_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'wb') as f:f.write(backup_bytes())
        with transaction() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS vucut_olcumleri(id INTEGER PRIMARY KEY AUTOINCREMENT,
              danisan_id INTEGER NOT NULL REFERENCES danisanlar(id), tarih TEXT NOT NULL, asama INTEGER NOT NULL,
              gerceklesen INTEGER NOT NULL, hedef TEXT DEFAULT '', notlar TEXT DEFAULT '', '''+
              ','.join(k+' REAL' for k,_ in MEASURE_FIELDS)+', UNIQUE(danisan_id,asama))')
            sessioncols={r['name'] for r in c.execute('PRAGMA table_info(seanslar)')}
            for col in ['program_id','planlanan_saat','plan_tarihi']:
                if col not in sessioncols:c.execute('ALTER TABLE seanslar ADD COLUMN '+col+" TEXT DEFAULT ''")
            c.execute('CREATE TABLE IF NOT EXISTS kayit_islemleri(istek_id TEXT PRIMARY KEY, sonuc TEXT NOT NULL)')
            cols={r['name'] for r in c.execute('PRAGMA table_info(portal_erisimleri)')}
            for col,typ in [('dokum_baslangic',"TEXT DEFAULT ''"),('dokum_bitis',"TEXT DEFAULT ''"),('gelecek_bitis',"TEXT DEFAULT ''"),('paylas_rapor','INTEGER DEFAULT 0'),('paylas_olcum','INTEGER DEFAULT 0')]:
                if col not in cols:c.execute('ALTER TABLE portal_erisimleri ADD COLUMN '+col+' '+typ)
            c.execute("INSERT INTO ayarlar(anahtar,deger) VALUES('schema_3110','1')")

_DB_310=get_db
_TX_310=transaction
_ATOMIC=threading.local()
class _BorrowedConnection:
    def __init__(self,c):self.c=c
    def __getattr__(self,n):return getattr(self.c,n)
    def close(self):pass
    def commit(self):pass
    def rollback(self):pass

def get_db():
    c=getattr(_ATOMIC,'connection',None)
    return _BorrowedConnection(c) if c is not None else _DB_310()

@contextmanager
def transaction():
    c=getattr(_ATOMIC,'connection',None)
    if c is not None:
        yield c
    else:
        with _TX_310() as conn:yield conn

@contextmanager
def atomic_registration():
    if getattr(_ATOMIC,'connection',None) is not None:raise ValueError('İç içe kayıt isteği geçersiz.')
    with _WRITE_LOCK:
        c=_DB_310();c.execute('BEGIN IMMEDIATE');_ATOMIC.connection=c
        try:
            yield c;c.commit()
        except Exception:c.rollback();raise
        finally:_ATOMIC.connection=None;c.close()

class _RegistrationConflict(Exception):
    def __init__(self,result):self.result=result

def kayit_program(d):
    request=required(d.get('istek_id'),'İşlem anahtarı')
    if len(request)>100:raise ValueError('İşlem anahtarı geçersiz.')
    try:
        with atomic_registration() as c:
            prior=c.execute('SELECT sonuc FROM kayit_islemleri WHERE istek_id=?',(request,)).fetchone()
            if prior:return json.loads(prior[0])
            program=dict(d.get('program') or {});did=d.get('danisan_id')
            if did:
                did=integer(did,1);exists(c,'danisanlar',did)
            else:
                client=dict(d.get('danisan') or {});client['terapist_id']=program.get('terapist_id')
                name=required(client.get('ad'),'Ad').strip().casefold();surname=str(client.get('soyad') or '').strip().casefold()
                phone=''.join(x for x in str(client.get('telefon') or '') if x.isdigit())
                for old in q(c,'SELECT id,ad,soyad,telefon FROM danisanlar WHERE aktif=1'):
                    if old['ad'].strip().casefold()==name and (old['soyad'] or '').strip().casefold()==surname and (not phone or ''.join(x for x in (old['telefon'] or '') if x.isdigit())==phone):
                        raise ValueError('Bu isim ve iletişim bilgileriyle danışan var. Mevcut danışan listesinden seçin; yeniden kayıt açılmadı.')
                did=danisan_ekle(client)
            program['danisan_id']=did
            if d.get('paket'):
                package=dict(d['paket']);package.pop('id',None);package['danisan_id']=did
                program['paket_id']=paket_kaydet(package)
            result=program_kaydet(program)
            if not result['saved']:raise _RegistrationConflict(result)
            if d.get('olcum'):
                measurement=dict(d['olcum']);measurement.pop('id',None);measurement.update(danisan_id=did,asama=0)
                olcum_kaydet(measurement)
            result.update(danisan_id=did,paket_id=program.get('paket_id'))
            if d.get('tahsilat'):
                if not program.get('paket_id'):raise ValueError('Paket tahsilatı için paket seçin.')
                _payment_write(c,dict(d['tahsilat'],danisan_id=did,paket_id=program['paket_id']))
            c.execute('INSERT INTO kayit_islemleri VALUES(?,?)',(request,json.dumps(result)))
            return result
    except _RegistrationConflict as e:return e.result

def olcum_veri(did):
    c=get_db()
    try:
        exists(c,'danisanlar',did)
        count=c.execute("SELECT COUNT(*) FROM seanslar s JOIN hizmet_alanlari h ON h.id=s.hizmet_id WHERE s.danisan_id=? AND h.kategori='pilates' AND s.gelmedi=0 AND s.tarih<=?",(did,date.today().isoformat())).fetchone()[0]
        rows=q(c,'SELECT * FROM vucut_olcumleri WHERE danisan_id=? ORDER BY asama,tarih',(did,))
        stages={r['asama'] for r in rows};due=[x for x in range(0,count+1,8) if x not in stages]
        member=bool(c.execute('SELECT 1 FROM pilates_uyeleri WHERE danisan_id=?',(did,)).fetchone() or c.execute('SELECT 1 FROM pilates_paketleri WHERE danisan_id=?',(did,)).fetchone() or count)
        return {'items':rows,'gerceklesen':count,'eksik_asamalar':due,'onerilen_asama':(count//8)*8 if (count//8)*8 not in stages else None,'sonraki_asama':((count//8)+1)*8,'pilates_uyesi':member}
    finally:c.close()

def olcum_kaydet(d):
    with transaction() as c:
        old=exists(c,'vucut_olcumleri',d['id']) if d.get('id') else {};v={**old,**d};did=integer(v.get('danisan_id'),1);exists(c,'danisanlar',did)
        if old and did!=old['danisan_id']:raise ValueError('Ölçüm başka kişiye taşınamaz.')
        stage=integer(v.get('asama',0),0,100000)
        if stage%8:raise ValueError('Ölçüm aşaması başlangıç veya 8’in katı olmalı.')
        info=olcum_veri(did)
        if stage>info['gerceklesen']:raise ValueError('Henüz bu seans aşamasına ulaşılmadı.')
        dt=valid_date(v.get('tarih'))
        if dt>date.today().isoformat():raise ValueError('Ölçüm tarihi gelecekte olamaz.')
        values=[]
        for key,_ in MEASURE_FIELDS:
            val=v.get(key)
            if val in (None,''):values.append(None);continue
            try:num=float(str(val).replace(',','.'))
            except (TypeError,ValueError):raise ValueError('Ölçümler sayı olmalı.')
            if not math.isfinite(num) or not 0<num<=500:raise ValueError('Ölçüler 0’dan büyük, en çok 500 olmalı.')
            values.append(round(num,2))
        if not any(x is not None for x in values):raise ValueError('En az bir ölçü girin.')
        duplicate=c.execute('SELECT id FROM vucut_olcumleri WHERE danisan_id=? AND asama=? AND id<>?',(did,stage,old.get('id',0))).fetchone()
        if duplicate:raise ValueError('Bu aşamanın ölçümü var; mevcut ölçümü düzenleyin.')
        fields=['danisan_id','tarih','asama','gerceklesen','hedef','notlar']+[k for k,_ in MEASURE_FIELDS]
        vals=[did,dt,stage,info['gerceklesen'],str(v.get('hedef') or ''),str(v.get('notlar') or '')]+values
        if old:c.execute('UPDATE vucut_olcumleri SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',vals+[old['id']]);return old['id']
        return c.execute('INSERT INTO vucut_olcumleri('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',vals).lastrowid

_DETAIL_310=danisan_detay

def danisan_detay(did):
    d=_DETAIL_310(did)
    if d:d['olcumler']=olcum_veri(did)
    return d

def client_statement(did,start=None,end=None,future_end=None,reports=False,measurements=False):
    today=date.today().isoformat();start=valid_date(start or today[:7]+'-01');end=valid_date(end or today);future_end=valid_date(future_end or (date.today()+timedelta(days=30)).isoformat())
    if end<start or (date.fromisoformat(end)-date.fromisoformat(start)).days>3660:raise ValueError('Döküm tarih aralığı geçersiz (en çok 10 yıl).')
    if future_end<today or (date.fromisoformat(future_end)-date.today()).days>366:raise ValueError('Gelecek program bitişi bugün ile bir yıl arasında olmalı.')
    c=get_db()
    try:
        person=exists(c,'danisanlar',did,'Danışan');person={k:person[k] for k in ['id','ad','soyad']}
        sessions=q(c,'''SELECT s.id,s.tarih,s.saat,s.gelmedi,s.hak_dustu,s.hediye,s.paket_id,s.ucret,h.alan_adi hizmet_adi,t.ad terapist_adi FROM seanslar s LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id LEFT JOIN terapistler t ON t.id=s.terapist_id WHERE s.danisan_id=? AND s.tarih BETWEEN ? AND ? ORDER BY s.tarih,s.saat''',(did,start,end))
        paid=q(c,'SELECT id,tarih,tutar,yontem,paket_id,seans_id FROM odemeler WHERE danisan_id=? AND tarih BETWEEN ? AND ? ORDER BY tarih,id',(did,start,end))
        packages=[p for p in paketler_listesi(did) if p['baslangic']<=end and p['bitis']>=start]
        # Outstanding balance as of the selected end date, with packages counted once.
        charge=c.execute('SELECT COALESCE(SUM(fiyat),0) FROM pilates_paketleri WHERE danisan_id=? AND baslangic<=?',(did,end)).fetchone()[0]+c.execute('SELECT COALESCE(SUM(ucret),0) FROM seanslar WHERE danisan_id=? AND paket_id IS NULL AND tarih<=?',(did,end)).fetchone()[0]
        receipts=c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE danisan_id=? AND tarih<=?',(did,end)).fetchone()[0]
        # Package table totals are evaluated at end, not today's later receipts.
        for p in packages:
            p['tahsilat']=round(c.execute('SELECT COALESCE(SUM(tutar),0) FROM odemeler WHERE paket_id=? AND tarih<=?',(p['id'],end)).fetchone()[0],2);p['bakiye']=round(max(0,p['fiyat']-p['tahsilat']),2)
        actual=q(c,'SELECT * FROM seanslar WHERE danisan_id=? AND tarih BETWEEN ? AND ?',(did,today,future_end))
        actual_keys={(s['tarih'],s['saat'],s['terapist_id']) for s in actual}
        for s in actual:
            if s.get('plan_tarihi') and s.get('planlanan_saat'):actual_keys.add((s['plan_tarihi'],s['planlanan_saat'],s['terapist_id']))
        appointments=q(c,"SELECT r.*,t.ad terapist_adi FROM randevular r LEFT JOIN terapistler t ON t.id=r.terapist_id WHERE r.danisan_id=? AND r.tarih BETWEEN ? AND ?",(did,today,future_end))
        cancelled={(a['tarih'],a['saat'],a['terapist_id']) for a in appointments if a['durum']=='iptal'}
        upcoming={}
        plans=[p for p in haftalik_program_sablonlari_listesi() if p['danisan_id']==int(did)]
        for p in plans:
            first=max(today,p.get('baslangic') or today);last=min(future_end,p.get('bitis') or future_end)
            dt=date.fromisoformat(first);dt+=timedelta(days=(p['gun_index']-dt.weekday())%7)
            while dt.isoformat()<=last:
                ds=dt.isoformat();key=(ds,p['saat'],p['terapist_id'])
                if key not in actual_keys and key not in cancelled and (ds>today or p['saat']>=datetime.now().strftime('%H:%M')):
                    upcoming[key]={'tarih':ds,'saat':p['saat'],'terapist_adi':p['terapist_adi'],'hizmet_adi':p['hizmet_adi'],'oda_adi':p['oda_adi'],'kaynak':'Haftalık program'}
                dt+=timedelta(days=7)
        for a in appointments:
            key=(a['tarih'],a['saat'],a['terapist_id'])
            if a['durum'] not in ('iptal','tamamlandi') and key not in actual_keys and (a['tarih']>today or a['saat']>=datetime.now().strftime('%H:%M')):
                upcoming.setdefault(key,{'tarih':a['tarih'],'saat':a['saat'],'terapist_adi':a['terapist_adi'],'hizmet_adi':'Randevu','oda_adi':'','kaynak':'Randevu'})
        result={'danisan':person,'start':start,'end':end,'future_end':future_end,'seanslar':sessions,'odemeler':paid,'paketler':packages,'gelecek':sorted(upcoming.values(),key=lambda r:(r['tarih'],r['saat'])),'donem_seans_tutari':round(sum(s['ucret'] for s in sessions),2),'donem_tahsilat':round(sum(p['tutar'] for p in paid),2),'bakiye':round(charge-receipts,2),'raporlar':[],'pdfler':[],'olcumler':[]}
        if reports:
            result['raporlar']=q(c,'SELECT id,tarih,baslik,icerik FROM danisan_raporlar WHERE danisan_id=? AND tarih<=? ORDER BY tarih DESC',(did,end))
            result['pdfler']=q(c,'SELECT id,tarih,dosya_adi FROM danisan_rapor_dosyalari WHERE danisan_id=? AND tarih<=? ORDER BY tarih DESC',(did,end))
        if measurements:result['olcumler']=q(c,'SELECT * FROM vucut_olcumleri WHERE danisan_id=? AND tarih<=? ORDER BY asama',(did,end))
        return result
    finally:c.close()

def portal_scope(token):
    c=get_db()
    try:
        r=c.execute("SELECT p.* FROM portal_erisimleri p JOIN danisanlar d ON d.id=p.danisan_id WHERE p.token=? AND p.aktif=1 AND d.aktif=1 AND p.son_gecerlilik>=?",(token,date.today().isoformat())).fetchone()
        return dict(r) if r else None
    finally:c.close()

def scoped_statement(token):
    scope=portal_scope(token)
    if not scope:return None
    # The generated link carries the date/attachment choices stored by the clinic.
    future=scope.get('gelecek_bitis') or (date.today()+timedelta(days=30)).isoformat()
    return client_statement(scope['danisan_id'],scope.get('dokum_baslangic') or None,scope.get('dokum_bitis') or None,max(future,date.today().isoformat()),bool(scope.get('paylas_rapor')),bool(scope.get('paylas_olcum')))

def statement_link(d):
    did=integer(d.get('danisan_id'),1);start=valid_date(d.get('start'));end=valid_date(d.get('end'));future=valid_date(d.get('future_end'))
    client_statement(did,start,end,future)
    with transaction() as c:
        token=secrets.token_urlsafe(24);expiry=(date.today()+timedelta(days=30)).isoformat()
        c.execute('INSERT INTO portal_erisimleri(danisan_id,token,aktif,olusturma_tarihi,son_gecerlilik,dokum_baslangic,dokum_bitis,gelecek_bitis,paylas_rapor,paylas_olcum) VALUES(?,?,1,?,?,?,?,?,?,?)',(did,token,datetime.now().isoformat(timespec='seconds'),expiry,start,end,future,flag(d.get('reports')),flag(d.get('measurements'))))
        return {'token':token,'expires':expiry}

def statement_html(d,token=None):
    esc=lambda x:html_lib.escape(str(x if x is not None else ''))
    tl=lambda x:f'{float(x):,.2f}'.replace(',','X').replace('.',',').replace('X','.')+' TL'
    def tab(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+(''.join('<tr>'+''.join('<td>'+str(v)+'</td>' for v in row)+'</tr>' for row in rows) or '<tr><td colspan="'+str(len(headers))+'">Kayıt yok</td></tr>')+'</tbody></table></div>'
    sessions=tab(['Tarih','Saat','Hizmet / Terapist','Katılım','Ücret','Ücret türü'],[[esc(s['tarih']),esc(s['saat']),esc(str(s['hizmet_adi'] or '')+' / '+str(s['terapist_adi'] or '')),('Gelmedi · hak düşüldü' if s['hak_dustu'] else 'Gelmedi · hak düşülmedi') if s['gelmedi'] else 'Geldi',tl(s['ucret']),'Paket içi · tekrar borçlandırılmaz' if s['paket_id'] else 'Tek seans'] for s in d['seanslar']])
    packages=tab(['Paket','Grup','Kişi başı toplam','Dönem sonuna dek tahsilat','Paket bakiyesi'],[[esc(p['ad']),esc({'bireysel':'Bireysel','grup2':'2 kişi','grup3':'3 kişi'}.get(p['grup_turu'])),tl(p['fiyat']),tl(p['tahsilat']),tl(p['bakiye'])] for p in d['paketler']])
    payments=tab(['Ödeme tarihi','Tutar','Yöntem'],[[esc(p['tarih']),tl(p['tutar']),esc(p['yontem'])] for p in d['odemeler']])
    future=tab(['Tarih','Saat','Hizmet','Terapist','Salon'],[[esc(p['tarih']),esc(p['saat']),esc(p['hizmet_adi']),esc(p['terapist_adi']),esc(p['oda_adi'])] for p in d['gelecek']])
    report=''.join('<article><h3>'+esc(r['baslik'])+' · '+esc(r['tarih'])+'</h3><pre>'+esc(r['icerik'])+'</pre></article>' for r in d['raporlar'])
    for r in d['pdfler']:
        url=('/portal-pdf?token='+urllib.parse.quote(token)+'&id=' if token else '/rapor_pdf?id=')+str(r['id'])
        report+='<p><a target="_blank" rel="noopener" href="'+esc(url)+'">'+esc(r['dosya_adi'])+' · '+esc(r['tarih'])+'</a></p>'
    measures=''
    if d['olcumler']:
        measures='<h2>Vücut ölçümleri</h2>'+tab(['Ölçüm']+[('Başlangıç' if r['asama']==0 else str(r['asama'])+'. seans')+' · '+r['tarih'] for r in d['olcumler']],[[esc(label)]+[esc(r[key]) if r[key] is not None else '—' for r in d['olcumler']] for key,label in MEASURE_FIELDS])
    return '''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Danışan Dökümü</title><style>body{font:14px system-ui;color:#24303d;max-width:1100px;margin:25px auto;padding:15px}h1{font-size:26px}h2{font-size:18px;border-bottom:2px solid #eabf47;padding-bottom:8px;margin-top:28px}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:9px;border-bottom:1px solid #e2e5e8;text-align:left}th{background:#fff4d4}.scroll{overflow:auto}pre{white-space:pre-wrap;font:inherit}article{break-inside:avoid}button{padding:8px 15px;border:1px solid #ddd;background:#fff;border-radius:7px}.summary{background:#f5f6f8;padding:16px;border-radius:8px;line-height:1.8}@media print{button{display:none}.scroll{overflow:visible}body{margin:0;padding:0}}</style><button onclick="window.print()">Yazdır / PDF kaydet</button>'''+ '<h1>'+esc(ayar_al('klinik_adi','Arte Terapi'))+' · Danışan Dökümü</h1><h2>'+esc(d['danisan']['ad']+' '+d['danisan']['soyad'])+'</h2><p>Dönem: '+esc(d['start'])+' — '+esc(d['end'])+'</p><div class="summary">Dönem seans tutarı: <b>'+tl(d['donem_seans_tutari'])+'</b> · Dönem tahsilatı: <b>'+tl(d['donem_tahsilat'])+'</b><br>Dönem sonu hesap bakiyesi: <b>'+tl(d['bakiye'])+'</b> (eksi tutar avans/fazla ödeme).<br>Paket içindeki seanslar paket ücretine tekrar eklenmez. Bağlantısı olmayan eski ödemeler hesap bakiyesine dahildir; eski “ödendi” işaretleri tek başına tahsilat sayılmaz.</div><h2>Gün gün seanslar</h2>'+sessions+'<h2>Paket ücretleri</h2>'+packages+'<h2>Ödemeler</h2>'+payments+'<h2>Gelecek seanslar · '+esc(d['future_end'])+' tarihine kadar</h2>'+future+('<h2>Gelişim raporları ve ekler</h2>'+report if report else '')+measures+'</html>'

def public_portal_html(token):
    d=scoped_statement(token)
    return statement_html(d,token) if d else '<meta charset="utf-8"><p>Bağlantı geçersiz veya süresi dolmuş.</p>'

_SAVE_310=_save_kind
_LIST_310=_list_kind
_DELETE_310=_delete_record

def _save_kind(kind,d):
    if kind=='kayit_program':return kayit_program(d)
    if kind=='olcumler':return olcum_kaydet(d)
    if kind=='dokum_link':return statement_link(d)
    return _SAVE_310(kind,d)

def _list_kind(kind,qs):
    if kind=='olcumler':return olcum_veri(integer(qs.get('danisan_id'),1))
    return _LIST_310(kind,qs)

def _delete_record(kind,ident):
    if kind=='olcumler':
        with transaction() as c:c.execute('DELETE FROM vucut_olcumleri WHERE id=?',(integer(ident,1),))
        return True
    return _DELETE_310(kind,ident)


# v3.11.1: local network access and mobile connection information.
APP_VERSION='3.11.1'

def mobile_connection_info(server):
    import ipaddress
    bind,port=server.server_address[:2]
    enabled=bind not in ('127.0.0.1','::1','localhost')
    addresses=[]
    for raw in get_local_ips():
        try:ip=ipaddress.ip_address(raw)
        except ValueError:continue
        if ip.version==4 and ip.is_private and not ip.is_loopback and not ip.is_unspecified and not ip.is_link_local:
            if bind in ('0.0.0.0','') or str(ip)==bind:addresses.append(f'http://{ip}:{port}')
    return {'enabled':enabled,'port':port,'urls':list(dict.fromkeys(addresses)) if enabled else [],'local_url':f'http://127.0.0.1:{port}'}

def _run_app():
    init_db()
    bind=os.getenv('ARTE_BIND','0.0.0.0');port=integer(os.getenv('ARTE_PORT',str(PORT)),1,65535)
    try:server=ArteServer((bind,port),Handler)
    except OSError as e:
        print(f'Program başlatılamadı: {e}. Eski Arte Terapi penceresini kapatıp tekrar deneyin.')
        try:input('Kapatmak için Enter…')
        except (EOFError,KeyboardInterrupt):pass
        return
    info=mobile_connection_info(server)
    print(f'Arte Terapi v{APP_VERSION} — {info["local_url"]}')
    print('İlk kullanımda parolayı bu bilgisayardaki tarayıcıda oluşturun.')
    for url in info['urls']:print('Telefon (aynı Wi-Fi): '+url)
    if info['enabled']:print('Mobil adresleri Ayarlar > Telefondan erişim bölümünde görebilirsiniz. Bilgisayar ve bu pencere açık kalmalı.')
    print('Veriler: '+DB_PATH)
    if os.getenv('ARTE_NO_BROWSER', '').lower() not in ('1', 'true', 'yes'):
        threading.Timer(1,lambda:webbrowser.open(info['local_url'])).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

def get_local_ips():
    """Discover adapter addresses without requiring an Internet connection."""
    import ipaddress,re,subprocess
    found=[]
    def add(value):
        try:ip=ipaddress.ip_address(value)
        except ValueError:return
        if ip.version==4 and ip.is_private and not ip.is_loopback and not ip.is_unspecified and not ip.is_link_local and str(ip) not in found:found.append(str(ip))
    try:
        for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):add(item[4][0])
    except OSError:pass
    if os.name=='nt':
        try:
            result=subprocess.run(['ipconfig'],capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            text=result.stdout.decode('utf-8',errors='ignore')
            for value in re.findall(r'IPv4[^\r\n:]*:\s*(\d+\.\d+\.\d+\.\d+)',text):add(value)
        except (OSError,subprocess.TimeoutExpired):pass
    else:
        try:
            import fcntl,struct
            try:names=[name for _,name in socket.if_nameindex()]
            except OSError:names=os.listdir('/sys/class/net')
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                for name in names:
                    try:add(socket.inet_ntoa(fcntl.ioctl(s.fileno(),0x8915,struct.pack('256s',name.encode()[:15]))[20:24]))
                    except OSError:pass
        except (ImportError,OSError):pass
    return found or ['127.0.0.1']


APP_VERSION='3.12.0'
_INIT_311=init_db

def init_db():
    _INIT_311()
    with _INIT_LOCK:
        c=get_db()
        try:done=c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_3120'").fetchone()
        finally:c.close()
        if done:return
        folder=os.path.join(os.path.dirname(DB_PATH),'yedekler');os.makedirs(folder,exist_ok=True)
        with open(os.path.join(folder,'v3120_oncesi_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'wb') as f:f.write(backup_bytes())
        with transaction() as c:
            c.execute("CREATE TABLE IF NOT EXISTS pilates_gruplari(id INTEGER PRIMARY KEY,ad TEXT NOT NULL,kapasite INTEGER NOT NULL,aktif INTEGER NOT NULL DEFAULT 1)")
            c.execute("CREATE TABLE IF NOT EXISTS pilates_grup_uyeleri(grup_id INTEGER NOT NULL REFERENCES pilates_gruplari(id),danisan_id INTEGER NOT NULL REFERENCES danisanlar(id),aktif INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(grup_id,danisan_id))")
            if 'grup_id' not in {r['name'] for r in c.execute('PRAGMA table_info(pilates_paketleri)')}:c.execute('ALTER TABLE pilates_paketleri ADD COLUMN grup_id INTEGER REFERENCES pilates_gruplari(id)')
            c.execute("INSERT INTO ayarlar VALUES('schema_3120','1')")

def grup_kaydet(d):
    with transaction() as c:
        old=exists(c,'pilates_gruplari',d['id']) if d.get('id') else {};gid=old.get('id');capacity=integer(d.get('kapasite',old.get('kapasite',2)),2,3)
        members=d.get('uyeler',[])
        if not isinstance(members,list) or not 1<=len(members)<=capacity:raise ValueError('Gruba kapasitesi kadar, en az bir üye ekleyin.')
        ids=[integer(x.get('danisan_id'),1) for x in members]
        if len(set(ids))!=len(ids):raise ValueError('Aynı kişi gruba iki kez eklenemez.')
        if old and capacity!=old['kapasite'] and c.execute('SELECT 1 FROM pilates_paketleri WHERE grup_id=?',(gid,)).fetchone():raise ValueError('Paketi olan grubun türünü değiştirmeyin; yeni grup oluşturun.')
        for item,did in zip(members,ids):
            if not exists(c,'danisanlar',did)['aktif']:raise ValueError('Üye aktif olmalı.')
            if item.get('paket_id'):
                p=exists(c,'pilates_paketleri',integer(item['paket_id'],1))
                if p['danisan_id']!=did or p['grup_turu']!='grup'+str(capacity):raise ValueError('Her üyeye kendi adına, grup türüne uygun paket seçin.')
                if p.get('grup_id') and p['grup_id']!=gid:raise ValueError('Bu paket başka gruba bağlı.')
        name=required(d.get('ad',old.get('ad')),'Grup adı')
        if gid:c.execute('UPDATE pilates_gruplari SET ad=?,kapasite=?,aktif=? WHERE id=?',(name,capacity,flag(d.get('aktif',1)),gid))
        else:gid=c.execute('INSERT INTO pilates_gruplari(ad,kapasite,aktif) VALUES(?,?,?)',(name,capacity,flag(d.get('aktif',1)))).lastrowid
        c.execute('UPDATE pilates_grup_uyeleri SET aktif=0 WHERE grup_id=?',(gid,))
        for item,did in zip(members,ids):
            c.execute('INSERT INTO pilates_grup_uyeleri VALUES(?,?,1) ON CONFLICT(grup_id,danisan_id) DO UPDATE SET aktif=1',(gid,did))
            c.execute('INSERT OR IGNORE INTO pilates_uyeleri VALUES(?,?)',(did,date.today().isoformat()))
            if item.get('paket_id'):c.execute('UPDATE pilates_paketleri SET grup_id=? WHERE id=?',(gid,integer(item['paket_id'],1)))
        return gid

def gruplar_listesi():
    c=get_db()
    try:
        groups=q(c,'SELECT * FROM pilates_gruplari ORDER BY aktif DESC,ad,id')
        for g in groups:
            g['uyeler']=q(c,"SELECT u.danisan_id,u.aktif,d.ad||' '||d.soyad ad FROM pilates_grup_uyeleri u JOIN danisanlar d ON d.id=u.danisan_id WHERE u.grup_id=? ORDER BY u.aktif DESC,d.ad",(g['id'],))
        return groups
    finally:c.close()

def grup_detay(gid):
    c=get_db()
    try:
        g=exists(c,'pilates_gruplari',gid);g['uyeler']=[]
        for link in q(c,"SELECT u.danisan_id,u.aktif,d.ad||' '||d.soyad ad FROM pilates_grup_uyeleri u JOIN danisanlar d ON d.id=u.danisan_id WHERE grup_id=? ORDER BY u.aktif DESC,d.ad",(gid,)):
            did=link['danisan_id'];ps=[p for p in paketler_listesi(did) if p.get('grup_id')==int(gid)]
            payments=q(c,'SELECT o.id,o.tarih,o.tutar,o.yontem,o.notlar,o.paket_id,p.ad paket_adi FROM odemeler o JOIN pilates_paketleri p ON p.id=o.paket_id WHERE p.grup_id=? AND o.danisan_id=? ORDER BY o.tarih DESC,o.id DESC',(gid,did))
            g['uyeler'].append({**link,'paketler':ps,'odemeler':payments,'olcumler':olcum_veri(did),'paket_toplami':round(sum(p['fiyat'] for p in ps),2),'odenen':round(sum(p['tutar'] for p in payments),2),'bakiye':round(sum(p['bakiye'] for p in ps),2)})
        return g
    finally:c.close()

_PACKAGE_311=paket_kaydet

def paket_kaydet(d):
    # Keep ownership, package creation and group linkage in the same transaction.
    d=dict(d)
    if d.get('id'):
        c=get_db()
        try:old=exists(c,'pilates_paketleri',d['id'])
        finally:c.close()
        if old.get('grup_id') and d.get('grup_id') not in (None,'',old['grup_id'],str(old['grup_id'])):raise ValueError('Paket başka gruba taşınamaz.')
        d={**old,**d}
        if old.get('grup_id'):d['grup_id']=old['grup_id']
    if not d.get('grup_id'):return _PACKAGE_311(d)
    def write(c):
        group=exists(c,'pilates_gruplari',integer(d['grup_id'],1));did=integer(d.get('danisan_id'),1)
        if not d.get('id') and (not group['aktif'] or not c.execute('SELECT 1 FROM pilates_grup_uyeleri WHERE grup_id=? AND danisan_id=? AND aktif=1',(group['id'],did)).fetchone()):raise ValueError('Aktif grup üyesi seçin.')
        if d.get('grup_turu')!='grup'+str(group['kapasite']):raise ValueError('Paket türü grubun kapasitesiyle aynı olmalı.')
        if d.get('id'):
            old=exists(c,'pilates_paketleri',d['id'])
            if old.get('grup_id') and old['grup_id']!=group['id']:raise ValueError('Paket başka gruba taşınamaz.')
        pid=_PACKAGE_311(d);c.execute('UPDATE pilates_paketleri SET grup_id=? WHERE id=?',(group['id'],pid));return pid
    if getattr(_ATOMIC,'connection',None) is not None:return write(_ATOMIC.connection)
    with atomic_registration() as c:return write(c)

def service_references(c,hid):
    total=0
    for row in q(c,"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        table=row['name']
        if table=='hizmet_terapistleri':continue
        safe='"'+table.replace('"','""')+'"'
        if 'hizmet_id' in {r['name'] for r in c.execute('PRAGMA table_info('+safe+')')}:
            total+=c.execute('SELECT COUNT(*) FROM '+safe+' WHERE hizmet_id=?',(hid,)).fetchone()[0]
    return total

def service_action(d):
    with atomic_registration() as c:
        h=exists(c,'hizmet_alanlari',integer(d.get('id'),1),'Hizmet');action=d.get('islem')
        if action=='toggle':c.execute('UPDATE hizmet_alanlari SET aktif=? WHERE id=?',(flag(d.get('aktif')),h['id']));return h['id']
        if action=='delete':
            if service_references(c,h['id']):raise ValueError('Bu hizmetin kayıtları var; geçmişi korumak için silmek yerine kapatın.')
            c.execute('DELETE FROM hizmet_alanlari WHERE id=?',(h['id'],));return h['id']
        if action=='assign':
            tid=integer(d.get('terapist_id'),1)
            if not exists(c,'terapistler',tid)['aktif']:raise ValueError('Aktif terapist seçin.')
            if tid==h['terapist_id']:return h['id']
            existing=c.execute('SELECT id FROM hizmet_alanlari WHERE alan_adi=? AND kategori=? AND terapist_id=?',(h['alan_adi'],h['kategori'],tid)).fetchone()
            if existing:
                c.execute('UPDATE hizmet_alanlari SET aktif=1 WHERE id=?',(existing['id'],));return existing['id']
            if not service_references(c,h['id']):
                c.execute('UPDATE hizmet_alanlari SET terapist_id=? WHERE id=?',(tid,h['id']));return h['id']
            copy=dict(h);copy.pop('id');copy.update(terapist_id=tid,aktif=1)
            return _save_record('hizmetler',copy)
        raise ValueError('Hizmet işlemi geçersiz.')

_SAVE_312=_save_kind
_LIST_312=_list_kind

def _save_kind(kind,d):
    if kind=='gruplar':return grup_kaydet(d)
    if kind=='hizmet_islem':return service_action(d)
    if kind=='hizmetler' and d.get('id'):
        c=get_db()
        try:
            old=exists(c,'hizmet_alanlari',d['id'])
            if str(d.get('terapist_id',old['terapist_id']))!=str(old['terapist_id']) and service_references(c,old['id']):raise ValueError('Terapist ata düğmesini kullanın; geçmiş kayıtlar korunacak.')
        finally:c.close()
    return _SAVE_312(kind,d)

def _list_kind(kind,qs):
    if kind=='gruplar':return grup_detay(integer(qs['id'],1)) if qs.get('id') else gruplar_listesi()
    return _LIST_312(kind,qs)

_SAVE_GROUPS=_save_kind

def _save_kind(kind,d):
    if kind=='grup_odeme':
        with transaction() as c:
            gid=integer(d.get('grup_id'),1);did=integer(d.get('danisan_id'),1);pid=integer(d.get('paket_id'),1)
            exists(c,'pilates_gruplari',gid)
            if not c.execute('SELECT 1 FROM pilates_grup_uyeleri WHERE grup_id=? AND danisan_id=?',(gid,did)).fetchone():raise ValueError('Üye bu gruba ait değil.')
            p=exists(c,'pilates_paketleri',pid)
            if p['danisan_id']!=did or p.get('grup_id')!=gid:raise ValueError('Ödeme seçili üyenin bu gruptaki paketine ait olmalı.')
            return _payment_write(c,dict(d,seans_id=None))
    return _SAVE_GROUPS(kind,d)


APP_VERSION='3.13.0'
_INIT_312=init_db

def init_db():
    _INIT_312()
    with _INIT_LOCK:
        c=get_db()
        try:done=c.execute("SELECT 1 FROM ayarlar WHERE anahtar='schema_3130'").fetchone()
        finally:c.close()
        if done:return
        folder=os.path.join(os.path.dirname(DB_PATH),'yedekler');os.makedirs(folder,exist_ok=True)
        with open(os.path.join(folder,'v3130_oncesi_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.zip'),'wb') as f:f.write(backup_bytes())
        with transaction() as c:
            c.execute('CREATE TABLE IF NOT EXISTS hizmet_terapistleri(hizmet_id INTEGER NOT NULL REFERENCES hizmet_alanlari(id) ON DELETE CASCADE,terapist_id INTEGER NOT NULL REFERENCES terapistler(id),PRIMARY KEY(hizmet_id,terapist_id))')
            c.execute('INSERT OR IGNORE INTO hizmet_terapistleri SELECT id,terapist_id FROM hizmet_alanlari')
            c.execute("INSERT INTO ayarlar VALUES('schema_3130','1')")

def service_allows(c,hid,tid):
    return bool(c.execute('SELECT 1 FROM hizmet_terapistleri WHERE hizmet_id=? AND terapist_id=?',(hid,tid)).fetchone())

def hizmetler_listesi(terapist_id=None,include_inactive=False):
    c=get_db()
    try:
        rows=q(c,'SELECT h.* FROM hizmet_alanlari h WHERE 1=1'+('' if include_inactive else ' AND h.aktif=1')+(' AND EXISTS(SELECT 1 FROM hizmet_terapistleri a WHERE a.hizmet_id=h.id AND a.terapist_id=?)' if terapist_id else '')+' ORDER BY h.alan_adi,h.id',[terapist_id] if terapist_id else [])
        assignments={}
        for t in q(c,"SELECT a.hizmet_id,t.id,t.ad||' '||COALESCE(t.soyad,'') ad,t.aktif FROM hizmet_terapistleri a JOIN terapistler t ON t.id=a.terapist_id ORDER BY t.ad,t.id"):
            hid=t.pop('hizmet_id');assignments.setdefault(hid,[]).append(t)
        for h in rows:
            h['terapistler']=assignments.get(h['id'],[])
            h['terapist_ids']=[t['id'] for t in h['terapistler']];h['terapist_adi']=', '.join(t['ad'].strip() for t in h['terapistler'])
        return rows
    finally:c.close()

_RECORD_312=_save_record

def service_manage(d):
    def write(c):
        old=exists(c,'hizmet_alanlari',d['id']) if d.get('id') else {}
        current=[r[0] for r in c.execute('SELECT terapist_id FROM hizmet_terapistleri WHERE hizmet_id=?',(old.get('id',0),))]
        requested=d.get('terapist_ids')
        if requested is None:
            requested=current or [d.get('terapist_id')]
            if old and d.get('terapist_id') and int(d['terapist_id']) not in requested:requested=list(requested)+[d['terapist_id']]
        if not isinstance(requested,list) or not requested:raise ValueError('En az bir terapist seçin.')
        ids=sorted(set(integer(x,1) for x in requested))
        for tid in ids:
            t=exists(c,'terapistler',tid)
            if not t['aktif'] and tid not in current:raise ValueError('Yeni atama için aktif terapist seçin.')
        removed=set(current)-set(ids)
        for tid in removed:
            if c.execute("SELECT 1 FROM haftalik_program_sablonlari WHERE hizmet_id=? AND terapist_id=? AND aktif=1 AND (bitis IS NULL OR bitis='' OR bitis>=?)",(old['id'],tid,date.today().isoformat())).fetchone():raise ValueError('Çıkarmak istediğiniz terapistin aktif haftalık planları var. Önce bu planları aktarın veya durdurun.')
            if c.execute("SELECT 1 FROM randevular WHERE hizmet_id=? AND terapist_id=? AND tarih>=? AND durum NOT IN ('iptal','tamamlandi')",(old['id'],tid,date.today().isoformat())).fetchone():raise ValueError('Terapistin gelecek randevularını önce aktarın veya iptal edin.')
        payload=dict(d);payload['terapist_id']=old['terapist_id'] if old and old['terapist_id'] in ids else ids[0]
        hid=_RECORD_312('hizmetler',payload)
        c.execute('DELETE FROM hizmet_terapistleri WHERE hizmet_id=?',(hid,))
        c.executemany('INSERT INTO hizmet_terapistleri VALUES(?,?)',[(hid,tid) for tid in ids])
        return hid
    if getattr(_ATOMIC,'connection',None) is not None:return write(_ATOMIC.connection)
    with atomic_registration() as c:return write(c)

def _save_record(kind,d):
    return service_manage(d) if kind=='hizmetler' else _RECORD_312(kind,d)

_ACTION_312=service_action

def service_action(d):
    if d.get('islem')=='assign':
        c=get_db()
        try:ids=[r[0] for r in c.execute('SELECT terapist_id FROM hizmet_terapistleri WHERE hizmet_id=?',(d.get('id'),))]
        finally:c.close()
        return service_manage({'id':d.get('id'),'terapist_ids':ids+[d.get('terapist_id')]})
    return _ACTION_312(d)

def paket_sil(pid):
    with transaction() as c:
        exists(c,'pilates_paketleri',pid,'Paket')
        used=any(c.execute('SELECT 1 FROM '+table+' WHERE paket_id=?',(pid,)).fetchone() for table in ['seanslar','odemeler','haftalik_program_sablonlari'])
        if used:
            c.execute('UPDATE pilates_paketleri SET aktif=0 WHERE id=?',(pid,))
            stopped=c.execute('UPDATE haftalik_program_sablonlari SET aktif=0 WHERE paket_id=? AND aktif=1',(pid,)).rowcount
            return {'islem':'kapandi','durdurulan_plan':stopped}
        c.execute('DELETE FROM pilates_paketleri WHERE id=?',(pid,));return {'islem':'silindi'}

_SAVE_MULTI=_save_kind

def _save_kind(kind,d):
    if kind in ('hizmetler','hizmet_yonet'):return service_manage(d)
    if kind=='paket_sil':return paket_sil(integer(d.get('id'),1))
    return _SAVE_MULTI(kind,d)


def build_html():
    """Load the interface independently of the current working directory."""
    from pathlib import Path
    return (Path(__file__).resolve().parent / "web" / "index.html").read_text(encoding="utf-8")

def read_report_blob(record):
    if not os.path.isfile(record['dosya_yolu']): return None
    with open(record['dosya_yolu'], 'rb') as stream: return stream.read()

if CLOUD_MODE:
    from cloud.runtime import install
    install(globals())

if __name__ == '__main__':
    _run_app()


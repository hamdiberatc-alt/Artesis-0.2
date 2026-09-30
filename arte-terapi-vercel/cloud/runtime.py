"""Persistent cloud storage and Vercel request lifecycle. No local data files."""
import base64
import hashlib
import hmac
import io
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.parse
import zipfile
from . import db

SCHEMA = '''
CREATE TABLE IF NOT EXISTS cloud_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cloud_pdf_chunks(report_id INTEGER NOT NULL REFERENCES danisan_rapor_dosyalari(id) ON DELETE CASCADE,part INTEGER NOT NULL,data BLOB NOT NULL,PRIMARY KEY(report_id,part));
CREATE TABLE IF NOT EXISTS cloud_rate_limits(key TEXT PRIMARY KEY,window INTEGER NOT NULL,count INTEGER NOT NULL);
'''
CLOUD_VERSION = '1'
PDF_LIMIT = 2 * 1024 * 1024


def ensure_schema(c, password_hash):
    """Initialize only an empty database, under a remote writer lock."""
    c.execute('BEGIN IMMEDIATE')
    c.execute('PRAGMA defer_foreign_keys=ON')
    try:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if 'cloud_meta' in tables:
            version = c.execute("SELECT value FROM cloud_meta WHERE key='version'").fetchone()
            if not version or version[0] != CLOUD_VERSION:
                raise ValueError('Bulut şeması uyumsuz. Güncelleme öncesi yedek alın.')
        elif tables:
            raise ValueError('Hedef veritabanı boş değil. Yeni, boş bir Turso veritabanı seçin veya aktarım aracını kullanın.')
        else:
            c.executescript((Path(__file__).parent / 'seed.sql').read_text(encoding='utf-8'))
            c.executescript(SCHEMA)
            c.execute("INSERT INTO ayarlar(anahtar,deger) VALUES('admin_password_hash',?)", (password_hash,))
            c.execute("INSERT INTO cloud_meta VALUES('version',?)", (CLOUD_VERSION,))
        c.commit()
    except Exception:
        c.rollback()
        raise


def export_backup(connection):
    """A consistent remote read snapshot, exported to a portable SQLite ZIP.

    Bounded batches avoid collecting a whole remote table in one HTTP response.
    The SQLite copy exists only in RAM, never as primary storage.
    """
    local = sqlite3.connect(':memory:')
    try:
        # /dump produces one server-side snapshot without a long interactive transaction.
        local.executescript(connection.dump_sql())
        # A downloaded backup never carries active administrator browser sessions.
        local.execute('DELETE FROM auth_sessions')
        local.execute('DELETE FROM cloud_rate_limits')
        local.commit()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
            reports = local.execute('SELECT id FROM danisan_rapor_dosyalari').fetchall()
            for (rid,) in reports:
                parts = local.execute('SELECT data FROM cloud_pdf_chunks WHERE report_id=? ORDER BY part',(rid,)).fetchall()
                if parts: archive.writestr('rapor_pdfler/'+str(rid)+'.pdf', b''.join(r[0] for r in parts))
            archive.writestr('arteterapi.db', local.serialize())
            archive.writestr('OKU.txt', 'Tam yedek: SQLite ve rapor_pdfler. Yerel geri yüklemede uygulamayı kapatın, veritabanı ve PDF klasörünü birlikte geri yükleyin. Buluta geri yükleme için scripts/cloud_admin.py prepare-import kullanın; hedef boş olmalıdır.')
        return buf.getvalue()
    except Exception:
        connection.rollback()
        raise
    finally:
        local.close()


def install(app):
    os.environ.setdefault('TZ', 'Europe/Istanbul')
    if hasattr(time, 'tzset'): time.tzset()
    init_lock = threading.Lock()
    ready = False
    app['_DB_310'] = db.connect  # Preserve nested, atomic registration helpers.

    def init_db():
        nonlocal ready
        if ready: return
        with init_lock:
            if ready: return
            # Validate before connecting or changing the schema. No public setup route.
            password = os.getenv('ARTE_ADMIN_PASSWORD', '')
            if len(password) < 16:
                raise ValueError('ARTE_ADMIN_PASSWORD en az 16 karakter olmalı; Vercel ortam değişkenlerinden ayarlayın.')
            password_hash = app['_password_hash'](password)
            c = db.connect()
            try: ensure_schema(c, password_hash)
            finally: c.close()
            ready = True

    def read_report(record):
        c = app['get_db']()
        try: parts = c.execute('SELECT data FROM cloud_pdf_chunks WHERE report_id=? ORDER BY part', (record['id'],)).fetchall()
        finally: c.close()
        return b''.join(row[0] for row in parts) if parts else None

    def save_report(d):
        raw = str(d.get('base64', ''))
        if raw.startswith('data:'): raw = raw.split(',', 1)[-1]
        try: blob = base64.b64decode(raw, validate=True)
        except Exception: raise ValueError('PDF verisi geçersiz.')
        if not blob.startswith(b'%PDF-') or len(blob) > PDF_LIMIT:
            raise ValueError('Bulut sürümünde en fazla 2 MB PDF yükleyiniz.')
        with app['transaction']() as c:
            did = app['integer'](d.get('danisan_id'), 1)
            app['exists'](c, 'danisanlar', did, 'Danışan')
            tid = d.get('terapist_id') or None
            if tid: app['exists'](c, 'terapistler', tid, 'Terapist')
            name = app['_safe_pdf_name'](d.get('dosya_adi', 'rapor.pdf'))[:180]
            date = app['valid_date'](d.get('tarih') or app['date'].today().isoformat())
            rid = c.execute('INSERT INTO danisan_rapor_dosyalari(danisan_id,terapist_id,tarih,dosya_adi,dosya_yolu,boyut) VALUES(?,?,?,?,?,?)', (did, tid, date, name, 'cloud', len(blob))).lastrowid
            for part, start in enumerate(range(0, len(blob), 256 * 1024)):
                c.execute('INSERT INTO cloud_pdf_chunks VALUES(?,?,?)', (rid, part, blob[start:start + 256 * 1024]))
            return rid

    def delete_report(rid):
        with app['transaction']() as c:
            app['exists'](c, 'danisan_rapor_dosyalari', rid, 'PDF')
            c.execute('DELETE FROM cloud_pdf_chunks WHERE report_id=?', (rid,))
            c.execute('DELETE FROM danisan_rapor_dosyalari WHERE id=?', (rid,))
        return {'ok': True}

    def backup():
        c = db.connect()
        try: return export_backup(c)
        finally: c.close()

    def allow_attempt(key, limit, seconds):
        # Shared, atomic limits apply across all Vercel workers/restarts.
        window = int(time.time()) // seconds
        with app['transaction']() as c:
            c.execute('INSERT INTO cloud_rate_limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN window=excluded.window THEN count+1 ELSE 1 END,window=excluded.window', (key, window))
            count = c.execute('SELECT count FROM cloud_rate_limits WHERE key=?', (key,)).fetchone()[0]
        return count <= limit

    original_html = app['build_html']
    def cloud_html():
        return original_html().replace('v3.13.0', 'v3.14.0 Bulut').replace('Yedek indir', 'Yedekleme').replace('en çok 10 MB', 'en çok 2 MB').replace('f.size>10*1024*1024', 'f.size>2*1024*1024').replace('PDF en çok 10 MB olabilir.', 'PDF en çok 2 MB olabilir.').replace('Sürüm geçişinden önce otomatik yedek alınır.', 'Bulut tam yedeği bilgisayardaki yedekleme aracıyla alınır; kurulum rehberini izleyin.')
    app['build_html'] = cloud_html
    original = app['Handler']
    class CloudHandler(original):
        def _send(self, body, status=200, ctype='application/json; charset=utf-8', headers=None):
            headers = dict(headers or {})
            if 'Set-Cookie' in headers: headers['Set-Cookie'] += '; Secure'
            headers['Strict-Transport-Security'] = 'max-age=31536000'
            return super()._send(body, status, ctype, headers)
        def _ready(self):
            try:
                init_db()
                return True
            except Exception as error:
                # Never expose credentials or database details in public error responses.
                print('Cloud initialization failed:', type(error).__name__)
                self._send({'error': 'Bulut veritabanı başlatılamadı. TURSO_DATABASE_URL, TURSO_AUTH_TOKEN ve ARTE_ADMIN_PASSWORD ayarlarını kontrol edin.'}, 503)
                return False
        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == '/favicon.ico': return self._send(b'', 204, 'image/x-icon')
            if not self._ready(): return
            if path == '/api/backup':
                if not self._auth(): return self._send({'error': 'Oturum açınız.'}, 401)
                # Serverless downloads cannot support arbitrary backup sizes/duration.
                return self._send('<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bulut yedeği</title><body style="font:16px system-ui;max-width:750px;margin:40px auto;padding:20px"><h1>Bulut verilerinin yedeğini alma</h1><p>Veritabanı ve PDF raporlarını birlikte indirmek için bilgisayarınızda proje klasörünü açıp şu komutu çalıştırın:</p><pre style="white-space:pre-wrap">python scripts/cloud_admin.py backup yedek.zip</pre><p>Araç, Turso veritabanı adresini ve erişim anahtarını sorar. Erişim anahtarı ekranda gösterilmez. Her yedek için yeni bir dosya adı kullanın. Ayrıntılar indirdiğiniz paketin README dosyasında.</p><p><a href="/">Uygulamaya dön</a></p></body></html>', ctype='text/html; charset=utf-8')
            if path == '/api/mobile':
                if not self._auth(): return self._send({'error': 'Oturum açınız.'}, 401)
                return self._send({'enabled': True, 'cloud': True, 'urls': [], 'local_url': ''})
            return super().do_GET()
        def do_POST(self):
            if not self._ready(): return
            path = urllib.parse.urlparse(self.path).path
            if path == '/api/setup': return self._send({'error': 'Bulut parolası ilk kurulumda ortam değişkeninden belirlenir.'}, 403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length > 3 * 1024 * 1024: return self._send({'error': 'İstek en fazla 3 MB olabilir; PDF sınırı 2 MB.'}, 413)
                if path in ('/api/login', '/api/public/booking'):
                    origin = self.headers.get('Origin', '')
                    if self.headers.get('Sec-Fetch-Site') == 'cross-site' or (origin and urllib.parse.urlparse(origin).netloc != self.headers.get('Host', '')):
                        return self._send({'error': 'İstek kaynağı geçersiz.'}, 403)
                    if not allow_attempt(path, 30 if path == '/api/login' else 20, 300):
                        return self._send({'error': 'Çok fazla deneme. 5 dakika sonra tekrar deneyin.'}, 429)
                return super().do_POST()
            except Exception as error:
                print('Cloud request failed:', type(error).__name__)
                return self._send({'error': 'Veritabanına ulaşılamadı. İşlemin kaydını kontrol edip yeniden deneyin.'}, 503)

    app.update(init_db=init_db, read_report_blob=read_report,
               rapor_pdf_kaydet=save_report, rapor_pdf_sil=delete_report,
               backup_bytes=backup, Handler=CloudHandler, APP_VERSION='3.14.0-cloud')

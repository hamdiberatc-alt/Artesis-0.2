#!/usr/bin/env python3
"""Offline administration: backup, prepare a migration SQL file, reset password.
Secrets are read from the process environment or an interactive hidden prompt.
"""
import argparse
import base64
import getpass
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud import db
from cloud.runtime import SCHEMA, CLOUD_VERSION, export_backup


def credentials():
    if not os.getenv('TURSO_DATABASE_URL'):
        os.environ['TURSO_DATABASE_URL'] = input('Turso veritabanı adresi: ').strip()
    if not os.getenv('TURSO_AUTH_TOKEN'):
        os.environ['TURSO_AUTH_TOKEN'] = getpass.getpass('Turso erişim anahtarı (gizli): ')


def prepare_import(source, destination):
    """Migrate a COPY of a complete app ZIP backup, leaving the source untouched."""
    if destination.exists(): raise ValueError('Çıktı dosyası zaten var; farklı bir ad seçin.')
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with zipfile.ZipFile(source) as archive:
            if 'arteterapi.db' not in archive.namelist(): raise ValueError('Tam uygulama ZIP yedeği gerekli.')
            # Never extract caller-controlled archive paths.
            (folder/'arteterapi.db').write_bytes(archive.read('arteterapi.db'))
            reports = {}
            for name in archive.namelist():
                path = Path(name)
                if len(path.parts) == 2 and path.parts[0] == 'rapor_pdfler' and path.suffix == '.pdf' and path.stem.isdigit():
                    reports[int(path.stem)] = archive.read(name)
        old = {k:os.environ.get(k) for k in ('ARTE_CLOUD','VERCEL','ARTE_DB_PATH')}
        try:
            os.environ['ARTE_CLOUD']='0';os.environ.pop('VERCEL',None)
            os.environ['ARTE_DB_PATH']=str(folder/'arteterapi.db')
            app=runpy.run_path(str(ROOT/'app.py'));app['init_db']()
        finally:
            for k,v in old.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
        c=sqlite3.connect(folder/'arteterapi.db')
        try:
            c.executescript(SCHEMA)
            for rid, in c.execute('SELECT id FROM danisan_rapor_dosyalari').fetchall():
                blob=reports.get(rid)
                if blob is None:
                    parts=c.execute('SELECT data FROM cloud_pdf_chunks WHERE report_id=? ORDER BY part',(rid,)).fetchall()
                    if parts:blob=b''.join(p[0] for p in parts)
                if not blob or not blob.startswith(b'%PDF-'):raise ValueError(f'{rid} numaralı rapor yedekte eksik; aktarım durduruldu.')
                c.execute('DELETE FROM cloud_pdf_chunks WHERE report_id=?',(rid,))
                c.executemany('INSERT INTO cloud_pdf_chunks VALUES(?,?,?)',[(rid,i,blob[n:n+256*1024]) for i,n in enumerate(range(0,len(blob),256*1024))])
                c.execute("UPDATE danisan_rapor_dosyalari SET dosya_yolu='cloud' WHERE id=?",(rid,))
            password=getpass.getpass('Bulutta kullanılacak yeni yönetici parolası (en az 16 karakter): ')
            if len(password)<16:raise ValueError('Parola en az 16 karakter olmalı.')
            if password!=getpass.getpass('Parolayı tekrar girin: '):raise ValueError('Parolalar eşleşmedi.')
            c.execute("INSERT OR REPLACE INTO ayarlar VALUES('admin_password_hash',?)",(app['_password_hash'](password),))
            c.execute('DELETE FROM auth_sessions');c.execute('DELETE FROM cloud_rate_limits')
            c.execute("INSERT OR REPLACE INTO cloud_meta VALUES('version',?)",(CLOUD_VERSION,));c.commit()
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Veritabanı bütünlük kontrolü başarısız.')
            if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Veritabanında eksik bağlantılı kayıtlar var; aktarım durduruldu.')
            with destination.open('x',encoding='utf-8') as target:
                target.write('PRAGMA foreign_keys=OFF;\n')
                for line in c.iterdump():target.write(line+'\n')
        finally:c.close()
    print('Aktarım dosyası hazır. Bu dosya kişisel kayıt içerir; GitHub’a yüklemeyin.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    p=sub.add_parser('backup');p.add_argument('destination',type=Path)
    p=sub.add_parser('prepare-import');p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    sub.add_parser('reset-password')
    args=parser.parse_args()
    if args.action=='prepare-import':return prepare_import(args.source,args.destination)
    if args.action=='backup' and args.destination.exists():raise ValueError('Dosya zaten var; farklı bir yedek adı seçin.')
    credentials()
    c=db.connect()
    try:
        if args.action=='backup':
            content=export_backup(c)
            with args.destination.open('xb') as f:f.write(content)
            print('Veritabanı ve PDF raporları birlikte yedeklendi:',args.destination)
        else:
            password=getpass.getpass('Yeni parola (en az 16 karakter): ')
            if len(password)<16:raise ValueError('Parola en az 16 karakter olmalı.')
            if password!=getpass.getpass('Tekrar: '):raise ValueError('Parolalar eşleşmedi.')
            import hashlib,secrets
            salt=secrets.token_hex(16)
            hashed=salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),240000).hex()
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE ayarlar SET deger=? WHERE anahtar='admin_password_hash'",(hashed,))
            c.execute('DELETE FROM auth_sessions');c.commit()
            print('Parola değiştirildi; açık oturumlar sonlandırıldı.')
    except Exception:
        c.rollback();raise
    finally:c.close()

if __name__=='__main__':
    try:main()
    except Exception as error:
        print('İşlem tamamlanamadı:',str(error),file=sys.stderr)
        sys.exit(1)

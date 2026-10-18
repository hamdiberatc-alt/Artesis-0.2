"""Monthly completed-session compensation, independent of client receipts.

Settings live in the existing ayarlar table so local and cloud installations
share the same implementation without a destructive schema migration.
"""
import calendar
import csv
import io
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

KINDS = ('bireysel', 'grup2', 'grup3')
PREFIX = 'maas_v1:'


def month_bounds(month):
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('Ay YYYY-AA biçiminde olmalıdır.')
    try:
        first = date.fromisoformat(month + '-01')
    except ValueError:
        raise ValueError('Geçerli bir ay seçiniz.')
    return first.isoformat(), first.replace(day=calendar.monthrange(first.year, first.month)[1]).isoformat()


def amount(value):
    try:
        value = Decimal(str(value).strip().replace(',', '.'))
        if not value.is_finite() or not 0 <= value <= 1000000000:
            raise ValueError()
        return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (ValueError, InvalidOperation):
        raise ValueError('Seans ücreti 0 ile 1 milyar arasında olmalıdır (örnek: 250,50).')


def save_rates(app, data):
    month = data.get('ay')
    month_bounds(month)
    tid = app['integer'](data.get('terapist_id'), 1)
    rates = {kind: str(amount(data.get(kind, ''))) for kind in KINDS}
    mode = data.get('grup_sayimi', 'ders')
    if mode not in ('ders', 'katilim'):
        raise ValueError('Grup sayım yöntemi geçersiz.')
    record = {'ucretler': rates, 'grup_sayimi': mode}
    with app['transaction']() as conn:
        app['exists'](conn, 'terapistler', tid, 'Terapist')
        conn.execute('INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES(?,?)',
                     (PREFIX + month + ':' + str(tid), json.dumps(record)))
    return {'ay': month, 'terapist_id': tid}


def report(app, month, therapist_id=None):
    start, end = month_bounds(month)
    tid = app['integer'](therapist_id, 1) if therapist_id else None
    today = app['date'].today().isoformat()
    conn = app['get_db']()
    try:
        therapists = app['q'](conn, 'SELECT id,ad,soyad,aktif FROM terapistler' +
                              (' WHERE id=?' if tid else '') + ' ORDER BY ad,soyad,id', [tid] if tid else [])
        if tid and not therapists:
            raise ValueError('Terapist bulunamadı.')
        settings = {row['anahtar']: json.loads(row['deger']) for row in app['q'](
            conn, 'SELECT anahtar,deger FROM ayarlar WHERE anahtar LIKE ?', (PREFIX + month + ':%',))}
        sessions = app['q'](conn, '''SELECT s.*,d.ad||' '||d.soyad danisan_adi,
            h.alan_adi hizmet_adi,p.grup_id FROM seanslar s
            LEFT JOIN danisanlar d ON d.id=s.danisan_id
            LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
            LEFT JOIN pilates_paketleri p ON p.id=s.paket_id
            WHERE s.tarih BETWEEN ? AND ?''' + (' AND s.terapist_id=?' if tid else '') +
            ' ORDER BY s.tarih,s.saat,s.id', [start, end] + ([tid] if tid else []))
    finally:
        conn.close()
    rows, details, warnings = [], [], []
    excluded = {'gelmedi': 0, 'gelecek': 0, 'gecersiz': 0}
    by_therapist = {}
    for session in sessions:
        try:
            valid = date.fromisoformat(session['tarih']).isoformat() == session['tarih']
        except (TypeError, ValueError):
            valid = False
        if not valid:
            excluded['gecersiz'] += 1
        elif session['tarih'] > today:
            excluded['gelecek'] += 1
        elif session['gelmedi']:
            excluded['gelmedi'] += 1
        else:
            by_therapist.setdefault(session['terapist_id'], []).append(session)
    for therapist in therapists:
        ident = therapist['id']
        setting = settings.get(PREFIX + month + ':' + str(ident))
        mode = setting['grup_sayimi'] if setting else 'ders'
        rates = {kind: amount(setting['ucretler'][kind]) for kind in KINDS} if setting else None
        name = (therapist['ad'] + ' ' + (therapist['soyad'] or '')).strip()
        grouped = {}
        for session in by_therapist.get(ident, []):
            kind = session['grup_turu']
            if kind not in KINDS:
                warnings.append('Seans #' + str(session['id']) + ': grup türü tanınmıyor; hesaba katılmadı.')
                excluded['gecersiz'] += 1
                continue
            # Only a real group identity can safely combine participant records.
            # Unlinked legacy records stay separate and are flagged for review.
            key = ('record', session['id'])
            if mode == 'ders' and kind != 'bireysel':
                if session['grup_id'] and session['saat']:
                    key = ('group', session['grup_id'], session['tarih'], session['saat'],
                           session['hizmet_id'], session['oda_id'], session['sure_dk'], kind)
                else:
                    warnings.append('Seans #' + str(session['id']) + ': grup bağlantısı veya saat eksik; ayrı sayıldı. Kontrol edin.')
            grouped.setdefault(key, []).append(session)
        counts = dict.fromkeys(KINDS, 0)
        total = Decimal('0.00')
        for members in grouped.values():
            first = members[0]
            kind = first['grup_turu']
            counts[kind] += 1
            rate = rates[kind] if rates else None
            if rate is not None:
                total += rate
            details.append({'terapist_id': ident, 'terapist_adi': name, 'tarih': first['tarih'],
                            'saat': first['saat'], 'grup_turu': kind, 'hizmet': first['hizmet_adi'] or '',
                            'katilimci': len(members), 'hediye': sum(bool(m['hediye']) for m in members),
                            'seans_ids': [m['id'] for m in members],
                            'danisanlar': ', '.join(m['danisan_adi'] or '' for m in members),
                            'tutar': float(rate) if rate is not None else None})
        rows.append({'terapist_id': ident, 'ad': name, 'aktif': therapist['aktif'],
                     'ayarlanmis': setting is not None, 'grup_sayimi': mode,
                     'ucretler': {k: float(v) for k, v in rates.items()} if rates else dict.fromkeys(KINDS, None),
                     'adetler': counts, 'seans': sum(counts.values()),
                     'tutar': float(total) if rates else None})
    missing = sum(r['seans'] for r in rows if not r['ayarlanmis'])
    return {'ay': month, 'baslangic': start, 'bitis': end, 'terapistler': rows,
            'seanslar': sorted(details, key=lambda r: (r['tarih'], r['saat'], r['terapist_id'])),
            'haric': excluded, 'uyarilar': warnings, 'eksik_ucretli_seans': missing,
            'hesaplanan_toplam': float(sum((Decimal(str(r['tutar'])) for r in rows if r['tutar'] is not None), Decimal(0))),
            'tamamlandi': missing == 0 and not warnings and not excluded['gecersiz']}


def csv_text(data):
    out = io.StringIO(newline='')
    writer = csv.writer(out, delimiter=';')
    def safe(value):
        text = str(value if value is not None else 'Ücret eksik')
        return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text
    writer.writerow(['Ay', 'Tarih', 'Saat', 'Terapist', 'Tür', 'Katılımcı', 'Hediye katılım', 'Seans kayıtları', 'Tutar (TL)'])
    for row in data['seanslar']:
        writer.writerow([safe(x) for x in [data['ay'], row['tarih'], row['saat'], row['terapist_adi'],
                         row['grup_turu'], row['katilimci'], row['hediye'], ','.join(map(str, row['seans_ids'])),
                         format(Decimal(str(row['tutar'])), '.2f').replace('.', ',') if row['tutar'] is not None else None]])
    writer.writerow(['Hesaplanan toplam (TL)', str(data['hesaplanan_toplam']).replace('.', ',')])
    writer.writerow(['Durum', 'Tamamlandı' if data['tamamlandi'] else 'Eksik ücret / kontrol gerekli'])
    for warning in data['uyarilar']:
        writer.writerow(['Kontrol', safe(warning)])
    return '\ufeff' + out.getvalue()

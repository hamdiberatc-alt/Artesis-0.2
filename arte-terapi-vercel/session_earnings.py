"""Monthly attended-session list and therapist earnings by session order."""

import csv
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from payroll import month_bounds

RATE_PREFIX = 'seans_kazanc_orani_v1:'
DEFAULT_RATES = (Decimal('0.40'), Decimal('0.50'))


def _percentage(value):
    try:
        percent = Decimal(str(value).strip().replace(',', '.'))
        if not percent.is_finite() or not 0 <= percent <= 100:
            raise ValueError()
        return (percent / 100).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError('Kazanç oranı 0 ile 100 arasında yüzde olmalıdır (örnek: 45,5).')


def save_rates(app, data):
    month = data.get('ay')
    month_bounds(month)
    tid = app['integer'](data.get('terapist_id'), 1)
    first = _percentage(data.get('ilk_80_oran'))
    later = _percentage(data.get('sonraki_oran'))
    with app['transaction']() as conn:
        app['exists'](conn, 'terapistler', tid, 'Terapist')
        conn.execute('INSERT OR REPLACE INTO ayarlar(anahtar,deger) VALUES(?,?)',
                     (RATE_PREFIX + str(tid) + ':' + month,
                      json.dumps({'ilk_80':str(first),'sonraki':str(later)})))
    return {'ay':month,'terapist_id':tid,'ilk_80_oran':float(first),
            'sonraki_oran':float(later)}


def _money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def report(app, month, therapist_id=None):
    start, end = month_bounds(month)
    tid = app['integer'](therapist_id, 1) if therapist_id else None
    conn = app['get_db']()
    try:
        therapists = app['q'](conn, 'SELECT id,ad,soyad FROM terapistler' +
                              (' WHERE id=?' if tid else '') + ' ORDER BY ad,soyad,id',
                              [tid] if tid else [])
        if tid and not therapists:
            raise ValueError('Terapist bulunamadı.')
        rate_rows = app['q'](conn,'SELECT anahtar,deger FROM ayarlar WHERE anahtar LIKE ?',
                             (RATE_PREFIX + '%',))
        sessions = app['q'](conn, '''SELECT s.id,s.tarih,s.saat,s.terapist_id,s.tip,s.hediye,
            s.paket_id,s.ucret,s.grup_turu,s.hizmet_id,s.oda_id,s.sure_dk,p.grup_id,
            source.ucret kaynak_ucreti,
            d.ad||' '||d.soyad danisan_adi,h.alan_adi hizmet_adi
            FROM seanslar s
            LEFT JOIN seanslar source ON source.id=s.telafi_kaynak_id
            LEFT JOIN pilates_paketleri p ON p.id=s.paket_id
            LEFT JOIN danisanlar d ON d.id=s.danisan_id
            LEFT JOIN hizmet_alanlari h ON h.id=s.hizmet_id
            WHERE s.tarih BETWEEN ? AND ? AND s.tarih<=? AND s.gelmedi=0''' +
            (' AND s.terapist_id=?' if tid else '') +
            ' ORDER BY s.terapist_id,s.tarih,s.saat,s.id',
            [start,end,app['date'].today().isoformat()] + ([tid] if tid else []))
    finally:
        conn.close()

    grouped = {}
    for session in sessions:
        try:
            if date.fromisoformat(session['tarih']).isoformat() != session['tarih']:
                continue
        except (TypeError, ValueError):
            continue
        grouped.setdefault(session['terapist_id'], []).append(session)

    configured = {}
    for row in rate_rows:
        key = row['anahtar'][len(RATE_PREFIX):].split(':')
        if len(key) != 2 or not key[0].isdigit() or key[1] > month:
            continue
        ident = int(key[0])
        if ident not in configured or key[1] > configured[ident][0]:
            values = json.loads(row['deger'])
            configured[ident] = (key[1],Decimal(values['ilk_80']),Decimal(values['sonraki']))
    summaries, first_eighty, later = [], [], []
    for therapist in therapists:
        ident = therapist['id']
        name = (therapist['ad'] + ' ' + (therapist['soyad'] or '')).strip()
        active = configured.get(ident)
        first_rate, later_rate = (active[1],active[2]) if active else DEFAULT_RATES
        initial_total = later_total = Decimal('0.00')
        units = {}
        for session in grouped.get(ident, []):
            key = ('record',session['id'])
            if session['grup_turu'] in ('grup2','grup3') and session['saat']:
                key = ('group',session['grup_id'],session['tarih'],session['saat'],session['hizmet_id'],
                       session['oda_id'],session['sure_dk'],session['grup_turu'])
            units.setdefault(key,[]).append(session)
        for index, members in enumerate(units.values(), 1):
            first = members[0]
            rate = first_rate if index <= 80 else later_rate
            # Older completed makeups stored the package fee on the missed source.
            gross = sum((_money(s['kaynak_ucreti'] if s['tip']=='telafi' and
                          not s['ucret'] and s['kaynak_ucreti'] is not None
                          else s['ucret']) for s in members),Decimal('0.00'))
            earning = (gross * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            row = {'id':first['id'],'seans_ids':[s['id'] for s in members],
                   'terapist_id':ident,'terapist_adi':name,
                   'sira':index,'tarih':first['tarih'],'saat':first['saat'] or '',
                   'danisan_adi':', '.join(s['danisan_adi'] or '' for s in members),
                   'hizmet_adi':first['hizmet_adi'] or '',
                   'tip':first['tip'],'grup_turu':first['grup_turu'],
                   'katilimci':len(members),'hediye':sum(bool(s['hediye']) for s in members),
                   'paket_id':first['paket_id'],'seans_ucreti':float(gross),
                   'oran':float(rate),'terapist_kazanci':float(earning)}
            if index <= 80:
                first_eighty.append(row)
                initial_total += earning
            else:
                later.append(row)
                later_total += earning
        summaries.append({'terapist_id':ident,'terapist_adi':name,
                          'ilk_80_oran':float(first_rate),'sonraki_oran':float(later_rate),
                          'oran_baslangic':active[0] if active else None,
                          'ilk_80_adet':min(80,len(units)),
                          'sonraki_adet':max(0,len(units)-80),
                          'ilk_80_kazanc':float(initial_total),
                          'sonraki_kazanc':float(later_total),
                          'toplam_kazanc':float(initial_total+later_total)})
    return {'ay':month,'terapistler':summaries,'ilk_80':first_eighty,'sonraki':later,
            'toplam_seans':len(first_eighty)+len(later),
            'toplam_kazanc':float(sum((Decimal(str(r['toplam_kazanc'])) for r in summaries),Decimal('0.00')))}


def csv_text(data):
    output=io.StringIO(newline='')
    writer=csv.writer(output,delimiter=';')
    def safe(value):
        value=str(value if value is not None else '')
        return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r','\n')) else value
    writer.writerow(['Ay','Terapist','Sıra','Tarih','Saat','Danışan','Hizmet','Seans türü',
                     'Katılımcı','Seans kayıtları',
                     'Seans ücreti (TL)','Oran','Terapist kazancı (TL)'])
    for row in data['ilk_80']+data['sonraki']:
        writer.writerow([safe(x) for x in [data['ay'],row['terapist_adi'],row['sira'],
                         row['tarih'],row['saat'],row['danisan_adi'],row['hizmet_adi'],
                         row['tip'],row['katilimci'],','.join(map(str,row['seans_ids'])),
                         f"{row['seans_ucreti']:.2f}".replace('.',','),
                         format((Decimal(str(row['oran']))*100).normalize(),'f').replace('.',',')+'%',
                         f"{row['terapist_kazanci']:.2f}".replace('.',',')]])
    return '\ufeff'+output.getvalue()

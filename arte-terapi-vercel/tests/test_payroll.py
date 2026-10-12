import json
import unittest
from datetime import date, timedelta
import test_core
import payroll


class PayrollTest(unittest.TestCase):
    setUp = test_core.AppTest.setUp
    tearDown = test_core.AppTest.tearDown
    call = test_core.AppTest.call
    rows = test_core.AppTest.rows
    sess = test_core.AppTest.sess
    package = test_core.AppTest.package
    http = test_core.AppTest.http

    def rates(self, **changes):
        data = dict(ay=self.today[:7], terapist_id=1, bireysel='250,55', grup2=400, grup3=500, grup_sayimi='ders')
        data.update(changes)
        return payroll.save_rates(self.m, data)

    def report(self, tid=None, month=None):
        return payroll.report(self.m, month or self.today[:7], tid)

    def test_completed_only_including_gift_not_absence_or_plans(self):
        self.rates()
        self.sess()
        self.sess(saat='10:30', hediye=1)
        self.sess(saat='11:30', gelmedi=1, hak_dustu=1)
        self.call('haftalik_program_kaydet', dict(danisan_id=self.b, terapist_id=1, hizmet_id=1,
                  gun_index=date.today().weekday(), saat='12:30', baslangic=self.today))
        data = self.report(1)
        self.assertEqual(data['hesaplanan_toplam'], 501.10)
        self.assertEqual(data['terapistler'][0]['seans'], 2)
        self.assertEqual(data['haric']['gelmedi'], 1)
        self.assertEqual(sum(r['hediye'] for r in data['seanslar']), 1)

    def test_missing_rate_is_not_silently_zero(self):
        self.sess()
        data = self.report(1)
        self.assertEqual(data['eksik_ucretli_seans'], 1)
        self.assertFalse(data['tamamlandi'])
        self.assertIsNone(data['terapistler'][0]['tutar'])
        self.rates(bireysel=0)
        self.assertTrue(self.report(1)['tamamlandi'])

    def test_month_and_therapist_isolation_and_inactive_history(self):
        self.rates()
        self.rates(ay='2025-01', bireysel=99)
        self.sess()
        self.sess(terapist_id=2, hizmet_id=4)
        with self.call('transaction') as conn:
            conn.execute('UPDATE terapistler SET aktif=0 WHERE id=1')
        self.assertEqual(self.report(1)['hesaplanan_toplam'], 250.55)
        self.assertEqual(self.report(1, '2025-01')['terapistler'][0]['ucretler']['bireysel'], 99)
        self.assertEqual(self.report(2)['eksik_ucretli_seans'], 1)
        self.assertEqual(self.report(1)['terapistler'][0]['aktif'], 0)

    def group_sessions(self):
        with self.call('transaction') as conn:
            conn.execute("INSERT INTO pilates_gruplari(id,ad,kapasite) VALUES(90,'Test',2)")
        pids=[]
        for did in (self.a, self.b):
            pid=self.call('paket_kaydet', dict(danisan_id=did, ad='Test', fiyat=1000, seans_sayisi=8,
                hediye_seans=1, baslangic=self.today, bitis=(date.today()+timedelta(days=60)).isoformat(),grup_turu='grup2'))
            with self.call('transaction') as conn:
                conn.execute('UPDATE pilates_paketleri SET grup_id=90 WHERE id=?',(pid,))
            pids.append(pid)
            self.sess(danisan_id=did, terapist_id=3, hizmet_id=11, paket_id=pid, saat='09:30')
        self.rates(terapist_id=3)
        return pids

    def test_group_once_and_per_participant_option(self):
        self.group_sessions()
        data=self.report(3)
        self.assertEqual(data['hesaplanan_toplam'],400)
        self.assertEqual(data['seanslar'][0]['katilimci'],2)
        self.rates(terapist_id=3,grup_sayimi='katilim')
        self.assertEqual(self.report(3)['hesaplanan_toplam'],800)

    def test_group_different_slots_and_partial_attendance(self):
        pids=self.group_sessions()
        self.sess(terapist_id=3,hizmet_id=11,paket_id=pids[0],saat='11:30')
        with self.call('transaction') as conn:
            conn.execute('UPDATE seanslar SET gelmedi=1 WHERE danisan_id=?',(self.b,))
        data=self.report(3)
        self.assertEqual(data['hesaplanan_toplam'],800)
        self.assertEqual(data['haric']['gelmedi'],1)

    def test_legacy_unlinked_groups_are_flagged(self):
        self.sess(grup_turu='grup2')
        self.rates()
        data=self.report(1)
        self.assertEqual(data['hesaplanan_toplam'],400)
        self.assertEqual(len(data['uyarilar']),1)
        self.assertFalse(data['tamamlandi'])

    def test_future_rows_are_excluded_even_if_marked_attended(self):
        sid=self.sess()
        future=(date.today()+timedelta(days=32)).isoformat()
        with self.call('transaction') as conn:
            conn.execute('UPDATE seanslar SET tarih=? WHERE id=?',(future,sid))
        self.rates(ay=future[:7])
        data=self.report(1,future[:7])
        self.assertEqual(data['hesaplanan_toplam'],0)
        self.assertEqual(data['haric']['gelecek'],1)

    def test_invalid_rates_and_months_do_not_overwrite_settings(self):
        self.rates()
        for value in ('', '-1', 'NaN', 'Infinity', '1000000001', 'x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.rates(bireysel=value)
        for month in ('2026-00', '2026-13', '2026-1', 'x', None):
            with self.subTest(month=month), self.assertRaises(ValueError):
                payroll.report(self.m,month)
        with self.assertRaises(ValueError):self.rates(terapist_id=9999)
        with self.assertRaises(ValueError):self.rates(grup_sayimi='invalid')
        self.assertEqual(self.report(1)['terapistler'][0]['ucretler']['bireysel'],250.55)

    def test_decimal_rounding_and_csv_formula_escaping(self):
        self.rates(bireysel='0.105')
        for hour in (9,10,11):self.sess(saat=f'{hour:02d}:30')
        with self.call('transaction') as conn:
            conn.execute("UPDATE terapistler SET ad='=1+1',soyad='' WHERE id=1")
        data=self.report(1)
        self.assertEqual(data['hesaplanan_toplam'],0.33)
        text=payroll.csv_text(data)
        self.assertTrue(text.startswith('\ufeff'))
        self.assertIn("'=1+1",text)
        self.assertIn('0,11',text)

    def test_payroll_http_auth_csrf_and_export(self):
        self.assertEqual(self.http('/api/payroll?ay='+self.today[:7])[0],401)
        self.assertEqual(self.http('/api/payroll.csv?ay='+self.today[:7])[0],401)
        status,body,headers=self.http('/api/setup',{'password':'testpass123'})
        self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf']
        data=dict(ay=self.today[:7],terapist_id=1,bireysel=100,grup2=200,grup3=300)
        self.assertEqual(self.http('/api/payroll/rates',data,cookie)[0],403)
        self.assertEqual(self.http('/api/payroll/rates',data,cookie,csrf)[0],200)
        self.sess()
        status,body,_=self.http('/api/payroll?ay='+self.today[:7],cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['hesaplanan_toplam'],100)
        status,body,headers=self.http('/api/payroll.csv?ay='+self.today[:7],cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn('text/csv',headers['Content-Type'])
        self.assertIn('100,00',body.decode('utf-8-sig'))

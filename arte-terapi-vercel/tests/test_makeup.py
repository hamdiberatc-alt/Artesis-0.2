from datetime import date, timedelta

from test_core import AppTest


class MakeupTest(AppTest):
    def pilates(self, package_id, time, **extra):
        return self.sess(terapist_id=3, hizmet_id=11, paket_id=package_id, saat=time, **extra)

    def test_cancel_choice_makeup_and_extra_session(self):
        package_id = self.package(n=4, gift=0, price=1200)
        cancelled = self.pilates(package_id, '09:00', gelmedi=1,
                                  gelmedi_nedeni='İptal edildi', hak_dustu=1)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 3)
        cancelled_row=self.call('seans_detay',cancelled)
        self.assertEqual(cancelled_row['terapist_payi'],0)
        self.assertEqual(cancelled_row['isletme_payi'],cancelled_row['ucret'])
        pending = self.pilates(package_id, '10:00', gelmedi=1,
                                gelmedi_nedeni='Telafi bekliyor', hak_dustu=0)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 3)
        makeup = self.pilates(package_id, '11:00', tip='telafi', telafi_kaynak_id=pending)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        self.assertEqual(self.call('seans_detay', makeup)['hak_dustu'], 1)
        self.assertEqual(self.call('paket_seanslari', package_id)[-1]['telafi_kaynak_id'], pending)
        self.assertEqual(next(s for s in self.call('paket_seanslari', package_id) if s['id'] == pending)['telafi_yapildi'], 1)
        week = self.call('seans_haftalik_programi', self.today)
        self.assertEqual(next(s for s in week['items'] if s.get('id') == pending)['telafi_yapildi'], 1)
        with self.assertRaises(ValueError):
            self.pilates(package_id, '12:00', tip='telafi', telafi_kaynak_id=pending)
        with self.assertRaises(ValueError):
            self.call('seans_sil', pending)
        self.pilates(package_id, '13:00')
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.call('seans_sil', makeup)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        self.assertEqual(self.call('seans_detay', cancelled)['gelmedi'], 1)

    def test_makeup_can_be_scheduled_only_within_package_period(self):
        package_id = self.package(n=2, gift=0, price=600)
        pending = self.pilates(package_id, '10:00', gelmedi=1,
                                gelmedi_nedeni='Telafi bekliyor', hak_dustu=0)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.call('telafi_planla', {'id': pending, 'tarih': tomorrow, 'saat': '11:00'})
        planned = [r for r in self.call('seans_haftalik_programi', tomorrow)['items']
                   if r.get('kaynak') == 'telafi_planli']
        self.assertEqual(len(planned), 1)
        self.assertEqual((planned[0]['telafi_kaynak_id'], planned[0]['tarih']), (pending, tomorrow))
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        with self.assertRaises(ValueError):
            self.call('telafi_planla', {'id': pending, 'tarih': (date.today()+timedelta(days=61)).isoformat(), 'saat': '11:00'})
        self.call('telafi_planla', {'id': pending, 'islem': 'yeniden'})
        self.assertFalse([r for r in self.call('seans_haftalik_programi', tomorrow)['items']
                          if r.get('kaynak') == 'telafi_planli'])
        self.call('telafi_planla', {'id': pending, 'tarih': self.today, 'saat': '12:00'})
        self.pilates(package_id, '12:00', tip='telafi', telafi_kaynak_id=pending)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.assertFalse([r for r in self.call('seans_haftalik_programi', self.today)['items']
                          if r.get('kaynak') == 'telafi_planli'])

    def test_burned_session_uses_right_without_counting_attendance(self):
        package_id = self.package(n=2, gift=0, price=600)
        self.pilates(package_id, '09:00', gelmedi=1,
                     gelmedi_nedeni='Gelmedi, hak yandı', hak_dustu=1)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.assertEqual(self.call('danisan_detay', self.a)['toplam_seans'], 0)
        self.assertEqual(self.call('gelir_raporu', self.today, self.today)['toplam']['gelen'], 0)
        self.assertEqual(self.call('gelir_raporu', self.today, self.today)['toplam']['terapist_payi'], 0)

    def test_planned_makeup_cancel_consumes_right(self):
        package_id = self.package(n=2, gift=0, price=600)
        pending = self.pilates(package_id, '10:00', gelmedi=1,
                               gelmedi_nedeni='Telafi bekliyor', hak_dustu=0)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        self.call('telafi_planla', {'id': pending, 'tarih': self.today, 'saat': '11:00'})
        self.call('telafi_planla', {'id': pending, 'islem': 'iptal'})
        row = self.call('seans_detay', pending)
        self.assertEqual((row['gelmedi_nedeni'], row['hak_dustu'], row['terapist_payi']), ('İptal edildi', 1, 0))
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.assertEqual(row['telafi_plan_tarihi'], '')

    def test_existing_completed_makeup_remains_one_consumed_right(self):
        package_id = self.package(n=2, gift=0, price=600)
        pending = self.pilates(package_id, '10:00', gelmedi=1,
                               gelmedi_nedeni='Telafi bekliyor', hak_dustu=1)
        makeup = self.pilates(package_id, '11:00', tip='telafi', telafi_kaynak_id=pending)
        self.assertEqual(self.call('seans_detay', makeup)['hak_dustu'], 0)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)

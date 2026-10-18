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
        pending = self.pilates(package_id, '10:00', gelmedi=1,
                                gelmedi_nedeni='Telafi bekliyor', hak_dustu=0)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 3)
        makeup = self.pilates(package_id, '11:00', tip='telafi', telafi_kaynak_id=pending)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        self.assertEqual(self.call('paket_seanslari', package_id)[-1]['telafi_kaynak_id'], pending)
        with self.assertRaises(ValueError):
            self.pilates(package_id, '12:00', tip='telafi', telafi_kaynak_id=pending)
        with self.assertRaises(ValueError):
            self.call('seans_sil', pending)
        self.pilates(package_id, '13:00')
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.call('seans_sil', makeup)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 2)
        self.assertEqual(self.call('seans_detay', cancelled)['gelmedi'], 1)

    def test_burned_session_uses_right_without_counting_attendance(self):
        package_id = self.package(n=2, gift=0, price=600)
        self.pilates(package_id, '09:00', gelmedi=1,
                     gelmedi_nedeni='Gelmedi, hak yandı', hak_dustu=1)
        self.assertEqual(self.call('paketler_listesi')[0]['kalan'], 1)
        self.assertEqual(self.call('danisan_detay', self.a)['toplam_seans'], 0)
        self.assertEqual(self.call('gelir_raporu', self.today, self.today)['toplam']['gelen'], 0)
        self.assertEqual(self.call('gelir_raporu', self.today, self.today)['toplam']['terapist_payi'], 0)

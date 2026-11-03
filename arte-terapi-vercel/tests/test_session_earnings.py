import json
import unittest
from datetime import date, timedelta

import session_earnings
from test_core import AppTest


class SessionEarningsTest(unittest.TestCase):
    setUp=AppTest.setUp
    tearDown=AppTest.tearDown
    call=AppTest.call
    sess=AppTest.sess
    package=AppTest.package
    http=AppTest.http

    def report(self, therapist=None):
        return session_earnings.report(self.m,self.today[:7],therapist)

    def test_threshold_resets_for_each_therapist_and_ignores_absence(self):
        for index in range(82):
            minute=9*60+index*5
            self.sess(saat=f'{minute//60:02d}:{minute%60:02d}',sure_dk=5)
        self.sess(saat='16:00',gelmedi=1,gelmedi_nedeni='İptal edildi',hak_dustu=1)
        self.sess(terapist_id=2,hizmet_id=4,saat='09:00')
        data=self.report()
        first=[r for r in data['ilk_80'] if r['terapist_id']==1]
        later=[r for r in data['sonraki'] if r['terapist_id']==1]
        other=[r for r in data['ilk_80'] if r['terapist_id']==2]
        self.assertEqual((len(first),len(later),len(other)),(80,2,1))
        self.assertEqual((first[-1]['sira'],later[0]['sira'],later[0]['oran']),(80,81,0.5))
        self.assertEqual(data['toplam_seans'],83)
        self.assertEqual(sum(r['terapist_kazanci'] for r in first),80*1200)
        self.assertEqual(sum(r['terapist_kazanci'] for r in later),2*1500)
        self.assertEqual(self.report(1)['toplam_seans'],82)
        self.assertEqual(len(self.report(2)['sonraki']),0)
        previous_month=(date.today().replace(day=1)-timedelta(days=1)).isoformat()
        self.sess(tarih=previous_month,saat='08:00')
        previous=session_earnings.report(self.m,previous_month[:7],1)
        self.assertEqual((previous['toplam_seans'],previous['ilk_80'][0]['oran']),(1,0.4))

    def test_makeup_counts_when_completed_and_gift_has_zero_fee(self):
        package_id=self.package(n=2,gift=1,price=600)
        pending=self.sess(terapist_id=3,hizmet_id=11,paket_id=package_id,
                          saat='09:00',gelmedi=1,gelmedi_nedeni='Telafi bekliyor',hak_dustu=0)
        self.assertEqual(self.report(3)['toplam_seans'],0)
        self.sess(terapist_id=3,hizmet_id=11,paket_id=package_id,
                  saat='10:00',tip='telafi',telafi_kaynak_id=pending)
        self.sess(terapist_id=3,hizmet_id=11,paket_id=package_id,
                  saat='11:00',hediye=1)
        data=self.report(3)
        self.assertEqual(data['toplam_seans'],2)
        self.assertEqual([r['seans_ucreti'] for r in data['ilk_80']],[300,0])
        self.assertEqual(data['toplam_kazanc'],120)

    def test_legacy_completed_makeup_uses_source_fee_and_csv_is_safe(self):
        package_id=self.package(n=2,gift=0,price=600)
        pending=self.sess(terapist_id=3,hizmet_id=11,paket_id=package_id,
                          saat='09:00',gelmedi=1,gelmedi_nedeni='Telafi bekliyor',hak_dustu=1)
        self.sess(terapist_id=3,hizmet_id=11,paket_id=package_id,
                  saat='10:00',tip='telafi',telafi_kaynak_id=pending)
        with self.call('transaction') as c:
            c.execute("UPDATE terapistler SET ad='=HESAPLA()' WHERE id=3")
        data=self.report(3)
        self.assertEqual(data['toplam_kazanc'],120)
        self.assertIn("'=HESAPLA()",session_earnings.csv_text(data))

    def test_group_lesson_is_one_session_with_attendee_fees_combined(self):
        end=(date.today()+timedelta(days=30)).isoformat()
        packages=[]
        for did in (self.a,self.b):
            packages.append(self.call('paket_kaydet',{'danisan_id':did,'ad':'Grup',
                'fiyat':600,'seans_sayisi':2,'hediye_seans':0,'grup_turu':'grup2',
                'baslangic':self.today,'bitis':end}))
        for did,pid in zip((self.a,self.b),packages):
            self.sess(danisan_id=did,terapist_id=3,hizmet_id=11,paket_id=pid,saat='09:00')
        self.sess(danisan_id=self.a,terapist_id=3,hizmet_id=11,paket_id=packages[0],saat='10:00')
        self.sess(danisan_id=self.b,terapist_id=3,hizmet_id=11,paket_id=packages[1],
                  saat='10:00',gelmedi=1,gelmedi_nedeni='İptal edildi',hak_dustu=1)
        data=self.report(3)
        self.assertEqual(data['toplam_seans'],2)
        self.assertEqual([r['katilimci'] for r in data['ilk_80']],[2,1])
        self.assertEqual([r['seans_ucreti'] for r in data['ilk_80']],[600,300])
        self.assertEqual(data['toplam_kazanc'],360)

    def test_month_validation(self):
        with self.assertRaises(ValueError):session_earnings.report(self.m,'2026-13')
        with self.assertRaises(ValueError):session_earnings.report(self.m,self.today[:7],99999)

    def test_private_report_and_csv(self):
        month=self.today[:7]
        self.assertEqual(self.http('/api/session-earnings?ay='+month)[0],401)
        status,_,headers=self.http('/api/setup',{'password':'testpass123'})
        self.assertEqual(status,200)
        cookie=headers['Set-Cookie'].split(';')[0]
        self.sess()
        status,body,_=self.http('/api/session-earnings?ay='+month,cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['toplam_seans'],1)
        status,body,headers=self.http('/api/session-earnings.csv?ay='+month,cookie=cookie)
        self.assertEqual(status,200)
        self.assertIn('text/csv',headers['Content-Type'])
        self.assertIn('40%',body.decode('utf-8-sig'))

import unittest
from datetime import date, timedelta

import test_core
import session_earnings


class PackageRenewalTest(unittest.TestCase):
    setUp=test_core.AppTest.setUp
    tearDown=test_core.AppTest.tearDown
    call=test_core.AppTest.call
    sess=test_core.AppTest.sess
    package=test_core.AppTest.package
    rows=test_core.AppTest.rows
    def test_same_price_adds_rights_without_repricing_old_sessions(self):
        old=self.package(n=2,gift=0,price=600)
        first=self.sess(terapist_id=3,hizmet_id=11,paket_id=old,saat='09:00')
        second=self.sess(terapist_id=3,hizmet_id=11,paket_id=old,saat='10:00')
        self.call('_save_record','terapistler',{'ad':'İkinci Pilates','uzmanlik':'Pilates','aktif':1})
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_kazanc'],240)
        renewed=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Yeni alım','fiyat':600,
            'seans_sayisi':3,'hediye_seans':0,'baslangic':self.today,
            'bitis':(date.today()+timedelta(days=90)).isoformat(),
            'yenilenen_paket_id':old})
        self.assertEqual(renewed,old)
        package=self.call('paketler_listesi')[0]
        self.assertEqual((package['fiyat'],package['seans_sayisi'],package['kalan']),(1200,5,3))
        self.assertEqual(package['sonraki_seans_ucreti'],200)
        self.assertEqual([r['ucret'] for r in self.rows('SELECT ucret FROM seanslar ORDER BY id')],[300,300])
        self.sess(terapist_id=4,hizmet_id=11,paket_id=old,saat='11:00')
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_kazanc'],240)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_kazanc'],80)
        self.assertEqual(self.call('seans_detay',first)['terapist_id'],3)
        self.assertEqual(self.call('seans_detay',second)['ucret'],300)
        with self.assertRaises(ValueError):
            self.call('paket_kaydet',{'id':old,'fiyat':1300})

    def test_changed_price_starts_new_package(self):
        old=self.package(n=1,gift=0,price=300)
        self.sess(terapist_id=3,hizmet_id=11,paket_id=old)
        new=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Yeni fiyat','fiyat':400,
            'seans_sayisi':1,'baslangic':self.today,
            'bitis':(date.today()+timedelta(days=80)).isoformat(),
            'yenilenen_paket_id':old})
        self.assertNotEqual(new,old)
        self.assertEqual(len(self.call('paketler_listesi')),2)

    def test_expired_package_merges_and_program_resumes_after_gap(self):
        old=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Önceki','fiyat':300,
            'seans_sayisi':1,'hediye_seans':0,'baslangic':self.today,'bitis':self.today})
        saved=self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,
            'paket_id':old,'baslangic':self.today,'bitis':self.today,
            'slots':[{'gun_index':date.today().weekday(),'saat':'10:00'}]})
        self.assertTrue(saved['saved'])
        later=(date.today()+timedelta(days=14)).isoformat()
        end=(date.today()+timedelta(days=35)).isoformat()
        renewed=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Yenileme','fiyat':300,
            'seans_sayisi':1,'hediye_seans':0,'baslangic':later,'bitis':end})
        self.assertEqual(renewed,old)
        plans=self.rows('SELECT baslangic,bitis,paket_id FROM haftalik_program_sablonlari ORDER BY id')
        self.assertEqual([(p['baslangic'],p['bitis']) for p in plans],[(self.today,self.today),(later,end)])
        self.assertTrue(any(r['paket_id']==old and r['tarih']==later for r in self.call('seans_haftalik_programi',later)['items']))


if __name__=='__main__':unittest.main()

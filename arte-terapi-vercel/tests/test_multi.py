from test_core import AppTest
from datetime import date,timedelta
import unittest
class MultiTest(AppTest):
 def test_same_service_multiple_therapists_and_report(self):
  self.call('service_manage',{'id':1,'terapist_ids':[1,2]});a=self.sess();b=self.sess(terapist_id=2,hizmet_id=1,saat='11:00')
  self.assertEqual(self.call('seans_detay',b)['hizmet_id'],1)
  self.assertTrue(any(h['id']==1 for h in self.call('hizmetler_listesi',2)))
  report=self.call('gelir_raporu',self.today,self.today);self.assertEqual(report['toplam']['brut'],6000);self.assertEqual(len(report['terapistler']),2)
  self.call('service_manage',{'id':1,'terapist_ids':[2]});self.call('seans_kaydet',{'id':a,'soap':{'s':'Geçmiş düzeltme'}})
  with self.assertRaises(ValueError):self.sess(saat='12:00')
 def test_multi_weekly_program_and_removal_guard(self):
  self.call('service_manage',{'id':1,'terapist_ids':[1,2]})
  result=self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':2,'hizmet_id':1,'baslangic':self.today,'bitis':(date.today()+timedelta(days=30)).isoformat(),'slots':[{'gun_index':1,'saat':'10:00'}]});self.assertTrue(result['saved'])
  with self.assertRaises(ValueError):self.call('service_manage',{'id':1,'terapist_ids':[1]})
  self.assertEqual(sorted(next(x for x in self.call('hizmetler_listesi') if x['id']==1)['terapist_ids']),[1,2])
 def test_create_multi_and_delete_unused(self):
  hid=self.call('_save_kind','hizmet_yonet',{'alan_adi':'Ortak Hizmet','kategori':'ftr','seans_ucreti':1200,'terapist_ids':[1,2,3]});self.assertEqual(sorted(next(x for x in self.call('hizmetler_listesi') if x['id']==hid)['terapist_ids']),[1,2,3])
  self.call('service_action',{'id':hid,'islem':'delete'});self.assertFalse(self.rows('SELECT * FROM hizmet_terapistleri WHERE hizmet_id=?',(hid,)))
 def test_assignment_validation_and_preservation(self):
  before=self.rows('SELECT * FROM hizmet_alanlari WHERE id=1')
  for ids in [[],[99999]]:
   with self.assertRaises(ValueError):self.call('service_manage',{'id':1,'alan_adi':'BOZUK','terapist_ids':ids})
  self.assertEqual(before,self.rows('SELECT * FROM hizmet_alanlari WHERE id=1'))
  self.assertEqual(self.call('service_action',{'id':1,'islem':'assign','terapist_id':3}),1)
  self.assertEqual(self.rows('SELECT COUNT(*) n FROM hizmet_terapistleri WHERE hizmet_id=1')[0]['n'],2)
 def test_delete_unused_package(self):
  pid=self.package();self.assertEqual(self.call('paket_sil',pid)['islem'],'silindi');self.assertEqual(self.call('paketler_listesi'),[])
 def test_close_used_package_preserves_payment_and_session(self):
  pid=self.package();sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid)
  self.call('odeme_ekle',{'danisan_id':self.a,'paket_id':pid,'tarih':self.today,'tutar':1000})
  self.assertEqual(self.call('paket_sil',pid)['islem'],'kapandi');self.assertEqual(self.call('seans_detay',sid)['paket_id'],pid);self.assertEqual(self.call('odemeler_listesi')[0]['tutar'],1000)
  self.call('paket_kaydet',{'id':pid,'ad':'Düzenlendi','aktif':1});self.assertEqual(self.call('paketler_listesi')[0]['ad'],'Düzenlendi')
 def test_close_scheduled_package_stops_future_only(self):
  pid=self.package();self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,'paket_id':pid,'baslangic':self.today,'bitis':(date.today()+timedelta(days=30)).isoformat(),'slots':[{'gun_index':1,'saat':'10:00'},{'gun_index':3,'saat':'14:30'}]})
  result=self.call('paket_sil',pid);self.assertEqual(result['islem'],'kapandi');self.assertEqual(result['durdurulan_plan'],2);self.assertEqual(self.call('haftalik_program_sablonlari_listesi'),[])

def load_tests(loader, tests, pattern):
 return unittest.TestSuite(MultiTest(name) for name in MultiTest.__dict__ if name.startswith("test_"))

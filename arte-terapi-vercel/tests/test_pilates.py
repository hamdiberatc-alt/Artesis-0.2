from test_core import AppTest
from datetime import date,timedelta
import unittest
class PilatesTest(AppTest):
 def program(self,pid,**kw):
  return self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,'paket_id':pid,'sure_dk':45,'baslangic':self.today,'bitis':(date.today()+timedelta(days=30)).isoformat(),'slots':[{'gun_index':0,'saat':'10:00'},{'gun_index':2,'saat':'14:30'},{'gun_index':4,'saat':'09:00'}],**kw})
 def test_multiple_slots_no_charge(self):
  pid=self.package();r=self.program(pid);self.assertTrue(r['saved']);self.assertEqual(r['slots'],3)
  self.assertEqual(len(self.call('haftalik_program_sablonlari_listesi')),3);self.assertEqual(self.call('paketler_listesi')[0]['kalan'],10);self.assertEqual(self.call('gelir_raporu',self.today,self.today)['toplam']['brut'],0)
  week=self.call('seans_haftalik_programi',(date.today()+timedelta(days=7)).isoformat());self.assertEqual(len(week['items']),3);self.assertTrue(all(x['paket_id']==pid for x in week['items']))
  self.assertEqual(self.call('seans_haftalik_programi',(date.today()+timedelta(days=50)).isoformat())['items'],[])
  self.assertEqual(self.call('seans_haftalik_programi',(date.today()-timedelta(days=10)).isoformat())['items'],[])
 def test_edit_stop_program_preserves_actual(self):
  pid=self.package();r=self.program(pid);actual=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid)
  v=self.program(pid,program_id=r['program_id'],slots=[{'gun_index':1,'saat':'15:30'}]);self.assertTrue(v['saved']);self.assertEqual(len(self.call('haftalik_program_sablonlari_listesi')),1)
  self.call('_delete_record','programlar',r['program_id']);self.assertEqual(self.call('haftalik_program_sablonlari_listesi'),[]);self.assertEqual(self.call('seans_detay',actual)['paket_id'],pid)
 def test_atomic_invalid_and_conflict(self):
  pid=self.package();r=self.program(pid)
  with self.assertRaises(ValueError):self.program(pid,program_id=r['program_id'],slots=[{'gun_index':1,'saat':'11:00'},{'gun_index':1,'saat':'11:15'}])
  self.assertEqual(len(self.call('haftalik_program_sablonlari_listesi')),3)
  conflict=self.program(pid);self.assertFalse(conflict['saved']);self.assertEqual(len(self.call('haftalik_program_sablonlari_listesi')),3)
 def test_person_package_tariff_snapshot(self):
  tid=self.call('pilates_tarife_kaydet',{'ad':'8 seans','seans_sayisi':8,'hediye_seans':2,'hafta':6,'bireysel':6400,'grup2':4000,'grup3':3200})
  for did in [self.a,self.b]:self.call('paket_kaydet',{'danisan_id':did,'ad':'İkili','fiyat':4000,'grup_turu':'grup2','seans_sayisi':8,'hediye_seans':2,'baslangic':self.today,'bitis':(date.today()+timedelta(days=41)).isoformat()})
  self.call('pilates_tarife_kaydet',{'id':tid,'grup2':4800});ps=self.call('paketler_listesi');self.assertEqual(sum(x['fiyat'] for x in ps),8000);self.assertEqual(len(self.call('pilates_veri')['uyeler']),2)
 def test_membership_idempotent(self):
  self.call('pilates_uye_kaydet',{'danisan_id':self.a});self.call('pilates_uye_kaydet',{'danisan_id':self.a});self.assertEqual(len(self.call('pilates_veri')['uyeler']),1)
 def test_pilates_requires_package(self):
  with self.assertRaises(ValueError):self.sess(terapist_id=3,hizmet_id=11)
 def test_date_bound_conflicts(self):
  pid=self.package();r=self.program(pid)
  later=(date.today()+timedelta(days=40)).isoformat();end=(date.today()+timedelta(days=55)).isoformat()
  self.assertTrue(self.program(pid,baslangic=later,bitis=end)['saved'])
 def test_plan_conversion(self):
  pid=self.package();sid=self.call('haftalik_program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,'gun_index':0,'saat':'10:00','sure_dk':45})
  r=self.program(pid,source_plan_id=sid);self.assertTrue(r['saved']);self.assertEqual(len(self.call('haftalik_program_sablonlari_listesi')),3)

def load_tests(loader, tests, pattern):
 return unittest.TestSuite(PilatesTest(name) for name in PilatesTest.__dict__ if name.startswith("test_"))

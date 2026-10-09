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
 def test_weekly_calendar_filters_programs_outside_requested_dates(self):
  pid=self.package();start=(date.today()+timedelta(days=90)).isoformat();end=(date.today()+timedelta(days=120)).isoformat();self.call('paket_kaydet',{'id':pid,'bitis':end});self.program(pid,baslangic=start,bitis=end)
  self.assertEqual(self.call('haftalik_program_sablonlari_listesi',None,self.today,(date.today()+timedelta(days=6)).isoformat()),[])
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
 def test_group_program_schedules_all_members_atomically(self):
  end=(date.today()+timedelta(days=30)).isoformat()
  pa=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Grup A','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  pb=self.call('paket_kaydet',{'danisan_id':self.b,'ad':'Grup B','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  gid=self.call('grup_kaydet',{'ad':'Akşam Pilates','kapasite':2,'uyeler':[{'danisan_id':self.a,'paket_id':pa},{'danisan_id':self.b,'paket_id':pb}]})
  room=self.call('odalar_listesi')[0]
  with self.call('transaction') as c:c.execute('UPDATE odalar SET kapasite=2 WHERE id=?',(room['id'],))
  slots=[{'gun_index':date.today().weekday(),'saat':'18:00'}]
  common={'grup_id':gid,'terapist_id':3,'hizmet_id':11,'oda_id':room['id'],'sure_dk':45,'baslangic':self.today,'bitis':end,'slots':slots}
  with self.assertRaises(ValueError):self.call('_save_kind','grup_programi',{**common,'paketler':{str(self.a):pa}})
  self.assertEqual(len(self.rows('SELECT * FROM haftalik_program_sablonlari')),0)
  result=self.call('_save_kind','grup_programi',{**common,'paketler':{str(self.a):pa,str(self.b):pb}})
  self.assertEqual((result['saved'],result['members'],result['slots']),(True,2,1))
  plans=self.rows('SELECT danisan_id,gun_index,saat,paket_id FROM haftalik_program_sablonlari ORDER BY danisan_id')
  self.assertEqual([(x['danisan_id'],x['saat']) for x in plans],[(self.a,'18:00'),(self.b,'18:00')])
 def test_group_attendance_without_room_is_not_rejected_as_conflict(self):
  end=(date.today()+timedelta(days=30)).isoformat()
  pa=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Grup A','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  pb=self.call('paket_kaydet',{'danisan_id':self.b,'ad':'Grup B','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  gid=self.call('grup_kaydet',{'ad':'Odasız grup','kapasite':2,'uyeler':[{'danisan_id':self.a,'paket_id':pa},{'danisan_id':self.b,'paket_id':pb}]})
  common={'grup_id':gid,'terapist_id':3,'hizmet_id':11,'sure_dk':45,'baslangic':self.today,'bitis':end,'slots':[{'gun_index':date.today().weekday(),'saat':'18:00'}],'paketler':{str(self.a):pa,str(self.b):pb}}
  self.call('_save_kind','grup_programi',common)
  for did,pid in ((self.a,pa),(self.b,pb)):
   sid=self.call('_save_kind','seanslar',{'danisan_id':did,'terapist_id':3,'hizmet_id':11,'paket_id':pid,'tarih':self.today,'saat':'18:00','sure_dk':45,'grup_turu':'grup2','gelmedi':0,'hak_dustu':0})
   self.assertTrue(sid)
 def test_group_attendance_is_atomic_and_consumes_every_member_package(self):
  end=(date.today()+timedelta(days=30)).isoformat()
  pa=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Grup A','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  pb=self.call('paket_kaydet',{'danisan_id':self.b,'ad':'Grup B','fiyat':4000,'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2','baslangic':self.today,'bitis':end})
  gid=self.call('grup_kaydet',{'ad':'Birlikte katılım','kapasite':2,'uyeler':[{'danisan_id':self.a,'paket_id':pa},{'danisan_id':self.b,'paket_id':pb}]})
  self.call('_save_kind','grup_programi',{'grup_id':gid,'terapist_id':3,'hizmet_id':11,'sure_dk':45,'baslangic':self.today,'bitis':end,'slots':[{'gun_index':date.today().weekday(),'saat':'18:00'}],'paketler':{str(self.a):pa,str(self.b):pb}})
  plans=self.rows('SELECT id,danisan_id,paket_id FROM haftalik_program_sablonlari ORDER BY danisan_id')
  with self.assertRaises(ValueError):self.call('_save_kind','grup_katilim',{'tarih':self.today,'uyeler':[{'id':plans[0]['id'],'kaynak':'planli'},{'id':999999,'kaynak':'planli'}]})
  self.assertEqual(self.rows('SELECT id FROM seanslar'),[])
  result=self.call('_save_kind','grup_katilim',{'tarih':self.today,'uyeler':[{'id':p['id'],'kaynak':'planli'} for p in plans]})
  self.assertEqual(result['members'],2)
  self.assertEqual(self.rows('SELECT danisan_id,paket_id,hak_dustu FROM seanslar ORDER BY danisan_id'),[{'danisan_id':self.a,'paket_id':pa,'hak_dustu':1},{'danisan_id':self.b,'paket_id':pb,'hak_dustu':1}])

def load_tests(loader, tests, pattern):
 return unittest.TestSuite(PilatesTest(name) for name in PilatesTest.__dict__ if name.startswith("test_"))


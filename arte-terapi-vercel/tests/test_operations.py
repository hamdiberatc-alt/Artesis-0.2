from test_core import AppTest
from datetime import date,timedelta
import unittest,json,threading,http.client
class OperationsTest(AppTest):
 def payload(self,**kw):
  x={'istek_id':'test-key','danisan':{'ad':'Yeni','soyad':'Üye','telefon':'0555'},'program':{'terapist_id':3,'hizmet_id':11,'sure_dk':45,'oda_id':3,'baslangic':self.today,'bitis':(date.today()+timedelta(days=41)).isoformat(),'slots':[{'gun_index':0,'saat':'10:00'},{'gun_index':2,'saat':'14:30'}]},'paket':{'ad':'İkili','fiyat':4000,'grup_turu':'grup2','seans_sayisi':8,'hediye_seans':2,'baslangic':self.today,'bitis':(date.today()+timedelta(days=41)).isoformat()},'olcum':{'tarih':self.today,'boy':156,'kilo':45,'bel':60},'tahsilat':{'tarih':self.today,'tutar':1000,'yontem':'nakit'}};x.update(kw);return x
 def test_atomic_registration_and_retry(self):
  d=self.payload();r=self.call('kayit_program',d);self.assertTrue(r['saved']);again=self.call('kayit_program',d);self.assertEqual(r,again)
  self.assertEqual(len(self.rows('SELECT * FROM pilates_paketleri')),1);self.assertEqual(len(self.rows('SELECT * FROM odemeler')),1);self.assertEqual(len(self.rows('SELECT * FROM vucut_olcumleri')),1)
  self.assertEqual(len(self.rows('SELECT * FROM haftalik_program_sablonlari')),2)
  self.assertEqual(self.call('olcum_veri',r['danisan_id'])['gerceklesen'],0)
 def test_full_rollback_after_measurement_failure(self):
  d=self.payload(olcum={'tarih':self.today,'kilo':-1})
  with self.assertRaises(ValueError):self.call('kayit_program',d)
  for table in ['pilates_paketleri','odemeler','vucut_olcumleri','haftalik_program_sablonlari','kayit_islemleri']:self.assertEqual(self.rows('SELECT * FROM '+table),[])
  self.assertEqual(len(self.rows('SELECT * FROM danisanlar')),2)
 def test_conflict_is_reviewable_without_partial_records(self):
  first=self.call('kayit_program',self.payload());d=self.payload(istek_id='other',danisan={'ad':'Başka','soyad':'Üye'})
  d['paket']['grup_turu']='bireysel';r=self.call('kayit_program',d);self.assertFalse(r['saved']);self.assertTrue(r['conflicts']);self.assertEqual(len(self.rows('SELECT * FROM pilates_paketleri')),1)
  d['program']['conflict_override']=1;self.assertTrue(self.call('kayit_program',d)['saved']);self.assertEqual(len(self.rows('SELECT * FROM pilates_paketleri')),2)
 def test_no_duplicate_person(self):
  self.call('kayit_program',self.payload())
  with self.assertRaises(ValueError):self.call('kayit_program',self.payload(istek_id='second'))
 def test_measurements_eight_attended_not_noshow(self):
  pid=self.package(8,2);self.call('olcum_kaydet',{'danisan_id':self.a,'tarih':self.today,'asama':0,'boy':156,'kilo':45,'omuz':88})
  for i in range(7):self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat=f'{8+i:02}:00')
  self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='16:00',gelmedi=1,hak_dustu=1)
  self.assertEqual(self.call('olcum_veri',self.a)['eksik_asamalar'],[])
  self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='17:00',hediye=1)
  info=self.call('olcum_veri',self.a);self.assertEqual(info['gerceklesen'],8);self.assertEqual(info['eksik_asamalar'],[8])
  self.call('olcum_kaydet',{'danisan_id':self.a,'tarih':self.today,'asama':8,'kilo':'44,5','bel':59})
  self.assertEqual(self.call('danisan_detay',self.a)['olcumler']['items'][1]['kilo'],44.5)
  with self.assertRaises(ValueError):self.call('olcum_kaydet',{'danisan_id':self.a,'tarih':self.today,'asama':16,'kilo':43})
 def test_statement_ledger_upcoming_reports_scope(self):
  result=self.call('kayit_program',self.payload());did=result['danisan_id'];pid=result['paket_id']
  self.call('seans_kaydet',{'danisan_id':did,'terapist_id':3,'hizmet_id':11,'tarih':self.today,'saat':'08:00','paket_id':pid})
  self.call('seans_kaydet',{'danisan_id':did,'terapist_id':3,'hizmet_id':11,'tarih':self.today,'saat':'09:00','paket_id':pid,'gelmedi':1,'hak_dustu':1})
  self.call('rapor_ekle',{'danisan_id':did,'tarih':self.today,'baslik':'Gelişim','icerik':'<script>alert(1)</script>Güç gelişti'})
  future=(date.today()+timedelta(days=21)).isoformat();r=self.call('client_statement',did,self.today,self.today,future,True,True)
  self.assertEqual(len(r['seanslar']),2);self.assertEqual(r['bakiye'],3000);self.assertEqual(r['donem_seans_tutari'],1000);self.assertTrue(r['gelecek']);self.assertEqual(len(r['raporlar']),1);self.assertEqual(len(r['olcumler']),1)
  html=self.call('statement_html',r);self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>alert(1)',html)
  link=self.call('statement_link',{'danisan_id':did,'start':self.today,'end':self.today,'future_end':future,'reports':0,'measurements':0})
  public=self.call('scoped_statement',link['token']);self.assertEqual(public['raporlar'],[]);self.assertEqual(public['olcumler'],[]);self.assertNotIn('soap_s',str(public));self.assertEqual(public['danisan']['id'],did)
 def test_http_statement_requires_auth_and_pdf_scope(self):
  server=self.m['ThreadingHTTPServer'](('127.0.0.1',0),self.m['Handler']);self.srv=server;threading.Thread(target=server.serve_forever,daemon=True).start()
  def req(method,path,data=None,cookie='',csrf=''):
   h={'Content-Type':'application/json','Cookie':cookie,'X-CSRF-Token':csrf};conn=http.client.HTTPConnection('127.0.0.1',server.server_port);conn.request(method,path,json.dumps(data) if data is not None else None,h);r=conn.getresponse();body=r.read();headers=dict(r.getheaders());conn.close();return r.status,body,headers
  code,_,_=req('GET','/danisan-dokumu?id='+str(self.a));self.assertEqual(code,401)
  code,body,heads=req('POST','/api/setup',{'password':'test-password'});self.assertEqual(code,200);csrf=json.loads(body)['csrf'];cookie=heads['Set-Cookie'].split(';')[0]
  code,body,_=req('POST','/api/save',{'kind':'kayit_program','data':self.payload()},cookie,csrf);self.assertEqual(code,200);did=json.loads(body)['id']['danisan_id']
  code,body,_=req('GET','/danisan-dokumu?id='+str(did)+'&reports=1&measurements=1',cookie=cookie);self.assertEqual(code,200);self.assertIn('Vücut ölçümleri',body.decode())
  self.assertEqual(req('GET','/portal-pdf?token=wrong&id=1')[0],403)
 def test_future_session_guard(self):
  with self.assertRaises(ValueError):self.sess(tarih=(date.today()+timedelta(days=1)).isoformat())
 def test_moved_session_consumes_original_plan(self):
  pid=self.package();weekday=date.today().weekday()
  result=self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,'paket_id':pid,'sure_dk':45,'baslangic':self.today,'bitis':(date.today()+timedelta(days=21)).isoformat(),'slots':[{'gun_index':weekday,'saat':'09:00'}]})
  self.assertTrue(result['saved'])
  self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='10:00',program_id=result['program_id'],plan_tarihi=self.today,planlanan_saat='09:00')
  items=self.call('seans_haftalik_programi',self.today)['items'];todayitems=[r for r in items if r['tarih']==self.today]
  self.assertEqual(len(todayitems),1);self.assertEqual(todayitems[0]['saat'],'10:00')
  nextweek=self.call('seans_haftalik_programi',(date.today()+timedelta(days=7)).isoformat())['items'];self.assertEqual(len(nextweek),1);self.assertEqual(nextweek[0]['saat'],'09:00')
 def test_cancelled_plan_and_report_date_limit(self):
  result=self.call('kayit_program',self.payload());did=result['danisan_id'];future=(date.today()+timedelta(days=21)).isoformat()
  r=self.call('client_statement',did,self.today,self.today,future);slot=r['gelecek'][0]
  self.call('randevu_ekle',{'danisan_id':did,'terapist_id':3,'tarih':slot['tarih'],'saat':slot['saat'],'durum':'iptal','sure_dk':45})
  r=self.call('client_statement',did,self.today,self.today,future);self.assertFalse(any(x['tarih']==slot['tarih'] and x['saat']==slot['saat'] for x in r['gelecek']))
  week=self.call('seans_haftalik_programi',slot['tarih'])['items'];self.assertFalse(any(x['danisan_id']==did and x['tarih']==slot['tarih'] and x['saat']==slot['saat'] for x in week))

def load_tests(loader, tests, pattern):
 return unittest.TestSuite(OperationsTest(name) for name in OperationsTest.__dict__ if name.startswith("test_"))

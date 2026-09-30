import unittest,os,pathlib,runpy,tempfile,threading,http.client,json,base64,sqlite3,zipfile,io
from datetime import date,timedelta
ROOT=pathlib.Path(__file__).resolve().parent
class AppTest(unittest.TestCase):
 def setUp(self):
  self.old_db_path=os.environ.get('ARTE_DB_PATH');self.tmp=tempfile.TemporaryDirectory();os.environ['ARTE_DB_PATH']=self.tmp.name+'/test.db';self.m=runpy.run_path(str(ROOT.parent/'app.py'));self.m['init_db']();self.today=date.today().isoformat();self.a=self.call('danisan_ekle',{'ad':'A','terapist_id':1,'terapist_ids':[2,3]});self.b=self.call('danisan_ekle',{'ad':'B','terapist_id':2});self.srv=None
 def tearDown(self):
  if self.srv:self.srv.shutdown();self.srv.server_close()
  self.tmp.cleanup()
  if self.old_db_path is None:os.environ.pop('ARTE_DB_PATH',None)
  else:os.environ['ARTE_DB_PATH']=self.old_db_path
 def call(self,name,*a,**k):return self.m[name](*a,**k)
 def rows(self,sql,p=()):
  c=self.call('get_db');r=self.call('q',c,sql,p);c.close();return r
 def sess(self,**kw):
  return self.call('seans_kaydet',{'danisan_id':self.a,'terapist_id':1,'hizmet_id':1,'tarih':self.today,'saat':'09:30',**kw})
 def package(self,n=8,gift=2,price=6400):
  return self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Test','fiyat':price,'seans_sayisi':n,'hediye_seans':gift,'baslangic':self.today,'bitis':(date.today()+timedelta(days=60)).isoformat()})
 def test_fresh_and_idempotent(self):
  room=self.call('odalar_listesi')[0];self.call('oda_kaydet',{**room,'ad':'TEST','kapasite':1,'kategori':'grup','aktif':0});self.m['init_db'].__globals__['_INITIALIZED_PATHS'].clear();self.call('init_db');r=self.rows('SELECT * FROM odalar WHERE id=?',(room['id'],))[0];self.assertEqual((r['ad'],r['kapasite'],r['kategori'],r['aktif']),('TEST',1,'grup',0));self.assertEqual(len(self.rows('SELECT * FROM odalar')),3)
 def test_multi_therapist(self):
  x=self.sess();y=self.sess(terapist_id=2,hizmet_id=4);self.assertNotEqual(x,y);d=self.call('danisan_detay',self.a);self.assertEqual(len(d['terapistler']),3);r=self.call('gelir_raporu',self.today,self.today);self.assertEqual(r['toplam']['brut'],5000);self.assertEqual(len(r['terapistler']),2)
 def test_update_time_soap(self):
  sid=self.sess(soap={'s':'KEEP','o':'o','a':'a','p':'p'},tip='degerlendirme');self.call('seans_kaydet',{'id':sid,'saat':'10:00'});r=self.rows('SELECT * FROM seanslar')[0];self.assertEqual(len(self.rows('SELECT * FROM seanslar')),1);self.assertEqual((r['soap_s'],r['tip']),('KEEP','degerlendirme'))
 def test_no_show(self):
  s=self.sess(gelmedi=1,hak_dustu=0);r=self.call('seans_detay',s);self.assertEqual((r['ucret'],r['gelmedi'],r['hak_dustu']),(0,1,0));self.call('seans_kaydet',{'id':s,'hak_dustu':1});self.assertEqual(self.call('seans_detay',s)['ucret'],3000)
 def test_package_gifts_shared(self):
  pid=self.package(n=2,gift=1,price=1001);h2=self.call('hizmet_ekle',{'terapist_id':2,'alan_adi':'Pilates','kategori':'pilates','paket_mi':1,'seans_ucreti':1001,'paket_seans':2,'terapist_prim_orani':.4})
  for i,(tid,hid) in enumerate([(3,11),(2,h2),(3,11)]):self.sess(terapist_id=tid,hizmet_id=hid,saat=f'{9+i}:30'.zfill(5),paket_id=pid)
  rows=self.rows('SELECT * FROM seanslar ORDER BY id');self.assertEqual([r['ucret'] for r in rows],[500.5,500.5,0]);self.assertEqual(rows[-1]['hediye'],1);self.assertEqual(self.call('paketler_listesi')[0]['kalan'],0)
  with self.assertRaises(ValueError):self.sess(terapist_id=3,hizmet_id=11,saat='15:00',paket_id=pid)
  r=self.call('gelir_raporu',self.today,self.today);self.assertEqual(r['toplam']['brut'],1001);self.assertEqual(r['toplam']['terapist_payi'],400.4);self.assertEqual(r['haftalik'][0]['brut'],r['aylik'][0]['brut'])
 def test_package_edit_remaining(self):
  pid=self.package(2,1,1000);s=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid);self.call('paket_kaydet',{'id':pid,'fiyat':1400,'seans_sayisi':3,'hediye_seans':2});self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='10:00');r=self.rows('SELECT ucret FROM seanslar ORDER BY id');self.assertEqual([x['ucret'] for x in r],[500,450]);self.assertEqual(self.call('paketler_listesi')[0]['hediye_seans'],2)
 def test_payment_and_cash(self):
  s=self.sess(ucret_alindi=1);self.assertEqual(len(self.call('odemeler_listesi')),1);self.assertEqual(len(self.call('kasa_listesi')),1);self.assertEqual(self.call('seans_detay',s)['ucret_alindi'],1);o=self.call('odemeler_listesi')[0];self.call('odeme_sil',o['id']);self.assertEqual(self.call('kasa_listesi'),[]);self.assertEqual(self.call('seans_detay',s)['ucret_alindi'],0)
 def test_identical_payments(self):
  a=self.call('odeme_ekle',{'danisan_id':self.a,'tarih':self.today,'tutar':100});b=self.call('odeme_ekle',{'danisan_id':self.b,'tarih':self.today,'tutar':100});self.call('odeme_sil',a);self.assertEqual(self.call('kasa_listesi')[0]['kaynak_id'],b)
 def test_identical_expenses(self):
  a=self.call('gider_ekle',{'tarih':self.today,'tutar':100,'kategori':'A'});b=self.call('gider_ekle',{'tarih':self.today,'tutar':100,'kategori':'B'});self.call('gider_sil',a);self.assertEqual(self.call('kasa_listesi')[0]['kaynak_id'],b)
 def test_invalid_inputs_and_rollback(self):
  with self.assertRaises(sqlite3.IntegrityError):self.call('danisan_ekle',{'ad':'Bad','terapist_id':1,'terapist_ids':[999999]})
  self.assertFalse(self.call('danisanlar_listesi',None,'Bad'))
  for change in [{'hizmet_id':999999},{'saat':'99:99'},{'sure_dk':-5},{'tarih':'2026-02-30'}]:
   with self.assertRaises(ValueError):self.sess(**change)
  with self.assertRaises(ValueError):self.call('odeme_ekle',{'danisan_id':999,'tarih':self.today,'tutar':-100})
 def test_stock(self):
  k=self.call('stok_kalem_kaydet',{'ad':'X','mevcut_stok':5})
  for d in [{'tur':'cikis','miktar':-2},{'tur':'xyz','miktar':1},{'tur':'cikis','miktar':10}]:
   with self.assertRaises(ValueError):self.call('stok_hareket_ekle',{'kalem_id':k,**d})
  self.assertEqual(self.call('stok_hareket_ekle',{'kalem_id':k,'tur':'sayim','miktar':0})['mevcut_stok'],0)
 def test_portal_expiry(self):
  t=self.call('portal_token_olustur',self.a,-1);self.assertIsNone(self.call('portal_veri',t))
 def test_archive(self):
  sid=self.sess();self.call('danisan_sil',self.a);self.assertIsNotNone(self.call('seans_detay',sid));self.assertFalse(self.call('danisanlar_listesi',None,'A'));self.assertEqual(self.call('gelir_raporu',self.today,self.today)['toplam']['brut'],3000)
 def test_report_week_month_and_no_sessions(self):
  self.sess(tarih='2026-08-31');self.sess(tarih='2026-09-01',saat='10:00');r=self.call('gelir_raporu','2026-08-31','2026-09-06');self.assertEqual(len(r['haftalik']),1);self.assertEqual(len(r['aylik']),2);self.assertEqual(r['toplam']['brut'],6000);self.assertEqual(self.call('gelir_raporu','2026-08-31','2026-09-06',2)['toplam']['brut'],0)
 def test_zero_debt_and_cancelled_reminder(self):
  self.assertEqual(self.call('odeme_hatirlatma_hedefleri'),[]);dt=(date.today()+timedelta(days=1)).isoformat();self.call('randevu_ekle',{'danisan_id':self.a,'terapist_id':1,'hizmet_id':1,'tarih':dt,'saat':'09:30','durum':'iptal'});self.assertEqual(self.call('mesaj_hedefleri_listesi','24saat_kala')['items'],[])
 def http(self,path,data=None,cookie='',csrf=''):
  if not self.srv:self.srv=self.m['ArteServer'](('127.0.0.1',0),self.m['Handler']);threading.Thread(target=self.srv.serve_forever,daemon=True).start()
  c=http.client.HTTPConnection('127.0.0.1',self.srv.server_port,timeout=10);c.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':cookie,'X-CSRF-Token':csrf});r=c.getresponse();b=r.read();headers=dict(r.getheaders());status=r.status;c.close();return status,b,headers
 def test_auth_http_pdf(self):
  self.assertEqual(self.http('/api/bootstrap')[0],401);status,body,h=self.http('/api/setup',{'password':'testpass123'});self.assertEqual(status,200);cookie=h['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf'];self.assertEqual(self.http('/api/save',{'kind':'danisanlar','data':{'ad':'X','terapist_id':1}},cookie)[0],403)
  rid=self.call('rapor_pdf_kaydet',{'danisan_id':self.a,'dosya_adi':'ölçüm_şığ.pdf','base64':base64.b64encode(b'%PDF-1.4\n%%EOF').decode()});status,body,h=self.http('/rapor_pdf?id='+str(rid),cookie=cookie);self.assertEqual(status,200);self.assertTrue(body.startswith(b'%PDF-'));self.assertIn('filename*=',h['Content-Disposition']);self.assertNotIn('Access-Control-Allow-Origin',h)
  status,body,h=self.http('/api/save',{'kind':'seanslar','data':{'danisan_id':self.a,'terapist_id':1,'hizmet_id':1,'tarih':self.today,'saat':'09:30','gelmedi':1}},cookie,csrf);self.assertEqual(status,200,body);self.assertEqual(self.call('seans_detay',json.loads(body)['id'])['gelmedi'],1)
  self.assertEqual(self.http('/api/bootstrap',cookie=cookie)[0],200);self.assertEqual(self.http('/api/report?start='+self.today+'&end='+self.today,cookie=cookie)[0],200)
 def test_backup(self):
  rid=self.call('rapor_pdf_kaydet',{'danisan_id':self.a,'dosya_adi':'a.pdf','base64':base64.b64encode(b'%PDF-1.4\n%%EOF').decode()});z=zipfile.ZipFile(io.BytesIO(self.call('backup_bytes')));self.assertIn('arteterapi.db',z.namelist());self.assertIn(f'rapor_pdfler/{rid}.pdf',z.namelist())
if __name__=='__main__':unittest.main(verbosity=2)

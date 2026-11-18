import unittest
from datetime import date, timedelta

import test_core
import session_earnings
import payroll


class TherapistChangeTest(unittest.TestCase):
    setUp=test_core.AppTest.setUp
    tearDown=test_core.AppTest.tearDown
    call=test_core.AppTest.call
    sess=test_core.AppTest.sess
    package=test_core.AppTest.package
    rows=test_core.AppTest.rows
    def _plan(self):
        start=self.today
        end=(date.today()+timedelta(days=21)).isoformat()
        pid=self.package()
        self.assertEqual(self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1}),4)
        result=self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,
            'paket_id':pid,'baslangic':start,'bitis':end,
            'slots':[{'gun_index':date.today().weekday(),'saat':'14:00'}]})
        self.assertTrue(result['saved'])
        plan=self.call('haftalik_program_sablonlari_listesi')[0]
        return plan,pid

    def test_client_change_updates_program_from_today(self):
        plan,pid=self._plan()
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        week=self.call('seans_haftalik_programi',self.today)['items']
        selected=next(x for x in week if x['kaynak']=='planli' and x['tarih']==self.today)
        self.assertEqual(selected['terapist_id'],4)
        next_week=(date.today()+timedelta(days=7)).isoformat()
        later=next(x for x in self.call('seans_haftalik_programi',next_week)['items'] if x['kaynak']=='planli')
        self.assertEqual(later['terapist_id'],4)
        self.assertEqual(self.call('danisan_detay',self.a)['terapist_id'],4)
        self.sess(terapist_id=4,hizmet_id=11,paket_id=pid,saat='14:00',
            program_id=selected['program_id'],plan_tarihi=self.today,planlanan_saat='14:00')
        same_day=[x for x in self.call('seans_haftalik_programi',self.today)['items'] if x['tarih']==self.today and x['danisan_id']==self.a and x['saat']=='14:00']
        self.assertEqual(len(same_day),1)
        self.assertEqual(same_day[0]['kaynak'],'gerceklesen')

    def test_client_change_moves_recorded_same_day_session_and_earnings(self):
        self.assertEqual(self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1}),4)
        pid=self.package()
        sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='14:00')
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(self.call('danisan_detay',self.a)['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_seans'],1)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_seans'],0)

    def test_client_change_moves_current_and_future_program_only(self):
        self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1})
        start=(date.today()-timedelta(days=7)).isoformat()
        end=(date.today()+timedelta(days=21)).isoformat()
        pid=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Dönem','fiyat':1200,
            'seans_sayisi':4,'hediye_seans':0,'baslangic':start,'bitis':end})
        saved=self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,
            'paket_id':pid,'baslangic':start,'bitis':end,
            'slots':[{'gun_index':date.today().weekday(),'saat':'14:00'}]})
        self.assertTrue(saved['saved'])
        before=next(r for r in self.call('seans_haftalik_programi',start)['items'] if r['kaynak']=='planli')
        self.assertEqual(before['terapist_id'],3)
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        previous=next(r for r in self.call('seans_haftalik_programi',start)['items'] if r['kaynak']=='planli')
        current=next(r for r in self.call('seans_haftalik_programi',self.today)['items'] if r['kaynak']=='planli')
        future=next(r for r in self.call('seans_haftalik_programi',(date.today()+timedelta(days=7)).isoformat())['items'] if r['kaynak']=='planli')
        self.assertEqual((previous['terapist_id'],current['terapist_id'],future['terapist_id']),(3,4,4))
        self.assertEqual([r['terapist_id'] for r in self.rows('SELECT terapist_id FROM haftalik_program_sablonlari ORDER BY baslangic')],[3,4])
        sid=self.sess(terapist_id=4,hizmet_id=11,paket_id=pid,saat='14:00',
            program_id=current['program_id'],plan_tarihi=self.today,planlanan_saat='14:00')
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_kazanc'],120)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_kazanc'],0)
        self.assertEqual(len([r for r in self.call('seans_haftalik_programi',self.today)['items'] if r['danisan_id']==self.a and r['saat']=='14:00']),1)

    def test_recorded_same_day_session_moves_to_new_therapist(self):
        plan,pid=self._plan()
        sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='14:00',
            program_id=plan['program_id'],plan_tarihi=self.today,planlanan_saat='14:00')
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_kazanc'],0)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_kazanc'],320)
        same_day=[r for r in self.call('seans_haftalik_programi',self.today)['items'] if r['danisan_id']==self.a and r['saat']=='14:00']
        self.assertEqual(len(same_day),1)
        next_week=(date.today()+timedelta(days=7)).isoformat()
        self.assertEqual(next(r['terapist_id'] for r in self.call('seans_haftalik_programi',next_week)['items'] if r['kaynak']=='planli'),4)

    def test_new_session_uses_client_assignment_after_change(self):
        _,pid=self._plan()
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='08:00')
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_seans'],0)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_seans'],1)
        self.assertEqual(payroll.report(self.m,self.today[:7],3)['terapistler'][0]['seans'],0)
        self.assertEqual(payroll.report(self.m,self.today[:7],4)['terapistler'][0]['seans'],1)

    def test_previous_day_stays_with_original_therapist(self):
        self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1})
        old_day=(date.today()-timedelta(days=1)).isoformat()
        pid=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Dönem','fiyat':1200,
            'seans_sayisi':4,'hediye_seans':0,'baslangic':old_day,
            'bitis':(date.today()+timedelta(days=21)).isoformat()})
        old_sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,tarih=old_day,saat='08:00')
        today_sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='09:00')
        with self.m['transaction']() as c:
            c.execute('INSERT INTO odemeler(danisan_id,terapist_id,tarih,tutar,seans_id) VALUES(?,?,?,?,?)',
                (self.a,3,self.today,300,today_sid))
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(self.call('seans_detay',old_sid)['terapist_id'],3)
        self.assertEqual(self.call('seans_detay',today_sid)['terapist_id'],4)
        self.assertEqual(self.rows('SELECT terapist_id FROM odemeler WHERE seans_id=?',(today_sid,))[0]['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_seans'],1)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_seans'],1)

    def test_existing_change_is_reconciled_by_schema_upgrade(self):
        from cloud.runtime import ensure_schema
        self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1})
        pid=self.package()
        sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='08:00')
        with self.m['transaction']() as c:
            c.execute('INSERT INTO odemeler(danisan_id,terapist_id,tarih,tutar,seans_id) VALUES(?,?,?,?,?)',
                (self.a,3,self.today,800,sid))
        with self.m['transaction']() as c:
            c.execute('CREATE TABLE cloud_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            c.execute("INSERT INTO cloud_meta VALUES('version','7')")
            c.execute('UPDATE danisanlar SET terapist_id=4 WHERE id=?',(self.a,))
            c.execute('INSERT INTO danisan_terapist_degisimleri VALUES(?,?,?)',(self.a,self.today,4))
        c=self.call('get_db')
        try:
            ensure_schema(c,lambda:'unused',reconcile=self.m['_pilates_seans_terapistlerini_uzlastir'])
            self.assertEqual(c.execute("SELECT value FROM cloud_meta WHERE key='version'").fetchone()[0],'8')
        finally:c.close()
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(self.rows('SELECT terapist_id FROM odemeler WHERE seans_id=?',(sid,))[0]['terapist_id'],4)

    def test_renewal_copies_only_current_therapist_program(self):
        self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1})
        start=(date.today()-timedelta(days=7)).isoformat()
        end=(date.today()+timedelta(days=21)).isoformat()
        old=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Eski','fiyat':300,
            'seans_sayisi':1,'baslangic':start,'bitis':end})
        self.call('program_kaydet',{'danisan_id':self.a,'terapist_id':3,'hizmet_id':11,
            'paket_id':old,'baslangic':start,'bitis':end,
            'slots':[{'gun_index':date.today().weekday(),'saat':'14:00'}]})
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.sess(terapist_id=4,hizmet_id=11,paket_id=old,saat='08:00')
        renewed=self.call('paket_kaydet',{'danisan_id':self.a,'ad':'Yeni fiyat','fiyat':600,
            'seans_sayisi':2,'baslangic':self.today,
            'bitis':(date.today()+timedelta(days=49)).isoformat()})
        self.assertNotEqual(old,renewed)
        future=(date.today()+timedelta(days=28)).isoformat()
        planned=[r for r in self.call('seans_haftalik_programi',future)['items'] if r['kaynak']=='planli' and r['danisan_id']==self.a]
        self.assertEqual(len(planned),1)
        self.assertEqual((planned[0]['paket_id'],planned[0]['terapist_id']),(renewed,4))

    def test_reject_unassigned_or_busy_new_therapist(self):
        plan,pid=self._plan()
        with self.assertRaises(ValueError):
            self.call('danisan_guncelle',{'id':self.a,'terapist_id':2})
        end=(date.today()+timedelta(days=21)).isoformat()
        other=self.call('paket_kaydet',{'danisan_id':self.b,'ad':'B','fiyat':800,
            'seans_sayisi':2,'baslangic':self.today,'bitis':end})
        self.call('program_kaydet',{'danisan_id':self.b,'terapist_id':4,'hizmet_id':11,
            'paket_id':other,'baslangic':self.today,'bitis':end,
            'slots':[{'gun_index':date.today().weekday(),'saat':'14:00'}]})
        with self.assertRaises(ValueError):
            self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(self.call('danisan_detay',self.a)['terapist_id'],1)

    def test_group_members_can_move_to_same_therapist(self):
        self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1})
        end=(date.today()+timedelta(days=30)).isoformat()
        packages=[]
        for did in (self.a,self.b):
            packages.append(self.call('paket_kaydet',{'danisan_id':did,'ad':'Grup','fiyat':4000,
                'seans_sayisi':8,'hediye_seans':0,'grup_turu':'grup2',
                'baslangic':self.today,'bitis':end}))
        gid=self.call('grup_kaydet',{'ad':'İkili','kapasite':2,'uyeler':[
            {'danisan_id':self.a,'paket_id':packages[0]},
            {'danisan_id':self.b,'paket_id':packages[1]}]})
        result=self.call('grup_programi_kaydet',{'grup_id':gid,'terapist_id':3,'hizmet_id':11,
            'baslangic':self.today,'bitis':end,'slots':[{'gun_index':date.today().weekday(),'saat':'18:00'}],
            'paketler':{str(self.a):packages[0],str(self.b):packages[1]}})
        self.assertTrue(result['saved'])
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.call('danisan_guncelle',{'id':self.b,'terapist_id':4})
        visible=[r for r in self.call('seans_haftalik_programi',self.today)['items'] if r['kaynak']=='planli']
        self.assertEqual([r['terapist_id'] for r in visible],[4,4])


if __name__=='__main__':unittest.main()

import unittest
from datetime import date, timedelta

import test_core
import session_earnings


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

    def test_planned_occurrence_changes_only_selected_date(self):
        plan,pid=self._plan()
        self.call('program_seans_terapist_degistir',{'plan_ids':[plan['id']],
            'tarih':self.today,'terapist_id':4})
        week=self.call('seans_haftalik_programi',self.today)['items']
        selected=next(x for x in week if x['kaynak']=='planli' and x['tarih']==self.today)
        self.assertEqual(selected['terapist_id'],4)
        self.assertEqual(self.call('haftalik_program_sablonlari_listesi')[0]['terapist_id'],3)
        next_week=(date.today()+timedelta(days=7)).isoformat()
        later=next(x for x in self.call('seans_haftalik_programi',next_week)['items'] if x['kaynak']=='planli')
        self.assertEqual(later['terapist_id'],3)
        self.assertEqual(self.call('danisan_detay',self.a)['terapist_id'],1)
        self.sess(terapist_id=4,hizmet_id=11,paket_id=pid,saat='14:00',
            program_id=plan['program_id'],plan_tarihi=self.today,planlanan_saat='14:00')
        same_day=[x for x in self.call('seans_haftalik_programi',self.today)['items'] if x['tarih']==self.today and x['danisan_id']==self.a and x['saat']=='14:00']
        self.assertEqual(len(same_day),1)
        self.assertEqual(same_day[0]['kaynak'],'gerceklesen')

    def test_client_and_recorded_session_therapist_are_independent(self):
        self.assertEqual(self.call('_save_record','terapistler',{'ad':'Yeni Pilates','uzmanlik':'Pilates','aktif':1}),4)
        pid=self.package()
        sid=self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='14:00')
        self.call('danisan_guncelle',{'id':self.a,'terapist_id':4})
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],3)
        self.call('kayitli_seans_terapist_degistir',{'seans_id':sid,'terapist_id':4})
        self.assertEqual(self.call('seans_detay',sid)['terapist_id'],4)
        self.assertEqual(self.call('danisan_detay',self.a)['terapist_id'],4)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],4)['toplam_seans'],1)
        self.assertEqual(session_earnings.report(self.m,self.today[:7],3)['toplam_seans'],0)

    def test_reject_unassigned_therapist_and_recorded_plan(self):
        plan,pid=self._plan()
        with self.assertRaises(ValueError):
            self.call('program_seans_terapist_degistir',{'plan_ids':[plan['id']],
                'tarih':self.today,'terapist_id':2})
        self.sess(terapist_id=3,hizmet_id=11,paket_id=pid,saat='14:00',
            program_id=plan['program_id'],plan_tarihi=self.today,planlanan_saat='14:00')
        with self.assertRaises(ValueError):
            self.call('program_seans_terapist_degistir',{'plan_ids':[plan['id']],
                'tarih':self.today,'terapist_id':4})

    def test_group_occurrence_moves_all_members(self):
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
        plan=self.rows('SELECT id FROM haftalik_program_sablonlari LIMIT 1')[0]
        changed=self.call('program_seans_terapist_degistir',{'plan_ids':[plan['id']],
            'tarih':self.today,'terapist_id':4})
        self.assertEqual(len(changed['plan_ids']),2)
        visible=[r for r in self.call('seans_haftalik_programi',self.today)['items'] if r['kaynak']=='planli']
        self.assertEqual([r['terapist_id'] for r in visible],[4,4])


if __name__=='__main__':unittest.main()

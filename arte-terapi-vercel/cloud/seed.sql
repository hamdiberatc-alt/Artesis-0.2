CREATE TABLE auth_sessions(token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE automation_runs(rule_id INTEGER, target_key TEXT, run_date TEXT,
                PRIMARY KEY(rule_id,target_key,run_date));
CREATE TABLE ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger TEXT NOT NULL
    );
CREATE TABLE danisan_rapor_dosyalari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        dosya_adi TEXT NOT NULL,
        dosya_yolu TEXT NOT NULL,
        mime_tur TEXT DEFAULT 'application/pdf',
        boyut INTEGER DEFAULT 0,
        eklenme_ts TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE SET NULL
    );
CREATE TABLE danisan_raporlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        baslik TEXT NOT NULL,
        icerik TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id)
    );
CREATE TABLE danisan_terapistler (
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        rol TEXT DEFAULT 'ek',
        PRIMARY KEY (danisan_id, terapist_id),
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE CASCADE
    );
CREATE TABLE danisanlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        terapist_id INTEGER NOT NULL,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        telefon TEXT DEFAULT '',
        dogum_tarihi TEXT DEFAULT '',
        tckn TEXT DEFAULT '',
        cinsiyet TEXT DEFAULT '',
        meslek TEXT DEFAULT '',
        tani TEXT DEFAULT '',
        sikayet TEXT DEFAULT '',
        hedefler TEXT DEFAULT '',
        notlar TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        kayit_tarihi TEXT DEFAULT (date('now','localtime')), pilates_baslangic_tarihi TEXT DEFAULT '', pilates_paket_odendi INTEGER DEFAULT 0, pilates_paket_odeme_tarihi TEXT DEFAULT '', email TEXT DEFAULT '',
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
CREATE TABLE gelisim_notlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        tur TEXT DEFAULT 'genel',
        metin TEXT NOT NULL,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id)
    );
CREATE TABLE giderler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        kategori TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT DEFAULT ''
    );
CREATE TABLE haftalik_program_sablonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        gun_index INTEGER NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        oda_id INTEGER,
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT '', grup_turu TEXT DEFAULT 'bireysel', program_id TEXT, paket_id INTEGER, baslangic TEXT DEFAULT '', bitis TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id) ON DELETE CASCADE,
        FOREIGN KEY(hizmet_id) REFERENCES hizmet_alanlari(id),
        FOREIGN KEY(oda_id) REFERENCES odalar(id)
    );
CREATE TABLE hizmet_alanlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        terapist_id INTEGER NOT NULL,
        alan_adi TEXT NOT NULL,
        kategori TEXT DEFAULT 'ftr',
        seans_ucreti REAL DEFAULT 0,
        paket_mi INTEGER DEFAULT 0,
        paket_seans INTEGER DEFAULT 8,
        paket_hafta INTEGER DEFAULT 6,
        bireysel_fiyat REAL DEFAULT 0,
        grup2_fiyat REAL DEFAULT 0,
        grup3_fiyat REAL DEFAULT 0,
        terapist_prim_orani REAL DEFAULT 0,
        aktif INTEGER DEFAULT 1, takvim_rengi TEXT DEFAULT '#3b82f6', hediye_seans INTEGER DEFAULT 0,
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
CREATE TABLE hizmet_terapistleri(hizmet_id INTEGER NOT NULL REFERENCES hizmet_alanlari(id) ON DELETE CASCADE,terapist_id INTEGER NOT NULL REFERENCES terapistler(id),PRIMARY KEY(hizmet_id,terapist_id));
CREATE TABLE kasa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        tur TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT DEFAULT '',
        kaynak TEXT DEFAULT 'manuel'
    , kaynak_id INTEGER);
CREATE TABLE kayit_islemleri(istek_id TEXT PRIMARY KEY, sonuc TEXT NOT NULL);
CREATE TABLE kaynak_rezervasyonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kaynak_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        baslik TEXT NOT NULL,
        tip TEXT DEFAULT 'manuel',
        danisan_id INTEGER,
        terapist_id INTEGER,
        meta_json TEXT DEFAULT '',
        FOREIGN KEY(kaynak_id) REFERENCES kaynaklar(id) ON DELETE CASCADE
    );
CREATE TABLE kaynaklar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        tur TEXT DEFAULT 'ekipman',
        renk TEXT DEFAULT '#0ea5e9',
        kapasite INTEGER DEFAULT 1,
        bagli_oda_id INTEGER,
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
CREATE TABLE mesaj_kayitlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        kanal TEXT NOT NULL,
        hedef_turu TEXT DEFAULT '',
        hedef_id INTEGER,
        hedef_ad TEXT DEFAULT '',
        hedef_iletisim TEXT DEFAULT '',
        konu TEXT DEFAULT '',
        metin TEXT DEFAULT '',
        durum TEXT DEFAULT 'hazirlandi',
        meta_json TEXT DEFAULT ''
    );
CREATE TABLE mesaj_sablonlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kod TEXT UNIQUE,
        ad TEXT NOT NULL,
        kanal TEXT DEFAULT 'whatsapp',
        konu TEXT DEFAULT '',
        metin TEXT NOT NULL,
        sistem INTEGER DEFAULT 0,
        aktif INTEGER DEFAULT 1
    );
CREATE TABLE odalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL UNIQUE,
        renk TEXT DEFAULT '#64748b',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    , kategori TEXT DEFAULT 'uygulama', kapasite INTEGER DEFAULT 1, ozellikler TEXT DEFAULT '');
CREATE TABLE odemeler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER,
        tarih TEXT NOT NULL,
        tutar REAL NOT NULL,
        yontem TEXT DEFAULT 'nakit',
        notlar TEXT DEFAULT ''
    , seans_id INTEGER REFERENCES seanslar(id) ON DELETE CASCADE, paket_id INTEGER REFERENCES pilates_paketleri(id) ON DELETE CASCADE);
CREATE TABLE online_talepler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        telefon TEXT DEFAULT '',
        email TEXT DEFAULT '',
        hizmet_adi TEXT DEFAULT '',
        tercih_tarih TEXT DEFAULT '',
        tercih_saat TEXT DEFAULT '',
        notlar TEXT DEFAULT '',
        durum TEXT DEFAULT 'yeni',
        token TEXT DEFAULT '',
        olusturma_tarihi TEXT DEFAULT (datetime('now','localtime'))
    );
CREATE TABLE otomasyon_kurallari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kod TEXT UNIQUE,
        ad TEXT NOT NULL,
        tur TEXT NOT NULL,
        kanal TEXT DEFAULT 'whatsapp',
        sablon_kod TEXT DEFAULT '',
        ayar_json TEXT DEFAULT '{}',
        aktif INTEGER DEFAULT 1,
        son_calisma TEXT DEFAULT ''
    );
CREATE TABLE pilates_grup_uyeleri(grup_id INTEGER NOT NULL REFERENCES pilates_gruplari(id),danisan_id INTEGER NOT NULL REFERENCES danisanlar(id),aktif INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(grup_id,danisan_id));
CREATE TABLE pilates_gruplari(id INTEGER PRIMARY KEY,ad TEXT NOT NULL,kapasite INTEGER NOT NULL,aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE pilates_paketleri(
                id INTEGER PRIMARY KEY AUTOINCREMENT, danisan_id INTEGER NOT NULL,
                ad TEXT NOT NULL, fiyat REAL NOT NULL DEFAULT 0,
                seans_sayisi INTEGER NOT NULL DEFAULT 8, hediye_seans INTEGER NOT NULL DEFAULT 0,
                baslangic TEXT NOT NULL, bitis TEXT NOT NULL, grup_turu TEXT NOT NULL DEFAULT 'bireysel',
                aktif INTEGER NOT NULL DEFAULT 1, legacy INTEGER NOT NULL DEFAULT 0, grup_id INTEGER REFERENCES pilates_gruplari(id),
                FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE);
CREATE TABLE pilates_tarifeleri(id INTEGER PRIMARY KEY AUTOINCREMENT,
              ad TEXT NOT NULL, seans_sayisi INTEGER NOT NULL, hediye_seans INTEGER NOT NULL DEFAULT 0,
              hafta INTEGER NOT NULL, bireysel REAL NOT NULL, grup2 REAL NOT NULL, grup3 REAL NOT NULL, aktif INTEGER NOT NULL DEFAULT 1);
CREATE TABLE pilates_uyeleri(danisan_id INTEGER PRIMARY KEY REFERENCES danisanlar(id), kayit_tarihi TEXT NOT NULL);
CREATE TABLE portal_erisimleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        token TEXT NOT NULL UNIQUE,
        aktif INTEGER DEFAULT 1,
        olusturma_tarihi TEXT NOT NULL,
        son_gecerlilik TEXT DEFAULT '',
        son_giris TEXT DEFAULT '', dokum_baslangic TEXT DEFAULT '', dokum_bitis TEXT DEFAULT '', gelecek_bitis TEXT DEFAULT '', paylas_rapor INTEGER DEFAULT 0, paylas_olcum INTEGER DEFAULT 0,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id) ON DELETE CASCADE
    );
CREATE TABLE randevular (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        tarih TEXT NOT NULL,
        saat TEXT NOT NULL,
        sure_dk INTEGER DEFAULT 45,
        durum TEXT DEFAULT 'bekliyor',
        notlar TEXT DEFAULT '', oda_id INTEGER,
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id),
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
CREATE TABLE seanslar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        danisan_id INTEGER NOT NULL,
        terapist_id INTEGER NOT NULL,
        hizmet_id INTEGER,
        tarih TEXT NOT NULL,
        tip TEXT DEFAULT 'normal',
        grup_turu TEXT DEFAULT 'bireysel',
        ucret REAL DEFAULT 0,
        terapist_payi REAL DEFAULT 0,
        isletme_payi REAL DEFAULT 0,
        indirimli INTEGER DEFAULT 0,
        ucret_alindi INTEGER DEFAULT 0,
        tahsilat_tarihi TEXT DEFAULT '',
        soap_s TEXT DEFAULT '',
        soap_o TEXT DEFAULT '',
        soap_a TEXT DEFAULT '',
        soap_p TEXT DEFAULT '', saat TEXT DEFAULT '', sure_dk INTEGER DEFAULT 45, oda_id INTEGER, gelmedi INTEGER DEFAULT 0, gelmedi_nedeni TEXT DEFAULT '', paket_id INTEGER REFERENCES pilates_paketleri(id), hediye INTEGER DEFAULT 0, hak_dustu INTEGER DEFAULT 1, prim_orani REAL DEFAULT 0, anlasilan_ucret REAL DEFAULT 0, program_id TEXT DEFAULT '', planlanan_saat TEXT DEFAULT '', plan_tarihi TEXT DEFAULT '',
        FOREIGN KEY(danisan_id) REFERENCES danisanlar(id),
        FOREIGN KEY(terapist_id) REFERENCES terapistler(id)
    );
CREATE TABLE stok_hareketleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kalem_id INTEGER NOT NULL,
        tarih TEXT NOT NULL,
        tur TEXT NOT NULL,
        miktar REAL NOT NULL,
        birim_fiyat REAL DEFAULT 0,
        aciklama TEXT DEFAULT '',
        FOREIGN KEY(kalem_id) REFERENCES stok_kalemleri(id) ON DELETE CASCADE
    );
CREATE TABLE stok_kalemleri (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        kategori TEXT DEFAULT 'Sarf',
        birim TEXT DEFAULT 'adet',
        mevcut_stok REAL DEFAULT 0,
        min_stok REAL DEFAULT 0,
        birim_maliyet REAL DEFAULT 0,
        barkod TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
CREATE TABLE terapistler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        soyad TEXT DEFAULT '',
        renk TEXT DEFAULT '#f5b800',
        uzmanlik TEXT DEFAULT '',
        aktif INTEGER DEFAULT 1,
        notlar TEXT DEFAULT ''
    );
CREATE TABLE vucut_olcumleri(id INTEGER PRIMARY KEY AUTOINCREMENT,
              danisan_id INTEGER NOT NULL REFERENCES danisanlar(id), tarih TEXT NOT NULL, asama INTEGER NOT NULL,
              gerceklesen INTEGER NOT NULL, hedef TEXT DEFAULT '', notlar TEXT DEFAULT '', boy REAL,kilo REAL,omuz REAL,gogus REAL,bel REAL,karin REAL,kalca REAL,basen REAL,sag_kol REAL,sol_kol REAL,sag_ust_bacak REAL,sol_ust_bacak REAL,sag_diz_ustu REAL,sol_diz_ustu REAL,sag_baldir REAL,sol_baldir REAL, UNIQUE(danisan_id,asama));
INSERT INTO "ayarlar" VALUES('tema','sari');
INSERT INTO "ayarlar" VALUES('klinik_adi','Arte Terapi');
INSERT INTO "ayarlar" VALUES('ozel_renk','#f5b800');
INSERT INTO "ayarlar" VALUES('db_path','/tmp/tmpyjoaw139/seed.db');
INSERT INTO "ayarlar" VALUES('schema_370_initialized','1');
INSERT INTO "ayarlar" VALUES('schema_390','1');
INSERT INTO "ayarlar" VALUES('app_version','3.13.0');
INSERT INTO "ayarlar" VALUES('schema_3100','1');
INSERT INTO "ayarlar" VALUES('schema_3110','1');
INSERT INTO "ayarlar" VALUES('schema_3120','1');
INSERT INTO "ayarlar" VALUES('schema_3130','1');
INSERT INTO "hizmet_alanlari" VALUES(1,1,'Bobath Seansı','ftr',3000.0,0,1,1,0.0,0.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(2,1,'HEP Seansı','ftr',3000.0,0,1,1,0.0,0.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(3,1,'Duyu Bütünleme','ftr',3000.0,0,1,1,0.0,0.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(4,2,'Nöroloji Seansı','ftr',2000.0,0,1,1,0.0,1500.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(5,2,'Ortopedi Seansı','ftr',2000.0,0,1,1,0.0,1500.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(6,2,'Masaj Seansı','masaj',2000.0,0,1,1,0.0,1500.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(7,2,'Pediatri Seansı','ftr',2000.0,0,1,1,0.0,1500.0,0.0,0.0,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(8,3,'Nöroloji FTR','ftr',2000.0,0,1,1,0.0,0.0,0.0,0.5,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(9,3,'Ortopedi FTR','ftr',2000.0,0,1,1,0.0,0.0,0.0,0.5,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(10,3,'Masaj Seansı','masaj',2000.0,0,1,1,0.0,0.0,0.0,0.5,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(11,3,'Pilates (Bireysel)','pilates',6400.0,1,8,6,0.0,0.0,0.0,0.4,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(12,3,'Pilates (2 Kişi)','pilates',0.0,1,8,6,0.0,4000.0,0.0,0.4,1,'#3b82f6',0);
INSERT INTO "hizmet_alanlari" VALUES(13,3,'Pilates (3 Kişi)','pilates',0.0,1,8,6,0.0,0.0,3200.0,0.4,1,'#3b82f6',0);
INSERT INTO "hizmet_terapistleri" VALUES(1,1);
INSERT INTO "hizmet_terapistleri" VALUES(2,1);
INSERT INTO "hizmet_terapistleri" VALUES(3,1);
INSERT INTO "hizmet_terapistleri" VALUES(4,2);
INSERT INTO "hizmet_terapistleri" VALUES(5,2);
INSERT INTO "hizmet_terapistleri" VALUES(6,2);
INSERT INTO "hizmet_terapistleri" VALUES(7,2);
INSERT INTO "hizmet_terapistleri" VALUES(8,3);
INSERT INTO "hizmet_terapistleri" VALUES(9,3);
INSERT INTO "hizmet_terapistleri" VALUES(10,3);
INSERT INTO "hizmet_terapistleri" VALUES(11,3);
INSERT INTO "hizmet_terapistleri" VALUES(12,3);
INSERT INTO "hizmet_terapistleri" VALUES(13,3);
INSERT INTO "kaynaklar" VALUES(1,'Oda 1','oda','#3b82f6',1,1,1,'Oda kaynağı');
INSERT INTO "kaynaklar" VALUES(2,'Oda 2','oda','#10b981',1,2,1,'Oda kaynağı');
INSERT INTO "kaynaklar" VALUES(3,'Pilates Stüdyosu','oda','#8b5cf6',1,3,1,'Oda kaynağı');
INSERT INTO "mesaj_sablonlari" VALUES(1,'randevu_wp','Randevu Hatırlatma','whatsapp','','Merhaba {ad}, {tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır. Uygun değilseniz lütfen bize haber verin. {klinik}',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(2,'randevu_mail','Randevu Hatırlatma','email','Randevu Hatırlatma | {klinik}','Merhaba {ad},

{tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır.
{oda_satiri}
Uygun değilseniz lütfen bize dönüş yapın.

{klinik}',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(3,'pilates_wp','Pilates Paket Uyarısı','whatsapp','','Merhaba {ad}, pilates paketinizde {kalan_seans} seans ve {kalan_gun} gün kaldı. Paket bitiş tarihiniz: {bitis_tarihi}. Uygun gününüzü planlamak için bize yazabilirsiniz. {klinik}',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(4,'toplu_duyuru_mail','Toplu Bilgilendirme','email','{klinik} Bilgilendirme','Merhaba {ad},

{icerik}

{klinik}',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(5,'odeme_wp','Ödeme Hatırlatma','whatsapp','','Merhaba {ad}, {klinik} kayıtlarına göre tahsil edilmemiş {borc_tutar} tutarında seans/paket bakiyeniz görünüyor. Uygun olduğunuzda ödeme planı için bize dönüş yapabilirsiniz.',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(6,'recall_wp','Recall Hatırlatma','whatsapp','','Merhaba {ad}, sizi bir süredir klinikte göremedik. Son seansınızın üzerinden {gecen_gun} gün geçti. Uygun olduğunuzda devam planınızı birlikte netleştirebiliriz. {klinik}',1,1);
INSERT INTO "mesaj_sablonlari" VALUES(7,'24saat_wp','24 Saat Kala WhatsApp','whatsapp','','Merhaba {ad}, yarın {tarih} tarihinde saat {saat} için {terapist} ile {hizmet} seansınız planlıdır. Uygun değilseniz lütfen bize bilgi verin. {oda_satiri} {klinik}',1,1);
INSERT INTO "odalar" VALUES(1,'Uygulama odası 1 (pediatri)','#3b82f6',1,'','uygulama',1,'');
INSERT INTO "odalar" VALUES(2,'Uygulama odası 2 (FTR)','#10b981',1,'','uygulama',1,'');
INSERT INTO "odalar" VALUES(3,'Pilates Stüdyosu','#8b5cf6',1,'','uygulama',1,'');
INSERT INTO "otomasyon_kurallari" VALUES(1,'randevu_yarin','Yarın randevu hatırlatma','randevu_hatirlatma','whatsapp','randevu_wp','{"tip": "yarin_randevu"}',1,'');
INSERT INTO "otomasyon_kurallari" VALUES(2,'odeme_3gun','3 gün geçmiş tahsilat uyarısı','odeme_hatirlatma','whatsapp','odeme_wp','{"gun_esik": 3}',1,'');
INSERT INTO "otomasyon_kurallari" VALUES(3,'recall_21','21 gün pasif danışan recall','recall','whatsapp','recall_wp','{"gun_esik": 21}',0,'');
INSERT INTO "pilates_tarifeleri" VALUES(1,'Pilates (Bireysel)',8,0,6,6400.0,0.0,0.0,1);
INSERT INTO "pilates_tarifeleri" VALUES(2,'Pilates (2 Kişi)',8,0,6,0.0,4000.0,0.0,1);
INSERT INTO "pilates_tarifeleri" VALUES(3,'Pilates (3 Kişi)',8,0,6,0.0,0.0,3200.0,1);
INSERT INTO "stok_kalemleri" VALUES(1,'Dezenfektan','Sarf','adet',4.0,2.0,120.0,'',1,'');
INSERT INTO "stok_kalemleri" VALUES(2,'Kağıt Havlu','Sarf','paket',8.0,3.0,65.0,'',1,'');
INSERT INTO "stok_kalemleri" VALUES(3,'Lateks Eldiven','Sarf','kutu',5.0,2.0,180.0,'',1,'');
INSERT INTO "stok_kalemleri" VALUES(4,'Pilates Bandı','Ekipman','adet',6.0,2.0,250.0,'',1,'');
INSERT INTO "terapistler" VALUES(1,'Terapist 1','','#e67e22','Bobath, HEP, Duyu Bütünleme',1,'');
INSERT INTO "terapistler" VALUES(2,'Terapist 2','','#2980b9','Nöroloji, Ortopedi, Masaj, Pediatri',1,'');
INSERT INTO "terapistler" VALUES(3,'Terapist 3','','#8e44ad','Nöroloji, Ortopedi, Masaj, Pilates',1,'');
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('mesaj_sablonlari',7);
INSERT INTO "sqlite_sequence" VALUES('odalar',3);
INSERT INTO "sqlite_sequence" VALUES('terapistler',3);
INSERT INTO "sqlite_sequence" VALUES('hizmet_alanlari',13);
INSERT INTO "sqlite_sequence" VALUES('kaynaklar',3);
INSERT INTO "sqlite_sequence" VALUES('stok_kalemleri',4);
INSERT INTO "sqlite_sequence" VALUES('otomasyon_kurallari',3);
INSERT INTO "sqlite_sequence" VALUES('pilates_tarifeleri',3);
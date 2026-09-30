import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from test_cloud import HranaSimulator, ROOT
from cloud import db


class ToolsTest(unittest.TestCase):
    def test_real_transport_serialization_and_tls_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            sim=HranaSimulator(tmp+'/wire.db')
            class HTTPS(db.http.client.HTTPSConnection):
                debuglevel=0
                instances=0
                def __init__(self,*args,**kwargs):HTTPS.instances+=1
                def request(self,method,path,body,headers):
                    assert method=='POST' and path=='/v2/pipeline'
                    assert headers['Authorization']=='Bearer test-token'
                    self.result=sim(json.loads(body))
                def getresponse(self):
                    content=json.dumps(self.result).encode()
                    class Response:
                        status=200
                        def read(self):return content
                    return Response()
                def close(self):pass
            with patch('cloud.db.http.client.HTTPSConnection',HTTPS):
                c=db.Connection('libsql://example.turso.io','test-token')
                c.execute('CREATE TABLE t(id INTEGER PRIMARY KEY,data BLOB,name TEXT)')
                c.execute('INSERT INTO t VALUES(?,?,?)',(1,b'\x00\xff','Ölçüm'));c.commit()
                row=c.execute('SELECT * FROM t').fetchone()
                self.assertEqual(dict(row),{'id':1,'data':b'\x00\xff','name':'Ölçüm'})
                self.assertEqual(HTTPS.instances,1)
                c.close()
            sim.close()
    def test_backup_migration_preserves_payment_and_report(self):
        spec=importlib.util.spec_from_file_location('admin_tools',ROOT/'scripts/cloud_admin.py')
        admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            with patch.dict(os.environ,{'ARTE_CLOUD':'0','VERCEL':'0','ARTE_DB_PATH':str(folder/'local.db')}):
                app=runpy.run_path(str(ROOT/'app.py'));app['init_db']()
                did=app['danisan_ekle']({'ad':'Aktarım test','terapist_id':1})
                app['odeme_ekle']({'danisan_id':did,'tarih':'2026-09-30','tutar':500})
                blob=b'%PDF-1.4\n%%EOF'
                rid=app['rapor_pdf_kaydet']({'danisan_id':did,'dosya_adi':'rapor.pdf','base64':base64.b64encode(blob).decode()})
                before=app['backup_bytes']();(folder/'backup.zip').write_bytes(before)
            with patch('getpass.getpass',return_value='New-password-123456'):
                admin.prepare_import(folder/'backup.zip',folder/'migration.sql')
            c=sqlite3.connect(':memory:');c.executescript((folder/'migration.sql').read_text())
            self.assertEqual(c.execute('SELECT tutar FROM odemeler').fetchone()[0],500)
            self.assertEqual(c.execute('SELECT data FROM cloud_pdf_chunks WHERE report_id=?',(rid,)).fetchone()[0],blob)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual((folder/'backup.zip').read_bytes(),before)
            c.close()

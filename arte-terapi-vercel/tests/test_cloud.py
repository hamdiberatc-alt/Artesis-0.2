"""Cloud contract tests. Uses real HTTP, a local Hrana protocol simulator,
SQLite and the actual application; no live Turso/Vercel account is required.
"""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import secrets
import sqlite3
import sys
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cloud import db
from cloud.runtime import ensure_schema, export_backup


class HranaSimulator:
    def __init__(self, path): self.path, self.connections = path, {}
    def reset_metrics(self): self.connects=0;self.roundtrips=0
    def __call__(self, payload):
        if hasattr(self,'roundtrips'): self.roundtrips+=1
        baton = payload.get('baton')
        if baton:
            if baton not in self.connections: raise RuntimeError('Expired baton')
            c = self.connections[baton]
        else:
            if hasattr(self,'connects'): self.connects+=1
            baton = secrets.token_hex(16)
            c = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
            self.connections[baton] = c
        results = []
        for request in payload['requests']:
            if request['type'] == 'close':
                c.close(); del self.connections[baton]; baton = None
                results.append({'type': 'ok', 'response': {'type': 'close'}})
                continue
            try:
                stmt = request['stmt']
                params = [db.decode(x) for x in stmt.get('args', [])]
                if 'named_args' in stmt: params = {v['name']: db.decode(v['value']) for v in stmt['named_args']}
                cur = c.execute(stmt['sql'], params)
                result = {'cols': [{'name': x[0]} for x in cur.description or []],
                    'rows': [[db.encode(v) for v in r] for r in cur.fetchall()],
                    'affected_row_count': max(cur.rowcount, 0), 'last_insert_rowid': str(cur.lastrowid) if cur.lastrowid else None}
                results.append({'type': 'ok', 'response': {'type': 'execute', 'result': result}})
            except sqlite3.Error as e:
                results.append({'type': 'error', 'error': {'code': e.sqlite_errorname, 'message': str(e)}})
        return {'baton': baton, 'base_url': None, 'results': results}
    def dump_sql(self):
        c = sqlite3.connect(self.path)
        try: return '\n'.join(c.iterdump())
        finally: c.close()
    def close(self):
        for c in self.connections.values(): c.close()
        self.connections.clear()


class CloudTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sim = HranaSimulator(self.tmp.name+'/remote.db')
        self.connect_patch = patch.object(db, 'connect', self.connect)
        self.connect_patch.start()
        self.env = patch.dict(os.environ, {'ARTE_CLOUD': '1', 'ARTE_ADMIN_PASSWORD': 'Test-passphrase-12345'})
        self.env.start()
        self.addCleanup(self.cleanup_cloud)
        self.app = runpy.run_path(str(ROOT/'app.py'))
        self.app['init_db']()
    def connect(self):
        c = db.Connection('https://test.turso.io', 'fake', transport=self.sim)
        c.execute('PRAGMA foreign_keys=ON')
        return c
    def cleanup_cloud(self):
        self.connect_patch.stop();self.env.stop();self.sim.close();self.tmp.cleanup()
    def test_import_never_writes_to_filesystem(self):
        with patch('os.makedirs', side_effect=AssertionError('Cloud wrote to disk')):
            m = runpy.run_path(str(ROOT/'app.py'))
            m['init_db']()
            self.assertEqual(m['DB_PATH'], 'cloud://arteterapi')
    def test_rollback_and_constraint(self):
        c = self.connect()
        c.execute('BEGIN IMMEDIATE')
        c.execute("INSERT INTO danisanlar(ad,terapist_id) VALUES('Test',1)")
        c.rollback()
        self.assertEqual(c.execute('SELECT COUNT(*) FROM danisanlar').fetchone()[0],0)
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute('INSERT INTO hizmet_terapistleri VALUES(99999,1)')
        c.rollback();c.close()
    def test_persistent_data_new_worker_and_pdf_export(self):
        a=self.app
        did=a['danisan_ekle']({'ad':'Bulut Test','terapist_id':1})
        blob=b'%PDF-1.4\n'+b'x'*300000
        rid=a['rapor_pdf_kaydet']({'danisan_id':did,'dosya_adi':'test.pdf','base64':base64.b64encode(blob).decode()})
        second=runpy.run_path(str(ROOT/'app.py'));second['init_db']()
        self.assertEqual(second['danisan_detay'](did)['ad'],'Bulut Test')
        self.assertEqual(second['read_report_blob']({'id':rid}),blob)
        with zipfile.ZipFile(io.BytesIO(second['backup_bytes']())) as z:
            self.assertEqual(z.read('rapor_pdfler/'+str(rid)+'.pdf'),blob)
            c=sqlite3.connect(':memory:');c.deserialize(z.read('arteterapi.db'))
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok');c.close()
        second['rapor_pdf_sil'](rid)
        self.assertIsNone(second['read_report_blob']({'id':rid}))
    def test_idempotent_init_and_password_not_overwritten(self):
        stored=self.app['ayar_al']('admin_password_hash')
        os.environ['ARTE_ADMIN_PASSWORD']='Different-password-12345'
        m=runpy.run_path(str(ROOT/'app.py'));m['init_db']()
        self.assertEqual(m['ayar_al']('admin_password_hash'),stored)
    def test_configuration_fails_closed(self):
        os.environ['ARTE_ADMIN_PASSWORD']='short'
        m=runpy.run_path(str(ROOT/'app.py'))
        with self.assertRaises(ValueError):m['init_db']()
    def test_authenticated_get_reuses_one_connection(self):
        token='read-request-session'
        c=self.connect()
        c.execute('INSERT INTO auth_sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),'csrf',9999999999))
        c.commit();c.close();self.sim.reset_metrics()
        handler=self.app['Handler'].__new__(self.app['Handler'])
        handler.path='/api/bootstrap'
        handler.headers={'Cookie':'arte_session='+token}
        handler.client_address=('127.0.0.1',0)
        responses=[];handler._send=lambda body,status=200,**kwargs:responses.append((body,status))
        handler.do_GET()
        self.assertEqual(responses[-1][1],200)
        self.assertEqual(self.sim.connects,1)
        self.assertEqual(self.sim.roundtrips,10)
        self.assertEqual(self.sim.connections,{})
    def test_http_auth_csrf_and_setup_block(self):
        import http.client
        server=ThreadingHTTPServer(('127.0.0.1',0),self.app['Handler'])
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def request(path,data=None,headers=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
            conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json',**(headers or {})})
            res=conn.getresponse();result=(res.status,res.read(),dict(res.getheaders()));conn.close();return result
        try:
            self.assertEqual(request('/api/bootstrap')[0],401)
            self.assertEqual(request('/api/setup',{'password':'overwrite'})[0],403)
            status,body,headers=request('/api/login',{'password':'Test-passphrase-12345'})
            self.assertEqual(status,200,body);self.assertIn('Secure',headers['Set-Cookie'])
            cookie=headers['Set-Cookie'].split(';')[0];csrf=json.loads(body)['csrf']
            self.assertEqual(request('/api/bootstrap',headers={'Cookie':cookie})[0],200)
            payload={'kind':'danisanlar','data':{'ad':'HTTP test','terapist_id':1}}
            self.assertEqual(request('/api/save',payload,{'Cookie':cookie})[0],403)
            self.assertEqual(request('/api/save',payload,{'Cookie':cookie,'X-CSRF-Token':csrf})[0],200)
            self.assertEqual(request('/favicon.ico')[0],204)
        finally:server.shutdown();server.server_close()
    def test_no_write_retry_after_transport_failure(self):
        calls=[]
        def fail(payload):calls.append(payload);raise OSError('network')
        c=db.Connection('https://test.turso.io','fake',transport=fail)
        with self.assertRaises(sqlite3.OperationalError):c.execute('INSERT INTO x VALUES(1)')
        with self.assertRaises(sqlite3.OperationalError):c.execute('INSERT INTO x VALUES(1)')
        self.assertEqual(len(calls),1)

if __name__=='__main__': unittest.main()


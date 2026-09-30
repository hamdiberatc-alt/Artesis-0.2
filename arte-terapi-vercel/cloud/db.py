"""Small synchronous DB-API adapter for libSQL's documented Hrana v2 API.

Never retries a write: an interrupted COMMIT has an unknown outcome. A baton
keeps every transaction on the same remote connection; no local DB fallback.
"""
import base64
import json
import http.client
import math
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request


def encode(value):
    if value is None: return {'type': 'null'}
    if isinstance(value, bool): value = int(value)
    if isinstance(value, int): return {'type': 'integer', 'value': str(value)}
    if isinstance(value, float):
        if not math.isfinite(value): raise ValueError('Sonlu sayı gerekli.')
        return {'type': 'float', 'value': value}
    if isinstance(value, bytes):
        return {'type': 'blob', 'base64': base64.b64encode(value).decode()}
    if isinstance(value, str): return {'type': 'text', 'value': value}
    raise TypeError('Desteklenmeyen SQL parametresi.')


def decode(value):
    kind = value['type']
    if kind == 'null': return None
    if kind == 'integer': return int(value['value'])
    if kind == 'float': return float(value['value'])
    if kind == 'blob': return base64.b64decode(value['base64'])
    return value['value']


class Row:
    def __init__(self, names, values): self.names, self.values = names, values
    def keys(self): return self.names
    def __getitem__(self, key):
        if isinstance(key, (int, slice)): return self.values[key]
        return self.values[self.names.index(key)]
    def __iter__(self): return iter(self.values)
    def __len__(self): return len(self.values)


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.rowcount = -1
        self.lastrowid = None
        self.description = None
    def execute(self, sql, parameters=()):
        result = self.connection._execute(sql, parameters)
        names = [c['name'] for c in result.get('cols', [])]
        self.description = [(n, None, None, None, None, None, None) for n in names] or None
        self.rows = [Row(names, [decode(v) for v in r]) for r in result.get('rows', [])]
        self.rowcount = result.get('affected_row_count', 0)
        rowid = result.get('last_insert_rowid')
        self.lastrowid = int(rowid) if rowid is not None else None
        return self
    def executemany(self, sql, parameters):
        count = 0
        for params in parameters:
            self.execute(sql, params)
            count += max(0, self.rowcount)
        self.rowcount = count
        return self
    def fetchone(self): return self.rows.pop(0) if self.rows else None
    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows
    def fetchmany(self, size=1):
        rows, self.rows = self.rows[:size], self.rows[size:]
        return rows
    def __iter__(self):
        while self.rows: yield self.fetchone()
    def close(self): self.rows = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise sqlite3.OperationalError('Veritabanı yönlendirmesi reddedildi.')


class Connection:
    def __init__(self, url=None, token=None, transport=None):
        self.url = (url or os.getenv('TURSO_DATABASE_URL', '')).strip()
        self.token = token or os.getenv('TURSO_AUTH_TOKEN', '')
        self.url = re.sub(r'^(libsql|turso)://', 'https://', self.url).rstrip('/')
        parsed = urllib.parse.urlparse(self.url)
        if not transport and (parsed.scheme != 'https' or not parsed.hostname or
                              parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('TURSO_DATABASE_URL geçerli bir HTTPS/libSQL adresi olmalı.')
        if not self.token: raise ValueError('TURSO_AUTH_TOKEN eksik.')
        self.origin = parsed.netloc
        self.http = None
        self.baton = None
        self.in_transaction = False
        self.closed = False
        self.failed = False
        self.row_factory = Row
        self.transport = transport
        self.opener = urllib.request.build_opener(NoRedirect())
    def _request(self, requests):
        if self.closed or self.failed:
            raise sqlite3.OperationalError('Veritabanı bağlantısı kapalı; işlemi yeniden kontrol edin.')
        payload = {'baton': self.baton, 'requests': requests}
        try:
            if self.transport:
                result = self.transport(payload)
            else:
                parsed = urllib.parse.urlparse(self.url)
                if self.http is None:
                    self.http = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=15)
                # Reuse TLS connection during an interactive transaction; no retries.
                self.http.request('POST', parsed.path.rstrip('/') + '/v2/pipeline',
                    body=json.dumps(payload, allow_nan=False).encode(),
                    headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
                response = self.http.getresponse()
                content = response.read()
                if response.status != 200:
                    raise OSError('Remote database HTTP error')
                result = json.loads(content)
            self.baton = result.get('baton')
            if result.get('base_url'):
                target = urllib.parse.urlparse(result['base_url'])
                # Only the configured trusted database origin can receive its token.
                allowed_host = target.netloc == self.origin or (self.origin.endswith('.turso.io') and (target.hostname or '').endswith('.turso.io'))
                if target.scheme != 'https' or not allowed_host or target.username or target.password or target.query or target.fragment:
                    raise sqlite3.OperationalError('Beklenmeyen veritabanı bağlantı adresi.')
                new_url = result['base_url'].rstrip('/')
                if new_url != self.url and self.http is not None:
                    self.http.close(); self.http = None
                self.url = new_url
            results = result['results']
            for item in results:
                if item['type'] == 'error':
                    error = item['error']
                    if str(error.get('code', '')).startswith('SQLITE_CONSTRAINT'):
                        raise sqlite3.IntegrityError(error.get('message', 'Kayıt çakışması.'))
                    raise sqlite3.OperationalError(error.get('message', 'Veritabanı işlemi başarısız.'))
            return [item['response'] for item in results]
        except (sqlite3.Error, ValueError, TypeError): raise
        except Exception as error:
            self.failed = True
            raise sqlite3.OperationalError('Kalıcı veritabanına erişilemedi. Son işlemin kaydını kontrol edin; otomatik tekrar yapılmadı.') from error
    def _raw(self, sql, parameters=()):
        stmt = {'sql': sql, 'want_rows': True}
        if isinstance(parameters, dict):
            stmt['named_args'] = [{'name': k, 'value': encode(v)} for k, v in parameters.items()]
        else: stmt['args'] = [encode(v) for v in parameters]
        return self._request([{'type': 'execute', 'stmt': stmt}])[0]['result']
    def _execute(self, sql, parameters):
        word = sql.lstrip().split(None, 1)[0].upper().rstrip(';')
        if word in ('INSERT', 'UPDATE', 'DELETE', 'REPLACE') and not self.in_transaction:
            self._raw('BEGIN IMMEDIATE')
            self.in_transaction = True
        result = self._raw(sql, parameters)
        if word == 'BEGIN': self.in_transaction = True
        elif word in ('COMMIT', 'END', 'ROLLBACK'): self.in_transaction = False
        return result
    def cursor(self): return Cursor(self)
    def execute(self, sql, parameters=()): return self.cursor().execute(sql, parameters)
    def executemany(self, sql, parameters): return self.cursor().executemany(sql, parameters)
    def executescript(self, script):
        # Caller owns the transaction. A failing pipeline is rolled back, never committed.
        requests = [{'type': 'execute', 'stmt': {'sql': s, 'want_rows': False}} for s in statements(script)]
        for offset in range(0, len(requests), 100): self._request(requests[offset:offset + 100])
        return self.cursor()
    def dump_sql(self):
        if self.transport and hasattr(self.transport, 'dump_sql'):
            return self.transport.dump_sql()
        req = urllib.request.Request(self.url + '/dump', headers={'Authorization': 'Bearer ' + self.token})
        try:
            with self.opener.open(req, timeout=120) as response:
                return response.read().decode('utf-8')
        except Exception as error:
            raise sqlite3.OperationalError('Bulut yedeği alınamadı; mevcut yedek korunur.') from error

    def commit(self):
        if self.in_transaction:
            self._raw('COMMIT')
            self.in_transaction = False
    def rollback(self):
        if self.in_transaction and not self.failed:
            try: self._raw('ROLLBACK')
            finally: self.in_transaction = False
    def close(self):
        if self.closed: return
        try:
            if self.baton and not self.failed: self._request([{'type': 'close'}])
        finally:
            self.closed = True
            if self.http is not None: self.http.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, *_):
        if exc_type: self.rollback()
        else: self.commit()


def statements(script):
    buf = ''
    for char in script:
        buf += char
        if char == ';' and sqlite3.complete_statement(buf):
            yield buf.strip()
            buf = ''
    if buf.strip(): yield buf.strip()


def connect():
    c = Connection()
    try: c.execute('PRAGMA foreign_keys=ON')
    except Exception:
        c.close()
        raise
    return c

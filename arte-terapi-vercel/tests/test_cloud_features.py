"""Run existing business regressions through the cloud adapter as well."""
import unittest
from datetime import date
from test_cloud import CloudTest
from test_core import AppTest
from test_multi import MultiTest
from test_operations import OperationsTest
from test_pilates import PilatesTest


def setup(self):
    CloudTest.setUp(self)
    self.m = self.app
    self.today = date.today().isoformat()
    self.a = self.call('danisan_ekle', {'ad':'A','terapist_id':1,'terapist_ids':[2,3]})
    self.b = self.call('danisan_ekle', {'ad':'B','terapist_id':2})
    self.srv = None


def teardown(self):
    if self.srv: self.srv.shutdown(); self.srv.server_close()


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    excluded = {'test_auth_http_pdf', 'test_fresh_and_idempotent', 'test_http_statement_requires_auth_and_pdf_scope'}
    for base in (AppTest, MultiTest, OperationsTest, PilatesTest):
        cls = type('Cloud'+base.__name__, (base,), {'setUp':setup,'tearDown':teardown,
            'connect':CloudTest.connect,'cleanup_cloud':CloudTest.cleanup_cloud})
        for name in base.__dict__:
            if name.startswith('test_') and name not in excluded: suite.addTest(cls(name))
    return suite

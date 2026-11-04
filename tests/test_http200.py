"""Exercise HTTP 200 responses that do not contain the promised resource."""
import io
import contextlib
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import acquire_fulltext
import search_europe_pmc


class Reply:
    status = 200

    def __init__(self, body, content_type, extra_bytes=0):
        self.stream = io.BytesIO(body)
        self.headers = {'Content-Type': content_type, 'Content-Length': str(len(body) + extra_bytes)}

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, count): return self.stream.read(count)


def make_source(root):
    source = root / 'source.json'
    source.write_text(json.dumps({'doi': '10.1234/example', 'pmcid': 'PMC123',
                                  'scope': 'eligible', 'access_status': 'allowed', 'open_access': True}))
    return source


class Http200Test(unittest.TestCase):
    def article(self):
        return (b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/example</article-id>'
                b'<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front><body><p>' +
                b'synthetic text ' * 60 + b'</p></body></article>')

    def test_fulltext_truncated_transport_is_not_accepted_even_if_xml_parses(self):
        body = self.article()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Reply(body, 'application/xml', extra_bytes=10)
                result = acquire_fulltext.acquire(make_source(root), root / 'out')
            self.assertEqual(result['status'], 'incomplete_response')
            self.assertEqual(result['http_status'], 200)
            self.assertEqual((result['expected_bytes'], result['received_bytes']), (len(body) + 10, len(body)))
            self.assertFalse((root / 'out/fulltext.xml').exists())
            self.assertEqual((root / 'out/fulltext.xml.partial').read_bytes(), body)

    def test_fulltext_without_content_length_still_accepts_valid_xml(self):
        reply = Reply(self.article(), 'application/xml')
        reply.headers.pop('Content-Length')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = reply
                result = acquire_fulltext.acquire(make_source(root), root / 'out')
            self.assertEqual(result['status'], 'valid_fulltext_xml')
            self.assertNotIn('expected_bytes', result)

    def test_search_truncated_transport_is_not_reported_as_completed(self):
        body = b'{"hitCount":0,"resultList":{"result":[]}}'
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'search'
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Reply(body, 'application/json', 10)):
                with self.assertRaises(ValueError):
                    search_europe_pmc.run('synthetic', output)
            receipt = json.loads((output / 'manifest.json').read_text())
            self.assertEqual((receipt['status'], receipt['http_status']), ('incomplete_response', 200))
            self.assertEqual((output / receipt['partial']).read_bytes(), body)

    def test_xhtml_challenge_is_access_stop_for_search_and_fulltext(self):
        body = b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>captcha required</body></html>'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Reply(body, 'application/xhtml+xml')
                fulltext = acquire_fulltext.acquire(make_source(root), root / 'fulltext')
            self.assertEqual(fulltext['status'], 'access_stop')
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Reply(body, 'application/xhtml+xml')):
                with self.assertRaises(search_europe_pmc.AccessStop):
                    search_europe_pmc.run('synthetic', root / 'search')
            self.assertEqual(json.loads((root / 'search/manifest.json').read_text())['status'], 'access_stop')

    def test_unknown_html_is_diagnosed_and_retained(self):
        body = b'<!doctype html><html><body>Library page</body></html>'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Reply(body, 'text/html; charset=utf-8')
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext')
            self.assertEqual((result['status'], result['http_status'], result['content_type']),
                             ('unexpected_html', 200, 'text/html'))
            self.assertEqual((root / 'fulltext/fulltext.xml.partial').read_bytes(), body)
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Reply(body, 'text/html')):
                with self.assertRaises(ValueError):
                    search_europe_pmc.run('synthetic', root / 'search')
            receipt = json.loads((root / 'search/manifest.json').read_text())
            self.assertEqual((receipt['status'], receipt['content_type']), ('unexpected_html', 'text/html'))

    def test_invalid_json_with_http200_is_retained_for_diagnosis(self):
        body = b'{"incomplete-json":'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Reply(body, 'application/json')):
                with self.assertRaises(ValueError):
                    search_europe_pmc.run('synthetic', root / 'search')
            receipt = json.loads((root / 'search/manifest.json').read_text())
            self.assertEqual((receipt['status'], receipt['http_status']), ('unexpected_response', 200))
            self.assertEqual((root / 'search' / receipt['partial']).read_bytes(), body)

    def test_access_challenge_takes_precedence_over_length_mismatch(self):
        body = b'<html><body>captcha required</body></html>'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Reply(body, 'text/html', extra_bytes=20)
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext')
            self.assertEqual(result['status'], 'access_stop')
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Reply(body, 'text/html', 20)):
                with self.assertRaises(search_europe_pmc.AccessStop):
                    search_europe_pmc.run('synthetic', root / 'search')

    def test_incomplete_read_saves_partial_and_a_receipt(self):
        class Interrupted(Reply):
            def read(self, count):
                raise http.client.IncompleteRead(b'partial bytes', 10)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Interrupted(b'', 'application/xml')
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext')
            self.assertEqual(result['status'], 'incomplete_response')
            self.assertEqual((root / 'fulltext/fulltext.xml.partial').read_bytes(), b'partial bytes')
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Interrupted(b'', 'application/json')):
                with self.assertRaises(ValueError):
                    search_europe_pmc.run('synthetic', root / 'search')
            receipt = json.loads((root / 'search/manifest.json').read_text())
            self.assertEqual(receipt['status'], 'incomplete_response')
            self.assertEqual((root / 'search' / receipt['partial']).read_bytes(), b'partial bytes')

    def test_incomplete_read_that_contains_challenge_remains_access_stop(self):
        class Interrupted(Reply):
            def read(self, count):
                raise http.client.IncompleteRead(b'<html>captcha required</html>', 10)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Interrupted(b'', 'text/html')
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext')
            self.assertEqual(result['status'], 'access_stop')
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', return_value=Interrupted(b'', 'text/html')):
                with self.assertRaises(search_europe_pmc.AccessStop):
                    search_europe_pmc.run('synthetic', root / 'search')
            self.assertEqual(json.loads((root / 'search/manifest.json').read_text())['status'], 'access_stop')

    def test_page_headers_do_not_leak_between_search_pages(self):
        first = json.dumps({'hitCount': 2, 'resultList': {'result': [{}]}, 'nextCursorMark': 'next'}).encode()
        second = json.dumps({'hitCount': 2, 'resultList': {'result': [{}]}}).encode()
        later = Reply(second, 'application/json')
        later.headers.pop('Content-Length')
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'search'
            with patch.object(search_europe_pmc.urllib.request, 'urlopen', side_effect=[Reply(first, 'application/json'), later]), \
                 patch.object(search_europe_pmc.time, 'sleep'):
                result = search_europe_pmc.run('synthetic', output, max_pages=2, page_size=1)
            self.assertEqual((result['status'], result['rows_received']), ('reported_hit_count_reached', 2))

    def test_failed_next_page_does_not_report_previous_http_status(self):
        first = json.dumps({'hitCount': 2, 'resultList': {'result': [{}]}, 'nextCursorMark': 'next'}).encode()
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'search'
            with patch.object(search_europe_pmc.urllib.request, 'urlopen',
                              side_effect=[Reply(first, 'application/json'), urllib.error.URLError('synthetic DNS failure')]), \
                 patch.object(search_europe_pmc.time, 'sleep'):
                with self.assertRaises(urllib.error.URLError):
                    search_europe_pmc.run('synthetic', output, max_pages=2, page_size=1)
            result = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertNotIn('http_status', result)
            self.assertNotIn('received_bytes', result)

    def test_fulltext_can_use_explicit_server_proxy_without_logging_credentials(self):
        proxy = 'http://synthetic-user:synthetic-password@127.0.0.1:3128'
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'https_proxy': proxy, 'no_proxy': ''}):
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.return_value = Reply(self.article(), 'application/xml')
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext', use_env_proxy=True)
            self.assertEqual(result['status'], 'valid_fulltext_xml')
            self.assertEqual(result['network_mode'], 'environment')
            self.assertEqual(factory.call_args.args[0].proxies['https'], proxy)
            self.assertNotIn('synthetic-password', json.dumps(result))

    def test_cli_passes_explicit_proxy_choice(self):
        args = ['acquire_fulltext.py', '--source', 'source.json', '--out', 'out', '--use-env-proxy']
        with patch.object(sys, 'argv', args), patch.object(acquire_fulltext, 'acquire',
                return_value={'status': 'valid_fulltext_xml', 'attempts': 1}) as acquire, \
                contextlib.redirect_stdout(io.StringIO()):
            acquire_fulltext.main()
        self.assertTrue(acquire.call_args.kwargs['use_env_proxy'])

    def test_stopped_source_cannot_be_opened_with_proxy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = make_source(root)
            values = json.loads(source.read_text())
            values['access_status'] = 'stopped'
            source.write_text(json.dumps(values))
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                result = acquire_fulltext.acquire(source, root / 'fulltext', use_env_proxy=True)
            self.assertEqual(result['status'], 'access_stop')
            factory.assert_not_called()

    def test_proxy_error_does_not_expose_credentials_in_receipt(self):
        secret = 'synthetic-password'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(acquire_fulltext.urllib.request, 'build_opener') as factory:
                factory.return_value.open.side_effect = OSError('proxy credential ' + secret)
                result = acquire_fulltext.acquire(make_source(root), root / 'fulltext', use_env_proxy=True)
            self.assertEqual(result['status'], 'transport_failed')
            self.assertNotIn(secret, json.dumps(result))
            with patch.object(acquire_fulltext.urllib.request, 'ProxyHandler', side_effect=ValueError(secret)):
                setup_error = acquire_fulltext.acquire(root / 'source.json', root / 'setup_error', use_env_proxy=True)
            self.assertEqual(setup_error['status'], 'invalid_source')
            self.assertNotIn(secret, json.dumps(setup_error))


class SandboxHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_GET(self):
        body = (b'<article><front><article-meta><article-id pub-id-type="doi">10.1234/example</article-id>'
                b'<article-id pub-id-type="pmcid">PMC123</article-id></article-meta></front><body><p>' +
                b'synthetic text ' * 60 + b'</p></body></article>')
        if '/search/' in self.path:
            body = b'{"hitCount":0,"resultList":{"result":[]}}'
        if '/gate/' in self.path:
            body = b'<?xml version="1.0"?><html><body>captcha required</body></html>'
        self.send_response(200)
        content_type = 'text/html' if '/gate/' in self.path else 'application/json' if '/search/' in self.path else 'application/xml'
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body) + (10 if '/short/' in self.path else 0)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class LoopbackSandboxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.server = ThreadingHTTPServer(('127.0.0.1', 0), SandboxHandler)
        except PermissionError:
            raise unittest.SkipTest('Loopback binding is restricted in this environment')
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_real_http_200_fulltext_and_search(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'no_proxy': '127.0.0.1', 'NO_PROXY': '127.0.0.1'}):
            root = Path(temp)
            source = make_source(root)
            for name, expected in (('valid', 'valid_fulltext_xml'), ('short', 'incomplete_response'), ('gate', 'access_stop')):
                with self.subTest(name=name), patch.object(acquire_fulltext, 'BASE', self.base + '/' + name + '/'):
                    result = acquire_fulltext.acquire(source, root / ('fulltext_' + name))
                self.assertEqual((result['status'], result['http_status']), (expected, 200))
            for name, expected in (('valid', 'reported_hit_count_reached'), ('short', 'incomplete_response'), ('gate', 'access_stop')):
                out = root / ('search_' + name)
                with self.subTest(name=name), patch.object(search_europe_pmc, 'BASE', self.base + '/search/' + name + '/'):
                    if name == 'valid':
                        result = search_europe_pmc.run('synthetic', out, max_pages=1, page_size=1)
                    else:
                        with self.assertRaises(ValueError):
                            search_europe_pmc.run('synthetic', out, max_pages=1, page_size=1)
                        result = json.loads((out / 'manifest.json').read_text())
                self.assertEqual((result['status'], result['http_status']), (expected, 200))


if __name__ == '__main__':
    unittest.main()

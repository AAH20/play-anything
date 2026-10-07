"""Authentication and malformed-target regressions over real local HTTP."""

import http.client
from functools import partial
from http.server import ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from play_anything.creator_server import CreatorHandler
from play_anything.core.venture_planner import calculate_plan


class CreatorRequestAuthTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(token='local-auth-test', instance='test', events=[],
                                     dispatch=Mock(return_value={'accepted': True}))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0),
                                         partial(CreatorHandler, state=self.state))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close_server)

    def _close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def _request(self, method='POST', target='/api/economics', *, token=None,
                 extra_headers=(), body=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            payload = (json.dumps(body if body is not None else {'selected': []}).encode()
                       if method == 'POST' else None)
            conn.putrequest(method, target, skip_host=True)
            conn.putheader('Host', '127.0.0.1:' + str(self.server.server_address[1]))
            if method == 'POST':
                conn.putheader('X-Play-Token', self.state.token if token is None else token)
                conn.putheader('Content-Length', str(len(payload)))
            for name, value in extra_headers:
                conn.putheader(name, value)
            conn.endheaders(payload)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_nonascii_token_returns_403_without_dispatch_or_echo(self):
        status, body = self._request(token='private-marker-caf\xe9')
        self.assertEqual(status, 403)
        self.assertNotIn('private-marker', json.dumps(body))
        self.state.dispatch.assert_not_called()

    def test_duplicate_security_headers_are_rejected(self):
        host = '127.0.0.1:' + str(self.server.server_address[1])
        for headers in [ [('Host', host)],
                         [('X-Play-Token', self.state.token)],
                         [('Origin', 'http://' + host), ('Origin', 'http://' + host)] ]:
            with self.subTest(headers=headers):
                status, _ = self._request(extra_headers=headers)
                self.assertEqual(status, 403)
                self.state.dispatch.assert_not_called()

    def test_malformed_request_target_is_controlled_on_get_and_post(self):
        for method in ('GET', 'POST'):
            with self.subTest(method=method):
                status, body = self._request(method, 'http://[invalid')
                self.assertEqual(status, 400)
                self.assertIn('target', body['error'])
                self.state.dispatch.assert_not_called()

    def test_accounting_errors_and_supported_results_cross_real_http(self):
        # Exercise the real calculator and response serializer; no provider calls.
        self.state.dispatch.side_effect = lambda route, body: calculate_plan(
            body.get('selected', []), body.get('assumptions'))
        for price in ('1e-320', '1e-999999999'):
            with self.subTest(price=price):
                status, body = self._request(body={'selected': [], 'assumptions': {'price': price}})
                self.assertEqual(status, 400)
                self.assertIn('range', body['error'])
        for price in ('0', '1e-30'):
            with self.subTest(price=price):
                status, body = self._request(body={'selected': [], 'assumptions': {'price': price}})
                self.assertEqual(status, 200)
                json.dumps(body, allow_nan=False)
                self.assertIn('profit', body)

    def test_valid_token_and_same_origin_continue_to_dispatch(self):
        host = '127.0.0.1:' + str(self.server.server_address[1])
        status, body = self._request(extra_headers=[('Origin', 'http://' + host)])
        self.assertEqual((status, body), (200, {'accepted': True}))
        self.state.dispatch.assert_called_once_with('/api/economics', {'selected': []})


if __name__ == '__main__':
    unittest.main()

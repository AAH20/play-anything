"""Creator HTTP JSON contracts, exercised through a real loopback connection."""

from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import math
from threading import Thread
from types import SimpleNamespace
import unittest

from play_anything.creator_server import CreatorHandler


class CreatorJsonBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.dispatched = []

        def dispatch(route, body):
            self.dispatched.append((route, body))
            return {'accepted': True}

        state = SimpleNamespace(token='json-boundary-test', dispatch=dispatch)
        self.server = ThreadingHTTPServer(
            ('127.0.0.1', 0), partial(CreatorHandler, state=state))
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def post(self, payload):
        connection = HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            body = payload if isinstance(payload, bytes) else payload.encode('utf-8')
            connection.request('POST', '/api/json-boundary', body,
                               {'X-Play-Token': 'json-boundary-test',
                                'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_finite_numeric_values_reach_dispatch_unchanged(self):
        status, result = self.post('{"large":1e307,"small":1e-307,"count":123}')
        self.assertEqual((status, result), (200, {'accepted': True}))
        route, body = self.dispatched[0]
        self.assertEqual(route, '/api/json-boundary')
        self.assertTrue(math.isfinite(body['large']))
        self.assertEqual(body['large'], 1e307)
        self.assertEqual(body['small'], 1e-307)
        self.assertEqual(body['count'], 123)
        self.assertIs(type(body['count']), int)

    def test_overflowing_exponents_are_rejected_before_dispatch(self):
        for token in ('1e309', '-1e309', '1e1000000000'):
            with self.subTest(token=token):
                status, result = self.post('{"nested":[{"amount":' + token + '}]}')
                self.assertEqual(status, 400)
                self.assertIn('Non-finite', result['error'])
        self.assertEqual(self.dispatched, [])

    def test_container_depth_boundary_is_explicit_and_cross_version(self):
        # One root object plus 63 arrays is the documented 64-container limit.
        accepted = '{"value":' + '[' * 63 + '0' + ']' * 63 + '}'
        status, result = self.post(accepted)
        self.assertEqual((status, result), (200, {'accepted': True}))
        self.dispatched.clear()
        rejected = '{"value":' + '[' * 64 + '0' + ']' * 64 + '}'
        status, result = self.post(rejected)
        self.assertEqual(status, 400)
        self.assertIn('64 container levels', result['error'])
        self.assertEqual(self.dispatched, [])

    def test_deep_arrays_and_objects_return_json_error_responses(self):
        for nested in ('[' * 3000 + '0' + ']' * 3000,
                       '{"child":' * 3000 + '0' + '}' * 3000):
            with self.subTest(kind=nested[0]):
                status, result = self.post('{"value":' + nested + '}')
                self.assertEqual(status, 400)
                self.assertIn('nesting', result['error'])
                self.assertLess(len(result['error']), 1000)
        self.assertEqual(self.dispatched, [])

    def test_escaped_quotes_backslashes_and_brackets_are_string_data(self):
        text = ('[{' * 1000 + '\\"' + '}]' * 1000 + '\\\\"')
        payload = json.dumps({'description': text, 'other': ['ok']})
        status, result = self.post(payload)
        self.assertEqual((status, result), (200, {'accepted': True}))
        self.assertEqual(self.dispatched[0][1], {'description': text, 'other': ['ok']})

    def test_duplicate_keys_constants_and_malformed_json_stay_rejected(self):
        for payload in ('{"key":1,"key":2}', '{"value":NaN}',
                        '{"value":Infinity}', '{"value":"\\q"}', '{"value":]}'):
            with self.subTest(payload=payload):
                status, result = self.post(payload)
                self.assertEqual(status, 400)
                self.assertIn('error', result)
        self.assertEqual(self.dispatched, [])

    def test_invalid_utf8_body_is_not_dispatched(self):
        status, result = self.post(b'{"value":"\xff"}')
        self.assertEqual(status, 400)
        self.assertIn('error', result)
        self.assertEqual(self.dispatched, [])

    def test_nonobject_root_is_not_dispatched(self):
        for payload in ('[]', '1', 'true', 'null', '"text"'):
            with self.subTest(payload=payload):
                status, result = self.post(payload)
                self.assertEqual(status, 400)
                self.assertIn('Expected a JSON object', result['error'])
        self.assertEqual(self.dispatched, [])


if __name__ == '__main__':
    unittest.main()

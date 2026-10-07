"""Real HTTP response completion and JSON boundaries for local fake agents."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest

from play_anything.creator_server import agent_request


class LocalAgentResponseHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = self.server.response_payload
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        if self.server.include_length:
            self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class CreatorAgentHttpResponseTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), LocalAgentResponseHandler)
        self.server.include_length = True
        self.server.response_payload = b'{}'
        self.thread = Thread(target=self.server.serve_forever,
                             kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()
        self.assertFalse(self.thread.is_alive())

    def request(self, payload, *, include_length=True):
        self.server.response_payload = payload
        self.server.include_length = include_length
        return agent_request(f'http://127.0.0.1:{self.server.server_port}', '/v1/models')

    def test_completed_length_delimited_http10_response_survives_socket_close(self):
        data = {'data': [{'id': 'local-test-model'}]}
        self.assertEqual(self.request(json.dumps(data).encode()), data)

    def test_eof_delimited_response_survives_socket_close(self):
        data = {'data': [{'id': 'local-test-model'}]}
        self.assertEqual(self.request(json.dumps(data).encode(), include_length=False), data)

    def test_agent_json_container_depth_boundary_matches_creator_request_boundary(self):
        valid = ('{"data":' + '[' * 63 + '0' + ']' * 63 + '}').encode()
        self.assertIsInstance(self.request(valid)['data'], list)
        invalid = ('{"data":' + '[' * 64 + '0' + ']' * 64 + '}').encode()
        with self.assertRaisesRegex(ValueError, 'Invalid JSON response'):
            self.request(invalid)

    def test_deep_json_is_a_controlled_error_on_all_supported_decoders(self):
        payload = ('{"data":' + '[' * 3000 + '0' + ']' * 3000 + '}').encode()
        with self.assertRaisesRegex(ValueError, 'Invalid JSON response'):
            self.request(payload)

    def test_overflow_constants_duplicate_keys_and_invalid_utf8_stay_rejected(self):
        for payload in (b'{"data":1e309}', b'{"data":NaN}',
                        b'{"data":1,"data":2}', b'{"data":"\xff"}'):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, 'Invalid JSON response'):
                    self.request(payload)

    def test_quoted_delimiters_do_not_consume_the_nesting_budget(self):
        text = '[{' * 1000 + '\\"' + '}]' * 1000
        data = {'data': [{'id': 'local-test-model', 'description': text}]}
        self.assertEqual(self.request(json.dumps(data).encode()), data)


if __name__ == '__main__':
    unittest.main()

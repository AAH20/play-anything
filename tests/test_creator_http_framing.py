"""Verify the local API rejects transport framing it cannot decode."""

import http.client
from functools import partial
from http.server import ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from play_anything.creator_server import CreatorHandler


class CreatorHTTPFramingTests(unittest.TestCase):
    def setUp(self):
        self.state = SimpleNamespace(token='local-framing-test', dispatch=Mock(
            return_value={'accepted': True}))
        handler = partial(CreatorHandler, state=self.state)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close_server)

    def _close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def _post(self, transfer_encoding=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        payload = b'{"selected":[]}'
        try:
            connection.putrequest('POST', '/api/economics')
            connection.putheader('X-Play-Token', self.state.token)
            connection.putheader('Content-Length', str(len(payload)))
            if transfer_encoding is not None:
                connection.putheader('Transfer-Encoding', transfer_encoding)
            connection.endheaders(payload)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_conflicting_transfer_encoding_is_rejected_before_dispatch(self):
        # This endpoint reads Content-Length bytes; it has no chunk decoder.
        # Accepting the body despite TE would give peers different framing rules.
        for value in ('chunked', 'identity', ''):
            with self.subTest(transfer_encoding=value):
                status, body = self._post(value)
                self.assertEqual(status, 400)
                self.assertIn('Transfer-Encoding', body['error'])
                self.state.dispatch.assert_not_called()

    def test_supported_content_length_request_still_dispatches(self):
        status, body = self._post()
        self.assertEqual((status, body), (200, {'accepted': True}))
        self.state.dispatch.assert_called_once_with('/api/economics', {'selected': []})


if __name__ == '__main__':
    unittest.main()

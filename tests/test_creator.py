import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from play_anything.core.venture_planner import calculate_plan, resolve_modules
from play_anything.creator_server import (
    AGENT_RESPONSE_BODY_TIMEOUT_SECONDS,
    MAX_HTTP_BODY_BYTES,
    CreatorHandler,
    CreatorState,
    agent_request,
    repository_url,
    inspect_repository,
)


class AgentResponseDeadlineTests(unittest.TestCase):
    def test_invalid_key_headers_are_rejected_without_echo_before_transport(self):
        marker = 'example-only-sensitive-marker'
        for suffix in ('\n', '\r\n ', '\t', '\x00', '\x7f', '\u20ac'):
            with self.subTest(suffix=repr(suffix)), patch(
                    'play_anything.creator_server.build_opener') as opener:
                with self.assertRaises(ValueError) as caught:
                    agent_request('http://127.0.0.1:9', '/models', marker + suffix)
                self.assertNotIn(marker, str(caught.exception))
                self.assertIn('API key', str(caught.exception))
                opener.assert_not_called()

    def _request_with_response_body(self, payload):
        class FakeSocket:
            def __init__(self):
                self.timeout = 9.0

            def gettimeout(self):
                return self.timeout

            def settimeout(self, value):
                self.timeout = value

        class Response:
            def __init__(self):
                self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=fake_socket))
                self.remaining = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read1(self, size):
                chunk, self.remaining = self.remaining[:size], self.remaining[size:]
                return chunk

        fake_socket = FakeSocket()
        opener = SimpleNamespace(open=Mock(return_value=Response()))
        with patch('play_anything.creator_server.build_opener', return_value=opener):
            result = agent_request('https://models.example/v1', '/models')
        self.assertEqual(fake_socket.timeout, 9.0)
        return result

    def test_provider_body_read_is_bounded_by_one_total_deadline(self):
        clock = SimpleNamespace(now=0.0)

        def monotonic():
            return clock.now

        class Response:
            def __init__(self):
                self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=socket))
                self.read_sizes = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read1(self, size):
                self.read_sizes.append(size)
                if socket.timeout < 20.0:
                    clock.now += socket.timeout
                    raise TimeoutError('socket operation timed out')
                clock.now += 20.0
                return b'x'

        class Socket:
            def __init__(self):
                self.timeout = 9.0
                self.timeouts = []

            def gettimeout(self):
                return self.timeout

            def settimeout(self, value):
                self.timeout = value
                self.timeouts.append(value)

        socket = Socket()
        response = Response()
        opener = SimpleNamespace(open=Mock(return_value=response))
        with patch('play_anything.creator_server.build_opener', return_value=opener), \
                patch('play_anything.creator_server.time.monotonic', side_effect=monotonic):
            with self.assertRaisesRegex(ValueError, 'response body.*deadline'):
                agent_request('https://models.example/v1', '/models')

        self.assertEqual(socket.timeouts, [45.0, 25.0, 5.0, 9.0])
        self.assertEqual(socket.timeout, 9.0)
        self.assertEqual(response.read_sizes, [64 * 1024] * 3)
        self.assertEqual(clock.now, AGENT_RESPONSE_BODY_TIMEOUT_SECONDS)

    def test_provider_json_preserves_valid_response_shape(self):
        self.assertEqual(
            self._request_with_response_body(b'{"data":[{"id":"fixture"}],"score":1.25}'),
            {'data': [{'id': 'fixture'}], 'score': 1.25},
        )

    def test_provider_json_rejects_nested_duplicate_keys_without_echoing_content(self):
        with self.assertRaisesRegex(ValueError, '^Invalid JSON response from agent endpoint\\.$') as raised:
            self._request_with_response_body(
                b'{"data":{"model":"public-name","model":"secret-provider-value"}}')
        self.assertNotIn('secret-provider-value', str(raised.exception))
        self.assertNotIn('model', str(raised.exception))

    def test_provider_json_rejects_nonfinite_numbers_and_float_overflow(self):
        for number in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            with self.subTest(number=number):
                with self.assertRaisesRegex(
                        ValueError, '^Invalid JSON response from agent endpoint\\.$'):
                    self._request_with_response_body(b'{"score":' + number + b'}')

    def test_provider_json_normalizes_malformed_json_without_echoing_content(self):
        with self.assertRaisesRegex(ValueError, '^Invalid JSON response from agent endpoint\\.$') as raised:
            self._request_with_response_body(b'{"content":"secret-provider-value"')
        self.assertNotIn('secret-provider-value', str(raised.exception))

    def test_provider_json_normalizes_malformed_utf8_without_echoing_bytes(self):
        with self.assertRaisesRegex(ValueError, '^Invalid JSON response from agent endpoint\\.$'):
            self._request_with_response_body(b'{"content":"private-\xff-value"}')



class VentureAccountingTests(unittest.TestCase):
    def test_dependencies_are_transitive_and_stable(self):
        self.assertEqual(resolve_modules(['studio']), ['world', 'skills', 'maps', 'quests', 'studio'])
        self.assertEqual(resolve_modules(['studio', 'studio']), resolve_modules(['studio']))
        with self.assertRaises(ValueError):
            resolve_modules(['invented'])

    def test_accounting_known_scenario(self):
        result = calculate_plan([], dict(active=100, paying=10, price=20, hourly=10,
            maintenance=2, overhead=15, acquisition=10, new_customers=2,
            platform_pct=5, payment_pct=3, transaction_fee=.5, refund_pct=2))
        self.assertEqual(result['gross'], 200)
        self.assertEqual(result['refunds'], 4)
        self.assertEqual(result['fees'], 21)
        self.assertEqual(result['module_variable'], 1)
        self.assertEqual(result['fixed'], 40)
        self.assertEqual(result['contribution'], 174)
        self.assertEqual(result['profit'], 124)
        self.assertEqual(result['setup'], 80)
        self.assertEqual(result['cac'], 5)
        self.assertEqual(result['break_even_payers'], 3)

    def test_ai_costs_and_module_overrides(self):
        result = calculate_plan(['agent'], overrides={'agent': {'hours': 0, 'fixed': 0, 'variable': .50}})
        self.assertEqual(result['ai'], 9)
        row = next(r for r in result['rows'] if r['id'] == 'agent')
        self.assertEqual(row['monthly'], 500)
        self.assertEqual(row['setup'], 0)
        self.assertEqual(calculate_plan([])['ai'], 0)

    def test_zero_sales_and_negative_contribution(self):
        empty = calculate_plan([], dict(active=0, paying=0, new_customers=0))
        self.assertIsNone(empty['break_even_payers'])
        self.assertIsNone(empty['margin_pct'])
        self.assertIsNone(empty['cac'])
        self.assertIsNone(empty['setup_payback_months'])
        negative = calculate_plan([], dict(price=0))
        self.assertLess(negative['profit'], 0)
        self.assertIsNone(negative['break_even_payers'])

    def test_invalid_inputs_rejected(self):
        for values in ({'active': -1}, {'paying': 1001}, {'new_customers': 101},
                       {'price': float('nan')}, {'price': True}, {'paying': .5},
                       {'payment_pct': 101}, {'price': 'abc'}, {'unknown': 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculate_plan([], values)
        with self.assertRaises(ValueError):
            calculate_plan([], overrides={'world': {'variable': -1}})


class CreatorServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = CreatorState(self.root / 'workspaces')

    def test_repo_urls_exclude_credentials_local_files_and_shell_inputs(self):
        self.assertEqual(repository_url('https://github.com/team/project.git'), 'https://github.com/team/project.git')
        for url in ('file:///etc/passwd', 'https://localhost/a/b', 'https://user:secret@github.com/a/b',
                    'https://github.com/a/../b', 'https://github.com/a/b?token=secret',
                    'https://github.com/a/b;touch /tmp/no', 'https://github.com:222/a/b'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                repository_url(url)

    def test_inspection_uses_real_imports_and_license_evidence(self):
        repo = self.root / 'fixture'
        repo.mkdir()
        (repo / 'a.py').write_text('VALUE = 1\n')
        (repo / 'b.py').write_text('import a\n')
        (repo / 'LICENSE').write_text('Fixture license')
        report = inspect_repository(repo, 'fixture')
        self.assertEqual(report['edges'], [('a.py', 'b.py')])
        self.assertEqual(report['licenses'][0]['text'], 'Fixture license')
        self.assertFalse(report['truncated'])
        self.assertEqual(inspect_repository(repo, 'https://github.com/team/example.git')['name'], 'example')

    def test_connections_are_explicit_and_do_not_return_credentials(self):
        handoff = self.state.dispatch('/api/connect', {'mode': 'handoff', 'harness': 'Custom'})
        self.assertEqual(handoff['status'], 'Handoff ready')
        with patch('play_anything.creator_server.agent_request', return_value={'data': [{'id': 'test-model'}]}):
            live = self.state.dispatch('/api/connect', {'mode': 'endpoint', 'endpoint': 'http://localhost:9999/v1', 'api_key': 'secret'})
        self.assertEqual(live['model'], 'test-model')
        self.assertNotIn('secret', json.dumps(live))
        self.assertNotIn('api_key', live)
        with patch('play_anything.creator_server.agent_request', return_value=[]):
            with self.assertRaises(ValueError):
                self.state.dispatch('/api/connect', {'mode': 'endpoint', 'endpoint': 'http://localhost/v1'})

    def test_clone_requires_tutorial_and_permissions(self):
        self.state.analyses['fixture'] = {'path': self.root, 'report': {'url': 'fixture', 'groups': []}, 'completed': False}
        with self.assertRaises(ValueError):
            self.state.dispatch('/api/create', {'analysis_id': 'fixture', 'rights_reviewed': True})
        with self.assertRaises(ValueError):
            self.state.dispatch('/api/tutorial', {'analysis_id': 'fixture', 'answers': {'dependencies': 'nearby'}})
        self.state.dispatch('/api/tutorial', {'analysis_id': 'fixture', 'answers': {'dependencies': 'imports', 'rights': 'review'}})
        with self.assertRaises(ValueError):
            self.state.dispatch('/api/create', {'analysis_id': 'fixture'})
        with patch('play_anything.creator_server.git_clone') as clone:
            result = self.state.dispatch('/api/create', {'analysis_id': 'fixture', 'rights_reviewed': True, 'selected': ['studio']})
            clone.assert_called_once()
        self.assertTrue((Path(result['path']) / 'venture-plan.json').exists())
        self.assertIn('studio', result['plan']['modules'])

    def test_workspace_name_and_source_choices_are_validated(self):
        self.state.analyses['fixture'] = {'path': self.root, 'report': {'url': 'fixture', 'groups': []}, 'completed': True}
        for extra in ({'name': '../escape'}, {'source_modules': ['invented']}):
            with self.assertRaises(ValueError):
                self.state.dispatch('/api/create', {'analysis_id': 'fixture', 'rights_reviewed': True, **extra})

    def test_failed_clone_cleans_only_its_created_directory(self):
        with patch('play_anything.creator_server.git_clone', side_effect=ValueError('offline')):
            with self.assertRaises(ValueError):
                self.state.dispatch('/api/analyze', {'url': 'https://github.com/a/b'})
        self.assertEqual(list(self.state.root.iterdir()), [])

    def test_event_dedup_and_sample_label(self):
        event = {'id': 'one', 'name': 'tutorial_completed', 'demo': True}
        self.state.dispatch('/api/event', event)
        self.state.dispatch('/api/event', event)
        self.assertEqual(self.state.events, [event])

    def test_http_rejects_foreign_origin_or_missing_token(self):
        for headers in ({'Host': '127.0.0.1:8765'}, {'Host': 'evil.example', 'X-Play-Token': self.state.token},
                        {'Host': '127.0.0.1:8765', 'Origin': 'https://evil.example', 'X-Play-Token': self.state.token}):
            handler = CreatorHandler.__new__(CreatorHandler)
            handler.state = self.state
            handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
            handler.headers = headers
            handler.send = Mock()
            handler.do_POST()
            self.assertEqual(handler.send.call_args.args[0], 403)

    def test_http_valid_request_and_static_allowlist(self):
        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        payload = json.dumps({'selected': []}).encode()
        handler.headers = {'Host': '127.0.0.1:8765', 'Content-Length': str(len(payload)), 'X-Play-Token': self.state.token}
        handler.path = '/api/economics'
        handler.rfile = io.BytesIO(payload)
        handler.send = Mock()
        handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0], 200)
        handler.path = '/../../.git/config'
        handler.do_GET()
        self.assertEqual(handler.send.call_args.args[0], 404)

    def _post(self, route, body, *, length=None):
        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        payload = body if isinstance(body, bytes) else body.encode('utf-8')
        headers = {'Host': '127.0.0.1:8765', 'X-Play-Token': self.state.token}
        if length is not False:
            headers['Content-Length'] = str(len(payload) if length is None else length)
        handler.headers = headers
        handler.path = route
        handler.rfile = io.BytesIO(payload)
        handler.request = self._request_socket()
        handler.send = Mock()
        handler.do_POST()
        return handler.send.call_args.args

    @staticmethod
    def _request_socket():
        class FakeSocket:
            def __init__(self):
                self.timeout = 15
                self.timeouts = []

            def gettimeout(self):
                return self.timeout

            def settimeout(self, value):
                self.timeout = value
                self.timeouts.append(value)

        return FakeSocket()

    def test_http_rejects_nonstandard_or_duplicate_content_length(self):
        payload = b'{"selected":[]}'
        status, response = self._post('/api/economics', payload, length='+' + str(len(payload)))
        self.assertEqual(status, 400)
        self.assertIn('Content-Length', response['error'])

        status, _ = self._post('/api/economics', b'{"selected":[]}', length='-1')
        self.assertEqual(status, 400)
        for bad_length in ('nope', '200001', False):
            status, _ = self._post('/api/economics', b'{"selected":[]}', length=bad_length)
            self.assertEqual(status, 400)

        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        payload = b'{"selected":[]}'

        class DuplicateLengthHeaders(dict):
            def get_all(self, name, failobj=None):
                return [str(len(payload)), str(len(payload))] if name == 'Content-Length' else failobj

        handler.headers = DuplicateLengthHeaders({
            'Host': '127.0.0.1:8765', 'X-Play-Token': self.state.token,
            'Content-Length': str(len(payload)),
        })
        handler.path = '/api/economics'
        handler.rfile = io.BytesIO(payload)
        handler.request = self._request_socket()
        handler.send = Mock()
        handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0], 400)

    def test_http_strict_json_rejects_nonfinite_numbers_and_duplicate_keys(self):
        events_before = list(self.state.events)
        status, response = self._post('/api/event', b'{"id":"x","name":"mentor_opened","extra":NaN}')
        self.assertEqual(status, 400)
        self.assertIn('Non-finite', response['error'])
        self.assertEqual(self.state.events, events_before)

        status, response = self._post('/api/economics', b'{"selected":[],"selected":["agent"]}')
        self.assertEqual(status, 400)
        self.assertIn('Duplicate', response['error'])

        for invalid_body in (b'{', b'[]', b'\xff'):
            status, _ = self._post('/api/economics', invalid_body)
            self.assertEqual(status, 400)

    def test_http_invalid_analysis_ids_and_boolean_budgets_are_client_errors(self):
        status, response = self._post('/api/graph', b'{"analysis_id":[]}')
        self.assertEqual(status, 400)
        self.assertIn('analysis identifier', response['error'].lower())

        status, response = self._post('/api/graph', b'{"analysis_id":"missing"}')
        self.assertEqual(status, 400)
        self.assertIn('Analyze a repository first', response['error'])

        status, response = self._post('/api/economics', b'{"selected":[],"hosting":{"seats":true}}')
        self.assertEqual(status, 400)
        self.assertTrue(response['error'])

    def test_http_client_disconnect_during_success_response_is_not_retried_as_400(self):
        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        payload = b'{"selected":[]}'
        handler.headers = {
            'Host': '127.0.0.1:8765', 'Content-Length': str(len(payload)),
            'X-Play-Token': self.state.token,
        }
        handler.path = '/api/economics'
        handler.rfile = io.BytesIO(payload)
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.wfile = Mock()
        handler.wfile.write.side_effect = BrokenPipeError('client disconnected')

        handler.do_POST()

        handler.send_response.assert_called_once_with(200)

    def test_creator_setup_applies_per_connection_socket_timeout(self):
        class FakeSocket:
            def __init__(self):
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def makefile(self, *_args, **_kwargs):
                return io.BytesIO()

            def sendall(self, _payload):
                pass

        handler = CreatorHandler.__new__(CreatorHandler)
        handler.request = FakeSocket()
        handler.server = SimpleNamespace(timeout=None)

        handler.setup()

        self.assertEqual(handler.request.timeout, 15)

    def test_http_body_read_timeout_returns_408(self):
        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        handler.headers = {
            'Host': '127.0.0.1:8765', 'Content-Length': '10',
            'X-Play-Token': self.state.token,
        }
        handler.path = '/api/economics'
        handler.rfile = Mock()
        handler.rfile.read1.side_effect = TimeoutError('read timed out')
        handler.request = self._request_socket()
        handler.send = Mock()
        handler.close_connection = False

        handler.do_POST()

        self.assertEqual(handler.send.call_args.args[0], 408)
        self.assertIn('timed out', handler.send.call_args.args[1]['error'].lower())
        self.assertTrue(handler.close_connection)

    def test_http_trickled_body_hits_absolute_deadline_and_restores_socket_timeout(self):
        from types import SimpleNamespace

        clock = SimpleNamespace(now=0.0, reads=0)

        def monotonic():
            return clock.now

        class TrickleReader:
            def read1(self, size):
                self_size.append(size)
                clock.reads += 1
                clock.now += 10.0
                return b'x'

        self_size = []
        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        handler.headers = {
            'Host': '127.0.0.1:8765', 'Content-Length': '20',
            'X-Play-Token': self.state.token,
        }
        handler.path = '/api/economics'
        handler.rfile = TrickleReader()
        handler.request = self._request_socket()
        handler.send = Mock()
        handler.close_connection = False

        with patch('play_anything.creator_server.time.monotonic', side_effect=monotonic):
            handler.do_POST()

        status, response = handler.send.call_args.args[:2]
        self.assertEqual(status, 408)
        self.assertIn('total', response['error'].lower())
        self.assertTrue(handler.close_connection)
        self.assertEqual(clock.now, 60.0)
        self.assertEqual(clock.reads, 6)
        self.assertTrue(self_size)
        self.assertTrue(all(size <= 64 * 1024 for size in self_size))
        self.assertTrue(any(timeout < 15 for timeout in handler.request.timeouts))
        self.assertEqual(handler.request.timeout, 15)

    def test_http_accepts_exact_maximum_body_split_across_reads(self):
        from types import SimpleNamespace

        prefix = b'{"id":"max-body","name":"mentor_opened","pad":"'
        suffix = b'"}'
        payload = prefix + b'x' * (MAX_HTTP_BODY_BYTES - len(prefix) - len(suffix)) + suffix
        self.assertEqual(len(payload), MAX_HTTP_BODY_BYTES)

        handler = CreatorHandler.__new__(CreatorHandler)
        handler.state = self.state
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8765))
        handler.headers = {
            'Host': '127.0.0.1:8765', 'Content-Length': str(MAX_HTTP_BODY_BYTES),
            'X-Play-Token': self.state.token,
        }
        handler.path = '/api/event'
        handler.rfile = io.BytesIO(payload)
        handler.request = self._request_socket()
        handler.request.timeout = 11
        handler.send = Mock()

        with patch('play_anything.creator_server.time.monotonic', return_value=100.0):
            handler.do_POST()

        self.assertEqual(handler.send.call_args.args[0], 200)
        self.assertIn({'name': 'mentor_opened', 'id': 'max-body', 'demo': False}, self.state.events)
        self.assertEqual(handler.request.timeout, 11)

    def test_creator_session_caps_must_be_positive_integers(self):
        for kwargs in ({'max_analyses': 0}, {'max_connections': True}, {'max_connections': 1.5},
                       {'max_explain_requests': 0}, {'max_explain_requests': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CreatorState(self.root / 'bounded', **kwargs)

    def test_explanation_requests_are_bounded_and_reservations_release(self):
        state = CreatorState(self.root / 'bounded', max_explain_requests=1)
        state.analyses['analysis'] = {'report': {'files': [], 'edges': []}}
        state.connections['connection'] = {
            'mode': 'endpoint', 'endpoint': 'https://models.example/v1',
            'api_key': '', 'model': 'fixture',
        }
        entered = threading.Event()
        release = threading.Event()
        outcomes = []

        def slow_response(*_args, **_kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release explanation worker')
            return {'choices': [{'message': {'content': 'fixture explanation'}}]}

        request = {'analysis_id': 'analysis', 'connection_id': 'connection'}
        with patch('play_anything.creator_server.agent_request', side_effect=slow_response):
            worker = threading.Thread(target=lambda: outcomes.append(
                state.dispatch('/api/explain', request)))
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(ValueError, 'explanation.*limit'):
                state.dispatch('/api/explain', request)
            release.set()
            worker.join(3)

        self.assertFalse(worker.is_alive())
        self.assertEqual(outcomes, [{'explanation': 'fixture explanation'}])
        self.assertEqual(state._pending_explanations, 0)
        with patch('play_anything.creator_server.agent_request', side_effect=ValueError('endpoint failed')):
            with self.assertRaisesRegex(ValueError, 'endpoint failed'):
                state.dispatch('/api/explain', request)
        self.assertEqual(state._pending_explanations, 0)

    def test_analysis_capacity_is_reserved_before_slow_work_and_released(self):
        state = CreatorState(self.root / 'bounded', max_analyses=1)
        entered = threading.Event()
        release = threading.Event()
        outcomes = []

        def slow_inspect(*_args, **_kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release analysis worker')
            return {'analysis': {'status': 'complete'}, 'graph': {}, 'files': [], 'edges': [],
                    'groups': [], 'licenses': [], 'truncated': False, 'python_files': 0, 'name': 'fixture'}

        with patch('play_anything.creator_server.git_clone'), patch(
                'play_anything.creator_server.inspect_repository', side_effect=slow_inspect):
            worker = threading.Thread(target=lambda: outcomes.append(
                state.dispatch('/api/analyze', {'url': 'https://github.com/team/project'})))
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(ValueError, 'session.*limit') as raised:
                state.dispatch('/api/analyze', {'url': 'https://github.com/team/other'})
            self.assertIn('restart', str(raised.exception).lower())
            release.set()
            worker.join(3)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(state.analyses), 1)
        self.assertEqual(state._pending_analyses, 0)

    def test_failed_slow_analysis_releases_its_reserved_capacity(self):
        state = CreatorState(self.root / 'bounded', max_analyses=1)
        report = {'analysis': {'status': 'complete'}, 'graph': {}, 'files': [], 'edges': [],
                  'groups': [], 'licenses': [], 'truncated': False, 'python_files': 0, 'name': 'fixture'}
        with patch('play_anything.creator_server.git_clone', side_effect=[ValueError('clone failed'), None]), patch(
                'play_anything.creator_server.inspect_repository', return_value=report):
            with self.assertRaisesRegex(ValueError, 'clone failed'):
                state.dispatch('/api/analyze', {'url': 'https://github.com/team/project'})
            state.dispatch('/api/analyze', {'url': 'https://github.com/team/project'})
        self.assertEqual(len(state.analyses), 1)
        self.assertEqual(state._pending_analyses, 0)

    def test_connection_capacity_is_reserved_during_endpoint_verification(self):
        state = CreatorState(self.root / 'bounded', max_connections=1)
        entered = threading.Event()
        release = threading.Event()
        outcomes = []

        def slow_models(*_args, **_kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release connection worker')
            return {'data': [{'id': 'fixture-model'}]}

        with patch('play_anything.creator_server.agent_request', side_effect=slow_models):
            worker = threading.Thread(target=lambda: outcomes.append(state.dispatch(
                '/api/connect', {'mode': 'endpoint', 'endpoint': 'https://models.example/v1'})))
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaisesRegex(ValueError, 'session.*limit'):
                state.dispatch('/api/connect', {'mode': 'handoff'})
            release.set()
            worker.join(3)

        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(state.connections), 1)
        self.assertEqual(state._pending_connections, 0)

    def test_failed_connection_verification_releases_its_reserved_capacity(self):
        state = CreatorState(self.root / 'bounded', max_connections=1)
        with patch('play_anything.creator_server.agent_request', side_effect=ValueError('endpoint unavailable')):
            with self.assertRaisesRegex(ValueError, 'endpoint unavailable'):
                state.dispatch('/api/connect', {
                    'mode': 'endpoint', 'endpoint': 'https://models.example/v1',
                })
        result = state.dispatch('/api/connect', {'mode': 'handoff'})
        self.assertEqual(result['status'], 'Handoff ready')
        self.assertEqual(len(state.connections), 1)
        self.assertEqual(state._pending_connections, 0)

    def test_workspace_write_errors_do_not_expose_private_paths_over_http(self):
        private_path = self.state.root / 'private-workspaces'
        self.state.analyses['fixture'] = {
            'path': self.root / 'repository',
            'report': {'url': 'https://github.com/team/project', 'groups': []},
            'completed': True,
        }
        original_write_text = Path.write_text

        def fail_plan_write(candidate, data, *args, **kwargs):
            if candidate.name == 'venture-plan.json':
                raise PermissionError(f'permission denied: {private_path / candidate.name}')
            return original_write_text(candidate, data, *args, **kwargs)

        body = json.dumps({
            'analysis_id': 'fixture', 'rights_reviewed': True, 'name': 'demo',
            'source_modules': [],
        })
        with patch('play_anything.creator_server.git_clone'), patch.object(
                Path, 'write_text', autospec=True, side_effect=fail_plan_write):
            status, response = self._post('/api/create', body)

        self.assertEqual(status, 400)
        self.assertNotIn(str(private_path), response['error'])
        self.assertIn('Could not write venture workspace', response['error'])


if __name__ == '__main__':
    unittest.main()

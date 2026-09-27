import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from play_anything.core.venture_planner import calculate_plan, resolve_modules
from play_anything.creator_server import CreatorHandler, CreatorState, repository_url, inspect_repository


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


if __name__ == '__main__':
    unittest.main()

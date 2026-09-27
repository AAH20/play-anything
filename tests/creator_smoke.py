"""Optional integration smoke: real HTTP and Git with a local model fixture.

Run: python3 tests/creator_smoke.py
Requires permission to bind loopback ports and an installed Git executable.
No remote model calls or remote repository access are needed.
"""
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from play_anything.creator_server import CreatorHandler, CreatorState, inspect_repository


class ModelFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        assert self.path == '/v1/models'
        self.respond({'data': [{'id': 'fixture-model'}]})

    def do_POST(self):
        assert self.path == '/v1/chat/completions'
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert 'a.py' in payload['messages'][1]['content']
        self.respond({'choices': [{'message': {'content': 'Fixture explanation: b.py imports a.py.'}}]})


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        repo = root / 'source'
        repo.mkdir()
        (repo / 'a.py').write_text('VALUE = 1\n')
        (repo / 'b.py').write_text('import a\n')
        (repo / 'LICENSE').write_text('Fixture license for integration testing.\n')
        for command in (['git', 'init', '-q'], ['git', 'add', '.'],
                        ['git', '-c', 'user.name=Creator Test', '-c', 'user.email=test@example.invalid',
                         '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture']):
            subprocess.run(command, cwd=repo, check=True, capture_output=True)
        state = CreatorState(root / 'workspaces')
        state.analyses['fixture'] = {'path': repo, 'report': inspect_repository(repo, 'local:test-fixture'), 'completed': False}
        app = ThreadingHTTPServer(('127.0.0.1', 0), partial(CreatorHandler, state=state))
        model = ThreadingHTTPServer(('127.0.0.1', 0), ModelFixture)
        threads = [Thread(target=s.serve_forever, kwargs={'poll_interval': .01}, daemon=True) for s in (app, model)]
        for thread in threads:
            thread.start()
        base = f'http://127.0.0.1:{app.server_port}'
        def request(path, data=None, token=state.token):
            headers = {'Content-Type': 'application/json', 'X-Play-Token': token}
            with urlopen(Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)) as response:
                return json.load(response)
        try:
            session = request('/api/session')
            assert session['token'] == state.token
            try:
                request('/api/economics', {'selected': []}, token='wrong')
                raise AssertionError('CSRF token was not checked')
            except HTTPError as error:
                assert error.code == 403
            connection = request('/api/connect', {'mode': 'endpoint', 'endpoint': f'http://127.0.0.1:{model.server_port}/v1'})
            explanation = request('/api/explain', {'analysis_id': 'fixture', 'connection_id': connection['id']})
            assert 'b.py imports a.py' in explanation['explanation']
            request('/api/tutorial', {'analysis_id': 'fixture', 'answers': {'dependencies': 'imports', 'rights': 'review'}})
            result = request('/api/create', {'analysis_id': 'fixture', 'rights_reviewed': True,
                                            'name': 'fixture-venture', 'selected': ['studio'], 'source_modules': ['root files']})
            clone = Path(result['repository'])
            assert (clone / 'a.py').read_text() == 'VALUE = 1\n'
            assert (clone / 'LICENSE').exists()
            assert (clone / '.git').exists()
            assert (Path(result['path']) / 'venture-plan.json').exists()
            assert (Path(result['path']) / 'AGENT-HANDOFF.md').exists()
            print('PASS: HTTP session, request protection, live fixture model connection/explanation, tutorial, real Git clone, license preservation, plan and handoff.')
        finally:
            for server in (app, model):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()


if __name__ == '__main__':
    main()

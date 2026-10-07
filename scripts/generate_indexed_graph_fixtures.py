"""Generate development-only graph fixtures through the real index CLI.

The destination must not exist. No user repository or private profile is read.
Generation identifiers are intentionally fresh; manifest hashes identify the
exact exported snapshots used by subsequent browser checks.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from play_anything.index_cli import run_index_command


def _invoke(command, arguments):
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = run_index_command(command, list(map(str, arguments)))
    if code:
        raise ValueError(f'Fixture CLI {command} failed: {errors.getvalue().strip()}')
    return json.loads(output.getvalue())


def generate_fixtures(destination):
    """Write four snapshots and a hash manifest to a new directory only."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Fixture destination must not exist; existing data is never overwritten.')
    with tempfile.TemporaryDirectory(prefix='play-anything-fixture-') as directory:
        base = Path(directory)
        root = base / 'indexed-example'
        root.mkdir()
        sources = {'a.py': 'import b\ndef first(): return b.second()\n',
                   'b.py': 'import c\ndef second(): return c.third()\n',
                   'c.py': 'def third(): return 3\n'}
        for name, source in sources.items():
            (root / name).write_text(source, encoding='utf-8')
        arguments = [root, '--database', base / 'index.sqlite']
        _invoke('index-repository', arguments)
        pages = {}
        for filename, offset in [('page-0.json', 0), ('page-1.json', 2)]:
            pages[filename] = _invoke('query-repository', arguments +
                                     ['--view', 'graph', '--limit', 2, '--offset', offset, '--edge-limit', 1])
        invalid = json.loads(json.dumps(pages['page-0.json']))
        invalid['coverage']['returned_nodes'] += 1
        pages['invalid-coverage.json'] = invalid
        hostile = json.loads(json.dumps(pages['page-1.json']))
        hostile['name'] = 'hostile-label-fixture'
        hostile['nodes'][0]['name'] = '<script>alert("fixture")</script>'
        pages['hostile-label.json'] = hostile
    encoded = {name: (json.dumps(snapshot, indent=2, allow_nan=False) + '\n').encode('utf-8')
               for name, snapshot in pages.items()}
    manifest = {'schema_version': 1, 'evidence_type': 'synthetic_index_cli_fixture',
                'source': 'Three generated Python files; no user repository was analyzed.',
                'files': [{'name': name, 'bytes': len(data),
                           'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(encoded.items())]}
    # Exclusive directory and file creation prevent accidental baseline replacement.
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in encoded.items():
        with (destination / name).open('xb') as stream:
            stream.write(data)
    with (destination / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return manifest


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='New directory for synthetic development fixtures')
    args = parser.parse_args(arguments)
    try:
        manifest = generate_fixtures(args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Fixture generation error: {error}\n')
    print(json.dumps(manifest, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

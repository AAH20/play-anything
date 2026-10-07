"""Optional disk-backed repository index commands; no WorldState allocation."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .adapters.repository_index import DEFAULT_MAX_SOURCE_BYTES
from .adapters.repository_store import SQLiteRepositoryStore

DEFAULT_TOTAL_SOURCE_BYTES = 32 * 1024 * 1024


def _positive(value):
    number = int(value)
    if not 1 <= number <= 2**63 - 1:
        raise argparse.ArgumentTypeError('must be an integer from 1 to 9223372036854775807')
    return number


def _page_limit(value):
    number = _positive(value)
    if number > 1000:
        raise argparse.ArgumentTypeError('must be an integer from 1 to 1000')
    return number


def _byte_limit(value):
    number = _positive(value)
    if number > sys.maxsize - 1:
        raise argparse.ArgumentTypeError(f'must not exceed {sys.maxsize - 1}')
    return number


def _nonnegative(value):
    number = int(value)
    if not 0 <= number <= 2**63 - 1:
        raise argparse.ArgumentTypeError('must be an integer from 0 to 9223372036854775807')
    return number


def _edge_limit(value):
    number = _positive(value)
    if number > 10000:
        raise argparse.ArgumentTypeError('must be an integer from 1 to 10000')
    return number


def _source_budget_limit(value):
    number = _nonnegative(value)
    if number > sys.maxsize - 1:
        raise argparse.ArgumentTypeError(f'must not exceed {sys.maxsize - 1}')
    return number


def run_index_command(command, arguments):
    """Return a CLI exit code; JSON results go to stdout, failures to stderr."""
    parser = argparse.ArgumentParser(prog=f'python3 -m play_anything.cli {command}')
    parser.add_argument('root', type=Path, help='Repository identity/path to index or query')
    parser.add_argument('--database', required=True, type=Path, help='SQLite database outside the repository root')
    if command == 'index-repository':
        files = parser.add_mutually_exclusive_group()
        files.add_argument('--max-files', type=_positive, default=10000)
        files.add_argument('--all-files', action='store_true', help='Disable the file-count cap; source byte caps still apply')
        sizes = parser.add_mutually_exclusive_group()
        sizes.add_argument('--max-file-bytes', type=_byte_limit, default=DEFAULT_MAX_SOURCE_BYTES)
        sizes.add_argument('--uncapped-file-bytes', action='store_true')
        budget = parser.add_mutually_exclusive_group()
        budget.add_argument('--max-total-source-bytes', type=_source_budget_limit,
                            default=DEFAULT_TOTAL_SOURCE_BYTES,
                            help='Aggregate source-read budget; 0 inventories without reading source (default 32 MiB)')
        budget.add_argument('--uncapped-total-source-bytes', action='store_true',
                            help='Disable only the aggregate source-read budget; other caps still apply')
    elif command == 'query-repository':
        parser.add_argument('--view', choices=('status', 'files', 'imports', 'dependencies', 'graph'), default='status',
                            help='graph emits importable v1 JSON; other views emit a result envelope')
        parser.add_argument('--path', help='Relative source path for imports/dependencies')
        parser.add_argument('--search', help='Literal case-sensitive path substring, for files or graph')
        parser.add_argument('--direction', choices=('imports', 'imported_by'))
        parser.add_argument('--limit', type=_page_limit, default=100)
        parser.add_argument('--offset', type=_nonnegative, default=0)
        parser.add_argument('--edge-limit', type=_edge_limit, help='Maximum internal edges, only for graph (default 2000)')
    else:
        raise ValueError('Unsupported index command.')
    try:
        args = parser.parse_args(arguments)
        if command == 'query-repository' and args.view == 'graph' and args.offset > 2**53 - 1:
            parser.error('graph offsets must be from 0 to 2**53 - 1 for portable JSON/Graph Studio')
        if command == 'query-repository':
            if args.view == 'dependencies' and not args.path:
                parser.error('--path is required for dependencies')
            if args.search is not None and args.view not in {'files', 'graph'}:
                parser.error('--search is only valid with --view files or graph')
            if args.path is not None and args.view not in {'imports', 'dependencies'}:
                parser.error('--path is only valid with imports or dependencies')
            if args.direction is not None and args.view != 'dependencies':
                parser.error('--direction is only valid with --view dependencies')
            if args.edge_limit is not None and args.view != 'graph':
                parser.error('--edge-limit is only valid with --view graph')
    except SystemExit as error:
        return int(error.code)
    try:
        if command == 'query-repository' and not args.database.is_file():
            raise ValueError('no repository index database exists; run index-repository first')
        with SQLiteRepositoryStore(args.database, read_only=command == 'query-repository') as store:
            if command == 'index-repository':
                result = store.rebuild(args.root, max_files=None if args.all_files else args.max_files,
                                       max_file_bytes=None if args.uncapped_file_bytes else args.max_file_bytes,
                                       max_total_source_bytes=None if args.uncapped_total_source_bytes else args.max_total_source_bytes)
            elif args.view == 'status':
                result = store.status(args.root)
            elif args.view == 'files':
                page = dict(limit=args.limit, offset=args.offset)
                result = store.files(args.root, **page) if args.search is None else store.search_files(args.root, args.search, **page)
            elif args.view == 'imports':
                result = store.imports(args.root, args.path, limit=args.limit, offset=args.offset)
            elif args.view == 'graph':
                result = store.graph_page(args.root, limit=args.limit, offset=args.offset,
                                          max_edges=args.edge_limit or 2000, search=args.search)
            else:
                result = store.dependencies(args.root, args.path, direction=args.direction or 'imports',
                                            limit=args.limit, offset=args.offset)
        output = result if getattr(args, 'view', None) == 'graph' else {'schema_version': 1, 'operation': command,
                          'view': getattr(args, 'view', 'status'), 'result': result}
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, sqlite3.DatabaseError) as error:
        print(f'Repository index error: {error}', file=sys.stderr)
        return 1

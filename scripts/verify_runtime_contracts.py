"""Statically check Python 3.10 syntax and the standard-library import boundary."""

import ast
import json
import os
import stat
from pathlib import Path
import sys


def _read_regular_source(path):
    """Reject special files and avoid following a replaced source symlink."""
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0)
        flags |= getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError('Runtime source is not a regular file.')
        with os.fdopen(descriptor, 'rb') as source:
            descriptor = None
            return source.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _is_regular_file(path):
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _is_directory(path):
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _internal_module_exists(package: Path, module_parts, pruned) -> bool:
    """Check an explicit source module path without importing or following links.

    This recognizes Python source modules, regular packages, and namespace
    package directories; it does not resolve extension modules or symbols.
    """
    if not module_parts or module_parts[0] != package.name:
        return False
    relative_parts = module_parts[1:]
    if any(part in pruned for part in relative_parts) or not _is_directory(package):
        return False
    if not relative_parts:
        return True

    parent = package
    for part in relative_parts[:-1]:
        parent = parent / part
        if not _is_directory(parent):
            return False

    name = relative_parts[-1]
    module_file = parent / (name + '.py')
    package_dir = parent / name
    # A directory without __init__.py is a valid namespace package target.
    return _is_regular_file(module_file) or _is_directory(package_dir)


def audit_runtime(package: Path) -> dict:
    violations = []
    checked = 0
    allowed = sys.stdlib_module_names | {package.name}
    pruned = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'site-dist'}

    def relative_path(value):
        if not value:
            return '.'
        try:
            return Path(value).relative_to(package).as_posix()
        except ValueError:
            return '<outside package>'

    def record_walk_error(error):
        violations.append({
            'file': relative_path(getattr(error, 'filename', None)),
            'kind': 'traversal_error',
            'message': 'Could not enumerate a runtime package directory.',
        })

    for directory, children, files in os.walk(
            package, followlinks=False, onerror=record_walk_error):
        visible_children = []
        for name in sorted(children):
            if name in pruned:
                continue
            child_path = Path(directory) / name
            try:
                is_symlink = child_path.is_symlink()
            except OSError:
                is_symlink = True
            if is_symlink:
                violations.append({
                    'file': relative_path(child_path),
                    'kind': 'skipped_symlink_directory',
                    'message': 'Symlinked runtime directories are not followed by the audit.',
                })
                continue
            visible_children.append(name)
        children[:] = visible_children
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            path = Path(directory) / name
            relative = path.relative_to(package).as_posix()
            checked += 1
            try:
                mode = path.lstat().st_mode
                if not stat.S_ISREG(mode):
                    violations.append({
                        'file': relative, 'kind': 'nonregular_source',
                        'message': 'Runtime source must be a regular file, not a symlink or special file.',
                    })
                    continue
                tree = ast.parse(_read_regular_source(path), filename=relative,
                                 feature_version=(3, 10))
            except (OSError, UnicodeError, SyntaxError, RecursionError) as error:
                violations.append({'file': relative, 'kind': 'syntax_or_read', 'message': str(error)})
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                    for module in names:
                        if (module.split('.')[0] == package.name
                                and not _internal_module_exists(package, module.split('.'), pruned)):
                            violations.append({
                                'file': relative, 'line': node.lineno,
                                'kind': 'missing_internal_import', 'module': module,
                                'message': 'Explicit internal import target has no Python module or package directory.',
                            })
                elif isinstance(node, ast.ImportFrom):
                    # Validate explicit module targets; imported aliases may be package members.
                    if node.level == 0 and node.module:
                        names = [node.module]
                        module = node.module
                        if (module.split('.')[0] == package.name
                                and not _internal_module_exists(package, module.split('.'), pruned)):
                            violations.append({
                                'file': relative, 'line': node.lineno,
                                'kind': 'missing_internal_import', 'module': module,
                                'message': 'Explicit internal import target has no Python module or package directory.',
                            })
                    elif node.level:
                        current_package = [package.name, *Path(relative).parent.parts]
                        ascend = node.level - 1
                        if ascend >= len(current_package):
                            violations.append({
                                'file': relative, 'line': node.lineno,
                                'kind': 'relative_import_escape',
                                'module': node.module,
                                'message': 'Relative import climbs beyond the runtime package root.',
                            })
                        else:
                            base = current_package[:len(current_package) - ascend] if ascend else current_package
                            target = base + (node.module.split('.') if node.module else [])
                            if not _internal_module_exists(package, target, pruned):
                                violations.append({
                                    'file': relative, 'line': node.lineno,
                                    'kind': 'missing_internal_import',
                                    'module': '.'.join(target),
                                    'message': 'Explicit relative import target has no Python module or package directory.',
                                })
                for module in names:
                    if module.split('.')[0] not in allowed:
                        violations.append({'file': relative, 'line': node.lineno,
                                           'kind': 'external_import', 'module': module})
    if checked == 0:
        violations.append({'kind': 'empty_package', 'message': 'No Python runtime files found.'})
    return {'schema_version': 1, 'evidence_type': 'static_runtime_contract',
            'python_syntax_target': '3.10', 'checked_files': checked,
            'violations': violations, 'passed': not violations}


def main() -> int:
    package = Path(__file__).resolve().parents[1] / 'play_anything'
    report = audit_runtime(package)
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())

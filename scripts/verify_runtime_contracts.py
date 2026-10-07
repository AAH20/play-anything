"""Statically check Python 3.10 syntax and the standard-library import boundary."""

import ast
import json
import os
from pathlib import Path
import sys


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
                tree = ast.parse(path.read_text(encoding='utf-8'), filename=relative,
                                 feature_version=(3, 10))
            except (OSError, UnicodeError, SyntaxError) as error:
                violations.append({'file': relative, 'kind': 'syntax_or_read', 'message': str(error)})
                continue
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
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

"""Incremental file summaries with an optional bounded, content-addressed cache.

Only one source file/AST is held during parsing. Consumers may still materialize
the summaries or graph. Non-Python files have measured LOC but no inferred edges.
"""
import ast
from contextlib import closing, nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tokenize


_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".md"}
_EXCLUDED = {"node_modules", "__pycache__", "venv", "dist", "build"}
_CACHE_VERSION = "1"


def _summarize(path, relative_path, content):
    result = {
        "path": relative_path, "lines_of_code": len(content.splitlines()),
        "complexity": 1.0, "imports": [], "analysis": "unparsed_language",
    }
    if path.suffix != ".py":
        return result
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
        source = content.decode(encoding)
        tree = ast.parse(source, filename=relative_path)
    except (SyntaxError, UnicodeError, LookupError, ValueError, RecursionError):
        result["analysis"] = "python_parse_error"
        return result
    decisions = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)
    complexity = 1
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, decisions):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            complexity += 1 + len(node.ifs)
        elif isinstance(node, ast.Match):
            complexity += len(node.cases)
        if isinstance(node, ast.Import):
            imports.extend({"module": alias.name, "level": 0, "names": []}
                           for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append({"module": node.module or "", "level": node.level,
                            "names": [alias.name for alias in node.names]})
    result.update(complexity=float(complexity), imports=imports, analysis="python_ast")
    return result


def iter_repository_summaries(directory_path, max_files=50, *, cache_path=None,
                              cache_max_entries=10000):
    """Yield sorted file summaries; None explicitly removes the file-count limit.

    Cache contents are parser summaries only, not source code. Each key includes
    the repository, relative path, parser version, and SHA-256 of current bytes.
    SQLite setup/read/write failures propagate rather than silently disabling it.
    Symlinks are skipped. A missing/unreadable source is represented explicitly.
    """
    if max_files is not None and (type(max_files) is not int or max_files < 1):
        raise ValueError("max_files must be a positive integer or None")
    if type(cache_max_entries) is not int or cache_max_entries < 1:
        raise ValueError("cache_max_entries must be a positive integer")
    root_path = Path(directory_path).resolve()
    cache_file = Path(cache_path).resolve() if cache_path is not None else None
    context = closing(sqlite3.connect(str(cache_file))) if cache_file else nullcontext(None)
    with context as db:
        if db is not None:
            db.execute("CREATE TABLE IF NOT EXISTS repository_summaries "
                       "(cache_key TEXT PRIMARY KEY, summary TEXT NOT NULL, touched INTEGER NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS repository_summaries_recency "
                       "ON repository_summaries(touched, cache_key)")
            sequence = db.execute("SELECT COALESCE(MAX(touched), 0) FROM repository_summaries").fetchone()[0]
            _prune_cache(db, cache_max_entries)
            db.commit()
        count = 0
        for root, dirs, files in os.walk(root_path):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in _EXCLUDED)
            for filename in sorted(files):
                path = Path(root) / filename
                if path.suffix not in _EXTENSIONS or path.is_symlink() or path == cache_file:
                    continue
                relative = path.relative_to(root_path).as_posix()
                try:
                    content = path.read_bytes()
                except OSError:
                    summary = {"path": relative, "lines_of_code": 0, "complexity": 1.0,
                               "imports": [], "analysis": "unreadable_file"}
                else:
                    identity = json.dumps([str(root_path), relative, _CACHE_VERSION,
                                           hashlib.sha256(content).hexdigest()])
                    key = hashlib.sha256(identity.encode()).hexdigest()
                    cached = db.execute("SELECT summary FROM repository_summaries WHERE cache_key = ?",
                                        (key,)).fetchone() if db is not None else None
                    summary = json.loads(cached[0]) if cached else _summarize(path, relative, content)
                    if db is not None:
                        sequence += 1
                        db.execute("INSERT OR REPLACE INTO repository_summaries VALUES (?, ?, ?)",
                                   (key, json.dumps(summary), sequence))
                        _prune_cache(db, cache_max_entries)
                        db.commit()
                    del content
                yield summary
                count += 1
                if max_files is not None and count >= max_files:
                    return


def _prune_cache(db, limit):
    excess = db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0] - limit
    if excess > 0:
        db.execute("DELETE FROM repository_summaries WHERE cache_key IN "
                   "(SELECT cache_key FROM repository_summaries ORDER BY touched, cache_key "
                   "LIMIT ?)", (excess,))


def resolve_python_imports(summaries, node_ids):
    """Yield dependency -> importer pairs for imports resolving inside this scan.

    Supports root and src layouts, package initializers, and relative imports.
    Dynamic imports and ambiguous aliases are deliberately not inferred.
    """
    modules = {}
    packages = {}
    for summary in summaries:
        path = summary["path"]
        if not path.endswith(".py"):
            continue
        parts = path[:-3].split("/")
        if parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        is_init = parts[-1] == "__init__"
        module_parts = parts[:-1] if is_init else parts
        module = ".".join(module_parts)
        modules.setdefault(module, []).append(path)
        packages[path] = module_parts if is_init else module_parts[:-1]
    pairs = set()
    for summary in summaries:
        path = summary["path"]
        for item in summary["imports"]:
            module = item["module"]
            if item["level"]:
                package = packages.get(path, [])
                if item["level"] > len(package):
                    continue
                base = package[:len(package) - item["level"] + 1]
                module = ".".join(base + ([module] if module else []))
            candidates = [module] + [f"{module}.{name}" if module else name
                                      for name in item["names"] if name != "*"]
            for candidate in candidates:
                matches = modules.get(candidate, [])
                if len(matches) == 1 and matches[0] != path:
                    pairs.add((node_ids[matches[0]], node_ids[path]))
    yield from sorted(pairs)

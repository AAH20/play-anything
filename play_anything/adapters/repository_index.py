"""Incremental file summaries with an optional bounded, content-addressed cache.

Only one source file/AST is held during parsing. Consumers may still materialize
the summaries or graph. Non-Python files have measured LOC but no inferred edges.
"""
import ast
from contextlib import closing, nullcontext
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tokenize


_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".md"}
_EXCLUDED = {"node_modules", "__pycache__", "venv", "dist", "build", "site-dist"}
_CACHE_VERSION = "1"
_CACHE_WRITE_BATCH_SIZE = 64
DEFAULT_MAX_SOURCE_BYTES = 2 * 1024 * 1024
SOURCE_READ_CHUNK_BYTES = 64 * 1024


def _raise_walk_error(error):
    raise error


def _resolve_cache_path(cache_path):
    path = Path(cache_path)
    try:
        resolved = path.resolve()
    except RuntimeError as exc:
        # pathlib versions before 3.13 expose symlink loops as RuntimeError.
        if "symlink loop" not in str(exc).lower():
            raise
        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), os.fspath(path)) from exc
    # Newer pathlib can leave a loop unresolved with strict=False. Stat also
    # catches loops in parent components; a missing new cache file is normal.
    try:
        os.stat(path)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), os.fspath(path)) from exc
    return resolved


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


def _read_bounded_source(path, limit):
    """Read a source prefix in bounded chunks, returning one overflow sentinel."""
    content = bytearray()
    remaining = None if limit is None else limit + 1
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(errno.EINVAL, "source is not a regular file", os.fspath(path))
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            while remaining is None or remaining > 0:
                chunk_size = SOURCE_READ_CHUNK_BYTES if remaining is None else min(
                    SOURCE_READ_CHUNK_BYTES, remaining
                )
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                content.extend(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise _SourceReadError(exc, len(content)) from exc
    return bytes(content)


class _SourceReadError(OSError):
    def __init__(self, cause, bytes_read):
        super().__init__(str(cause))
        self.bytes_read = bytes_read


def iter_repository_summaries(directory_path, max_files=50, *, cache_path=None,
                              cache_max_entries=10000,
                              max_file_bytes=DEFAULT_MAX_SOURCE_BYTES,
                              max_total_source_bytes=None,
                              include_source_metrics=False):
    """Yield sorted file summaries; None explicitly removes the file-count limit.

    Cache contents are parser summaries only, not source code. Each key includes
    the repository, relative path, parser version, and SHA-256 of current bytes.
    SQLite setup/read/write failures propagate rather than silently disabling it.
    Source reads are capped at 2 MiB per file by default; set max_file_bytes=None
    to disable that cap. Symlinks are skipped. A missing/unreadable source is
    represented explicitly. Dot-prefixed directories and files are excluded.
    Directory traversal errors propagate to the caller.
    Cache writes are buffered in batches of 64 and flushed on exhaustion or close;
    no write transaction remains open while a yielded summary is suspended.
    """
    if max_files is not None and (type(max_files) is not int or max_files < 1):
        raise ValueError("max_files must be a positive integer or None")
    if type(cache_max_entries) is not int or cache_max_entries < 1:
        raise ValueError("cache_max_entries must be a positive integer")
    if max_file_bytes is not None and (type(max_file_bytes) is not int or max_file_bytes < 1):
        raise ValueError("max_file_bytes must be a positive integer or None")
    if (max_total_source_bytes is not None and
            (type(max_total_source_bytes) is not int or
             not 0 <= max_total_source_bytes < sys.maxsize)):
        raise ValueError(f"max_total_source_bytes must be an integer from 0 to {sys.maxsize - 1}, or None")
    if type(include_source_metrics) is not bool:
        raise TypeError("include_source_metrics must be a bool")
    root_input = Path(directory_path)
    root_stat = os.stat(root_input)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise NotADirectoryError(str(root_input))
    root_path = root_input.resolve()
    cache_file = _resolve_cache_path(cache_path) if cache_path is not None else None
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
        source_bytes_read = 0
        source_budget_exceeded_files = 0
        source_budget_exhausted = False
        pending_cache_rows = []
        try:
            for root, dirs, files in os.walk(root_path, onerror=_raise_walk_error):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in _EXCLUDED)
                for filename in sorted(files):
                    if filename.startswith("."):
                        continue
                    path = Path(root) / filename
                    if path.suffix not in _EXTENSIONS or path.is_symlink() or path == cache_file:
                        continue
                    relative = path.relative_to(root_path).as_posix()
                    try:
                        source_stat = path.stat()
                        if not stat.S_ISREG(source_stat.st_mode):
                            raise OSError(errno.EINVAL, "source is not a regular file",
                                          os.fspath(path))
                        source_size = source_stat.st_size
                        if max_file_bytes is not None and source_size > max_file_bytes:
                            content = None
                            too_large = True
                            budget_exceeded = False
                        else:
                            too_large = False
                            remaining_budget = (
                                None if max_total_source_bytes is None
                                else max_total_source_bytes - source_bytes_read
                            )
                            if (remaining_budget is not None and source_size > remaining_budget):
                                content = None
                                budget_exceeded = True
                            elif remaining_budget == 0:
                                content = b"" if source_size == 0 else None
                                budget_exceeded = source_size > 0
                            else:
                                budget_exceeded = False
                                read_limit = max_file_bytes
                                if remaining_budget is not None:
                                    read_limit = (remaining_budget if read_limit is None
                                                  else min(read_limit, remaining_budget))
                                content = _read_bounded_source(path, read_limit)
                                source_bytes_read += len(content)
                                too_large = (max_file_bytes is not None and
                                             len(content) > max_file_bytes)
                                budget_exceeded = (
                                    max_total_source_bytes is not None and
                                    source_bytes_read > max_total_source_bytes
                                )
                    except OSError as exc:
                        source_bytes_read += getattr(exc, "bytes_read", 0)
                        if (max_total_source_bytes is not None and
                                source_bytes_read >= max_total_source_bytes):
                            source_budget_exhausted = True
                        summary = {"path": relative, "lines_of_code": 0, "complexity": 1.0,
                                   "imports": [], "analysis": "unreadable_file"}
                    else:
                        if too_large:
                            summary = {"path": relative, "lines_of_code": 0, "complexity": 1.0,
                                       "imports": [], "analysis": "source_too_large"}
                        elif budget_exceeded:
                            source_budget_exceeded_files += 1
                            source_budget_exhausted = True
                            summary = {"path": relative, "lines_of_code": 0, "complexity": 1.0,
                                       "imports": [], "analysis": "source_budget_exceeded"}
                        else:
                            if (max_total_source_bytes is not None and
                                    source_bytes_read >= max_total_source_bytes):
                                source_budget_exhausted = True
                            identity = json.dumps([str(root_path), relative, _CACHE_VERSION,
                                                   hashlib.sha256(content).hexdigest()])
                            key = hashlib.sha256(identity.encode()).hexdigest()
                            cached = db.execute("SELECT summary FROM repository_summaries WHERE cache_key = ?",
                                                (key,)).fetchone() if db is not None else None
                            summary = json.loads(cached[0]) if cached else _summarize(path, relative, content)
                            if db is not None:
                                sequence += 1
                                pending_cache_rows.append(
                                    (key, json.dumps(summary), sequence)
                                )
                                if len(pending_cache_rows) >= _CACHE_WRITE_BATCH_SIZE:
                                    _flush_cache(db, pending_cache_rows, cache_max_entries)
                            del content
                    if max_total_source_bytes is not None or include_source_metrics:
                        summary.update(
                            source_bytes_read=source_bytes_read,
                            source_budget_bytes=max_total_source_bytes,
                            source_budget_exceeded_files=source_budget_exceeded_files,
                            source_budget_exhausted=source_budget_exhausted,
                        )
                    yield summary
                    count += 1
                    if max_files is not None and count >= max_files:
                        return
        finally:
            if db is not None and pending_cache_rows:
                _flush_cache(db, pending_cache_rows, cache_max_entries)


def _flush_cache(db, rows, limit):
    """Persist a bounded batch and enforce the cache limit before releasing it."""
    if not rows:
        return
    try:
        db.executemany("INSERT OR REPLACE INTO repository_summaries VALUES (?, ?, ?)", rows)
        _prune_cache(db, limit)
        db.commit()
    except Exception:
        db.rollback()
        rows.clear()
        raise
    rows.clear()


def _prune_cache(db, limit):
    excess = db.execute("SELECT COUNT(*) FROM repository_summaries").fetchone()[0] - limit
    if excess > 0:
        db.execute("DELETE FROM repository_summaries WHERE cache_key IN "
                   "(SELECT cache_key FROM repository_summaries ORDER BY touched, cache_key "
                   "LIMIT ?)", (excess,))


class PythonImportResolver:
    """Incrementally index module paths and only the summaries that contain imports."""

    def __init__(self):
        self.modules = {}
        self.packages = {}
        self.imports_by_path = {}

    def add_summary(self, summary):
        path = summary["path"]
        if not path.endswith(".py"):
            return
        parts = path[:-3].split("/")
        if parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        is_init = parts[-1] == "__init__"
        module_parts = parts[:-1] if is_init else parts
        module = ".".join(module_parts)
        self.modules.setdefault(module, []).append(path)
        imports = summary["imports"]
        if imports:
            self.imports_by_path[path] = imports
            if any(item["level"] for item in imports):
                self.packages[path] = module_parts if is_init else module_parts[:-1]

    def resolve(self, node_ids):
        """Yield dependency -> importer pairs for imports resolving inside this scan.

        Supports root and src layouts, package initializers, and relative imports.
        Dynamic imports and ambiguous aliases are deliberately not inferred.
        """
        pairs = set()
        for path, imports in self.imports_by_path.items():
            for item in imports:
                module = item["module"]
                if item["level"]:
                    package = self.packages.get(path, [])
                    if item["level"] > len(package):
                        continue
                    base = package[:len(package) - item["level"] + 1]
                    module = ".".join(base + ([module] if module else []))
                candidates = [module] + [f"{module}.{name}" if module else name
                                          for name in item["names"] if name != "*"]
                for candidate in candidates:
                    matches = self.modules.get(candidate, [])
                    if len(matches) == 1 and matches[0] != path:
                        pairs.add((node_ids[matches[0]], node_ids[path]))
        yield from sorted(pairs)


def resolve_python_imports(summaries, node_ids):
    """Resolve imports from summaries while retaining only compact import metadata."""
    resolver = PythonImportResolver()
    for summary in summaries:
        resolver.add_summary(summary)
    yield from resolver.resolve(node_ids)

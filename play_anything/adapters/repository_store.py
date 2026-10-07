"""Optional on-disk, paginated index over deterministic repository summaries.

The store persists file summaries and statically resolved Python import edges in
SQLite. Rebuilds retain only a bounded write batch in Python memory; this does
not make source parsing or downstream graph/world generation constant-memory.
"""
from contextlib import closing, contextmanager
import errno
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import stat
import sys
import uuid

from .repository_index import DEFAULT_MAX_SOURCE_BYTES, iter_repository_summaries


_BATCH_SIZE = 64
_MAX_PAGE_SIZE = 1000
_MAX_GRAPH_EDGE_PAGE = 10000
_MAX_SQLITE_INTEGER = (1 << 63) - 1
_MAX_JSON_SAFE_INTEGER = (1 << 53) - 1
_PARTIAL_ANALYSIS = {"python_parse_error", "source_too_large", "source_budget_exceeded",
                     "unreadable_file"}


def _escaped_path_excerpt(path, limit=120):
    """Bound and ASCII-escape a rejected filename for safe diagnostics."""
    if not isinstance(path, str):
        return "<non-string path>"
    excerpt = path[:limit]
    if len(path) > limit:
        excerpt += "…"
    return ascii(excerpt)


def _resolve_store_path(value):
    path = Path(value).expanduser()
    try:
        resolved = path.resolve()
    except RuntimeError as exc:
        # pathlib versions before 3.13 report symlink loops as RuntimeError;
        # callers (including the CLI) otherwise cannot handle them as OS input errors.
        if "symlink loop" not in str(exc).lower():
            raise
        raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), os.fspath(path)) from exc
    # pathlib versions that stop resolution at a repeated link can return the
    # unresolved alias. Verify symlink targets so both versions expose ELOOP.
    try:
        if path.is_symlink():
            os.stat(path)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), os.fspath(path)) from exc
    return resolved


def _json_safe_optional_counts(values, fields):
    """Keep optional graph-page counts exact across JSON/JavaScript consumers."""
    for field in fields:
        value = values.get(field)
        if type(value) is int and value > _MAX_JSON_SAFE_INTEGER:
            values[field + "_exact"] = str(value)
            values[field] = None


class SQLiteRepositoryStore:
    """A context-managed SQLite store for multiple repository roots.

    The database must be outside every scanned root so its database and journal
    files cannot be mistaken for repository source. Query methods return one
    bounded page at a time. Imports are static Python imports only; dynamic
    imports, call graphs, and non-Python dependency semantics are not inferred.
    """

    def __init__(self, database_path, *, read_only=False):
        if not isinstance(database_path, (str, os.PathLike)):
            raise TypeError("database_path must be a path")
        if not os.fspath(database_path):
            raise ValueError("database_path must not be empty")
        if type(read_only) is not bool:
            raise TypeError("read_only must be a bool")
        self.database_path = _resolve_store_path(database_path)
        self.read_only = read_only
        self._db = None
        self._closed = False

    @property
    def closed(self):
        return self._closed

    def __enter__(self):
        if self._closed:
            raise RuntimeError("repository store is closed")
        if self._db is not None:
            raise RuntimeError("repository store context is already open")
        if not self.read_only:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = self._open()
        try:
            self._ensure_schema(self._db, read_only=self.read_only)
        except BaseException:
            self._db.close()
            self._db = None
            raise
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._closed = True

    def _open(self):
        if self._closed:
            raise RuntimeError("repository store is closed")
        if self.read_only:
            uri = self.database_path.as_uri() + "?mode=ro"
            return sqlite3.connect(uri, uri=True, timeout=5.0)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(self.database_path), timeout=5.0)

    @staticmethod
    def _ensure_schema(db, *, read_only=False):
        expected_columns = {
            "pa_repo_generations": {"root", "generation", "max_files", "max_file_bytes",
                                    "file_count", "created_at"},
            "pa_repo_active": {"root", "generation"},
            "pa_repo_files": {"root", "generation", "path", "analysis", "summary_json"},
            "pa_repo_modules": {"root", "generation", "module", "path"},
            "pa_repo_import_edges": {"root", "generation", "dependency", "importer"},
        }
        expected_primary_keys = {
            "pa_repo_generations": ("root", "generation"),
            "pa_repo_active": ("root",),
            "pa_repo_files": ("root", "generation", "path"),
            "pa_repo_modules": ("root", "generation", "module", "path"),
            "pa_repo_import_edges": ("root", "generation", "dependency", "importer"),
        }
        existing = {name: kind for kind, name in db.execute(
            "SELECT type, name FROM sqlite_master WHERE name IN (" +
            ",".join("?" for _ in expected_columns) + ")",
            tuple(expected_columns)).fetchall()}
        for name, required in expected_columns.items():
            if name not in existing:
                continue
            if existing[name] != "table":
                raise sqlite3.DatabaseError(f"incompatible repository store object: {name}")
            details = db.execute(f"PRAGMA table_info({name})").fetchall()
            actual = {row[1] for row in details}
            if not required <= actual:
                raise sqlite3.DatabaseError(f"incompatible repository store table: {name}")
            actual_primary_key = tuple(row[1] for row in sorted(
                (column for column in details if column[5]), key=lambda column: column[5]))
            if actual_primary_key != expected_primary_keys[name]:
                raise sqlite3.DatabaseError(f"incompatible repository store key: {name}")
        if read_only:
            missing = sorted(set(expected_columns) - set(existing))
            if missing:
                raise sqlite3.DatabaseError(
                    "repository store schema is missing required table(s): " + ", ".join(missing))
            generation_columns = {row[1] for row in db.execute(
                "PRAGMA table_info(pa_repo_generations)").fetchall()}
            required_generation_columns = {
                "truncated", "max_total_source_bytes", "source_bytes_read",
                "source_budget_exhausted", "source_budget_exceeded_files",
                "source_metrics_available",
            }
            missing_generation_columns = sorted(required_generation_columns - generation_columns)
            if missing_generation_columns:
                raise sqlite3.DatabaseError(
                    "incompatible repository store table: pa_repo_generations (missing " +
                    ", ".join(missing_generation_columns) + ")")
            return
        db.executescript(
            "CREATE TABLE IF NOT EXISTS pa_repo_generations ("
            "root TEXT NOT NULL, generation TEXT NOT NULL, max_files INTEGER, "
            "max_file_bytes INTEGER, max_total_source_bytes INTEGER, "
            "source_bytes_read INTEGER, "
            "source_budget_exhausted INTEGER NOT NULL DEFAULT 0, "
            "source_budget_exceeded_files INTEGER NOT NULL DEFAULT 0, "
            "source_metrics_available INTEGER NOT NULL DEFAULT 0, "
            "file_count INTEGER NOT NULL DEFAULT 0, "
            "truncated INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY(root, generation));"
            "CREATE TABLE IF NOT EXISTS pa_repo_active ("
            "root TEXT PRIMARY KEY, generation TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS pa_repo_files ("
            "root TEXT NOT NULL, generation TEXT NOT NULL, path TEXT NOT NULL, "
            "analysis TEXT NOT NULL, summary_json TEXT NOT NULL, "
            "PRIMARY KEY(root, generation, path));"
            "CREATE INDEX IF NOT EXISTS pa_repo_files_page "
            "ON pa_repo_files(root, generation, path);"
            "CREATE TABLE IF NOT EXISTS pa_repo_modules ("
            "root TEXT NOT NULL, generation TEXT NOT NULL, module TEXT NOT NULL, "
            "path TEXT NOT NULL, PRIMARY KEY(root, generation, module, path));"
            "CREATE INDEX IF NOT EXISTS pa_repo_modules_lookup "
            "ON pa_repo_modules(root, generation, module);"
            "CREATE TABLE IF NOT EXISTS pa_repo_import_edges ("
            "root TEXT NOT NULL, generation TEXT NOT NULL, dependency TEXT NOT NULL, "
            "importer TEXT NOT NULL, PRIMARY KEY(root, generation, dependency, importer));"
            "CREATE INDEX IF NOT EXISTS pa_repo_edges_importer "
            "ON pa_repo_import_edges(root, generation, importer, dependency);"
            "CREATE INDEX IF NOT EXISTS pa_repo_edges_dependency "
            "ON pa_repo_import_edges(root, generation, dependency, importer);"
        )
        generation_columns = {row[1] for row in db.execute(
            "PRAGMA table_info(pa_repo_generations)").fetchall()}
        migration_columns = {
            "max_total_source_bytes": "INTEGER",
            # Existing generations cannot claim measured zero bytes after a
            # migration: only a new rebuild can establish these metrics.
            "source_bytes_read": "INTEGER",
            "source_budget_exhausted": "INTEGER NOT NULL DEFAULT 0",
            "source_budget_exceeded_files": "INTEGER NOT NULL DEFAULT 0",
            "source_metrics_available": "INTEGER NOT NULL DEFAULT 0",
            "truncated": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in migration_columns.items():
            if column not in generation_columns:
                db.execute(f"ALTER TABLE pa_repo_generations ADD COLUMN {column} {definition}")
        db.commit()

    @contextmanager
    def _connection(self):
        if self._closed:
            raise RuntimeError("repository store is closed")
        if self._db is not None:
            yield self._db
            return
        with closing(self._open()) as db:
            self._ensure_schema(db, read_only=self.read_only)
            yield db

    @contextmanager
    def _read_snapshot(self):
        with self._connection() as db:
            db.execute("BEGIN")
            try:
                yield db
            finally:
                if db.in_transaction:
                    db.rollback()

    @staticmethod
    def _root(root):
        if not isinstance(root, (str, os.PathLike)):
            raise TypeError("root must be a path")
        return _resolve_store_path(root)

    def _validate_db_location(self, root):
        try:
            self.database_path.relative_to(root)
        except ValueError:
            return
        raise ValueError("repository database must be outside the scanned root")

    @staticmethod
    def _validate_page(limit, offset):
        if type(limit) is not int or not 1 <= limit <= _MAX_PAGE_SIZE:
            raise ValueError(f"limit must be an integer from 1 to {_MAX_PAGE_SIZE}")
        if type(offset) is not int or not 0 <= offset <= _MAX_SQLITE_INTEGER:
            raise ValueError("offset must be a non-negative integer")

    @staticmethod
    def _relative_path(path):
        if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
            raise ValueError("path must be a non-empty repository-relative POSIX path")
        parsed = PurePosixPath(path)
        if any(part in {"", ".", ".."} for part in path.split("/")) or parsed.is_absolute():
            raise ValueError("path must not escape the repository root")
        return parsed.as_posix()

    @staticmethod
    def _decode_summary(path, payload):
        try:
            summary = json.loads(payload)
        except (ValueError, RecursionError):
            raise ValueError(
                f"invalid stored summary for repository file "
                f"{_escaped_path_excerpt(path)}"
            ) from None
        if not isinstance(path, str) or not isinstance(summary, dict):
            raise ValueError(
                f"stored summary for repository file {_escaped_path_excerpt(path)} "
                "must be a JSON object"
            )
        if summary.get("path") != path:
            raise ValueError(
                f"stored summary path does not match indexed repository file "
                f"{_escaped_path_excerpt(path)}"
            )
        return summary

    @staticmethod
    def _module_for_path(path):
        if not path.endswith(".py"):
            return None
        parts = path[:-3].split("/")
        if parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    @staticmethod
    def _relative_package(path):
        module_parts = (SQLiteRepositoryStore._module_for_path(path) or "").split(".")
        if module_parts == [""]:
            module_parts = []
        return module_parts if path.endswith("/__init__.py") or path == "__init__.py" else module_parts[:-1]

    def rebuild(self, root, *, max_files=50, max_file_bytes=DEFAULT_MAX_SOURCE_BYTES,
                max_total_source_bytes=None):
        """Build a new generation; publish it only after traversal and indexing succeed."""
        if self.read_only:
            raise ValueError("cannot rebuild a read-only repository store")
        root_path = self._root(root)
        root_stat = os.stat(root_path)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise NotADirectoryError(str(root_path))
        self._validate_db_location(root_path)
        if max_files is not None and (type(max_files) is not int or
                                      not 1 <= max_files <= _MAX_SQLITE_INTEGER):
            raise ValueError("max_files must be a positive SQLite integer or None")
        max_source_limit = min(_MAX_SQLITE_INTEGER, sys.maxsize - 1)
        if max_file_bytes is not None and (type(max_file_bytes) is not int or
                                           not 1 <= max_file_bytes <= max_source_limit):
            raise ValueError("max_file_bytes must be a positive readable SQLite integer or None")
        if (max_total_source_bytes is not None and
                (type(max_total_source_bytes) is not int or
                 not 0 <= max_total_source_bytes <= max_source_limit)):
            raise ValueError("max_total_source_bytes must be an integer from 0 to the readable SQLite limit, or None")

        root_key = str(root_path)
        generation = uuid.uuid4().hex
        with self._connection() as db:
            try:
                db.execute("INSERT INTO pa_repo_generations(root, generation, max_files, max_file_bytes, "
                           "max_total_source_bytes) VALUES (?, ?, ?, ?, ?)",
                           (root_key, generation, max_files, max_file_bytes, max_total_source_bytes))
                db.commit()
            except BaseException:
                db.rollback()
                raise
            pending_files = []
            pending_modules = []
            file_count = 0
            truncated = False
            source_bytes_read = 0
            source_budget_exhausted = False
            source_budget_exceeded_files = 0
            try:
                # One-item lookahead detects a real max_files truncation while
                # keeping memory bounded and preserving deterministic scan order.
                iterator_limit = None if max_files is None else max_files + 1
                summaries = iter_repository_summaries(
                    root_path, max_files=iterator_limit, max_file_bytes=max_file_bytes,
                    max_total_source_bytes=max_total_source_bytes,
                    include_source_metrics=True)
                try:
                    for summary in summaries:
                        source_bytes_read = summary.get("source_bytes_read", source_bytes_read)
                        source_budget_exhausted = summary.get(
                            "source_budget_exhausted", source_budget_exhausted)
                        source_budget_exceeded_files = summary.get(
                            "source_budget_exceeded_files", source_budget_exceeded_files)
                        if max_files is not None and file_count >= max_files:
                            truncated = True
                            break
                        summary_path = summary["path"]
                        try:
                            path = self._relative_path(summary_path)
                        except ValueError as exc:
                            raise ValueError(
                                f"{exc}; repository-relative filename="
                                f"{_escaped_path_excerpt(summary_path)}"
                            ) from None
                        analysis = summary.get("analysis", "unknown")
                        pending_files.append((root_key, generation, path, analysis,
                                              json.dumps(summary, sort_keys=True)))
                        module = self._module_for_path(path)
                        if module is not None:
                            pending_modules.append((root_key, generation, module, path))
                        file_count += 1
                        if len(pending_files) >= _BATCH_SIZE:
                            self._write_rows(db, pending_files, pending_modules)
                finally:
                    summaries.close()
                self._write_rows(db, pending_files, pending_modules)
                self._resolve_staged_imports(db, root_key, generation)

                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("SELECT generation FROM pa_repo_active WHERE root = ?",
                                      (root_key,)).fetchone()
                db.execute("UPDATE pa_repo_generations SET file_count = ?, truncated = ?, "
                           "source_bytes_read = ?, source_budget_exhausted = ?, "
                           "source_budget_exceeded_files = ?, source_metrics_available = 1 "
                           "WHERE root = ? AND generation = ?",
                           (file_count, int(truncated), source_bytes_read,
                            int(source_budget_exhausted), source_budget_exceeded_files,
                            root_key, generation))
                db.execute("INSERT OR REPLACE INTO pa_repo_active(root, generation) VALUES (?, ?)",
                           (root_key, generation))
                if previous and previous[0] != generation:
                    self._delete_generation(db, root_key, previous[0])
                published_status = self._status(db, root_key, generation)
                db.commit()
            except BaseException:
                db.rollback()
                try:
                    self._delete_generation(db, root_key, generation)
                    db.commit()
                except Exception:
                    db.rollback()
                raise
            return published_status

    @staticmethod
    def _write_rows(db, files, modules):
        if not files and not modules:
            return
        try:
            if files:
                db.executemany("INSERT INTO pa_repo_files VALUES (?, ?, ?, ?, ?)", files)
            if modules:
                db.executemany("INSERT INTO pa_repo_modules VALUES (?, ?, ?, ?)", modules)
            db.commit()
        except Exception:
            db.rollback()
            raise
        files.clear()
        modules.clear()

    @staticmethod
    def _delete_generation(db, root, generation):
        for table in ("pa_repo_import_edges", "pa_repo_modules", "pa_repo_files",
                      "pa_repo_generations"):
            db.execute(f"DELETE FROM {table} WHERE root = ? AND generation = ?",
                       (root, generation))

    def _resolve_staged_imports(self, db, root, generation):
        cursor = db.execute("SELECT path, summary_json FROM pa_repo_files "
                            "WHERE root = ? AND generation = ? ORDER BY path",
                            (root, generation))
        pending = []
        for path, summary_json in cursor:
            imports = json.loads(summary_json).get("imports", ())
            package = self._relative_package(path)
            for item in imports:
                module = item.get("module", "")
                level = item.get("level", 0)
                if level:
                    if level > len(package):
                        continue
                    base = package[:len(package) - level + 1]
                    module = ".".join(base + ([module] if module else []))
                candidates = [module]
                candidates.extend(f"{module}.{name}" if module else name
                                  for name in item.get("names", ()) if name != "*")
                for candidate in candidates:
                    matches = db.execute(
                        "SELECT path FROM pa_repo_modules WHERE root = ? AND generation = ? "
                        "AND module = ? ORDER BY path LIMIT 2",
                        (root, generation, candidate)).fetchall()
                    if len(matches) == 1 and matches[0][0] != path:
                        pending.append((root, generation, matches[0][0], path))
                        if len(pending) >= _BATCH_SIZE:
                            self._write_edges(db, pending)
        self._write_edges(db, pending)

    @staticmethod
    def _write_edges(db, edges):
        if not edges:
            return
        try:
            db.executemany("INSERT OR IGNORE INTO pa_repo_import_edges VALUES (?, ?, ?, ?)", edges)
            db.commit()
        except Exception:
            db.rollback()
            raise
        edges.clear()

    @staticmethod
    def _active_generation(db, root):
        row = db.execute("SELECT generation FROM pa_repo_active WHERE root = ?", (root,)).fetchone()
        if row is None:
            raise ValueError(f"no repository index for {root}")
        return row[0]

    @staticmethod
    def _status(db, root, generation):
        row = db.execute("SELECT max_files, max_file_bytes, max_total_source_bytes, "
                         "source_bytes_read, source_budget_exhausted, "
                         "source_budget_exceeded_files, file_count, truncated, "
                         "source_metrics_available "
                         "FROM pa_repo_generations "
                         "WHERE root = ? AND generation = ?", (root, generation)).fetchone()
        if row is None:
            raise ValueError(f"no repository generation for {root}")
        counts = dict(db.execute("SELECT analysis, COUNT(*) FROM pa_repo_files "
                                 "WHERE root = ? AND generation = ? GROUP BY analysis ORDER BY analysis",
                                 (root, generation)).fetchall())
        partial = (bool(row[7]) or bool(row[5]) or
                   any(counts.get(kind, 0) for kind in _PARTIAL_ANALYSIS))
        imports_partial = partial or counts.get("unparsed_language", 0) > 0
        source_metrics_available = bool(row[8])
        edge_count = db.execute("SELECT COUNT(*) FROM pa_repo_import_edges "
                                "WHERE root = ? AND generation = ?",
                                (root, generation)).fetchone()[0]
        return {"root": root, "generation": generation, "file_count": row[6],
                "max_files": row[0], "max_file_bytes": row[1],
                "max_total_source_bytes": row[2],
                "source_bytes_read": row[3] if source_metrics_available else None,
                "source_budget_bytes": row[2] if source_metrics_available else None,
                "source_budget_exhausted": bool(row[4]) if source_metrics_available else None,
                "source_budget_exceeded_files": row[5] if source_metrics_available else None,
                "source_metrics_available": source_metrics_available,
                "truncated": bool(row[7]),
                "partial": bool(partial), "imports_partial": bool(imports_partial),
                "analysis_counts": counts, "import_edge_count": edge_count}

    def status(self, root):
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            return self._status(db, root_key, self._active_generation(db, root_key))

    def files(self, root, *, limit=100, offset=0):
        self._validate_page(limit, offset)
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            generation = self._active_generation(db, root_key)
            rows = db.execute("SELECT path, summary_json FROM pa_repo_files WHERE root = ? "
                              "AND generation = ? ORDER BY path LIMIT ? OFFSET ?",
                              (root_key, generation, limit, offset)).fetchall()
            return [self._decode_summary(row[0], row[1]) for row in rows]

    def search_files(self, root, query, *, limit=100, offset=0):
        """Find summaries whose relative paths contain query literally (case-sensitive)."""
        self._validate_page(limit, offset)
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            generation = self._active_generation(db, root_key)
            rows = db.execute("SELECT path, summary_json FROM pa_repo_files WHERE root = ? "
                              "AND generation = ? AND instr(path, ?) > 0 "
                              "ORDER BY path LIMIT ? OFFSET ?",
                              (root_key, generation, query, limit, offset)).fetchall()
            return [self._decode_summary(row[0], row[1]) for row in rows]

    def imports(self, root, path=None, *, limit=100, offset=0):
        self._validate_page(limit, offset)
        path = self._relative_path(path) if path is not None else None
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            generation = self._active_generation(db, root_key)
            sql = ("SELECT dependency, importer FROM pa_repo_import_edges WHERE root = ? "
                   "AND generation = ?")
            params = [root_key, generation]
            if path is not None:
                sql += " AND importer = ?"
                params.append(path)
            sql += " ORDER BY dependency, importer LIMIT ? OFFSET ?"
            params.extend((limit, offset))
            return [{"dependency": row[0], "importer": row[1]}
                    for row in db.execute(sql, params).fetchall()]

    def dependencies(self, root, path, *, direction="imports", limit=100, offset=0):
        self._validate_page(limit, offset)
        path = self._relative_path(path)
        if direction not in {"imports", "imported_by"}:
            raise ValueError("direction must be 'imports' or 'imported_by'")
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            generation = self._active_generation(db, root_key)
            if direction == "imports":
                predicate, column = "importer = ?", "dependency"
            else:
                predicate, column = "dependency = ?", "importer"
            rows = db.execute(f"SELECT {column} FROM pa_repo_import_edges WHERE root = ? "
                              f"AND generation = ? AND {predicate} ORDER BY {column} "
                              "LIMIT ? OFFSET ?",
                              (root_key, generation, path, limit, offset)).fetchall()
            return [row[0] for row in rows]

    def graph_page(self, root, *, limit=250, offset=0, max_edges=2000, search=None):
        """Return one bounded file/import snapshot page for graph viewers.

        Nodes and summaries are read from one active generation in a single
        SQLite snapshot. Only resolved Python import edges with both endpoints
        in this page are returned. Other incident edges are counted explicitly;
        this is a file/import view, not a symbol or call graph.
        """
        self._validate_page(limit, offset)
        if offset > _MAX_JSON_SAFE_INTEGER:
            raise ValueError(
                "graph_page offset must fit the JavaScript-safe integer range for portable graph snapshots")
        if type(max_edges) is not int or not 1 <= max_edges <= _MAX_GRAPH_EDGE_PAGE:
            raise ValueError(f"max_edges must be an integer from 1 to {_MAX_GRAPH_EDGE_PAGE}")
        if search is not None and not isinstance(search, str):
            raise TypeError("search must be a string or None")
        root_key = str(self._root(root))
        with self._read_snapshot() as db:
            generation = self._active_generation(db, root_key)
            status = self._status(db, root_key, generation)
            where_search = " AND instr(path, ?) > 0" if search is not None else ""
            search_params = (search,) if search is not None else ()
            matching_nodes = db.execute(
                "SELECT COUNT(*) FROM pa_repo_files WHERE root = ? AND generation = ?" + where_search,
                (root_key, generation, *search_params)).fetchone()[0]
            rows = db.execute(
                "SELECT path, summary_json FROM pa_repo_files WHERE root = ? AND generation = ?" +
                where_search + " ORDER BY path LIMIT ? OFFSET ?",
                (root_key, generation, *search_params, limit, offset)).fetchall()
            paths = [row[0] for row in rows]
            nodes = []
            for path, payload in rows:
                item = self._decode_summary(path, payload)
                nodes.append({
                    "id": "file:" + path, "name": PurePosixPath(path).name,
                    "kind": "file", "path": path, "line": 1,
                    "summary": "Repository file summary; no symbols or call graph included.",
                    "confidence": "observed", "analysis": item.get("analysis", "unknown"),
                    "lines_of_code": item.get("lines_of_code", 0),
                    "complexity": item.get("complexity", 1.0),
                })

            internal_edge_count = 0
            cross_page_edge_count = 0
            edges = []
            if paths:
                page_cte = ("WITH page(path) AS (SELECT path FROM pa_repo_files "
                            "WHERE root = ? AND generation = ?" + where_search +
                            " ORDER BY path LIMIT ? OFFSET ?) ")
                page_params = (root_key, generation, *search_params, limit, offset)
                internal_sql = (page_cte +
                    "SELECT COUNT(*) FROM pa_repo_import_edges e "
                    "JOIN page i ON i.path = e.importer "
                    "JOIN page d ON d.path = e.dependency "
                    "WHERE e.root = ? AND e.generation = ?")
                internal_edge_count = db.execute(
                    internal_sql, (*page_params, root_key, generation)).fetchone()[0]
                incident_sql = (page_cte +
                    "SELECT COUNT(*) FROM ("
                    "SELECT e.dependency, e.importer FROM page p "
                    "CROSS JOIN pa_repo_import_edges e "
                    "WHERE e.root = ? AND e.generation = ? AND e.importer = p.path "
                    "UNION ALL "
                    "SELECT e.dependency, e.importer FROM page p "
                    "CROSS JOIN pa_repo_import_edges e "
                    "WHERE e.root = ? AND e.generation = ? AND e.dependency = p.path "
                    "AND NOT EXISTS (SELECT 1 FROM page q WHERE q.path = e.importer))")
                incident_count = db.execute(
                    incident_sql, (*page_params, root_key, generation,
                                   root_key, generation)).fetchone()[0]
                cross_page_edge_count = incident_count - internal_edge_count
                edge_sql = (page_cte +
                    "SELECT e.importer, e.dependency FROM pa_repo_import_edges e "
                    "JOIN page i ON i.path = e.importer "
                    "JOIN page d ON d.path = e.dependency "
                    "WHERE e.root = ? AND e.generation = ? "
                    "ORDER BY e.importer, e.dependency LIMIT ?")
                edge_rows = db.execute(
                    edge_sql, (*page_params, root_key, generation, max_edges + 1)).fetchall()
                edges = [{"source": "file:" + importer,
                          "target": "file:" + dependency,
                          "relation": "imports", "confidence": "parsed"}
                         for importer, dependency in edge_rows[:max_edges]]

        has_previous = offset > 0 and matching_nodes > 0
        has_next = offset + len(rows) < matching_nodes
        omitted_page_edges = max(0, internal_edge_count - len(edges))
        filtered = search is not None
        source_partial = any(status["analysis_counts"].get(kind, 0)
                             for kind in _PARTIAL_ANALYSIS) or bool(
                                 status["source_budget_exceeded_files"])
        imports_partial = status["imports_partial"]
        source_truncated = status["truncated"]
        partial = source_partial or imports_partial or source_truncated
        complete = (not filtered and not has_previous and not has_next and not partial and
                    omitted_page_edges == 0 and len(rows) == status["file_count"])
        page_status = "complete" if complete else "partial"
        coverage = {
            "generation": generation, "status": page_status, "complete": complete,
            "total_nodes": status["file_count"], "matching_nodes": matching_nodes,
            "offset": offset, "page_size": limit, "returned_nodes": len(nodes),
            "has_previous": has_previous, "has_next": has_next, "filtered": filtered,
            "total_import_edges": status["import_edge_count"],
            "returned_page_edges": len(edges), "omitted_page_edges": omitted_page_edges,
            "omitted_cross_page_edges": cross_page_edge_count,
            "source_partial": source_partial, "imports_partial": imports_partial,
            "scan_truncated": source_truncated, "max_files": status["max_files"],
            "max_file_bytes": status["max_file_bytes"],
            "max_total_source_bytes": status["max_total_source_bytes"],
            "source_budget_bytes": status["source_budget_bytes"],
            "source_bytes_read": status["source_bytes_read"],
            "source_budget_exhausted": status["source_budget_exhausted"],
            "source_budget_exceeded_files": status["source_budget_exceeded_files"],
            "source_metrics_available": status["source_metrics_available"],
            "max_edges": max_edges,
        }
        truncated = (filtered or has_previous or has_next or partial or omitted_page_edges > 0 or
                     cross_page_edge_count > 0)
        warnings = []
        if imports_partial:
            warnings.append("Import coverage is partial; only statically resolved Python imports are represented.")
        if source_truncated:
            warnings.append("The repository scan stopped at its configured file limit.")
        analysis = {
            "source_kind": "sqlite_file_import_page", "status": page_status,
            "message": "Bounded file inventory and resolved Python imports; no symbols or call graph.",
            "file_count": status["file_count"], "matching_files": matching_nodes,
            "returned_files": len(nodes), "imports_partial": imports_partial,
            "source_partial": source_partial, "scan_truncated": source_truncated,
            "source_bytes_read": status["source_bytes_read"],
            "source_budget_bytes": status["source_budget_bytes"],
            "source_budget_exhausted": status["source_budget_exhausted"],
            "source_budget_exceeded_files": status["source_budget_exceeded_files"],
            "source_metrics_available": status["source_metrics_available"],
            "file_limit_reached": source_truncated, "file_limit": status["max_files"],
            "max_file_bytes": status["max_file_bytes"],
            "analyzed_files": status["analysis_counts"].get("python_ast", 0),
            "unparsed_files": status["analysis_counts"].get("unparsed_language", 0),
            "parse_errors": status["analysis_counts"].get("python_parse_error", 0),
            "unreadable_files": status["analysis_counts"].get("unreadable_file", 0),
            "too_large_files": status["analysis_counts"].get("source_too_large", 0),
            "warnings": warnings,
        }
        _json_safe_optional_counts(analysis, (
            "file_limit", "max_file_bytes", "source_budget_bytes", "source_bytes_read",
            "source_budget_exceeded_files",
        ))
        _json_safe_optional_counts(coverage, (
            "max_files", "max_file_bytes", "max_total_source_bytes", "source_budget_bytes",
            "source_bytes_read", "source_budget_exceeded_files",
        ))
        return {
            "version": 1, "name": Path(root_key).name, "nodes": nodes, "edges": edges,
            "summary": {"files": status["file_count"], "modules": 0, "functions": 0,
                        "classes": 0, "relationships": status["import_edge_count"], "hubs": []},
            "unresolved": [], "unresolved_truncated": False, "warnings": warnings,
            "truncated": truncated, "limits": {"files": status["max_files"],
                                                   "edges": max_edges},
            "analysis": analysis, "coverage": coverage,
        }

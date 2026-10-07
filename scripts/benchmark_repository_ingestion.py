"""Measure ingestion and SQLite graph-page queries on a deterministic fixture.

Peak memory is Python allocations tracked by tracemalloc. The graph-page mode
measures the query separately from fixture creation and SQLite index building.
It is not process RSS, live inference latency, or evidence of solver optimality.
"""

import argparse
from itertools import count as count_statements
import json
import sqlite3
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from play_anything.adapters.repository_index import (  # noqa: E402
    DEFAULT_MAX_SOURCE_BYTES,
    iter_repository_summaries,
)
from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator  # noqa: E402
from play_anything.adapters.repository_store import SQLiteRepositoryStore  # noqa: E402


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return number


def source_byte_limit(value: str) -> int:
    number = positive_integer(value)
    if number > sys.maxsize - 1:
        raise argparse.ArgumentTypeError(f"must not exceed {sys.maxsize - 1}")
    return number


def total_source_byte_limit(value: str) -> int:
    number = nonnegative_integer(value)
    if number > sys.maxsize - 1:
        raise argparse.ArgumentTypeError(f"must not exceed {sys.maxsize - 1}")
    return number


def benchmark(file_count: int, functions_per_file: int, *, mode: str = "index",
              repeats: int = 2, cache: bool = False,
              max_file_bytes: int = DEFAULT_MAX_SOURCE_BYTES,
              max_total_source_bytes: int | None = None,
              page_limit: int | None = None, page_offset: int | None = None,
              edge_limit: int | None = None, search: str | None = None) -> dict:
    """Measure cold/repeated ingestion of a synthetic ring of Python modules."""
    if mode not in {"index", "world", "store", "graph-page"}:
        raise ValueError("mode must be index, world, store, or graph-page")
    graph_options = (page_limit, page_offset, edge_limit, search)
    if mode != "graph-page" and any(value is not None for value in graph_options):
        raise ValueError("graph-page options are only valid with graph-page mode")
    if mode == "graph-page":
        page_limit = 100 if page_limit is None else page_limit
        page_offset = 0 if page_offset is None else page_offset
        edge_limit = 2000 if edge_limit is None else edge_limit
        if type(page_limit) is not int or not 1 <= page_limit <= 1000:
            raise ValueError("page_limit must be an integer from 1 to 1000")
        if type(page_offset) is not int or not 0 <= page_offset <= 2**53 - 1:
            raise ValueError("page_offset must be an integer from 0 to 2**53 - 1 for portable JSON graph pages")
        if type(edge_limit) is not int or not 1 <= edge_limit <= 10000:
            raise ValueError("edge_limit must be an integer from 1 to 10000")
        if search is not None and not isinstance(search, str):
            raise ValueError("search must be a string or None")
        if cache:
            raise ValueError("graph-page mode does not use the summary cache")
    if mode == "store" and cache:
        raise ValueError("store mode rebuilds the durable index; --cache is only for index/world summary caching")
    if (max_total_source_bytes is not None and
            (type(max_total_source_bytes) is not int or
             not 0 <= max_total_source_bytes <= sys.maxsize - 1)):
        raise ValueError(f"max_total_source_bytes must be an integer from 0 to {sys.maxsize - 1}, or None")
    for value in (file_count, functions_per_file, repeats):
        if type(value) is not int or value <= 0:
            raise ValueError("fixture sizes and repeats must be positive integers")
    if type(max_file_bytes) is not int or not 1 <= max_file_bytes <= sys.maxsize - 1:
        raise ValueError(f"max_file_bytes must be an integer from 1 to {sys.maxsize - 1}")
    if tracemalloc.is_tracing():
        raise RuntimeError("Stop existing tracemalloc tracing before measuring ingestion in isolation.")
    measurements = []
    with tempfile.TemporaryDirectory(prefix="play-anything-benchmark-") as temporary:
        directory = Path(temporary) / "repository"
        directory.mkdir()
        source_bytes = 0
        fixture_started = time.perf_counter()
        for index in range(file_count):
            source = f"import module_{(index + 1) % file_count:05d}\n"
            source += "\n".join(
                f"def function_{number}(value):\n    return value + {number}\n"
                for number in range(functions_per_file)
            )
            encoded = source.encode("utf-8")
            (directory / f"module_{index:05d}.py").write_bytes(encoded)
            source_bytes += len(encoded)
        fixture_creation_seconds = time.perf_counter() - fixture_started
        cache_path = str(Path(temporary) / "summaries.sqlite") if cache else None
        if mode == "graph-page":
            database_path = Path(temporary) / "repository.sqlite"
            tracemalloc.start()
            index_started = time.perf_counter()
            try:
                with SQLiteRepositoryStore(database_path) as store:
                    index_status = store.rebuild(
                        directory, max_files=None, max_file_bytes=max_file_bytes,
                        max_total_source_bytes=max_total_source_bytes)
                index_build_seconds = time.perf_counter() - index_started
                _, index_peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            database_bytes = database_path.stat().st_size
            for repeat in range(repeats):
                with SQLiteRepositoryStore(database_path, read_only=True) as store:
                    statements = count_statements()
                    store._db.set_trace_callback(lambda _sql: next(statements))
                    tracemalloc.start()
                    query_started = time.perf_counter()
                    try:
                        page = store.graph_page(
                            directory, limit=page_limit, offset=page_offset,
                            max_edges=edge_limit, search=search)
                        query_elapsed = time.perf_counter() - query_started
                        _, query_peak = tracemalloc.get_traced_memory()
                    finally:
                        tracemalloc.stop()
                        store._db.set_trace_callback(None)
                    statement_count = next(statements) - 1
                coverage = page["coverage"]
                measurements.append({
                    "run": repeat + 1, "cache_state": "not_applicable",
                    "elapsed_seconds": query_elapsed,
                    "query_elapsed_seconds": query_elapsed,
                    "python_peak_bytes": query_peak,
                    "returned_files": coverage["returned_nodes"],
                    "matching_files": coverage["matching_nodes"],
                    "total_files": coverage["total_nodes"],
                    "total_import_edges": coverage["total_import_edges"],
                    "returned_page_edges": coverage["returned_page_edges"],
                    "omitted_page_edges": coverage["omitted_page_edges"],
                    "omitted_cross_page_edges": coverage["omitted_cross_page_edges"],
                    "query_status": coverage["status"],
                    "query_truncated": page["truncated"],
                    "sqlite_statement_count": statement_count,
                })
            return {
                "schema_version": 1,
                "workload": "synthetic_python_module_ring",
                "mode": mode,
                "fixture_files": file_count,
                "functions_per_file": functions_per_file,
                "fixture_source_bytes": source_bytes,
                "max_file_bytes": max_file_bytes,
                "max_total_source_bytes": max_total_source_bytes,
                "page_limit": page_limit, "page_offset": page_offset,
                "edge_limit": edge_limit, "search": search,
                "memory_measurement": (
                    "tracemalloc Python allocations during graph_page query only, including statement-observer overhead; "
                    "excludes fixture creation and SQLite index build; not process RSS"),
                "sqlite_database_measurement": (
                    "main SQLite file st_size in bytes; excludes sidecars and allocated-block overhead"),
                "setup_metrics": {
                    "fixture_creation_seconds": fixture_creation_seconds,
                    "index_build_seconds": index_build_seconds,
                    "index_build_python_peak_bytes": index_peak,
                    "indexed_files": index_status["file_count"],
                    "indexed_import_edges": index_status["import_edge_count"],
                    "index_partial": index_status["partial"],
                    "index_truncated": index_status["truncated"],
                    "source_bytes_read": index_status["source_bytes_read"],
                    "source_budget_bytes": index_status["source_budget_bytes"],
                    "source_budget_exhausted": index_status["source_budget_exhausted"],
                    "source_budget_exceeded_files": index_status["source_budget_exceeded_files"],
                    "source_metrics_available": index_status["source_metrics_available"],
                    "sqlite_database_bytes": database_bytes,
                },
                "python_version": sys.version.split()[0],
                "measurements": measurements,
            }
        for repeat in range(repeats):
            tracemalloc.start()
            started = time.perf_counter()
            try:
                if mode == "index":
                    count = 0
                    statuses = {}
                    for summary in iter_repository_summaries(
                        directory, max_files=None, cache_path=cache_path,
                        max_file_bytes=max_file_bytes,
                        max_total_source_bytes=max_total_source_bytes,
                        include_source_metrics=True,
                    ):
                        count += 1
                        status = summary["analysis"]
                        statuses[status] = statuses.get(status, 0) + 1
                        source_metrics = {
                            key: summary[key] for key in (
                                "source_bytes_read", "source_budget_bytes",
                                "source_budget_exhausted", "source_budget_exceeded_files",
                            )
                        }
                    result = {"files": count, "analysis_counts": statuses,
                              "source_metrics_available": bool(count), **source_metrics}
                elif mode == "world":
                    world = RepoRPGGenerator.scan_local_directory(
                        str(directory), max_files=None, cache_path=cache_path,
                        max_file_bytes=max_file_bytes,
                        max_total_source_bytes=max_total_source_bytes,
                    )
                    result = {"nodes": len(world.nodes), "edges": len(world.edges)}
                    if world.analysis is not None:
                        result.update(world.analysis)
                else:
                    database_path = Path(temporary) / "repository.sqlite"
                    with SQLiteRepositoryStore(database_path) as store:
                        status = store.rebuild(
                            directory, max_files=None, max_file_bytes=max_file_bytes,
                            max_total_source_bytes=max_total_source_bytes)
                    result = {"files": status["file_count"], "edges": status["import_edge_count"],
                              "analysis_counts": status["analysis_counts"],
                              "partial": status["partial"], "truncated": status["truncated"],
                              "source_bytes_read": status["source_bytes_read"],
                              "source_budget_bytes": status["source_budget_bytes"],
                              "source_budget_exhausted": status["source_budget_exhausted"],
                              "source_budget_exceeded_files": status["source_budget_exceeded_files"],
                              "source_metrics_available": status["source_metrics_available"],
                              "sqlite_database_bytes": database_path.stat().st_size}
                elapsed = time.perf_counter() - started
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            measurements.append({
                "run": repeat + 1,
                "cache_state": "not_applicable" if mode == "store" else "disabled" if not cache else ("cold" if repeat == 0 else "warm"),
                "elapsed_seconds": elapsed,
                "python_peak_bytes": peak,
                **result,
            })
    return {
        "schema_version": 1,
        "workload": "synthetic_python_module_ring",
        "mode": mode,
        "fixture_files": file_count,
        "functions_per_file": functions_per_file,
        "fixture_source_bytes": source_bytes,
        "max_file_bytes": max_file_bytes,
        "max_total_source_bytes": max_total_source_bytes,
        "memory_measurement": "tracemalloc Python allocations; excludes fixture creation; not process RSS",
        "sqlite_database_measurement": (
            "main SQLite file st_size in bytes; excludes sidecars and allocated-block overhead"
            if mode == "store" else "not measured"),
        "python_version": sys.version.split()[0],
        "measurements": measurements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=positive_integer, default=100)
    parser.add_argument("--functions-per-file", type=positive_integer, default=10)
    parser.add_argument("--mode", choices=("index", "world", "store", "graph-page"), default="index")
    parser.add_argument("--repeats", type=positive_integer, default=2)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--max-file-bytes", type=source_byte_limit, default=DEFAULT_MAX_SOURCE_BYTES)
    parser.add_argument("--max-total-source-bytes", type=total_source_byte_limit,
                        help="Aggregate source-byte budget for index/world/store/graph-page modes; zero inventories without reading source")
    parser.add_argument("--page-limit", type=positive_integer)
    parser.add_argument("--page-offset", type=nonnegative_integer)
    parser.add_argument("--edge-limit", type=positive_integer)
    parser.add_argument("--search", help="Literal case-sensitive file path substring for graph-page mode")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        graph_options = (args.page_limit, args.page_offset, args.edge_limit, args.search)
        if args.mode != "graph-page" and any(value is not None for value in graph_options):
            parser.error("--page-limit, --page-offset, --edge-limit, and --search require --mode graph-page")
        report = benchmark(args.files, args.functions_per_file, mode=args.mode,
                           repeats=args.repeats, cache=args.cache, max_file_bytes=args.max_file_bytes,
                           max_total_source_bytes=args.max_total_source_bytes,
                           page_limit=args.page_limit, page_offset=args.page_offset,
                           edge_limit=args.edge_limit, search=args.search)
        payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Benchmark error: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

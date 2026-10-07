# Disk-backed source indexing and visual checks

This optional path indexes file summaries and statically resolved Python imports
in SQLite without constructing a `WorldState`. The existing world generation and
Creator graph remain separate, in-memory interfaces; this is not a complete
on-disk call graph or a browser WASM parser.

## Build and query

`query-repository` opens an existing compatible index in SQLite read-only mode.
It does not create a missing database or migrate an unrelated/older schema;
use `index-repository` to initialize or rebuild the index.

```bash
python3 -m play_anything.cli index-repository /path/to/repo --database /tmp/repo.sqlite
python3 -m play_anything.cli query-repository /path/to/repo --database /tmp/repo.sqlite
python3 -m play_anything.cli query-repository /path/to/repo --database /tmp/repo.sqlite --view files --limit 100 --offset 100
python3 -m play_anything.cli query-repository /path/to/repo --database /tmp/repo.sqlite --view files --search engine
python3 -m play_anything.cli query-repository /path/to/repo --database /tmp/repo.sqlite --view dependencies --path src/service.py
python3 -m play_anything.cli query-repository /path/to/repo --database /tmp/repo.sqlite --view dependencies --path src/service.py --direction imported_by
```

The CLI defaults to 10,000 files and a 2 MiB per-file cap. `--all-files` disables
the file-count cap, while `--uncapped-file-bytes` explicitly disables the source
size cap. Query pages contain at most 1,000 records. Search is a literal,
case-sensitive substring of relative file paths, not full-text source search.
Database files must be outside the indexed repository. Use a dedicated database;
SQLite storage and the filesystem still need enough disk space.

Rebuilds stage bounded batches, then atomically switch the active generation.
Fatal traversal/storage errors leave the previous snapshot usable. Per-file
parse/size/read limitations are retained as partial-analysis evidence. A capped
scan summarizes one additional file to distinguish a true omission from an exact-cap
finish. Reads use a consistent SQLite snapshot during concurrent rebuilds.

Import edges match the existing Python import resolver, including relative
packages and `src` layouts. Missing or ambiguous modules do not become invented
internal edges; dynamic imports are not inferred. Results distinguish file counts,
import counts, partial import coverage, and configured limits. Status contains the
absolute local repository identity: it is intended for local CLI use and must be
sanitized before exposing it through an HTTP endpoint.

## Measure the actual workload

```bash
python3 scripts/benchmark_repository_ingestion.py --files 1000 --functions-per-file 5 --mode store --repeats 2
```

The fixture is a generated ring of Python modules. Reported peak memory is traced
Python allocations excluding fixture creation, not process RSS or SQLite's full
native allocation footprint. Store mode rebuilds its durable index and does not
claim summary-cache hits; `--cache` is rejected in this mode. Timing measures
elapsed wall time. Compare results on equivalent workloads under similar load.

### Local measured observations

On Python 3.14.7, a synthetic ring with five functions per file and the default
2 MiB source cap preserved 1,000 files/1,000 import edges in two rebuilds:
1.249 s and 0.472 s, with 2,396,528 and 2,332,678 traced peak Python bytes.
A separate 5,000-file/5,000-edge ring (1,220,000 source bytes) took 2.751 s
and 2,910,448 traced peak Python bytes. All snapshots were complete for their
fixtures. These are local observations, not production capacity or latency
guarantees. Store mode produces a summary/import index, so these times are not
directly comparable to world-generation timings.

Current store reports also include `sqlite_database_bytes`: the closed main
SQLite file's byte length. It excludes journal/WAL sidecars and filesystem
allocation overhead. The earlier observations above predate that field; they
do not measure native SQLite memory or whole-process RSS.

## Import a bounded SQLite graph page

```bash
python3 -m play_anything.cli index-repository /path/to/repository --database /tmp/repository.sqlite
python3 -m play_anything.cli query-repository /path/to/repository --database /tmp/repository.sqlite --view graph --limit 100 --offset 0 --edge-limit 2000 > /tmp/graph-page.json
```

The graph view emits a raw version 1 snapshot, suitable for the Graph page's JSON import or Creator's **Understand → Preview an exported graph**. Other query views retain their result envelope. Use the next offset reported in coverage to export another page; importing a page does not fetch the remaining database. `--search` is a literal, case-sensitive file-path substring. Page size is at most 1,000 files; the edge cap is at most 10,000.

These pages contain file nodes and parsed import relationships only. Edges are emitted only when both endpoints are in the page. Coverage distinguishes repository totals, filtered matches, returned files, omitted edges within the page, and incident edges crossing its boundary. A pinned SQLite read transaction keeps rows and counts on one active generation. Uncapped index settings are represented by null limits. A Creator preview does not verify source, alter a repository analysis, or complete the understanding tutorial.

Creator analysis now grants its summary scan and full graph scan separate 16 MiB source-read budgets (32 MiB combined, plus up to one growth-detection sentinel per scan). Reports expose bytes read, exhaustion, and inventory-only excluded files. An exactly filled budget need not imply omitted files; use completion and excluded-file counts. This is not a process memory bound. SQLite rebuilds now also accept `max_total_source_bytes` in the Python API, defaulting to uncapped for compatibility. The CLI defaults to a 32 MiB aggregate source-read budget; `--max-total-source-bytes 0` performs an inventory without reading source, and `--uncapped-total-source-bytes` disables only this aggregate cap. `--all-files` and `--uncapped-file-bytes` do not implicitly disable it. Reports distinguish budget exclusion from an exactly exhausted but complete scan. Migrated historical generations explicitly mark source metrics unavailable instead of inventing zero-byte measurements.

### Exact graph metadata and historical indexes

Python status queries retain exact integer settings. In graph JSON, optional cap/count fields larger than JavaScript's maximum safe integer (9,007,199,254,740,991) use a null numeric field plus a canonical decimal `<field>_exact` string. For example, `source_budget_bytes: null` with `source_budget_bytes_exact: "9223372036854775806"` is a known exact cap, not an uncapped setting. Ordinary values remain numeric; the browser validates companion syntax and range and displays exact values.

Historical migrated generations have `source_metrics_available: false` and unknown read/exhaustion/exclusion counters rather than fabricated zero values. An intermediate schema may still retain a known configured `max_total_source_bytes`; that setting is separate from unavailable measurements. Rebuild to obtain new measured read metrics. Read-only queries do not migrate a database; writable store initialization performs the additive migration while preserving indexed rows.

### Graph-page measurements

```bash
python3 scripts/benchmark_repository_ingestion.py --mode graph-page --files 1000 --functions-per-file 1 --page-limit 100 --edge-limit 2000 --repeats 1
python3 scripts/benchmark_repository_ingestion.py --mode graph-page --files 5000 --functions-per-file 1 --page-limit 100 --edge-limit 2000 --repeats 1
```

Use `--output` to save the JSON report; the fixture and SQLite database are created in temporary storage. Fixture creation and SQLite rebuild are setup costs, reported separately from the measured graph query. A local Python 3.14.7 synthetic ring fixture (one function per file, 100-file page, edge cap 2,000) produced the following single-run observations:

| Files indexed | Index setup | SQLite bytes | Page query | Python allocation peak during query | SQLite statements |
| --- | --- | --- | --- | --- | --- |
| 1,000 | 1.075 s | 2,101,248 | 0.01265 s | 130,369 bytes | 10 |
| 5,000 | 3.458 s | 10,203,136 | 0.01537 s | 130,369 bytes | 10 |

Both pages emitted 99 internal edges and reported two incident cross-page edges. Statement tracing adds measurement overhead; tracemalloc is not RSS. These observations are not a general monorepo performance guarantee.

### Aggregate-budget measurements

```bash
python3 scripts/benchmark_repository_ingestion.py --mode graph-page --files 1000 --functions-per-file 1 --repeats 1 --page-limit 100 --edge-limit 2000 --max-total-source-bytes 4096
python3 scripts/benchmark_repository_ingestion.py --mode graph-page --files 5000 --functions-per-file 1 --repeats 1 --page-limit 100 --edge-limit 2000 --max-total-source-bytes 4096
```

The optional benchmark budget applies to index, world, store and graph-page setup. World mode caps source reads while keeping the generated world in RAM; it does not imply bounded whole-world memory. The earlier disk-index single-run synthetic observations with this 4,096-byte budget were:

| Files inventoried | Files parsed | Excluded by budget | Source bytes read | Index setup | Page query | SQLite bytes |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 64 | 936 | 4,096 | 0.179 s | 0.0052 s | 1,495,040 |
| 5,000 | 64 | 4,936 | 4,096 | 0.914 s | 0.0152 s | 7,008,256 |

Both queries returned 100 inventory nodes and 64 edges using ten SQLite statements. Source admission reduces parsing work; it does not remove excluded files from inventory or imply complete import coverage. These fixture-specific measurements are not production cost or RSS guarantees.

## Screenshot capture and comparison

The application Python runtime remains standard-library-only. Playwright,
Chromium, and Sharp are optional development tools for browser/pixel checks.

```bash
python3 -m play_anything.cli creator --no-browser --port 5200 --workspace-root /tmp/play-anything-visual
node scripts/verify_dashboard_browser.mjs http://127.0.0.1:5200 /tmp/capture-one
node scripts/verify_dashboard_browser.mjs http://127.0.0.1:5200 /tmp/capture-two
node scripts/compare_dashboard_screenshots.mjs /tmp/capture-one /tmp/capture-two /tmp/comparison
node --test tests/js/*.test.mjs
```

Use `PLAYWRIGHT_MODULE_PATH`, `BROWSER_EXECUTABLE`, and `SHARP_MODULE_PATH` when
using existing local tool installations. The capture harness blocks external
HTTP requests and exercises Creator and graph interactions, eleven dashboard
routes, keyboard selection, and map layouts at four viewport widths.

Review the first capture before treating it as a baseline. Captures must use the
same code/fixtures, browser build, fonts, and viewport configuration. Repository
counts and other live fixture changes legitimately affect screenshots. This tool
does not silently update or approve baselines.

The comparator requires distinct input directories, rejects output overlapping
an input tree, and refuses failed capture reports. It compares the exact PNG set
and dimensions, normalizes PNG channels to RGBA, and writes failed pixel diffs.
Defaults allow at most 0.5% changed pixels with a per-channel threshold of 16;
optional numeric arguments override these values. Thresholds are a test policy,
not proof of perceptual or accessibility equivalence. Missing/extra captures and
dimension changes fail regardless of pixel tolerance. Pure comparison and real
PNG CLI tests include deliberate failures, alpha changes, grayscale inputs,
invalid policy values, and path overlap protections.

The dedicated graph interaction check runs independently:

Use an isolated local workbench session for these tests. Full Creator checks
retain analysis/connection records and intentionally obey the server's ten-record
caps; repeated captures eventually require restarting that test server. Do not
run the harness against a session containing user work that needs to be kept.

```bash
node scripts/verify_graph_interactions.mjs http://127.0.0.1:PORT /tmp/play-anything-graph-check
node --test tests/js/pixel_comparison.test.mjs
```

The graph check verifies two component instances, associated labels, inspector
focus restoration, neighborhood filtering, empty states, and malformed snapshots.
The full browser capture now waits for the embedded graph to contain nodes and
for Creator's local-service readiness before capturing either dashboard frame.
It also checks that mobile map overlays sit below the canvas viewport.

### Stable display-fixture captures

```bash
node scripts/verify_dashboard_browser.mjs http://127.0.0.1:PORT /tmp/capture-a --fixture-graph /tmp/fixed-graph.json
node scripts/verify_dashboard_browser.mjs http://127.0.0.1:PORT /tmp/capture-b --fixture-graph /tmp/fixed-graph.json
node scripts/compare_dashboard_screenshots.mjs /tmp/capture-a /tmp/capture-b /tmp/capture-diff 0 0
```

The opt-in fixture must be a bounded version 1 graph snapshot. The report records its SHA-256 and distinguishes fixed displayed graph data from the real bundled analysis used to register the Creator tutorial on the local server. This mode uses controlled software rendering, waits for font/paint settling, and removes lingering focus only after keyboard/focus assertions. Default runs continue to exercise live bundled repository analysis. A fixture capture is evidence of UI behavior on those bytes, not a new user repository analysis or a production GPU benchmark. Keep accepted input fixtures separate from capture outputs, and compare explicit directories; the comparator does not auto-approve a baseline.

The indexed helper checks every generated fixture's hash and size before browser launch and uploads those retained bounded bytes. It rejects modified manifests/files, path-escaping records and nonregular inputs. A legacy fixture directory without a manifest remains usable but is explicitly marked unverified. Hash integrity is not publisher authentication.

### Indexed export and Creator preview acceptance

The optional `scripts/verify_indexed_graph_browser.mjs` helper checks real CLI exports against imported node IDs, relationships and coverage, then verifies Creator preview isolation and the tutorial gate. It requires a loopback Creator server and a separate fixture directory containing `page-0.json`, `page-1.json`, `invalid-coverage.json`, and `hostile-label.json`. The first two are actual `--view graph` exports; the invalid fixture has an inconsistent `coverage.returned_nodes`, and the hostile-label fixture is a valid snapshot named `hostile-label-fixture` with a script-looking node label. The generator creates these from three synthetic Python files through the real CLI and writes exact SHA-256 hashes in `manifest.json`. Its destination must not already exist; it never overwrites an accepted baseline or reads a user repository. Generation IDs are fresh, so hashes identify an exact fixture set rather than implying independent rebuilds produce identical bytes. Fixture data is development input, not a user repository analysis.

```bash
python3 scripts/generate_indexed_graph_fixtures.py /tmp/graph-fixtures
node scripts/verify_indexed_graph_browser.mjs http://127.0.0.1:PORT /tmp/graph-fixtures /tmp/graph-browser-check
```

Use the existing optional Playwright module and browser environment variables described above. External HTTP requests are blocked. Its report records failures as failures and preserves a screenshot for diagnosis; importing these fixtures never completes Creator understanding.

## Repeatable runtime checks

```bash
python3 scripts/verify_runtime_contracts.py
python3 -W error::ResourceWarning -m unittest discover tests
```

The static check parses runtime files using Python 3.10 grammar and checks
literal import statements against the standard library and local package.
It does not execute imports or detect dynamic imports. The test-only GitHub
workflow covers Python 3.10, 3.11, 3.12, and 3.14, plus dependency-free Node
pixel tests. Action revisions are pinned to commits verified from the official
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python), and
[setup-node](https://github.com/actions/setup-node) repositories.
The hosted workflow has not been run from this local working tree.

## Boundaries still needing separate work

- SQLite serializes writers; the index is local storage, not a distributed graph DB.
- Page queries are bounded, but on-disk summaries/edges and source parsing still
  consume resources. Large real-monorepo/RSS measurements remain necessary.
- Source index, Creator symbol graph, and RPG world have different purposes and
  must not be described as equally complete analyses of every language.
- Pixel comparison complements interaction and manual accessibility review.
  Representative fixture baselines must be reviewed and maintained deliberately.


## Optional source-read budgets for full worlds

Full world generation can now cap aggregate source reads without changing
`generate_world(repo_path)` or its default behavior:

```python
from play_anything.engine import PlayAnythingEngine

engine = PlayAnythingEngine(max_total_source_bytes=32 * 1024 * 1024)
world = engine.generate_world('/path/to/repository')
print(world.analysis)
```

```bash
python3 -m play_anything.cli play /path/to/repository --max-total-source-bytes 33554432
python3 -m play_anything.cli play /path/to/repository --max-total-source-bytes 0
python3 scripts/benchmark_repository_ingestion.py --mode world --files 1000 --functions-per-file 1 --repeats 1 --max-total-source-bytes 4096
```

The budget is optional; omitting it retains uncapped aggregate reads and the
existing per-file and file-count limits. Zero keeps file inventory while skipping
nonempty source analysis. Budgeted worlds include source-read totals, analysis
status counts, budget exclusions, file-limit evidence, and explicit synthetic
fallback provenance when there is no repository inventory. Reaching the budget
exactly with no exclusions is distinct from incomplete source analysis. The CLI
prints these boundaries before the simulated gameplay preview.

This caps source reads, not total memory. Nodes, edges, rooms, quests and skills
still materialize in RAM. The disk index remains the separate path for bounded
paged graph queries. Benchmark memory reports measure Python allocations through
`tracemalloc`, not process RSS or production capacity.

Graph-page offsets must be between 0 and 9,007,199,254,740,991 inclusive so JSON
pagination arithmetic remains exact in Graph Studio. Other SQLite query views
retain their signed 64-bit offset range. Oversized graph-page offsets fail before
the query begins.


## Creator accounting and document preview limits

Creator inspection records actual source reads even when the aggregate source
budget is omitted. Summary-pass totals include the bounded file-count lookahead;
its file is not exported. Uncapped file summaries retain their prior shape, and
capped summaries retain their existing cumulative metrics. The separate graph
pass has its own read counters and scope.

In `inspect_repository`, the same configured source-byte cap is applied
independently to the summary pass and graph pass. Their combined source reads
can therefore approach twice that value; this is not one shared request-wide
budget. The separate license previews are excluded from both counters.

License-document previews are a separate bounded operation. By default,
`inspect_repository` retains the lexicographically first 32 matching root files
and at most 12,000 characters per document. It streams the root directory and
keeps only a bounded selection; total matching count and omissions remain
visible in `analysis.license_files_seen`, `license_file_limit`, and
`license_file_limit_reached`. Shortened text has `text_truncated: true`, and
`license_preview_truncated_files` reports how many previews were shortened.
Warnings make the analysis incomplete when documents or text were omitted.

The optional `max_license_files` keyword accepts 1–1,000 or `None`; `None`
retains all matching documents and opts out of the file-count bound. These are
text previews, not a complete license inventory or a legal clearance. Their
character limit is separate from source-byte accounting. Full world state and
full graph state still materialize in RAM.

Preview reads open a regular-file descriptor with no-follow/nonblocking flags
where supported, then compare pre-open, descriptor and post-open file identity
before reading. A deterministic replacement-to-symlink test confirms that
outside target text is not returned. This protects that opening boundary; it
does not freeze file contents against writes after opening or provide a
transactional snapshot of the entire repository.

## Follow-up for responsive map capture stability

Keep exact screenshot comparison as the acceptance gate. For the unresolved
320px map difference, record full canvas-pixel hashes twice in the same session:
after resize/fonts settle and after two further animation frames. Record the
intrinsic canvas dimensions, its CSS rectangle, device pixel ratio, font status
and actual reduced-motion media state alongside each hash. The current 64-by-64
sample fingerprint is diagnostic evidence, not a full-image identity test.

If the full hashes change within one session, trace resize and scheduled draws
before changing presentation code. If they remain stable but independent runs
differ, compare browser/rendering configuration next. Neither result alone
establishes a GPU-driver cause. Preserve the failed image/diff artifacts and
do not automatically approve new baselines or widen pixel tolerances.

The seventh pass added an exact full-resolution canvas comparison across two
animation frames under reduced motion, with dimensions/media/font evidence and
an explicit expected-ledger check. Both fresh complete captures passed 34 checks
and their 18 PNGs matched at zero tolerance. Direct-load, resize/navigation and
independent-process map probes also matched. This does not prove the cause of
the older failed captures or guarantee identical rasterization on every browser
and machine; the strict gate remains enabled.

## Repository roots, literal search and portable paths

The exported summary iterator now validates the root before opening its SQLite
cache. Missing and non-directory roots fail distinctly, permission failures
propagate, and an invalid root cannot create a cache database. Cache-path
symlink loops are reported as `OSError(ELOOP)` across older/newer Python path
resolution behavior. Ordinary SQLite cache errors still propagate as SQLite
errors; the optional cache is not silently discarded on failure.

SQLite file/graph search uses literal, case-sensitive Unicode-codepoint
substring matching. Percent, underscore and backslash are not SQL wildcard
operators. Composed/decomposed Unicode strings and upper/lowercase remain
distinct. Store wire paths require portable repository-relative POSIX paths;
a legal POSIX basename containing a literal backslash remains unsupported.
Such a rebuild fails rather than silently omitting the file or exporting an
ambiguous path. This constraint differs from the filesystem iterator, which
can discover that filename.

Rebuild now identifies the offending name with a bounded ASCII-escaped excerpt
while preserving the existing `ValueError` reason. The POSIX regression includes
a backslash, newline and long basename, and confirms that a failed generation
leaves the previously published index active. The guard is not silently relaxed
and no partial generation is published for this case.


## Special files and stored-summary integrity

The shared source iterator inventories extension-matching non-regular files as
`unreadable_file` without opening them. Source reads use nonblocking/no-follow
flags where supported, then verify that the opened descriptor is a regular
file. This prevents a FIFO from blocking ingestion, including replacement of
a regular file after its initial stat. The scan remains partial when a source
entry cannot be read; descriptor checks do not freeze the repository.

SQLite file/search/graph queries reject stored summaries that are malformed
JSON, non-object values, or do not match their indexed path. These are bounded
`ValueError` diagnostics without stored-content excerpts; CLI queries return
exit 1 without a traceback. They leave the active generation unchanged, so a
failed read is not presented as a successful rebuild or a newly empty index.

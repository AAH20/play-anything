# Repository ingestion and manifest validation

The runtime remains Python 3.10+ standard library only.

## Manifest contract

`schemas/realm-manifest.schema.json` is the exported Draft 2020-12 structural
contract. It is derived from the existing dataclasses, so required constructor
arguments are required properties and fields with defaults remain optional.
Unknown fields, wrong nested types, invalid enum values, non-string map keys,
and non-finite numbers are rejected. JSON Schema integer semantics allow `512.0`
but reject `512.5` and booleans for an integer property.

```python
from play_anything.core.realm_studio import RealmManifest, RealmStudioEngine

studio = RealmStudioEngine()
manifest = studio.create_template_manifest("Example Realm", "Author", "local")
payload = manifest.to_json()
restored = RealmManifest.from_json(payload)
errors = RealmManifest.validate_dict(restored.to_dict())
schema = RealmManifest.json_schema()
business_result = studio.validate_manifest(restored)
```

`from_dict` validates before conversion and does not modify or retain references
to the caller's nested dictionaries. It now raises `ValueError` with field paths
for malformed inputs. `from_json` also rejects malformed JSON. Existing valid
manifests and nested defaults continue to work.

The built-in validator implements only the keywords emitted by this schema;
it is not an arbitrary JSON Schema engine. Business rules such as minimum title
length, mandatory objectives, and the 85% creator revenue-share cap remain in
`RealmStudioEngine.validate_manifest`. Structural validity alone is not approval
to publish. No format checks or numeric business bounds are implied by export.

After changing manifest dataclasses, regenerate the schema:

```bash
python3 - <<'PY'
import json
from pathlib import Path
from play_anything.core.realm_studio import RealmManifest
Path('schemas/realm-manifest.schema.json').write_text(
    json.dumps(RealmManifest.json_schema(), indent=2) + '\n'
)
PY
```

The schema regression test detects a stale export.

## Incremental scanning

```python
from play_anything.adapters.repository_index import iter_repository_summaries
from play_anything.adapters.repo_rpg_generator import RepoRPGGenerator

# Consume summaries without materializing the full graph.
for summary in iter_repository_summaries(
    ".", max_files=None, cache_path="/tmp/play-anything-index.sqlite",
    cache_max_entries=10000,
):
    print(summary["path"], summary["analysis"])

# Existing callers keep the 50-file default and the WorldState return type.
world = RepoRPGGenerator.scan_local_directory(
    ".", cache_path="/tmp/play-anything-index.sqlite"
)
```

The iterator sorts directories and files, skips excluded directories and symlink
files, and reads/parses one source file at a time. Explicit `max_files=None`
removes the file-count cap; nonpositive or noninteger limits raise `ValueError`.
Close a partially consumed iterator when using the cache so its connection is
released promptly. No database is created unless a cache path is supplied.

Python summaries measure LOC and estimate file-level decision complexity from
the AST. Static imports resolve within the scanned files for root and `src`
layouts, including relative imports and package initializers. Edges point from
dependency to importer to match progression direction. External, dynamic, and
ambiguous imports do not produce guessed edges. Complexity is an approximation,
not a certified cyclomatic metric or vulnerability analysis.

Other supported languages have measured LOC, baseline complexity, and an
`unparsed_language` tag. Syntax/encoding failures use `python_parse_error`;
unreadable files use `unreadable_file`. Filename-based layer classification is
retained. Fabricated adjacency edges and filename-based vulnerability scores
have been removed. Consequently, real graphs can be disconnected; the existing
quest solver's fallback path is gameplay scaffolding, not proof of a code dependency.

Cache keys include repository identity, relative path, parser version, and a
SHA-256 content hash. A cache hit avoids AST parsing but still reads/hashes bytes
to detect edits independent of modification timestamps. Least-recently-used
entries are pruned to the configured row limit. Deleted files are not yielded;
their old cache entries may remain until eviction. The limit bounds row count,
not database bytes. SQLite failures propagate to the caller.

World generation still materializes nodes, summaries, and edges because current
solvers require lists. One large file must also fit in memory. This change does
not establish million-line scalability; that needs profiling and later solver work.

## Verification

Run `python3 -m unittest discover tests`. New cases cover schema drift,
serialization, defaults, malformed values, caller-data preservation, AST metrics,
relative imports, encoding, fallbacks, limits, cache identity/invalidation/eviction,
and lazy iteration. Compile changed Python files with `python3 -m py_compile`.

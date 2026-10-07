import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { DASHBOARD_BROWSER_USAGE, loadBrowserGraphFixture, MAX_GRAPH_FIXTURE_BYTES,
  parseDashboardBrowserArgs } from '../../scripts/lib/browser_graph_fixture.mjs';

async function withFixture(graph, callback) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'play-anything-graph-fixture-'));
  const file = path.join(directory, 'graph.json');
  await fs.writeFile(file, JSON.stringify(graph));
  try { await callback(file); } finally { await fs.rm(directory, { recursive: true, force: true }); }
}

const sourceGraph = () => ({ version: 1, name: 'fixed-import-fixture',
  nodes: [
    { id: 'file:pkg/a.py', name: 'a.py', kind: 'file', path: 'pkg/a.py' },
    { id: 'file:pkg/b.py', name: 'b.py', kind: 'file', path: 'pkg/b.py' },
  ],
  edges: [{ source: 'file:pkg/a.py', target: 'file:pkg/b.py', relation: 'imports' }],
  summary: { files: 2, modules: 0, functions: 0, classes: 0, relationships: 1, unresolved: 0, hubs: [] },
  warnings: [], unresolved: [], analysis: { status: 'partial', complete: false },
});

test('fixed fixture evidence has stable identity and explicit non-repository provenance', async () => {
  await withFixture(sourceGraph(), async file => {
    const first = await loadBrowserGraphFixture(file);
    const second = await loadBrowserGraphFixture(file);
    assert.equal(first.sha256, second.sha256);
    assert.equal(first.identity, `sha256:${first.sha256}`);
    assert.equal(first.report.id, second.report.id);
    assert.equal(first.graph.analysis.source_kind, 'browser_fixed_fixture');
    assert.equal(first.report.analysis.source_kind, 'browser_fixed_fixture');
    assert.equal(first.report.analysis.complete, false);
    assert.equal('source_bytes_read' in first.graph.analysis, false);
    assert.equal('source_bytes_read' in first.report.analysis, false);
    assert.match(first.report.analysis.message, /static test data, not evidence about the selected repository/);
    assert.deepEqual(first.report.edges, [['pkg/b.py', 'pkg/a.py']]);
    assert.equal(first.report.files.length, 2);
  });
});

test('fixed fixture loading rejects non-v1 or missing graph arrays', async () => {
  await withFixture({ version: 2, nodes: [], edges: [] }, async file => {
    await assert.rejects(loadBrowserGraphFixture(file), /version 1 snapshot/);
  });
});

test('fixed fixture loader rejects oversized files before reading their contents', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'play-anything-oversized-'));
  const file = path.join(directory, 'large.json');
  try {
    await fs.writeFile(file, '');
    await fs.truncate(file, MAX_GRAPH_FIXTURE_BYTES + 1);
    await assert.rejects(loadBrowserGraphFixture(file), /exceeds the 15000000-byte browser import limit/);
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});

test('browser harness fixture options reject missing paths and unknown options', () => {
  assert.deepEqual(parseDashboardBrowserArgs(['http://127.0.0.1:8000', '/tmp/output']), {
    url: 'http://127.0.0.1:8000', output: '/tmp/output', fixturePath: null,
  });
  assert.deepEqual(parseDashboardBrowserArgs(['http://127.0.0.1:8000', '/tmp/output',
    '--fixture-graph', '/tmp/graph.json']), {
    url: 'http://127.0.0.1:8000', output: '/tmp/output', fixturePath: '/tmp/graph.json',
  });
  for (const args of [
    ['http://127.0.0.1:8000', '/tmp/output', '--fixture-graph'],
    ['http://127.0.0.1:8000', '/tmp/output', '--fixture-graph', ''],
    ['http://127.0.0.1:8000', '/tmp/output', '--unknown', '/tmp/graph.json'],
  ]) assert.throws(() => parseDashboardBrowserArgs(args), new RegExp(DASHBOARD_BROWSER_USAGE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

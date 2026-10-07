import assert from 'node:assert/strict';
import test from 'node:test';

const registry = new Map();
globalThis.HTMLElement = class HTMLElement {};
globalThis.customElements = { define: (name, element) => registry.set(name, element) };
await import('../../play_anything/graph-viewer.js');
const RepoGraph = registry.get('repo-graph');

const graphFixture = () => ({
  version: 1,
  name: 'Contract fixture',
  nodes: [{ id: 'module:.', name: 'root', kind: 'module', path: '.', summary: 'Root module', confidence: 'observed', connections: 0 }],
  edges: [],
  summary: { files: 0, modules: 1, functions: 0, classes: 0, relationships: 0, unresolved: 0, hubs: [] },
  analysis: { status: 'complete', complete: true, file_count: 0 },
  warnings: [],
  unresolved: [],
});
const coverageFixture = overrides => ({ generation: 'fixture', status: 'partial', complete: false,
  total_nodes: 1, matching_nodes: 1, offset: 0, page_size: 250, returned_nodes: 1,
  has_previous: false, has_next: false, filtered: false, total_import_edges: 0,
  returned_page_edges: 0, omitted_page_edges: 0, omitted_cross_page_edges: 0,
  source_partial: false, imports_partial: false, scan_truncated: false,
  max_files: 2000, max_file_bytes: 1048576, max_edges: 2000, ...overrides });
const component = value => {
  const viewer = Object.create(RepoGraph.prototype);
  viewer.graph = value;
  return viewer;
};
const assign = value => component(value).graph;

test('valid v1 snapshots retain their analysis, nodes, and coverage page', () => {
  const graph = graphFixture();
  graph.coverage = coverageFixture({ total_nodes: 501, matching_nodes: 501, offset: 250,
    has_previous: true, has_next: true, omitted_page_edges: 2, omitted_cross_page_edges: 7 });
  assert.equal(assign(graph), graph);
});

test('uncapped SQLite snapshots may use null file and byte limits', () => {
  const graph = graphFixture();
  graph.coverage = coverageFixture({ max_files: null, max_file_bytes: null });
  assert.equal(assign(graph), graph);
});

test('migrated generations preserve a configured total cap when measured metrics are unavailable', () => {
  const graph = graphFixture();
  graph.coverage = coverageFixture({ source_metrics_available: false,
    max_total_source_bytes: 8192, source_budget_bytes: null,
    source_bytes_read: null, source_budget_exceeded_files: null,
    source_budget_exhausted: null });
  assert.equal(assign(graph), graph);
});

test('SQLite complete claims are rejected when coverage reports gaps', () => {
  const contradictions = [
    { filtered: true }, { source_partial: true }, { imports_partial: true },
    { scan_truncated: true }, { omitted_page_edges: 1 }, { omitted_cross_page_edges: 1 },
  ];
  for (const fields of contradictions) {
    const graph = graphFixture();
    graph.coverage = coverageFixture({ status: 'complete', complete: true, ...fields });
    assert.throws(() => assign(graph), /complete coverage cannot include/);
  }
});

test('complete claims cannot hide known source-budget exclusions', () => {
  const graph = graphFixture();
  graph.analysis = { status: 'partial', complete: false };
  for (const exclusion of [
    { source_budget_exceeded_files: 1 },
    { source_budget_exceeded_files: null, source_budget_exceeded_files_exact: '9007199254740992' },
  ]) {
    graph.coverage = coverageFixture({ status: 'complete', complete: true, source_partial: false,
      source_metrics_available: true, source_bytes_read: 100, source_budget_bytes: null,
      source_budget_exceeded_files: 0, source_budget_exhausted: true, ...exclusion });
    assert.throws(() => assign(graph), /source-budget exclusions/);
  }
  graph.analysis = { status: 'complete', complete: true, source_metrics_available: true,
    source_bytes_read: 100, source_budget_bytes: null, source_budget_exceeded_files: 1,
    source_budget_exhausted: true };
  delete graph.coverage;
  assert.throws(() => assign(graph), /complete analysis cannot include source-budget exclusions/);
});

test('known source-budget exclusions require explicitly partial coverage', () => {
  const graph = graphFixture();
  graph.coverage = coverageFixture({ source_metrics_available: true,
    source_bytes_read: 100, source_budget_bytes: null, source_budget_exhausted: true,
    source_budget_exceeded_files: 1, source_partial: false });
  assert.throws(() => assign(graph), /known source-budget exclusions require source_partial/);
  graph.coverage = coverageFixture({ source_metrics_available: true,
    source_bytes_read: 100, source_budget_bytes: null, source_budget_exhausted: true,
    source_budget_exceeded_files: null, source_budget_exceeded_files_exact: '9007199254740992',
    source_partial: false });
  assert.throws(() => assign(graph), /known source-budget exclusions require source_partial/);
  graph.coverage = coverageFixture({ source_metrics_available: true,
    source_bytes_read: 100, source_budget_bytes: null, source_budget_exhausted: true,
    source_budget_exceeded_files: 0, source_partial: false });
  assert.equal(assign(graph), graph, 'exact budget exhaustion with no excluded files remains valid');
});

test('malformed graph structures, duplicate IDs, and dangling edges are rejected', () => {
  const missingNodes = graphFixture(); delete missingNodes.nodes;
  const duplicateIds = graphFixture(); duplicateIds.nodes.push({ ...duplicateIds.nodes[0] });
  const dangling = graphFixture(); dangling.edges.push({ source: 'module:.', target: 'missing', relation: 'imports' });
  for (const graph of [null, {}, missingNodes, duplicateIds, dangling]) {
    assert.throws(() => assign(graph), TypeError);
  }
});

test('node and edge counts are checked before expensive traversal', () => {
  const tooManyNodes = graphFixture();
  tooManyNodes.nodes = Array(65001).fill(tooManyNodes.nodes[0]);
  assert.throws(() => assign(tooManyNodes), /65,000/);
  const tooManyEdges = graphFixture();
  tooManyEdges.edges = Array(250001).fill({ source: 'module:.', target: 'module:.', relation: 'contains' });
  assert.throws(() => assign(tooManyEdges), /250,000/);
});

test('rendered text and structural metadata have bounded safe types', () => {
  const longNode = graphFixture(); longNode.nodes[0].name = 'x'.repeat(4097);
  const badConnections = graphFixture(); badConnections.nodes[0].connections = Infinity;
  const badCoverage = graphFixture(); badCoverage.coverage = coverageFixture({ total_nodes: 'many' });
  const badBudget = graphFixture(); badBudget.analysis.source_bytes_read = Infinity;
  for (const graph of [longNode, badConnections, badCoverage, badBudget]) {
    assert.throws(() => assign(graph), TypeError);
  }
});

test('analysis status discloses source-byte budget use and skipped files', () => {
  const viewer = component(graphFixture());
  const message = viewer.formatAnalysis({ status: 'partial', message: 'Partial scan.',
    source_bytes_read: 1024, source_budget_bytes: 2048, source_budget_exceeded_files: 3,
    source_budget_exhausted: true });
  assert.match(message, /3 files skipped by the total source byte budget/);
  assert.match(message, /1024 source bytes read/);
  assert.match(message, /total source byte budget 2048 bytes/);
  assert.match(message, /the total source byte budget was exhausted/);
});

test('large source counts and caps preserve exact decimal values in v1 metadata', () => {
  const graph = graphFixture();
  graph.analysis = { source_kind: 'sqlite_file_import_page', status: 'partial',
    file_limit: null, file_limit_exact: '9223372036854775807', file_limit_reached: true,
    max_file_bytes: null, max_file_bytes_exact: '9007199254740992',
    source_metrics_available: true, source_bytes_read: null, source_bytes_read_exact: '9223372036854775807',
    source_budget_bytes: null, source_budget_bytes_exact: '9007199254740992',
    source_budget_exceeded_files: null, source_budget_exceeded_files_exact: '9007199254740992',
    source_budget_exhausted: true };
  graph.coverage = coverageFixture({ source_metrics_available: true,
    source_bytes_read: null, source_bytes_read_exact: '9223372036854775807',
    source_budget_bytes: null, source_budget_bytes_exact: '9007199254740992',
    source_budget_exceeded_files: null, source_budget_exceeded_files_exact: '9007199254740992',
    source_budget_exhausted: true,
    max_total_source_bytes: null, max_total_source_bytes_exact: '9007199254740992',
    max_files: null, max_files_exact: '9223372036854775807',
    max_file_bytes: null, max_file_bytes_exact: '9007199254740992',
    source_partial: true });
  assert.equal(assign(graph), graph);
  const viewer = component(graph);
  const analysis = viewer.formatAnalysis(graph.analysis);
  assert.match(analysis, /9223372036854775807 source bytes read/);
  assert.match(analysis, /total source byte budget 9007199254740992 bytes/);
  assert.match(analysis, /9007199254740992 files skipped by the total source byte budget/);
  assert.match(analysis, /9223372036854775807-file summary limit/);
  assert.match(analysis, /summary per-file byte cap 9007199254740992/);
  const coverage = viewer.formatCoverage(graph.coverage);
  assert.match(coverage, /9223372036854775807 source bytes were read/);
  assert.match(coverage, /Configured file limits: 9223372036854775807 files; 9007199254740992 bytes per file/);
});

test('exact decimal companions reject unsafe, malformed, out-of-range, or contradictory values', () => {
  const invalid = [
    { value: '09007199254740992', available: true },
    { value: '9007199254740991', available: true },
    { value: '9223372036854775808', available: true },
    { value: 9007199254740992, available: true },
    { value: '9007199254740992', available: false },
  ];
  for (const { value, available } of invalid) {
    const graph = graphFixture();
    graph.analysis = { source_metrics_available: available, source_bytes_read: null,
      source_bytes_read_exact: value, source_budget_bytes: null,
      source_budget_exceeded_files: null, source_budget_exhausted: available ? false : null };
    if (available) graph.analysis.source_budget_exceeded_files = 0;
    assert.throws(() => assign(graph), TypeError);
  }
  const numberAndExact = graphFixture();
  numberAndExact.analysis = { file_limit: 12, file_limit_exact: '9007199254740992' };
  assert.throws(() => assign(numberAndExact), /must be null when file_limit_exact is present/);
  const nullWithoutExact = graphFixture();
  nullWithoutExact.analysis = { source_metrics_available: true, source_bytes_read: null,
    source_budget_bytes: null, source_budget_exceeded_files: 0, source_budget_exhausted: false };
  assert.throws(() => assign(nullWithoutExact), /nonnegative safe integer/);
});

test('legacy unknown source metrics remain unavailable instead of becoming zero', () => {
  const graph = graphFixture();
  graph.analysis = { source_metrics_available: false, source_budget_bytes: null,
    source_bytes_read: null, source_budget_exhausted: null, source_budget_exceeded_files: null };
  for (const [cap, exact, shown] of [
    [8192, undefined, '8192'],
    [null, '9007199254740992', '9007199254740992'],
  ]) {
    graph.coverage = coverageFixture({ source_metrics_available: false, source_budget_bytes: null,
      max_total_source_bytes: cap, ...(exact ? { max_total_source_bytes_exact: exact } : {}),
      source_bytes_read: null, source_budget_exhausted: null, source_budget_exceeded_files: null });
    const viewer = component(graph);
    assert.equal(viewer.graph, graph);
    assert.match(viewer.formatAnalysis(graph.analysis), /unavailable for this older index generation/);
    const coverage = viewer.formatCoverage(graph.coverage);
    assert.match(coverage, /measurements are unavailable for this older index generation/);
    assert.match(coverage, new RegExp(`Configured total source-read cap: ${shown} bytes; measured usage is unavailable`));
    assert.doesNotMatch(coverage, /\d+ source bytes were read|source-byte budget was \d+/);
    assert.doesNotMatch(viewer.formatAnalysis(graph.analysis), /0 source bytes read/);
  }
});

test('SQLite coverage names source-page gaps and keeps local canvas paging distinct', () => {
  const graph = graphFixture();
  graph.coverage = coverageFixture({ total_nodes: 800, matching_nodes: 800, offset: 250,
    has_previous: true, has_next: true, omitted_page_edges: 2, omitted_cross_page_edges: 7,
    source_partial: true });
  const viewer = component(graph);
  const message = viewer.formatCoverage(graph.coverage);
  assert.match(message, /Canvas paging stays inside this imported page/);
  assert.match(message, /2 imports within this page were omitted/);
  assert.match(message, /7 imports cross this page boundary/);
  assert.match(message, /query-repository --view graph --offset 500/);
  assert.doesNotMatch(message, /Load next page|fetch next/i);
});

test('SQLite file-only snapshots do not present absent node kinds as repository totals', () => {
  const graph = graphFixture();
  graph.analysis = { source_kind: 'sqlite_file_import_page', status: 'partial' };
  graph.coverage = coverageFixture({ total_nodes: 800, matching_nodes: 800, offset: 250,
    has_previous: true, has_next: true, total_import_edges: 900 });
  const narrative = component(graph).formatNarrative(graph);
  assert.match(narrative, /page 251–251 of 800 matching paths across 800 indexed files/);
  assert.match(narrative, /900 static Python import relationships are indexed overall/);
  assert.match(narrative, /file nodes only; modules, functions, and classes are not represented/);
  assert.doesNotMatch(narrative, /0 directories|0 functions|0 classes/);
});

test('an empty SQLite page beyond the result range remains a valid bounded snapshot', () => {
  const graph = graphFixture(); graph.nodes = [];
  graph.analysis = { source_kind: 'sqlite_file_import_page', status: 'partial' };
  graph.coverage = coverageFixture({ total_nodes: 3, matching_nodes: 3, offset: 999,
    returned_nodes: 0, has_previous: true, has_next: false });
  const viewer = component(graph);
  assert.match(viewer.formatNarrative(graph), /at offset 999 \(no rows returned\)/);
  assert.match(viewer.formatCoverage(graph.coverage), /at offset 999 \(no rows returned\)/);
});

test('the component indexes incident relationships after validating input', () => {
  const graph = graphFixture();
  graph.nodes.push({ id: 'file:a.py', name: 'a.py', kind: 'file', path: 'a.py' });
  graph.edges.push({ source: 'module:.', target: 'file:a.py', relation: 'contains' });
  const viewer = component(graph);
  assert.equal(viewer.incidentEdges.get('module:.')[0], graph.edges[0]);
  assert.equal(viewer.incidentEdges.get('file:a.py')[0], graph.edges[0]);
});

test('clearing a component drops imported graph data and releases indexed edges', () => {
  const graph = graphFixture();
  graph.nodes.push({ id: 'file:a.py', name: 'a.py', kind: 'file', path: 'a.py' });
  graph.edges.push({ source: 'module:.', target: 'file:a.py', relation: 'contains' });
  const viewer = component(graph);
  viewer.clear();
  assert.equal(viewer.graph, null);
  assert.equal(viewer.incidentEdges.size, 0);
  assert.equal(viewer.visible, null);
});

test('latest-request gate keeps file import over startup response and cancels reads on clear', async () => {
  const gate = globalThis.playAnythingCreateRequestGate();
  let shown = 'previous graph';
  let resolveStartup;
  const startupRequest = gate.begin();
  const startup = new Promise(resolve => { resolveStartup = resolve; });
  const applyStartup = startup.then(graph => { if (gate.isCurrent(startupRequest)) shown = graph; });
  const fileRequest = gate.begin();
  shown = 'manually imported page';
  resolveStartup('late startup response');
  await applyStartup;
  assert.equal(shown, 'manually imported page');

  let resolveRead;
  const creatorRequest = gate.begin();
  const fileRead = new Promise(resolve => { resolveRead = resolve; });
  const applyRead = fileRead.then(graph => { if (gate.isCurrent(creatorRequest)) shown = graph; });
  gate.invalidate();
  resolveRead('late file read');
  await applyRead;
  assert.equal(shown, 'manually imported page');
  assert.ok(gate.isCurrent(fileRequest) === false);
});

test('draw renders a bounded graph and coverage panel without losing summary data', () => {
  const graph = graphFixture();
  graph.truncated = true;
  graph.coverage = coverageFixture({ total_nodes: 2, matching_nodes: 2, has_next: true });
  const viewer = component(graph);
  const svg = { innerHTML: '', contains: () => false, querySelectorAll: () => [] };
  const inspector = { innerHTML: '', contains: () => false };
  const elements = new Map([
    ['.graph-analysis', { textContent: '' }], ['.graph-narrative', { textContent: '' }],
    ['.graph-level', { value: 'module' }], ['.graph-search', { value: '' }],
    ['.graph-relation', { value: 'all' }], ['.graph-inferred', { checked: true }],
    ['.graph-caption', { textContent: '' }], ['.graph-prev', { disabled: false }],
    ['.graph-next', { disabled: false }], ['.graph-empty', { hidden: true, textContent: '' }],
    ['.graph-evidence div', { innerHTML: '' }], ['svg', svg], ['.graph-inspector', inspector],
  ]);
  viewer.querySelector = selector => elements.get(selector);
  const previousDocument = globalThis.document;
  globalThis.document = { activeElement: null };
  viewer.ready = true;
  try {
    assert.doesNotThrow(() => viewer.draw());
    assert.match(elements.get('.graph-caption').textContent, /Showing 1 of 1 matching nodes/);
    assert.match(svg.innerHTML, /data-node="module:\."/);
    assert.match(elements.get('.graph-evidence div').innerHTML, /references unresolved/);
    assert.doesNotMatch(elements.get('.graph-evidence div').innerHTML, /File limit reached/);
    graph.coverage.scan_truncated = true;
    viewer.draw();
    assert.match(elements.get('.graph-evidence div').innerHTML, /Repository scan stopped at its configured file limit/);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

test('draw escapes untrusted snapshot labels and warnings in its SVG and evidence panel', () => {
  const graph = graphFixture();
  graph.nodes[0].name = '<img src=x onerror=alert(1)>';
  graph.warnings = ['<script>alert(2)</script>'];
  const viewer = component(graph);
  const svg = { innerHTML: '', contains: () => false, querySelectorAll: () => [] };
  const inspector = { innerHTML: '', contains: () => false };
  const elements = new Map([
    ['.graph-analysis', { textContent: '' }], ['.graph-narrative', { textContent: '' }],
    ['.graph-level', { value: 'module' }], ['.graph-search', { value: '' }],
    ['.graph-relation', { value: 'all' }], ['.graph-inferred', { checked: true }],
    ['.graph-caption', { textContent: '' }], ['.graph-prev', { disabled: false }],
    ['.graph-next', { disabled: false }], ['.graph-empty', { hidden: true, textContent: '' }],
    ['.graph-evidence div', { innerHTML: '' }], ['svg', svg], ['.graph-inspector', inspector],
  ]);
  viewer.querySelector = selector => elements.get(selector);
  const previousDocument = globalThis.document;globalThis.document = { activeElement: null };viewer.ready = true;
  try {
    viewer.draw();
    assert.ok(svg.innerHTML.includes('&lt;img src=x onerror=alert(1)&gt;'));
    assert.ok(elements.get('.graph-evidence div').innerHTML.includes('&lt;script&gt;alert(2)&lt;/script&gt;'));
    assert.ok(!svg.innerHTML.includes('<img src=x'));
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});

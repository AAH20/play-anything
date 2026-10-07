/** Optional browser checks for graph accessibility, filters, focus, and errors. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { evaluateCheckLedger } from './lib/browser_check_ledger.mjs';

const require = createRequire(import.meta.url);
const args = process.argv.slice(2);
if (args.length !== 2) {
  console.error('Usage: node scripts/verify_graph_interactions.mjs http://127.0.0.1:PORT OUTPUT_DIRECTORY');
  process.exit(2);
}
const base = new URL(args[0]);
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) {
  throw new Error('Graph verification requires a loopback HTTP server.');
}
const output = path.resolve(args[1]);
await fs.mkdir(output, { recursive: true });

let playwright;
try {
  playwright = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
} catch {
  throw new Error('Playwright is optional development tooling. Install it or set PLAYWRIGHT_MODULE_PATH to an existing module.');
}

const report = { schema_version: 1, evidence_type: 'browser_graph_interactions', external_requests: 'blocked', checks: [], errors: [] };
const expectedChecks = [
  'bundled_repository_graph_loaded',
  'two_graph_instances_have_component_local_accessible_labels',
  'keyboard_focus_neighborhood_restores_node_focus',
  'neighborhood_filters_remain_effective',
  'filtered_empty_state_is_distinct',
  'empty_source_state_is_distinct',
  'malformed_snapshot_error_is_announced',
  'missing_nodes_snapshot_error_is_announced',
];
function check(name, passed, details = {}) {
  const result = { name, passed: Boolean(passed), ...details };
  report.checks.push(result);
  console.log(JSON.stringify({ check: name, passed: result.passed }));
  if (!result.passed) throw new Error(`Graph browser assertion failed: ${name}`);
}

const browser = await playwright.chromium.launch({
  headless: true,
  ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}),
});
let page;
try {
  page = await browser.newPage({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  page.setDefaultTimeout(12000);
  page.setDefaultNavigationTimeout(30000);
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['http:', 'https:'].includes(url.protocol) && url.origin !== base.origin
      ? route.abort() : route.continue();
  });
  page.on('pageerror', error => report.errors.push(error.message));
  const response = await page.goto(new URL('/graph.html', base).href, { waitUntil: 'domcontentloaded' });
  if (!response?.ok()) throw new Error('Repository graph page did not load successfully.');
  const first = page.locator('repo-graph').first();
  await first.locator('svg g[data-node]').first().waitFor({ state: 'visible', timeout: 60000 });
  check('bundled_repository_graph_loaded', true, {
    node_count: await first.locator('svg g[data-node]').count(),
    source_status: (await first.locator('.graph-analysis').innerText()).slice(0, 240),
  });

  await page.evaluate(() => {
    const firstViewer = document.querySelector('repo-graph');
    const secondViewer = document.createElement('repo-graph');
    document.body.append(secondViewer);
    secondViewer.graph = firstViewer.graph;
  });
  const second = page.locator('repo-graph').nth(1);
  await second.locator('svg g[data-node]').first().waitFor({ state: 'visible' });
  const labels = await first.locator('label').evaluateAll(elements => elements.map(label => ({
    caption: [...label.childNodes].filter(node => node.nodeType === Node.TEXT_NODE)
      .map(node => node.textContent).join('').trim(),
    className: label.control?.className || '',
    associated: Boolean(label.control && Array.from(label.control.labels || []).includes(label)),
  })));
  const expectedControls = ['graph-level', 'graph-search', 'graph-relation', 'graph-inferred'];
  const roleByControl = { 'graph-level': 'combobox', 'graph-search': 'searchbox', 'graph-relation': 'combobox', 'graph-inferred': 'checkbox' };
  const labelResults = { captions: labels.map(label => label.caption), controls: labels.map(label => label.className) };
  labelResults.wrapped_and_named = labels.length === expectedControls.length
    && labels.every(label => label.caption && expectedControls.includes(label.className) && label.associated)
    && expectedControls.every(className => labels.filter(label => label.className === className).length === 1);
  for (const label of labels) {
    const controls = page.getByRole(roleByControl[label.className], { name: label.caption, exact: false });
    labelResults[label.className] = await controls.count();
    if (labelResults[label.className] !== 2) continue;
    labelResults[`${label.className}_local`] = await controls.evaluateAll((elements, expectedClass) =>
      elements[0].closest('repo-graph') !== elements[1].closest('repo-graph')
      && elements.every(element => element.className === expectedClass
        && element.labels?.length === 1 && element.labels[0].control === element), label.className);
  }
  check('two_graph_instances_have_component_local_accessible_labels',
    labelResults.wrapped_and_named === true && expectedControls.every(className =>
      labelResults[className] === 2 && labelResults[`${className}_local`] === true), { labelResults });

  await first.locator('.graph-level').selectOption('all');
  const candidate = await first.evaluate(viewer => {
    const graph = viewer.graph;
    const nodes = new Map(graph.nodes.map(node => [node.id, node]));
    const visible = viewer.visible || [];
    for (const selected of visible) {
      const neighborIds = new Set([selected.id]);
      for (const edge of graph.edges) {
        if (edge.source === selected.id) neighborIds.add(edge.target);
        if (edge.target === selected.id) neighborIds.add(edge.source);
      }
      const neighbors = [...neighborIds].map(id => nodes.get(id)).filter(Boolean);
      for (const target of neighbors) {
        if (target.id === selected.id) continue;
        const query = target.name.trim().toLowerCase();
        if (query.length < 3) continue;
        const matching = neighbors.filter(node => `${node.name} ${node.path}`.toLowerCase().includes(query));
        if (matching.length === 1 && matching[0].id === target.id) {
          return { selected: selected.id, target: target.id, query, neighborhood_size: neighbors.length };
        }
      }
    }
    return null;
  });
  if (!candidate) throw new Error('Bundled graph has no visible neighborhood with a uniquely searchable neighbor.');
  const selectedIndex = await first.locator('svg g[data-node]').evaluateAll((elements, id) =>
    elements.findIndex(element => element.dataset.node === id), candidate.selected);
  if (selectedIndex < 0) throw new Error('Selected neighborhood node is not present in the graph viewport.');
  await first.locator('svg g[data-node]').nth(selectedIndex).click();
  const neighborhoodButton = first.locator('.graph-inspector .graph-focus');
  await neighborhoodButton.focus();
  await page.keyboard.press('Enter');
  const restoredFocus = await page.evaluate(() => document.activeElement?.getAttribute('data-node'));
  check('keyboard_focus_neighborhood_restores_node_focus', restoredFocus === candidate.selected,
    { expected_focus: candidate.selected, actual_focus: restoredFocus });

  await first.locator('.graph-search').fill(candidate.query);
  await page.waitForFunction(() => {
    const viewer = document.querySelector('repo-graph');
    return viewer?.focused && viewer.visible?.length === 1;
  });
  const filtered = await first.evaluate(viewer => ({
    focused: viewer.focused,
    visible: viewer.visible.map(node => node.id),
    caption: viewer.querySelector('.graph-caption').textContent,
  }));
  check('neighborhood_filters_remain_effective', filtered.focused
    && filtered.visible.length === 1 && filtered.visible[0] === candidate.target,
  { expected_visible: candidate.target, ...filtered });

  await first.locator('.graph-search').fill('no-match-fixture-7f2d46a1');
  await page.waitForFunction(() => document.querySelector('repo-graph')?.visible?.length === 0);
  const noMatch = await first.locator('.graph-caption').innerText();
  check('filtered_empty_state_is_distinct', noMatch.includes('No nodes match the current filters.'), { caption: noMatch });

  await page.evaluate(() => {
    document.querySelector('repo-graph').graph = {
      name: 'Empty graph verification fixture', nodes: [], edges: [], summary: {},
      analysis: { status: 'empty', complete: false, message: 'No supported source files were found.' },
      warnings: [], unresolved: [],
    };
  });
  const emptySource = await first.locator('.graph-caption').innerText();
  check('empty_source_state_is_distinct', emptySource.includes('No source nodes were found.'), { caption: emptySource });

  const file = page.locator('#graph-file');
  await file.setInputFiles({ name: 'malformed-graph.json', mimeType: 'application/json', buffer: Buffer.from('{broken') });
  await page.waitForFunction(() => /JSON|Unexpected|position/i.test(document.querySelector('#graph-status')?.textContent || ''));
  const malformed = await page.locator('#graph-status').innerText();
  check('malformed_snapshot_error_is_announced', /JSON|Unexpected|position/i.test(malformed), { status: malformed });
  await file.setInputFiles({ name: 'missing-nodes.json', mimeType: 'application/json', buffer: Buffer.from('{"edges":[]}') });
  await page.waitForFunction(() => /Graph could not be loaded .*Invalid graph snapshot:/.test(document.querySelector('#graph-status')?.textContent || ''));
  const missingNodes = await page.locator('#graph-status').innerText();
  check('missing_nodes_snapshot_error_is_announced', /Graph could not be loaded .*Invalid graph snapshot:/.test(missingNodes), { status: missingNodes });
} catch (error) {
  report.errors.push(error.message);
  if (page) {
    report.failure_state = await page.evaluate(() => ({
      url: location.href,
      status: document.querySelector('#graph-status')?.textContent || '',
      caption: document.querySelector('repo-graph .graph-caption')?.textContent || '',
    })).catch(() => null);
  }
} finally {
  await browser.close();
}
report.check_ledger = evaluateCheckLedger(report.checks, expectedChecks);
if (!report.check_ledger.ledger_pass) report.errors.push('Check ledger mismatch: expected check names were missing, duplicated, invalid, or unexpected.');
report.passed = report.errors.length === 0 && report.check_ledger.ledger_pass && report.check_ledger.failed_count === 0;
await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;

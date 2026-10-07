// Optional local-only acceptance check: index CLI exports -> browser graph import.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { evaluateCheckLedger } from './lib/browser_check_ledger.mjs';
import { loadIndexedGraphFixtures } from './visual/fixture_manifest.mjs';

const [baseArgument, fixtureArgument, outputArgument] = process.argv.slice(2);
if (!baseArgument || !fixtureArgument || !outputArgument) {
  console.error('Usage: node verify_indexed_graph_browser.mjs LOOPBACK_URL FIXTURE_DIRECTORY OUTPUT_DIRECTORY');
  process.exit(2);
}
const base = new URL(baseArgument);
if (base.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) {
  throw new Error('A loopback HTTP test server is required.');
}
const fixtures = path.resolve(fixtureArgument), output = path.resolve(outputArgument);
if (fixtures === output || fixtures.startsWith(output + path.sep) || output.startsWith(fixtures + path.sep)) {
  throw new Error('Fixtures and browser output must be separate directories.');
}
await fs.mkdir(output, { recursive: true });
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const report = { schema_version: 1, evidence_type: 'indexed_graph_browser_flow', external_requests: 'blocked', checks: [], errors: [] };
const expectedChecks = [
  'file_detail_option_page_0', 'indexed_page_0_matches_export', 'indexed_page_0_announces_scope',
  'file_detail_option_page_1', 'indexed_page_1_matches_export', 'indexed_page_1_announces_scope',
  'graph_search_and_filter_controls_have_accessible_names', 'keyboard_search_filters_to_matching_file',
  'no_match_search_announces_empty_state', 'keyboard_node_selection_updates_inspector',
  'focus_neighborhood_announces_scope', 'focus_neighborhood_relationship_count_matches_export',
  'relationship_filter_updates_visible_link_count', 'invalid_coverage_rejected_without_replacing_valid_graph',
  'untrusted_label_remains_text', 'creator_baseline_is_bundled_repository_scan',
  'creator_preview_is_browsing_only_and_source_scoped', 'valid_preview_preserves_creator_state_and_plan',
  'creator_invalid_preview_keeps_previous_graph', 'invalid_preview_preserves_creator_state_and_plan',
  'clear_preview_preserves_analysis_plan_and_tutorial_gate', 'preview_does_not_complete_tutorial_or_open_compose',
  'no_browser_page_errors',
];
let fixturePayloads;
try {
  const loaded = await loadIndexedGraphFixtures(fixtures);
  report.fixture_integrity = loaded.integrity;
  fixturePayloads = loaded.payloads;
}
catch (error) {
  report.passed = false;
  report.errors.push(`Fixture integrity: ${error.message}`);
  await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.error(report.errors[0]);
  process.exit(1);
}
const firstFixtureBytes = fixturePayloads.get('page-0.json');
report.fixture_evidence = { type: 'fixed_indexed_graph_snapshot', file: 'page-0.json',
  sha256: createHash('sha256').update(firstFixtureBytes).digest('hex'), bytes: firstFixtureBytes.byteLength,
  claim: 'Static exported graph page fixture; not a live repository analysis.' };
const upload = name => ({ name, mimeType: 'application/json', buffer: fixturePayloads.get(name) });
function check(name, passed, details = {}) {
  report.checks.push({ name, passed, ...details });
  console.log(JSON.stringify({ check: name, passed }));
  if (!passed) throw new Error(`Indexed graph check failed: ${name}`);
}
const browser = await chromium.launch({ headless: true,
  ...(process.env.BROWSER_EXECUTABLE ? { executablePath: process.env.BROWSER_EXECUTABLE } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
const page = await context.newPage();
page.setDefaultTimeout(15000);
const pageErrors = [], dialogs = [];
page.on('pageerror', error => pageErrors.push(error.message));
page.on('dialog', async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
await context.route('**/*', route => {
  const url = new URL(route.request().url());
  return ['http:', 'https:'].includes(url.protocol) && url.origin !== base.origin ? route.abort() : route.continue();
});
try {
  await page.goto(new URL('/graph.html', base).href, { waitUntil: 'domcontentloaded', timeout: 30000 });
  const viewer = page.locator('repo-graph').first();
  const input = page.locator('input[type=file]');
  for (const [pageIndex, name] of ['page-0.json', 'page-1.json'].entries()) {
    const expected = JSON.parse(fixturePayloads.get(name).toString('utf8'));
    await input.setInputFiles(upload(name));
    await page.waitForFunction(offset => document.querySelector('repo-graph')?.graph?.coverage?.offset === offset,
      expected.coverage.offset, { timeout: 15000 });
    const options = await viewer.locator('.graph-level option').evaluateAll(elements => elements.map(element => ({ value: element.value, text: element.textContent })));
    const filesOption = options.find(option => /^Files\b/.test(option.text));
    check(`file_detail_option_page_${pageIndex}`, Boolean(filesOption));
    await viewer.locator('.graph-level').selectOption(filesOption.value);
    if (expected.nodes.length) await viewer.locator('svg g[data-node]').first().waitFor({ state: 'visible' });
    const actual = await viewer.evaluate(element => ({ ids: element.graph.nodes.map(node => node.id),
      coverage: element.graph.coverage, edges: element.graph.edges,
      renderedIds: [...element.querySelectorAll('svg g[data-node]')].map(node => node.dataset.node) }));
    check(`indexed_page_${pageIndex}_matches_export`, JSON.stringify(actual.ids) === JSON.stringify(expected.nodes.map(node => node.id)) &&
      JSON.stringify(actual.coverage) === JSON.stringify(expected.coverage) &&
      JSON.stringify(actual.edges) === JSON.stringify(expected.edges) && actual.renderedIds.every(id => actual.ids.includes(id)),
      { node_count: actual.ids.length, rendered_count: actual.renderedIds.length, offset: actual.coverage.offset });
    const analysis = await viewer.locator('.graph-analysis').innerText();
    check(`indexed_page_${pageIndex}_announces_scope`, /SQLite|indexed/i.test(analysis) && /page/i.test(analysis) && /imports|import/i.test(analysis), { analysis });
    await page.screenshot({ path: path.join(output, name.replace('.json', '.png')), fullPage: true });
  }
  const interactionFixture = JSON.parse(fixturePayloads.get('page-0.json').toString('utf8'));
  await input.setInputFiles(upload('page-0.json'));
  await page.waitForFunction(() => document.querySelector('repo-graph')?.graph?.coverage?.offset === 0);
  const searchbox = viewer.getByRole('searchbox', { name: 'Find a node' });
  const detailControl = viewer.getByRole('combobox', { name: 'Detail' });
  const relationshipControl = viewer.getByRole('combobox', { name: 'Relationship' });
  check('graph_search_and_filter_controls_have_accessible_names',
    await searchbox.count() === 1 && await detailControl.count() === 1 && await relationshipControl.count() === 1);
  await detailControl.selectOption('file');
  await searchbox.focus();
  await page.keyboard.type(interactionFixture.nodes[0].name);
  const matchedNodes = await viewer.locator('svg g[data-node]').evaluateAll(elements => elements.map(element => element.dataset.node));
  check('keyboard_search_filters_to_matching_file', matchedNodes.length === 1 && matchedNodes[0] === interactionFixture.nodes[0].id,
    { query: interactionFixture.nodes[0].name, matchedNodes });
  await searchbox.fill('__play_anything_no_matching_path__');
  check('no_match_search_announces_empty_state', await viewer.locator('.graph-empty').isVisible() &&
    /No nodes match the current filters/.test(await viewer.locator('.graph-caption').innerText()));
  await searchbox.fill('');
  const keyboardNode = viewer.locator('svg g[data-node]').first();
  const focusedNodeId = await keyboardNode.getAttribute('data-node');
  const focusedNode = interactionFixture.nodes.find(node => node.id === focusedNodeId);
  await keyboardNode.focus();
  await page.keyboard.press('Enter');
  check('keyboard_node_selection_updates_inspector', await viewer.locator('svg g[data-node][aria-pressed="true"]').getAttribute('data-node') === focusedNodeId &&
    await viewer.locator('.graph-inspector h4').innerText() === focusedNode?.name);
  await viewer.locator('.graph-inspector .graph-focus').click();
  const neighborhoodCaption = await viewer.locator('.graph-caption').innerText();
  const expectedNeighborhoodEdges = interactionFixture.edges.filter(edge => edge.source === focusedNodeId || edge.target === focusedNodeId).length;
  check('focus_neighborhood_announces_scope', /in the selected neighborhood/.test(neighborhoodCaption));
  check('focus_neighborhood_relationship_count_matches_export', neighborhoodCaption.includes(`${expectedNeighborhoodEdges} links on this page.`),
    { expectedNeighborhoodEdges, neighborhoodCaption });
  await relationshipControl.selectOption('calls');
  check('relationship_filter_updates_visible_link_count', /0 links on this page/.test(await viewer.locator('.graph-caption').innerText()));
  const before = await viewer.evaluate(element => element.graph.nodes.map(node => node.id));
  await input.setInputFiles(upload('invalid-coverage.json'));
  await page.locator('#graph-status').filter({ hasText: /Invalid graph snapshot/ }).waitFor();
  const after = await viewer.evaluate(element => element.graph.nodes.map(node => node.id));
  check('invalid_coverage_rejected_without_replacing_valid_graph', JSON.stringify(before) === JSON.stringify(after),
    { status: await page.locator('#graph-status').innerText() });
  await input.setInputFiles(upload('hostile-label.json'));
  await page.waitForFunction(() => document.querySelector('repo-graph')?.graph?.name === 'hostile-label-fixture');
  check('untrusted_label_remains_text', await viewer.locator('script').count() === 0 && dialogs.length === 0,
    { dialogs });

  // Creator preview is intentionally ephemeral: it cannot satisfy repository
  // analysis or the tutorial gate, and malformed imports must preserve it.
  await page.goto(new URL('/creator.html#connect', base).href, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.locator('#connect').click();
  await page.locator('#connection-status').filter({ hasText: 'Handoff ready' }).waitFor();
  await page.locator('#to-repository').click();
  await page.locator('#analyze-local').waitFor({ state: 'visible' });
  await page.locator('#analyze-local').click();
  await page.waitForFunction(() => Boolean(window.CreatorWorkbench?.getState()?.report?.id), null, { timeout: 30000 });
  const creatorProjection = () => page.evaluate(() => {
    const state = window.CreatorWorkbench.getState();
    const plan = window.CreatorWorkbench.getPlan();
    return {
      state: {
        report: state.report ? { id: state.report.id, name: state.report.name, url: state.report.url,
          source_kind: state.report.analysis?.source_kind, analysis_status: state.report.analysis?.status,
          sample_fallback: state.report.analysis?.sample_fallback } : null,
        completed: state.completed, demo: state.demo, step: state.step,
        sourceModules: [...state.sourceModules], selected: [...state.selected],
        connection: state.connection ? { mode: state.connection.mode, harness: state.connection.harness,
          status: state.connection.status, model: state.connection.model || null } : null,
      },
      plan: plan ? { setup: plan.setup, profit: plan.profit,
        moduleIds: (plan.modules || []).map(item => item.id), rowIds: (plan.rows || []).map(item => item.id) } : null,
    };
  });
  const creatorBefore = await creatorProjection();
  check('creator_baseline_is_bundled_repository_scan', creatorBefore.state.report?.source_kind === 'bundled_sample' &&
    creatorBefore.state.report?.analysis_status === 'sample_repo' && creatorBefore.state.report?.sample_fallback === true,
    { source_kind: creatorBefore.state.report?.source_kind, analysis_status: creatorBefore.state.report?.analysis_status,
      sample_fallback: creatorBefore.state.report?.sample_fallback });
  const validCreatorFixture = JSON.parse(fixturePayloads.get('page-0.json').toString('utf8'));
  await page.locator('#graph-preview-file').setInputFiles(upload('page-0.json'));
  await page.waitForFunction(offset => document.querySelector('#imported-graph-viewer')?.graph?.coverage?.offset === offset,
    validCreatorFixture.coverage.offset, { timeout: 15000 });
  await page.locator('#imported-graph-preview').waitFor({ state: 'visible' });
  const creatorPreviewText = await page.locator('#graph-preview-status').innerText();
  const previewScope = await page.locator('#imported-graph-viewer .graph-analysis').innerText();
  check('creator_preview_is_browsing_only_and_source_scoped', /browsing only/i.test(creatorPreviewText) &&
    /page|SQLite|indexed/i.test(previewScope), { creatorPreviewText, previewScope });
  await page.screenshot({ path: path.join(output, 'creator-graph-preview.png'), fullPage: true });
  const creatorAfterValid = await creatorProjection();
  check('valid_preview_preserves_creator_state_and_plan', JSON.stringify(creatorAfterValid) === JSON.stringify(creatorBefore),
    { before: creatorBefore, after: creatorAfterValid });

  await page.locator('#graph-preview-file').setInputFiles(upload('invalid-coverage.json'));
  await page.locator('#graph-preview-status').filter({ hasText: /Could not import graph preview:.*Invalid graph snapshot/i }).waitFor();
  const retainedCreatorGraph = await page.locator('#imported-graph-viewer').evaluate(element => ({
    name: element.graph?.name, coverage: element.graph?.coverage,
  }));
  check('creator_invalid_preview_keeps_previous_graph', retainedCreatorGraph.name === validCreatorFixture.name &&
    retainedCreatorGraph.coverage?.offset === validCreatorFixture.coverage.offset);
  const creatorAfterInvalid = await creatorProjection();
  check('invalid_preview_preserves_creator_state_and_plan', JSON.stringify(creatorAfterInvalid) === JSON.stringify(creatorBefore),
    { before: creatorBefore, after: creatorAfterInvalid });

  await page.locator('#graph-preview-clear').click();
  await page.locator('#imported-graph-preview').waitFor({ state: 'hidden' });
  const creatorAfterClear = await creatorProjection();
  check('clear_preview_preserves_analysis_plan_and_tutorial_gate', JSON.stringify(creatorAfterClear) === JSON.stringify(creatorBefore) &&
    creatorAfterClear.state.completed === false && creatorAfterClear.state.step === 1);
  await page.locator('button[data-step="2"]').click();
  const gatedCreator = await creatorProjection();
  check('preview_does_not_complete_tutorial_or_open_compose', gatedCreator.state.completed === false &&
    gatedCreator.state.step === 1 && /Complete the short repository tutorial first/i.test(await page.locator('#notice').innerText()));
  check('no_browser_page_errors', pageErrors.length === 0, { pageErrors });
} catch (error) {
  report.errors.push(error.message);
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  report.failure_state = { url: page.url(), status: await page.locator('#graph-status, #graph-preview-status').first().innerText().catch(() => '') };
} finally {
  await browser.close();
}
report.check_ledger = evaluateCheckLedger(report.checks, expectedChecks);
if (!report.check_ledger.ledger_pass) report.errors.push('Check ledger mismatch: expected check names were missing, duplicated, invalid, or unexpected.');
report.passed = report.errors.length === 0 && report.check_ledger.ledger_pass && report.check_ledger.failed_count === 0;
await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: report.passed, checks: report.checks.length, errors: report.errors }));
if (!report.passed) process.exitCode = 1;

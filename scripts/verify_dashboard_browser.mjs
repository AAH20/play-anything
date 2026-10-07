/** Optional development verification using Playwright; no Python runtime dependency.
 * Screenshots are evidence, not pixel-regression comparisons against golden baselines.
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { DASHBOARD_BROWSER_USAGE, loadBrowserGraphFixture, parseDashboardBrowserArgs } from './lib/browser_graph_fixture.mjs';
import { evaluateCheckLedger } from './lib/browser_check_ledger.mjs';
import { compareCanvasPixelBuffers } from './visual/canvas_pixel_stability.mjs';

const require = createRequire(import.meta.url);
let parsedArgs;
try { parsedArgs = parseDashboardBrowserArgs(process.argv.slice(2)); }
catch { console.error(DASHBOARD_BROWSER_USAGE); process.exit(2); }
const { url, output: outputDirectory, fixturePath } = parsedArgs;
const base = new URL(url);
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) {
  throw new Error('Verification requires an HTTP loopback server.');
}
const output = path.resolve(outputDirectory);
await fs.mkdir(output, { recursive: true });
const fixedFixture = fixturePath ? await loadBrowserGraphFixture(fixturePath) : null;
let playwright;
try {
  playwright = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
} catch {
  throw new Error('Playwright is optional development tooling. Install it or set PLAYWRIGHT_MODULE_PATH to an existing module.');
}
const options = { headless: true };
if (fixedFixture) options.args = ['--disable-gpu'];
if (process.env.BROWSER_EXECUTABLE) options.executablePath = process.env.BROWSER_EXECUTABLE;
const browser = await playwright.chromium.launch(options);
const report = { schema_version: 1, evidence_type: 'browser_interaction_and_screenshot', external_requests: 'blocked', checks: [], errors: [] };
if (fixedFixture) report.fixture_evidence = {
  type: 'fixed_browser_fixture', identity: fixedFixture.identity, sha256: fixedFixture.sha256,
  file: fixedFixture.file, bytes: fixedFixture.bytes,
  claim: 'The displayed graph is deterministic fixture data, not evidence about a live repository.',
  registration: 'The local service scans its bundled sample only to register a real analysis ID for the tutorial gate; its returned graph content is replaced by this fixed fixture.',
};
const appendChecks = report.checks.push.bind(report.checks);
report.checks.push = (...checks) => {
  for (const check of checks) console.log(JSON.stringify({ check: check.name, route: check.route, width: check.width, passed: check.passed }));
  return appendChecks(...checks);
};
const routes = ['graph', 'quickstart', 'map', 'skills', 'battle', 'voice', 'benchmarks', 'studio', 'personalization', 'enterprise', 'swarm'];
function expectedDashboardChecks(fixed) {
  const expected = [
    'creator_loaded', 'creator_initial_progress_is_announced', 'creator_progress_tracks_tutorial_completion',
    'creator_prepares_handoff_without_provider', 'failed_endpoint_clears_key_and_prior_connection',
    fixed ? 'creator_fixed_fixture_provenance' : 'creator_bundled_repository_provenance',
    'creator_module_selection', 'creator_business_preview', 'creator_tiny_price_rejects_and_recovers', 'graph_keyboard_selection_retains_focus',
    'graph_search_filters_nodes', 'graph_detail_filter_selects_files',
    'map_keyboard_selection_reveals_fog_and_updates_inspector', 'illustrative_metrics_are_labeled_as_demo',
  ];
  for (const route of routes) {
    expected.push(`direct_hash_route:${route}`);
    if (route === 'graph') expected.push(fixed ? 'embedded_fixed_fixture_graph_loaded' : 'embedded_graph_loaded');
    if (route === 'quickstart') expected.push('embedded_creator_loaded');
    if (route === 'map') expected.push('map_renders_with_reduced_motion');
  }
  for (const width of [320, 768, 1024, 1920]) {
    if (width <= 720) expected.push(`mobile_map_overlays_leave_canvas_clear:${width}`);
    expected.push(`map_document_fits_viewport:${width}`, `map_renders_after_resize:${width}`);
    if (width === 320) expected.push('map_canvas_pixel_stability_under_reduced_motion:320');
    expected.push(`creator_compose_costing_responsive:${width}`, `graph_detail_responsive:${width}`);
  }
  expected.push('keyboard_view_selection');
  return expected;
}
function canvasEvidence() {
  const canvas = document.querySelector('#view-map canvas');
  if (!canvas || !canvas.width || !canvas.height) return { drawn: false };
  const sample = document.createElement('canvas');
  sample.width = sample.height = 64;
  const context = sample.getContext('2d');
  const colors = new Set();
  if (!context) return { drawn: false };
  context.drawImage(canvas, 0, 0, 64, 64);
  const { data } = context.getImageData(0, 0, 64, 64);
  let fingerprint = 2166136261;
  for (let index = 0; index < data.length; index += 4) {
    colors.add(`${data[index]},${data[index + 1]},${data[index + 2]},${data[index + 3]}`);
    for (let channel = 0; channel < 4; channel++) {
      fingerprint = Math.imul(fingerprint ^ data[index + channel], 16777619) >>> 0;
    }
  }
  const rect = canvas.getBoundingClientRect();
  return {
    drawn: colors.size > 2,
    bounded: canvas.width <= innerWidth * 2 && canvas.height <= innerHeight * 2,
    colors: colors.size,
    width: canvas.width,
    height: canvas.height,
    prefersReducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    canvasRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    sampleFingerprint: fingerprint.toString(16).padStart(8, '0'),
  };
}
async function canvasPixelStabilityEvidence(page) {
  const frames = await page.evaluate(async () => {
    const canvas = document.querySelector('#view-map canvas');
    const context = canvas?.getContext('2d');
    if (!canvas || !context) throw new Error('Map canvas is unavailable for pixel stability capture.');
    const capture = () => {
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let binary = '';
      for (let offset = 0; offset < pixels.length; offset += 0x8000) {
        binary += String.fromCharCode(...pixels.subarray(offset, Math.min(offset + 0x8000, pixels.length)));
      }
      return btoa(binary);
    };
    const before = { width: canvas.width, height: canvas.height, pixels: capture() };
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const after = { width: canvas.width, height: canvas.height, pixels: capture() };
    const rect = canvas.getBoundingClientRect();
    return {
      before,
      after,
      prefersReducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
      fontsStatus: document.fonts?.status || 'unavailable',
      canvasRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  });
  const dimensionsStable = frames.before.width === frames.after.width && frames.before.height === frames.after.height;
  const pixelComparison = dimensionsStable
    ? compareCanvasPixelBuffers(Buffer.from(frames.before.pixels, 'base64'), Buffer.from(frames.after.pixels, 'base64'), frames.before.width, frames.before.height)
    : { changedPixels: null, changedChannels: null, maxChannelDelta: null, bounds: null };
  return {
    dimensionsBefore: [frames.before.width, frames.before.height],
    dimensionsAfter: [frames.after.width, frames.after.height],
    dimensionsStable,
    prefersReducedMotion: frames.prefersReducedMotion,
    fontsStatus: frames.fontsStatus,
    canvasRect: frames.canvasRect,
    ...pixelComparison,
  };
}
async function settleFixturePaint(page) {
  await page.evaluate(() => document.fonts?.ready);
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
let page;
try {
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (fixedFixture && url.origin === base.origin) {
      const request = route.request();
      if (url.pathname === '/api/analyze' && request.method() === 'POST') {
        let body = {};
        try { body = request.postDataJSON(); } catch { /* Invalid request stays on the real server path. */ }
        if (body?.sample === true) {
          // Let the local service establish a real analysis ID so its tutorial gate
          // remains exercised; replace only the displayed report/graph with fixed data.
          const response = await route.fetch();
          if (!response.ok()) return route.fulfill({ response });
          const registered = await response.json();
          if (typeof registered.id !== 'string' || !registered.id) throw new Error('Local analysis registration returned no analysis ID.');
          return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...fixedFixture.report, id: registered.id }) });
        }
      }
      if (url.pathname === '/api/graph' && request.method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixedFixture.graph) });
      }
    }
    return ['http:', 'https:'].includes(url.protocol) && url.origin !== base.origin ? route.abort() : route.continue();
  });
  page.setDefaultTimeout(15000);
  page.setDefaultNavigationTimeout(60000);
  page.on('pageerror', error => report.errors.push(error.message));
  const creator = await page.goto(new URL('/', base).href, { waitUntil: 'domcontentloaded' });
  if (!creator?.ok()) throw new Error('Creator HTTP page did not load successfully.');
  await page.locator('h1').waitFor({ state: 'visible' });
  await page.screenshot({ path: path.join(output, 'creator-desktop.png'), fullPage: true });
  report.checks.push({ name: 'creator_loaded', passed: true, title: await page.title() });
  const initialProgress = await page.evaluate(() => ({
    sidebar: [...document.querySelectorAll('#side-steps [aria-current="step"]')].map(element => element.dataset.step),
    stepper: [...document.querySelectorAll('.stepper [aria-current="step"]')].map(element => element.dataset.step),
    visiblePanel: [...document.querySelectorAll('[data-panel]')].filter(element => !element.hidden).map(element => element.dataset.panel),
  }));
  report.checks.push({ name: 'creator_initial_progress_is_announced', passed:
    JSON.stringify(initialProgress.sidebar) === '["0"]' && JSON.stringify(initialProgress.stepper) === '["0"]' &&
    JSON.stringify(initialProgress.visiblePanel) === '["0"]', progress: initialProgress });
  await page.locator('#service-status').filter({ hasText: 'Local service ready' }).waitFor();
  await page.locator('#connect').click();
  await page.locator('#connection-status').filter({ hasText: 'Handoff ready' }).waitFor();
  report.checks.push({ name: 'creator_prepares_handoff_without_provider', passed: true });
  await page.locator('#connection-mode').selectOption('endpoint');
  await page.locator('#endpoint').fill('not-a-valid-endpoint');
  await page.locator('#model').fill('verification-fixture');
  await page.locator('#api-key').fill('invalid-test-fixture');
  await page.locator('#connect').click();
  await page.waitForFunction(() => document.querySelector('#api-key').value === '' && !document.querySelector('#connect').disabled);
  const inactive = await page.locator('#connection-status').innerText();
  const inactiveSummary = await page.locator('#summary-agent').innerText();
  await page.locator('#to-repository').click();
  const blocked = await page.locator('[data-panel="0"]').isVisible() && !await page.locator('[data-panel="1"]').isVisible();
  report.checks.push({ name: 'failed_endpoint_clears_key_and_prior_connection', passed: /^No verified endpoint\./.test(inactive) && inactiveSummary === 'Choose your agent' && blocked, status: inactive, inactiveSummary, blocked });
  await page.locator('#connection-mode').selectOption('handoff');
  await page.locator('#connect').click();
  await page.locator('#connection-status').filter({ hasText: 'Handoff ready' }).waitFor();
  await page.locator('#to-repository').click();
  await page.locator('#analyze-local').click();
  await page.locator('#repository-report').waitFor({ state: 'visible', timeout: 60000 });
  if (!fixedFixture) await page.locator('#repo-limit').filter({ hasText: /bundled/i }).waitFor();
  else await page.locator('#repo-limit').filter({ hasText: fixedFixture.identity }).waitFor();
  const provenance = await page.locator('#repo-limit').innerText();
  if (fixedFixture) {
    const fixtureState = await page.evaluate(() => ({ sourceKind: window.CreatorWorkbench.getState().report?.analysis?.source_kind,
      complete: window.CreatorWorkbench.getState().report?.analysis?.complete }));
    report.checks.push({ name: 'creator_fixed_fixture_provenance', passed: provenance.includes(fixedFixture.identity) &&
      /Fixed browser graph fixture/.test(provenance) && fixtureState.sourceKind === 'browser_fixed_fixture' && fixtureState.complete === false,
      provenance, fixtureState, identity: fixedFixture.identity });
  } else {
    report.checks.push({ name: 'creator_bundled_repository_provenance', passed: /bundled Play-Anything repository was scanned/i.test(provenance) && /no user repository was provided/i.test(provenance) && !/synthetic demo/i.test(provenance), provenance });
  }
  await page.locator('[name="dependencies"][value="imports"]').check();
  await page.locator('[name="rights"][value="review"]').check();
  await page.locator('#complete-tutorial').click();
  await page.locator('[data-panel="2"]').waitFor({ state: 'visible' });
  const composeProgress = await page.evaluate(() => ({
    sidebar: [...document.querySelectorAll('#side-steps [aria-current="step"]')].map(element => element.dataset.step),
    stepper: [...document.querySelectorAll('.stepper [aria-current="step"]')].map(element => element.dataset.step),
    activePanel: document.activeElement?.closest('[data-panel]')?.dataset.panel || null,
  }));
  report.checks.push({ name: 'creator_progress_tracks_tutorial_completion', passed:
    JSON.stringify(composeProgress.sidebar) === '["2"]' && JSON.stringify(composeProgress.stepper) === '["2"]' &&
    composeProgress.activePanel === '2', progress: composeProgress });
  await page.locator('[data-preset="tool"]').click();
  await page.locator('#module-grid [data-module="agent"]').check();
  report.checks.push({ name: 'creator_module_selection', passed: await page.locator('#module-grid [data-module="agent"]').isChecked() });
  await page.locator('#to-business').click();
  await page.locator('[data-panel="3"]').waitFor({ state: 'visible' });
  const business = { stats: await page.locator('#business-stats .stat').count(), costs: await page.locator('#cost-breakdown').innerText() };
  report.checks.push({ name: 'creator_business_preview', passed: business.stats > 0 && business.costs.trim().length > 0, business });
  await page.screenshot({ path: path.join(output, 'creator-business.png'), fullPage: true });
  await page.goto(new URL('/graph.html', base).href, { waitUntil: 'domcontentloaded' });
  const firstNode = page.locator('svg g[tabindex="0"]').first();
  await firstNode.waitFor({ state: 'visible' });
  const selectedId = await firstNode.getAttribute('data-node');
  await firstNode.focus();
  await page.keyboard.press('Enter');
  const selection = await page.evaluate(() => ({ id: document.activeElement?.getAttribute('data-node'), pressed: document.activeElement?.getAttribute('aria-pressed') }));
  report.checks.push({ name: 'graph_keyboard_selection_retains_focus', passed: selection.id === selectedId && selection.pressed === 'true', selection });
  const search = page.getByPlaceholder('Path, function, or module…');
  await search.fill('verification-no-match-8c1f440d');
  await page.waitForFunction(() => document.querySelectorAll('svg g[tabindex="0"]').length === 0);
  report.checks.push({ name: 'graph_search_filters_nodes', passed: true });
  await search.fill('');
  await page.locator('select').first().selectOption('file');
  await page.locator('svg g[aria-label^="Inspect file"]').first().waitFor({ state: 'visible' });
  report.checks.push({ name: 'graph_detail_filter_selects_files', passed: true });
  if (fixedFixture) {
    // Search focus is exercised above; clear its transient outline before saving
    // a comparison image so focus-ring rasterization is outside this screenshot.
    await page.evaluate(() => document.activeElement?.blur());
    await settleFixturePaint(page);
    report.graph_capture_diagnostics = await page.evaluate(() => {
      const viewer=document.querySelector('repo-graph'), inspector=viewer?.querySelector('.graph-inspector');
      const badge=inspector?.querySelector('.badge'), button=inspector?.querySelector('.graph-focus');
      const rect=element=>{const r=element?.getBoundingClientRect();return r?{x:r.x,y:r.y,width:r.width,height:r.height,top:r.top,right:r.right,bottom:r.bottom,left:r.left}:null;};
      const style=element=>{if(!element)return null;const s=getComputedStyle(element);return {backgroundColor:s.backgroundColor,color:s.color,borderColor:s.borderColor,borderWidth:s.borderWidth,borderRadius:s.borderRadius,outlineColor:s.outlineColor,outlineWidth:s.outlineWidth,opacity:s.opacity,transform:s.transform};};
      const active=document.activeElement;
      return {devicePixelRatio,viewport:{width:innerWidth,height:innerHeight},
        activeElement:active?{tag:active.tagName,className:typeof active.className==='string'?active.className:'',label:active.getAttribute('aria-label')}:null,
        selection:{selected:viewer?.selected||null,focused:viewer?.focused||false,detail:viewer?.querySelector('.graph-level')?.value||null,search:viewer?.querySelector('.graph-search')?.value||null},
        inspector:{rect:rect(inspector),clientHeight:inspector?.clientHeight,scrollHeight:inspector?.scrollHeight,scrollTop:inspector?.scrollTop},
        badge:{rect:rect(badge),style:style(badge),hovered:badge?.matches(':hover')||false},
        focusButton:{rect:rect(button),style:style(button),focused:button===active,focusVisible:button?.matches(':focus-visible')||false,hovered:button?.matches(':hover')||false},
        activeAnimations:document.getAnimations({subtree:true}).filter(animation=>animation.playState==='running').length,
        fontsStatus:document.fonts?.status||'unavailable'};
    });
  }
  await page.screenshot({ path: path.join(output, 'repository-graph.png'), fullPage: true });
  for (const route of routes) {
    // Force a document load: changing only the hash returns no HTTP response.
    await page.goto('about:blank', { waitUntil: 'commit' });
    const response = await page.goto(new URL(`/dashboard.html#${route}`, base).href, { waitUntil: 'domcontentloaded' });
    if (!response?.ok()) throw new Error(`Dashboard HTTP page failed for ${route}.`);
    await page.locator(`#view-${route}`).waitFor({ state: 'visible', timeout: 15000 });
    const visibleViews = await page.locator('[id^="view-"]').evaluateAll(elements => elements
      .filter(element => getComputedStyle(element).display !== 'none').map(element => element.id));
    const current = await page.locator(`#tab-btn-${route}`).getAttribute('aria-current');
    report.checks.push({ name: `direct_hash_route:${route}`, route, passed: visibleViews.length === 1 && visibleViews[0] === `view-${route}` && current === 'page', visibleViews, current });
    if (route === 'graph') {
      const embedded = page.frameLocator('#view-graph iframe');
      await embedded.getByRole('button', { name: 'Analyze this project', exact: true }).click();
      await embedded.locator('svg g[data-node]').first().waitFor({ state: 'visible', timeout: 60000 });
      const nodeCount = await embedded.locator('svg g[data-node]').count();
      const source = await embedded.locator('.graph-analysis').innerText();
      const sourceMatches = fixedFixture
        ? source.includes(fixedFixture.identity) && source.includes('Fixed browser graph fixture')
        : source.includes('bundled') && source.includes('no user repository');
      report.checks.push({ name: fixedFixture ? 'embedded_fixed_fixture_graph_loaded' : 'embedded_graph_loaded',
        passed: nodeCount > 0 && sourceMatches, nodeCount, source, fixture_identity: fixedFixture?.identity || null });
    }
    if (route === 'quickstart') {
      const embedded = page.frameLocator('#view-quickstart iframe');
      await embedded.locator('#service-status').filter({ hasText: 'Local service ready' }).waitFor({ timeout: 15000 });
      const visiblePanels = await embedded.locator('[data-panel]').evaluateAll(elements => elements
        .filter(element => element.getBoundingClientRect().width > 0 && element.getBoundingClientRect().height > 0)
        .map(element => element.dataset.panel));
      const ready = await embedded.locator('h1').isVisible() && visiblePanels.length === 1;
      report.checks.push({ name: 'embedded_creator_loaded', passed: ready, visiblePanels });
    }
    if (route === 'map') {
      await page.waitForFunction(`(${canvasEvidence.toString()})().drawn`);
      const evidence = await page.evaluate(canvasEvidence);
      report.checks.push({ name: 'map_renders_with_reduced_motion', passed: evidence.drawn && evidence.bounded && evidence.prefersReducedMotion, evidence });
    }
    if (fixedFixture) await settleFixturePaint(page);
    await page.screenshot({ path: path.join(output, `dashboard-${route}.png`), fullPage: true });
  }
  for (const width of [320, 768, 1024, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.locator('#tab-btn-map').click();
    await page.locator('#view-map').waitFor({ state: 'visible' });
    if (width <= 720) {
      const layout = await page.evaluate(() => {
        const frame = document.querySelector('#biome-canvas-frame').getBoundingClientRect();
        const overlays = ['.map-overlay-legend', '.map-overlay-hint', '.map-overlay-controls']
          .map(selector => ({ selector, top: document.querySelector(selector).getBoundingClientRect().top }));
        return { frameBottom: frame.bottom, frameHeight: frame.height, overlays };
      });
      report.checks.push({ name: `mobile_map_overlays_leave_canvas_clear:${width}`, width,
        passed: Math.abs(layout.frameHeight - 360) < 1 && layout.overlays.every(item => item.top >= layout.frameBottom - 1), layout });
    }
    await page.locator('#view-map canvas').scrollIntoViewIfNeeded();
    await page.waitForFunction(`(${canvasEvidence.toString()})().drawn`);
    const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
    report.checks.push({ name: `map_document_fits_viewport:${width}`, width, passed: dimensions.document <= dimensions.viewport, dimensions });
    const evidence = await page.evaluate(canvasEvidence);
    report.checks.push({ name: `map_renders_after_resize:${width}`, width, passed: evidence.drawn && evidence.bounded, evidence });
    if (width === 320) {
      if (fixedFixture) await settleFixturePaint(page);
      const stability = await canvasPixelStabilityEvidence(page);
      report.checks.push({ name: 'map_canvas_pixel_stability_under_reduced_motion:320', width,
        passed: stability.dimensionsStable && stability.prefersReducedMotion && stability.fontsStatus === 'loaded' && stability.changedPixels === 0,
        evidence: stability });
    }
    if (fixedFixture) await settleFixturePaint(page);
    await page.screenshot({ path: path.join(output, `dashboard-map-${width}.png`), fullPage: true });
  }
  await page.locator('#tab-btn-map').click();
  const mapCanvas = page.locator('#biome-canvas');
  await mapCanvas.focus();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowRight');
  const revealed = await page.evaluate(() => ({
    selected: document.querySelector('#biome-canvas')?.dataset.selectedIsland,
    focused: document.activeElement === document.querySelector('#biome-canvas'),
    role: document.querySelector('#biome-canvas')?.getAttribute('role'),
    tabIndex: document.querySelector('#biome-canvas')?.tabIndex,
    accessibleName: document.querySelector('#biome-canvas')?.getAttribute('aria-label'),
    focusOutline: getComputedStyle(document.querySelector('#biome-canvas')).outlineStyle,
    announcement: document.querySelector('#map-selection-announcement')?.textContent || '',
    name: document.querySelector('#chamber-name')?.textContent || '',
    description: document.querySelector('#chamber-desc')?.textContent || '',
  }));
  await page.keyboard.press('Enter');
  const activated = await page.evaluate(() => ({
    focused: document.activeElement === document.querySelector('#biome-canvas'),
    announcement: document.querySelector('#map-selection-announcement')?.textContent || '',
  }));
  report.checks.push({ name: 'map_keyboard_selection_reveals_fog_and_updates_inspector',
    passed: revealed.selected === 'room_03' && revealed.focused && revealed.role === 'group' && revealed.tabIndex === 0 &&
      revealed.accessibleName?.includes('arrow keys') && revealed.focusOutline !== 'none' && revealed.announcement.includes('Fog revealed.') &&
      revealed.name === 'The Citadel of Services' && revealed.description.includes('Asynchronous checkout') &&
      activated.focused && activated.announcement.includes('Fog is clear.'), revealed, activated });
  const benchmarkLabels = await page.locator('#view-benchmarks').textContent();
  const telemetryLabels = await page.locator('#view-personalization').textContent();
  report.checks.push({ name: 'illustrative_metrics_are_labeled_as_demo',
    passed: benchmarkLabels.includes('Illustrative reference: 582.7 µs (not a live measurement)') &&
      telemetryLabels.includes('Illustrative Behavioral Telemetry (Demo)') && telemetryLabels.includes('SAMPLE VALUES') &&
      !telemetryLabels.includes('STREAMING 60Hz') && !telemetryLabels.includes('Continuous Biometric'),
    benchmark_label: benchmarkLabels.includes('Illustrative reference: 582.7 µs (not a live measurement)'),
    telemetry_heading: telemetryLabels.includes('Illustrative Behavioral Telemetry (Demo)'),
    telemetry_badge: telemetryLabels.includes('SAMPLE VALUES') });
  for (const width of [320, 768, 1024, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(new URL('/creator.html', base).href, { waitUntil: 'domcontentloaded' });
    await page.locator('#service-status').filter({ hasText: 'Local service ready' }).waitFor();
    await page.locator('#side-steps [data-step="2"]').click();
    await page.locator('[data-panel="2"]').waitFor({ state: 'visible' });
    const compose = await page.evaluate(() => ({
      viewport: innerWidth, document: document.documentElement.scrollWidth,
      workspace: document.querySelector('.workspace').getBoundingClientRect().toJSON(),
      currentStep: document.querySelector('#side-steps [aria-current="step"]')?.dataset.step,
      progressStep: document.querySelector('.stepper [aria-current="step"]')?.dataset.step,
      focusedPanel: document.activeElement?.closest('[data-panel]')?.dataset.panel,
    }));
    if (width === 320) await page.screenshot({ path: path.join(output, 'creator-compose-320.png'), fullPage: true });
    await page.locator('#side-steps [data-step="3"]').click();
    await page.locator('[data-panel="3"]').waitFor({ state: 'visible' });
    const costing = await page.evaluate(() => {
      const table = document.querySelector('.table-scroll');
      return { viewport: innerWidth, document: document.documentElement.scrollWidth,
        workspace: document.querySelector('.workspace').getBoundingClientRect().toJSON(),
        currentStep: document.querySelector('#side-steps [aria-current="step"]')?.dataset.step,
        progressStep: document.querySelector('.stepper [aria-current="step"]')?.dataset.step,
        focusedPanel: document.activeElement?.closest('[data-panel]')?.dataset.panel,
        table: table ? { clientWidth: table.clientWidth, scrollWidth: table.scrollWidth,
          overflowX: getComputedStyle(table).overflowX } : null };
    });
    if (width === 320) await page.screenshot({ path: path.join(output, 'creator-costing-320.png'), fullPage: true });
    const creatorPass = compose.document <= width && compose.workspace.right <= width + 1 &&
      compose.currentStep === '2' && compose.progressStep === '2' && compose.focusedPanel === '2' &&
      costing.document <= width && costing.workspace.right <= width + 1 && costing.currentStep === '3' &&
      costing.progressStep === '3' && costing.focusedPanel === '3' &&
      costing.table?.overflowX === 'auto' && costing.table.clientWidth <= width;
    report.checks.push({ name: `creator_compose_costing_responsive:${width}`, passed: creatorPass, width, compose, costing });

    if (width === 320) {
      const priceInput = page.locator('[data-assumption="price"]');
      await priceInput.fill('1e-320');
      await page.waitForFunction(() => document.querySelector('#cost-error')?.textContent.includes('Cost preview unavailable:'));
      const rejected = await page.evaluate(() => ({
        message: document.querySelector('#cost-error')?.textContent || '',
        errorRole: document.querySelector('#cost-error')?.getAttribute('role'),
        errorVisible: !document.querySelector('#cost-error')?.hidden,
        staleBreakdownCleared: !document.querySelector('#cost-breakdown')?.textContent?.trim(),
        topDisabled: document.querySelector('#export-top')?.disabled,
        planCleared: window.CreatorWorkbench?.getPlan() === null,
      }));
      await priceInput.fill('1e-300');
      await page.waitForFunction(() => {
        const plan = window.CreatorWorkbench?.getPlan();
        const finite = value => typeof value === 'number' ? Number.isFinite(value) : Array.isArray(value) ? value.every(finite) : value && typeof value === 'object' ? Object.values(value).every(finite) : true;
        return plan && finite(plan) && !document.querySelector('#cost-breakdown')?.textContent.includes('Cost preview unavailable:');
      });
      const recovered = await page.evaluate(() => ({
        price: window.CreatorWorkbench?.getPlan()?.assumptions.price,
        margin: window.CreatorWorkbench?.getPlan()?.margin_pct,
        topDisabled: document.querySelector('#export-top')?.disabled,
        errorHidden: document.querySelector('#cost-error')?.hidden,
        containsNonfiniteText: /Infinity|NaN/.test(document.querySelector('#cost-breakdown')?.textContent || ''),
      }));
      await priceInput.fill('0');
      const zeroPrice = await page.evaluate(() => ({
        price: window.CreatorWorkbench?.getPlan()?.assumptions.price,
        margin: window.CreatorWorkbench?.getPlan()?.margin_pct,
        valid: !document.querySelector('#export-top')?.disabled,
      }));
      report.checks.push({ name: 'creator_tiny_price_rejects_and_recovers',
        passed: rejected.message.includes('Contribution margin exceeds the supported numeric range') && !rejected.message.includes('plan.') && rejected.topDisabled && rejected.planCleared &&
          rejected.errorRole === 'alert' && rejected.errorVisible && rejected.staleBreakdownCleared &&
          recovered.price === 1e-300 && Number.isFinite(recovered.margin) && !recovered.topDisabled && recovered.errorHidden && !recovered.containsNonfiniteText &&
          zeroPrice.price === 0 && zeroPrice.margin === null && zeroPrice.valid,
        rejected, recovered, zero_price: zeroPrice });
    }

    await page.goto(new URL('/graph.html', base).href, { waitUntil: 'domcontentloaded' });
    const node = page.locator('svg g[data-node]').first();
    await node.waitFor({ state: 'visible', timeout: 60000 });
    const graphLayout = await page.evaluate(() => {
      const bounds = selector => document.querySelector(selector)?.getBoundingClientRect().toJSON() || null;
      return { viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth,
        main: bounds('main'), shell: bounds('.graph-shell'), canvas: bounds('.graph-canvas'), inspector: bounds('.graph-inspector') };
    });
    const graphLabel = await node.getAttribute('aria-label');
    const graphTitle = await node.locator('title').textContent();
    await node.focus();
    await page.keyboard.press('Enter');
    const graphSelection = await page.evaluate(() => ({
      activeLabel: document.activeElement?.getAttribute('aria-label'),
      pressed: document.activeElement?.getAttribute('aria-pressed'),
      inspectorName: document.querySelector('.graph-inspector h4')?.textContent?.trim(),
      focusStroke: getComputedStyle(document.activeElement?.querySelector('rect')).strokeWidth,
      document: document.documentElement.scrollWidth, viewport: innerWidth,
    }));
    if (width === 320) await page.screenshot({ path: path.join(output, 'graph-responsive-320.png'), fullPage: true });
    const graphPass = graphLayout.document <= width && graphLayout.body <= width && graphLayout.main.right <= width + 1 &&
      graphLayout.shell.right <= width + 1 && graphLayout.canvas.right <= width + 1 &&
      graphLayout.inspector.left >= -1 && graphLayout.inspector.right <= width + 1 &&
      Boolean(graphTitle?.trim()) && graphLabel === graphSelection.activeLabel && graphSelection.pressed === 'true' &&
      graphSelection.inspectorName && graphLabel.includes(graphSelection.inspectorName) && graphSelection.focusStroke !== '0px' &&
      graphSelection.document <= width && graphSelection.viewport === width;
    report.checks.push({ name: `graph_detail_responsive:${width}`, passed: graphPass, width, layout: graphLayout,
      tooltip: graphTitle, accessible_label: graphLabel, selection: graphSelection });
  }
  await page.goto(new URL('/dashboard.html#map', base).href, { waitUntil: 'domcontentloaded' });
  await page.locator('#tab-btn-skills').waitFor({ state: 'visible' });
  await page.locator('#tab-btn-skills').focus();
  await page.keyboard.press('Enter');
  report.checks.push({ name: 'keyboard_view_selection', passed: await page.locator('#view-skills').isVisible() && await page.locator('#tab-btn-skills').getAttribute('aria-current') === 'page' });
} catch (error) {
  report.errors.push(error.message);
  if (page) {
    report.failure_state = await page.evaluate(() => ({ url: location.href, notice: document.querySelector('#notice')?.textContent || '' })).catch(() => null);
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  }
} finally {
  await browser.close();
}
report.check_ledger = evaluateCheckLedger(report.checks, expectedDashboardChecks(Boolean(fixedFixture)));
if (!report.check_ledger.ledger_pass) report.errors.push('Check ledger mismatch: expected check names were missing, duplicated, invalid, or unexpected.');
report.passed = report.errors.length === 0 && report.check_ledger.ledger_pass && report.check_ledger.failed_count === 0;
await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
if (!report.passed) process.exitCode = 1;

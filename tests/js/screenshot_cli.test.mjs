import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';

const require = createRequire(import.meta.url);
let sharp;
try { sharp = require(process.env.SHARP_MODULE_PATH || 'sharp'); } catch { /* Optional dev tool. */ }
const command = fileURLToPath(new URL('../../scripts/compare_dashboard_screenshots.mjs', import.meta.url));

async function fixture(callback) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'play-anything-pixels-'));
  const baseline = path.join(root, 'baseline');
  const current = path.join(root, 'current');
  const output = path.join(root, 'output');
  await fs.mkdir(baseline); await fs.mkdir(current);
  try { await callback({ baseline, current, output }); }
  finally { await fs.rm(root, { recursive: true, force: true }); }
}
async function writeImage(filename, color = 'white', width = 4) {
  await sharp({ create: { width, height: 4, channels: 4, background: color } }).png().toFile(filename);
}
function run(paths) {
  return spawnSync(process.execPath, [command, paths.baseline, paths.current, paths.output], { encoding: 'utf8' });
}

test('PNG directory comparison passes identical captures and writes report', { skip: !sharp }, async () => {
  await fixture(async paths => {
    await writeImage(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'));
    assert.equal(run(paths).status, 0);
    const report = JSON.parse(await fs.readFile(path.join(paths.output, 'comparison.json'), 'utf8'));
    assert.equal(report.passed, true); assert.equal(report.checks[0].changedPixels, 0);
  });
});
test('real PNG pixel regression fails and creates a diff', { skip: !sharp }, async () => {
  await fixture(async paths => {
    await writeImage(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'), 'black');
    assert.equal(run(paths).status, 1);
    assert.equal((await fs.stat(path.join(paths.output, 'map.diff.png'))).isFile(), true);
  });
});
test('missing/extra capture names and dimensions cannot pass', { skip: !sharp }, async () => {
  await fixture(async paths => {
    await writeImage(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'), 'white', 5);
    await writeImage(path.join(paths.current, 'unexpected.png'));
    assert.equal(run(paths).status, 1);
    const report = JSON.parse(await fs.readFile(path.join(paths.output, 'comparison.json'), 'utf8'));
    assert.deepEqual(report.checks.map(item => item.reason), ['dimensions_changed', 'unexpected_capture']);
  });
});
test('failed browser capture and empty baseline are rejected', { skip: !sharp }, async () => {
  await fixture(async paths => {
    assert.notEqual(run(paths).status, 0);
    await writeImage(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'));
    await fs.writeFile(path.join(paths.current, 'report.json'), JSON.stringify({ passed: false }));
    const result = run(paths);
    assert.notEqual(result.status, 0); assert.match(result.stderr, /failed\/incomplete/);
  });
});
test('grayscale PNGs normalize to RGBA before comparing', { skip: !sharp }, async () => {
  await fixture(async paths => {
    await sharp({ create: { width: 4, height: 4, channels: 3, background: 'white' } }).greyscale().png().toFile(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'));
    const result = run(paths); assert.equal(result.status, 0, result.stderr);
  });
});
test('self comparison, symlink aliases and nested output cannot silently pass or mutate captures', { skip: !sharp }, async () => {
  await fixture(async paths => {
    await writeImage(path.join(paths.baseline, 'map.png'));
    await writeImage(path.join(paths.current, 'map.png'));
    const self = run({ ...paths, current: paths.baseline });
    assert.notEqual(self.status, 0); assert.match(self.stderr, /must be distinct/);
    const alias = path.join(path.dirname(paths.output), 'alias');
    await fs.symlink(paths.baseline, alias, 'dir');
    assert.notEqual(run({ ...paths, current: alias }).status, 0);
    const nested = path.join(paths.baseline, 'comparison');
    const result = run({ ...paths, output: nested });
    assert.notEqual(result.status, 0); assert.match(result.stderr, /must not overlap/);
    await assert.rejects(fs.stat(nested), { code: 'ENOENT' });
  });
});

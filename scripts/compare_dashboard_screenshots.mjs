/** Compare reviewed screenshot directories; optional Sharp is development tooling. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { comparePixels } from './visual/pixel_comparison.mjs';

const require = createRequire(import.meta.url);
const arguments_ = process.argv.slice(2);
if (arguments_.length < 3 || arguments_.length > 5) {
  console.error('Usage: node scripts/compare_dashboard_screenshots.mjs BASELINE CURRENT OUTPUT [MAX_CHANGED_RATIO] [CHANNEL_THRESHOLD]');
  process.exit(2);
}
const inputPaths = arguments_.slice(0, 3).map(value => path.resolve(value));
const baseline = await fs.realpath(inputPaths[0]);
const current = await fs.realpath(inputPaths[1]);
async function canonicalOutput(filename) {
  try { return await fs.realpath(filename); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    const parent = path.dirname(filename);
    if (parent === filename) throw error;
    return path.join(await canonicalOutput(parent), path.basename(filename));
  }
}
const output = await canonicalOutput(inputPaths[2]);
function contains(parent, child) {
  const relative = path.relative(parent, child);
  return relative === '' || (!path.isAbsolute(relative) && relative !== '..' && !relative.startsWith(`..${path.sep}`));
}
if (baseline === current) throw new Error('Baseline and current capture directories must be distinct.');
if ([baseline, current].some(input => contains(input, output) || contains(output, input))) {
  throw new Error('Output must not overlap either screenshot directory.');
}
const maxChangedRatio = arguments_[3] === undefined ? 0.005 : Number(arguments_[3]);
const channelThreshold = arguments_[4] === undefined ? 16 : Number(arguments_[4]);
// Validate policy before decoding or creating any output files.
comparePixels({ width: 1, height: 1, data: new Uint8Array(4) },
  { width: 1, height: 1, data: new Uint8Array(4) }, { maxChangedRatio, channelThreshold });
let sharp;
try { sharp = require(process.env.SHARP_MODULE_PATH || 'sharp'); }
catch { throw new Error('Sharp is optional development tooling; install it or set SHARP_MODULE_PATH to an existing module.'); }

async function captureFiles(directory) {
  const reportPath = path.join(directory, 'report.json');
  try {
    const report = JSON.parse(await fs.readFile(reportPath, 'utf8'));
    if (report.passed !== true) throw new Error(`Refusing failed/incomplete browser capture: ${directory}`);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const entries = await fs.readdir(directory, { withFileTypes: true });
  return entries.filter(entry => entry.isFile() && entry.name.endsWith('.png') && !entry.name.endsWith('.diff.png'))
    .map(entry => entry.name).sort();
}
async function decode(filename) {
  const image = sharp(filename, { limitInputPixels: 16000000 });
  const { data, info } = await image.toColourspace('srgb').ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return { data, width: info.width, height: info.height };
}
const expectedNames = await captureFiles(baseline);
const actualNames = await captureFiles(current);
if (!expectedNames.length) throw new Error('Baseline contains no PNG screenshots.');
await fs.mkdir(output, { recursive: true });
const report = { schema_version: 1, evidence_type: 'pixel_comparison', maxChangedRatio, channelThreshold, checks: [] };
const names = [...new Set([...expectedNames, ...actualNames])].sort();
for (const name of names) {
  if (!expectedNames.includes(name) || !actualNames.includes(name)) {
    report.checks.push({ name, passed: false, reason: expectedNames.includes(name) ? 'missing_capture' : 'unexpected_capture' });
    continue;
  }
  const expected = await decode(path.join(baseline, name));
  const actual = await decode(path.join(current, name));
  const result = comparePixels(expected, actual, { channelThreshold, maxChangedRatio });
  const { diff, ...statistics } = result;
  report.checks.push({ name, ...statistics });
  if (!result.passed && diff) {
    await sharp(Buffer.from(diff), { raw: { width: expected.width, height: expected.height, channels: 4 } })
      .png().toFile(path.join(output, `${name.slice(0, -4)}.diff.png`));
  }
}
report.passed = report.checks.every(check => check.passed);
await fs.writeFile(path.join(output, 'comparison.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: report.passed, checks: report.checks.length,
  failures: report.checks.filter(check => !check.passed), report: path.join(output, 'comparison.json') }, null, 2));
if (!report.passed) process.exitCode = 1;

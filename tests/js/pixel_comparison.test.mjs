import assert from 'node:assert/strict';
import test from 'node:test';
import { comparePixels } from '../../scripts/visual/pixel_comparison.mjs';

const bitmap = (values, width = 2, height = 1) => ({ data: new Uint8Array(values), width, height });
const original = bitmap([10, 20, 30, 255, 40, 50, 60, 255]);

test('identical pixels pass with no tolerance', () => {
  const result = comparePixels(original, original, { channelThreshold: 0, maxChangedRatio: 0 });
  assert.equal(result.passed, true);
  assert.equal(result.changedPixels, 0);
});
test('a real one-pixel regression fails and marks its location', () => {
  const changed = bitmap([200, 20, 30, 255, 40, 50, 60, 255]);
  const result = comparePixels(original, changed);
  assert.equal(result.passed, false);
  assert.equal(result.changedPixels, 1);
  assert.equal(result.changedRatio, 0.5);
  assert.deepEqual([...result.diff.slice(0, 4)], [225, 25, 125, 255]);
});
test('channel noise threshold is inclusive and ratio threshold is inclusive', () => {
  const changed = bitmap([26, 20, 30, 255, 57, 50, 60, 255]);
  const result = comparePixels(original, changed, { channelThreshold: 16, maxChangedRatio: 0.5 });
  assert.equal(result.changedPixels, 1);
  assert.equal(result.passed, true);
});
test('dimension changes never pass a permissive pixel tolerance', () => {
  assert.equal(comparePixels(original, bitmap([...original.data], 1, 2), { maxChangedRatio: 1 }).reason, 'dimensions_changed');
});
test('alpha changes count and input buffers are not mutated', () => {
  const before = [...original.data];
  const changed = bitmap([10, 20, 30, 0, 40, 50, 60, 255]);
  assert.equal(comparePixels(original, changed).changedPixels, 1);
  assert.deepEqual([...original.data], before);
});
test('invalid dimensions, byte counts and tolerances are rejected', () => {
  for (const candidate of [bitmap([1]), bitmap([], 0, 1), { width: 2, height: 1, data: [1] }]) {
    assert.throws(() => comparePixels(original, candidate), TypeError);
  }
  for (const channelThreshold of [-1, 256, 0.5, NaN]) {
    assert.throws(() => comparePixels(original, original, { channelThreshold }), RangeError);
  }
  for (const maxChangedRatio of [-1, 2, NaN, Infinity]) {
    assert.throws(() => comparePixels(original, original, { maxChangedRatio }), RangeError);
  }
});

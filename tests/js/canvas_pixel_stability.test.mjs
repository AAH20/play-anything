import test from 'node:test';
import assert from 'node:assert/strict';
import { compareCanvasPixelBuffers } from '../../scripts/visual/canvas_pixel_stability.mjs';

test('identical complete RGBA frames have exact zero change', () => {
  const frame = Uint8Array.from([1, 2, 3, 255, 4, 5, 6, 255]);
  assert.deepEqual(compareCanvasPixelBuffers(frame, frame.slice(), 2, 1), {
    changedPixels: 0, changedChannels: 0, maxChannelDelta: 0, bounds: null,
  });
});

test('frame comparison counts changed pixels, channels, magnitude, and bounds exactly', () => {
  const before = Uint8Array.from([10, 20, 30, 255, 40, 50, 60, 255, 70, 80, 90, 255, 100, 110, 120, 255]);
  const after = before.slice();
  after[1] += 1;
  after[14] -= 9;
  assert.deepEqual(compareCanvasPixelBuffers(before, after, 2, 2), {
    changedPixels: 2, changedChannels: 2, maxChannelDelta: 9, bounds: [0, 0, 1, 1],
  });
  assert.equal(before[1], 20, 'comparison must not mutate the original frame');
});

test('alpha changes count as pixel changes', () => {
  assert.equal(compareCanvasPixelBuffers(Uint8Array.from([0, 0, 0, 255]), Uint8Array.from([0, 0, 0, 0]), 1, 1).changedPixels, 1);
});

test('invalid dimensions and incomplete/non-byte frames fail closed', () => {
  const frame = new Uint8Array(4);
  assert.throws(() => compareCanvasPixelBuffers(frame, frame, 0, 1), RangeError);
  assert.throws(() => compareCanvasPixelBuffers(frame, frame, 1.5, 1), RangeError);
  assert.throws(() => compareCanvasPixelBuffers(frame, new Uint8Array(3), 1, 1), RangeError);
  assert.throws(() => compareCanvasPixelBuffers({ byteLength: 4 }, frame, 1, 1), RangeError);
});

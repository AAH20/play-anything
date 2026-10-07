/** Pure pixel comparison helpers, independent of the optional PNG decoder. */
export function comparePixels(expected, actual, {
  channelThreshold = 16, maxChangedRatio = 0.005,
} = {}) {
  if (!Number.isInteger(channelThreshold) || channelThreshold < 0 || channelThreshold > 255) {
    throw new RangeError('channelThreshold must be an integer in [0, 255].');
  }
  if (!Number.isFinite(maxChangedRatio) || maxChangedRatio < 0 || maxChangedRatio > 1) {
    throw new RangeError('maxChangedRatio must be a finite number in [0, 1].');
  }
  for (const bitmap of [expected, actual]) {
    if (!Number.isInteger(bitmap.width) || !Number.isInteger(bitmap.height)
      || bitmap.width <= 0 || bitmap.height <= 0
      || !(bitmap.data instanceof Uint8Array)
      || bitmap.data.length !== bitmap.width * bitmap.height * 4) {
      throw new TypeError('Each bitmap needs positive dimensions and exact RGBA bytes.');
    }
  }
  if (expected.width !== actual.width || expected.height !== actual.height) {
    return { passed: false, reason: 'dimensions_changed', expected: [expected.width, expected.height], actual: [actual.width, actual.height] };
  }
  const pixels = expected.width * expected.height;
  let changedPixels = 0;
  const diff = new Uint8Array(pixels * 4);
  for (let index = 0; index < expected.data.length; index += 4) {
    let changed = false;
    for (let channel = 0; channel < 4; channel++) {
      if (Math.abs(expected.data[index + channel] - actual.data[index + channel]) > channelThreshold) changed = true;
    }
    if (changed) changedPixels++;
    diff[index] = changed ? 225 : expected.data[index];
    diff[index + 1] = changed ? 25 : expected.data[index + 1];
    diff[index + 2] = changed ? 125 : expected.data[index + 2];
    diff[index + 3] = 255;
  }
  const changedRatio = changedPixels / pixels;
  return { passed: changedRatio <= maxChangedRatio, reason: 'pixels_compared',
    changedPixels, pixels, changedRatio, channelThreshold, maxChangedRatio, diff };
}

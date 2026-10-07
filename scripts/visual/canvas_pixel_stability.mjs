/** Exact comparison for browser canvas stability probes (RGBA, no tolerance). */
export function compareCanvasPixelBuffers(before, after, width, height) {
  if (!Number.isSafeInteger(width) || width < 1 || !Number.isSafeInteger(height) || height < 1) {
    throw new RangeError('Canvas dimensions must be positive safe integers.');
  }
  const expectedLength = width * height * 4;
  const isByteView = value => ArrayBuffer.isView(value) && !(value instanceof DataView) && value.BYTES_PER_ELEMENT === 1;
  if (!Number.isSafeInteger(expectedLength) || !isByteView(before) || !isByteView(after) ||
      before.byteLength !== expectedLength || after.byteLength !== expectedLength) {
    throw new RangeError('Canvas pixel buffers must match the declared RGBA dimensions.');
  }

  let changedPixels = 0;
  let changedChannels = 0;
  let maxChannelDelta = 0;
  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;
  for (let pixel = 0; pixel < width * height; pixel += 1) {
    const offset = pixel * 4;
    let pixelChanged = false;
    for (let channel = 0; channel < 4; channel += 1) {
      const delta = after[offset + channel] - before[offset + channel];
      if (delta !== 0) {
        pixelChanged = true;
        changedChannels += 1;
        maxChannelDelta = Math.max(maxChannelDelta, Math.abs(delta));
      }
    }
    if (pixelChanged) {
      changedPixels += 1;
      const x = pixel % width;
      const y = Math.floor(pixel / width);
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  return {
    changedPixels,
    changedChannels,
    maxChannelDelta,
    bounds: changedPixels ? [minX, minY, maxX, maxY] : null,
  };
}

import test from 'node:test';
import assert from 'node:assert/strict';
import {bindRendererContextEvents} from '../lib/renderer-lifecycle';

test('StrictMode teardown cannot mark the replacement renderer as unavailable', () => {
  const oldCanvas = new EventTarget(), currentCanvas = new EventTarget();
  let unavailable = false, retries = 0;
  const lost = (event: Event) => {event.preventDefault(); unavailable = true;};
  const restored = () => {retries++;};
  const disposeOld = bindRendererContextEvents([oldCanvas], lost, restored);
  disposeOld(); // React cleanup must run before Sigma deliberately loses contexts.
  const disposeCurrent = bindRendererContextEvents([currentCanvas], lost, restored);
  oldCanvas.dispatchEvent(new Event('webglcontextlost', {cancelable:true}));
  oldCanvas.dispatchEvent(new Event('webglcontextrestored'));
  assert.equal(unavailable, false);
  assert.equal(retries, 0);
  const realLoss = new Event('webglcontextlost', {cancelable:true});
  currentCanvas.dispatchEvent(realLoss);
  assert.equal(unavailable, true);
  assert.equal(realLoss.defaultPrevented, true);
  currentCanvas.dispatchEvent(new Event('webglcontextrestored'));
  assert.equal(retries, 1);
  disposeCurrent();
  disposeCurrent();
});

test('cleanup detaches context handlers from every renderer layer', () => {
  const canvases = Array.from({length:7}, () => new EventTarget());
  let notifications = 0;
  const dispose = bindRendererContextEvents(canvases, () => notifications++, () => notifications++);
  dispose();
  for (const canvas of canvases) {
    canvas.dispatchEvent(new Event('webglcontextlost'));
    canvas.dispatchEvent(new Event('webglcontextrestored'));
  }
  assert.equal(notifications, 0);
});

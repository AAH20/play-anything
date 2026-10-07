import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const HostingModel = require('../../play_anything/hosting-model.js');

test('hosting estimate rejects null, array, and inherited-key settings', () => {
  for (const settings of [null, [], new Date()]) {
    assert.throws(() => HostingModel.estimate(settings), /Hosting settings must be an object/);
  }
  assert.throws(() => HostingModel.estimate({ constructor: 1 }), /Unknown hosting setting/);
});

test('hosting numeric settings reject coercible non-number scalar types', () => {
  for (const extra of [null, true, [], {}]) {
    assert.throws(() => HostingModel.estimate({ extra }), /Invalid hosting input: extra/);
  }
  assert.throws(() => HostingModel.estimate({ extra: '1e-99999999' }), /Invalid hosting input: extra/);
  assert.equal(HostingModel.estimate({ extra: '2.5' }).settings.extra, 2.5);
  assert.equal(HostingModel.estimate({ extra: 0 }).settings.extra, 0);
});

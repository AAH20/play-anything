import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const CreatorModel = require('../../play_anything/creator-model.js');
const selected = ['repository', 'studio', 'personalization', 'pitch'];
const finiteNumbers = value => {
  if (typeof value === 'number') return Number.isFinite(value);
  if (Array.isArray(value)) return value.every(finiteNumbers);
  if (value && typeof value === 'object') return Object.values(value).every(finiteNumbers);
  return true;
};

test('zero price remains valid and reports unavailable margin', () => {
  const plan = CreatorModel.calculate(selected, { price: 0 });
  assert.equal(plan.assumptions.price, 0);
  assert.equal(plan.gross, 0);
  assert.equal(plan.margin_pct, null);
  assert.equal(finiteNumbers(plan), true);
});

test('tiny representable positive price is accepted when every result stays finite', () => {
  const plan = CreatorModel.calculate(selected, { price: 1e-300 });
  assert.equal(plan.assumptions.price, 1e-300);
  assert.equal(finiteNumbers(plan), true);
});

test('non-finite derived ratios fail with a field-specific calculation error', () => {
  assert.throws(() => CreatorModel.calculate(selected, { price: 1e-320 }), /plan\.margin_pct must be finite/);
});

test('positive decimal input that underflows to zero is rejected while literal zero is allowed', () => {
  assert.throws(() => CreatorModel.calculate(selected, { price: '1e-99999999' }), /price must be between/);
  const zero = CreatorModel.calculate(selected, { price: '0e-99999999' });
  assert.equal(zero.assumptions.price, 0);
  assert.equal(zero.margin_pct, null);
});

test('assumptions accept only numeric scalars and record containers', () => {
  for (const price of [null, true, [], {}]) {
    assert.throws(() => CreatorModel.calculate([], { price }), /price must be between/);
  }
  for (const assumptions of [null, [], true]) {
    assert.throws(() => CreatorModel.calculate([], assumptions), /Accounting assumptions must be an object/);
  }
  assert.throws(() => CreatorModel.calculate([], { constructor: 1 }), /Unknown accounting assumption/);
});

test('module cost overrides reject non-record containers and nonscalar costs', () => {
  for (const overrides of [null, []]) {
    assert.throws(() => CreatorModel.calculate([], {}, overrides), /Module cost overrides must be an object/);
  }
  for (const hours of [true, null, [], {}]) {
    assert.throws(() => CreatorModel.calculate([], {}, { world: { hours } }), /World runtime: enter a nonnegative, finite cost/);
  }
  assert.throws(() => CreatorModel.calculate([], {}, { world: [] }), /World runtime: cost overrides must be an object/);
  assert.equal(CreatorModel.calculate([], {}, { world: { hours: '1.5' } }).rows.find(row => row.id === 'world').hours, 1.5);
});

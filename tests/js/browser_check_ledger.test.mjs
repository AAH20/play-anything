import assert from 'node:assert/strict';
import test from 'node:test';
import { evaluateCheckLedger } from '../../scripts/lib/browser_check_ledger.mjs';

test('the ledger passes only when every independently expected check appears once', () => {
  const result = evaluateCheckLedger([
    { name: 'loads', passed: true }, { name: 'searches', passed: true },
  ], ['loads', 'searches']);
  assert.equal(result.ledger_pass, true);
  assert.equal(result.expected_count, 2);
  assert.equal(result.recorded_count, 2);
  assert.equal(result.passed_count, 2);
});

test('the ledger rejects omitted, duplicated, unexpected, and malformed check records', () => {
  const result = evaluateCheckLedger([
    { name: 'loads', passed: true }, { name: 'loads', passed: true },
    { name: 'extra', passed: true }, { name: 'malformed' },
  ], ['loads', 'searches']);
  assert.equal(result.ledger_pass, false);
  assert.deepEqual(result.missing, ['searches']);
  assert.deepEqual(result.duplicate_recorded, ['loads']);
  assert.deepEqual(result.unexpected, ['extra']);
  assert.deepEqual(result.invalid_record_indexes, [3]);
});

test('ledger integrity is distinct from a check failure and reports outcome counts', () => {
  const result = evaluateCheckLedger([
    { name: 'loads', passed: true }, { name: 'searches', passed: false },
  ], ['loads', 'searches']);
  assert.equal(result.ledger_pass, true);
  assert.equal(result.passed_count, 1);
  assert.equal(result.failed_count, 1);
});

test('duplicate expected names and invalid input fail closed', () => {
  assert.equal(evaluateCheckLedger([{ name: 'loads', passed: true }], ['loads', 'loads']).ledger_pass, false);
  assert.throws(() => evaluateCheckLedger({}, []), TypeError);
  assert.throws(() => evaluateCheckLedger([], ['']), TypeError);
});

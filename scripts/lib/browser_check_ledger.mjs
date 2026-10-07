export function evaluateCheckLedger(checks, expectedNames) {
  if (!Array.isArray(checks) || !Array.isArray(expectedNames) || expectedNames.some(name => typeof name !== 'string' || !name)) {
    throw new TypeError('Browser check ledger requires arrays of named checks.');
  }
  const expectedCounts = new Map(), actualCounts = new Map(), invalidRecords = [];
  for (const name of expectedNames) expectedCounts.set(name, (expectedCounts.get(name) || 0) + 1);
  for (const [index, check] of checks.entries()) {
    if (!check || typeof check !== 'object' || typeof check.name !== 'string' || !check.name || typeof check.passed !== 'boolean') {
      invalidRecords.push(index);
      continue;
    }
    actualCounts.set(check.name, (actualCounts.get(check.name) || 0) + 1);
  }
  const duplicateExpected = [...expectedCounts].filter(([, count]) => count > 1).map(([name]) => name);
  const duplicateRecorded = [...actualCounts].filter(([, count]) => count > 1).map(([name]) => name);
  const missing = [...expectedCounts.keys()].filter(name => !actualCounts.has(name));
  const unexpected = [...actualCounts.keys()].filter(name => !expectedCounts.has(name));
  const valid = checks.filter(check => check && typeof check === 'object' &&
    typeof check.name === 'string' && check.name && typeof check.passed === 'boolean');
  const passed = valid.filter(check => check.passed).length;
  const failed = valid.length - passed;
  const ledgerPass = checks.length === expectedNames.length && !duplicateExpected.length &&
    !duplicateRecorded.length && !missing.length && !unexpected.length && !invalidRecords.length;
  return {
    ledger_pass: ledgerPass,
    expected_count: expectedNames.length,
    recorded_count: checks.length,
    passed_count: passed,
    failed_count: failed,
    invalid_record_count: invalidRecords.length,
    missing, duplicate_recorded: duplicateRecorded, duplicate_expected: duplicateExpected,
    unexpected, invalid_record_indexes: invalidRecords,
  };
}

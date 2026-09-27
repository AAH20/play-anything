import assert from 'node:assert/strict';
import test from 'node:test';
import { getIntegration, integrationCatalog } from '../lib/integration-catalog';

const expectedIds = [
  'cognee',
  'mirofish',
  'langgraph',
  'crewai',
  'hermes',
  'openmanus',
  'understand-anything',
  'graph-rag-kernel',
  'agentic-kernel',
  'mirofish-optimizer',
  'graph-swarm-kernel',
];

test('integration catalog has every stable id once and supports lookup', () => {
  assert.deepEqual(integrationCatalog.map(({ id }) => id), expectedIds);
  for (const integration of integrationCatalog) {
    assert.equal(getIntegration(integration.id), integration);
  }
  assert.equal(getIntegration('unknown'), undefined);
});

test('catalog records are JSON-serializable and source-backed', () => {
  const roundTrip = JSON.parse(JSON.stringify(integrationCatalog));
  assert.deepEqual(roundTrip, integrationCatalog);

  for (const integration of integrationCatalog) {
    assert.ok(integration.name.length > 0);
    assert.ok(integration.repository.startsWith('https://github.com/'));
    assert.ok(integration.revision.length > 0);
    assert.ok(integration.license.length > 0);
    assert.ok(['native-api', 'local-command', 'harness-plugin', 'needs-adapter'].includes(integration.surface));
    for (const contract of integration.interfaces) {
      assert.ok(contract.name.length > 0);
      assert.ok(contract.signature.length > 0);
      assert.ok(contract.input.length > 0);
      assert.ok(contract.output.length > 0);
      assert.ok(contract.source.startsWith('https://'));
    }
  }
});

test('local kernel methods are accurately marked as requiring an adapter', () => {
  const kernelIds = expectedIds.slice(7);
  for (const id of kernelIds) {
    const integration = getIntegration(id);
    assert.ok(integration);
    assert.equal(integration.surface, 'needs-adapter');
    assert.deepEqual(integration.dependencies, []);
    assert.ok(integration.interfaces.length >= 2);
    assert.ok(integration.constraints.length > 0);
    assert.ok(integration.interfaces.every((contract) => contract.source.startsWith(integration.repository)));
  }
});

test('remote and harness sources expose their actual operational limits', () => {
  assert.match(getIntegration('mirofish')?.auth ?? '', /No authentication contract/);
  assert.match(getIntegration('cognee')?.auth ?? '', /X-Api-Key/);
  assert.match(getIntegration('hermes')?.auth ?? '', /API_SERVER_KEY/);
  assert.equal(getIntegration('understand-anything')?.surface, 'harness-plugin');
  assert.equal(getIntegration('openmanus')?.surface, 'harness-plugin');
});

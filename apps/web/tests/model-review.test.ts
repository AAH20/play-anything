import assert from 'node:assert/strict';
import test from 'node:test';
import {
  hasSafeOrigin,
  isAuthorized,
  isReviewEnabled,
  parseReviewInput,
  REVIEW_MAX_BYTES,
  REVIEW_MAX_OUTPUT_TOKENS,
  validateCitations,
} from '../lib/model-review';
import { parseSnapshot } from '../lib/graph';

const graph = parseSnapshot({
  version: 1,
  name: 'fixture',
  nodes: [
    { id: 'module:a', name: 'a', kind: 'module', path: 'a.py', summary: 'entry', confidence: 'parsed' },
    { id: 'function:b', name: 'b', kind: 'function', path: 'b.py', summary: 'worker', confidence: 'observed' },
  ],
  edges: [{ source: 'module:a', target: 'function:b', relation: 'imports', confidence: 'parsed' }],
  warnings: [],
  truncated: false,
});

test('review request validates graph, goal, and bounded token cap', () => {
  assert.deepEqual(parseReviewInput({ graph, goal: 'Find central components', maxOutputTokens: 250 }), {
    graph, goal: 'Find central components', maxOutputTokens: 250,
  });
  assert.throws(() => parseReviewInput({ graph, goal: '', maxOutputTokens: 250 }));
  assert.throws(() => parseReviewInput({ graph, goal: 'x', maxOutputTokens: REVIEW_MAX_OUTPUT_TOKENS + 1 }));
  assert.throws(() => parseReviewInput({ graph: { ...graph, nodes: [{ ...graph.nodes[0], id: '' }] }, goal: 'x', maxOutputTokens: 100 }));
});

test('bearer token and same-origin guards reject missing or cross-origin access', () => {
  const request = (authorization?: string, origin = 'https://example.test') => new Request('https://example.test/api/review', {
    headers: { host: 'example.test', ...(authorization ? { authorization } : {}), origin },
  });
  assert.equal(isAuthorized(request('Bearer secret'), 'secret'), true);
  assert.equal(isAuthorized(request('Bearer wrong'), 'secret'), false);
  assert.equal(isAuthorized(request(), 'secret'), false);
  assert.equal(hasSafeOrigin(request('Bearer secret')), true);
  assert.equal(hasSafeOrigin(request('Bearer secret', 'https://attacker.test')), false);
  assert.equal(hasSafeOrigin(request('Bearer secret', 'not a url')), false);
});

test('configuration status requires all secrets without returning them', () => {
  assert.equal(isReviewEnabled({ AI_GATEWAY_API_KEY: 'key', GRAPH_REVIEW_MODEL: 'vendor/model', GRAPH_REVIEW_ACCESS_TOKEN: 'token' }), true);
  assert.equal(isReviewEnabled({ AI_GATEWAY_API_KEY: 'key', GRAPH_REVIEW_MODEL: 'vendor/model' }), false);
  assert.ok(REVIEW_MAX_BYTES <= 2 * 1024 * 1024);
});

test('model findings require citations that exist in the graph', () => {
  const finding = { title: 'Central module', detail: 'This module has a direct import edge.', nodeIds: ['module:a', 'module:a'] };
  assert.deepEqual(validateCitations({ summary: 'A small graph.', findings: [finding] }, graph), [{ ...finding, nodeIds: ['module:a'], confidence: 'model-suggestion' }]);
  assert.throws(() => validateCitations({ summary: 'A small graph.', findings: [{ ...finding, nodeIds: ['invented'] }] }, graph));
});

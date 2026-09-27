import assert from 'node:assert/strict';
import test from 'node:test';
import {
  createNeo4jStore,
  getNeo4jConfig,
  hasGraphStoreSafeOrigin,
  isGraphStoreAuthorized,
  resolveQueryUrl,
  validateGraphForStorage,
  type Neo4jConfig,
} from '../lib/neo4j-store';
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
const config: Neo4jConfig = { uri: 'https://db.example.test', username: 'workspace', password: 'private', namespace: 'trusted-space' };

function queryResponse(fields: string[], row: unknown[]) {
  return new Response(JSON.stringify({ data: { fields, values: [row] } }), { status: 202, headers: { 'content-type': 'application/json' } });
}

test('storage validates, hashes, and bounds a serialized graph', () => {
  const stored = validateGraphForStorage(graph);
  assert.equal(stored.revision.length, 64);
  assert.equal(JSON.parse(stored.snapshotJson).name, 'fixture');
  assert.throws(() => validateGraphForStorage({ ...graph, nodes: [{ ...graph.nodes[0], id: '' }] }));
});

test('configuration and Query API URL are server-controlled and validated', () => {
  assert.equal(getNeo4jConfig({ NEO4J_URI: 'http://localhost:7474', NEO4J_USERNAME: 'u', NEO4J_PASSWORD: 'p', GRAPH_STORE_NAMESPACE: 'workspace' })?.database, 'neo4j');
  assert.equal(getNeo4jConfig({ NEO4J_URI: 'http://localhost:7474', NEO4J_USERNAME: 'u', NEO4J_PASSWORD: 'p' }), null);
  assert.equal(resolveQueryUrl(config), 'https://db.example.test/db/neo4j/query/v2');
  assert.throws(() => resolveQueryUrl({ ...config, uri: 'https://user:password@db.example.test' }));
  assert.throws(() => resolveQueryUrl({ ...config, uri: 'file:///tmp/db' }));
  assert.throws(() => resolveQueryUrl({ ...config, database: 'neo4j/../system' }));
});

test('graph store requires a bearer token and matching browser origin', () => {
  const request = (authorization?: string, origin = 'https://app.example.test') => new Request('https://app.example.test/api/graph-store', {
    headers: { host: 'app.example.test', ...(authorization ? { authorization } : {}), origin },
  });
  assert.equal(isGraphStoreAuthorized(request('Bearer secret'), 'secret'), true);
  assert.equal(isGraphStoreAuthorized(request('Bearer wrong'), 'secret'), false);
  assert.equal(isGraphStoreAuthorized(request('Bearer secret'), undefined), false);
  assert.equal(hasGraphStoreSafeOrigin(request('Bearer secret')), true);
  assert.equal(hasGraphStoreSafeOrigin(request('Bearer secret', 'https://evil.example')), false);
  assert.equal(hasGraphStoreSafeOrigin(request('Bearer secret', 'invalid')), false);
});

test('save uses parameterized scoped Cypher and publishes only after revision data writes', async () => {
  const { revision } = validateGraphForStorage(graph);
  let capturedUrl = '';
  let captured: { statement: string; parameters: Record<string, unknown> } | undefined;
  const store = createNeo4jStore(config, async (url, init) => {
    capturedUrl = String(url);
    captured = JSON.parse(String(init?.body));
    return queryResponse(['revision', 'name', 'nodeCount', 'edgeCount', 'createdAt'], [revision, graph.name, 2, 1, '2026-09-27T12:00:00Z']);
  });
  const result = await store.save(graph);
  assert.equal(result.revision, revision);
  assert.equal(result.nodeCount, 2);
  assert.equal(capturedUrl, 'https://db.example.test/db/neo4j/query/v2');
  assert.ok(captured);
  assert.equal(captured!.parameters.namespace, 'trusted-space');
  assert.equal(captured!.parameters.revision, revision);
  assert.equal(captured!.parameters.snapshotJson, JSON.stringify(graph));
  assert.ok(captured!.statement.indexOf('CALL { WITH rev UNWIND $nodes') < captured!.statement.indexOf('SET state.activeRevision=$revision'));
  assert.ok(captured!.statement.indexOf('CALL { WITH rev UNWIND $edges') < captured!.statement.indexOf('SET state.activeRevision=$revision'));
  assert.match(captured!.statement, /SET state\.writeSequence=coalesce\(state\.writeSequence,0\)\+1/);
  assert.ok(!captured!.statement.includes(graph.name));
  assert.ok(!captured!.statement.includes('untrusted-namespace'));
});

test('load reads only the active namespaced revision and checks snapshot integrity', async () => {
  const stored = validateGraphForStorage(graph);
  let statement = '';
  const store = createNeo4jStore(config, async (_url, init) => {
    const request = JSON.parse(String(init?.body));
    statement = request.statement;
    assert.deepEqual(request.parameters, { namespace: 'trusted-space' });
    return queryResponse(['snapshotJson', 'revision', 'name', 'nodeCount', 'edgeCount', 'createdAt'], [stored.snapshotJson, stored.revision, graph.name, 2, 1, null]);
  });
  const loaded = await store.load();
  assert.equal(loaded?.revision.revision, stored.revision);
  assert.deepEqual(loaded?.graph, graph);
  assert.match(statement, /GraphWorkspace \{namespace:\$namespace\}/);
  assert.match(statement, /GraphRevision \{namespace:\$namespace\}/);

  const corrupt = createNeo4jStore(config, async () => queryResponse(['snapshotJson', 'revision', 'name', 'nodeCount', 'edgeCount', 'createdAt'], [stored.snapshotJson, '0'.repeat(64), graph.name, 2, 1, null]));
  await assert.rejects(corrupt.load(), /integrity validation/);
});

test('Neo4j Query API errors are treated as failed transactions despite HTTP 202', async () => {
  const store = createNeo4jStore(config, async () => new Response(JSON.stringify({ errors: [{ code: 'Neo.ClientError.Statement.SyntaxError', message: 'private query detail' }] }), { status: 202 }));
  await assert.rejects(store.save(graph), /Neo4j query failed/);
});

import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { executeFramework, getFrameworkIntegrations } from '../lib/framework-adapters';
import type { IntegrationInput } from '../lib/integration-runtime';

const env = {
  COGNEE_BASE_URL: 'https://cognee.example', COGNEE_API_KEY: 'cognee-secret', COGNEE_DATASET: 'repo-test',
  MIROFISH_BASE_URL: 'http://127.0.0.1:5001',
  LANGGRAPH_BASE_URL: 'https://langgraph.example', LANGGRAPH_API_KEY: 'lg-secret', LANGGRAPH_ASSISTANT_ID: 'agent',
  CREWAI_BASE_URL: 'https://crew.example', CREWAI_TOKEN: 'crew-secret',
};
const input: IntegrationInput = {
  goal: 'Review dependency risks',
  graph: {
    version: 1, name: 'fixture', warnings: [], truncated: false,
    nodes: [
      { id: 'file:a.py', name: 'a.py', kind: 'file', path: 'a.py', summary: 'fixture module', confidence: 'parsed' },
      { id: 'file:b.py', name: 'b.py', kind: 'file', path: 'b.py', summary: 'second fixture', confidence: 'parsed' },
    ],
    edges: [{ source: 'file:a.py', target: 'file:b.py', relation: 'imports', confidence: 'parsed' }],
  },
  parameters: {},
};

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test('catalog exposes only configured framework operations and their real scope', () => {
  const catalog = getFrameworkIntegrations(env);
  assert.deepEqual(catalog.map((entry) => entry.id), ['cognee', 'mirofish', 'langgraph', 'crewai']);
  assert.deepEqual(catalog.find((entry) => entry.id === 'cognee')?.operations.map((op) => op.id), ['add', 'cognify', 'search']);
  const operations = Object.fromEntries(catalog.map((entry) => [entry.id, Object.fromEntries(entry.operations.map((op) => [op.id, op.inputFields?.map((field) => field.id) || []]))]));
  assert.deepEqual(operations.cognee, { add: ['dataset'], cognify: ['dataset'], search: ['dataset', 'searchType', 'topK'] });
  assert.deepEqual(operations.mirofish, { simulate: ['simulationId', 'platform', 'maxRounds'], status: ['simulationId'], cancel: ['simulationId'] });
  assert.deepEqual(operations.langgraph, { run: [], status: ['threadId', 'runId'], cancel: ['threadId', 'runId'] });
  assert.deepEqual(operations.crewai, { run: ['inputsJson'], status: ['kickoffId'] });
  assert.match(catalog.find((entry) => entry.id === 'crewai')?.statusText || '', /not automatically sent/);
  assert.deepEqual(getFrameworkIntegrations({}).map((entry) => entry.operations), [[], [], [], []]);
});

test('Cognee add ingests the selected graph, then search stays dataset scoped', async () => {
  const seen: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), init });
    return new Response(JSON.stringify({ success: true, data: { accepted: true } }), { status: 200 });
  };
  const added = await executeFramework('cognee', 'add', input, env, new AbortController().signal);
  const addBody = JSON.parse(String(seen[0].init?.body));
  assert.equal(seen[0].url, 'https://cognee.example/api/v1/add');
  assert.equal(seen[0].init?.headers && (seen[0].init?.headers as Record<string, string>)['X-Api-Key'], 'cognee-secret');
  assert.equal(addBody.datasetName, 'repo-test');
  assert.match(addBody.data, /dependency/);
  assert.equal((added.result as { scope: string }).scope, 'selected-snapshot-ingested');

  await executeFramework('cognee', 'search', input, env, new AbortController().signal);
  const searchBody = JSON.parse(String(seen[1].init?.body));
  assert.deepEqual(searchBody.datasets, ['repo-test']);
  assert.equal(searchBody.query, input.goal);
  assert.equal(seen[1].init?.redirect, 'error');
  await executeFramework('cognee', 'cognify', input, env);
  assert.equal(seen[2].url, 'https://cognee.example/api/v1/cognify');
  assert.deepEqual(JSON.parse(String(seen[2].init?.body)), { datasets: ['repo-test'], run_in_background: true });
});

test('MiroFish refuses to start a non-idle run and never requests force restart', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify({ success: true, data: { runner_status: 'completed' } }), { status: 200 });
  };
  await assert.rejects(executeFramework('mirofish', 'simulate', { ...input, parameters: { simulationId: 'sim-1' } }, env), /idle state/);
  assert.equal(calls, 1);

  const requests: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ success: true, data: requests.length === 1 ? { runner_status: 'idle' } : { runner_status: 'running' } }), { status: 200 });
  };
  const result = await executeFramework('mirofish', 'simulate', { ...input, parameters: { simulationId: 'sim-1', maxRounds: 4 } }, env);
  assert.equal(requests[1].url, 'http://127.0.0.1:5001/api/simulation/start');
  assert.equal(JSON.parse(String(requests[1].init?.body)).force, false);
  assert.equal((result.result as { scope: string }).scope, 'existing-prepared-simulation');
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ success: true, data: { runner_status: 'stopped' } }), { status: 200 });
  };
  await executeFramework('mirofish', 'cancel', { ...input, parameters: { simulationId: 'sim-1' } }, env);
  assert.equal(requests.at(-1)?.url, 'http://127.0.0.1:5001/api/simulation/stop');
  assert.deepEqual(JSON.parse(String(requests.at(-1)?.init?.body)), { simulation_id: 'sim-1' });
});

test('LangGraph async run returns IDs; status and cancel use those IDs', async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    const payload = requests.length === 1 ? { thread_id: 'thread-1' } : requests.length === 2 ? { run_id: 'run-1', status: 'pending' } : { status: 'ok' };
    return new Response(JSON.stringify(payload), { status: 200 });
  };
  const result = await executeFramework('langgraph', 'run', input, env);
  assert.equal(requests[0].url, 'https://langgraph.example/threads');
  assert.equal(requests[1].url, 'https://langgraph.example/threads/thread-1/runs');
  const runBody = JSON.parse(String(requests[1].init?.body));
  assert.equal(runBody.assistant_id, 'agent');
  assert.match(runBody.input.messages[0].content, /Selected repository graph context/);
  assert.deepEqual(result.result && { threadId: (result.result as { threadId: string }).threadId, runId: (result.result as { runId: string }).runId }, { threadId: 'thread-1', runId: 'run-1' });

  await executeFramework('langgraph', 'status', { ...input, parameters: { threadId: 'thread-1', runId: 'run-1' } }, env);
  assert.equal(requests[2].url, 'https://langgraph.example/threads/thread-1/runs/run-1');
  await executeFramework('langgraph', 'cancel', { ...input, parameters: { threadId: 'thread-1', runId: 'run-1' } }, env);
  assert.equal(requests[3].url, 'https://langgraph.example/threads/thread-1/runs/run-1/cancel?wait=0&action=interrupt');
});

test('CrewAI uses its documented kickoff/status endpoints without implying graph ingestion', async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify(requests.length === 1 ? { kickoff_id: 'kick-1' } : { state: 'RUNNING' }), { status: 200 });
  };
  const result = await executeFramework('crewai', 'run', { ...input, parameters: { inputsJson: '{"region":"eu","limit":4}' } }, env);
  assert.equal(requests[0].url, 'https://crew.example/kickoff');
  assert.deepEqual(JSON.parse(String(requests[0].init?.body)).inputs, { region: 'eu', limit: 4, goal: input.goal });
  assert.equal((result.result as { graphIncluded: boolean }).graphIncluded, false);
  await executeFramework('crewai', 'status', { ...input, parameters: { kickoffId: 'kick-1' } }, env);
  assert.equal(requests[1].url, 'https://crew.example/status/kick-1');
  assert.equal(requests[0].init?.redirect, 'error');
  await assert.rejects(executeFramework('crewai', 'run', { ...input, parameters: { inputsJson: '["not","object"]' } }, env), /JSON object/);
  await assert.rejects(executeFramework('crewai', 'run', { ...input, parameters: { inputsJson: '{"nested":{"unsafe":true}}' } }, env), /values must be strings/);
});

test('framework adapter rejects unknown operations, unsafe URLs, and oversized graph uploads', async () => {
  await assert.rejects(executeFramework('mirofish', 'restart', input, env), /not allowlisted/);
  await assert.rejects(executeFramework('mirofish', 'status', { ...input, parameters: { simulationId: 'sim-1' } }, { ...env, MIROFISH_BASE_URL: 'https://public.example' }), /server-private/);
  await assert.rejects(executeFramework('crewai', 'cancel', input, env), /not allowlisted/);
  await assert.rejects(executeFramework('cognee', 'search', input, { ...env, COGNEE_BASE_URL: 'http://example.com' }), /HTTPS/);
  const hugeInput = { ...input, graph: { ...input.graph!, name: 'x'.repeat(999_999) } };
  globalThis.fetch = async () => new Response('{}', { status: 200 });
  await assert.rejects(executeFramework('cognee', 'add', hugeInput, env), /1 MB input limit/);
});

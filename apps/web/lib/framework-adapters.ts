import type { IntegrationField, IntegrationInfo, IntegrationInput } from './integration-runtime';

type FrameworkEnv = Record<string, string | undefined>;
type FrameworkResult = {
  result: unknown;
  usage?: { inputTokens: number | null; outputTokens: number | null };
};

const MAX_FRAMEWORK_BODY = 1_000_000;
const MAX_FRAMEWORK_OUTPUT = 1_000_000;

const field = (id: string, label: string, required = true): IntegrationField => ({ id, label, type: 'text', required });
const numberField = (id: string, label: string, defaultValue?: number): IntegrationField => ({ id, label, type: 'number', required: false, ...(defaultValue === undefined ? {} : { defaultValue }) });
const selectField = (id: string, label: string, options: string[], defaultValue?: string): IntegrationField => ({ id, label, type: 'select', required: false, options, ...(defaultValue ? { defaultValue } : {}) });

function configured(env: FrameworkEnv, keys: string[]) {
  return keys.every((key) => Boolean(env[key]?.trim()));
}

export function getFrameworkIntegrations(env: FrameworkEnv = process.env): IntegrationInfo[] {
  const cogneeReady = configured(env, ['COGNEE_BASE_URL', 'COGNEE_DATASET']);
  const cogneeHeaders = env.COGNEE_API_KEY?.trim();
  const mirofishReady = configured(env, ['MIROFISH_BASE_URL']);
  const langgraphReady = configured(env, ['LANGGRAPH_BASE_URL', 'LANGGRAPH_ASSISTANT_ID', 'LANGGRAPH_API_KEY']);
  const crewReady = configured(env, ['CREWAI_BASE_URL', 'CREWAI_TOKEN']);
  return [
    {
      id: 'cognee', label: 'Cognee', category: 'framework', mode: 'remote_api', configured: cogneeReady,
      capability: cogneeReady ? 'ready' : 'unconfigured',
      statusText: cogneeReady
        ? `Dataset-scoped API configured (${cogneeHeaders ? 'API-key auth' : 'self-hosted unauthenticated mode'}). Add explicitly ingests the selected snapshot; search/cognify operate on this dataset.`
        : 'Set COGNEE_BASE_URL and COGNEE_DATASET. COGNEE_API_KEY is required for Cognee Cloud; self-hosted instances may allow no auth.',
      operations: cogneeReady ? [
        { id: 'add', label: 'Ingest selected graph', description: 'Explicitly adds a bounded JSON representation of the selected snapshot to the configured Cognee dataset.', inputFields: [field('dataset', 'Cognee dataset', false)] },
        { id: 'cognify', label: 'Build knowledge graph', description: 'Runs Cognee cognify for the configured dataset; the API may return an asynchronous acknowledgment.', inputFields: [field('dataset', 'Cognee dataset', false)] },
        { id: 'search', label: 'Search dataset', description: 'Searches only the configured Cognee dataset; selected graph data is used only if it was ingested first.', inputFields: [field('dataset', 'Cognee dataset', false), selectField('searchType', 'Search type', ['GRAPH_COMPLETION', 'RAG_COMPLETION', 'CHUNKS', 'SUMMARIES', 'TRIPLET_COMPLETION', 'CHUNKS_LEXICAL', 'CODING_RULES', 'TEMPORAL'], 'GRAPH_COMPLETION'), numberField('topK', 'Top results', 5)] },
      ] : [],
      inputFields: [field('dataset', 'Cognee dataset', false), field('searchType', 'Search type', false), numberField('topK', 'Top results', 5)],
    },
    {
      id: 'mirofish', label: 'MiroFish', category: 'framework', mode: 'remote_api', configured: mirofishReady,
      capability: mirofishReady ? 'partial' : 'unconfigured',
      statusText: mirofishReady
        ? 'Uses an existing prepared MiroFish simulation ID. The upstream Flask API has no authentication; configure a server-private endpoint only. Stop terminates its simulation process.'
        : 'Set MIROFISH_BASE_URL to a server-private MiroFish API. Upstream API does not authenticate requests.',
      operations: mirofishReady ? [
        { id: 'simulate', label: 'Start prepared simulation', description: 'Requires an existing prepared simulation ID. A run-status preflight must be idle; force restart is always false.', inputFields: [field('simulationId', 'Prepared simulation ID'), selectField('platform', 'Platform', ['twitter', 'reddit', 'parallel'], 'parallel'), numberField('maxRounds', 'Maximum rounds', 10)] },
        { id: 'status', label: 'Check simulation status', description: 'Reads the existing simulation runner status and progress.', inputFields: [field('simulationId', 'Prepared simulation ID')] },
        { id: 'cancel', label: 'Stop simulation process', description: 'Terminates the existing MiroFish simulation runner. This stops an external process; it does not cancel only this dashboard job.', inputFields: [field('simulationId', 'Prepared simulation ID')] },
      ] : [],
      inputFields: [field('simulationId', 'Prepared simulation ID'), field('platform', 'Platform', false), numberField('maxRounds', 'Maximum rounds', 10)],
    },
    {
      id: 'langgraph', label: 'LangGraph', category: 'framework', mode: 'remote_api', configured: langgraphReady,
      capability: langgraphReady ? 'ready' : 'unconfigured',
      statusText: langgraphReady
        ? 'Uses the configured LangGraph deployment and assistant with the documented messages-state input. Run returns remote thread/run IDs for later status or cancellation.'
        : 'Set LANGGRAPH_BASE_URL, LANGGRAPH_ASSISTANT_ID, and LANGGRAPH_API_KEY for an Agent Server deployment.',
      operations: langgraphReady ? [
        { id: 'run', label: 'Run deployment', description: 'Creates a remote thread and async run; sends the goal and selected graph as a user message.', inputFields: [] },
        { id: 'status', label: 'Check run status', description: 'Requires threadId and runId returned by Run deployment.', inputFields: [field('threadId', 'Thread ID'), field('runId', 'Run ID')] },
        { id: 'cancel', label: 'Cancel remote run', description: 'Requires threadId and runId returned by Run deployment.', inputFields: [field('threadId', 'Thread ID'), field('runId', 'Run ID')] },
      ] : [],
      inputFields: [field('threadId', 'Thread ID', false), field('runId', 'Run ID', false)],
    },
    {
      id: 'crewai', label: 'CrewAI AMP', category: 'framework', mode: 'remote_api', configured: crewReady,
      capability: crewReady ? 'partial' : 'unconfigured',
      statusText: crewReady
        ? 'Uses one configured CrewAI deployment URL and token. Kickoff submits goal/parameters as deployment-specific inputs; selected graph is not automatically sent. Official API guide documents kickoff/status, not cancellation.'
        : 'Set CREWAI_BASE_URL and CREWAI_TOKEN for a deployed CrewAI AMP crew or flow.',
      operations: crewReady ? [
        { id: 'run', label: 'Kick off deployed crew', description: 'Submits deployment-specific JSON inputs plus the task goal. Returns kickoffId for polling.', inputFields: [field('inputsJson', 'Deployment inputs (JSON)', false)] },
        { id: 'status', label: 'Check kickoff status', description: 'Requires kickoffId returned by Kick off deployed crew.', inputFields: [field('kickoffId', 'Kickoff ID')] },
      ] : [],
      inputFields: [field('kickoffId', 'Kickoff ID', false)],
    },
  ];
}

function required(value: string | undefined, name: string) {
  if (!value?.trim()) throw new Error(`${name} is not configured.`);
  return value.trim();
}

function serviceBase(env: FrameworkEnv, name: string, allowHttpLocal = false) {
  const raw = required(env[name], name);
  let url: URL;
  try { url = new URL(raw); } catch { throw new Error(`${name} must be a valid service URL.`); }
  const local = url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '::1';
  if ((url.protocol !== 'https:' && !(allowHttpLocal && local && url.protocol === 'http:')) || url.username || url.password || url.search || url.hash) {
    throw new Error(`${name} must use HTTPS (HTTP is allowed only for localhost) and contain no credentials, query, or fragment.`);
  }
  return url.toString().replace(/\/$/, '');
}

function assertPrivateMiroFish(base: string) {
  const host = new URL(base).hostname.toLowerCase().replace(/^\[|\]$/g, '');
  const local = ['localhost', '::1'].includes(host) || host.endsWith('.local');
  const privateV4 = /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) || host.startsWith('127.');
  const privateV6 = /^(fc|fd|fe80:)/.test(host);
  if (!(local || privateV4 || privateV6)) throw new Error('MIROFISH_BASE_URL must target a server-private or loopback service because the upstream API has no authentication.');
}

function id(value: string | number | undefined, label: string) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
    throw new Error(`${label} is required and must be a valid identifier.`);
  }
  return value;
}

function boundedJson(value: unknown) {
  const text = JSON.stringify(value);
  if (new TextEncoder().encode(text).byteLength > MAX_FRAMEWORK_BODY) throw new Error('Framework request exceeded the 1 MB input limit.');
  return text;
}

async function requestJson(url: string, init: RequestInit, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { ...init, signal, redirect: 'error', cache: 'no-store' });
  const declaredLength = Number(response.headers.get('content-length') || 0);
  if (declaredLength > MAX_FRAMEWORK_OUTPUT) throw new Error('Framework response exceeded the 1 MB output limit.');
  const reader = response.body?.getReader();
  let text = '';
  if (reader) {
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_FRAMEWORK_OUTPUT) {
        await reader.cancel();
        throw new Error('Framework response exceeded the 1 MB output limit.');
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    text = new TextDecoder().decode(bytes);
  }
  if (!response.ok) throw new Error(`Framework request failed with HTTP ${response.status}.`);
  if (!text) return null;
  try { return JSON.parse(text); } catch { return text.slice(0, 12_000); }
}

function envelope(value: unknown) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (record.success === false) throw new Error('Framework rejected the request.');
    return 'data' in record ? record.data : record;
  }
  return value;
}

function graphDocument(input: IntegrationInput) {
  if (!input.graph) throw new Error('This operation requires the selected repository graph.');
  return {
    name: input.graph.name,
    goal: input.goal.slice(0, 2_000),
    nodes: input.graph.nodes.map((node) => ({ id: node.id, name: node.name, kind: node.kind, path: node.path, summary: node.summary.slice(0, 500) })),
    edges: input.graph.edges.map((edge) => ({ source: edge.source, target: edge.target, relation: edge.relation })),
  };
}

async function executeCognee(operation: string, input: IntegrationInput, env: FrameworkEnv, signal: AbortSignal): Promise<FrameworkResult> {
  const base = serviceBase(env, 'COGNEE_BASE_URL', true);
  const dataset = typeof input.parameters.dataset === 'string' && input.parameters.dataset.trim()
    ? input.parameters.dataset.trim() : required(env.COGNEE_DATASET, 'COGNEE_DATASET');
  if (!/^[A-Za-z0-9][A-Za-z0-9 _.-]{0,99}$/.test(dataset)) throw new Error('Cognee dataset name is invalid.');
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (env.COGNEE_API_KEY?.trim()) headers['X-Api-Key'] = env.COGNEE_API_KEY.trim();
  let url: string;
  let body: unknown;
  let scope: string;
  if (operation === 'add') {
    const document = graphDocument(input);
    url = `${base}/api/v1/add`;
    body = { data: boundedJson(document), datasetName: dataset };
    scope = 'selected-snapshot-ingested';
  } else if (operation === 'cognify') {
    url = `${base}/api/v1/cognify`;
    body = { datasets: [dataset], run_in_background: true };
    scope = 'configured-dataset';
  } else if (operation === 'search') {
    url = `${base}/api/v1/search`;
    const searchType = typeof input.parameters.searchType === 'string' ? input.parameters.searchType : 'GRAPH_COMPLETION';
    const allowedSearchTypes = new Set(['GRAPH_COMPLETION', 'RAG_COMPLETION', 'CHUNKS', 'SUMMARIES', 'TRIPLET_COMPLETION', 'CHUNKS_LEXICAL', 'CODING_RULES', 'TEMPORAL']);
    if (!allowedSearchTypes.has(searchType)) throw new Error('Cognee search type is not allowlisted.');
    const requestedTopK = Number(input.parameters.topK ?? 5);
    const topK = Number.isFinite(requestedTopK) ? Math.max(1, Math.min(20, Math.floor(requestedTopK))) : 5;
    body = { query: input.goal.slice(0, 2_000), search_type: searchType, datasets: [dataset], top_k: topK };
    scope = 'configured-dataset';
  } else throw new Error('Cognee operation is not allowlisted.');
  const result = await requestJson(url, { method: 'POST', headers, body: boundedJson(body) }, signal);
  return { result: { integrationId: 'cognee', operation, scope, dataset, response: envelope(result), ...(operation === 'cognify' ? { remoteExecution: { state: 'accepted', terminal: false, followUpOperation: 'search', note: 'The request used run_in_background=true; this acknowledgment does not prove cognification completed.' } } : {}) } };
}

async function executeMiroFish(operation: string, input: IntegrationInput, env: FrameworkEnv, signal: AbortSignal): Promise<FrameworkResult> {
  const base = serviceBase(env, 'MIROFISH_BASE_URL', true);
  assertPrivateMiroFish(base);
  const simulationId = id(input.parameters.simulationId, 'simulationId');
  const root = `${base}/api/simulation`;
  if (operation === 'status') {
    const status = await requestJson(`${root}/${encodeURIComponent(simulationId)}/run-status`, { method: 'GET' }, signal);
    return { result: { integrationId: 'mirofish', operation, scope: 'existing-simulation', simulationId, response: envelope(status) } };
  }
  if (operation === 'cancel') {
    const stopped = await requestJson(`${root}/stop`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: boundedJson({ simulation_id: simulationId }) }, signal);
    return { result: { integrationId: 'mirofish', operation, scope: 'existing-simulation-process-termination', simulationId, response: envelope(stopped) } };
  }
  if (operation !== 'simulate') throw new Error('MiroFish operation is not allowlisted.');
  const before = envelope(await requestJson(`${root}/${encodeURIComponent(simulationId)}/run-status`, { method: 'GET' }, signal)) as Record<string, unknown> | null;
  if (before?.runner_status !== 'idle') throw new Error('MiroFish can start only a prepared simulation in idle state; existing run data was left untouched.');
  const platform = typeof input.parameters.platform === 'string' ? input.parameters.platform : 'parallel';
  if (!['twitter', 'reddit', 'parallel'].includes(platform)) throw new Error('MiroFish platform is invalid.');
  const maxRounds = Number(input.parameters.maxRounds ?? 10);
  if (!Number.isInteger(maxRounds) || maxRounds < 1 || maxRounds > 100) throw new Error('MiroFish maxRounds must be an integer from 1 to 100.');
  const started = await requestJson(`${root}/start`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: boundedJson({ simulation_id: simulationId, platform, max_rounds: maxRounds, force: false }),
  }, signal);
  return { result: { integrationId: 'mirofish', operation, scope: 'existing-prepared-simulation', simulationId, response: envelope(started), remoteExecution: { state: 'accepted', terminal: false, followUpOperation: 'status' }, note: 'The upstream runner executes independently after this start response; poll status using the returned simulationId.' } };
}

function langGraphHeaders(env: FrameworkEnv) {
  return { 'content-type': 'application/json', 'x-api-key': required(env.LANGGRAPH_API_KEY, 'LANGGRAPH_API_KEY') };
}

async function executeLangGraph(operation: string, input: IntegrationInput, env: FrameworkEnv, signal: AbortSignal): Promise<FrameworkResult> {
  const base = serviceBase(env, 'LANGGRAPH_BASE_URL');
  const headers = langGraphHeaders(env);
  if (operation === 'run') {
    const thread = envelope(await requestJson(`${base}/threads`, { method: 'POST', headers, body: '{}' }, signal)) as Record<string, unknown> | null;
    const createdThreadId = id(typeof thread?.thread_id === 'string' ? thread.thread_id : undefined, 'LangGraph thread_id response');
    let content = input.goal;
    let context: unknown = null;
    if (input.graph) {
      const nodes = input.graph.nodes.slice(0, 90).map((node) => ({ id: node.id.slice(0, 160), name: node.name.slice(0, 160), kind: node.kind, path: node.path.slice(0, 240) }));
      const nodeIds = new Set(nodes.map((node) => node.id));
      const edges = input.graph.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).slice(0, 180).map((edge) => ({ source: edge.source.slice(0, 160), target: edge.target.slice(0, 160), relation: edge.relation.slice(0, 120) }));
      context = { snapshot: input.graph.name.slice(0, 200), nodes, edges, omittedNodes: input.graph.nodes.length - nodes.length, omittedEdges: input.graph.edges.length - edges.length };
      content = `${input.goal}\n\nSelected repository graph context (JSON; bounded selection):\n${JSON.stringify(context)}`;
    }
    if (content.length > 60_000) throw new Error('LangGraph message exceeded the 60 KB input limit.');
    const assistantId = required(env.LANGGRAPH_ASSISTANT_ID, 'LANGGRAPH_ASSISTANT_ID');
    const run = envelope(await requestJson(`${base}/threads/${encodeURIComponent(createdThreadId)}/runs`, {
      method: 'POST', headers,
      body: boundedJson({ assistant_id: assistantId, input: { messages: [{ role: 'user', content }] } }),
    }, signal)) as Record<string, unknown> | null;
    const runId = typeof run?.run_id === 'string' ? run.run_id : typeof run?.id === 'string' ? run.id : null;
    return { result: { integrationId: 'langgraph', operation, scope: input.graph ? 'bounded-selected-snapshot-in-user-message' : 'goal-only', threadId: createdThreadId, runId, ...(context ? { graphContext: context } : {}), response: run, ...(runId ? { remoteExecution: { state: 'accepted', terminal: false, followUpOperation: 'status' } } : {}) } };
  }
  if (operation === 'status') {
    const threadId = id(input.parameters.threadId, 'threadId');
    const runId = id(input.parameters.runId, 'runId');
    const status = await requestJson(`${base}/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}`, { method: 'GET', headers }, signal);
    return { result: { integrationId: 'langgraph', operation, threadId, runId, response: envelope(status) } };
  }
  if (operation === 'cancel') {
    const threadId = id(input.parameters.threadId, 'threadId');
    const runId = id(input.parameters.runId, 'runId');
    const query = new URLSearchParams({ wait: '0', action: 'interrupt' });
    const cancelled = await requestJson(`${base}/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/cancel?${query}`, { method: 'POST', headers }, signal);
    return { result: { integrationId: 'langgraph', operation, threadId, runId, response: envelope(cancelled) } };
  }
  throw new Error('LangGraph operation is not allowlisted.');
}

async function executeCrewAI(operation: string, input: IntegrationInput, env: FrameworkEnv, signal: AbortSignal): Promise<FrameworkResult> {
  const base = serviceBase(env, 'CREWAI_BASE_URL');
  const headers = { authorization: `Bearer ${required(env.CREWAI_TOKEN, 'CREWAI_TOKEN')}`, 'content-type': 'application/json' };
  if (operation === 'run') {
    const rawInputs = input.parameters.inputsJson;
    let deploymentInputs: Record<string, unknown> = {};
    if (typeof rawInputs === 'string' && rawInputs.trim()) {
      if (new TextEncoder().encode(rawInputs).byteLength > 16_000) throw new Error('CrewAI deployment inputs are limited to 16 KB.');
      let parsed: unknown;
      try { parsed = JSON.parse(rawInputs); } catch { throw new Error('CrewAI deployment inputs must be valid JSON.'); }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('CrewAI deployment inputs must be a JSON object.');
      deploymentInputs = parsed as Record<string, unknown>;
      if (Object.values(deploymentInputs).some((value) => value !== null && !['string', 'number', 'boolean'].includes(typeof value))) {
        throw new Error('CrewAI deployment input values must be strings, numbers, booleans, or null.');
      }
    }
    const inputs = { ...deploymentInputs, goal: input.goal.slice(0, 2_000) };
    const response = await requestJson(`${base}/kickoff`, { method: 'POST', headers, body: boundedJson({ inputs }) }, signal);
    const result = envelope(response) as Record<string, unknown> | null;
    const kickoffId = typeof result?.kickoff_id === 'string' ? result.kickoff_id : null;
    return { result: { integrationId: 'crewai', operation, scope: 'configured-deployment-inputs', graphIncluded: false, kickoffId, response: result, ...(kickoffId ? { remoteExecution: { state: 'accepted', terminal: false, followUpOperation: 'status' } } : {}) } };
  }
  if (operation === 'status') {
    const kickoffId = id(input.parameters.kickoffId, 'kickoffId');
    const status = await requestJson(`${base}/status/${encodeURIComponent(kickoffId)}`, { method: 'GET', headers }, signal);
    return { result: { integrationId: 'crewai', operation, scope: 'configured-deployment-run', kickoffId, response: envelope(status) } };
  }
  throw new Error('CrewAI operation is not allowlisted.');
}

export async function executeFramework(
  integrationId: string,
  operation: string,
  input: IntegrationInput,
  env: FrameworkEnv = process.env,
  signal: AbortSignal = new AbortController().signal,
  _jobId?: string,
): Promise<FrameworkResult> {
  if (signal.aborted) throw new Error('Framework operation cancelled.');
  const allowed: Record<string, string[]> = {
    cognee: ['add', 'cognify', 'search'],
    mirofish: ['simulate', 'status', 'cancel'],
    langgraph: ['run', 'status', 'cancel'],
    crewai: ['run', 'status'],
  };
  if (!allowed[integrationId]?.includes(operation)) throw new Error('Framework operation is not allowlisted.');
  switch (integrationId) {
    case 'cognee': return executeCognee(operation, input, env, signal);
    case 'mirofish': return executeMiroFish(operation, input, env, signal);
    case 'langgraph': return executeLangGraph(operation, input, env, signal);
    case 'crewai': return executeCrewAI(operation, input, env, signal);
    default: throw new Error('Framework integration is not allowlisted.');
  }
}

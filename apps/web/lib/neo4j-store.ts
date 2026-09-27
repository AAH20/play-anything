import { createHash, timingSafeEqual } from 'node:crypto';
import { parseSnapshot, type Snapshot } from './graph';

export const GRAPH_STORE_MAX_BYTES = 2 * 1024 * 1024;
export const GRAPH_STORE_TIMEOUT_MS = 20_000;
export const GRAPH_STORE_MAX_NODES = 20_000;
export const GRAPH_STORE_MAX_EDGES = 80_000;

export type Neo4jConfig = {
  uri: string;
  username: string;
  password: string;
  database?: string;
  namespace: string;
};

export type StoredRevision = {
  revision: string;
  name: string;
  nodeCount: number;
  edgeCount: number;
  createdAt: string | null;
};

type QueryResult = { data?: { fields?: string[]; values?: unknown[][] }; errors?: { code?: string; message?: string }[] };

export function getNeo4jConfig(env: Record<string, string | undefined> = process.env): Neo4jConfig | null {
  const { NEO4J_URI: uri, NEO4J_USERNAME: username, NEO4J_PASSWORD: password, GRAPH_STORE_NAMESPACE: namespace } = env;
  if (!uri || !username || !password || !namespace) return null;
  return { uri, username, password, namespace, database: env.NEO4J_DATABASE || 'neo4j' };
}

export function isGraphStoreAuthorized(request: Request, token: string | undefined): boolean {
  if (!token) return false;
  const value = request.headers.get('authorization') || '';
  if (!value.startsWith('Bearer ') || value.length !== token.length + 7) return false;
  const received = Buffer.from(value.slice(7));
  const expected = Buffer.from(token);
  return received.length === expected.length && timingSafeEqual(received, expected);
}

export function hasGraphStoreSafeOrigin(request: Request): boolean {
  const origin = request.headers.get('origin');
  if (!origin) return true;
  try {
    const parsed = new URL(origin);
    const host = request.headers.get('x-forwarded-host') || request.headers.get('host');
    const proto = request.headers.get('x-forwarded-proto') || new URL(request.url).protocol.slice(0, -1);
    return Boolean(host && parsed.host === host && parsed.protocol === `${proto}:`);
  } catch { return false; }
}

export function validateGraphForStorage(value: unknown): { graph: Snapshot; revision: string; snapshotJson: string } {
  const graph = parseSnapshot(value);
  if (graph.nodes.length > GRAPH_STORE_MAX_NODES || graph.edges.length > GRAPH_STORE_MAX_EDGES) throw new Error('Graph exceeds storage limits.');
  const snapshotJson = JSON.stringify(graph);
  if (Buffer.byteLength(snapshotJson, 'utf8') > GRAPH_STORE_MAX_BYTES) throw new Error(`Graph snapshot exceeds ${GRAPH_STORE_MAX_BYTES} bytes.`);
  const revision = createHash('sha256').update(snapshotJson).digest('hex');
  return { graph, revision, snapshotJson };
}

export function resolveQueryUrl(config: Neo4jConfig): string {
  let base: URL;
  try { base = new URL(config.uri); } catch { throw new Error('Neo4j URI is invalid.'); }
  if (!['http:', 'https:'].includes(base.protocol) || !base.hostname || base.username || base.password || base.search || base.hash || (base.pathname !== '/' && base.pathname !== '')) {
    throw new Error('Neo4j URI must be an HTTP(S) origin without credentials, path, query, or fragment.');
  }
  const database = config.database || 'neo4j';
  if (!/^[A-Za-z0-9_.-]{1,63}$/.test(database)) throw new Error('Neo4j database name is invalid.');
  if (!config.namespace || config.namespace.length > 128) throw new Error('Graph store namespace is invalid.');
  return new URL(`/db/${encodeURIComponent(database)}/query/v2`, base).toString();
}

function extractRows(body: QueryResult): { fields: string[]; values: unknown[][] } {
  if (body.errors?.length) throw new Error('Neo4j query failed.');
  if (!body.data || !Array.isArray(body.data.fields) || !Array.isArray(body.data.values)) throw new Error('Neo4j returned an invalid response.');
  return body.data as { fields: string[]; values: unknown[][] };
}

export function createNeo4jStore(config: Neo4jConfig, fetcher: typeof fetch = fetch) {
  const url = resolveQueryUrl(config);
  const database = config.database || 'neo4j';
  const authorization = `Basic ${Buffer.from(`${config.username}:${config.password}`, 'utf8').toString('base64')}`;

  async function query<T>(statement: string, parameters: Record<string, unknown>, signal?: AbortSignal): Promise<T[]> {
    const response = await fetcher(url, {
      method: 'POST',
      headers: { authorization, 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ statement, parameters }),
      signal: signal ?? AbortSignal.timeout(GRAPH_STORE_TIMEOUT_MS),
    });
    if (!response.ok) throw new Error('Neo4j request failed.');
    const body = await response.json() as QueryResult;
    const { fields, values } = extractRows(body);
    return values.map(row => Object.fromEntries(fields.map((field, index) => [field, row[index]])) as T);
  }

  return {
    async save(value: unknown, signal?: AbortSignal): Promise<StoredRevision> {
      const { graph, revision, snapshotJson } = validateGraphForStorage(value);
      const parameters = {
        namespace: config.namespace,
        revision,
        snapshotJson,
        name: graph.name,
        nodeCount: graph.nodes.length,
        edgeCount: graph.edges.length,
        nodes: graph.nodes.map(n => ({ id: n.id, name: n.name, kind: n.kind, path: n.path, summary: n.summary, confidence: n.confidence, line: n.line ?? null })),
        edges: graph.edges.map((e, index) => ({ key: String(index), source: e.source, target: e.target, relation: e.relation, confidence: e.confidence, line: e.line ?? null, count: e.count ?? null })),
      };
      const statement = `MERGE (state:GraphWorkspace {namespace:$namespace}) SET state.writeSequence=coalesce(state.writeSequence,0)+1 WITH state OPTIONAL MATCH (state)-[prior:ACTIVE_REVISION]->() DELETE prior WITH DISTINCT state MERGE (rev:GraphRevision {namespace:$namespace,revision:$revision}) ON CREATE SET rev.snapshotJson=$snapshotJson, rev.digest=$revision, rev.name=$name, rev.nodeCount=$nodeCount, rev.edgeCount=$edgeCount, rev.createdAt=datetime() WITH state,rev CALL { WITH rev UNWIND $nodes AS item MERGE (n:CodeNode {namespace:$namespace,revision:$revision,id:item.id}) ON CREATE SET n.name=item.name,n.kind=item.kind,n.path=item.path,n.summary=item.summary,n.confidence=item.confidence,n.line=item.line RETURN count(*) AS persistedNodes } CALL { WITH rev UNWIND $edges AS item MATCH (source:CodeNode {namespace:$namespace,revision:$revision,id:item.source}) MATCH (target:CodeNode {namespace:$namespace,revision:$revision,id:item.target}) MERGE (source)-[edge:CODE_EDGE {namespace:$namespace,revision:$revision,key:item.key}]->(target) ON CREATE SET edge.relation=item.relation,edge.confidence=item.confidence,edge.line=item.line,edge.count=item.count RETURN count(*) AS persistedEdges } WITH state,rev,persistedNodes,persistedEdges SET state.activeRevision=$revision CREATE (state)-[:ACTIVE_REVISION]->(rev) RETURN rev.revision AS revision,rev.name AS name,persistedNodes AS nodeCount,persistedEdges AS edgeCount,toString(rev.createdAt) AS createdAt`;
      const rows = await query<StoredRevision>(statement, parameters, signal);
      if (!rows[0]) throw new Error('Neo4j did not confirm the saved revision.');
      return rows[0];
    },
    async load(signal?: AbortSignal): Promise<{ graph: Snapshot; revision: StoredRevision } | null> {
      const rows = await query<{ snapshotJson: string; revision: string; name: string; nodeCount: number; edgeCount: number; createdAt: string | null }>(
        'MATCH (:GraphWorkspace {namespace:$namespace})-[:ACTIVE_REVISION]->(rev:GraphRevision {namespace:$namespace}) RETURN rev.snapshotJson AS snapshotJson,rev.revision AS revision,rev.name AS name,rev.nodeCount AS nodeCount,rev.edgeCount AS edgeCount,toString(rev.createdAt) AS createdAt',
        { namespace: config.namespace }, signal,
      );
      const row = rows[0];
      if (!row) return null;
      if (typeof row.snapshotJson !== 'string' || typeof row.revision !== 'string') throw new Error('Stored graph snapshot is invalid.');
      const graph = parseSnapshot(JSON.parse(row.snapshotJson));
      const actualDigest = createHash('sha256').update(JSON.stringify(graph)).digest('hex');
      if (actualDigest !== row.revision) throw new Error('Stored graph snapshot failed integrity validation.');
      return { graph, revision: { revision: row.revision, name: row.name, nodeCount: row.nodeCount, edgeCount: row.edgeCount, createdAt: row.createdAt ?? null } };
    },
    database,
    namespace: config.namespace,
  };
}

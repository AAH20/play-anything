/** Source-grounded integration facts for the optional web studio. */
export type IntegrationSurface = 'native-api' | 'local-command' | 'harness-plugin' | 'needs-adapter';

export type IntegrationInterface = {
  name: string;
  signature: string;
  input: string;
  output: string;
  source: string;
};

export type IntegrationSource = {
  id: string;
  name: string;
  repository: string;
  revision: string;
  license: string;
  runtime: string;
  surface: IntegrationSurface;
  dependencies: string[];
  launch: string | null;
  auth: string | null;
  interfaces: IntegrationInterface[];
  constraints: string[];
};

/**
 * Interfaces below describe upstream entry points, not integrations implemented
 * by this application. Remote endpoints and local Python APIs require a configured
 * upstream runtime; no credentials or remote execution are performed here.
 */
export const integrationCatalog: IntegrationSource[] = [
  {
    id: 'cognee',
    name: 'Cognee',
    repository: 'https://github.com/topoteretes/cognee',
    revision: 'main @ 2026-09-06 (history head e93a4f0; full hash unavailable in source fetch)',
    license: 'Apache-2.0',
    runtime: 'Python package or self-hosted API server; external model, embedding, and graph/vector storage configuration may be required.',
    surface: 'native-api',
    dependencies: ['cognee Python package', 'configured LLM/embedding providers', 'configured storage adapters'],
    launch: 'Self-hosted: `docker run --env-file ./.env -p 8000:8000 cognee/cognee:main`; package API: `await cognee.add(...)`, `await cognee.cognify()`, `await cognee.search(...)`.',
    auth: 'Cognee Cloud uses `X-Api-Key`; local development auth is optional unless REQUIRE_AUTHENTICATION is enabled.',
    interfaces: [
      { name: 'HTTP add', signature: 'POST /api/v1/add', input: 'Multipart form data: `data` files/text and `datasetName`.', output: 'JSON response from add operation; exact fields are server-version-dependent.', source: 'https://docs.cognee.ai/api-reference/introduction' },
      { name: 'HTTP cognify', signature: 'POST /api/v1/cognify', input: 'JSON: `{ datasets?: string[], run_in_background?: boolean, chunks_per_batch?: number }`.', output: 'JSON response; background operation status can be inspected with dataset status endpoints.', source: 'https://github.com/topoteretes/cognee/blob/main/cognee/cli/api_client.py' },
      { name: 'HTTP search', signature: 'POST /api/v1/search', input: 'JSON: `{ query: string, search_type?: string, datasets?: string[], top_k?: number }`.', output: 'JSON search results (list-shaped in the official API client). HTTP does not accept all advanced Python search options.', source: 'https://github.com/topoteretes/cognee/blob/main/cognee/cli/api_client.py' },
    ],
    constraints: ['Cloud and local auth modes differ.', 'HTTP search has a narrower parameter set than the Python SDK.', 'A local DB path is not included in this project; upstream storage and model configuration are prerequisites.'],
  },
  {
    id: 'mirofish',
    name: 'MiroFish',
    repository: 'https://github.com/666ghj/MiroFish',
    revision: '39d849138ef254f6c737ab4c4705e5545dbe31d4 (main, 2026-09-03)',
    license: 'MIT',
    runtime: 'Python Flask backend plus frontend; simulation invokes configured LLM/Zep services and OASIS-related runtime dependencies.',
    surface: 'native-api',
    dependencies: ['Flask backend dependencies', 'LLM provider credentials', 'Zep API credentials', 'OASIS simulation environment'],
    launch: 'Repository documents backend API at http://localhost:5001; run the upstream Docker Compose stack or backend setup. The API route module is `backend/app/api/simulation.py`.',
    auth: 'No authentication contract was found in the inspected API routes. Treat the service as trusted-local only; do not expose it to an untrusted network.',
    interfaces: [
      { name: 'Create simulation', signature: 'POST /api/simulation/create', input: 'JSON `{ project_id: string, graph_id?: string, enable_twitter?: boolean, enable_reddit?: boolean }`.', output: 'JSON envelope `{ success: true, data: { simulation_id, project_id, graph_id, status, ... } }`.', source: 'https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/app/api/simulation.py' },
      { name: 'Prepare simulation', signature: 'POST /api/simulation/prepare', input: 'JSON `{ simulation_id: string, entity_types?: string[], use_llm_for_profiles?: boolean, parallel_profile_count?: number, force_regenerate?: boolean }`.', output: 'JSON envelope containing `simulation_id`, `task_id` for newly started asynchronous work, `status`, and `already_prepared`.', source: 'https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/app/api/simulation.py' },
      { name: 'Simulation lifecycle', signature: 'POST /api/simulation/start|stop; GET /api/simulation/<simulation_id>/run-status', input: 'Start/stop JSON is route-specific; status uses simulation id in path.', output: 'Run-status data includes runner status; stop may stop external processes and is a destructive operation.', source: 'https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/app/api/simulation.py' },
    ],
    constraints: ['Workflow is project/graph based and is not a single prompt-in/result-out call.', 'Prepare and report generation can trigger model-provider calls.', 'Route source did not establish auth; isolate and explicitly authorize any deployment before connecting.'],
  },
  {
    id: 'langgraph',
    name: 'LangGraph',
    repository: 'https://github.com/langchain-ai/langgraph',
    revision: 'main docs/source checked 2026-09-27; commit SHA not exposed by fetched GitHub history page',
    license: 'MIT (LangGraph repository/package license as declared upstream)',
    runtime: 'Python or JavaScript; compiled graph executes in-process, with optional LangGraph Agent Server/LangSmith deployment for HTTP runs.',
    surface: 'needs-adapter',
    dependencies: ['langgraph package matching implementation language', 'application-defined graph state and node functions', 'optional checkpointer and model/tool providers'],
    launch: null,
    auth: 'In-process calls have no transport auth. Hosted Agent Server authentication/deployment credentials are deployment-specific.',
    interfaces: [
      { name: 'Compiled graph invoke', signature: 'compiled_graph.invoke(input: State, config?: RunnableConfig) -> OutputState', input: 'Application-defined graph state; state schema is the graph input schema.', output: 'Graph output state as declared by output schema (defaults to graph state).', source: 'https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx' },
      { name: 'Graph construction', signature: 'StateGraph(State).add_node(...).add_edge(...).compile()', input: 'TypedDict/Pydantic/dataclass state schema and application callables.', output: 'Compiled graph with invoke/stream interfaces.', source: 'https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx' },
    ],
    constraints: ['The graph, state schema, node functions, tools, and optional persistence must be authored and configured by the embedding application.', 'The LangGraph library alone does not provide a universally running HTTP endpoint; Agent Server adds a distinct deployment surface.'],
  },
  {
    id: 'crewai',
    name: 'CrewAI',
    repository: 'https://github.com/crewAIInc/crewAI',
    revision: 'main @ 2026-09-11 (history head e1f3c4b; full hash unavailable in source fetch)',
    license: 'MIT',
    runtime: 'Python library; the application defines agents, tasks, tools, and a Crew before kickoff.',
    surface: 'needs-adapter',
    dependencies: ['crewai Python package', 'configured LLM provider', 'application-defined agents/tasks/tools'],
    launch: null,
    auth: 'No generic library-level transport authentication; provider/tool credentials are configured by the host application.',
    interfaces: [
      { name: 'Run a crew', signature: 'crew.kickoff(inputs: dict[str, Any] | None = None) -> CrewOutput', input: 'Mapping values substituted into crew/task/agent prompt templates.', output: 'CrewOutput containing run result and execution metadata.', source: 'https://github.com/crewAIInc/crewAI/blob/main/docs/v1.10.1/en/concepts/agents.mdx' },
      { name: 'Async kickoff', signature: 'await crew.kickoff_async(inputs=...) -> CrewOutput', input: 'Same application-defined input map as kickoff.', output: 'CrewOutput.', source: 'https://docs.crewai.com/en/concepts/crews' },
    ],
    constraints: ['`kickoff` runs the Crew’s configured plan; it is not a universal remote run API.', 'A server wrapper and lifecycle/error mapping are needed for UI-driven jobs.'],
  },
  {
    id: 'hermes',
    name: 'Hermes Agent',
    repository: 'https://github.com/NousResearch/hermes-agent',
    revision: 'main @ 2026-09-12 (history head bf867d3; full hash unavailable in source fetch)',
    license: 'MIT',
    runtime: 'Python CLI or optional HTTP API server started by `hermes gateway`.',
    surface: 'native-api',
    dependencies: ['Hermes Agent installation', 'configured model provider', 'optional configured tools/tool backends'],
    launch: '`hermes gateway` after enabling the API server in Hermes config/environment.',
    auth: 'API server requires `API_SERVER_KEY`; send `Authorization: Bearer <key>`. Default host is loopback (127.0.0.1).',
    interfaces: [
      { name: 'OpenAI-compatible completion', signature: 'POST /v1/chat/completions', input: 'OpenAI Chat Completions JSON with `model` and `messages`; stateless full conversation.', output: 'OpenAI-compatible completion response; streaming is SSE.', source: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md' },
      { name: 'Session chat stream', signature: 'POST /api/sessions/{id}/chat/stream', input: 'JSON `{ input: string }` (other documented session options may apply).', output: 'Server-sent event stream with response and tool progress.', source: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md' },
      { name: 'Run status/cancel', signature: 'GET /v1/runs/{run_id}; POST /v1/runs/{run_id}/stop', input: 'Run ID in path; bearer key required.', output: 'Run lifecycle record / stop response per API server.', source: 'https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md' },
    ],
    constraints: ['The API server can expose powerful tools including terminal execution; keep it bound to trusted interfaces and protect the key.', 'Model and tool provider configuration remains external to this application.'],
  },
  {
    id: 'openmanus',
    name: 'OpenManus',
    repository: 'https://github.com/FoundationAgents/OpenManus',
    revision: 'main observed 2026-09-27; exact full HEAD SHA not exposed by primary repository fetch',
    license: 'MIT',
    runtime: 'Python command-line application with separate MCP entry point.',
    surface: 'harness-plugin',
    dependencies: ['OpenManus requirements', 'configured LLM provider/API key', 'optional Browser Use and browser runtime'],
    launch: '`python main.py` for interactive CLI; `python run_mcp.py` for its MCP mode.',
    auth: 'LLM provider credentials in `config/config.toml`; no generic HTTP auth contract in the documented CLI/MCP startup.',
    interfaces: [
      { name: 'Interactive runner', signature: 'python main.py', input: 'User idea entered through terminal interaction.', output: 'Agent response and tool actions in the CLI session.', source: 'https://github.com/FoundationAgents/OpenManus/blob/main/README.md' },
      { name: 'MCP runner', signature: 'python run_mcp.py', input: 'MCP client tool calls according to registered server tools.', output: 'MCP protocol results; tool catalog and schemas depend on the selected runner/configuration.', source: 'https://github.com/FoundationAgents/OpenManus/blob/main/README.md' },
    ],
    constraints: ['No stable generic REST launch/status/cancel contract was found in the upstream README.', 'The README describes multi-agent flow mode as unstable.', 'MCP is a harness protocol and needs a separately managed process and transport.'],
  },
  {
    id: 'understand-anything',
    name: 'Understand Anything',
    repository: 'https://github.com/Egonex-AI/Understand-Anything',
    revision: '5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc (main, 2026-09-08)',
    license: 'MIT',
    runtime: 'Coding-agent plugin/skills; optional Node.js viewer for a previously generated local graph.',
    surface: 'harness-plugin',
    dependencies: ['Compatible coding-agent host for analysis plugin', 'Node.js >=18 for standalone viewer; pnpm >=10 to build from source'],
    launch: 'Agent workflow uses `/understand` in supported hosts. Standalone viewer: `npx https://github.com/Egonex-AI/Understand-Anything/releases/latest/download/understand-anything-viewer.tgz /path/to/project`.',
    auth: 'Viewer serves local files; README says viewer does not make LLM calls. The analysis workflow uses the configured host/model credentials.',
    interfaces: [
      { name: 'Generated graph artifact', signature: 'Read `.ua/knowledge-graph.json` (legacy `.understand-anything/` may be selected).', input: 'Prior `/understand` analysis in a compatible agent host.', output: 'JSON with `project`, `nodes[]`, and graph metadata including analyzed commit.', source: 'https://github.com/Egonex-AI/Understand-Anything/blob/main/README.md' },
      { name: 'Local viewer', signature: 'npx understand-anything-viewer.tgz <project-path>', input: 'Project directory containing `.ua/` or legacy `.understand-anything/` graph artifact.', output: 'Tokenized local viewer URL; read-only dashboard.', source: 'https://github.com/Egonex-AI/Understand-Anything/blob/main/README.md' },
    ],
    constraints: ['The scanner is driven by agent-host skills/plugin commands, not a general callable HTTP API.', 'The standalone viewer consumes an existing graph and does not perform analysis.', 'The separate ua-mcp project is not part of this repository and cannot be attributed as its native API.'],
  },
  {
    id: 'graph-rag-kernel',
    name: 'Graph RAG NP-Hard Kernel',
    repository: 'https://github.com/AAH20/graph-rag-np-hard-kernel',
    revision: '35b1bb93a04d419fc1167480d93a1eed711fb711',
    license: 'Apache-2.0',
    runtime: 'Python >=3.10; package declares no runtime dependencies.',
    surface: 'needs-adapter',
    dependencies: [],
    launch: 'Local library: instantiate `GraphRAGNPHardEngine` and call a solver; project also declares an `graph-rag-kernel` CLI for benchmarks.',
    auth: 'None in the local library interface.',
    interfaces: [
      { name: 'Steiner subgraph', signature: 'GraphRAGNPHardEngine.extract_steiner_subgraph(nodes: list[GraphNode], edges: list[GraphEdge], root_seed_id: str | None = None) -> SteinerTreeResult', input: 'Typed GraphNode/GraphEdge collections and optional seed ID.', output: 'SteinerTreeResult dataclass.', source: 'https://github.com/AAH20/graph-rag-np-hard-kernel/blob/35b1bb93a04d419fc1167480d93a1eed711fb711/graph_rag_np_hard_kernel/engine.py' },
      { name: 'Community detection', signature: 'GraphRAGNPHardEngine.detect_communities_modularity(nodes: list[str], edges: list[tuple[str, str, float]], gamma: float = 1.0) -> CommunityPartitionResult', input: 'Node IDs and weighted edge triples.', output: 'CommunityPartitionResult dataclass.', source: 'https://github.com/AAH20/graph-rag-np-hard-kernel/blob/35b1bb93a04d419fc1167480d93a1eed711fb711/graph_rag_np_hard_kernel/engine.py' },
      { name: 'Submodular graph summary', signature: 'GraphRAGNPHardEngine.summarize_graph_submodular(units: list[KnowledgeUnit], token_budget: int = 4000) -> SubmodularSummaryResult', input: 'KnowledgeUnit records and token budget.', output: 'SubmodularSummaryResult dataclass.', source: 'https://github.com/AAH20/graph-rag-np-hard-kernel/blob/35b1bb93a04d419fc1167480d93a1eed711fb711/graph_rag_np_hard_kernel/engine.py' },
    ],
    constraints: ['Python objects must be constructed from the declared package dataclasses; JSON transport requires an adapter.', 'No HTTP launch, job status, or cancel API is present in the inspected engine.'],
  },
  {
    id: 'agentic-kernel',
    name: 'Agentic NP-Hard Kernel',
    repository: 'https://github.com/AAH20/agentic-np-hard-kernel',
    revision: 'ad8e99faa20c414b60d86b8ec211863c003535fc',
    license: 'Apache-2.0',
    runtime: 'Python >=3.10; package declares no runtime dependencies.',
    surface: 'needs-adapter',
    dependencies: [],
    launch: 'Local library: instantiate `AgenticNPHardEngine` and call solver methods; project also declares a benchmark CLI.',
    auth: 'None in the local library interface.',
    interfaces: [
      { name: 'Tool routing', signature: 'AgenticNPHardEngine.route_tools(tool_inventory: list[ToolDefinition], max_latency_ms: float = 500.0, max_token_budget: int = 4000) -> ToolRoutingResult', input: 'ToolDefinition records with utility, latency, token cost, and prerequisite fields.', output: 'ToolRoutingResult with selected tools and aggregate utility/latency/token cost.', source: 'https://github.com/AAH20/agentic-np-hard-kernel/blob/ad8e99faa20c414b60d86b8ec211863c003535fc/agentic_np_hard_kernel/engine.py' },
      { name: 'Workflow DAG synthesis', signature: 'AgenticNPHardEngine.synthesize_workflow_dag(tasks: list[SubTask]) -> WorkflowDAGResult', input: 'SubTask records with IDs, durations, dependencies, and roles.', output: 'WorkflowDAGResult with schedule, critical path, makespan, and parallelism factor.', source: 'https://github.com/AAH20/agentic-np-hard-kernel/blob/ad8e99faa20c414b60d86b8ec211863c003535fc/agentic_np_hard_kernel/engine.py' },
      { name: 'Submodular memory retrieval', signature: 'AgenticNPHardEngine.retrieve_submodular_memory(memory_pool: list[AgentMemoryRecord], k_records: int = 5, diversity_penalty: float = 0.35) -> SubmodularMemoryResult', input: 'Memory records, top-k count, and diversity penalty.', output: 'SubmodularMemoryResult dataclass.', source: 'https://github.com/AAH20/agentic-np-hard-kernel/blob/ad8e99faa20c414b60d86b8ec211863c003535fc/agentic_np_hard_kernel/engine.py' },
    ],
    constraints: ['Solver data are package dataclasses and require input/output serialization for HTTP integration.', 'No HTTP launch, job status, or cancel API is present in the inspected engine.'],
  },
  {
    id: 'mirofish-optimizer',
    name: 'MiroFish Swarm Optimizer',
    repository: 'https://github.com/AAH20/mirofish-swarm-optimizer',
    revision: 'd2a3df25cf80750fadd562373f7941b9cb8db2f1',
    license: 'Apache-2.0',
    runtime: 'Python >=3.10; package declares no runtime dependencies.',
    surface: 'needs-adapter',
    dependencies: [],
    launch: 'Local library: instantiate `MiroFishSwarmEngine` and call optimizer methods; project also declares benchmark CLI.',
    auth: 'None in the local library interface.',
    interfaces: [
      { name: 'Influence maximization', signature: 'MiroFishSwarmEngine.solve_critical_influence(agents: list[SwarmAgent], network: dict[str, list[tuple[str, float]]], k_seeds: int = 3) -> InfluenceResult', input: 'SwarmAgent dataclasses, adjacency mapping from agent IDs to neighbor/weight pairs, and seed count.', output: 'InfluenceResult dataclass.', source: 'https://github.com/AAH20/mirofish-swarm-optimizer/blob/d2a3df25cf80750fadd562373f7941b9cb8db2f1/mirofish_swarm_optimizer/engine.py' },
      { name: 'Attention knapsack', signature: 'MiroFishSwarmEngine.allocate_attention_knapsack(agents: list[SwarmAgent], token_budget: int = 5000) -> AttentionAllocationResult', input: 'SwarmAgent dataclasses and token budget.', output: 'AttentionAllocationResult dataclass.', source: 'https://github.com/AAH20/mirofish-swarm-optimizer/blob/d2a3df25cf80750fadd562373f7941b9cb8db2f1/mirofish_swarm_optimizer/engine.py' },
      { name: 'Disjunctive scheduling', signature: 'MiroFishSwarmEngine.schedule_disjunctive_events(tasks: list[TaskActivity], num_workers: int = 4) -> ScheduleResult', input: 'TaskActivity records and worker count.', output: 'ScheduleResult dataclass.', source: 'https://github.com/AAH20/mirofish-swarm-optimizer/blob/d2a3df25cf80750fadd562373f7941b9cb8db2f1/mirofish_swarm_optimizer/engine.py' },
    ],
    constraints: ['Solver input and output are Python dataclasses/dicts; no HTTP transport is included.', 'No HTTP launch, job status, or cancel API is present in the inspected engine.'],
  },
  {
    id: 'graph-swarm-kernel',
    name: 'Agentic Graph Swarm Kernel',
    repository: 'https://github.com/AAH20/agentic-graph-swarm-kernel',
    revision: 'd429ee702e0e9b59b68f3714723a4f1d4bc425c8',
    license: 'Apache-2.0',
    runtime: 'Python >=3.10; package declares no runtime dependencies.',
    surface: 'needs-adapter',
    dependencies: [],
    launch: 'Local library: `AgenticGraphSwarmEngine` exposes the core solver functions as static methods; benchmark CLI is a separate interface.',
    auth: 'None in the local library interface.',
    interfaces: [
      { name: 'Hypergraph coalition structure', signature: 'AgenticGraphSwarmEngine.solve_csg(agents: list[AgentProfile], hyperedges: list[KnowledgeHyperedge]) -> HypergraphCSGResult', input: 'Agent capabilities/efficiency and knowledge hyperedges.', output: 'HypergraphCSGResult dataclass.', source: 'https://github.com/AAH20/agentic-graph-swarm-kernel/blob/d429ee702e0e9b59b68f3714723a4f1d4bc425c8/agentic_graph_swarm_kernel/engine.py' },
      { name: 'Causal DAG synthesis', signature: 'AgenticGraphSwarmEngine.solve_causal_dag(variables: list[VariableObservation], max_in_degree: int = 3) -> CausalDAGResult', input: 'Variable observations with named time-series values and in-degree bound.', output: 'CausalDAGResult dataclass.', source: 'https://github.com/AAH20/agentic-graph-swarm-kernel/blob/d429ee702e0e9b59b68f3714723a4f1d4bc425c8/agentic_graph_swarm_kernel/engine.py' },
      { name: 'Tool scheduling', signature: 'AgenticGraphSwarmEngine.solve_tool_scheduler(tasks: list[AgentToolTask], resources: list[ToolResource]) -> DisjunctiveToolScheduleResult', input: 'Agent tool tasks with durations/prerequisites and resource capacities.', output: 'DisjunctiveToolScheduleResult dataclass.', source: 'https://github.com/AAH20/agentic-graph-swarm-kernel/blob/d429ee702e0e9b59b68f3714723a4f1d4bc425c8/agentic_graph_swarm_kernel/engine.py' },
    ],
    constraints: ['This repo exposes ten pure solver functions through one Python engine; they are not remote agents or a simulation service.', 'Dataclass serialization, worker isolation, job state, and cancellation would be host responsibilities.'],
  },
];

export function getIntegration(id: string): IntegrationSource | undefined {
  return integrationCatalog.find((integration) => integration.id === id);
}

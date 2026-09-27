# Integration source audit

Checked 2026-09-27 against the upstream documentation and repository files linked below. This catalog is a reference map, not a claim that this app has integrated, installed, or executed any upstream system. Re-check links and pinned revisions before using an upstream runtime; its defaults and APIs can change.

## Surface classification

`native-api` means an upstream HTTP interface is documented. `local-command` means the repo has a documented executable CLI. `harness-plugin` means it is exposed through an agent host/plugin/MCP interface. `needs-adapter` means only an in-process API or app-specific components were verified, so the optional web app would need a bridge before invoking it. These labels describe upstream surfaces, not their security readiness.

| ID | Upstream / observed revision | License | Surface | Relevant dependencies and launch |
| --- | --- | --- | --- | --- |
| `cognee` | [topoteretes/cognee](https://github.com/topoteretes/cognee), main history head `e93a4f0` (2026-09-06; complete hash could not be read from the fetched source page) | Apache-2.0 | Native API | Python service or SDK; LLM, embedding, and storage providers. Self-host via documented Docker command. |
| `mirofish` | [666ghj/MiroFish](https://github.com/666ghj/MiroFish), `39d849138ef254f6c737ab4c4705e5545dbe31d4` | MIT | Native API | Flask, model provider, Zep, simulation dependencies. Backend defaults to port 5001 per upstream project docs. |
| `langgraph` | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph), official API docs checked 2026-09-27; main SHA was not exposed by the fetched history page | MIT | Needs adapter | Python/JS library, app-authored graph/state/nodes; optional checkpointer, model, tools. `CompiledStateGraph.invoke(input, config)` is local execution. |
| `crewai` | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI), main history head `e1f3c4b` (2026-09-11; complete hash could not be read from fetched source page) | MIT | Needs adapter | Python package, app-authored Crew/agents/tasks/tools, configured model provider; call `Crew.kickoff(inputs=...)`. |
| `hermes` | [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), API-server source docs checked 2026-09-27; history snapshot `bf867d3` (2026-09-12) | MIT | Native API | Python install and configured model/tool backends; `hermes gateway` starts optional API server. |
| `openmanus` | [FoundationAgents/OpenManus](https://github.com/FoundationAgents/OpenManus), README checked 2026-09-27; fetched primary source did not expose a full HEAD SHA | MIT | Harness plugin | Python package requirements and model credentials; README documents `python main.py` and MCP mode. Current file listing and README differ on MCP runner filename; check a pinned checkout. |
| `understand-anything` | [Egonex-AI/Understand-Anything](https://github.com/Egonex-AI/Understand-Anything), `5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc` | MIT | Harness plugin | Agent host for graph generation. Node.js >=18 for the read-only viewer, which consumes existing `.ua/knowledge-graph.json`. |
| `graph-rag-kernel` | [AAH20/graph-rag-np-hard-kernel](https://github.com/AAH20/graph-rag-np-hard-kernel), `35b1bb93a04d419fc1167480d93a1eed711fb711` | Apache-2.0 | Needs adapter | Python >=3.10; zero declared package dependencies; local `GraphRAGNPHardEngine`. |
| `agentic-kernel` | [AAH20/agentic-np-hard-kernel](https://github.com/AAH20/agentic-np-hard-kernel), `ad8e99faa20c414b60d86b8ec211863c003535fc` | Apache-2.0 | Needs adapter | Python >=3.10; zero declared package dependencies; local `AgenticNPHardEngine`. |
| `mirofish-optimizer` | [AAH20/mirofish-swarm-optimizer](https://github.com/AAH20/mirofish-swarm-optimizer), `d2a3df25cf80750fadd562373f7941b9cb8db2f1` | Apache-2.0 | Needs adapter | Python >=3.10; zero declared package dependencies; local `MiroFishSwarmEngine`. |
| `graph-swarm-kernel` | [AAH20/agentic-graph-swarm-kernel](https://github.com/AAH20/agentic-graph-swarm-kernel), `d429ee702e0e9b59b68f3714723a4f1d4bc425c8` | Apache-2.0 | Needs adapter | Python >=3.10; zero declared package dependencies; local `AgenticGraphSwarmEngine`. |

The four AAH20 revisions were inspected from shallow, read-only clones and package metadata; no fetched code was run. Their `pyproject.toml` files declare Python >=3.10, no runtime dependencies, and Apache-2.0. The package facade methods accept package dataclasses and return dataclasses; to use them over HTTP, a host must define JSON DTOs, validation, process/job lifetime, serialization, status, timeout, and cancellation behavior. The upstream engine files inspected do not expose an HTTP run/status/cancel API.

## Callable contracts and limits

### Cognee

The documented lifecycle is `POST /api/v1/add`, `POST /api/v1/cognify`, and `POST /api/v1/search`. `add` uses multipart file/text data and `datasetName`; `cognify` accepts a JSON body with `datasets`, `run_in_background`, and optional `chunks_per_batch`; `search` accepts `query`, `search_type`, optional `datasets`, and `top_k`, returning JSON results. Cognee Cloud requires `X-Api-Key`; local authentication can be disabled, or enabled with `REQUIRE_AUTHENTICATION=true`. The upstream API docs caution that advanced Python search options are not all accepted by HTTP. [API overview](https://docs.cognee.ai/api-reference/introduction), [official API client](https://github.com/topoteretes/cognee/blob/main/cognee/cli/api_client.py).

### MiroFish

The Flask route module documents a multi-step project workflow. `POST /api/simulation/create` requires `project_id`, accepts optional `graph_id`, `enable_twitter`, and `enable_reddit`, and returns an envelope with the `simulation_id`. `POST /api/simulation/prepare` takes a `simulation_id` plus optional entity/profile controls and returns a task ID when work starts; the module points to a status endpoint for the asynchronous task. Run control routes start/stop simulation processes and expose a run-status GET endpoint. Report generation is another asynchronous model-backed path. No authentication decorator/contract was found in the inspected route modules; that is an integration risk, not evidence of safe unauthenticated deployment. [Simulation routes at pinned commit](https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/app/api/simulation.py), [report routes](https://github.com/666ghj/MiroFish/blob/39d849138ef254f6c737ab4c4705e5545dbe31d4/backend/app/api/report.py).

### LangGraph and CrewAI

LangGraph's core call is `compiled_graph.invoke(input, config?) -> output`; state schema and output shape are authored per graph. `StateGraph(...).compile()` creates the graph. A remote Agent Server is an optional additional product/deployment, not an HTTP API implied by importing the core package. [Official graph API source](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/graph-api.mdx).

CrewAI's Python path is `crew.kickoff(inputs={...}) -> CrewOutput`; the map fills placeholders in app-defined crew configuration and tasks. Neither the call nor `CrewOutput` supplies a generic web-service protocol. [CrewAI example](https://github.com/crewAIInc/crewAI/blob/main/docs/v1.10.1/en/concepts/agents.mdx).

### Hermes Agent and OpenManus

Hermes can optionally run an OpenAI-compatible server using `hermes gateway`. Its docs show `POST /v1/chat/completions` with `model` and `messages`, and session-stream requests with `{input}`; API routes are gated by `API_SERVER_KEY` as a bearer token. The API server can grant access to terminal and file tools, so keep it private and use a dedicated key. [Official API-server docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md).

OpenManus's README describes `python main.py` as a terminal interaction and `python run_mcp.py` as MCP mode. This is a local/harness launch, not a documented generic REST API. A GitHub tree page fetched during this audit lists `run_mcp_server.py`, so the MCP filename must be resolved against a pinned checkout before automating. The README says its multi-agent flow mode is unstable. [Official README](https://github.com/FoundationAgents/OpenManus/blob/main/README.md).

### Understand Anything

Understand Anything is an agent-host plugin/skill workflow for analysis and graph generation. The output schema documented by its plugin includes project metadata and nodes; its standalone Node viewer reads an existing `.ua/knowledge-graph.json` (or legacy `.understand-anything`) graph. The viewer is read-only and does not perform the analysis. A separate `ua-mcp` repository exists; its tools are not native endpoints of this scanner and require the graph artifact first. [Official README](https://github.com/Egonex-AI/Understand-Anything/blob/5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc/README.md), [separate MCP project prerequisite](https://github.com/uamcp/Understand-Anything-MCP).

### AAH20 callable kernels

The methods listed in [`integration-catalog.ts`](../apps/web/lib/integration-catalog.ts) are from the pinned `engine.py` files and the `core/models.py` declarations. Representative exact method contracts are:

- `GraphRAGNPHardEngine.extract_steiner_subgraph(nodes: list[GraphNode], edges: list[GraphEdge], root_seed_id: str | None) -> SteinerTreeResult`; `detect_communities_modularity(nodes, weighted_edges, gamma) -> CommunityPartitionResult`; `summarize_graph_submodular(units, token_budget) -> SubmodularSummaryResult`.
- `AgenticNPHardEngine.route_tools(tool_inventory, max_latency_ms, max_token_budget) -> ToolRoutingResult`; `synthesize_workflow_dag(tasks) -> WorkflowDAGResult`; `retrieve_submodular_memory(memory_pool, k_records, diversity_penalty) -> SubmodularMemoryResult`.
- `MiroFishSwarmEngine.solve_critical_influence(agents, network, k_seeds) -> InfluenceResult`; `allocate_attention_knapsack(agents, token_budget) -> AttentionAllocationResult`; `schedule_disjunctive_events(tasks, num_workers) -> ScheduleResult`.
- `AgenticGraphSwarmEngine.solve_csg(agents, hyperedges) -> HypergraphCSGResult`; `solve_causal_dag(variables, max_in_degree) -> CausalDAGResult`; `solve_tool_scheduler(tasks, resources) -> DisjunctiveToolScheduleResult`.

These callable optimization routines return results; they do not themselves execute chosen tools, run a multi-agent simulation, expose network APIs, or prove superiority over a workload-specific baseline. Their claims and benchmark names are not performance evidence. Any product integration must provide its own fixtures, measurement methodology, resource limits, and independent validation.

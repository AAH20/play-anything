# Optional Next.js Graph Studio

The optional app lives in `apps/web`. The existing Python CLI, dashboard, and Creator server retain their standard-library-only runtime. JavaScript dependencies belong to this separate frontend and server adapter.

## Run locally

From the repository root:

```sh
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

Open http://127.0.0.1:3000 for Graph Studio and `/creator` for the Creator Studio shell. The asset preparation step builds a repository snapshot and copies the existing Creator assets. Its **Understand the Repo** graph is replaced in the copied page with the new explorer. The original Python dashboard remains usable.

The copied Creator is a static workbench: live repository cloning and analysis still require the local Python Creator server. Export a graph there and import it in Graph Studio. The same-origin embedded graph also receives repository walkthrough snapshots through an origin-checked parent/iframe bridge. No arbitrary repository code is executed by graph inspection.

## What is implemented

- Sigma/WebGL navigation, grouped layout and background ForceAtlas2 layout, camera controls, node inspection, source locations and summaries.
- Module, file, symbol and neighborhood views; relationship, evidence, directory and text filters; directed semantic dependency paths; a keyboard-accessible node list.
- Explicit source coverage, inferred/unresolved references, truncation and rendering limits. Visual proximity is not evidence of a dependency.
- Three deterministic browser-worker specialists: structure, dependencies and evidence. A coordinator reconciles their findings. Concurrency, timeout, cancellation, status and report export are visible. These workers do not call a language model.
- Optional server-side language-model review and a three-agent model team: two independent reviewers run concurrently, followed by a critic that preserves agreements and disagreements. Graph tools, validated node references, execution budgets, cancellation and usage reporting are included. Configuration and explicit invocation are required.
- Optional Neo4j save/load, separate from the downloadable Cypher import bundle.

## Optional model configuration

Copy `.env.example` to `.env.local` inside `apps/web` and configure `AI_GATEWAY_API_KEY`, `GRAPH_REVIEW_MODEL`, and `GRAPH_REVIEW_ACCESS_TOKEN`. Restart the dev server. Enter the private workspace access token in the model panel when requesting a review; the UI retains it in memory only. Provider credentials are server-only and must never use a `NEXT_PUBLIC_` prefix.

The team has a 45-second deadline, two concurrent specialist invocations, then one critic invocation. Each invocation allows three steps of up to 600 output tokens: a 5,400-token planned generation budget, separate from input/tool costs and any provider-specific accounting. Single review allows up to four steps with the selected per-step token cap.

Model output is a suggestion even when its node IDs exist. Citation validation establishes that a reference belongs to the submitted graph; it cannot prove a model's interpretation. Actual cost depends on the chosen provider/model, input, output and tool-loop steps. Token limits per generation do not mean a dollar spending cap. Configure provider budgets separately. No provider is called by the default local worker analysis.

## Optional Neo4j configuration

First apply `docs/neo4j-store-setup.cypher` once with a database administrator/schema account. Its uniqueness constraints provide indexed identity and safe concurrent saves. Use a separate read/write application account for normal requests.

Configure these server values in the same environment file:

```dotenv
NEO4J_URI=http://127.0.0.1:7474
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-private-password
NEO4J_DATABASE=neo4j
GRAPH_STORE_NAMESPACE=play-anything
GRAPH_STORE_ACCESS_TOKEN=your-private-workspace-token
```

`NEO4J_URI` is the HTTP(S) origin exposing Neo4j Query API v2, **not** a Bolt or `neo4j+s://` URI. Use TLS for remote connections. The server fixes the namespace, database, query and destination; callers cannot submit arbitrary Cypher or choose another namespace. Enter the workspace token in **Neo4j graph storage**, then explicitly save or load.

The adapter stores a versioned snapshot plus queryable nodes and relationships. Saves publish an active revision only after the revision's data is written. A browser loads that revision as an in-memory snapshot; database changes are not streamed into the canvas. Revisions are retained, so deployment owners must plan retention and storage capacity. A failed or cancelled request can leave an inactive revision; cancellation cannot undo an already committed save.

Graph storage is bounded to 2 MiB serialized snapshots, 20,000 nodes and 80,000 edges with a 20-second request budget. Browser import is separately bounded to 15 MB, 25,000 nodes and 100,000 edges. These are protective caps, not benchmark claims that all such graphs fit every deployment or device.

The bearer-token adapters are for a trusted private workspace. They are not tenant identity, subscription authorization, or an Internet-facing multi-user security design. A public SaaS deployment needs session-based tenant authorization, per-tenant namespaces, rate limits, quotas and audit retention before exposing billed or persistent operations.

## Optional integrations and local kernels

`/api/integrations` exposes a non-secret capability registry. To enable an integration, set its server-only values from `.env.example`, restart the Next.js server, then enter `INTEGRATION_ACCESS_TOKEN` in the integration panel. Only explicit Run actions create jobs. Start and job status/cancel requests require the bearer token and a matching browser origin. Requests are limited to 2 MiB; the process-local queue runs at most two jobs concurrently, holds at most 12 queued jobs, applies a 45-second deadline and caps serialized results at 1 MiB. Job state is in memory and is lost on process restart; it is not durable across serverless instances.

OpenRouter uses its fixed API origin and server-selected model. vLLM uses a server-configured HTTPS OpenAI-compatible URL, allowing HTTP only for loopback development. The direct review sends one bounded structured request; delegate runs two specialists in parallel followed by a critic. Graph citation IDs are checked against the submitted snapshot and actual usage is reported when the provider returns it. Token limits are generation limits, not a dollar cap.

Cognee operations explicitly add a selected graph to the configured dataset, run `cognify` against that dataset, or search that dataset. A background acknowledgment means the upstream task started; this app does not claim downstream completion without a status API. MiroFish operates on an existing prepared simulation ID and exposes the upstream process-stop action as a separate explicit operation. LangGraph reports remote thread/run IDs for status or cancellation. CrewAI reports kickoff IDs for status; its verified adapter does not claim cancellation. Hermes API uses its configured OpenAI-compatible endpoint. Framework credentials and deployment URLs stay on the server. OpenManus and UnderstandAnything require a server-enabled local runner profile.

The four AAH20 graph kernels run as local Python 3.10+ engines with no pip dependencies. Configure their repository-root variables only for the reviewed source copies and adjacent `sources.json` revision manifest in `.integration-sources/`. The adapters call fixed engine methods and pass the complete selected graph only when it fits the explicit caps (500 nodes, 5,000 edges); oversized inputs are rejected rather than silently truncated. The comparison suite records each solver's source revision, execution time, assumptions and input counts. It is a comparative diagnostic, not a universal optimizer or proof that one solver is superior. Cyclic workflow inputs are rejected before the upstream scheduler, whose fallback does not safely validate cycles.

The optional local runner bridge uses fixed server-enabled command profiles and a separate bridge token. It does not accept browser commands or executable paths. `subscription` selects a locally authenticated CLI profile; it is not an API key or unlimited API entitlement. The bridge is not auto-started, and an unset or disabled profile remains unavailable.

## Rendering and language boundaries

At most 1,800 nodes and 12,000 edges are drawn per filtered view. The UI reports omitted matches and preserves the complete imported snapshot for exports. On WebGL failure, a selectable SVG fallback shows at most 200 nodes and 600 links with a visible truncation notice. Force layout runs in a worker with a three-second computation budget. Dense edge sets, browser GPU capacity, reduced-motion preferences and WebGL availability affect the experience. There is no hard real-time guarantee; use the included benchmark and browser checks on target hardware before setting latency commitments.

Python relationships use the repository's AST analyzer. JavaScript/TypeScript relationships remain lexical hints. Rust, Go and C++ are inventoried as files; compiler-backed symbol resolution and native acceleration remain subsequent, benchmark-gated migration phases. Adding three runtimes does not itself eliminate UI latency. See `nextjs-graph-native-migration.md` for the staged architecture.

## Deployment boundary

The repository-root Vercel/Cloudflare configuration continues to build the static Python-generated site. It does not automatically deploy this Next.js app. Deploy `apps/web` as a separate Next.js project, make the repository files outside that root available to `scripts/prepare-assets.mjs`, and provide Python 3.10+ during asset preparation (or pre-generate the allowlisted assets in CI). Store secrets in the deployment's server environment.

The model and graph-store routes require a Node-capable runtime; a plain static export cannot serve them. A Cloudflare Next.js runtime adapter needs its own compatibility verification before these routes are deployed there. Supabase plan storage remains in the existing Creator integration; it does not replace Neo4j or automatically authenticate these new private-workspace endpoints. Hosted services are not provisioned by running this app.

## Verification

```sh
python3 -m unittest discover tests
npm --prefix apps/web run test
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Browser verification must cover graph load, filters, node selection, local specialist completion/cancellation, layout changes, Creator embedding, mobile overflow and console errors. Optional database and model connectivity require separately configured services; mocked contract tests alone do not establish live connectivity.

# Graph Studio: frameworks, kernels and harnesses

Graph Studio now separates graph exploration, tool execution and business assumptions. Expand the graph with the fullscreen button beside search; Escape returns to the workspace. Browsers without native fullscreen use an expanded page view. Creator Studio's embedded graph supports the same control.

## Local quick start

```sh
python3 scripts/setup_integration_kernels.py --write-env
npm --prefix apps/web run dev
```

Open `http://127.0.0.1:3000/graph#integrations`. The setup command downloads only the four AAH20 repositories and exact revisions in `integrations/kernel-sources.json`; it does not execute them or install dependencies. Existing checkouts and environment values are preserved. `--check` is read-only. Local copies and `.env.local` are ignored by Git.

In the private local workspace, copy `INTEGRATION_ACCESS_TOKEN` from `apps/web/.env.local` into the execution panel's password field. It stays in browser memory and is excluded from exported plans. This is the app's execution token, not a provider API key. The generated local configuration enables the four original kernels; it contains no paid provider credentials.

Choose a kernel or the combined diagnostic suite, an operation, and repository scope. **Current filtered graph view** is the default: it uses exactly the selected module/file/symbol view, including its omissions. Choose **Full repository snapshot** only if it fits the operation's limits. A filtered view is explicitly marked partial and cannot establish whole-repository guarantees.

## What the four original projects contribute

| Project | Callable contribution | Interpretation |
| --- | --- | --- |
| `graph-rag-np-hard-kernel` | Graph partitioning / retrieval subgraph algorithms | Bounded graph optimization; objective and input assumptions matter. |
| `agentic-np-hard-kernel` | Workflow DAG synthesis | Dependencies require validation; a repository graph is not automatically an executable workflow. |
| `mirofish-swarm-optimizer` | Influence selection / consensus algorithms | Simulation assumptions and the selected objective limit the result. |
| `agentic-graph-swarm-kernel` | Graph/swarm solver interfaces | Upstream certification claims must be independently checked. |

The combined suite calls the original implementations on the same bounded snapshot and returns separate diagnostics and timings. Their objective scores measure different things and must not be ranked against one another as a common quality score. Source pins and licenses are retained. See [source audit](integration-source-audit.md) and [capability matrix](kernel-capability-matrix.md) for the supported contracts and limitations.

## External frameworks

The integration registry reports configuration independently of source availability. A source link or installed plugin does not mean a service is running. Native HTTP adapters use server-configured destinations and credentials; local CLI/plugin integrations use explicitly configured runner profiles.

- Cognee operations use its documented GraphRAG service interface. Dataset operations must distinguish existing data from newly ingested repository evidence.
- MiroFish operations target explicit project/simulation identifiers. Existing results must not be reset implicitly.
- LangGraph operates against a separately deployed graph service and its assistant/thread identifiers.
- CrewAI service operations target an existing deployment. Open-source CrewAI installed locally is not automatically that deployment API.
- Hermes can use its authenticated OpenAI-compatible API, or an explicitly configured local harness profile.
- OpenManus uses its installed local application through a runner profile.
- Understand Anything uses an installed compatible harness plugin. Its viewer displays an existing graph; opening the viewer does not perform repository analysis.

A completed HTTP submission is not a completed remote workflow. Operations that submit remote work return the remote identifiers and require the corresponding status operation. Cancellation support is adapter-specific; stopping local tracking does not guarantee remote tools stopped.

## Harnesses and authentication

The selector includes Codex, Claude Code, Cursor, Antigravity, OpenCode and Hermes. See [harness billing sources](harness-costs.md) for verified authentication modes. Selection applies to local harness runs and exported plans. External frameworks keep their own model configuration.

Subscriptions are used through supported authenticated clients. They are not generic API credentials, unlimited quotas, or permission to reuse another product's authentication. API usage requires the provider's supported key or endpoint. Manual products remain manual unless a supported runner profile is explicitly configured.

The optional [local runner](local-harness-runner.md) fixes each profile's command, working directory and authentication mode on the server. Browser requests supply a goal and allowlisted identifiers, never arbitrary shell commands or executable paths. Profiles are disabled until configured. The runner's time/output/concurrency limits do not create an OS security sandbox; run tool-enabled harnesses in the workspace/container appropriate to their permissions.

## OpenRouter, vLLM and economics

Direct inference supports a single review or bounded delegation: independent specialists followed by critic synthesis. API credentials and model identifiers remain server-side. vLLM requires an already running compatible inference endpoint; choosing it does not provision a GPU.

The economics panel exposes its assumptions: input/output/cache tokens, fanout, retries, success rate, monthly volume, subscription allocation, GPU usage, fixed costs, revenue and budgets. Dated reference rates are editable. Unknown prices remain unknown. Match the rate card to the actual execution model; a billing scenario does not change provider routing.

Provider-reported token usage describes actual requests, while projections use the entered assumptions. Dollar estimates exclude unentered infrastructure, taxes, discounts and provider-specific tiers. A subscription's allocated monthly cost is distinct from incremental API charges. GPU reserved capacity and consumption assumptions must be accounted for consistently to avoid counting the same spend twice.

Exported execution plans include selections, source references and estimates, never credentials. Importing or sharing a plan does not start execution.

## Operational limits

The current job registry is process-local and expires old jobs. It is suitable for this private local workspace, not durable multi-instance orchestration. Server restarts lose tracking. Hosted multi-user operation requires durable jobs, tenant authorization, scoped credentials, quotas and per-tenant storage before exposing execution publicly. Local Python/CLI adapters cannot run inside a static site export and need an execution host alongside a hosted frontend.

Benchmarking against the upstream projects remains a measured target. Use held-out repositories, fixed versions/seeds, common resource budgets and task-specific quality/latency/cost metrics. The app does not claim that NP-hard problems have been solved generally or that every integrated system has been outperformed.

## Verification

Run `python3 -m unittest discover tests` from the repository root, then `npm --prefix apps/web test` and `npm --prefix apps/web run build`. Runner tests bind only localhost and need local socket permission. They use harmless Python fixtures rather than real agent subscriptions.

With the local preview running and the kernels configured, run `node --import tsx scripts/smoke-kernels.mjs` from `apps/web`. This checks public configuration, rejected unauthorized/foreign-origin requests, all four original kernels, and every result inside the combined suite against the prepared module graph. It reads the workspace token locally without printing it and makes no paid model calls.

Native framework tests mock documented HTTP contracts; they do not establish that your separately deployed services or provider credentials are operational. Configure and verify those services before relying on a live run.

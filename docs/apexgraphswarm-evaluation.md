# ApexGraphSwarm: evaluation and scale plan

Research checked **2026-09-27**. This is an evaluation design, not a report of ApexGraphSwarm results. Every target below is **proposed and unmeasured** unless explicitly marked **measured/published**. Benchmark papers and vendor reports are reference points; none establishes ApexGraphSwarm superiority.

## What Anthropic's “300+ agents” evidence supports

The number needs a scope label:

- **Measured/published, internal activity:** Anthropic's September 2026 AI-R&D measurement says approximately **30,000 agents were doing research and engineering work at any one time on its most-used internal platform, as of August 2026**. It explicitly limits the measure to that platform. This supports an internal active-agent count at that point in time; it does not say these agents formed one swarm or worked on one task. The same page says monitor coverage was 100% for activity on that platform and warns that the measurement picture is incomplete. [Anthropic, “Measurements for understanding the pace of AI development inside frontier labs”](https://www.anthropic.com/institute/measuring-pace-of-ai-development), checked 2026-09-27.
- **Measured/published, product limit:** Anthropic Managed Agents documents a maximum of **25 concurrent session threads** (advisor consultations are exempt), up to 20 unique agent definitions in a coordinator roster, and multiple copies of a roster agent. This is a product/API limit documented on that page, not a cap on Anthropic's internal platform or on other user-built orchestration. [Anthropic Managed Agents multiagent orchestration](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration), checked 2026-09-27.
- **Measured/published, coding case study:** Anthropic's C-compiler project describes **16 agents**, nearly **2,000 Claude Code sessions over time**, and about **$20,000** in API cost. Those are separate quantities: the session count is cumulative and is not 2,000 simultaneous workers. [Anthropic, “Building a C compiler with a team of parallel Claudes”](https://www.anthropic.com/engineering/building-c-compiler), published 2026-02-05.
- **Measured/published, coordination experiments:** Anthropic reports a vulnerability-search swarm of **45 agents**, each on a VM, and a separate 12-hour software-game experiment varying swarm size up to **80 agents**. It observed code-sharing/merge failures for older model configurations and found the finished games poor; results varied by model and setup. These are specific experiments, not a 300-agent general-purpose benchmark. [Anthropic, “Patterns and problems in emerging multiagent systems”](https://www.anthropic.com/research/multiagent-systems), published 2026-08-13.

Therefore, if “300+” means a general public product limit or a demonstrated 300-agent single-task team, the reviewed primary sources do **not** establish that. Anthropic does report 30,000 internal agents active at once, but that does not establish quality, throughput, collaboration, or 300-agent task success for ApexGraphSwarm. Its API's published concurrency limit is a different surface.

Anthropic's other results are also scope-specific: its 2025 Research post reports a **90.2% improvement over a single-agent Opus 4 configuration on its internal research eval**, and about **15× chat token usage** for multi-agent systems. The eval details are not public in that post, and chat is not a rigor-matched single-agent baseline. Treat these as vendor-reported context, not an ApexGraphSwarm target or a directly comparable score. [Anthropic, “How we built our multi-agent research system”](https://www.anthropic.com/engineering/multi-agent-research-system), published 2025-06-13.

## Relevant evaluation benchmarks

| Source | What it measures | Use for ApexGraphSwarm / limitation |
| --- | --- | --- |
| [MultiAgentBench paper](https://arxiv.org/abs/2503.01935), 2025 | Interactive collaboration and competition tasks; milestone/task metrics; star, chain, tree, and graph coordination protocols; discussion and planning strategies. | Closest published multi-agent comparison for graph topology and collaboration. Reuse its task/milestone perspective where licenses and task fit permit; add graph integrity, permissions, conflicts, and system costs. Results from its tasks do not prove repository-engineering quality. |
| [AgentBench paper](https://arxiv.org/abs/2308.03688), ICLR 2024 | Eight multi-turn interactive environments across OS, database, knowledge graph, game, and web tasks. | Good source of environment-grounded agent evaluation patterns and failure taxonomy. Primarily measures agent capability in environments, not large-team concurrency or shared-code coordination. |
| [τ²-Bench paper](https://arxiv.org/abs/2506.07982), 2025 | Dual-control telecom tasks where both user and agent act in a shared dynamic environment; compositional task generation; ablations that distinguish reasoning from communication/coordination errors. | Adapt its state-based, controllable task design to handoffs and operator-agent interactions. Its user simulator is not a swarm of coding agents. |
| [τ^τ-Bench paper](https://arxiv.org/abs/2609.04611), 2026 | End-to-end agent construction from business records, client requirements, APIs, inherited code, and serving-cost constraints; grades deployed agents on held-out simulated traffic. | Useful for evaluating whether ApexGraphSwarm can produce a deployable artifact under requirements and cost limits, rather than reward self-authored tests. It evaluates construction agents, not 300-worker scaling. |
| [Anthropic multiagent study](https://www.anthropic.com/research/multiagent-systems), 2026 | Coordinated vs independent vulnerability search; code-sharing and merge fraction in shared software tasks; conflict/sabotage scenarios. | Directly motivates separate search-diversity, integration-throughput, conflict, and misuse measures. It is an Anthropic study, not a reusable standardized benchmark suite. |
| [Anthropic agent eval design guide](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents), 2026 | Recommends state checks, tool-call constraints where necessary, transcript/latency/token metrics, isolated trials, and deterministic graders where possible. | Apply the grader principles. Avoid scoring only prose or prescribed call sequences; grade final graph/code state and safety constraints. |

## Evaluation protocol

### Immutable run and configuration lineage

Assign each run an immutable `experiment_id` and each configuration a semantic `config_version` plus content hash. Store a manifest containing: orchestrator and worker code commit; graph schema/parser and extractor versions; prompt/system instruction hashes; model/provider/version and sampling settings; tool registry and permission policy; topology, role roster, concurrency cap, retry/timeout/stop rules; task IDs/split; environment image/dependency lock; random seeds; budgets; grader versions; and source snapshot hash. Record all tool calls, handoffs, retries, state mutations, worker lifetimes, and costs against that run. Never edit a result in place after seeing a score: publish a new config version and retain the prior run.

For every candidate, use a short smoke/canary stage, then a preregistered batch. Promote only after independent held-out tasks pass the same acceptance gates. Keep an append-only change log that ties each prompt, topology, algorithm, tool, or budget change to a hypothesis and planned metric. Report failed and canceled trials; do not silently drop them. Keep evaluator/gold artifacts outside agent-readable workspaces and do not let agents modify test harnesses, task labels, or scoring code.

### Tasks, splits, and contamination controls

Construct an evaluation set from tasks that require graph-grounded repository work: locate and explain dependency paths; detect a deliberately seeded relationship defect; change a small feature with tests; propose a migration plan; and integrate parallel, non-overlapping changes. Include tasks with independent subproblems and tasks with shared dependencies so the benchmark does not structurally favor fan-out. Define acceptance criteria and hidden tests before execution. Pair synthetic controlled fixtures with a held-out set of recent, permissioned repositories/issues not used for prompt tuning. For public datasets, track publication and model training cutoffs where known; exclude or separately report items with disclosed gold patches or likely memorized answers. Refresh held-out tasks on a schedule and preserve their labels in an access-controlled evaluator.

Each task instance starts from a clean, immutable repo snapshot and isolated worktree/sandbox. Verify no previous trial's branch, cache, memories, locks, or generated files are mounted. Randomize task order and config assignment. Use at least several independent model seeds/runs per task when sampling is enabled; compute confidence intervals clustered by task, not just by individual agent. A separate benchmark owner should review task validity and grader/test alignment.

### Baselines, comparisons, and ablations

Run these configurations against the **same model versions, task snapshot, available tools, permission policy, per-task deadline, and aggregate spend/token ceiling**:

1. One agent, no swarm machinery (the quality baseline).
2. One agent with graph retrieval/context only (isolates graph value).
3. Independent parallel agents with no shared memory/handoffs (parallel-search baseline).
4. ApexGraphSwarm with its proposed coordination and graph-based routing.
5. A simple non-LLM graph/heuristic baseline for deterministic extraction, pathfinding, or task allocation where applicable.

Then ablate one feature at a time: graph input; coordination topology; task decomposition; shared graph/memory; deduplication; verifier/critic; conflict resolver; retry policy; worker specialization; and adaptive routing. Include both **equal-total-budget** comparisons (same max tokens/API cost/tool budget) and **equal-wall-clock** comparisons (same deadline, report actual cost). Also show quality at matched cost and cost at matched quality when a frontier can be estimated. Do not call lower latency a win if it spends more compute without reporting it. Do not attribute gains to “swarm” when model, context, tools, or budget also changed.

Report task success and quality separately from system behavior. Core outcome metrics: hidden-test pass rate; human-graded correctness/usefulness with blinded rubrics; graph edge/node precision, recall, and referential integrity against gold where available; unsupported-claim rate; regression rate; safe completion rate; and partial completion. System metrics: total and per-agent tokens, provider/tool dollars, wall-clock p50/p95, time-to-first-useful-result, active vs queued worker counts, throughput, retries, failed work, duplicate effort, handoff loss, merge/conflict/rework rate, graph freshness/staleness, and peak CPU/RAM/storage/network. Include per-task results, not only averages.

### Concurrency sweep: 1 / 10 / 30 / 100 / 300

Run a fixed task mix at **maximum active-worker caps** of 1, 10, 30, 100, and 300, with separate runs and the same total budget per task. Measure observed active workers, queue wait, accepted/rejected launches, provider rate-limit events, saturation, completion throughput, quality, cost, and tail latency. Keep tasks numerous enough to occupy each cap; also include a small fixed set to expose oversubscription waste. Include one-task and batch-throughput modes separately.

Treat 30/100/300 as **stress-test tiers proposed for ApexGraphSwarm, not demonstrated targets**. First validate the scheduler using a deterministic mock worker, then a constrained sandbox with synthetic tasks. Only benchmark live model providers at a concurrency the provider contract and account limit authorize; disclose when the tested cap cannot be achieved. The concurrency number is a cap, not proof all workers ran simultaneously. Report peak and time-integrated concurrency. For any managed-agent platform, obey its documented thread/rate limits; e.g. Anthropic Managed Agents documents 25 concurrent threads, so its endpoint cannot substantiate a 30–300 concurrency result without a different permitted execution surface.

At each tier, plot success/quality versus active concurrency and cost/latency versus quality. Stop scaling when marginal task throughput flattens while errors, duplicate work, cost, latency, or conflicts rise. A 300-worker result should be described as a stress test of this particular harness/model/environment/task mix, never as a general capability claim.

### Graph correctness, permissions, handoffs, and contention

- **Graph correctness:** validate node/edge IDs and types on every write; compare extracted nodes/edges to a hidden ground-truth graph on controlled fixtures; check path claims against repository files; detect dangling references, duplicates, cycles where the schema requires a DAG, stale evidence, and contradictory facts. Use adversarial malformed, empty, disconnected, cyclic, and duplicated inputs. The verifier must be independent of the agent that authored the graph.
- **Tool permissions:** assign each worker least-privilege read/write scopes and explicit allowed commands/network destinations. Test path traversal, symlink escape, shell metacharacters, secret access, cross-worktree writes, network egress, branch/commit actions, and attempts to edit hidden evaluator assets. Grade policy violations as hard failures even if the task result is correct. Log denied calls as well as allowed calls.
- **Handoffs:** pass typed, versioned artifacts (task ID, owned files/resources, assumptions, evidence/citations, changeset, tests, unresolved questions, and expected consumer). Measure required-field completeness, evidence survival, duplicate work, dropped constraints, and successful continuation by a fresh worker with no private predecessor context. Reject stale or mismatched graph/schema versions.
- **Conflicts:** create paired tasks that intentionally touch disjoint files, the same file, and incompatible requirements. Measure overlapping writes, lock/claim violations, merge conflicts, reverted work, unmerged PRs, deadlocks, and human recovery time. Include controlled contradictory instructions and malicious-worker attempts to overwrite or sabotage another worker. Shared worktrees need transactional claims or isolated branches and a guarded merge gate.
- **Concurrency safety:** inject worker crashes during lock acquisition, after partial writes, during handoff, and during merge; stale lease recovery; duplicate delivery; lost/duplicated events; cancellation; provider 429/5xx/timeouts; slow graders; malformed/oversized results; graph-store outages; and orchestrator restart. Verify idempotent retries, bounded queue growth, no ghost active tasks, no leaked locks, deterministic terminal state, and that partial results are labeled as partial.

## Proposed initial service-level targets (all unmeasured)

Targets below are acceptance hypotheses for a first controlled release, **not achieved SLOs**. Revisit them after baseline measurement; publish hardware, model, provider, concurrency, and workload with every result.

| Area | Proposed target / gate |
| --- | --- |
| Correctness | 100% schema-valid and reference-valid graph outputs on deterministic fixtures; no accepted hidden-test regression; quality must be non-inferior to the single-agent baseline within a preregistered margin at equal cost. |
| Permissions | Zero successful out-of-scope tool actions in the red-team suite; denied-action detection and audit coverage at 100% for instrumented calls. |
| Reliability | At least 99% of worker/task transitions reach a terminal state under fault injection; no duplicate side effect on retry for idempotency-tested operations. |
| Handoff | At least 99% of required handoff fields preserved; zero continuation on a stale schema/hash without an explicit migration. |
| Scaling | No claim of a quality/SLO target for 100 or 300 until those tiers are run. For each tested tier, require reported p50/p95 queue time, throughput, cost, active-worker trace, and task success; stop the sweep when matched-budget quality drops materially or queue/error rates become unstable. |
| Latency | Proposed local scheduling overhead p95 under 1 second, excluding model/tool time; end-to-end deadline must be task-class-specific and measured. |
| Cost | Every run must have a complete recorded spend/token total or be marked unknown; no quality claim may omit cost. |

## Primary-source reading list (checked 2026-09-27)

- Anthropic, [Measurements for understanding the pace of AI development inside frontier labs](https://www.anthropic.com/institute/measuring-pace-of-ai-development) (30,000 active internal agents, scoped to one platform, and oversight metrics).
- Anthropic, [Managed Agents multiagent orchestration docs](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration) (25 concurrent threads; coordinator roster mechanics).
- Anthropic, [Building a C compiler with a team of parallel Claudes](https://www.anthropic.com/engineering/building-c-compiler) (16-agent coding case study; nearly 2,000 cumulative sessions; cost and merge lessons).
- Anthropic, [Patterns and problems in emerging multiagent systems](https://www.anthropic.com/research/multiagent-systems) (45-agent vulnerability search, 10–80-agent software collaboration trials, coordination and conflict outcomes).
- Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) (internal research result and token-overhead caveats).
- Anthropic, [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (grader design, repeated trials, isolation, state and cost/latency metrics).
- Zhu et al., [MultiAgentBench](https://arxiv.org/abs/2503.01935) (ACL 2025).
- Liu et al., [AgentBench](https://arxiv.org/abs/2308.03688) (ICLR 2024).
- Barres et al., [τ²-Bench](https://arxiv.org/abs/2506.07982) (dual-control user-agent evaluation, 2025).
- Shi et al., [τ^τ-Bench](https://arxiv.org/abs/2609.04611) (end-to-end agent construction, 2026).

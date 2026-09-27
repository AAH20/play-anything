# Codex Agentic AI: Autonomous Exploration & Enhancement Guide
> **Repository**: `AAH20/play-anything`  
> **Target Models**: Frontier Coding Models (Codex, Astra, Claude 3.7, DeepSeek-R1)  
> **Operational Standard**: Zero Hallucination, Deterministic AST Grounding, Strict Token Budgeting

---

## 1. System Topology & Architectural Invariants

`play-anything` transforms any software repository into a deterministic, procedural RPG-like state machine and interactive developer dashboard with zero external pip dependencies.

### Core Modules Directory
```
play_anything/
├── core/
│   ├── models.py                     # Fundamental dataclasses (Chamber, Quest, SkillNode, WorldMap)
│   ├── dungeon_partitioner.py        # Spectral min-cut & topological AST file partitioning
│   ├── skill_tree_induction.py       # Dependency DAG extraction and skill tier synthesis
│   ├── submodular_graphrag.py        # Submodular greedy node selection (Coverage vs Diversity)
│   ├── npc_role_assigner.py          # Git blame & commit entropy archetype allocation
│   ├── quest_steiner_synthesizer.py  # Minimal Steiner tree quest route synthesis
│   ├── sandbox_scheduler.py          # Priority-queue task executor with backpressure
│   ├── tokenomics_equilibrium.py     # Bonding curve and reward distribution math
│   ├── temporal_drift_engine.py      # Git log commit velocity & code rot degradation
│   ├── byzantine_fairplay.py         # Anti-cheat AST mutation and test audit verification
│   ├── realm_studio.py               # Map creation manifest compiler & Kaggle arena evaluation
│   ├── personalization_engine.py     # Age-clustered onboarding, peer/AI matchmaking, leaderboards
│   ├── strategic_whales_consortium.py# AAA game engine coordination & anti-escapism governance
│   └── enterprise_infra.py           # Serverless scale-to-zero, multi-cloud anycast, vLLM/OpenRouter arbitrage, SOC/GRC
├── adapters/
│   ├── repo_rpg_generator.py         # High-level filesystem reader & world generator
│   ├── computer_use_sandbox_adapter.py # OS-level action executor (screen/mouse/keyboard)
│   └── voice_agent_adapter.py        # Full-duplex conversational voice intent dispatcher
├── engine.py                         # Master coordinator and public facade
├── cli.py                            # Zero-dependency command-line entry point
└── dashboard.html                    # Single-file zero-dependency Tailwind WebGL/Canvas UI
```

---

## 2. Strict Rules to Prevent Token Waste & Context Drift

When an autonomous AI agent explores or refactors this codebase, it must adhere to the following token conservation and precision protocols:

### A. AST Signature Lookups Before Full-File Ingestion
* **Do NOT** ingest full 800+ line files into the prompt context when investigating method signatures or class relationships.
* **DO** inspect target class and method definitions specifically using targeted line range slicing.
* **Token Budget Limit**: Keep per-turn file reading context below **8,000 tokens**. Never read the entire `dashboard.html` (170 KB) unless making a targeted surgical modification.

### B. Zero-Entropy Sampling for Analysis & Edits
* Set generation temperature to `0.0` or equivalent low-entropy decoding.
* Eliminate speculative commentary; focus strictly on verifiable AST diffs, formal logic, and runtime assertions.

### C. Grep/Glob Fallback Discipline
* **Priority 1**: AST Graph / Symbol discovery (inspect class and function definitions directly).
* **Priority 2**: Targeted ripgrep for exact string literals, error identifiers, or configuration keys.
* **Prohibited**: Unbounded glob searches that recurse into `.git/`, `__pycache__/`, or node modules.

### D. Deterministic Import Verification
* Verify all imported modules exist on disk before writing replacement chunks.
* Maintain the **Zero Pip Dependency Rule**: The runtime must only utilize the Python 3.10+ standard library (`dataclasses`, `enum`, `math`, `hashlib`, `json`, `time`, `typing`, `unittest`, `pathlib`).

---

## 3. Anti-Hallucination & Grounding Protocols

To ensure that suggested enhancements are real, functional, and verifiable:

### A. Mandatory Test Suite Verification
Every proposed bugfix, refactoring, or algorithmic enhancement **must be validated** by running the automated unit test suite:
```bash
python3 -m unittest discover tests
```
* **Acceptance Criteria**: 100% of unit tests must pass with zero failures and zero errors in $< 0.05\text{s}$.
* If an agent claims an enhancement works without running the test suite, the assertion is classified as an unverified hallucination.

### B. Interface Contract Preservation
Edits must preserve backward compatibility across all public core interfaces:
* `PlayAnythingEngine.generate_world(repo_path: str) -> WorldMap`
* `AdaptivePersonalizationEngine.calibrate_player_profile(user_id: str, ...) -> PersonalizationProfile`
* `ServerlessScaleToZeroManager.acquire_replica(tier: SandboxTier) -> MicroVMReplica`
* `OpenRouterComplexityArbitrageEngine.determine_optimal_model_route(...) -> Dict[str, Any]`

---

## 4. Current Technical Boundaries & Limitations

An exploring agent must understand the explicit boundaries of the current system to prevent proposing unrealistic or out-of-scope modifications:

| Subsystem | Current Implementation | Real-World Boundary & Constraint |
|---|---|---|
| **Hardware Sandboxing** | Multi-tier abstraction with mock/simulated KVM microVM handles in `enterprise_infra.py` | Bare-metal Firecracker microVMs require Linux root access (`/dev/kvm`). On macOS/Windows, execution falls back to process-isolated sandbox mocks. |
| **vLLM Inference Fleet** | Deterministic Task Complexity Index ($\text{TCI}$) calculation & routing simulation | Live GPU acceleration requires NVIDIA H100/B200 clusters with CUDA 12+. When run locally, routing verdicts provide mathematical cost estimates rather than live API calls. |
| **In-Memory Graph Scaling** | Submodular greedy graph selection executed in pure RAM | Repositories exceeding 500,000 lines of code or 50,000 files will encounter RAM allocation limits without an external on-disk key-value store (e.g. SQLite / RocksDB). |
| **Browser Canvas Rendering** | Single-canvas procedural isometric projection in `dashboard.html` | Client CPU/GPU performance degrades if rendering $> 500$ simultaneous animated nodes without hierarchical level-of-detail (LOD) culling. |
| **Voice NPC Audio** | Web Audio API synthesizer + Web Speech API fallback | Full-duplex sub-120ms neural audio relies on browser speech synthesis capabilities unless connected to an external WebSocket streaming server. |

---

## 5. Concrete, Grounded Enhancement Vectors

When an autonomous agent is instructed to enhance the project, it should focus exclusively on these grounded, high-leverage architectural vectors:

### Enhancement Vector 1: Monorepo Streaming AST Parser
* **Problem**: Ingesting massive monorepos ($>1\text{M}$ LOC) causes memory spikes during initial graph construction.
* **Implementation Plan**:
  1. Refactor `adapters/repo_rpg_generator.py` to yield a generator of AST nodes rather than building an in-memory list.
  2. Implement an incremental bounding cache storing node summaries in local SQLite storage.
  3. Validate using `tests/test_play_anything.py`.

### Enhancement Vector 2: Client-Side WebAssembly (WASM) Engine
* **Problem**: The dashboard currently requires local Python execution to generate new realm structures.
* **Implementation Plan**:
  1. Compile the core AST partitioning and Steiner tree algorithms into a WebAssembly micro-bundle via Pyodide or Rust-WASM.
  2. Embed the WASM binary directly inside `dashboard.html` as a Base64 data URI to enable 100% offline, zero-server repository gamification directly in the browser.

### Enhancement Vector 3: Formal JSON Schema Manifest Export
* **Problem**: Realm manifests created in the Realm Studio are exported as dynamic Python dictionaries.
* **Implementation Plan**:
  1. Define a strict JSON Schema (Draft 2020-12) specification for `RealmManifest`.
  2. Implement schema validation in `core/realm_studio.py` using standard library `json` parsing and structural pattern matching.

### Enhancement Vector 4: Automated Headless Visual Regression Harness
* **Problem**: Dashboard UI regressions across the 8 views must currently be checked manually.
* **Implementation Plan**:
  1. Add a lightweight headless test runner in `tests/test_visual_regression.py`.
  2. Automate snapshot captures across all 8 tab hashes (`#map`, `#skills`, `#battle`, `#voice`, `#benchmarks`, `#studio`, `#personalization`, `#enterprise`).

---

## 6. Execution Protocol Checklist for Codex / Frontier Agents

Before submitting any Pull Request or completing any autonomous coding task on this repository, execute the following protocol:

- [ ] **AST Integrity**: Verify all modified Python files parse cleanly with `python3 -m py_compile <path>`.
- [ ] **Test Coverage**: Run `python3 -m unittest discover tests` and verify 29/29 tests pass in $<0.05\text{s}$.
- [ ] **Zero-Dependency Audit**: Confirm `git diff` introduces no new `import` statements outside the Python standard library.
- [ ] **Dashboard Sync**: If modifying `dashboard.html`, verify that hash routing (`#map`, `#personalization`, etc.) functions cleanly and that all closing `</div>` tags match.
- [ ] **Commit Hygiene**: Ensure commit messages follow Conventional Commits formatting (`feat:`, `fix:`, `refactor:`, `docs:`).

"""Data contracts and schemas for Play-Anything: The Apex Repo-as-a-Living-RPG Engine.

Defines all core types for AST call graphs, pedagogical skill trees, dungeon fog-of-war biomes,
multi-agent NPC personas, prize-collecting quest paths, full-duplex voice intent routing,
submodular GraphRAG context, computer-use sandbox schedules, tokenomics, temporal drift, and anti-cheat.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any


# --- Base Graph & Code Entities ---
@dataclass(frozen=True)
class CodeNode:
    """Represents a file, module, class, or function in the analyzed codebase."""
    node_id: str
    name: str
    kind: str  # 'file', 'module', 'class', 'function', 'test'
    layer: str  # 'api', 'service', 'domain', 'data', 'infra', 'ui'
    complexity: float  # Cyclomatic / AST cognitive complexity
    lines_of_code: int
    vulnerability_score: float = 0.0  # 0.0 to 1.0 (CVE / code smell likelihood)
    tags: Set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CodeEdge:
    """Directed dependency, import, call, or inheritance relationship."""
    source: str
    target: str
    relation: str  # 'imports', 'calls', 'inherits', 'tests', 'instantiates'
    weight: float = 1.0


# --- P1: Pedagogical Skill Tree Induction ---
@dataclass
class SkillNode:
    skill_id: str
    title: str
    associated_node_id: str
    layer: str
    xp_reward: int
    prerequisites: List[str] = field(default_factory=list)
    unlocked: bool = False
    mastery_level: int = 0  # 0 to 5


@dataclass
class SkillTreeResult:
    root_skills: List[str]
    skill_nodes: Dict[str, SkillNode]
    feedback_arcs_removed: int
    tree_depth: int
    is_acyclic: bool
    algorithm: str
    execution_time_us: float


# --- P2: Dungeon Fog-of-War Partitioning ---
@dataclass
class DungeonRoom:
    room_id: str
    name: str
    biome: str  # 'Crypt of Auth', 'Citadel of Services', 'Forgotten DB Caves'
    contained_nodes: List[str]
    danger_level: int  # 1 to 10
    is_fog_covered: bool = True
    boss_node_id: Optional[str] = None


@dataclass
class FogOfWarPartitionResult:
    rooms: List[DungeonRoom]
    cut_edges_count: int
    balance_ratio: float
    partition_count: int
    algorithm: str
    execution_time_us: float


# --- P3: Multi-Agent NPC Role & Persona Assignment ---
@dataclass
class AgentPersona:
    npc_id: str
    name: str
    archetype: str  # 'Senior Architect Wizard', 'Security Rogue', 'DevOps Blacksmith', 'Corrupted Boss'
    voice_tone: str  # 'mystical_authoritative', 'shadow_cunning', 'boisterous_industrial', 'menacing_glitch'
    dialogue_style: str
    assigned_room_id: Optional[str] = None
    assigned_node_id: Optional[str] = None
    affinity_layers: Set[str] = field(default_factory=set)


@dataclass
class NPCAssignmentResult:
    npc_assignments: Dict[str, str]  # npc_id -> node_id or room_id
    total_affinity_score: float
    unassigned_count: int
    algorithm: str
    execution_time_us: float


# --- P4: Dynamic Quest & Boss Battle Synthesis (PCST) ---
@dataclass
class QuestPath:
    quest_id: str
    title: str
    narrative_hook: str
    start_node: str
    target_boss_node: str
    path_nodes: List[str]
    total_xp_yield: int
    token_cost: int
    boss_hp: int
    failing_test_command: str


@dataclass
class PrizeSteinerQuestResult:
    quest: QuestPath
    total_cost: float
    prize_collected: float
    nodes_included_count: int
    algorithm: str
    execution_time_us: float


# --- P5: Voice Agent Graph Routing under Latency Deadlines ---
@dataclass
class VoicePacket:
    packet_id: str
    user_transcript: str
    extracted_entities: List[str]
    deadline_ms: float = 180.0


@dataclass
class LatencyConstrainedVoiceResult:
    selected_subgraph: List[str]
    predicted_stt_ms: float
    graph_routing_ms: float
    predicted_tts_ms: float
    total_roundtrip_ms: float
    deadline_met: bool
    algorithm: str
    execution_time_us: float


# --- P6: GraphRAG Submodular Curiosity Context Distillation ---
@dataclass
class ContextSnippet:
    snippet_id: str
    node_id: str
    content: str
    token_length: int
    novelty_score: float
    concepts: Set[str]


@dataclass
class SubmodularCuriosityResult:
    selected_snippets: List[str]
    total_coverage: float
    used_tokens: int
    token_budget: int
    redundancy_penalty: float
    algorithm: str
    execution_time_us: float


# --- P7: Computer-Use Sandbox Task Scheduler ---
@dataclass
class SandboxAction:
    action_id: str
    name: str  # 'git_checkout', 'npm_build', 'playwright_browser_test', 'cargo_test'
    resource_id: str  # 'terminal_shell', 'headless_browser', 'port_8080'
    duration_ms: int
    precedence_deps: List[str] = field(default_factory=list)
    release_ms: int = 0


@dataclass
class DisjunctiveSandboxResult:
    schedule: Dict[str, int]  # action_id -> start_time_ms
    makespan_ms: int
    deadlock_free: bool
    algorithm: str
    execution_time_us: float


# --- P8: In-Game Tokenomics Equilibrium ---
@dataclass
class PlayerWallet:
    player_id: str
    xp: int
    mana_credits: float  # LLM query credits
    bounty_coins: int
    utility_weight: float = 1.0


@dataclass
class MarketEquilibriumResult:
    clearing_prices: Dict[str, float]  # resource -> price per unit
    allocations: Dict[str, Dict[str, float]]  # player_id -> {resource: amount}
    market_cleared: bool
    social_welfare: float
    algorithm: str
    execution_time_us: float


# --- P9: Temporal Code Drift & Invalidation ---
@dataclass
class GitDiffDelta:
    commit_hash: str
    modified_files: List[str]
    added_functions: List[str]
    deleted_functions: List[str]
    timestamp: float


@dataclass
class TemporalDriftResult:
    invalidated_quests: List[str]
    mutated_rooms: List[str]
    respawned_bosses: List[str]
    unaffected_skills_count: int
    algorithm: str
    execution_time_us: float


# --- P10: Multi-Agent Byzantine Fair-Play Anti-Cheat ---
@dataclass
class SolutionSubmission:
    submission_id: str
    quest_id: str
    player_id: str
    patch_diff: str
    sandbox_exit_code: int
    test_output: str


@dataclass
class ByzantineVerificationResult:
    is_valid: bool
    consensus_score: float
    quarantined_agents: List[str]
    tamper_detected: bool
    verdict: str  # 'ACCEPTED_GENUINE_PASS', 'REJECTED_MOCK_TEST_CHEAT', 'REJECTED_SYNTAX_ERROR'
    algorithm: str
    execution_time_us: float

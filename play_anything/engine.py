"""Play-Anything Master Engine Facade.

Unified access point orchestrating the 10 NP-Hard / PPAD-complete combinatorial solvers,
world generation, full-duplex voice dialogues, computer-use sandbox execution, and microsecond benchmarks.
"""
import time
from typing import List, Dict, Any, Optional

from .core.models import (
    CodeNode, CodeEdge,
    SkillNode, SkillTreeResult,
    DungeonRoom, FogOfWarPartitionResult,
    AgentPersona, NPCAssignmentResult,
    QuestPath, PrizeSteinerQuestResult,
    VoicePacket, LatencyConstrainedVoiceResult,
    ContextSnippet, SubmodularCuriosityResult,
    SandboxAction, DisjunctiveSandboxResult,
    PlayerWallet, MarketEquilibriumResult,
    GitDiffDelta, TemporalDriftResult,
    SolutionSubmission, ByzantineVerificationResult,
)
from .core.skill_tree_induction import solve_skill_tree_induction
from .core.dungeon_partitioner import solve_dungeon_partitioning
from .core.npc_role_assigner import solve_npc_role_assignment
from .core.quest_steiner_synthesizer import solve_quest_steiner_synthesis
from .core.voice_intent_router import solve_voice_intent_routing
from .core.submodular_graphrag import solve_submodular_graphrag
from .core.sandbox_scheduler import solve_sandbox_scheduling
from .core.tokenomics_equilibrium import solve_tokenomics_equilibrium
from .core.temporal_drift_engine import solve_temporal_drift_sync
from .core.byzantine_fairplay import solve_byzantine_fairplay

from .adapters.voice_agent_adapter import VoiceAgentAdapter
from .adapters.computer_use_sandbox_adapter import ComputerUseSandboxAdapter
from .adapters.repo_rpg_generator import RepoRPGGenerator, WorldState


class PlayAnythingEngine:
    """Master engine facade for Codebase Gamification & Agentic Swarm Orchestration."""

    def __init__(self):
        self.voice = VoiceAgentAdapter()
        self.sandbox = ComputerUseSandboxAdapter()
        self.generator = RepoRPGGenerator()

    def generate_world(self, repo_path: Optional[str] = None) -> WorldState:
        """Compiles a repository or sample codebase into a living RPG world state."""
        if repo_path:
            return self.generator.scan_local_directory(repo_path)
        return self.generator.generate_synthetic_world()

    def create_benchmark_suite(self) -> Dict[str, Any]:
        """Constructs synthetic workloads for benchmarking all 10 combinatorial solvers."""
        # 1. Nodes & Edges (9 nodes)
        nodes = [
            CodeNode("n1", "DBPool.ts", "class", "data", 4.0, 150, 0.05, {"db"}),
            CodeNode("n2", "Redis.ts", "class", "infra", 3.0, 90, 0.0, {"cache"}),
            CodeNode("n3", "User.ts", "class", "domain", 2.0, 110, 0.0, {"user"}),
            CodeNode("n4", "AuthJWT.ts", "class", "domain", 7.5, 220, 0.4, {"auth"}),
            CodeNode("n5", "Order.ts", "service", "service", 8.0, 300, 0.3, {"order"}),
            CodeNode("n6", "Stripe.ts", "service", "service", 6.0, 180, 0.1, {"pay"}),
            CodeNode("n7", "Router.ts", "module", "api", 5.0, 140, 0.1, {"http"}),
            CodeNode("n8", "Modal.tsx", "ui", "ui", 3.5, 120, 0.0, {"ui"}),
            CodeNode("n9", "Test.ts", "test", "test", 2.5, 75, 0.0, {"test"}),
        ]
        edges = [
            CodeEdge("n1", "n3", "imports", 1.0),
            CodeEdge("n2", "n4", "calls", 1.2),
            CodeEdge("n3", "n4", "imports", 1.0),
            CodeEdge("n4", "n5", "calls", 1.5),
            CodeEdge("n1", "n5", "calls", 1.3),
            CodeEdge("n6", "n5", "imports", 1.1),
            CodeEdge("n5", "n7", "calls", 1.4),
            CodeEdge("n7", "n8", "calls", 1.2),
            CodeEdge("n4", "n9", "tests", 1.0),
        ]

        # 3. Personas
        personas = [
            AgentPersona("npc_1", "Gandalf", "Senior Architect Wizard", "mystical", "advice", affinity_layers={"domain"}),
            AgentPersona("npc_2", "Rogue", "Security Rogue", "shadow", "audit", affinity_layers={"domain", "api"}),
            AgentPersona("npc_3", "Smith", "DevOps Blacksmith", "industrial", "forge", affinity_layers={"infra"}),
            AgentPersona("npc_4", "Boss", "Corrupted Boss", "glitch", "combat", affinity_layers={"service"}),
        ]

        # 5. Voice Packet
        voice_pkt = VoicePacket("v_01", "How do I fix authentication tokens?", ["auth", "token"], deadline_ms=180.0)

        # 6. GraphRAG Snippets
        snippets = [
            ContextSnippet("sn_1", "n4", "JWT Token Signing logic and private key parsing", 200, 9.2, {"auth", "jwt"}),
            ContextSnippet("sn_2", "n4", "Refresh token rotation and expiration checking", 250, 8.8, {"auth", "security"}),
            ContextSnippet("sn_3", "n1", "Connection pool recycling parameters", 180, 5.4, {"db", "pool"}),
            ContextSnippet("sn_4", "n5", "Order transaction isolation level locks", 300, 7.5, {"order", "lock"}),
            ContextSnippet("sn_5", "n2", "Redis cache TTL configuration", 150, 4.2, {"cache", "redis"}),
        ]

        # 7. Sandbox Actions
        actions = [
            SandboxAction("act_1", "git_checkout", "terminal_shell", 25),
            SandboxAction("act_2", "compile_ts", "terminal_shell", 60, precedence_deps=["act_1"]),
            SandboxAction("act_3", "spin_mock_server", "port_8080", 40, precedence_deps=["act_2"]),
            SandboxAction("act_4", "run_playwright", "headless_browser", 80, precedence_deps=["act_3"]),
            SandboxAction("act_5", "audit_log", "terminal_shell", 20, precedence_deps=["act_4"]),
        ]

        # 8. Wallets
        wallets = [
            PlayerWallet("player_1", xp=1500, mana_credits=30.0, bounty_coins=5),
            PlayerWallet("player_2", xp=4200, mana_credits=75.0, bounty_coins=12),
        ]
        supplies = {"llm_tokens": 100000.0, "gpu_seconds": 3600.0, "sandbox_slots": 10.0}

        # 9. Git Diff
        diff = GitDiffDelta("c_abc123", ["AuthJWT.ts"], ["validateToken"], ["oldVerify"], 100.0)
        dummy_quest = QuestPath("q_1", "Auth Raid", "Fix auth", "n1", "n4", ["n1", "n4"], 500, 1000, 100, "npm test")

        # 10. Submission
        sub = SolutionSubmission("sub_1", "q_1", "p1", "+ token.atomicRefresh()", 0, "4 passed")

        return {
            "nodes": nodes,
            "edges": edges,
            "personas": personas,
            "voice_pkt": voice_pkt,
            "snippets": snippets,
            "actions": actions,
            "wallets": wallets,
            "supplies": supplies,
            "diff": diff,
            "dummy_quest": dummy_quest,
            "sub": sub
        }

    def run_full_benchmark_suite(self) -> List[Dict[str, Any]]:
        """Runs microsecond benchmarks across all 10 solvers."""
        suite = self.create_benchmark_suite()
        results = []

        # P1: Skill Tree Induction
        p1 = solve_skill_tree_induction(suite["nodes"], suite["edges"])
        results.append({
            "solver": "P1_Skill_Tree_Induction",
            "metric": f"skills={len(p1.skill_nodes)}, depth={p1.tree_depth}",
            "latency_us": round(p1.execution_time_us, 1)
        })

        # P2: Dungeon Fog-of-War
        p2 = solve_dungeon_partitioning(suite["nodes"], suite["edges"])
        results.append({
            "solver": "P2_Dungeon_FogOfWar",
            "metric": f"rooms={p2.partition_count}, cuts={p2.cut_edges_count}",
            "latency_us": round(p2.execution_time_us, 1)
        })

        # P3: NPC Role Assignment
        p3 = solve_npc_role_assignment(suite["personas"], suite["nodes"], p2.rooms)
        results.append({
            "solver": "P3_NPC_Role_Assignment",
            "metric": f"assigned={len(p3.npc_assignments)}, affinity={p3.total_affinity_score}",
            "latency_us": round(p3.execution_time_us, 1)
        })

        # P4: Quest Steiner PCST
        p4 = solve_quest_steiner_synthesis(suite["nodes"], suite["edges"], "n1", "n5")
        results.append({
            "solver": "P4_Quest_Steiner_PCST",
            "metric": f"quest_nodes={p4.nodes_included_count}, prize={p4.prize_collected}",
            "latency_us": round(p4.execution_time_us, 1)
        })

        # P5: Voice Intent Router
        p5 = solve_voice_intent_routing(suite["voice_pkt"], suite["nodes"], suite["edges"])
        results.append({
            "solver": "P5_Voice_Intent_Router",
            "metric": f"total_rt={p5.total_roundtrip_ms}ms, deadline_ok={p5.deadline_met}",
            "latency_us": round(p5.execution_time_us, 1)
        })

        # P6: Submodular GraphRAG
        p6 = solve_submodular_graphrag(suite["snippets"], token_budget=500)
        results.append({
            "solver": "P6_Submodular_GraphRAG",
            "metric": f"snippets={len(p6.selected_snippets)}, coverage={p6.total_coverage}",
            "latency_us": round(p6.execution_time_us, 1)
        })

        # P7: Sandbox Task Scheduler
        p7 = solve_sandbox_scheduling(suite["actions"])
        results.append({
            "solver": "P7_Sandbox_Scheduler",
            "metric": f"makespan={p7.makespan_ms}ms, deadlock_free={p7.deadlock_free}",
            "latency_us": round(p7.execution_time_us, 1)
        })

        # P8: Tokenomics Equilibrium
        p8 = solve_tokenomics_equilibrium(suite["wallets"], suite["supplies"])
        results.append({
            "solver": "P8_Tokenomics_Equilibrium",
            "metric": f"welfare={p8.social_welfare}, cleared={p8.market_cleared}",
            "latency_us": round(p8.execution_time_us, 1)
        })

        # P9: Temporal Drift Sync
        p9 = solve_temporal_drift_sync(suite["diff"], p2.rooms, [suite["dummy_quest"]], p1.skill_nodes)
        results.append({
            "solver": "P9_Temporal_Drift_Sync",
            "metric": f"invalidated_q={len(p9.invalidated_quests)}, mutated_r={len(p9.mutated_rooms)}",
            "latency_us": round(p9.execution_time_us, 1)
        })

        # P10: Byzantine Anti-Cheat
        p10 = solve_byzantine_fairplay(suite["sub"])
        results.append({
            "solver": "P10_Byzantine_AntiCheat",
            "metric": f"valid={p10.is_valid}, verdict={p10.verdict}",
            "latency_us": round(p10.execution_time_us, 1)
        })

        return results

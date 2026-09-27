"""Play-Anything Core Graph & Swarm Solvers.

Exports the 10 apex NP-Hard and PPAD-complete combinatorial solvers for Codebase RPG Gamification.
"""
from .models import (
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
from .skill_tree_induction import solve_skill_tree_induction
from .dungeon_partitioner import solve_dungeon_partitioning
from .npc_role_assigner import solve_npc_role_assignment
from .quest_steiner_synthesizer import solve_quest_steiner_synthesis
from .voice_intent_router import solve_voice_intent_routing
from .submodular_graphrag import solve_submodular_graphrag
from .sandbox_scheduler import solve_sandbox_scheduling
from .tokenomics_equilibrium import solve_tokenomics_equilibrium
from .temporal_drift_engine import solve_temporal_drift_sync
from .byzantine_fairplay import solve_byzantine_fairplay

__all__ = [
    # Models
    "CodeNode", "CodeEdge",
    "SkillNode", "SkillTreeResult",
    "DungeonRoom", "FogOfWarPartitionResult",
    "AgentPersona", "NPCAssignmentResult",
    "QuestPath", "PrizeSteinerQuestResult",
    "VoicePacket", "LatencyConstrainedVoiceResult",
    "ContextSnippet", "SubmodularCuriosityResult",
    "SandboxAction", "DisjunctiveSandboxResult",
    "PlayerWallet", "MarketEquilibriumResult",
    "GitDiffDelta", "TemporalDriftResult",
    "SolutionSubmission", "ByzantineVerificationResult",
    # Solvers
    "solve_skill_tree_induction",
    "solve_dungeon_partitioning",
    "solve_npc_role_assigner",
    "solve_quest_steiner_synthesis",
    "solve_voice_intent_routing",
    "solve_submodular_graphrag",
    "solve_sandbox_scheduling",
    "solve_tokenomics_equilibrium",
    "solve_temporal_drift_sync",
    "solve_byzantine_fairplay",
]

"""Repo-to-RPG World Generator Adapter.

Transforms any raw file directory or Git repository into a fully playable RPG World State:
- Induces hierarchical skill tree DAGs.
- Partitions files into thematic dungeon rooms under fog-of-war.
- Populates rooms with autonomous voice-enabled NPCs.
- Synthesizes dynamic quests and boss fights.
"""
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Any
from .repository_index import iter_repository_summaries, resolve_python_imports
from ..core.models import (
    CodeNode, CodeEdge,
    SkillTreeResult, FogOfWarPartitionResult,
    AgentPersona, NPCAssignmentResult,
    PrizeSteinerQuestResult, QuestPath
)
from ..core.skill_tree_induction import solve_skill_tree_induction
from ..core.dungeon_partitioner import solve_dungeon_partitioning
from ..core.npc_role_assigner import solve_npc_role_assignment
from ..core.quest_steiner_synthesizer import solve_quest_steiner_synthesis


@dataclass
class WorldState:
    repo_name: str
    player_level: int
    player_xp: int
    player_mana: int
    skill_tree: SkillTreeResult
    dungeon: FogOfWarPartitionResult
    npc_assignment: NPCAssignmentResult
    active_quests: List[QuestPath]
    personas: List[AgentPersona]
    nodes: List[CodeNode]
    edges: List[CodeEdge]


class RepoRPGGenerator:
    """Compiles code repositories into living, playable RPG worlds."""

    @staticmethod
    def generate_synthetic_world(repo_name: str = "Apollo-Core") -> WorldState:
        """Generates a complete, structured sample RPG world state for immediate exploration."""
        nodes = [
            # Infrastructure & DB
            CodeNode("node_db", "DatabasePool.ts", "class", "data", 4.2, 180, 0.05, {"postgres", "pool"}),
            CodeNode("node_cache", "RedisCache.ts", "class", "infra", 3.1, 95, 0.0, {"cache", "redis"}),
            # Domain & Auth
            CodeNode("node_user", "UserEntity.ts", "class", "domain", 2.5, 120, 0.0, {"entity", "user"}),
            CodeNode("node_auth", "JWTAuthManager.ts", "class", "domain", 7.8, 240, 0.45, {"auth", "jwt", "crypto"}),
            # Service
            CodeNode("node_order_svc", "OrderProcessor.ts", "service", "service", 8.4, 310, 0.35, {"orders", "checkout"}),
            CodeNode("node_payment_svc", "PaymentGateway.ts", "service", "service", 6.2, 190, 0.15, {"stripe", "billing"}),
            # API & UI
            CodeNode("node_api_router", "ExpressRoutes.ts", "module", "api", 5.0, 150, 0.1, {"http", "express"}),
            CodeNode("node_frontend", "CheckoutModal.tsx", "ui", "ui", 4.0, 130, 0.0, {"react", "modal"}),
            # Test
            CodeNode("node_auth_test", "auth_race_test.ts", "test", "test", 3.0, 80, 0.0, {"test", "unit"}),
        ]

        edges = [
            CodeEdge("node_db", "node_user", "imports", 1.0),
            CodeEdge("node_cache", "node_auth", "calls", 1.2),
            CodeEdge("node_user", "node_auth", "imports", 1.0),
            CodeEdge("node_auth", "node_order_svc", "calls", 1.5),
            CodeEdge("node_db", "node_order_svc", "calls", 1.3),
            CodeEdge("node_payment_svc", "node_order_svc", "imports", 1.1),
            CodeEdge("node_order_svc", "node_api_router", "calls", 1.4),
            CodeEdge("node_api_router", "node_frontend", "calls", 1.2),
            CodeEdge("node_auth", "node_auth_test", "tests", 1.0),
        ]

        personas = [
            AgentPersona("npc_wizard", "Archmage Gandalf.ts", "Senior Architect Wizard", "mystical_authoritative", "Explains system design", affinity_layers={"domain", "data"}),
            AgentPersona("npc_rogue", "Shadow Rogue CVE", "Security Rogue", "shadow_cunning", "Challenges auth holes", affinity_layers={"api", "domain"}),
            AgentPersona("npc_smith", "Thorin the Builder", "DevOps Blacksmith", "boisterous_industrial", "Hammers CI/CD pipelines", affinity_layers={"infra", "data"}),
            AgentPersona("npc_boss", "The Race-Condition Golem", "Corrupted Boss", "menacing_glitch", "Corrupts concurrent transactions", affinity_layers={"service"}),
        ]

        # 1. Induce Skill Tree (P1)
        skill_res = solve_skill_tree_induction(nodes, edges, max_depth=4)

        # 2. Partition Dungeon Rooms (P2)
        dungeon_res = solve_dungeon_partitioning(nodes, edges, target_room_size=3)

        # 3. Assign NPCs to Rooms/Nodes (P3)
        npc_res = solve_npc_role_assignment(personas, nodes, dungeon_res.rooms)

        # 4. Synthesize Quest & Boss Battle (P4)
        quest_res = solve_quest_steiner_synthesis(
            nodes=nodes,
            edges=edges,
            start_node_id="node_db",
            target_boss_id="node_order_svc"
        )

        return WorldState(
            repo_name=repo_name,
            player_level=1,
            player_xp=150,
            player_mana=500,
            skill_tree=skill_res,
            dungeon=dungeon_res,
            npc_assignment=npc_res,
            active_quests=[quest_res.quest],
            personas=personas,
            nodes=nodes,
            edges=edges
        )

    @staticmethod
    def scan_local_directory(directory_path: str, max_files: Optional[int] = 50, *,
                             cache_path: Optional[str] = None, cache_max_entries: int = 10000) -> WorldState:
        """Scans an actual directory on disk and converts it into a playable RPG world."""
        repo_name = os.path.basename(os.path.abspath(directory_path))
        nodes: List[CodeNode] = []
        edges: List[CodeEdge] = []

        summaries = []
        for idx, summary in enumerate(iter_repository_summaries(
                directory_path, max_files, cache_path=cache_path,
                cache_max_entries=cache_max_entries)):
            summaries.append(summary)
            f = summary["path"]
            f_lower = f.lower()
            if "test" in f_lower:
                layer = "test"
            elif any(k in f_lower for k in ["api", "route", "controller", "endpoint"]):
                layer = "api"
            elif any(k in f_lower for k in ["service", "manager", "handler"]):
                layer = "service"
            elif any(k in f_lower for k in ["model", "schema", "entity", "type"]):
                layer = "domain"
            elif any(k in f_lower for k in ["db", "sql", "store", "repo"]):
                layer = "data"
            elif any(k in f_lower for k in ["config", "docker", "util", "tool", "infra"]):
                layer = "infra"
            elif any(k in f_lower for k in ["ui", "component", "view", "page", "modal"]):
                layer = "ui"
            else:
                layer = "domain"

            nid = f"file_{idx:02d}"
            nodes.append(CodeNode(
                node_id=nid,
                name=f,
                kind="file",
                layer=layer,
                complexity=summary["complexity"],
                lines_of_code=summary["lines_of_code"],
                vulnerability_score=0.0,
                tags={layer, summary["analysis"]}
            ))

        if not nodes:
            return RepoRPGGenerator.generate_synthetic_world(repo_name=repo_name)
        node_ids = {node.name: node.node_id for node in nodes}
        edges = [CodeEdge(source, target, "imports", 1.0)
                 for source, target in resolve_python_imports(summaries, node_ids)]

        personas = [
            AgentPersona("npc_wizard", "Master of Architecture", "Senior Architect Wizard", "mystical_authoritative", "Explains system design", affinity_layers={"domain", "data"}),
            AgentPersona("npc_rogue", "Shadow Auditor", "Security Rogue", "shadow_cunning", "Challenges auth holes", affinity_layers={"api", "domain"}),
            AgentPersona("npc_smith", "DevOps Forgemaster", "DevOps Blacksmith", "boisterous_industrial", "Hammers CI/CD pipelines", affinity_layers={"infra", "data"}),
            AgentPersona("npc_boss", "The Spaghetti Hydra", "Corrupted Boss", "menacing_glitch", "Corrupts codebase invariants", affinity_layers={"service"}),
        ]

        skill_res = solve_skill_tree_induction(nodes, edges, max_depth=5)
        dungeon_res = solve_dungeon_partitioning(nodes, edges, target_room_size=4)
        npc_res = solve_npc_role_assignment(personas, nodes, dungeon_res.rooms)

        start_id = nodes[0].node_id
        boss_id = nodes[-1].node_id
        quest_res = solve_quest_steiner_synthesis(nodes, edges, start_id, boss_id)

        return WorldState(
            repo_name=repo_name,
            player_level=1,
            player_xp=100,
            player_mana=500,
            skill_tree=skill_res,
            dungeon=dungeon_res,
            npc_assignment=npc_res,
            active_quests=[quest_res.quest],
            personas=personas,
            nodes=nodes,
            edges=edges
        )

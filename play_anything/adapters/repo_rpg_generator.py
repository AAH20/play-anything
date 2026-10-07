"""Repo-to-RPG World Generator Adapter.

Transforms any raw file directory or Git repository into a fully playable RPG World State:
- Induces hierarchical skill tree DAGs.
- Partitions files into thematic dungeon rooms under fog-of-war.
- Populates rooms with autonomous voice-enabled NPCs.
- Synthesizes dynamic quests and boss fights.
"""
import os
import stat
import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Any
from .repository_index import (
    DEFAULT_MAX_SOURCE_BYTES,
    PythonImportResolver,
    iter_repository_summaries,
)
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

_EMPTY_SCAN_FALLBACK_TAG = "provenance:synthetic_fallback:no_analyzable_files"


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
    analysis: Optional[Dict[str, Any]] = None


class RepoRPGGenerator:
    """Compiles code repositories into living, playable RPG worlds."""

    @staticmethod
    def _validate_total_source_budget(value):
        if value is not None and (type(value) is not int or not 0 <= value < sys.maxsize):
            raise ValueError(f"max_total_source_bytes must be an integer from 0 to {sys.maxsize - 1}, or None")

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
                             cache_path: Optional[str] = None, cache_max_entries: int = 10000,
                             max_file_bytes: Optional[int] = DEFAULT_MAX_SOURCE_BYTES,
                             max_total_source_bytes: Optional[int] = None) -> WorldState:
        """Scan a directory; source files over 2 MiB are inventoried without parsing by default.

        Set max_file_bytes=None to disable the per-file source-size limit.
        """
        RepoRPGGenerator._validate_total_source_budget(max_total_source_bytes)
        if max_files is not None and (type(max_files) is not int or max_files < 1):
            raise ValueError("max_files must be a positive integer or None")
        directory_stat = os.stat(directory_path)
        if not stat.S_ISDIR(directory_stat.st_mode):
            raise NotADirectoryError(directory_path)
        repo_name = os.path.basename(os.path.abspath(directory_path))
        nodes: List[CodeNode] = []
        edges: List[CodeEdge] = []

        import_resolver = PythonImportResolver()
        analysis_counts = {}
        source_bytes_read = 0
        source_budget_exhausted = False
        source_budget_exceeded_files = 0
        file_limit_reached = False
        # With a configured budget, inspect one extra summary to know whether
        # the world's existing max_files limit actually omitted a file. That
        # read is charged against the same aggregate byte budget and is not
        # included in the materialized world.
        iterator_limit = (max_files + 1 if max_total_source_bytes is not None and
                          max_files is not None else max_files)
        summaries = iter_repository_summaries(
                directory_path, iterator_limit, cache_path=cache_path,
                cache_max_entries=cache_max_entries,
                max_file_bytes=max_file_bytes,
                max_total_source_bytes=max_total_source_bytes,
                include_source_metrics=max_total_source_bytes is not None)
        try:
            for idx, summary in enumerate(summaries):
                if max_total_source_bytes is not None:
                    source_bytes_read = summary["source_bytes_read"]
                    source_budget_exhausted = summary["source_budget_exhausted"]
                    source_budget_exceeded_files = summary["source_budget_exceeded_files"]
                if max_files is not None and idx >= max_files:
                    file_limit_reached = True
                    break

                f = summary["path"]
                analysis = summary["analysis"]
                analysis_counts[analysis] = analysis_counts.get(analysis, 0) + 1
                import_resolver.add_summary(summary)
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
        finally:
            close = getattr(summaries, "close", None)
            if close is not None:
                close()

        if not nodes:
            world = RepoRPGGenerator.generate_synthetic_world(repo_name=repo_name)
            for node in world.nodes:
                node.tags.add(_EMPTY_SCAN_FALLBACK_TAG)
            if max_total_source_bytes is not None:
                world.analysis = {
                    "source_kind": "synthetic_fallback",
                    "status": "empty",
                    "file_count": 0,
                    "analysis_counts": {},
                    "source_bytes_read": source_bytes_read,
                    "source_budget_bytes": max_total_source_bytes,
                    "source_budget_exhausted": source_budget_exhausted,
                    "source_budget_exceeded_files": source_budget_exceeded_files,
                    "source_metrics_available": True,
                    "file_limit": max_files,
                    "file_limit_reached": False,
                    "world_materialized_in_memory": True,
                }
            return world
        node_ids = {node.name: node.node_id for node in nodes}
        edges = [CodeEdge(source, target, "imports", 1.0)
                 for source, target in import_resolver.resolve(node_ids)]

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

        partial_kinds = {"python_parse_error", "source_too_large", "source_budget_exceeded",
                         "unreadable_file", "unparsed_language"}
        partial = file_limit_reached or any(analysis_counts.get(kind, 0) for kind in partial_kinds)
        analysis_metadata = None
        if max_total_source_bytes is not None:
            analysis_metadata = {
                "source_kind": "repository",
                "status": "partial" if partial else "complete",
                "file_count": len(nodes),
                "analysis_counts": analysis_counts,
                "source_bytes_read": source_bytes_read,
                "source_budget_bytes": max_total_source_bytes,
                "source_budget_exhausted": source_budget_exhausted,
                "source_budget_exceeded_files": source_budget_exceeded_files,
                "source_metrics_available": True,
                "file_limit": max_files,
                "file_limit_reached": file_limit_reached,
                "world_materialized_in_memory": True,
            }

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
            edges=edges,
            analysis=analysis_metadata,
        )

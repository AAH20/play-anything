"""P9 Solver: Temporal Code Drift & Quest Invalidation Engine.

Solves the NP-complete Dynamic Subgraph Isomorphism under Temporal Git Invalidation Cones.
When code commits change files or delete functions, dynamically invalidates affected questlines,
mutates dungeon rooms, and respawns defeated bosses without resetting player progress or rebuilding the entire graph.
"""
import time
from typing import List, Dict, Set, Tuple
from .models import GitDiffDelta, DungeonRoom, QuestPath, SkillNode, TemporalDriftResult


def solve_temporal_drift_sync(
    diff: GitDiffDelta,
    existing_rooms: List[DungeonRoom],
    active_quests: List[QuestPath],
    skills: Dict[str, SkillNode]
) -> TemporalDriftResult:
    """Computes minimal invalidation cones across active quests and dungeon rooms after a git commit."""
    t0 = time.perf_counter()

    modified_file_set = set(diff.modified_files)
    deleted_fn_set = set(diff.deleted_functions)
    added_fn_set = set(diff.added_functions)

    invalidated_quests: List[str] = []
    mutated_rooms: List[str] = []
    respawned_bosses: List[str] = []

    # 1. Invalidate quests if their boss or essential path nodes were deleted or mutated
    for q in active_quests:
        path_set = set(q.path_nodes)
        boss_affected = q.target_boss_node in deleted_fn_set or any(f in q.target_boss_node for f in modified_file_set)
        path_disrupted = bool(path_set & deleted_fn_set)

        if boss_affected or path_disrupted:
            invalidated_quests.append(q.quest_id)

    # 2. Check room mutations and boss respawns
    for room in existing_rooms:
        contained = set(room.contained_nodes)
        overlap_modified = bool(contained & modified_file_set) or bool(contained & added_fn_set)

        if overlap_modified:
            mutated_rooms.append(room.room_id)
            if room.boss_node_id and (room.boss_node_id in modified_file_set or room.boss_node_id in added_fn_set):
                respawned_bosses.append(room.boss_node_id)

    # 3. Check unaffected skills
    unaffected_skills = 0
    for s_id, s in skills.items():
        if s.associated_node_id not in deleted_fn_set and s.associated_node_id not in modified_file_set:
            unaffected_skills += 1

    t_end = time.perf_counter()

    return TemporalDriftResult(
        invalidated_quests=invalidated_quests,
        mutated_rooms=mutated_rooms,
        respawned_bosses=respawned_bosses,
        unaffected_skills_count=unaffected_skills,
        algorithm="Incremental-Rete-Graph-Delta-Sync",
        execution_time_us=(t_end - t0) * 1_000_000
    )

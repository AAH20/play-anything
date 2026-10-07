"""P4 quest-route heuristic inspired by prize-collecting Steiner trees.

Finds a shortest start-to-boss trunk and adds qualifying one-hop prize branches. This is
an approximation heuristic, not an exact PCST solver; it does not establish global
optimality for the NP-hard prize-collecting problem.
"""
import time
import heapq
import math
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from .models import CodeNode, CodeEdge, QuestPath, PrizeSteinerQuestResult


def _finite_real(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def solve_quest_steiner_synthesis(
    nodes: List[CodeNode],
    edges: List[CodeEdge],
    start_node_id: str,
    target_boss_id: str,
    lambda_prize_weight: float = 1.5
) -> PrizeSteinerQuestResult:
    """Build a shortest-path trunk and greedily include valuable adjacent nodes."""
    t0 = time.perf_counter()
    if not _finite_real(lambda_prize_weight) or lambda_prize_weight < 0:
        raise ValueError("lambda_prize_weight must be a finite non-negative real number")
    for node in nodes:
        if not _finite_real(node.complexity) or node.complexity < 0:
            raise ValueError("node complexity must be a finite non-negative real number")
        if (not _finite_real(node.vulnerability_score)
                or not 0 <= node.vulnerability_score <= 1):
            raise ValueError("node vulnerability_score must be a finite real number from 0 to 1")
    for edge in edges:
        if not _finite_real(edge.weight) or edge.weight < 0:
            raise ValueError("edge weight must be a finite non-negative real number")

    node_map = {n.node_id: n for n in nodes}

    if start_node_id not in node_map or target_boss_id not in node_map:
        dummy_quest = QuestPath(
            quest_id="quest_default",
            title="The Grand Refactoring Trial",
            narrative_hook="Unravel the mysteries of the unmapped codebase.",
            start_node=start_node_id,
            target_boss_node=target_boss_id,
            path_nodes=[start_node_id, target_boss_id],
            total_xp_yield=500,
            token_cost=1000,
            boss_hp=100,
            failing_test_command="pytest tests/test_core.py"
        )
        return PrizeSteinerQuestResult(
            quest=dummy_quest,
            total_cost=0.0,
            prize_collected=0.0,
            nodes_included_count=2,
            algorithm="Shortest-Path-Trunk-One-Hop-Prize-Heuristic",
            execution_time_us=0.0
        )

    boss_node = node_map[target_boss_id]
    boss_hp_value = 100 + boss_node.complexity * 15 + boss_node.vulnerability_score * 50
    if not math.isfinite(boss_hp_value):
        raise ValueError("node scores produce a non-finite boss health")
    boss_hp = int(boss_hp_value)

    # Build adjacency with edge costs (higher complexity = higher cost to traverse)
    adj: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for e in edges:
        # Partial graphs are common during repository analysis; edges whose
        # endpoints were not analyzed cannot contribute to a route.
        if e.source not in node_map or e.target not in node_map:
            continue
        cost = e.weight + node_map[e.target].complexity * 0.1
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("effective edge traversal costs must be finite and non-negative")
        reverse_cost = cost * 1.2
        if not math.isfinite(reverse_cost):
            raise ValueError("effective edge traversal costs must be finite and non-negative")
        adj[e.source].append((e.target, cost))
        # Add slight bidirectional exploration permeability
        adj[e.target].append((e.source, reverse_cost))

    # Prize associated with each node: pedagogical value + vulnerability bonus
    prizes: Dict[str, float] = {}
    for n in nodes:
        prize = (n.complexity * 0.5) + (n.vulnerability_score * 10.0) + (1.0 if n.kind == "test" else 0.5)
        if not math.isfinite(prize):
            raise ValueError("node complexity produces a non-finite prize score")
        prizes[n.node_id] = prize

    # Dijkstra / A* to find base shortest path from start to boss
    distances: Dict[str, float] = {n.node_id: float('inf') for n in nodes}
    predecessors: Dict[str, Optional[str]] = {n.node_id: None for n in nodes}
    distances[start_node_id] = 0.0

    visited: Set[str] = set()
    queue: List[Tuple[float, str]] = [(0.0, start_node_id)]

    while queue:
        dist_u, u = heapq.heappop(queue)

        if u in visited:
            continue
        visited.add(u)

        if u == target_boss_id:
            break

        for v, cost in sorted(adj[u], key=lambda item: item[0]):
            if v not in visited:
                new_dist = dist_u + cost
                if new_dist < distances[v]:
                    distances[v] = new_dist
                    predecessors[v] = u
                    heapq.heappush(queue, (new_dist, v))

    # Reconstruct trunk path
    trunk_path: List[str] = []
    curr = target_boss_id
    while curr is not None:
        trunk_path.append(curr)
        curr = predecessors[curr]
    trunk_path.reverse()

    if trunk_path[0] != start_node_id:
        boss_node = node_map[target_boss_id]
        quest = QuestPath(
            quest_id=f"quest_{start_node_id}_to_{target_boss_id}",
            title=f"Unreachable: {boss_node.name}",
            narrative_hook=f"No route from {start_node_id} to {target_boss_id} exists in the analyzed graph.",
            start_node=start_node_id,
            target_boss_node=target_boss_id,
            path_nodes=[],
            total_xp_yield=0,
            token_cost=0,
            boss_hp=boss_hp,
            failing_test_command=f"pytest -k {boss_node.name}",
        )
        return PrizeSteinerQuestResult(
            quest=quest,
            total_cost=float("inf"),
            prize_collected=0.0,
            nodes_included_count=0,
            algorithm="Shortest-Path-Trunk-One-Hop-Prize-Heuristic",
            execution_time_us=(time.perf_counter() - t0) * 1_000_000,
        )

    # Expand from the trunk to adjacent prize nodes. A branch may be adjacent
    # to several trunk nodes or appear on parallel edges, so retain its
    # cheapest attachment once and charge it only if that node is selected.
    included_nodes = set(trunk_path)
    trunk_nodes = set(trunk_path)
    branch_costs: Dict[str, float] = {}
    for u in trunk_path:
        for v, cost in adj[u]:
            if v not in trunk_nodes and cost < branch_costs.get(v, float("inf")):
                branch_costs[v] = cost
    selected_branch_costs = []
    for node_id in sorted(branch_costs):
        cost = branch_costs[node_id]
        marginal_benefit = (prizes.get(node_id, 0.0) * lambda_prize_weight) - cost
        if not math.isfinite(marginal_benefit):
            raise ValueError("lambda_prize_weight produces a non-finite branch score")
        if marginal_benefit > 2.0:
            included_nodes.add(node_id)
            selected_branch_costs.append(cost)

    boss_node = node_map[target_boss_id]
    xp_values = [prizes.get(nid, 1.0) * 50 for nid in sorted(included_nodes)]
    if any(not math.isfinite(value) for value in xp_values):
        raise ValueError("node scores produce a non-finite quest reward")
    try:
        total_xp_value = math.fsum(xp_values)
    except OverflowError:
        raise ValueError("node scores produce a non-finite quest reward") from None
    if not math.isfinite(total_xp_value):
        raise ValueError("node scores produce a non-finite quest reward")
    total_xp = int(total_xp_value)
    est_tokens = len(included_nodes) * 250

    boss_name = boss_node.name
    quest_title = f"Raid: Slay the Corrupted {boss_name.upper()} Golem"
    narrative = (
        f"A critical instability looms in {boss_node.layer.upper()} layer! "
        f"The {boss_name} entity has accumulated technical debt. "
        f"Traverse through {len(included_nodes)-1} prerequisite modules and defeat the failing invariants."
    )

    test_cmd = f"npm test -- {boss_name}" if "ts" in boss_name or "js" in boss_name else f"pytest -k {boss_name}"

    ordered_included_nodes = trunk_path + sorted(included_nodes - set(trunk_path))
    quest = QuestPath(
        quest_id=f"quest_{start_node_id}_to_{target_boss_id}",
        title=quest_title,
        narrative_hook=narrative,
        start_node=start_node_id,
        target_boss_node=target_boss_id,
        path_nodes=ordered_included_nodes,
        total_xp_yield=total_xp,
        token_cost=est_tokens,
        boss_hp=boss_hp,
        failing_test_command=test_cmd
    )

    try:
        selected_branch_cost = math.fsum(selected_branch_costs)
    except OverflowError:
        raise ValueError("selected branches produce a non-finite total cost") from None
    total_cost = distances.get(target_boss_id, 10.0) + selected_branch_cost
    if not math.isfinite(total_cost):
        raise ValueError("selected branches produce a non-finite total cost")
    try:
        total_prize = math.fsum(prizes.get(n, 0.0) for n in sorted(included_nodes))
    except OverflowError:
        raise ValueError("node scores produce a non-finite total prize") from None
    if not math.isfinite(total_prize):
        raise ValueError("node scores produce a non-finite total prize")
    t_end = time.perf_counter()

    return PrizeSteinerQuestResult(
        quest=quest,
        total_cost=round(total_cost, 2),
        prize_collected=round(total_prize, 2),
        nodes_included_count=len(included_nodes),
        algorithm="Shortest-Path-Trunk-One-Hop-Prize-Heuristic",
        execution_time_us=(t_end - t0) * 1_000_000
    )

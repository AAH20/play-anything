"""Deterministic list-scheduling heuristic for sandbox actions.

Produces planned start times under release, dependency, and exclusive-resource
constraints. It does not execute actions or prove globally minimal makespan.
Cycles are reported through ``deadlock_free=False``.
"""
import time
from typing import List, Dict
from collections import defaultdict
from .models import SandboxAction, DisjunctiveSandboxResult


def solve_sandbox_scheduling(
    actions: List[SandboxAction]
) -> DisjunctiveSandboxResult:
    """Plan valid actions; reject ambiguous IDs, timing, and missing dependencies."""
    t0 = time.perf_counter()
    if not actions:
        return DisjunctiveSandboxResult(
            schedule={},
            makespan_ms=0,
            deadlock_free=True,
            algorithm="Deterministic-Precedence-Resource-List-Scheduler",
            execution_time_us=0.0
        )

    action_map = {}
    for action in actions:
        if not isinstance(action.action_id, str) or not action.action_id:
            raise ValueError('Action IDs must be nonempty strings.')
        if action.action_id in action_map:
            raise ValueError('Action IDs must be unique.')
        if not isinstance(action.resource_id, str) or not action.resource_id:
            raise ValueError('Resource IDs must be nonempty strings.')
        if any(type(value) is not int or value < 0
               for value in (action.duration_ms, action.release_ms)):
            raise ValueError('Duration and release must be nonnegative integer milliseconds.')
        action_map[action.action_id] = action
    for action in actions:
        if any(dependency not in action_map for dependency in action.precedence_deps):
            raise ValueError('Every precedence dependency must identify a supplied action.')

    # Precedence adjacency
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {a.action_id: 0 for a in actions}

    for a in actions:
        for dep in a.precedence_deps:
            if dep in action_map:
                adj[dep].append(a.action_id)
                in_degree[a.action_id] += 1

    # Ready queue based on precedence
    ready = [a_id for a_id, deg in in_degree.items() if deg == 0]
    # Resource availability track: resource_id -> next available time
    resource_free_at: Dict[str, int] = defaultdict(int)
    # Action completion times: action_id -> finish_time_ms
    finish_times: Dict[str, int] = {}
    start_times: Dict[str, int] = {}

    while ready:
        # Sort ready actions by earliest release date and duration
        ready.sort(key=lambda a_id: (action_map[a_id].release_ms,
                                    action_map[a_id].duration_ms, a_id))
        curr_id = ready.pop(0)
        curr_action = action_map[curr_id]

        # Earliest start is max of:
        # 1. Action release date
        # 2. Finish times of all precedence dependencies
        # 3. Next free time of required sandbox resource
        dep_finish = max([finish_times.get(d, 0) for d in curr_action.precedence_deps], default=0)
        res_free = resource_free_at[curr_action.resource_id]

        start_time = max(curr_action.release_ms, dep_finish, res_free)
        finish_time = start_time + curr_action.duration_ms

        start_times[curr_id] = start_time
        finish_times[curr_id] = finish_time
        resource_free_at[curr_action.resource_id] = finish_time

        # Update downstream dependents
        for dependent in adj[curr_id]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                ready.append(dependent)

    deadlock_free = len(start_times) == len(actions)
    makespan = max(finish_times.values()) if finish_times else 0
    t_end = time.perf_counter()

    return DisjunctiveSandboxResult(
        schedule=start_times,
        makespan_ms=makespan,
        deadlock_free=deadlock_free,
        algorithm="Deterministic-Precedence-Resource-List-Scheduler",
        execution_time_us=(t_end - t0) * 1_000_000
    )

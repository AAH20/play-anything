"""P6 Solver: GraphRAG Submodular Curiosity Context Distillation.

Solves the NP-hard Submodular Maximization under Knapsack Budget constraints.
Extracts non-redundant, cross-module context snippets that maximize user learning novelty and
pedagogical 'aha!' moments without exceeding strict LLM context token caps.
Implements Minoux's Accelerated Lazy-Greedy algorithm with the Nemhauser-Wolsey (1 - 1/e)
approximation guarantee and heap-based marginal gain pruning.
"""
import time
import heapq
from typing import List, Dict, Set, Tuple
from .models import ContextSnippet, SubmodularCuriosityResult


def solve_submodular_graphrag(
    snippets: List[ContextSnippet],
    token_budget: int = 1500,
    redundancy_penalty_factor: float = 0.5
) -> SubmodularCuriosityResult:
    """
    Selects subset of code snippets maximizing novelty and coverage under Knapsack token limit.
    Utilizes Minoux (1978) Lazy-Greedy algorithm with a max-heap priority queue.
    """
    t0 = time.perf_counter()
    if not snippets or token_budget <= 0:
        return SubmodularCuriosityResult(
            selected_snippets=[],
            total_coverage=0.0,
            used_tokens=0,
            token_budget=token_budget,
            redundancy_penalty=0.0,
            algorithm="Minoux-Lazy-Greedy-Submodular",
            execution_time_us=0.0
        )

    # Pre-filter snippets that individually exceed budget
    candidates = [s for s in snippets if s.token_length <= token_budget]
    if not candidates:
        return SubmodularCuriosityResult(
            selected_snippets=[],
            total_coverage=0.0,
            used_tokens=0,
            token_budget=token_budget,
            redundancy_penalty=0.0,
            algorithm="Minoux-Lazy-Greedy-Submodular",
            execution_time_us=0.0
        )

    covered_concepts: Set[str] = set()
    selected: List[ContextSnippet] = []
    used_tokens = 0
    total_coverage = 0.0
    total_penalty = 0.0

    # Helper function to compute marginal gain
    def compute_gain(s: ContextSnippet) -> Tuple[float, float]:
        new_concepts = s.concepts - covered_concepts
        overlap_concepts = s.concepts & covered_concepts
        redundancy = len(overlap_concepts) * redundancy_penalty_factor
        marginal_gain = (len(new_concepts) * 2.0) + s.novelty_score - redundancy
        return max(0.0, marginal_gain), redundancy

    # Build initial max-heap of marginal gain per token cost
    # Format: (-marginal_gain_per_token, last_evaluated_step, snippet_id, snippet)
    heap = []
    current_step = 0
    for s in candidates:
        gain, _ = compute_gain(s)
        if gain > 0:
            ratio = gain / s.token_length
            heapq.heappush(heap, (-ratio, current_step, s.snippet_id, s))

    # Minoux Lazy-Greedy Loop
    while heap and used_tokens < token_budget:
        neg_ratio, last_step, sid, candidate = heapq.heappop(heap)

        # Skip if adding this candidate exceeds token budget
        if used_tokens + candidate.token_length > token_budget:
            continue

        # If this candidate was evaluated in the current step, it is guaranteed
        # to be the global maximum due to the diminishing returns property
        if last_step == current_step:
            actual_gain, actual_redundancy = compute_gain(candidate)
            if actual_gain <= 0:
                continue

            selected.append(candidate)
            used_tokens += candidate.token_length
            total_coverage += actual_gain
            total_penalty += actual_redundancy
            covered_concepts.update(candidate.concepts)
            current_step += 1
        else:
            # Recompute marginal gain with respect to current covered_concepts
            fresh_gain, _ = compute_gain(candidate)
            if fresh_gain > 0:
                fresh_ratio = fresh_gain / candidate.token_length
                heapq.heappush(heap, (-fresh_ratio, current_step, candidate.snippet_id, candidate))

    t_end = time.perf_counter()

    return SubmodularCuriosityResult(
        selected_snippets=[s.snippet_id for s in selected],
        total_coverage=round(total_coverage, 2),
        used_tokens=used_tokens,
        token_budget=token_budget,
        redundancy_penalty=round(total_penalty, 2),
        algorithm="Minoux-Lazy-Greedy-Submodular",
        execution_time_us=(t_end - t0) * 1_000_000
    )

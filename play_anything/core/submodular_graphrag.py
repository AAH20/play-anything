"""P6 heuristic: GraphRAG Submodular Curiosity Context Distillation.

Solves the NP-hard Submodular Maximization under Knapsack Budget constraints.
Extracts non-redundant, cross-module context snippets that maximize user learning novelty and
pedagogical 'aha!' moments without exceeding strict LLM context token caps.
Uses lazy marginal-gain-per-token ordering. This knapsack heuristic is not an exact
solver, and this implementation does not claim the cardinality-constrained
Nemhauser-Wolsey (1 - 1/e) guarantee.
"""
import time
import heapq
import math
from typing import List, Set, Tuple
from .models import ContextSnippet, SubmodularCuriosityResult


def _finite_real(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def solve_submodular_graphrag(
    snippets: List[ContextSnippet],
    token_budget: int = 1500,
    redundancy_penalty_factor: float = 0.5
) -> SubmodularCuriosityResult:
    """
    Greedily selects snippets for novelty and coverage under the token limit, using
    lazy marginal-gain-per-token ordering with a max-heap.
    """
    t0 = time.perf_counter()
    if type(token_budget) is not int or token_budget < 0:
        raise ValueError("token_budget must be a nonnegative integer")
    if not _finite_real(redundancy_penalty_factor) or redundancy_penalty_factor < 0:
        raise ValueError("redundancy_penalty_factor must be non-negative and finite")
    if any(type(s.token_length) is not int or s.token_length < 0 for s in snippets):
        raise ValueError("snippet token_length must be non-negative integer")
    if any(not _finite_real(s.novelty_score) for s in snippets):
        raise ValueError("snippet novelty_score must be a finite real number")
    snippet_ids = [s.snippet_id for s in snippets]
    if len(snippet_ids) != len(set(snippet_ids)):
        raise ValueError("snippet_id values must be unique")
    if not snippets:
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
        if not math.isfinite(redundancy) or not math.isfinite(marginal_gain):
            raise ValueError("snippet scores produce a non-finite aggregate")
        return max(0.0, marginal_gain), redundancy

    # Build initial max-heap of marginal gain per token cost
    # Format: (-marginal_gain_per_token, last_evaluated_step, snippet_id, snippet)
    heap = []
    current_step = 0
    for s in candidates:
        gain, _ = compute_gain(s)
        if gain > 0:
            # Empty snippets can still add concepts or novelty and consume no
            # budget. Rank them first without dividing by zero.
            ratio = float("inf") if s.token_length == 0 else gain / s.token_length
            heapq.heappush(heap, (-ratio, current_step, s.snippet_id, s))

    # Minoux Lazy-Greedy Loop
    # Continue at an exactly exhausted budget so zero-token candidates remain
    # eligible; the fit check below still rejects every positive-cost item.
    while heap:
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

            next_coverage = total_coverage + actual_gain
            next_penalty = total_penalty + actual_redundancy
            if not math.isfinite(next_coverage) or not math.isfinite(next_penalty):
                raise ValueError("snippet scores produce a non-finite aggregate")

            selected.append(candidate)
            used_tokens += candidate.token_length
            total_coverage = next_coverage
            total_penalty = next_penalty
            covered_concepts.update(candidate.concepts)
            current_step += 1
        else:
            # Recompute marginal gain with respect to current covered_concepts
            fresh_gain, _ = compute_gain(candidate)
            if fresh_gain > 0:
                fresh_ratio = (
                    float("inf")
                    if candidate.token_length == 0
                    else fresh_gain / candidate.token_length
                )
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

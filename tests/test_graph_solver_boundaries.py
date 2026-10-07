"""Boundary and determinism regressions for the graph solvers."""
import unittest
from dataclasses import replace

from play_anything.core.models import CodeEdge, CodeNode, ContextSnippet
from play_anything.core.quest_steiner_synthesizer import solve_quest_steiner_synthesis
from play_anything.core.submodular_graphrag import solve_submodular_graphrag


class TestSubmodularBoundaryBehavior(unittest.TestCase):
    def test_zero_token_snippets_are_selectable_without_division_by_zero(self):
        snippet = ContextSnippet("free", "m", "", 0, 1.0, {"concept"})

        result = solve_submodular_graphrag([snippet], token_budget=1)

        self.assertEqual(result.selected_snippets, ["free"])
        self.assertEqual(result.used_tokens, 0)

    def test_zero_token_budget_still_accepts_zero_token_snippets(self):
        snippet = ContextSnippet("free", "m", "", 0, 1.0, {"concept"})

        result = solve_submodular_graphrag([snippet], token_budget=0)

        self.assertEqual(result.selected_snippets, ["free"])
        self.assertEqual(result.used_tokens, 0)

    def test_zero_budget_accepts_an_empty_candidate_list(self):
        result = solve_submodular_graphrag([], token_budget=0)

        self.assertEqual(result.selected_snippets, [])
        self.assertEqual(result.used_tokens, 0)

    def test_negative_token_budget_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "token_budget must be a nonnegative integer"):
            solve_submodular_graphrag([], token_budget=-1)

    def test_duplicate_snippet_ids_are_rejected_as_ambiguous(self):
        snippets = [
            ContextSnippet("same", "a", "first", 1, 1.0, {"a"}),
            ContextSnippet("same", "b", "second", 1, 1.0, {"b"}),
        ]

        with self.assertRaisesRegex(ValueError, "snippet_id.*unique"):
            solve_submodular_graphrag(snippets)

    def test_negative_token_length_is_rejected(self):
        snippet = ContextSnippet("bad", "m", "text", -1, 1.0, {"concept"})

        with self.assertRaisesRegex(ValueError, "token_length must be non-negative"):
            solve_submodular_graphrag([snippet])

    def test_bool_and_fractional_token_lengths_are_rejected(self):
        for value in (True, 1.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "token_length"):
                snippet = ContextSnippet("bad", "m", "text", value, 1.0, {"concept"})
                solve_submodular_graphrag([snippet])

    def test_bool_and_fractional_budgets_are_rejected(self):
        snippet = ContextSnippet("s", "m", "text", 1, 1.0, {"concept"})
        for value in (True, 1.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "token_budget"):
                solve_submodular_graphrag([snippet], token_budget=value)

    def test_nonnumeric_or_boolean_penalty_is_rejected_as_value_error(self):
        snippet = ContextSnippet("s", "m", "text", 1, 1.0, {"concept"})
        for value in (True, "high"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "redundancy_penalty_factor"):
                solve_submodular_graphrag([snippet], redundancy_penalty_factor=value)

    def test_nonfinite_or_nonnumeric_novelty_is_rejected(self):
        for value in (True, "novel", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "novelty_score"):
                snippet = ContextSnippet("s", "m", "text", 1, value, {"concept"})
                solve_submodular_graphrag([snippet])

    def test_zero_novelty_score_remains_valid(self):
        snippet = ContextSnippet("s", "m", "text", 1, 0.0, {"concept"})

        result = solve_submodular_graphrag([snippet], token_budget=1)

        self.assertEqual(result.selected_snippets, ["s"])

    def test_finite_novelty_scores_with_overflowing_coverage_sum_are_rejected(self):
        snippets = [
            ContextSnippet("s1", "m1", "one", 1, 1e308, {"one"}),
            ContextSnippet("s2", "m2", "two", 1, 1e308, {"two"}),
        ]

        with self.assertRaisesRegex(ValueError, "non-finite aggregate"):
            solve_submodular_graphrag(snippets, token_budget=2)

    def test_negative_redundancy_penalty_is_rejected(self):
        snippet = ContextSnippet("s", "m", "text", 1, 1.0, {"concept"})

        with self.assertRaisesRegex(ValueError, "redundancy_penalty_factor must be non-negative"):
            solve_submodular_graphrag([snippet], redundancy_penalty_factor=-0.5)


class TestQuestSteinerBoundaryBehavior(unittest.TestCase):
    def _nodes(self):
        return [CodeNode(n, n, "module", "service", 0.0, 1) for n in ("s", "a", "b", "t")]

    def test_equal_cost_routes_use_stable_node_id_tie_break(self):
        nodes = self._nodes()
        first_edges = [
            CodeEdge("s", "b", "imports"), CodeEdge("b", "t", "imports"),
            CodeEdge("s", "a", "imports"), CodeEdge("a", "t", "imports"),
        ]
        second_edges = list(reversed(first_edges))

        first = solve_quest_steiner_synthesis(nodes, first_edges, "s", "t")
        second = solve_quest_steiner_synthesis(nodes, second_edges, "s", "t")

        self.assertEqual(first.quest.path_nodes, second.quest.path_nodes)
        self.assertEqual(first.quest.path_nodes[:3], ["s", "a", "t"])
        self.assertEqual(first.algorithm, "Shortest-Path-Trunk-One-Hop-Prize-Heuristic")

    def test_edges_with_unknown_endpoints_are_ignored(self):
        nodes = [CodeNode(n, n, "module", "service", 0.0, 1) for n in ("s", "t")]
        result = solve_quest_steiner_synthesis(
            nodes,
            [CodeEdge("s", "missing", "imports"), CodeEdge("s", "t", "imports")],
            "s",
            "t",
        )

        self.assertEqual(result.total_cost, 1.0)
        self.assertEqual(result.quest.path_nodes[:2], ["s", "t"])

    def test_negative_traversal_cost_is_rejected(self):
        nodes = [CodeNode(n, n, "module", "service", 0.0, 1) for n in ("s", "t")]

        with self.assertRaisesRegex(ValueError, "non-negative"):
            solve_quest_steiner_synthesis(
                nodes, [CodeEdge("s", "t", "imports", weight=-1.0)], "s", "t"
            )

    def test_disconnected_boss_does_not_produce_a_fake_route(self):
        nodes = [CodeNode(n, n, "module", "service", 0.0, 1) for n in ("s", "t")]

        result = solve_quest_steiner_synthesis(nodes, [], "s", "t")

        self.assertEqual(result.quest.path_nodes, [])
        self.assertEqual(result.nodes_included_count, 0)
        self.assertEqual(result.total_cost, float("inf"))
        self.assertEqual(result.algorithm, "Shortest-Path-Trunk-One-Hop-Prize-Heuristic")

    def test_missing_endpoint_uses_same_heuristic_algorithm_label(self):
        result = solve_quest_steiner_synthesis([], [], "missing-start", "missing-boss")

        self.assertEqual(result.algorithm, "Shortest-Path-Trunk-One-Hop-Prize-Heuristic")

    def test_total_cost_includes_each_selected_shared_branch_once(self):
        nodes = [
            CodeNode("s", "start", "module", "service", 0.0, 1),
            CodeNode("m", "middle", "module", "service", 0.0, 1),
            CodeNode("t", "boss", "module", "service", 0.0, 1),
            CodeNode("b", "prize", "module", "service", 0.0, 1, vulnerability_score=1.0),
        ]
        edges = [
            CodeEdge("s", "m", "imports", 1.0),
            CodeEdge("m", "t", "imports", 1.0),
            CodeEdge("s", "t", "imports", 10.0),
            CodeEdge("s", "b", "imports", 3.0),
            CodeEdge("m", "b", "imports", 2.0),
            CodeEdge("m", "b", "calls", 2.5),
            CodeEdge("m", "unmapped", "imports", 0.1),
        ]

        result = solve_quest_steiner_synthesis(nodes, edges, "s", "t")

        self.assertEqual(result.quest.path_nodes, ["s", "m", "t", "b"])
        self.assertEqual(result.nodes_included_count, 4)
        self.assertEqual(result.total_cost, 4.0)

    def test_invalid_prize_weight_is_rejected_but_zero_disables_branches(self):
        nodes = self._nodes() + [
            CodeNode("prize", "prize", "module", "service", 0.0, 1, vulnerability_score=1.0)
        ]
        edges = [CodeEdge("s", "t", "imports", 1.0), CodeEdge("s", "prize", "imports", 1.0)]
        for value in (True, "weight", float("nan"), float("inf"), -1.0):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "lambda_prize_weight"):
                solve_quest_steiner_synthesis(nodes, edges, "s", "t", lambda_prize_weight=value)

        result = solve_quest_steiner_synthesis(nodes, edges, "s", "t", lambda_prize_weight=0.0)
        self.assertNotIn("prize", result.quest.path_nodes)

    def test_invalid_node_numeric_fields_are_rejected(self):
        edges = [CodeEdge("s", "t", "imports", 1.0)]
        for field, value in (
            ("complexity", True), ("complexity", "high"), ("complexity", float("nan")),
            ("complexity", float("inf")), ("complexity", -1.0),
            ("vulnerability_score", True), ("vulnerability_score", "high"),
            ("vulnerability_score", float("nan")), ("vulnerability_score", float("inf")),
            ("vulnerability_score", -0.1), ("vulnerability_score", 1.1),
        ):
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, field):
                nodes = [
                    CodeNode("s", "start", "module", "service", 0.0, 1),
                    CodeNode("t", "target", "module", "service", 0.0, 1),
                ]
                nodes[1] = replace(nodes[1], **{field: value})
                solve_quest_steiner_synthesis(nodes, edges, "s", "t")

    def test_invalid_edge_weights_are_rejected(self):
        nodes = self._nodes()
        for value in (True, "weight", float("nan"), float("inf"), -0.1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "edge weight"):
                solve_quest_steiner_synthesis(
                    nodes, [CodeEdge("s", "t", "imports", value)], "s", "t"
                )

    def test_zero_edge_weight_is_a_valid_zero_cost_route(self):
        nodes = [CodeNode("s", "start", "module", "service", 0.0, 1),
                 CodeNode("t", "target", "module", "service", 0.0, 1)]

        result = solve_quest_steiner_synthesis(
            nodes, [CodeEdge("s", "t", "imports", 0.0)], "s", "t", lambda_prize_weight=0.0
        )

        self.assertEqual(result.total_cost, 0.0)
        self.assertEqual(result.quest.path_nodes, ["s", "t"])

    def test_derived_overflow_from_finite_complexity_is_reported_clearly(self):
        nodes = [CodeNode("s", "start", "module", "service", 0.0, 1),
                 CodeNode("t", "target", "module", "service", 1e308, 1)]

        with self.assertRaisesRegex(ValueError, "non-finite boss health"):
            solve_quest_steiner_synthesis(
                nodes, [CodeEdge("s", "t", "imports", 0.0)], "s", "t"
            )

    def test_overflowing_sum_of_finite_selected_branch_costs_is_rejected(self):
        nodes = [
            CodeNode("s", "start", "module", "service", 0.0, 1),
            CodeNode("t", "target", "module", "service", 0.0, 1),
            *(CodeNode(f"b{i}", f"branch{i}", "module", "service", 2e306, 1)
              for i in range(3)),
        ]
        edges = [CodeEdge("s", "t", "imports", 1.0)] + [
            CodeEdge("s", f"b{i}", "imports", 9.88e307) for i in range(3)
        ]

        with self.assertRaisesRegex(ValueError, "total cost"):
            solve_quest_steiner_synthesis(nodes, edges, "s", "t", lambda_prize_weight=100.0)


if __name__ == "__main__":
    unittest.main()

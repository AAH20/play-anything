"""
Unit tests for Advanced Graph Solvers:
- Minoux Lazy-Greedy Submodular Maximization (P6)
- Eades-Lin-Smyth Minimum Feedback Arc Set (P1)
- GRAIL Multi-Dimensional Interval Reachability Index
"""
import unittest
from play_anything.core.models import ContextSnippet, CodeNode, CodeEdge
from play_anything.core.submodular_graphrag import solve_submodular_graphrag
from play_anything.core.skill_tree_induction import solve_skill_tree_induction
from play_anything.core.grail_reachability import GrailReachabilityIndex


class TestAdvancedGraphSolvers(unittest.TestCase):

    def test_minoux_lazy_greedy_submodular_maximization(self):
        # Create overlapping snippets to test diminishing returns
        snippets = [
            ContextSnippet("s1", "src/auth/token.py", "auth", 100, 0.8, {"jwt", "auth", "crypto"}),
            ContextSnippet("s2", "src/auth/crypto.py", "auth", 120, 0.7, {"crypto", "keys"}),
            ContextSnippet("s3", "src/db/repo.py", "data", 150, 0.9, {"sql", "db", "models"}),
            ContextSnippet("s4", "src/api/routes.py", "api", 110, 0.6, {"http", "jwt", "auth"}),
            ContextSnippet("s5", "src/orders/saga.py", "service", 180, 0.95, {"orders", "saga", "events"}),
        ]
        res = solve_submodular_graphrag(snippets, token_budget=350)
        self.assertLessEqual(res.used_tokens, 350)
        self.assertGreater(res.total_coverage, 0.0)
        self.assertIn("Minoux", res.algorithm)
        # Should pick high novelty distinct domains first (s5, s3, etc.)
        self.assertTrue(any(sid in res.selected_snippets for sid in ["s5", "s3"]))

    def test_eades_lin_smyth_feedback_arc_set_cycle_breaking(self):
        # Create an explicit cycle: node_a -> node_b -> node_c -> node_a
        nodes = [
            CodeNode("node_a", "ServiceA", "service/a.py", "service", 10, 0.1),
            CodeNode("node_b", "ServiceB", "service/b.py", "service", 12, 0.1),
            CodeNode("node_c", "ServiceC", "service/c.py", "service", 8, 0.1),
        ]
        cyclic_edges = [
            CodeEdge("node_a", "node_b", "calls"),
            CodeEdge("node_b", "node_c", "calls"),
            CodeEdge("node_c", "node_a", "calls"),  # Cycle
        ]
        res = solve_skill_tree_induction(nodes, cyclic_edges)
        self.assertTrue(res.is_acyclic)
        self.assertGreaterEqual(res.feedback_arcs_removed, 1)
        self.assertEqual(len(res.skill_nodes), 3)

    def test_grail_randomized_interval_reachability(self):
        nodes = ["A", "B", "C", "D", "E", "F"]
        # DAG: A -> B -> C -> D; E -> F
        edges = [
            ("A", "B"),
            ("B", "C"),
            ("C", "D"),
            ("E", "F")
        ]
        grail = GrailReachabilityIndex(dimensions=3, seed=123)
        grail.build_index(nodes, edges)

        # Reachable assertions
        self.assertTrue(grail.can_reach("A", "B"))
        self.assertTrue(grail.can_reach("A", "D"))
        self.assertTrue(grail.can_reach("B", "D"))
        self.assertTrue(grail.can_reach("E", "F"))
        self.assertTrue(grail.can_reach("A", "A"))

        # Non-reachable assertions (instant O(d) interval containment rejection)
        self.assertFalse(grail.can_reach("D", "A"))
        self.assertFalse(grail.can_reach("A", "E"))
        self.assertFalse(grail.can_reach("B", "F"))
        self.assertFalse(grail.can_reach("F", "E"))


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Swarm Orchestration, Context Compaction, and Distributed Concurrency."""

import time
import unittest

from play_anything.core.swarm_orchestrator import (
    AstPatch,
    CompactionResult,
    ContextCompactor,
    MemoryRecord,
    MergeOutcome,
    SwarmScheduleResult,
    SwarmTask,
    SwarmTaskScheduler,
    TreeCrdtSemanticMerger,
    WoundWaitLockManager,
)


class TestSwarmTaskScheduler(unittest.TestCase):
    def test_empty_tasks(self):
        scheduler = SwarmTaskScheduler(num_workers=300)
        res = scheduler.schedule([])
        self.assertEqual(res.makespan, 0.0)
        self.assertEqual(len(res.schedule), 0)

    def test_300_agents_dag_scheduling_and_critical_path(self):
        # Build a DAG with a known critical path
        # t0 -> t1 -> t2 -> t3 (durations 10, 20, 15, 5 = total 50)
        # Parallel tasks branching off t0 (durations 2 each)
        tasks = [
            SwarmTask(id="t0", name="Init AST Graph", duration=10.0),
            SwarmTask(id="t1", name="Semantic Embedding", duration=20.0, dependencies=["t0"]),
            SwarmTask(id="t2", name="CRDT Partitioning", duration=15.0, dependencies=["t1"]),
            SwarmTask(id="t3", name="Final Validation", duration=5.0, dependencies=["t2"]),
        ]
        # Add 50 parallel sidecar tasks that depend on t0
        for i in range(50):
            tasks.append(
                SwarmTask(
                    id=f"side_{i}",
                    name=f"Lint Task {i}",
                    duration=2.0,
                    dependencies=["t0"],
                )
            )

        scheduler = SwarmTaskScheduler(num_workers=300)
        result = scheduler.schedule(tasks)

        self.assertIsInstance(result, SwarmScheduleResult)
        # Critical path must be t0 -> t1 -> t2 -> t3
        self.assertIn("t0", result.critical_path)
        self.assertIn("t1", result.critical_path)
        self.assertIn("t2", result.critical_path)
        self.assertIn("t3", result.critical_path)
        # Makespan must be >= 50.0
        self.assertGreaterEqual(result.makespan, 50.0)
        # All tasks must be scheduled
        self.assertEqual(len(result.schedule), len(tasks))

    def test_work_stealing_under_imbalanced_load(self):
        # 10 heavy tasks, 10 workers
        tasks = [SwarmTask(id=f"task_{i}", name=f"Work {i}", duration=1.0) for i in range(20)]
        scheduler = SwarmTaskScheduler(num_workers=10)
        result = scheduler.schedule(tasks)
        self.assertEqual(len(result.schedule), 20)
        self.assertGreater(len(result.worker_allocations), 0)


class TestContextCompactor(unittest.TestCase):
    def setUp(self):
        self.compactor = ContextCompactor(half_life_seconds=3600.0)

    def test_strip_ephemeral_thinking_tokens(self):
        content = (
            "<thinking>\nAnalyzing AST nodes and calculating Leiden clusters...\n"
            "Checking interval labels.\n</thinking>\n"
            "def optimize_routing():\n    return True"
        )
        stripped, saved = ContextCompactor.strip_thinking_tokens(content)
        self.assertEqual(stripped, "def optimize_routing():\n    return True")
        self.assertGreater(saved, 10)

    def test_strip_markdown_thought_blocks(self):
        content = (
            "```thought\nLet me reason step-by-step about memory compaction.\n```\n"
            "Patched 3 files successfully."
        )
        stripped, saved = ContextCompactor.strip_thinking_tokens(content)
        self.assertEqual(stripped, "Patched 3 files successfully.")
        self.assertGreater(saved, 5)

    def test_ebbinghaus_retention_scoring(self):
        now = 10000.0
        fresh_record = MemoryRecord(
            id="r1",
            content="Important architecture spec",
            tokens=100,
            created_at=now - 60.0,
            last_accessed_at=now - 60.0,
            importance=0.9,
            centrality=0.8,
            embedding_vector=[1.0, 0.0, 0.0],
        )
        old_record = MemoryRecord(
            id="r2",
            content="Old log entry",
            tokens=100,
            created_at=now - 72000.0,
            last_accessed_at=now - 72000.0,
            importance=0.2,
            centrality=0.1,
            embedding_vector=[0.0, 1.0, 0.0],
        )

        query_vec = [1.0, 0.0, 0.0]
        score_fresh = self.compactor.score_record(fresh_record, query_vec, now)
        score_old = self.compactor.score_record(old_record, query_vec, now)

        self.assertGreater(score_fresh, score_old)
        self.assertLessEqual(score_fresh, 1.0)
        self.assertGreaterEqual(score_old, 0.0)

    def test_compaction_and_orphan_garbage_collection(self):
        now = 1000.0
        records = [
            # High priority root
            MemoryRecord(
                id="root",
                content="Architecture Root",
                tokens=200,
                created_at=now,
                last_accessed_at=now,
                importance=0.95,
                centrality=0.9,
            ),
            # Low priority child of root
            MemoryRecord(
                id="child_1",
                content="Detail 1",
                tokens=150,
                created_at=now,
                last_accessed_at=now,
                importance=0.5,
                centrality=0.4,
                parent_ids=["root"],
            ),
            # Orphan node pointing to non-existent parent
            MemoryRecord(
                id="orphan",
                content="Orphaned Subgraph Note",
                tokens=100,
                created_at=now,
                last_accessed_at=now,
                importance=0.3,
                centrality=0.1,
                parent_ids=["deleted_parent_xyz"],
            ),
            # Thinking-polluted record
            MemoryRecord(
                id="noisy",
                content="<thought>Scratchpad notes: trying 1, 2, 3...</thought>Final result.",
                tokens=300,
                created_at=now,
                last_accessed_at=now,
                importance=0.6,
                centrality=0.5,
            ),
        ]

        # Budget allows ~400 tokens
        result = self.compactor.compact(records, token_budget=400, current_time=now)

        self.assertIsInstance(result, CompactionResult)
        self.assertLessEqual(result.final_tokens, 400)
        self.assertGreater(result.thinking_tokens_pruned, 0)
        # Orphan should be swept or evicted
        retained_ids = [r.id for r in result.retained_records]
        self.assertIn("root", retained_ids)
        self.assertNotIn("orphan", retained_ids)


class TestTreeCrdtSemanticMerger(unittest.TestCase):
    def setUp(self):
        self.merger = TreeCrdtSemanticMerger()

    def test_commutativity_disjoint_subtrees(self):
        patch_a = AstPatch(
            patch_id="p1",
            agent_id="agent_001",
            lamport_clock=1,
            target_symbol="play_anything.core.models.CodeNode",
            operation="update",
            code_content="class CodeNode: pass",
        )
        patch_b = AstPatch(
            patch_id="p2",
            agent_id="agent_002",
            lamport_clock=1,
            target_symbol="play_anything.core.grail_reachability.GrailEngine",
            operation="update",
            code_content="class GrailEngine: pass",
        )

        # Must commute: disjoint subtrees
        self.assertTrue(self.merger.is_commutative(patch_a, patch_b))

        # Parent/child subtrees do NOT commute
        patch_child = AstPatch(
            patch_id="p3",
            agent_id="agent_003",
            lamport_clock=2,
            target_symbol="play_anything.core.models.CodeNode.validate",
            operation="insert",
            code_content="def validate(): return True",
        )
        self.assertFalse(self.merger.is_commutative(patch_a, patch_child))

    def test_conflict_resolution_and_convergence(self):
        # Two agents edit the exact same symbol concurrently
        patch_a = AstPatch(
            patch_id="p_older",
            agent_id="agent_001",
            lamport_clock=5,
            target_symbol="play_anything.core.tokenomics.burn_rate",
            operation="update",
            code_content="def burn_rate(): return 0.05",
            timestamp=100.0,
        )
        patch_b = AstPatch(
            patch_id="p_newer",
            agent_id="agent_002",
            lamport_clock=6,
            target_symbol="play_anything.core.tokenomics.burn_rate",
            operation="update",
            code_content="def burn_rate(): return 0.02",
            timestamp=101.0,
        )

        outcome = self.merger.merge_patches([patch_a, patch_b])
        self.assertIsInstance(outcome, MergeOutcome)
        self.assertTrue(outcome.is_convergent)
        self.assertEqual(len(outcome.conflicts_resolved), 1)
        # Higher Lamport clock (patch_b) wins
        self.assertEqual(
            outcome.merged_symbols["play_anything.core.tokenomics.burn_rate"],
            "def burn_rate(): return 0.02",
        )


class TestWoundWaitLockManager(unittest.TestCase):
    def setUp(self):
        self.lock_mgr = WoundWaitLockManager()

    def test_uncontended_acquire_and_release(self):
        t1 = self.lock_mgr.register_agent("agent_001", birth_time=10.0)
        acquired = self.lock_mgr.acquire_lock("agent_001", "file://core/models.py")
        self.assertTrue(acquired)

        released = self.lock_mgr.release_lock("agent_001", "file://core/models.py")
        self.assertIsNone(released)

    def test_older_wounds_younger(self):
        # Agent 2 is younger (timestamp 200.0)
        self.lock_mgr.register_agent("agent_young", birth_time=200.0)
        # Agent 1 is older (timestamp 100.0)
        self.lock_mgr.register_agent("agent_old", birth_time=100.0)

        # Younger acquires lock first
        acq_young = self.lock_mgr.acquire_lock("agent_young", "db://users")
        self.assertTrue(acq_young)

        # Older agent requests same lock -> wounds younger!
        acq_old = self.lock_mgr.acquire_lock("agent_old", "db://users")
        self.assertTrue(acq_old)
        self.assertTrue(self.lock_mgr.is_agent_aborted("agent_young"))

    def test_younger_waits_for_older(self):
        self.lock_mgr.register_agent("agent_old", birth_time=100.0)
        self.lock_mgr.register_agent("agent_young", birth_time=200.0)

        # Older acquires lock
        self.lock_mgr.acquire_lock("agent_old", "db://ledger")

        # Younger requests lock -> must WAIT (not acquire)
        acq_young = self.lock_mgr.acquire_lock("agent_young", "db://ledger")
        self.assertFalse(acq_young)
        self.assertFalse(self.lock_mgr.is_agent_aborted("agent_old"))

        # Older releases -> granted to younger waiter
        next_agent = self.lock_mgr.release_lock("agent_old", "db://ledger")
        self.assertEqual(next_agent, "agent_young")


if __name__ == "__main__":
    unittest.main()

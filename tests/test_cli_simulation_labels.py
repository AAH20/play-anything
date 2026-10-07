"""CLI labels distinguish simulated demos from executed work."""
import contextlib
import io
import unittest
from unittest.mock import patch

from play_anything import cli


class CLISimulationLabelTests(unittest.TestCase):
    def test_play_labels_supplied_patch_and_test_result_as_simulated(self):
        output = io.StringIO()
        with patch(
            "play_anything.adapters.computer_use_sandbox_adapter.ComputerUseSandboxAdapter.execute_boss_battle_round",
            return_value={
                "battle_status": "DEFEAT_OR_PENALTY",
                "verdict": "REJECTED_TEST_FAILURE",
                "xp_awarded": 0,
                "combat_log": "Demo verifier rejected supplied result.",
                "consensus_score": 0.25,
                "execution_time_us": 12.5,
            },
        ), contextlib.redirect_stdout(output):
            cli.run_play_interactive()

        text = output.getvalue()
        self.assertIn("SIMULATED", text)
        self.assertIn("No patch application, sandbox, shell, or test runner is executed", text)
        self.assertIn("+ export function secureValidate()", text)
        self.assertIn("4 passed in 0.12s", text)
        self.assertIn("DEFEAT_OR_PENALTY", text)
        self.assertIn("12.5 µs", text)
        self.assertNotIn("QUEST COMPLETE", text)
        self.assertNotIn("LEVEL UP!", text)
        self.assertNotIn("< 1 millisecond", text)

    def test_benchmark_labels_cpu_time_and_modeled_metrics(self):
        rows = [
            {"solver": "P5_Voice_Intent_Router", "metric": "total_rt=110ms, deadline_ok=True", "latency_us": 42.0},
            {"solver": "P7_Sandbox_Scheduler", "metric": "makespan=145ms, deadlock_free=True", "latency_us": 30.0},
            {"solver": "P1_Skill_Tree_Induction", "metric": "skills=4", "latency_us": 10.0},
        ]
        output = io.StringIO()
        with patch.object(cli.PlayAnythingEngine, "run_full_benchmark_suite", return_value=rows), \
                contextlib.redirect_stdout(output):
            cli.run_benchmark_all()

        text = output.getvalue()
        self.assertIn("SYNTHETIC FIXTURES", text)
        self.assertIn("Each solver runs once", text)
        self.assertIn("modeled speech round-trip", text)
        self.assertIn("planned schedule (not executed)", text)
        self.assertIn("One-shot solver elapsed (µs)", text)
        self.assertIn("Summed one-shot solver elapsed time", text)
        self.assertNotIn("solver CPU", text)
        self.assertNotIn("Total Combined Pipeline Benchmark Execution", text)


if __name__ == "__main__":
    unittest.main()

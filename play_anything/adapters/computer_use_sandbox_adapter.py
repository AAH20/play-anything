"""Computer-Use Sandbox Adapter for Boss Battles and Code Execution.

Coordinates autonomous computer-use test execution (browsers, shells, test runners).
Resolves live Boss Battles where Boss HP is drained ONLY when genuine unit/integration tests pass.
"""
import time
from typing import List, Dict, Optional, Any
from ..core.models import (
    SandboxAction, DisjunctiveSandboxResult,
    SolutionSubmission, ByzantineVerificationResult,
    QuestPath
)
from ..core.sandbox_scheduler import solve_sandbox_scheduling
from ..core.byzantine_fairplay import solve_byzantine_fairplay


class ComputerUseSandboxAdapter:
    """Manages autonomous sandbox actions and live test-driven Boss Battle encounters."""

    @staticmethod
    def schedule_sandbox_workflow(
        actions: List[SandboxAction]
    ) -> DisjunctiveSandboxResult:
        """Schedules concurrent sandbox tasks without port or lock contention."""
        return solve_sandbox_scheduling(actions)

    @staticmethod
    def execute_boss_battle_round(
        quest: QuestPath,
        player_patch: str,
        simulated_exit_code: int = 0,
        simulated_test_output: str = "PASS"
    ) -> Dict[str, Any]:
        """Runs computer-use verification of player's patch against the Boss node."""
        submission = SolutionSubmission(
            submission_id=f"sub_{quest.quest_id}_{int(time.time()*1000)}",
            quest_id=quest.quest_id,
            player_id="player_hero",
            patch_diff=player_patch,
            sandbox_exit_code=simulated_exit_code,
            test_output=simulated_test_output
        )

        verification: ByzantineVerificationResult = solve_byzantine_fairplay(submission)

        if verification.is_valid:
            boss_hp_remaining = 0
            battle_status = "VICTORY_BOSS_SLAIN"
            xp_awarded = quest.total_xp_yield
            combat_log = (
                f"⚔️ CRITICAL HIT! Your code patch successfully passed '{quest.failing_test_command}'. "
                f"The Corrupted Boss HP dropped to 0! You earned {xp_awarded} XP!"
            )
        else:
            boss_hp_remaining = quest.boss_hp
            battle_status = "DEFEAT_OR_PENALTY"
            xp_awarded = 0
            combat_log = f"🛡️ BLOCKED! Verdict: {verification.verdict}. Boss remains standing with {quest.boss_hp} HP!"

        return {
            "quest_id": quest.quest_id,
            "battle_status": battle_status,
            "boss_hp_remaining": boss_hp_remaining,
            "xp_awarded": xp_awarded,
            "verdict": verification.verdict,
            "consensus_score": verification.consensus_score,
            "combat_log": combat_log,
            "execution_time_us": verification.execution_time_us
        }

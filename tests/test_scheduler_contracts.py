"""Scheduling constraints and invalid-input contracts, independent of toy timings."""

import unittest

from play_anything.core.models import SandboxAction
from play_anything.core.sandbox_scheduler import solve_sandbox_scheduling


def action(identifier, resource='shell', duration=4, dependencies=None, release=0):
    return SandboxAction(identifier, identifier, resource, duration,
                         dependencies or [], release)


class SchedulerContracts(unittest.TestCase):
    def test_unknown_dependency_cannot_be_reported_as_deadlock_free(self):
        with self.assertRaisesRegex(ValueError, 'dependency'):
            solve_sandbox_scheduling([action('build', dependencies=['missing'])])

    def test_duplicate_ids_do_not_silently_replace_jobs(self):
        with self.assertRaisesRegex(ValueError, 'unique'):
            solve_sandbox_scheduling([action('build'), action('build', 'browser')])

    def test_invalid_timing_rejected(self):
        for value in (-1, True, 1.5, float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                solve_sandbox_scheduling([action('build', duration=value)])
            with self.subTest(release=value), self.assertRaises(ValueError):
                solve_sandbox_scheduling([action('build', release=value)])

    def test_tie_break_is_independent_of_input_order(self):
        jobs = [action('z'), action('a')]
        forward = solve_sandbox_scheduling(jobs)
        reverse = solve_sandbox_scheduling(list(reversed(jobs)))
        self.assertEqual(forward.schedule, reverse.schedule)

    def test_releases_dependencies_and_shared_resource_are_respected(self):
        jobs = [action('build', duration=7, release=3),
                action('lint', duration=5),
                action('browser', 'browser', 2, ['build', 'lint'])]
        result = solve_sandbox_scheduling(jobs)
        self.assertTrue(result.deadlock_free)
        by_id = {job.action_id: job for job in jobs}
        for job in jobs:
            start = result.schedule[job.action_id]
            self.assertGreaterEqual(start, job.release_ms)
            for predecessor in job.precedence_deps:
                self.assertGreaterEqual(start, result.schedule[predecessor] + by_id[predecessor].duration_ms)
        a, b = (result.schedule[name] for name in ('build', 'lint'))
        self.assertTrue(a + 7 <= b or b + 5 <= a)
        self.assertEqual(result.makespan_ms, max(result.schedule[job.action_id] + job.duration_ms for job in jobs))

    def test_cycle_remains_explicitly_unschedulable(self):
        result = solve_sandbox_scheduling([action('a', dependencies=['b']),
                                          action('b', dependencies=['a'])])
        self.assertFalse(result.deadlock_free)
        self.assertEqual(result.schedule, {})

    def test_zero_duration_checkpoint_is_valid(self):
        result = solve_sandbox_scheduling([action('checkpoint', duration=0),
                                          action('build', dependencies=['checkpoint'])])
        self.assertTrue(result.deadlock_free)
        self.assertEqual(result.makespan_ms, 4)

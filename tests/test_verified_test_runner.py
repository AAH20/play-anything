"""The release verifier must reject finalizer leaks that unittest ignores."""

import io
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest
import warnings

from scripts.run_verified_tests import run_verified_suite


class VerifiedTestRunnerTests(unittest.TestCase):
    def _run(self, body):
        case = unittest.FunctionTestCase(body)
        output = io.StringIO()
        result, ignored = run_verified_suite(unittest.TestSuite([case]), stream=output, verbosity=0)
        return result, ignored, output.getvalue()

    def test_clean_suite_passes_and_restores_hook_and_warning_filters(self):
        hook = sys.unraisablehook
        filters = warnings.filters[:]
        result, ignored, _ = self._run(lambda: None)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(ignored, {})
        self.assertIs(sys.unraisablehook, hook)
        self.assertEqual(warnings.filters, filters)

    def test_ignored_finalizer_error_makes_successful_unittest_run_fail_verification(self):
        class BrokenFinalizer:
            def __del__(self):
                raise RuntimeError('private-finalizer-marker')

        def body():
            value = BrokenFinalizer()
            del value

        result, ignored, output = self._run(body)
        self.assertTrue(result.wasSuccessful())  # This is the misleading ordinary outcome.
        self.assertEqual(ignored, {'RuntimeError': 1})
        self.assertIn('FAILED verification', output)
        self.assertNotIn('private-finalizer-marker', output)

    def test_cyclic_resource_warning_is_collected_before_verification_completes(self):
        class LeakedResource:
            def __del__(self):
                warnings.warn('private-resource-marker', ResourceWarning)

        def body():
            value = LeakedResource()
            value.cycle = value

        result, ignored, output = self._run(body)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(ignored, {'ResourceWarning': 1})
        self.assertNotIn('private-resource-marker', output)

    def test_normal_test_failures_remain_failures(self):
        def body():
            self.assertEqual(1, 2)

        result, ignored, _ = self._run(body)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(ignored, {})

    def test_cli_exits_nonzero_for_an_ignored_resource_finalizer(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'test_leak.py').write_text(
                'import unittest, warnings\n'
                'class Leaked:\n'
                ' def __del__(self): warnings.warn("secret-marker", ResourceWarning)\n'
                'class Case(unittest.TestCase):\n'
                ' def test_leak(self):\n'
                '  resource=Leaked(); resource.cycle=resource\n')
            runner = Path(__file__).resolve().parents[1] / 'scripts' / 'run_verified_tests.py'
            completed = subprocess.run([sys.executable, str(runner), '--start-dir', directory],
                                       capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertIn('ResourceWarning=1', completed.stderr)
        self.assertNotIn('secret-marker', completed.stderr)

    def test_interruption_restores_process_hook(self):
        original = sys.unraisablehook

        def body():
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self._run(body)
        self.assertIs(sys.unraisablehook, original)


if __name__ == '__main__':
    unittest.main()

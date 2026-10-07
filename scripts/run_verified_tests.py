"""Run unittest while also failing on otherwise ignored finalizer exceptions.

The regular unittest command remains supported. This development runner adds a
process-wide unraisable-exception check, including ResourceWarning finalizers
that ``-W error`` alone reports without making unittest fail.
"""

import argparse
from collections import Counter
import gc
from pathlib import Path
import sys
import unittest
import warnings


def run_verified_suite(suite, *, stream=None, verbosity=1):
    """Return (test result, exception-type counts) and restore global hooks."""
    output = sys.stderr if stream is None else stream
    unraisable = Counter()
    previous_hook = sys.unraisablehook

    def capture(event):
        # Retaining event/object/traceback can resurrect objects during GC. Record
        # only the exception type; never echo a finalizer's object or arguments.
        unraisable[event.exc_type.__name__] += 1

    try:
        sys.unraisablehook = capture
        with warnings.catch_warnings():
            warnings.simplefilter('error', ResourceWarning)
            result = unittest.TextTestRunner(stream=output, verbosity=verbosity).run(suite)
            # TestSuite releases executed cases. Collect cycles while our hook is
            # active instead of allowing leaks to surface after a successful exit.
            gc.collect()
    finally:
        sys.unraisablehook = previous_hook
    if unraisable:
        counts = ', '.join(f'{name}={count}' for name, count in sorted(unraisable.items()))
        output.write(f'FAILED verification: ignored finalizer exceptions ({counts})\n')
    return result, dict(unraisable)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-dir', default='tests')
    parser.add_argument('--pattern', default='test*.py')
    parser.add_argument('--verbosity', type=int, choices=(0, 1, 2), default=1)
    args = parser.parse_args(arguments)
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository))
    suite = unittest.defaultTestLoader.discover(args.start_dir, pattern=args.pattern)
    result, unraisable = run_verified_suite(suite, verbosity=args.verbosity)
    return 0 if result.wasSuccessful() and not unraisable else 1


if __name__ == '__main__':
    sys.exit(main())

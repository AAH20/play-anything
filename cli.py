#!/usr/bin/env python3
"""Root executable CLI entrypoint for Play-Anything."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from play_anything.cli import main

if __name__ == "__main__":
    sys.exit(main())

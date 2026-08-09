#!/usr/bin/env python3
"""Run the imported priority simulation before every existing live suite."""

from __future__ import annotations

import os
import subprocess
import sys


DEFAULT_COMMANDS = [
    [sys.executable, "scripts/test_live.py"],
    [sys.executable, "test_all.py"],
    [sys.executable, "test_live_full.py"],
    [sys.executable, "test_new_features.py"],
    [sys.executable, "test_simulations.py"],
    [sys.executable, "test_simulations_2.py"],
    [sys.executable, "scripts/test_e2e.py"],
    [sys.executable, "scripts/test_notification_system.py"],
    [sys.executable, "-m", "pytest", "tests/", "-v"],
]


def main() -> int:
    commands = [[sys.executable, "scripts/priority_live_simulation.py"], *DEFAULT_COMMANDS]
    failures = 0
    for command in commands:
        print("\n>>>", " ".join(command), flush=True)
        result = subprocess.run(command, env=os.environ.copy())
        if result.returncode:
            failures += 1
            print(f"<<< failed with exit code {result.returncode}", flush=True)
    print(f"\nLive suite complete: {len(commands) - failures}/{len(commands)} commands passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())